from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.listing import ListingSource


class ListingPage(BaseModel):
    """Raw page fetch result persisted before parsing."""

    listing_id: str
    fetched_url: str
    http_status: int = 0
    bot_blocked: bool = False
    html: str = ""
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class PageExtraction(BaseModel):
    """Structured metadata parsed from a listing page (Stage 2 output)."""

    listing_id: str
    url: str = ""
    source: ListingSource = ListingSource.UNKNOWN
    title: str = ""
    description: str = ""
    body_text: str = ""
    price_eur: int | None = None
    sqm: float | None = None
    rooms: int | None = None
    city: str = ""
    neighborhood: str = ""
    address: str = ""
    latitude: float | None = None
    longitude: float | None = None
    image_urls: list[str] = Field(default_factory=list)
    construction_year: int | None = None
    storeys: int | None = None
    seismic_risk_class: int | None = None
    parse_methods: list[str] = Field(default_factory=list)
    confidence: float = 0.0
