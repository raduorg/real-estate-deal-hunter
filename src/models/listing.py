from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


class ListingSource(str, enum.Enum):
    IMOBILIARE = "imobiliare"
    STORIA = "storia"
    OLX = "olx"
    PUBLI24 = "publi24"
    UNKNOWN = "unknown"


class ListingStatus(str, enum.Enum):
    NEW = "new"
    EXTRACTED = "extracted"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    ALERTED = "alerted"
    SKIPPED = "skipped"


class Listing(BaseModel):
    id: str = Field(description="Unique listing ID (URL hash or portal ID)")
    url: str = Field(description="Listing page URL")
    source: ListingSource = Field(default=ListingSource.UNKNOWN)
    title: str = ""
    description: str = ""
    price_eur: int | None = None
    sqm: float | None = None
    rooms: int | None = None
    city: str = ""
    neighborhood: str = ""
    address: str = ""
    latitude: float | None = None
    longitude: float | None = None
    image_urls: list[str] = Field(default_factory=list)
    status: ListingStatus = Field(default=ListingStatus.NEW)
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    email_subject: str = ""
    email_date: datetime | None = None


class VisionAnalysis(BaseModel):
    listing_id: str
    condition_tier: str = "unknown"
    estimated_renovation_cost_eur_per_sqm: int = 0
    heating_type_visible: str = "unknown"
    window_type: str = "unknown"
    deal_breakers: list[str] = Field(default_factory=list)
    image_score: float = 0.0
    reasoning: str = ""


class DealScore(BaseModel):
    listing_id: str
    adjusted_price_per_sqm: float = 0.0
    market_average_per_sqm: float = 0.0
    discount_percentage: float = 0.0
    is_deal: bool = False
    total_renovation_cost: int = 0
    deal_score: float = 0.0
    condition_tier: str = "unknown"
