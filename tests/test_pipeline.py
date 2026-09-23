"""Stage 8: LangGraph orchestration tests.

The compiled graph is run end-to-end with a mocked httpx transport (listing
page, image CDN and the Ollama vision endpoint), following the same fixture
pattern as the extractor and vision test suites.
"""

# ruff: noqa: E501 - long HTML fixture lines are intentional
from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from src.config import Config, EmailConfig, ExtractorConfig, TargetConfig, VisionConfig, ZoneConfig
from src.deal_calculator.valuator import DealScore
from src.email_listener.db import Database
from src.extractor.extractor import Extractor
from src.extractor.fetcher import PageFetcher
from src.geocoding.filter import FinancialResult, FinancialVerdict
from src.geocoding.prices import DEFAULT_ZONE_PRICES
from src.geocoding.zones import ZoneIndex, ZoneMatch, ZoneResolver
from src.models.extraction import PageExtraction
from src.models.listing import Listing, ListingSource, ListingStatus
from src.orchestration.graph import PipelineBuilder, evaluate_gate, merge_extraction
from src.vision_evaluator.evaluator import VisionEvaluator

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "zones"
SECTOR_3_AVG = DEFAULT_ZONE_PRICES["Sector 3"]

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNg"
    "AAIAAAUAAXpeqz8AAAAASUVORK5CYII="
)

# 80.000 Euro, 55 mp, Sector 3 coords -> viable, and after the vision-stated
# 100 EUR/sqm of renovation still ~19% below the sector average.
LISTING_HTML = """<!DOCTYPE html><html><head>
  <title>Apartament 2 camere, 55 mp</title>
  <meta property="og:title" content="Apartament 2 camere, 55 mp, 80.000 Euro - Bucuresti, Sector 3" />
  <meta property="og:description" content="Apartament de vanzare, 2 camere, 55 mp, 80.000 Euro, etaj 2, central" />
  <meta property="og:image" content="https://cdn.test/1.png" />
  <script>window.__STATE__ = {"lat": 44.4325, "lng": 26.1039};</script>
</head><body><h1>Apartament - Sector 3</h1></body></html>"""

OVERPRICED_HTML = """<!DOCTYPE html><html><head>
  <meta property="og:title" content="Apartament de lux, 45 mp, 150.000 Euro - Bucuresti, Sector 3" />
  <meta property="og:description" content="Apartament, 45 mp, 150.000 Euro, etaj 1, central" />
  <meta property="og:image" content="https://cdn.test/1.png" />
  <script>window.__STATE__ = {"lat": 44.4325, "lng": 26.1039};</script>
</head><body></body></html>"""

NO_PRICE_HTML = """<!DOCTYPE html><html><head>
  <meta property="og:title" content="Apartament 2 camere - Bucuresti, Sector 3" />
  <meta property="og:description" content="Apartament de vanzare, 2 camere, 55 mp, etaj 3, central" />
  <meta property="og:image" content="https://cdn.test/1.png" />
  <script>window.__STATE__ = {"lat": 44.4325, "lng": 26.1039};</script>
</head><body></body></html>"""


def make_config(tmp_path: Path) -> Config:
    return Config(
        email=EmailConfig(user="u", password="p"),
        target=TargetConfig(),
        vision=VisionConfig(
            ollama_host="http://ollama.test",
            ollama_model="gemma4:26b",
            timeout=5.0,
            max_retries=3,
            max_images=5,
            image_timeout=5.0,
            temperature=0.0,
        ),
        extractor=ExtractorConfig(min_delay=0, max_delay=0, timeout=2, max_retries=2, max_images=3),
        zones=ZoneConfig(geojson_path=DATA_DIR / "bucharest_sectors.geojson"),
        database_path=tmp_path / "pipeline.db",
    )


def make_listing(
    listing_id: str, url: str = "https://www.storia.ro/ro/oferta/apartament-x"
) -> Listing:
    return Listing(
        id=listing_id,
        url=url,
        source=ListingSource.STORIA,
        status=ListingStatus.NEW,
    )


def ollama_json(
    renovation: int = 100, tier: str = "habitable_dated", score: float = 6.5
) -> str:
    return json.dumps(
        {
            "condition_tier": tier,
            "estimated_renovation_cost_eur_per_sqm": renovation,
            "heating_type_visible": "gas_boiler",
            "window_type": "modern_pvc",
            "deal_breakers": ["old_fuse_box"],
            "image_score": score,
            "reasoning": "Dated but functional.",
        }
    )


def make_transport(html: str) -> httpx.MockTransport:
    """One transport serving the listing page, the image CDN and Ollama."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                json={"message": {"role": "assistant", "content": ollama_json()}},
            )
        if request.url.host == "cdn.test":
            return httpx.Response(200, content=PNG_BYTES, headers={"content-type": "image/png"})
        return httpx.Response(200, text=html)

    return httpx.MockTransport(handler)


async def build_runner(
    tmp_path: Path, html: str
) -> tuple[PipelineBuilder, Config, Listing]:
    config = make_config(tmp_path)
    transport = make_transport(html)
    db = Database(config.database_path)
    await db.connect()

    extractor = Extractor(PageFetcher(config.extractor, transport=transport), db, max_images=3)
    resolver = ZoneResolver(ZoneIndex(config.zones.geojson_path), prices=DEFAULT_ZONE_PRICES)
    evaluator = VisionEvaluator(config, db, transport=transport)
    builder = PipelineBuilder(
        config=config,
        db=db,
        extractor=extractor,
        resolver=resolver,
        vision_evaluator=evaluator,
    )
    listing = make_listing("l1")
    await db.save_listing(listing)
    return builder, config, listing


class TestEvaluateGate:
    def test_overpriced_routes_to_end(self) -> None:
        financial = FinancialResult(
            verdict=FinancialVerdict.TOO_EXPENSIVE,
            price_per_sqm=3333.0,
            zone_avg_price_sqm=SECTOR_3_AVG,
            ceiling=SECTOR_3_AVG * 1.3,
            floor=SECTOR_3_AVG * 0.5,
            reason="overpriced",
        )
        assert evaluate_gate(financial) == "end"

    def test_everything_else_proceeds_to_vision(self) -> None:
        viable = FinancialResult(
            verdict=FinancialVerdict.VIABLE,
            price_per_sqm=1454.0,
            zone_avg_price_sqm=SECTOR_3_AVG,
            ceiling=None,
            floor=None,
            reason="ok",
        )
        suspicious = FinancialResult(
            verdict=FinancialVerdict.SUSPICIOUS,
            price_per_sqm=900.0,
            zone_avg_price_sqm=SECTOR_3_AVG,
            ceiling=None,
            floor=None,
            reason="cheap",
        )
        assert evaluate_gate(viable) == "vision"
        assert evaluate_gate(suspicious) == "vision"
        assert evaluate_gate(None) == "vision"


class TestMergeExtraction:
    def test_enriches_listing_fields(self) -> None:
        listing = make_listing("m1")
        extraction = PageExtraction(
            listing_id="m1",
            title="Apartament 2 camere",
            price_eur=80000,
            sqm=55.0,
            latitude=44.4325,
            longitude=26.1039,
            image_urls=["https://cdn.test/1.png"],
        )
        merged = merge_extraction(listing, extraction)
        assert merged.price_eur == 80000
        assert merged.sqm == 55.0
        assert merged.latitude == pytest.approx(44.4325)
        assert merged.title == "Apartament 2 camere"


class TestPipelineGraph:
    async def test_full_viable_listing_ends_as_deal(self, tmp_path: Path) -> None:
        builder, _config, listing = await build_runner(tmp_path, LISTING_HTML)

        try:
            graph = builder.build_graph()
            final = await graph.ainvoke({"listing": listing})

            zone = final["zone_match"]
            assert zone.zone == "Sector 3"
            assert zone.avg_price_sqm == pytest.approx(SECTOR_3_AVG)

            financial = final["financial"]
            assert financial.verdict == FinancialVerdict.VIABLE

            deal = final["deal"]
            assert deal.is_deal
            assert deal.condition_tier == "habitable_dated"
            assert deal.discount_percentage == pytest.approx(19.25, abs=0.05)

            analyzed = await builder.db.get_listings_by_status(ListingStatus.ANALYZED)
            assert [r.id for r in analyzed] == [listing.id]
            assert analyzed[0].price_eur == 80000

            saved = await builder.db.get_pipeline_result(listing.id)
            assert saved is not None
            assert saved["passed_sanity"] is True
            assert saved["financial"]["verdict"] == "viable"
            assert saved["deal"]["is_deal"] is True
        finally:
            await builder.close()

    async def test_overpriced_listing_never_reaches_vision(self, tmp_path: Path) -> None:
        builder, config, listing = await build_runner(tmp_path, OVERPRICED_HTML)

        try:
            # Repoint vision at a transport that fails on any call, so a
            # routing lapse would raise instead of being silently absorbed.
            builder.vision_evaluator = VisionEvaluator(
                config, builder.db, transport=httpx.MockTransport(
                    lambda request: pytest.fail(f"unexpected call: {request.url}")
                )
            )

            graph = builder.build_graph()
            final = await graph.ainvoke({"listing": listing})

            assert final["financial"].verdict == FinancialVerdict.TOO_EXPENSIVE
            assert "deal" not in final
            assert "vision" not in final

            skipped = await builder.db.get_listings_by_status(ListingStatus.SKIPPED)
            assert [r.id for r in skipped] == [listing.id]
            assert await builder.db.get_pipeline_result(listing.id) is None
        finally:
            await builder.close()

    async def test_missing_price_proceeds_cautiously_no_deal(self, tmp_path: Path) -> None:
        builder, _config, listing = await build_runner(tmp_path, NO_PRICE_HTML)

        try:
            graph = builder.build_graph()
            final = await graph.ainvoke({"listing": listing})

            assert final["financial"].verdict == FinancialVerdict.INSUFFICIENT_DATA
            deal = final["deal"]
            assert deal is not None
            assert not deal.is_deal

            saved = await builder.db.get_pipeline_result(listing.id)
            assert saved is not None
            assert saved["passed_sanity"] is True
            assert saved["financial"]["verdict"] == "insufficient_data"
        finally:
            await builder.close()


class TestDbPersistence:
    async def test_save_and_get_pipeline_result(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "p.db")

        try:
            await db.connect()
            await db.save_listing(make_listing("p1"))
            zone = ZoneMatch(zone="Sector 3", avg_price_sqm=SECTOR_3_AVG, matched=True, method="coords")
            financial = FinancialResult(
                verdict=FinancialVerdict.VIABLE,
                price_per_sqm=1454.0,
                zone_avg_price_sqm=SECTOR_3_AVG,
                ceiling=None,
                floor=None,
                reason="within band",
            )
            deal = DealScore(
                listing_id="p1",
                adjusted_price_per_sqm=1554.5,
                market_average_per_sqm=SECTOR_3_AVG,
                discount_percentage=19.25,
                is_deal=True,
                deal_score=48.5,
                condition_tier="habitable_dated",
            )
            await db.save_pipeline_result("p1", zone_match=zone, financial=financial, deal=deal)

            saved = await db.get_pipeline_result("p1")
            assert saved is not None
            assert saved["passed_sanity"] is True
            assert saved["zone_match"]["zone"] == "Sector 3"
            assert saved["deal"]["is_deal"] is True
            assert saved["deal"]["deal_score"] == pytest.approx(48.5)
        finally:
            await db.close()