"""Stage 8: LangGraph wiring for the deterministic pipeline.

Every node is a plain async function over `ListingState`. LLM spend happens
only inside the vision node (local Ollama); everything before it is code that
fails the listing before any paid call. The single conditional edge is the
pure-math early-exit at Stage 4.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.config import Config
from src.deal_calculator.valuator import evaluate_deal
from src.email_listener.db import Database
from src.extractor.extractor import Extractor
from src.extractor.fetcher import PageFetcher
from src.filters import should_exclude
from src.geocoding.filter import FinancialResult, FinancialVerdict, is_financially_viable
from src.geocoding.prices import (
    calculate_zone_avg_prices_eur_per_sqm,
    load_zone_prices,
)
from src.geocoding.verify import verify_zone_mentions
from src.geocoding.zones import (
    Neighborhood,
    Sector,
    ZoneIndex,
    ZoneMatch,
    ZoneResolver,
)
from src.models.extraction import PageExtraction
from src.models.listing import Listing, ListingStatus, VisionAnalysis
from src.orchestration.state import ListingState
from src.seismic.risk import is_excluded, seismic_risk_score
from src.vision_evaluator.evaluator import VisionError, VisionEvaluator

logger = logging.getLogger(__name__)

# Numeric keys copied from the parsed page into the in-memory state listing.
_EXTRACTION_FIELDS = (
    "title",
    "description",
    "price_eur",
    "sqm",
    "rooms",
    "city",
    "neighborhood",
    "address",
    "latitude",
    "longitude",
    "image_urls",
    "construction_year",
    "storeys",
    "seismic_risk_class",
)


def merge_extraction(listing: Listing, extraction: PageExtraction) -> Listing:
    """Return a copy of `listing` enriched with the freshly parsed page data.

    `Extractor.extract` already persisted the extraction to SQLite; this merges
    it back into the in-memory listing so downstream nodes (zone, vision,
    valuation) never re-read the DB for fields they need.
    """
    update: dict[str, Any] = {}
    for field in _EXTRACTION_FIELDS:
        value = getattr(extraction, field)
        current = getattr(listing, field)
        if isinstance(value, str):
            update[field] = value or current
        else:
            update[field] = current if value is None else value
    return listing.model_copy(update=update)


def _zone_match_from_name(resolver: ZoneResolver, zone: str, method: str) -> ZoneMatch:
    neighborhood = Neighborhood.parse(zone)
    sector = neighborhood.sector if neighborhood is not None else Sector.parse(zone)
    sector_name = sector.value if sector is not None else None
    return ZoneMatch(
        zone=zone,
        avg_price_sqm=resolver.price_for(zone, sector_name),
        matched=neighborhood is not None or sector is not None,
        method=method,
        sector=sector_name,
        neighborhood=neighborhood.value if neighborhood is not None else None,
    )


def evaluate_gate(financial: FinancialResult | None) -> str:
    """Stage 4 conditional edge: TOO_EXPENSIVE ends the run; everything else
    (viable, suspicious, insufficient data) proceeds to vision."""
    if financial is not None and financial.verdict == FinancialVerdict.TOO_EXPENSIVE:
        return "end"
    return "vision"


class PipelineBuilder:
    """Owns the shared services and exposes one callable per graph node."""

    def __init__(
        self,
        *,
        config: Config,
        db: Database,
        extractor: Extractor,
        resolver: ZoneResolver,
        vision_evaluator: VisionEvaluator,
    ) -> None:
        self.config = config
        self.db = db
        self.extractor = extractor
        self.resolver = resolver
        self.vision_evaluator = vision_evaluator

    @classmethod
    def from_config(
        cls,
        config: Config,
        *,
        transport: Any | None = None,
        vision_transport: Any | None = None,
    ) -> PipelineBuilder:
        db = Database(config.database_path)
        fetcher = PageFetcher(config.extractor, transport=transport)
        extractor = Extractor(fetcher, db, max_images=config.extractor.max_images)
        resolver = ZoneResolver(
            ZoneIndex(config.zones.geojson_path),
            prices=load_zone_prices(),
            fallback_city=config.zones.fallback_city,
        )
        vision_evaluator = VisionEvaluator(config, db, transport=vision_transport)
        return cls(
            config=config,
            db=db,
            extractor=extractor,
            resolver=resolver,
            vision_evaluator=vision_evaluator,
        )

    async def close(self) -> None:
        await self.extractor.fetcher.close()
        await self.db.close()

    async def refresh_zone_prices(self) -> dict[str, float]:
        listings = await self.db.get_listings_for_zone_pricing()
        derived_prices = calculate_zone_avg_prices_eur_per_sqm(
            listings,
            self.resolver,
            fallback_zone=self.config.zones.fallback_city,
        )
        prices = load_zone_prices(derived_prices=derived_prices)
        self.resolver.replace_prices(prices)
        return prices

    # ------------------------------------------------------------------ nodes

    async def extract(self, state: ListingState) -> dict[str, object]:
        listing = state["listing"]
        try:
            extraction = await self.extractor.extract(listing)
        except Exception as exc:
            logger.exception("Extraction failed for %s (%s)", listing.id, listing.url)
            return {"extraction": None, "error": str(exc)}
        if extraction is None:
            logger.info("Listing %s skipped at extraction (fetch blocked/failed)", listing.id)
            return {"extraction": None}
        logger.info(
            "Listing %s extracted: price=%s sqm=%s images=%d",
            listing.id,
            extraction.price_eur,
            extraction.sqm,
            len(extraction.image_urls),
        )
        return {"extraction": extraction, "listing": merge_extraction(listing, extraction)}

    async def filter(self, state: ListingState) -> dict[str, object]:
        """Stage 3b: early-exit on sub-floor price or demisol/subsol level.

        Cheap text/math rules run right after extraction, so obvious junk
        (mislisted rentals, basements) never reaches zone/financial/vision.
        """
        listing = state["listing"]
        result = should_exclude(
            listing,
            min_price_eur=self.config.deals.min_price_eur,
        )
        if result.rejected:
            logger.info("Listing %s filtered out: %s", listing.id, result.reason)
            await self.db.update_listing_status(listing.id, ListingStatus.SKIPPED)
            return {"filter": result.reason}
        logger.debug("Listing %s passed pre-filters", listing.id)
        return {"filter": None}

    def filter_gate(self, state: ListingState) -> str:
        return "end" if state.get("filter") else "seismic"

    async def seismic(self, state: ListingState) -> dict[str, object]:
        """Stage 3a: score seismic risk right after extraction — pure text math.

        Risk-5 buildings are excluded here, before any zone/financial/vision
        spend, mirroring the Stage 4 early-exit philosophy.
        """
        listing = state["listing"]
        risk = seismic_risk_score(
            listing.seismic_risk_class,
            listing.construction_year,
            listing.storeys,
        )
        updated = listing.model_copy(update={"seismic_risk": risk})
        await self.db.update_seismic_risk(listing.id, risk)
        if is_excluded(risk):
            logger.info(
                "Listing %s excluded: seismic_risk=%s (class=%s year=%s storeys=%s)",
                listing.id,
                risk,
                listing.seismic_risk_class,
                listing.construction_year,
                listing.storeys,
            )
            await self.db.update_listing_status(listing.id, ListingStatus.SKIPPED)
            return {"listing": updated, "seismic": risk}
        logger.info(
            "Listing %s seismic risk: %s (class=%s year=%s storeys=%s)",
            listing.id,
            risk,
            listing.seismic_risk_class,
            listing.construction_year,
            listing.storeys,
        )
        return {"listing": updated, "seismic": risk}

    def seismic_gate(self, state: ListingState) -> str:
        return "end" if is_excluded(state.get("seismic")) else "verify_zone"

    async def verify_zone(self, state: ListingState) -> dict[str, object]:
        listing = state["listing"]
        extraction = state.get("extraction")
        body_text = extraction.body_text if extraction is not None else ""
        match = self.resolver.resolve(listing, body_text=body_text)
        verification = verify_zone_mentions(
            listing,
            body_text=body_text,
            known_zones=(
                set(self.resolver.price_keys)
                | {sector.value for sector in Sector}
                | {neighborhood.value for neighborhood in Neighborhood}
            ),
            include_neighborhoods=True,
        )
        if verification.discrepancy and verification.corrected_zone and (
            not match.neighborhood or verification.corrected_zone != match.neighborhood
        ):
            previous = match.zone or "unresolved"
            match = _zone_match_from_name(
                self.resolver,
                verification.corrected_zone,
                "description_discrepancy",
            )
            logger.info(
                "Listing %s zone overridden by description: %s -> %s",
                listing.id,
                previous,
                verification.corrected_zone,
            )
        elif not match.matched and verification.corrected_zone:
            match = _zone_match_from_name(
                self.resolver,
                verification.corrected_zone,
                "description",
            )
            logger.info(
                "Listing %s zone set from description: %s",
                listing.id,
                verification.corrected_zone,
            )
        logger.info(
            "Listing %s zone resolved: zone=%r method=%s",
            listing.id,
            match.zone,
            match.method,
        )
        return {"zone_match": match, "zone_verification": verification}

    async def financial(self, state: ListingState) -> dict[str, object]:
        listing = state["listing"]
        zone = state.get("zone_match")
        result = is_financially_viable(
            listing,
            zone.avg_price_sqm if zone else None,
            ceiling_multiplier=self.config.zones.ceiling_multiplier,
            floor_multiplier=self.config.zones.floor_multiplier,
        )
        logger.info(
            "Listing %s sanity: verdict=%s reason=%s",
            listing.id,
            result.verdict.value,
            result.reason,
        )
        if result.verdict == FinancialVerdict.TOO_EXPENSIVE:
            # The gate killed it: close the row so nothing re-processes it.
            await self.db.update_listing_status(listing.id, ListingStatus.SKIPPED)
        return {"financial": result}

    def should_evaluate(self, state: ListingState) -> str:
        return evaluate_gate(state.get("financial"))

    async def vision(self, state: ListingState) -> dict[str, object]:
        listing = state["listing"]
        await self.db.update_listing_status(listing.id, ListingStatus.ANALYZING)
        try:
            analysis = await self.vision_evaluator.evaluate_listing(listing)
        except VisionError as exc:
            # Not a hard skip: revert so a later pass can retry the expensive call.
            await self.db.update_listing_status(listing.id, ListingStatus.EXTRACTED)
            logger.error("Vision failed for %s: %s", listing.id, exc)
            return {"vision": None, "error": str(exc)}
        except Exception as exc:
            await self.db.update_listing_status(listing.id, ListingStatus.EXTRACTED)
            logger.exception("Unexpected vision failure for %s", listing.id)
            return {"vision": None, "error": str(exc)}

        if analysis is None:
            logger.info("Listing %s has no usable photos; skipping", listing.id)
            await self.db.update_listing_status(listing.id, ListingStatus.SKIPPED)
            return {"vision": None}

        await self.db.save_vision_analysis(
            listing_id=listing.id,
            analysis=analysis,
            model=self.vision_evaluator.vision.ollama_model,
            images_used=min(len(listing.image_urls), self.vision_evaluator.vision.max_images),
        )
        await self.db.update_listing_status(listing.id, ListingStatus.ANALYZED)
        return {"vision": analysis}

    async def value(self, state: ListingState) -> dict[str, object]:
        listing = state["listing"]
        extraction = state.get("extraction")
        zone = state.get("zone_match")
        financial = state.get("financial")
        if extraction is None:
            logger.info("Listing %s skipped at valuation (no extraction)", listing.id)
            return {"deal": None}

        analysis = state.get("vision") or VisionAnalysis(listing_id=listing.id)
        deal = evaluate_deal(
            listing,
            analysis,
            zone.avg_price_sqm if zone else None,
            deal_threshold_percent=self.config.deals.deal_threshold_percent,
            max_discount_percent=self.config.deals.max_discount_percent,
            discount_weight=self.config.deals.discount_weight,
            condition_weight=self.config.deals.condition_weight,
            seismic_weight=self.config.deals.seismic_weight,
            natural_light_weight=self.config.deals.natural_light_weight,
        )
        if financial is None:
            financial = FinancialResult(
                verdict=FinancialVerdict.INSUFFICIENT_DATA,
                price_per_sqm=None,
                zone_avg_price_sqm=None,
                ceiling=None,
                floor=None,
                reason="no financial verdict recorded",
            )
        await self.db.save_pipeline_result(
            listing.id,
            zone_match=zone or ZoneMatch(method="unresolved"),
            financial=financial,
            deal=deal,
        )
        logger.info(
            "Listing %s valued: adjusted=%.2f EUR/sqm discount=%.2f%% deal=%s score=%.1f light=%s",
            listing.id,
            deal.adjusted_price_per_sqm,
            deal.discount_percentage,
            deal.is_deal,
            deal.deal_score,
            deal.natural_light_score,
        )
        return {"deal": deal}

    # ------------------------------------------------------------------ graph

    def build_graph(self) -> Any:
        graph = StateGraph(ListingState)
        graph.add_node("extract", self.extract)
        graph.add_node("filter", self.filter)
        graph.add_node("seismic", self.seismic)
        graph.add_node("verify_zone", self.verify_zone)
        graph.add_node("financial", self.financial)
        graph.add_node("vision", self.vision)
        graph.add_node("value", self.value)
        graph.add_edge(START, "extract")
        graph.add_edge("extract", "filter")
        graph.add_conditional_edges(
            "filter", self.filter_gate, {"seismic": "seismic", "end": END}
        )
        graph.add_conditional_edges(
            "seismic", self.seismic_gate, {"verify_zone": "verify_zone", "end": END}
        )
        graph.add_edge("verify_zone", "financial")
        graph.add_conditional_edges(
            "financial", self.should_evaluate, {"vision": "vision", "end": END}
        )
        graph.add_edge("vision", "value")
        graph.add_edge("value", END)
        return graph.compile()


__all__ = ["PipelineBuilder", "evaluate_gate", "merge_extraction"]