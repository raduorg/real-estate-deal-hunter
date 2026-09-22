"""Image fetching + validation for the vision evaluator.

Downloads listing images conservatively, keeps only decodable photos, and
returns them as base64 payloads for the Ollama vision endpoint.
"""

from __future__ import annotations

import asyncio
import base64
import logging

import httpx

from src.config import VisionConfig

logger = logging.getLogger(__name__)


def _sniff_format(data: bytes) -> str | None:
    """Classify image format from magic bytes, or None if not a supported photo."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def validate_image(data: bytes, content_type: str = "") -> bool:
    """A photo is usable only if it is a supported raster image.

    Magic-byte sniffing is authoritative; a non-empty `content-type` that does
    not look like an image is treated as a contradiction and rejects the file.
    """
    if not data or _sniff_format(data) is None:
        return False
    if content_type and not content_type.startswith("image/"):
        return False
    return True


def to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class ImageDownloader:
    """Downloads and validates a listing's photo set (bounded concurrency)."""

    def __init__(
        self,
        config: VisionConfig,
        transport: httpx.AsyncBaseTransport | None = None,
        concurrency: int = 4,
    ) -> None:
        self.config = config
        self._transport = transport
        self._concurrency = concurrency
        self._limits = httpx.Limits(
            max_connections=concurrency, max_keepalive_connections=concurrency
        )
        self._sem = asyncio.Semaphore(concurrency)

    async def download(
        self, urls: list[str], referer: str = ""
    ) -> list[bytes]:
        """Return validated raw photo bytes for up to max_images URLs."""
        urls = urls[: self.config.max_images]
        if not urls:
            return []

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            "Referer": referer or "https://www.google.com/",
        }
        async with httpx.AsyncClient(
            transport=self._transport,
            follow_redirects=True,
            timeout=httpx.Timeout(self.config.image_timeout),
            limits=self._limits,
            headers=headers,
        ) as client:
            tasks = [self._one(client, url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            photos = [
                data for data in results if isinstance(data, bytes) and data
            ]
            logger.debug(
                "Image download: %d/%d usable", len(photos), len(urls)
            )
            return photos

    async def _one(self, client: httpx.AsyncClient, url: str) -> bytes | None:
        async with self._sem:
            try:
                response = await client.get(url)
            except httpx.HTTPError:
                logger.debug("Image download failed: %s", url)
                return None
            if response.status_code != httpx.codes.OK:
                logger.debug("Image HTTP %d: %s", response.status_code, url)
                return None
            data = response.content
            if len(data) > self.config.max_image_bytes:
                logger.debug("Image too large (%d bytes): %s", len(data), url)
                return None
            if not validate_image(data, response.headers.get("content-type", "")):
                logger.debug("Image rejected (not a supported photo): %s", url)
                return None
            return data