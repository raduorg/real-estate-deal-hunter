from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse

import httpx

from src.email_listener.parsers import (
    decode_imobiliare_tracking,
    is_tracking_url,
    normalize_listing_url,
)

logger = logging.getLogger(__name__)

# Paths that mark a resolved URL as an actual listing page (not homepage/contact/etc).
_LISTING_PATH_RE = re.compile(r"/(?:oferta|anunturi|detalii)/|/\d{6,}$", re.IGNORECASE)

_TRACKING_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
}


def _is_listing_path(url: str) -> bool:
    path = urlparse(url).path
    return bool(_LISTING_PATH_RE.search(path))


# Only these portal hosts count as listings (blocks LinkedIn, login pages, CDNs, etc).
_PORTAL_HOST_HINT = ("imobiliare.ro", "storia.ro", "olx.ro", "publi24.ro", "olx.pl")


def _is_listing_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return any(d in host for d in _PORTAL_HOST_HINT) and _is_listing_path(url)


class TrackingResolver:
    """Resolve email tracking links to canonical listing URLs."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=_TRACKING_HEADERS,
                follow_redirects=True,
                limits=httpx.Limits(max_connections=5),
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def resolve(self, url: str) -> str | None:
        """Return a canonical listing URL, or None if it's not a listing."""
        try:
            hostname = urlparse(url).hostname or ""
            if "link.imobiliare" in hostname:
                canonical = decode_imobiliare_tracking(url)
            elif is_tracking_url(url):
                canonical = await self._follow(url)
            else:
                # Direct listing URL — validate it looks like a real listing.
                canonical = url

            if canonical and _is_listing_url(canonical):
                return normalize_listing_url(canonical)
            return None
        except Exception:
            logger.warning("Failed to resolve tracking URL: %s", url, exc_info=True)
            return None

    async def _follow(self, url: str) -> str | None:
        client = await self._get_client()
        resp = await client.get(url)
        if resp.status_code not in (200, 301, 302, 303, 307, 308):
            return None
        return str(resp.url)

    async def resolve_many(self, urls: list[str]) -> list[str]:
        """Resolve a batch of URLs (deduped by normalised URL), preserving order."""
        logger.info("Resolving %d candidate URL(s)...", len(urls))
        results = await asyncio.gather(*(self.resolve(u) for u in urls))
        canonical: list[str] = []
        seen: set[str] = set()
        for resolved in results:
            if resolved and resolved not in seen:
                seen.add(resolved)
                canonical.append(resolved)
        logger.info("Resolved %d URL(s) to canonical listing(s)", len(canonical))
        return canonical