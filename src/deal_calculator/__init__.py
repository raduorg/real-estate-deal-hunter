"""Stage 6: Valuation & deal scoring (pure arithmetic)."""

from src.deal_calculator.valuator import (
    CONDITION_TIER_SCORES,
    DEAL_THRESHOLD_PERCENT,
    MAX_DISCOUNT_PERCENT,
    NATURAL_LIGHT_WEIGHT,
    DealScore,
    adjusted_price_per_sqm,
    condition_component,
    deal_score,
    discount_component,
    discount_percent,
    evaluate_deal,
    is_natural_light_excluded,
    natural_light_component,
    total_renovation_cost,
)

__all__ = [
    "CONDITION_TIER_SCORES",
    "DEAL_THRESHOLD_PERCENT",
    "MAX_DISCOUNT_PERCENT",
    "NATURAL_LIGHT_WEIGHT",
    "DealScore",
    "adjusted_price_per_sqm",
    "condition_component",
    "deal_score",
    "discount_component",
    "discount_percent",
    "evaluate_deal",
    "is_natural_light_excluded",
    "natural_light_component",
    "total_renovation_cost",
]
