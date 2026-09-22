from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import MultiPolygon, Point, shape

from src.models.listing import Listing

logger = logging.getLogger(__name__)

# Translates raw GeoJSON property names into canonical zone keys used by the
# price table (e.g. OSM "Sector 1" -> "Sector 1").
_ALIASES = {
    "sector 1": "Sector 1",
    "sectorul 1": "Sector 1",
    "sector 2": "Sector 2",
    "sectorul 2": "Sector 2",
    "sector 3": "Sector 3",
    "sectorul 3": "Sector 3",
    "sector 4": "Sector 4",
    "sectorul 4": "Sector 4",
    "sector 5": "Sector 5",
    "sectorul 5": "Sector 5",
    "sector 6": "Sector 6",
    "sectorul 6": "Sector 6",
    "bucuresti": "Bucuresti",
    "bucharest": "Bucuresti",
}


def canonical_zone_name(raw: str | None) -> str | None:
    if not raw:
        return None
    key = " ".join(str(raw).strip().lower().split())
    return _ALIASES.get(key, str(raw).strip())


@dataclass(frozen=True)
class ZoneMatch:
    """Result of resolving a listing to a canonical zone."""

    zone: str = ""
    avg_price_sqm: float | None = None
    matched: bool = False
    method: str = ""


class ZoneIndex:
    """Point-in-polygon index over zone boundary GeoJSON.

    Built once from a small bundled dataset (Bucharest sectors); pure-local
    and free per the no-proxy/no-LLM budget in the implementation plan.
    """

    def __init__(self, geojson_path: str | Path) -> None:
        self.geojson_path = Path(geojson_path)
        self._polygons: dict[str, MultiPolygon] = {}
        self._load()

    def _load(self) -> None:
        if not self.geojson_path.exists():
            logger.warning("Zone boundaries not found: %s", self.geojson_path)
            return
        data = json.loads(self.geojson_path.read_text(encoding="utf-8"))
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            geom = feature.get("geometry")
            if not geom:
                continue
            name = canonical_zone_name(props.get("name") or props.get("shapeName"))
            if not name:
                continue
            try:
                poly = shape(geom)
            except (TypeError, ValueError) as exc:
                logger.warning("Skipping unreadable geometry for %s: %s", name, exc)
                continue
            if isinstance(poly, MultiPolygon):
                self._polygons[name] = poly
            else:
                self._polygons[name] = MultiPolygon([poly])

    @property
    def zone_names(self) -> list[str]:
        return sorted(self._polygons)

    def zone_for_point(self, latitude: float, longitude: float) -> str | None:
        if not self._polygons:
            return None
        point = Point(longitude, latitude)
        for name, poly in self._polygons.items():
            if poly.contains(point):
                return name
        return None


class ZoneResolver:
    """Resolves a listing to a canonical zone using coordinates first."""

    def __init__(
        self,
        zone_index: ZoneIndex | None = None,
        prices: dict[str, float] | None = None,
    ) -> None:
        self.zone_index = zone_index
        self.prices = prices or {}

    def resolve(self, listing: Listing) -> ZoneMatch:
        if self.zone_index and listing.latitude is not None and listing.longitude is not None:
            zone = self.zone_index.zone_for_point(listing.latitude, listing.longitude)
            if zone:
                return ZoneMatch(
                    zone=zone,
                    avg_price_sqm=self.prices.get(zone),
                    matched=True,
                    method="coords",
                )
            return ZoneMatch(
                zone="",
                avg_price_sqm=None,
                matched=False,
                method="coords_outside",
            )
        if not (self.zone_index and listing.latitude is None):
            return ZoneMatch(method="no_coords")
        return ZoneMatch(method="no_coords")