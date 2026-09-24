"""Stage 6: Valuation & deal scoring — pure arithmetic, no I/O, no LLM.

Takes the already-extracted asking price, the vision-estimated renovation
cost, the zone market average and the seismic risk score, then produces:

    adjusted_price_sqm     = (price + total_renovation) / sqm
    discount_percentage    = (market_avg - adjusted) / market_avg * 100
    is_deal                = discount_percentage > deal_threshold
    deal_score             = weighted blend of discount + condition + seismic
"""

from __future__ import annotations

from src.models.listing import DealScore, Listing, VisionAnalysis
from src.seismic.risk import seismic_component

# Default deterministic thresholds (Stage 6). Config values may override.
DEAL_THRESHOLD_PERCENT = 10.0  # discount above this makes the listing a deal
MAX_DISCOUNT_PERCENT = 40.0  # discounts beyond this saturate the deal score
DISCOUNT_WEIGHT = 0.60  # market-relative value of the deal
CONDITION_WEIGHT = 0.15  # finish quality of the deal
SEISMIC_WEIGHT = 0.25  # seismic safety of the building

# Higher tier = better condition; mirrors the vision schema in prompts.py.
CONDITION_TIER_SCORES: dict[str, float] = {
    "needs_total_renovation": 1.0,
    "habitable_dated": 2.0,
    "renovated_standard": 3.0,
    "luxury": 4.0,
}
MAX_CONDITION_SCORE = max(CONDITION_TIER_SCORES.values())


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def condition_component(condition_tier: str) -> float:
    """Normalized 0..1 how good the condition is."""
    return CONDITION_TIER_SCORES.get(condition_tier, 0.0) / MAX_CONDITION_SCORE


def discount_component(discount_percent: float, max_discount_percent: float) -> float:
    """Normalized 0..1 market discount (overpriced listings clamp to 0)."""
    if discount_percent <= 0:
        return 0.0
    return _clamp(discount_percent / max_discount_percent, 0.0, 1.0)


def total_renovation_cost(renovation_per_sqm: int, sqm: float) -> int:
    if renovation_per_sqm <= 0 or sqm <= 0:
        return 0
    return int(round(renovation_per_sqm * sqm))


def adjusted_price_per_sqm(
    price_eur: int | None, total_renovation: int, sqm: float | None
) -> float | None:
    if price_eur is None or not sqm or sqm <= 0:
        return None
    return (price_eur + total_renovation) / sqm


def discount_percent(market_avg_sqm: float | None, adjusted_sqm: float | None) -> float | None:
    """Percent cheaper-than-market; None when either figure is missing."""
    if market_avg_sqm is None or adjusted_sqm is None or market_avg_sqm <= 0:
        return None
    return (market_avg_sqm - adjusted_sqm) / market_avg_sqm * 100.0


def deal_score(
    discount_percent: float | None,
    condition_tier: str,
    seismic_risk: int | None,
    max_discount_percent: float = MAX_DISCOUNT_PERCENT,
    discount_weight: float = DISCOUNT_WEIGHT,
    condition_weight: float = CONDITION_WEIGHT,
    seismic_weight: float = SEISMIC_WEIGHT,
) -> float:
    """Weighted 0..100 blend of market discount, finish quality and seismic safety.

    Without a market reference the discount component is dropped (it is not
    counted as zero); condition and seismic still contribute. An unknown
    seismic risk neutralizes at 0.5, so missing signals neither help nor hurt.
    """
    cond = condition_component(condition_tier)
    seam = seismic_component(seismic_risk)
    if discount_percent is None:
        combined = condition_weight + seismic_weight
        disc = 0.0
    else:
        combined = discount_weight + condition_weight + seismic_weight
        disc = discount_component(discount_percent, max_discount_percent)
    return round(
        100.0
        * (discount_weight * disc + condition_weight * cond + seismic_weight * seam)
        / combined,
        1,
    )


def evaluate_deal(
    listing: Listing,
    analysis: VisionAnalysis,
    market_average_per_sqm: float | None,
    deal_threshold_percent: float = DEAL_THRESHOLD_PERCENT,
    max_discount_percent: float = MAX_DISCOUNT_PERCENT,
    discount_weight: float = DISCOUNT_WEIGHT,
    condition_weight: float = CONDITION_WEIGHT,
    seismic_weight: float = SEISMIC_WEIGHT,
) -> DealScore:
    """Full Stage 6 pass: fill DealScore via pure arithmetic.

    Missing price/sqm degrade to a defensive result (no deal, no renovation
    spend) rather than raising — the orchestrator treats it as 'do not alert'.
    """
    sqm = listing.sqm
    if listing.price_eur is None or not sqm or sqm <= 0:
        return DealScore(listing_id=listing.id)

    renovation = total_renovation_cost(analysis.estimated_renovation_cost_eur_per_sqm, sqm)
    adjusted = adjusted_price_per_sqm(listing.price_eur, renovation, sqm)
    assert adjusted is not None

    disc = discount_percent(market_average_per_sqm, adjusted)
    is_deal = disc is not None and disc > deal_threshold_percent

    return DealScore(
        listing_id=listing.id,
        adjusted_price_per_sqm=round(adjusted, 2),
        market_average_per_sqm=market_average_per_sqm or 0.0,
        discount_percentage=round(disc, 2) if disc is not None else 0.0,
        is_deal=is_deal,
        total_renovation_cost=renovation,
        deal_score=deal_score(
            disc,
            analysis.condition_tier,
            listing.seismic_risk,
            max_discount_percent,
            discount_weight,
            condition_weight,
            seismic_weight,
        ),
        condition_tier=analysis.condition_tier,
        seismic_risk=listing.seismic_risk,
    )


__all__ = [
    "DISCOUNT_WEIGHT",
    "CONDITION_WEIGHT",
    "SEISMIC_WEIGHT",
    "CONDITION_TIER_SCORES",
    "DEAL_THRESHOLD_PERCENT",
    "MAX_DISCOUNT_PERCENT",
    "MAX_CONDITION_SCORE",
    "DealScore",
    "adjusted_price_per_sqm",
    "condition_component",
    "deal_score",
    "discount_component",
    "discount_percent",
    "evaluate_deal",
    "total_renovation_cost",
]