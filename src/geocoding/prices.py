from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

# Per-zone average asking prices (EUR / sqm usable) seeded from public market
# data (Imospot.ro, Sept 2025 -> 2026). These are configuration inputs, not
# computed values; override any/all via ZONE_AVG_PRICES_EUR_PER_SQM.
DEFAULT_ZONE_PRICES: dict[str, float] = {
    "Sector 1": 2575.0,
    "Sector 2": 2050.0,
    "Sector 3": 1925.0,
    "Sector 4": 1690.0,
    "Sector 5": 1875.0,
    "Sector 6": 1950.0,
    "Bucuresti": 2017.0,
}


def load_zone_prices(env_key: str = "ZONE_AVG_PRICES_EUR_PER_SQM") -> dict[str, float]:
    """Returns the zone price table, merging optional JSON env overrides.

    The env value is a JSON object mapping zone name -> EUR/sqm, e.g.
    {"Sector 1": 2600.0, "Sector 4": 1700.0}.
    """
    prices = dict(DEFAULT_ZONE_PRICES)
    raw = os.getenv(env_key, "")
    if not raw:
        return prices
    try:
        override = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Ignoring invalid %s (not valid JSON): %s", env_key, exc)
        return prices
    if not isinstance(override, dict):
        logger.warning("Ignoring invalid %s (expected JSON object)", env_key)
        return prices
    for key, value in override.items():
        try:
            prices[str(key)] = float(value)
        except (TypeError, ValueError):
            logger.warning("Ignoring non-numeric zone price for %r", key)
    return prices