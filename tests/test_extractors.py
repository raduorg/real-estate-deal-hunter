# ruff: noqa: E501 - long HTML fixture lines are intentional
import aiosqlite
import httpx
import pytest

from src.config import ExtractorConfig
from src.email_listener.db import Database
from src.extractor.extractor import Extractor
from src.extractor.fetcher import PageFetcher
from src.extractor.parsers import extract_from_html
from src.models.extraction import PageExtraction
from src.models.listing import Listing, ListingSource, ListingStatus

OLX_STYLE_HTML = """<!DOCTYPE html>
<html>
<head>
<title>Apartament 2 camere, 60 mp, Bucuresti, Floreasca</title>
<meta property="og:title" content="Apartament 2 camere, 60 mp, 89.000 Euro - Bucuresti, Floreasca" />
<meta property="og:description" content="Apartament de vanzare, 2 camere, 60 mp, 89.000 Euro, etaj 4, bloc 1965, central, Floreasca - Bucuresti" />
<meta property="og:image" content="https://ireland.apollo.olxcdn.com/v1/files/abc1.jpg" />
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Product",
 "name": "Apartament 2 camere, 60 mp",
 "image": ["https://ireland.apollo.olxcdn.com/v1/files/abc2.jpg"],
 "offers": {"@type": "Offer", "price": 89000, "priceCurrency": "EUR"}}
</script>
<script>
window.__PRERENDERED_STATE__ = {"ad": {"id": 123,
 "map": {"center": {"latitude": 44.44610, "longitude": 26.09800}},
 "images": [{"url": "https://ireland.apollo.olxcdn.com/v1/files/abc3.jpg"}]}};
</script>
</head>
<body>
<h1>Apartament 2 camere, 60 mp - Bucuresti, Floreasca</h1>
<img src="https://ireland.apollo.olxcdn.com/v1/files/abc2.jpg" />
</body>
</html>
"""

IMOBILIARE_STYLE_HTML = """<!DOCTYPE html>
<html>
<head>
<meta property="og:title" content="Apartament 3 camere, 75 m², 119.000 Euro" />
<meta property="og:description" content="Apartament de vanzare 3 camere, 75 m², 119.000 Euro, etaj 2, central, Sector 2" />
<meta property="og:image" content="https://img.imobiliare.ro/foto/123/abc.jpg" />
<script>
dataLayer = [{"price": 119000, "currency": "EUR", "surface": 75, "rooms": 3,
              "lat": 44.45000, "lng": 26.12000}];
</script>
</head>
<body><h1>Apartament 3 camere - Bucuresti, Sector 2</h1></body>
</html>
"""

JSONLD_ONLY_HTML = """<!DOCTYPE html>
<html>
<head><title>Garsoniera moderna</title></head>
<body>
<script type="application/ld+json">
{"@type": "RealEstateListing",
 "name": "Garsoniera moderna",
 "description": "Renovata integral, de vanzare",
 "offers": {"price": 56000, "priceCurrency": "EUR"},
 "latitude": 44.40000, "longitude": 26.09000,
 "image": "https://ireland.apollo.olxcdn.com/v1/files/zz1.jpg"}
</script>
</body>
</html>
"""

BOT_CHALLENGE_HTML = """<!DOCTYPE html>
<html><head><title>Just a moment...</title></head>
<body><div>Checking your browser before accessing imobiliare.ro.</div></body>
</html>
"""


class TestExtractFromHtml:
    def test_olx_style_full(self):
        ext = extract_from_html(
            OLX_STYLE_HTML, listing_id="x1", url=OLX_URL, source=ListingSource.OLX
        )
        assert ext.title == "Apartament 2 camere, 60 mp, 89.000 Euro - Bucuresti, Floreasca"
        assert ext.price_eur == 89000
        assert ext.sqm == 60
        assert ext.rooms == 2
        assert ext.city.lower() == "bucuresti"
        assert ext.neighborhood.lower() == "floreasca"
        assert ext.latitude == pytest.approx(44.4461)
        assert ext.longitude == pytest.approx(26.098)
        assert ext.image_urls == [
            "https://ireland.apollo.olxcdn.com/v1/files/abc1.jpg",
            "https://ireland.apollo.olxcdn.com/v1/files/abc2.jpg",
            "https://ireland.apollo.olxcdn.com/v1/files/abc3.jpg",
        ]
        assert ext.confidence > 0.5

    def test_imobiliare_style(self):
        ext = extract_from_html(
            IMOBILIARE_STYLE_HTML, listing_id="x1", url="https://www.imobiliare.ro/x"
        )
        assert ext.price_eur == 119000
        assert ext.sqm == 75
        assert ext.rooms == 3
        assert ext.latitude == pytest.approx(44.45)
        assert ext.image_urls[0] == "https://img.imobiliare.ro/foto/123/abc.jpg"

    def test_jsonld_only_page(self):
        ext = extract_from_html(JSONLD_ONLY_HTML, listing_id="x1", url="https://www.storia.ro/x")
        assert ext.title == "Garsoniera moderna"
        assert ext.description == "Renovata integral, de vanzare"
        assert ext.price_eur == 56000
        assert ext.sqm is None
        assert ext.latitude == pytest.approx(44.4)
        assert len(ext.image_urls) == 1

    def test_image_cap(self):
        ext = extract_from_html(
            IMAGED_HTML, listing_id="x1", url="https://www.olx.ro/x", max_images=2
        )
        assert len(ext.image_urls) == 2

    def test_noisy_bot_page_is_empty(self):
        ext = extract_from_html(
            BOT_CHALLENGE_HTML, listing_id="x1", url="https://www.imobiliare.ro/x"
        )
        assert ext.price_eur is None
        assert ext.image_urls == []


OLX_URL = "https://www.olx.ro/d/oferta/apartament-2-camere-ID_F1.html"


def olx_img(file: str) -> str:
    return f'<img src="https://ireland.apollo.olxcdn.com/v1/files/{file}" />'


IMAGED_HTML = f"""<!DOCTYPE html>
<html><head>
<meta property="og:image" content="https://ireland.apollo.olxcdn.com/v1/files/0001.jpg" />
<script>
window.data = {{"profile": {{"images": [
  {{"url": "https://ireland.apollo.olxcdn.com/v1/files/0002.jpg"}},
  {{"url": "https://ireland.apollo.olxcdn.com/v1/files/0003.jpg"}},
  {{"url": "https://ireland.apollo.olxcdn.com/v1/files/0004.jpg"}},
  {{"url": "https://ireland.apollo.olxcdn.com/v1/files/0005.jpg"}}
]}}}}
</script>
</head><body>{olx_img("0001.jpg")}{olx_img("0002.jpg")}{olx_img("0003.jpg")}</body></html>"""


class TestExtractorOrchestration:
    async def test_process_new_with_mock_fetch(self, tmp_path):
        html = IMOBILIARE_STYLE_HTML
        transport = httpx.MockTransport(handler=lambda request: httpx.Response(200, text=html))
        config = ExtractorConfig(min_delay=0, max_delay=0, timeout=2, max_retries=2)
        db = Database(tmp_path / "t.db")
        await db.connect()

        listing = Listing(
            id="l1",
            url="https://www.imobiliare.ro/apartamente-de-vanzare/bucuresti/x-12345",
            source=ListingSource.IMOBILIARE,
        )
        assert await db.save_listing(listing)

        extractor = Extractor(PageFetcher(config, transport=transport), db, max_images=10)
        extracted = await extractor.process_new()

        assert extracted == 1
        check = Database(tmp_path / "t.db")
        await check.connect()
        rows = await check.get_listings_by_status(ListingStatus.EXTRACTED)
        assert len(rows) == 1
        assert rows[0].price_eur == 119000
        assert rows[0].sqm == 75
        page = await check.get_page("l1")
        assert page is not None and page.http_status == 200
        await check.close()

    async def test_failed_fetch_marks_skipped(self, tmp_path):
        transport = httpx.MockTransport(handler=lambda request: httpx.Response(503))
        config = ExtractorConfig(min_delay=0, max_delay=0, timeout=2, max_retries=1)
        db = Database(tmp_path / "t.db")
        await db.connect()
        listing = Listing(id="l2", url="https://www.storia.ro/x", source=ListingSource.STORIA)
        await db.save_listing(listing)

        extractor = Extractor(PageFetcher(config, transport=transport), db)
        result = await extractor.extract(listing)

        assert result is None
        assert await db.get_listings_by_status(ListingStatus.SKIPPED)
        page = await db.get_page("l2")
        assert page is not None and page.bot_blocked is False and page.http_status == 503
        await db.close()


class TestDatabaseMigration:
    OLD_SCHEMA = """
    CREATE TABLE listings (
        id TEXT PRIMARY KEY, url TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'unknown', title TEXT DEFAULT '',
        price_eur INTEGER, sqm INTEGER, rooms INTEGER,
        city TEXT DEFAULT '', neighborhood TEXT DEFAULT '', address TEXT DEFAULT '',
        image_urls TEXT DEFAULT '[]', status TEXT DEFAULT 'new',
        discovered_at TEXT NOT NULL, email_subject TEXT DEFAULT '', email_date TEXT
    );
    CREATE TABLE processed_emails (message_id TEXT PRIMARY KEY, processed_at TEXT NOT NULL);
    CREATE INDEX idx_listings_status ON listings(status);
    """

    async def test_old_db_migrated_and_usable(self, tmp_path):
        path = tmp_path / "old.db"
        conn = await aiosqlite.connect(path)
        await conn.executescript(self.OLD_SCHEMA)
        await conn.execute(
            "INSERT INTO listings (id, url, status, discovered_at) VALUES ('legacy', 'https://x.ro', 'new', '2026-01-01T00:00:00')"
        )
        await conn.commit()
        await conn.close()

        db = Database(path)
        await db.connect()

        extraction = PageExtraction(
            listing_id="legacy",
            url="https://x.ro",
            title="T",
            price_eur=90000,
            sqm=55.5,
            latitude=44.4,
            longitude=26.1,
        )
        await db.apply_extraction("legacy", extraction, ListingStatus.EXTRACTED)

        rows = await db.get_listings_by_status(ListingStatus.EXTRACTED)
        assert len(rows) == 1
        assert rows[0].sqm == 55.5
        assert rows[0].latitude == 44.4
        await db.close()


class TestZonePricingQueries:
    async def test_returns_all_statuses_and_excludes_invalid_values(self, tmp_path):
        db = Database(tmp_path / "zone-prices.db")
        await db.connect()
        try:
            listings = [
                Listing(
                    id="new",
                    url="https://example.test/new",
                    price_eur=100_000,
                    sqm=50,
                    status=ListingStatus.NEW,
                ),
                Listing(
                    id="skipped",
                    url="https://example.test/skipped",
                    price_eur=200_000,
                    sqm=50,
                    status=ListingStatus.SKIPPED,
                ),
                Listing(
                    id="alerted",
                    url="https://example.test/alerted",
                    price_eur=300_000,
                    sqm=50,
                    status=ListingStatus.ALERTED,
                ),
                Listing(
                    id="missing-price",
                    url="https://example.test/missing-price",
                    price_eur=None,
                    sqm=50,
                ),
                Listing(
                    id="invalid-area",
                    url="https://example.test/invalid-area",
                    price_eur=100_000,
                    sqm=0,
                ),
            ]
            for listing in listings:
                await db.save_listing(listing)

            rows = await db.get_listings_for_zone_pricing()

            assert {row.id for row in rows} == {"new", "skipped", "alerted"}
        finally:
            await db.close()


class TestFetcher:
    async def test_fetch_ok(self):
        config = ExtractorConfig(min_delay=0, max_delay=0, timeout=2, max_retries=2)
        fetcher = PageFetcher(
            config,
            transport=httpx.MockTransport(handler=lambda r: httpx.Response(200, text="<ok>")),
        )
        result = await fetcher.fetch("https://x.ro/a")
        assert result.success and result.status == 200 and not result.bot_blocked
        assert result.html == "<ok>"
        await fetcher.close()

    async def test_bot_challenge_detected_and_not_retried(self):
        config = ExtractorConfig(min_delay=0, max_delay=0, timeout=2, max_retries=5)
        fetcher = PageFetcher(
            config,
            transport=httpx.MockTransport(
                handler=lambda r: httpx.Response(403, text="<title>Just a moment...</title>")
            ),
        )
        result = await fetcher.fetch("https://x.ro/a")
        assert not result.success
        assert result.bot_blocked is True
        assert result.attempts == 1
        await fetcher.close()

    async def test_retry_then_success(self):
        calls = {"n": 0}

        async def handler(request):
            calls["n"] += 1
            if calls["n"] < 2:
                return httpx.Response(503, text="busy")
            return httpx.Response(200, text="ok")

        config = ExtractorConfig(min_delay=0, max_delay=0, timeout=2, max_retries=3)
        fetcher = PageFetcher(config, transport=httpx.MockTransport(handler=handler))
        fetcher._backoff = _noop_backoff
        result = await fetcher.fetch("https://x.ro/a")
        assert result.success
        assert result.attempts == 2
        await fetcher.close()


async def _noop_backoff(attempt: int, base: float = 2.0) -> None:
    return None
