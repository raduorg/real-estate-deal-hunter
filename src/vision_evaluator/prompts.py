"""Prompt + structured-output schema for the vision evaluator.

One constrained inference pass over a listing's photos (Stage 5). The schema is
sent to Ollama as `format` so the model is forced into rigid JSON.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

CONDITION_TIERS = [
    "needs_total_renovation",
    "habitable_dated",
    "renovated_standard",
    "luxury",
]

HEATING_TYPES = ["gas_boiler", "district_radiators", "electric", "heat_pump", "unknown"]

WINDOW_TYPES = ["modern_pvc", "old_wood", "mixed", "unknown"]

SYSTEM_PROMPT = """You are a senior property condition analyst for the Romanian
real estate market. You inspect listing photos and produce a terse, structured
assessment of the property's physical condition.

Rules:
- Judge only what is actually visible in the photos. Absence of evidence is
  "unknown", never a guess.
- Floors: parquet is higher quality than laminate; cracked or worn tiles lower
  the score. Joinery: modern PVC windows are better than old wooden frames.
- Hardwood parquet, marble, designer finishes, new reno => "luxury" or
  "renovated_standard". Old but functional, dated finishes => "habitable_dated".
  Bare concrete, demolished interiors, mold, gutted electrical => "needs_total_renovation".
- estimated_renovation_cost_eur_per_sqm = approx EUR/sqm needed to bring the
  property to modern "renovated_standard" (0 for already renovated, up to ~800
  for gut renovation).
- image_score: 0-10 quality-of-condition barometer for a hypothetical buyer.
- deal_breakers: only objective red flags actually visible, e.g.
  "visible_moisture_stains", "mold", "outdated_fuse_box", "cracked_structure",
  "water_stains_on_ceiling".
- Reply with JSON only, matching the requested format exactly."""

VISION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "condition_tier": {"type": "string", "enum": CONDITION_TIERS},
        "estimated_renovation_cost_eur_per_sqm": {
            "type": "integer",
            "minimum": 0,
            "maximum": 1500,
        },
        "heating_type_visible": {"type": "string", "enum": HEATING_TYPES},
        "window_type": {"type": "string", "enum": WINDOW_TYPES},
        "deal_breakers": {"type": "array", "items": {"type": "string"}},
        "image_score": {"type": "number", "minimum": 0, "maximum": 10},
        "reasoning": {"type": "string"},
    },
    "required": [
        "condition_tier",
        "estimated_renovation_cost_eur_per_sqm",
        "heating_type_visible",
        "window_type",
        "deal_breakers",
        "image_score",
        "reasoning",
    ],
}


def vision_json_schema() -> dict[str, Any]:
    """Fresh copy per call so callers may mutate it freely."""
    return deepcopy(VISION_JSON_SCHEMA)


def build_user_prompt(
    title: str = "",
    description: str = "",
    price_eur: int | None = None,
    sqm: float | None = None,
    rooms: int | None = None,
    neighborhood: str = "",
) -> str:
    """Assemble the textual listing context shown alongside the photos."""
    lines = ["Inspect the attached photos of this Romanian apartment listing."]
    if title:
        lines.append(f"Title: {title}")
    if price_eur:
        lines.append(f"Asking price: {price_eur} EUR")
    if sqm:
        lines.append(f"Surface: {sqm:g} sqm")
    if rooms:
        lines.append(f"Rooms: {rooms}")
    if neighborhood:
        lines.append(f"Neighborhood: {neighborhood}")
    if description:
        excerpt = " ".join(description.split())
        lines.append(f"Seller description: {excerpt[:600]}")
    lines.append("Return your structured assessment as JSON.")
    return "\n".join(lines)