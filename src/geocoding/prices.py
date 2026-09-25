from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from collections.abc import Iterable, Mapping
from math import isfinite
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.geocoding.zones import ZoneResolver
    from src.models.listing import Listing

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


def load_zone_prices(
    env_key: str = "ZONE_AVG_PRICES_EUR_PER_SQM",
    *,
    derived_prices: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Return defaults merged with database-derived values and env overrides.

    The env value is a JSON object mapping zone name -> EUR/sqm, e.g.
    {"Primăverii": 3000.0, "Sector 1": 2600.0, "Sector 4": 1700.0}.
    Explicit environment values take precedence over values calculated from
    the listings table.
    """
    prices = dict(DEFAULT_ZONE_PRICES)
    if derived_prices:
        for key, value in derived_prices.items():
            try:
                prices[str(key)] = float(value)
            except (TypeError, ValueError):
                logger.warning("Ignoring non-numeric derived zone price for %r", key)

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


def calculate_zone_avg_prices_eur_per_sqm(
    listings: Iterable[Listing],
    resolver: ZoneResolver,
    fallback_zone: str = "Bucuresti",
) -> dict[str, float]:
    """Calculate sector averages from every valid listing in an iterable."""
    from src.geocoding.zones import canonical_zone_name

    fallback = canonical_zone_name(fallback_zone) or fallback_zone or "Bucuresti"
    samples: dict[str, list[float]] = defaultdict(list)
    for listing in listings:
        price = listing.price_eur
        sqm = listing.sqm
        if price is None or sqm is None or price <= 0 or sqm <= 0:
            continue
        if not isfinite(price) or not isfinite(sqm):
            continue

        match = resolver.resolve(listing)
        zone = match.sector or fallback
        samples[zone].append(price / sqm)

    return {zone: sum(values) / len(values) for zone, values in samples.items()}


derive_zone_avg_prices_eur_per_sqm = calculate_zone_avg_prices_eur_per_sqm


__all__ = [
    "DEFAULT_ZONE_PRICES",
    "calculate_zone_avg_prices_eur_per_sqm",
    "derive_zone_avg_prices_eur_per_sqm",
    "load_zone_prices",
]
