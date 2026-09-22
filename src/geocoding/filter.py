from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.models.listing import Listing

# Default deterministic math gate thresholds (Stage 4).
CEILING_MULTIPLIER = 1.30  # asking price/sqm above zone avg * this => reject
FLOOR_MULTIPLIER = 0.50  # price/sqm below zone avg * this => possible scam (flag)


class FinancialVerdict(str, Enum):
    VIABLE = "viable"
    TOO_EXPENSIVE = "too_expensive"
    SUSPICIOUS = "suspicious"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class FinancialResult:
    verdict: FinancialVerdict
    price_per_sqm: float | None
    zone_avg_price_sqm: float | None
    ceiling: float | None
    floor: float | None
    reason: str


def _price_per_sqm(price_eur: int | None, sqm: float | None) -> float | None:
    if price_eur is None or not sqm or sqm <= 0:
        return None
    return price_eur / sqm


def is_financially_viable(
    listing: Listing,
    zone_avg_price_sqm: float | None,
    ceiling_multiplier: float = CEILING_MULTIPLIER,
    floor_multiplier: float = FLOOR_MULTIPLIER,
) -> FinancialResult:
    """Deterministic financial gate; no vision spend for obvious dumps.

    - price/sqm > zone_avg * ceiling_multiplier  => TOO_EXPENSIVE (reject)
    - price/sqm < zone_avg * floor_multiplier    => SUSPICIOUS (possible scam)
    - otherwise                                   => VIABLE
    Any missing figure (price, sqm, zone avg) degrades to INSUFFICIENT_DATA,
    which the orchestrator treats as 'proceed cautiously', not as a hard skip.
    """
    per_sqm = _price_per_sqm(listing.price_eur, listing.sqm)
    if per_sqm is None:
        return FinancialResult(
            verdict=FinancialVerdict.INSUFFICIENT_DATA,
            price_per_sqm=None,
            zone_avg_price_sqm=zone_avg_price_sqm,
            ceiling=None,
            floor=None,
            reason="missing price or sqm",
        )
    if zone_avg_price_sqm is None:
        return FinancialResult(
            verdict=FinancialVerdict.INSUFFICIENT_DATA,
            price_per_sqm=per_sqm,
            zone_avg_price_sqm=None,
            ceiling=None,
            floor=None,
            reason="unknown zone average",
        )

    ceiling = zone_avg_price_sqm * ceiling_multiplier
    floor = zone_avg_price_sqm * floor_multiplier

    if per_sqm > ceiling:
        return FinancialResult(
            verdict=FinancialVerdict.TOO_EXPENSIVE,
            price_per_sqm=per_sqm,
            zone_avg_price_sqm=zone_avg_price_sqm,
            ceiling=ceiling,
            floor=floor,
            reason=(
                f"asking {per_sqm:.0f} EUR/sqm exceeds zone ceiling "
                f"{ceiling:.0f} EUR/sqm (avg {zone_avg_price_sqm:.0f} x {ceiling_multiplier})"
            ),
        )
    if per_sqm < floor:
        return FinancialResult(
            verdict=FinancialVerdict.SUSPICIOUS,
            price_per_sqm=per_sqm,
            zone_avg_price_sqm=zone_avg_price_sqm,
            ceiling=ceiling,
            floor=floor,
            reason=(
                f"asking {per_sqm:.0f} EUR/sqm far below zone avg "
                f"{zone_avg_price_sqm:.0f} EUR/sqm ({floor_multiplier:.0%} threshold)"
            ),
        )
    return FinancialResult(
        verdict=FinancialVerdict.VIABLE,
        price_per_sqm=per_sqm,
        zone_avg_price_sqm=zone_avg_price_sqm,
        ceiling=ceiling,
        floor=floor,
        reason=f"asking {per_sqm:.0f} EUR/sqm within {floor:.0f}-{ceiling:.0f} band",
    )