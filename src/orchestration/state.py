"""Stage 8: shared state object for the LangGraph pipeline.

Each node is a plain async function over this state; a node returns a partial
dict of the keys it produced and LangGraph merges them for the next hop. The
plan's flat `ListingState` (url, price, sqm, ...) is realized here as the
existing typed models, so no data is re-parsed between layers.
"""

from __future__ import annotations

from typing import TypedDict

from src.deal_calculator.valuator import DealScore
from src.geocoding.filter import FinancialResult
from src.geocoding.zones import ZoneMatch
from src.models.extraction import PageExtraction
from src.models.listing import Listing, VisionAnalysis


class ListingState(TypedDict, total=False):
    """One listing travelling through extract -> filter -> seismic ->
    verify_zone -> financial -> vision -> value. `total=False` keeps every
    channel optional so a node can run as soon as its inputs exist and fail
    downstream cheaply otherwise.
    """

    listing: Listing
    extraction: PageExtraction
    filter: str | None
    seismic: int | None
    zone_match: ZoneMatch
    financial: FinancialResult
    vision: VisionAnalysis
    deal: DealScore
    error: str