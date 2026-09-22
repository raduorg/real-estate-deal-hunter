from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.models.extraction import PageExtraction
from src.models.listing import ListingSource

logger = logging.getLogger(__name__)

_MAX_SQM = 5000
_MAX_PRICE_EUR = 5_000_000
_MIN_PRICE_EUR = 2_000

_CDN_RE = re.compile(
    r"(?:\.|^)(?:"
    r"apollo\.olxcdn\.com|olxcdn\.com|"
    r"img\.imobiliare\.ro|imobiliare\.ro|"
    r"imgix\.net|"
    r"publi24\.ro"
    r")",
    re.IGNORECASE,
)
_IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|webp|avif)(?:[?#]|$)", re.IGNORECASE)
_FOTO_PATH_RE = re.compile(r"/fot(?:o|os?)/", re.IGNORECASE)

_CITY_RE = re.compile(
    r"bucure?sti|cluj[- ]napoca|timisoara|iasi|brasov|constanta|sibiu|oradea|"
    r"galati|arad|pitesti|ploiesti|tg[- ]mures|craiova",
    re.IGNORECASE,
)

_PRICE_KEYS = {"price", "pricevalue", "askingprice", "sale_price"}
_SQM_KEYS = {
    "surface",
    "sqm",
    "squaremeters",
    "usablearea",
    "areaused",
    "livingsurface",
    "supratafelocabila",
}
_ROOM_KEYS = {"rooms", "numberofrooms", "roomcount", "numrooms", "no_of_rooms", "camere"}
_LAT_KEYS = {"latitude", "lat"}
_LON_KEYS = {"longitude", "lon", "lng", "long"}
_IMAGE_KEY_HINTS = ("image", "photo", "picture", "gallery", "thumb", "img")
_LOCATION_KEYS = {
    "city": {"city", "locality", "town", "oraș", "oras"},
    "neighborhood": {
        "neighborhood",
        "neighbourhood",
        "district",
        "sector",
        "zone",
        "cartier",
        # "area" is ambiguous (often usable sqm) — handled via _is_location_value.
    },
    "address": {"address", "street", "streetaddress", "displayaddress"},
}

# A neighborhood/city/address is text; reject pure numbers and sqm-style values
# (e.g. storia's `"Area":"39.36"`), which would otherwise leak into `neighborhood`.
_LOCATION_VALUE_RE = re.compile(r"^\d+(?:[.,]\d+)?\s*(?:m[²2]|m²|mp)?$", re.IGNORECASE)


def _is_location_value(value: str) -> bool:
    return bool(value) and not _LOCATION_VALUE_RE.match(value.strip())

_CURRENCY = r"(?:eur|€|euro|lei|ron)"
# "89.000 Euro", "89.000 €", "89 000 EUR", "€ 89.000" — currency required, avoids phone/date noise.
_PRICE_SUFFIX_RE = re.compile(
    rf"(?P<amount>\d{{1,4}}(?:[ .,']\d{{3}})+|\d{{5,8}})\s*(?P<cur>{_CURRENCY})(?!\w)",
    re.IGNORECASE,
)
_PRICE_PREFIX_RE = re.compile(
    rf"(?P<cur>{_CURRENCY})\s*(?P<amount>\d{{1,4}}(?:[ .,']\d{{3}})+|\d{{5,8}})(?!\w)",
    re.IGNORECASE,
)
_SQM_RE = re.compile(
    r"(?<![\d,.])(\d{1,4}(?:[.,]\d{1,2})?)\s*m(?:²|2|p(?![a-z])|p\.)(?!\d)",
    re.IGNORECASE,
)
_ROOMS_RE = re.compile(r"(?<!\d)(\d{1,2})\s*(?:camer[ăa]|camere|rooms?)\b", re.IGNORECASE)
_COORD_LAT_RE = re.compile(r'["\'](?:latitude|lat)["\']\s*[:=]\s*["\']?(-?\d{1,2}\.\d{4,12})["\']?')
_COORD_LON_RE = re.compile(
    r'["\'](?:longitude|lon|lng)["\']\s*[:=]\s*["\']?(-?\d{1,3}\.\d{4,12})["\']?'
)
_SCRIPT_BLOCK_RE = re.compile(r"<script([^>]*)>(.*?)</script>", re.S | re.I)
_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I
)
_SKIPPED_SCRIPT_TYPES = (
    "text/html",
    "text/template",
    "text/x-template",
    "text/ng-template",
    "application/ld+json",
)
_WHITESPACE_RE = re.compile(r"\s+")


def source_from_url(url: str) -> ListingSource:
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


# --------------------------------------------------------------------------- #
# Low-level JSON helpers
# --------------------------------------------------------------------------- #


def _safe_json_loads(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _iter_script_jsons(html: str) -> Iterator[dict]:
    """Yield parseable JSON dicts found inside executable <script> blocks."""
    for m in _SCRIPT_BLOCK_RE.finditer(html):
        attrs, body = m.group(1), m.group(2)
        if any(t in attrs.lower() for t in _SKIPPED_SCRIPT_TYPES):
            continue
        yield from _iter_json_objects(body)


def _iter_json_objects(text: str) -> Iterator[dict]:
    """Yield every valid JSON object in a JS-heavy blob using raw_decode scanning."""
    decoder = json.JSONDecoder()
    idx = 0
    size = len(text)
    while idx < size:
        try:
            idx = text.index("{", idx)
        except ValueError:
            return
        try:
            obj, consumed = decoder.raw_decode(text[idx:])
            if isinstance(obj, dict) and obj:
                yield obj
            idx += consumed
        except json.JSONDecodeError:
            idx += 1


def _iter_json_ld(html: str) -> Iterator[dict]:
    for m in _JSON_LD_RE.finditer(html):
        data = _safe_json_loads(m.group(1).strip())
        if isinstance(data, dict):
            yield data
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item


def _iter_dicts(node: Any) -> Iterator[dict]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_dicts(item)


def _iter_scalars(node: Any) -> Iterator[tuple[str, str]]:
    """Yield (key, string_value) for every string reachable in nested JSON."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str):
                yield key, value
            elif isinstance(value, dict):
                yield from _iter_scalars(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        yield key, item
                    elif isinstance(item, dict):
                        yield from _iter_scalars(item)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_scalars(item)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# --------------------------------------------------------------------------- #
# Pass 1: OpenGraph <meta> tags
# --------------------------------------------------------------------------- #


def _meta_content(soup: BeautifulSoup, prop: str | None = None, name: str | None = None) -> str:
    for attrs in ({"property": prop} if prop else None, {"name": name} if name else None):
        if not attrs:
            continue
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return _clean(tag["content"])
    return ""


def _clean(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


# --------------------------------------------------------------------------- #
# Pass 3: recursive JSON key scans
# --------------------------------------------------------------------------- #


def _price_from_json(node: Any) -> int | None:
    candidates: list[tuple[str | None, int]] = []
    for d in _iter_dicts(node):
        price = d.get("price")
        if isinstance(price, dict):
            price = price.get("value") or price.get("amount")
        if not _is_number(price):
            continue
        value = float(price)
        currency = d.get("priceCurrency") or d.get("currency")
        if isinstance(currency, str) and currency.lower() in ("ron", "lei"):
            value /= 5.0
        if _MIN_PRICE_EUR <= value <= _MAX_PRICE_EUR:
            candidates.append((currency, int(value)))
    if not candidates:
        return None
    for currency, value in candidates:
        if isinstance(currency, str) and currency.lower() in ("eur", "euro", "€"):
            return value
    for currency, value in candidates:
        if not isinstance(currency, str) or currency.lower() not in ("ron", "lei"):
            return value
    return candidates[0][1]


def _sqm_from_json(node: Any) -> float | None:
    for d in _iter_dicts(node):
        for key, value in d.items():
            if key.lower() not in _SQM_KEYS or not _is_number(value):
                continue
            sqm = float(value)
            if 1 <= sqm <= _MAX_SQM:
                return sqm
    return None


def _rooms_from_json(node: Any) -> int | None:
    for d in _iter_dicts(node):
        for key, value in d.items():
            if key.lower() not in _ROOM_KEYS or not _is_number(value):
                continue
            rooms = int(value)
            if 1 <= rooms <= 30:
                return rooms
    return None


def _coords_from_json(node: Any) -> tuple[float, float] | None:
    for d in _iter_dicts(node):
        lat = d.get("latitude")
        lon = d.get("longitude")
        if not _is_number(lat):
            lat = d.get("lat")
        if not _is_number(lon):
            lon = d.get("lon") or d.get("lng")
        if _is_number(lat) and _is_number(lon):
            lat_f, lon_f = float(lat), float(lon)
            if -90 <= lat_f <= 90 and -180 <= lon_f <= 180:
                return lat_f, lon_f
    return None


def _image_urls_from_json(nodes: list[Any]) -> list[str]:
    urls: list[str] = []
    for node in nodes:
        for key, value in _iter_scalars(node):
            if not value.startswith(("http://", "https://")):
                continue
            kl = key.lower()
            if not (any(h in kl for h in _IMAGE_KEY_HINTS) or _looks_like_photo(value)):
                continue
            urls.append(value)
    return urls


def _looks_like_photo(url: str) -> bool:
    return bool(_CDN_RE.search(url) or _IMAGE_EXT_RE.search(url) or _FOTO_PATH_RE.search(url))


# --------------------------------------------------------------------------- #
# Pass 4: regex on raw text
# --------------------------------------------------------------------------- #


def _price_from_text(text: str) -> int | None:
    for pattern in (_PRICE_PREFIX_RE, _PRICE_SUFFIX_RE):
        for m in pattern.finditer(text):
            amount = m.group("amount")
            currency = m.group("cur").lower()
            value = int(amount.replace(".", "").replace(" ", "").replace(",", "").replace("'", ""))
            if currency in ("lei", "ron"):
                value = int(value / 5)
            if _MIN_PRICE_EUR <= value <= _MAX_PRICE_EUR:
                return value
    return None


def _sqm_from_text(text: str) -> float | None:
    m = _SQM_RE.search(text)
    if not m:
        return None
    sqm = float(m.group(1).replace(",", "."))
    return sqm if 1 <= sqm <= _MAX_SQM else None


def _rooms_from_text(text: str) -> int | None:
    m = _ROOMS_RE.search(text)
    if m:
        return int(m.group(1))
    return None


def _coords_from_text(text: str) -> tuple[float, float] | None:
    lats = [float(x) for x in _COORD_LAT_RE.findall(text)]
    lons = [float(x) for x in _COORD_LON_RE.findall(text)]
    for lat, lon in zip(lats, lons):
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    return None


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #


def extract_from_html(
    html: str,
    *,
    listing_id: str,
    url: str = "",
    source: ListingSource = ListingSource.UNKNOWN,
    max_images: int = 15,
) -> PageExtraction:
    soup = BeautifulSoup(html, "lxml")
    text = _clean(soup.get_text(separator=" "))

    og_title = _meta_content(soup, prop="og:title")
    og_description = _meta_content(soup, prop="og:description")
    og_image = _meta_content(soup, prop="og:image")

    json_ld_nodes = list(_iter_json_ld(html))
    script_nodes = list(_iter_script_jsons(html))
    all_nodes = [*json_ld_nodes, *script_nodes]

    extraction = PageExtraction(listing_id=listing_id, url=url, source=source)

    # Title --------------------------------------------------------------- #
    og_default = (soup.title.string if soup.title else "") or ""
    title = og_title or _meta_content(soup, name="twitter:title") or og_default
    h1 = soup.find("h1")
    extraction.title = _clean(title) or (_clean(h1.get_text(" ", strip=True)) if h1 else "")
    for node in json_ld_nodes:
        if not extraction.title and node.get("name"):
            extraction.title = str(node["name"])

    # Description --------------------------------------------------------- #
    description = og_description or _meta_content(soup, name="description")
    for node in json_ld_nodes:
        if not description and node.get("description"):
            description = str(node["description"])
    extraction.description = _clean(description)

    # Price --------------------------------------------------------------- #
    # 1) og:description is portal-generated and short -> regex noise is minimal.
    price_method: str | None = None
    price: int | None = None
    meta_text = og_description or og_title
    if meta_text:
        price = _price_from_text(meta_text)
        if price is not None:
            price_method = "price_meta"
    if price is None:
        price = _price_from_json(all_nodes)
        if price is not None:
            price_method = "price_json"
    if price is None:
        price = _price_from_text(text[:6000])
        if price is not None:
            price_method = "price_text"
    extraction.price_eur = price
    if price_method:
        extraction.parse_methods.append(price_method)

    # Surface ------------------------------------------------------------- #
    sqm_method: str | None = None
    sqm: float | None = None
    if meta_text:
        sqm = _sqm_from_text(meta_text)
        if sqm is not None:
            sqm_method = "sqm_meta"
    if sqm is None:
        sqm = _sqm_from_json(all_nodes)
        if sqm is not None:
            sqm_method = "sqm_json"
    if sqm is None:
        sqm = _sqm_from_text(text[:6000])
        if sqm is not None:
            sqm_method = "sqm_text"
    extraction.sqm = sqm
    if sqm_method:
        extraction.parse_methods.append(sqm_method)

    # Rooms --------------------------------------------------------------- #
    rooms_method: str | None = None
    rooms: int | None = None
    if meta_text:
        rooms = _rooms_from_text(meta_text)
        if rooms is not None:
            rooms_method = "rooms_meta"
    if rooms is None:
        rooms = _rooms_from_json(all_nodes)
        if rooms is not None:
            rooms_method = "rooms_json"
    if rooms is None:
        rooms = _rooms_from_text(text[:6000])
        if rooms is not None:
            rooms_method = "rooms_text"
    extraction.rooms = rooms
    if rooms_method:
        extraction.parse_methods.append(rooms_method)

    # Location ------------------------------------------------------------ #
    for node in json_ld_nodes:
        if not extraction.city:
            extraction.city = _string_key(node, "addressLocality") or _string_key(node, "citytown")
        if not extraction.address:
            extraction.address = _string_key(node, "streetAddress") or _string_key(node, "address")
    if not extraction.city:
        loc = _location_from_title(extraction.title)
        if loc:
            extraction.city, extraction.neighborhood = loc
    if not extraction.address:
        extraction.address = _string_key_from_json(all_nodes, _LOCATION_KEYS["address"])
    if not extraction.city:
        extraction.city = _string_key_from_json(all_nodes, _LOCATION_KEYS["city"])
    if not extraction.neighborhood:
        extraction.neighborhood = _string_key_from_json(all_nodes, _LOCATION_KEYS["neighborhood"])

    # Coordinates --------------------------------------------------------- #
    coords = _coords_from_json(all_nodes)
    if coords is not None:
        extraction.latitude, extraction.longitude = coords
        extraction.parse_methods.append("coords_json")
    else:
        coords = _coords_from_text(html)
        if coords is not None:
            extraction.latitude, extraction.longitude = coords
            extraction.parse_methods.append("coords_regex")

    # Images -------------------------------------------------------------- #
    images = [og_image] if og_image else []
    for node in json_ld_nodes:
        for value in _image_scalars(node):
            images.append(value)
    images.extend(_image_urls_from_json(all_nodes))
    images.extend(_images_from_soup(soup))
    extraction.image_urls = _dedupe_http(images)[:max_images]
    if extraction.image_urls:
        extraction.parse_methods.append("images")

    extraction.parse_methods = list(dict.fromkeys(extraction.parse_methods))
    extraction.confidence = _confidence(extraction)
    return extraction


def _string_key(d: dict, key: str) -> str:
    value = d.get(key)
    if isinstance(value, str):
        return _clean(value)
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _string_key_from_json(nodes: list[Any], keys: set[str]) -> str:
    for node in nodes:
        for key, value in _iter_scalars(node):
            if key.lower() in keys and isinstance(value, str) and _is_location_value(value):
                return _clean(value)
    return ""


def _image_scalars(node: Any) -> Iterator[str]:
    for key, value in _iter_scalars(node):
        kl = key.lower()
        if kl in ("image", "images", "photo", "photos", "picture", "pictures") and value.startswith(
            ("http://", "https://")
        ):
            yield value


def _images_from_soup(soup: BeautifulSoup) -> list[str]:
    urls: list[str] = []
    for img in soup.find_all("img", src=True):
        src = img.get("src", "")
        data = img.get("data-src") or img.get("data-lazy") or ""
        for candidate in (src, data):
            if not candidate.startswith("data:"):
                urls.append(candidate)
    cleaned = []
    for url in urls:
        url = _normalize_image_url(url)
        if _looks_like_photo(url):
            cleaned.append(url)
    return cleaned


def _normalize_image_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url


def _dedupe_http(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned = []
    for url in urls:
        if not url:
            continue
        url = _normalize_image_url(url)
        if url in seen:
            continue
        seen.add(url)
        cleaned.append(url)
    return cleaned


def _location_from_title(title: str) -> tuple[str, str] | None:
    """Best-effort: '... - Bucuresti, Floreasca' or '... - Cluj-Napoca'."""
    tail = title.rsplit(" - ", 1)[-1] if " - " in title else ""
    if not tail:
        return None
    parts = [p.strip() for p in tail.split(",")]
    if not parts or not parts[0]:
        return None
    city = parts[0]
    if not _CITY_RE.search(city):
        return None
    neighborhood = parts[1] if len(parts) > 1 else ""
    return city, neighborhood


def _confidence(extraction: PageExtraction) -> float:
    fields = [
        bool(extraction.title),
        extraction.price_eur is not None,
        extraction.sqm is not None,
        extraction.latitude is not None and extraction.longitude is not None,
        bool(extraction.image_urls),
    ]
    return round(sum(1 for f in fields if f) / len(fields), 2)
