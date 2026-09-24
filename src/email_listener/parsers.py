from __future__ import annotations

import base64
import hashlib
import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from src.models.listing import Listing, ListingSource

logger = logging.getLogger(__name__)

# Romanian price/sqm patterns
_PRICE_RE = re.compile(r"([\d.]+)\s*(eur|€|euro|lei|ron)", re.IGNORECASE)
_SQM_RE = re.compile(r"(\d+)\s*m[²2]")
_ROOMS_RE = re.compile(r"(\d+)\s*camer[ăa]|(\d+)\s*room", re.IGNORECASE)

# Tracking/redirect link domains used by portal email alerts.
_TRACKING_HOSTS = (
    "link.imobiliare.ro",
    "clicks.alerts.storia.ro",
)
# Recognised listing path markers (used to validate resolved URLs).
_LISTING_PATH_RE = re.compile(r"/(?:oferta|ro/oferta|autobuz)/|\d{6,}$")


def _source_from_url(url: str) -> ListingSource:
    host = urlsplit(url).hostname or ""
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
    return hashlib.sha256(normalize_listing_url(url).encode()).hexdigest()[:16]


# Query params injected by email tracking redirects; not part of a listing identity.
_TRACKING_PARAMS = {"lid", "utm_source", "utm_medium", "utm_campaign", "utm_id", "utm_content"}


def normalize_listing_url(url: str) -> str:
    """Strip email-tracking query params so identical listings deduplicate."""
    parts = urlsplit(url)
    keep = [(k, v) for k, v in parse_qsl(parts.query) if k not in _TRACKING_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(keep), parts.fragment))


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


def _unwrap_auto_login(decoded: str) -> str | None:
    """Extract the real listing URL from an imobiliare `/auto-login/` target.

    Alert card links decode to an `auto-login` URL that carries the actual
    listing page in its `redirectUrl` query param. Non-listing auto-login
    targets (no redirectUrl) return None.
    """
    parts = urlsplit(decoded)
    if not parts.path.startswith("/auto-login"):
        return decoded
    params = dict(parse_qsl(parts.query))
    redirect = params.get("redirectUrl", "")
    if redirect.startswith("http"):
        return redirect
    return None


def decode_imobiliare_tracking(url: str) -> str | None:
    """Decode the base64-encoded target from a link.imobiliare.ro/click/... URL.

    Only `/click/` links point at portal pages; `/external/` links are social
    media profile URLs and are rejected. `/auto-login/` targets are unwrapped
    to the real listing URL carried in `redirectUrl`.
    """
    path = urlsplit(url).path
    # require /click/<id>/<b64> (not /external/<id>/<b64>)
    if "/click/" not in path:
        return None
    m = re.search(r"/click/[^/]+/([A-Za-z0-9_=-]+)", path)
    if not m:
        return None
    b64 = m.group(1)
    try:
        decoded = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-8", "replace")
    except Exception:
        return None
    if not decoded.startswith("http"):
        return None
    return _unwrap_auto_login(decoded)


def is_tracking_url(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return host in _TRACKING_HOSTS


def extract_listing_urls(html: str) -> list[str]:
    """Collect listing URLs + tracking links from an alert email."""
    soup = BeautifulSoup(html, "lxml")
    urls = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if _looks_like_listing_url(href) or is_tracking_url(href):
            urls.add(href)
    return list(urls)


def _looks_like_listing_url(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    is_portal = any(
        d in host for d in ("imobiliare.ro", "storia.ro", "olx.ro", "publi24.ro", "olx.pl")
    )
    if is_tracking_url(url):
        return True
    path = urlsplit(url).path
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

    soup = BeautifulSoup(html, "lxml")
    return build_listings(urls, soup.get_text(separator=" "), subject, email_date)


def _parse_email_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone()  # normalize to local tz (matches datetime.now())


def build_listings(
    urls: list[str],
    text: str,
    subject: str = "",
    email_date: str | None = None,
) -> list[Listing]:
    price = _parse_price(text)
    sqm = _parse_sqm(text)
    rooms = _parse_rooms(text)
    parsed_date = _parse_email_date(email_date)

    listings = []
    for url in urls:
        clean_url = normalize_listing_url(url)
        listing = Listing(
            id=_make_id(url),
            url=clean_url,
            source=_source_from_url(url),
            title=subject[:200],
            price_eur=price,
            sqm=sqm,
            rooms=rooms,
            email_subject=subject,
            email_date=parsed_date,
        )
        listings.append(listing)

    logger.info("Extracted %d listing(s) from email: %s", len(listings), subject[:80])
    return listings
