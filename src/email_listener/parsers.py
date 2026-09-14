from __future__ import annotations

import hashlib
import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.models.listing import Listing, ListingSource

logger = logging.getLogger(__name__)

# Romanian price/sqm patterns
_PRICE_RE = re.compile(r"([\d.]+)\s*(eur|€|euro|lei|ron)", re.IGNORECASE)
_SQM_RE = re.compile(r"(\d+)\s*m[²2]")
_ROOMS_RE = re.compile(r"(\d+)\s*camer[ăa]|(\d+)\s*room", re.IGNORECASE)


def _source_from_url(url: str) -> ListingSource:
    host = urlparse(url).hostname or ""
    if "imobiliare" in host:
        return ListingSource.IMOBILIARE
    if "storia" in host:
        return ListingSource.STORIA
    if "olx" in host:
        return ListingSource.OLX
    if "publi24" in host:
        return ListingSource.PUBLI24
    return ListingSource.UNKNOWN


def _make_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _parse_price(text: str) -> int | None:
    m = _PRICE_RE.search(text)
    if not m:
        return None
    raw = m.group(1).replace(".", "")
    currency = m.group(2).lower()
    val = int(raw)
    if currency in ("lei", "ron"):
        val = int(val / 5)  # approximate RON->EUR
    return val


def _parse_sqm(text: str) -> int | None:
    m = _SQM_RE.search(text)
    return int(m.group(1)) if m else None


def _parse_rooms(text: str) -> int | None:
    m = _ROOMS_RE.search(text)
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def extract_listing_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    urls = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if _looks_like_listing_url(href):
            urls.add(href)
    return list(urls)


def _looks_like_listing_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    is_portal = any(
        d in host for d in ("imobiliare.ro", "storia.ro", "olx.ro", "publi24.ro", "olx.pl")
    )
    path = urlparse(url).path
    has_id = bool(re.search(r"/\d+$", path)) or bool(re.search(r"/oferta/", path))
    return is_portal and has_id


def parse_email(
    html: str,
    subject: str = "",
    email_date: str | None = None,
) -> list[Listing]:
    urls = extract_listing_urls(html)
    if not urls:
        logger.debug("No listing URLs found in email")
        return []

    listings = []
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ")

    price = _parse_price(text)
    sqm = _parse_sqm(text)
    rooms = _parse_rooms(text)

    for url in urls:
        listing = Listing(
            id=_make_id(url),
            url=url,
            source=_source_from_url(url),
            title=subject[:200],
            price_eur=price,
            sqm=sqm,
            rooms=rooms,
            email_subject=subject,
            email_date=email_date,
        )
        listings.append(listing)

    logger.info("Extracted %d listing(s) from email: %s", len(listings), subject[:80])
    return listings
