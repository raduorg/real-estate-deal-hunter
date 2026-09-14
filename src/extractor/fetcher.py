from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field

import httpx

from src.config import ExtractorConfig

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
        "image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.google.com/",
}

# Transient / challenge status codes worth retrying with a cooldown.
_RETRYABLE_STATUS = {403, 405, 408, 425, 429, 500, 502, 503, 504}

# Cheap markers used by Cloudflare / AWS WAF on the Romanian portals.
_BOT_MARKERS = (
    "just a moment",
    "attention required",
    "cf-chl",
    "__cf_chl_",
    "access denied",
    "verify you are human",
    "captcha",
    "request could not be satisfied",
    "request blocked",
    "arm yourself",
)


@dataclass
class FetchResult:
    url: str
    status: int = 0
    html: str = ""
    bot_blocked: bool = False
    success: bool = False
    error: str = ""
    attempts: int = 0
    _closed: bool = field(default=False, repr=False)


def _is_bot_blocked(html: str, status: int) -> bool:
    if status not in (401, 403, 405, 503):
        return False
    snippet = html[:4000].lower() if html else ""
    return any(marker in snippet for marker in _BOT_MARKERS)


class PageFetcher:
    """Fetches listing pages with browser-like headers and anti-bot discipline.

    - Sequential requests only (single connection) to mimic a human tab.
    - Random 5-15s pause between requests (conservative rate).
    - Retries with exponential backoff on transient/rate-limit statuses,
      but never hammers a page already identified as a bot challenge.
    """

    def __init__(
        self,
        config: ExtractorConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._last_fetch_at = 0.0

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                transport=self._transport,
                headers=BROWSER_HEADERS,
                follow_redirects=True,
                timeout=httpx.Timeout(self.config.timeout),
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
                proxy=self.config.proxy_url or None,
            )
        return self._client

    async def _respect_rate_limit(self) -> None:
        now = asyncio.get_running_loop().time()
        elapsed = now - self._last_fetch_at
        if self._last_fetch_at and elapsed < self.config.min_delay:
            wait = random.uniform(self.config.min_delay, self.config.max_delay)
            logger.debug("Rate limiting: sleeping %.1fs before next fetch", wait)
            await asyncio.sleep(wait)
        self._last_fetch_at = asyncio.get_running_loop().time()

    async def fetch(self, url: str) -> FetchResult:
        await self._respect_rate_limit()
        client = await self._ensure_client()
        result = FetchResult(url=url)

        for attempt in range(1, self.config.max_retries + 1):
            result.attempts = attempt
            try:
                response = await client.get(url)
            except httpx.TimeoutException as exc:
                logger.debug("Timeout fetching %s (attempt %d): %s", url, attempt, exc)
                if attempt >= self.config.max_retries:
                    result.error = f"timeout: {type(exc).__name__}"
                    logger.warning("Giving up on %s after %d attempts", url, attempt)
                    return result
                await self._backoff(attempt, base=3.0)
                continue
            except httpx.HTTPError as exc:
                result.error = f"{type(exc).__name__}: {exc}"
                if attempt >= self.config.max_retries:
                    logger.warning(
                        "Giving up on %s after %d attempts: %s", url, attempt, result.error
                    )
                    return result
                await self._backoff(attempt)
                continue

            result.status = response.status_code
            result.html = response.text
            result.bot_blocked = _is_bot_blocked(result.html, response.status_code)

            if result.bot_blocked:
                result.success = False
                logger.info(
                    "Bot challenge for %s (HTTP %d); not retrying", url, response.status_code
                )
                return result

            if response.status_code == httpx.codes.OK:
                result.success = True
                logger.debug("Fetched %s (%d bytes)", url, len(result.html))
                return result

            if response.status_code in _RETRYABLE_STATUS and attempt < self.config.max_retries:
                logger.info(
                    "HTTP %d for %s (attempt %d/%d), backing off",
                    response.status_code,
                    url,
                    attempt,
                    self.config.max_retries,
                )
                await self._backoff(attempt)
                continue

            result.success = False
            result.error = f"unexpected HTTP {response.status_code}"
            logger.warning("Fetch failed for %s: %s", url, result.error)
            return result

        result.success = False
        return result

    async def _backoff(self, attempt: int, base: float = 2.0) -> None:
        delay = base**attempt + random.uniform(0, 1.0)
        logger.debug("Backoff %.1fs before retry", delay)
        await asyncio.sleep(delay)
