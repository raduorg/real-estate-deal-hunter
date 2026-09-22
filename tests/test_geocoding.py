from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.geocoding.filter import FinancialVerdict, is_financially_viable
from src.geocoding.prices import DEFAULT_ZONE_PRICES, load_zone_prices
from src.geocoding.zones import ZoneIndex, ZoneResolver, canonical_zone_name
from src.models.listing import Listing

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "zones"
SECTORS = {f"Sector {i}" for i in range(1, 7)}


@pytest.fixture(scope="module")
def zone_index() -> ZoneIndex:
    assert (DATA_DIR / "bucharest_sectors.geojson").exists()
    return ZoneIndex(DATA_DIR / "bucharest_sectors.geojson")


def make_listing(
    lat: float | None,
    lon: float | None,
    price: int | None,
    sqm: float | None,
) -> Listing:
    return Listing(
        id=f"t-{lat}-{lon}-{price}-{sqm}",
        url="https://example.test/",
        latitude=lat,
        longitude=lon,
        price_eur=price,
        sqm=sqm,
    )


class TestZoneIndex:
    def test_all_six_sectors_present(self, zone_index: ZoneIndex) -> None:
        assert SECTORS.issubset(set(zone_index.zone_names))

    def test_center_of_bucharest_maps_to_sector_3(self, zone_index: ZoneIndex) -> None:
        assert zone_index.zone_for_point(44.4325, 26.1039) == "Sector 3"

    def test_baneasa_maps_to_sector_1(self, zone_index: ZoneIndex) -> None:
        assert zone_index.zone_for_point(44.4847, 26.0769) in {"Sector 1"}

    def test_titan_maps_to_sector_3(self, zone_index: ZoneIndex) -> None:
        assert zone_index.zone_for_point(44.4311, 26.1318) in {"Sector 3"}

    def test_drumul_taberei_maps_to_sector_6(self, zone_index: ZoneIndex) -> None:
        assert zone_index.zone_for_point(44.4135, 26.0174) in {"Sector 6"}

    def test_point_outside_city_returns_none(self, zone_index: ZoneIndex) -> None:
        assert zone_index.zone_for_point(45.0, 25.0) is None

    def test_canonical_zone_aliases(self) -> None:
        assert canonical_zone_name("Sectorul 1") == "Sector 1"
        assert canonical_zone_name("  sector 2  ") == "Sector 2"
        assert canonical_zone_name("Bucharest") == "Bucuresti"
        assert canonical_zone_name(None) is None


class TestZoneResolver:
    def test_resolve_with_coords(self, zone_index: ZoneIndex) -> None:
        resolver = ZoneResolver(zone_index, prices=DEFAULT_ZONE_PRICES)
        match = resolver.resolve(make_listing(44.4325, 26.1039, 120000, 55))
        assert match.method == "coords"
        assert match.zone == "Sector 3"
        assert match.avg_price_sqm == pytest.approx(1925.0)

    def test_no_coords_is_not_a_match(self, zone_index: ZoneIndex) -> None:
        resolver = ZoneResolver(zone_index, prices=DEFAULT_ZONE_PRICES)
        match = resolver.resolve(make_listing(None, None, 120000, 55))
        assert not match.matched
        assert match.zone == ""
        assert match.avg_price_sqm is None


class TestFinancialFilter:
    def test_viable_within_band(self) -> None:
        listing = make_listing(None, None, 100_000, 55)  # ~1818 EUR/sqm
        result = is_financially_viable(listing, 1925.0)
        assert result.verdict == FinancialVerdict.VIABLE
        assert result.price_per_sqm == pytest.approx(1818.18, rel=1e-3)

    def test_rejects_above_ceiling(self) -> None:
        listing = make_listing(None, None, 160_000, 55)  # ~2909 EUR/sqm > 1925*1.3
        result = is_financially_viable(listing, 1925.0)
        assert result.verdict == FinancialVerdict.TOO_EXPENSIVE

    def test_edge_exactly_at_ceiling_is_viable(self) -> None:
        listing = make_listing(None, None, int(1925 * 1.30 * 55), 55)
        assert is_financially_viable(listing, 1925.0).verdict == FinancialVerdict.VIABLE

    def test_flags_suspicious_below_floor(self) -> None:
        listing = make_listing(None, None, 40_000, 60)  # ~667 EUR/sqm < 1925*0.5
        assert is_financially_viable(listing, 1925.0).verdict == FinancialVerdict.SUSPICIOUS

    def test_missing_price_is_insufficient(self) -> None:
        result = is_financially_viable(make_listing(None, None, None, 55), 1925.0)
        assert result.verdict == FinancialVerdict.INSUFFICIENT_DATA

    def test_missing_sqm_is_insufficient(self) -> None:
        result = is_financially_viable(make_listing(None, None, 100_000, None), 1925.0)
        assert result.verdict == FinancialVerdict.INSUFFICIENT_DATA

    def test_unknown_zone_avg_is_insufficient(self) -> None:
        result = is_financially_viable(make_listing(None, None, 100_000, 55), None)
        assert result.verdict == FinancialVerdict.INSUFFICIENT_DATA

    def test_custom_multipliers_respected(self) -> None:
        listing = make_listing(None, None, 100_000, 55)  # 1818
        assert is_financially_viable(listing, 1000.0).verdict == FinancialVerdict.TOO_EXPENSIVE
        assert is_financially_viable(listing, 1000.0).reason.startswith("asking")


class TestZonePrices:
    def test_default_table_covers_sectors(self) -> None:
        assert SECTORS.issubset(set(DEFAULT_ZONE_PRICES))
        for zone in SECTORS:
            assert DEFAULT_ZONE_PRICES[zone] > 0

    def test_load_zone_prices_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ZONE_AVG_PRICES_EUR_PER_SQM", raising=False)
        assert load_zone_prices() == DEFAULT_ZONE_PRICES

    def test_load_zone_prices_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ZONE_AVG_PRICES_EUR_PER_SQM", json.dumps({"Sector 1": 2700.0}))
        prices = load_zone_prices()
        assert prices["Sector 1"] == 2700.0
        assert prices["Sector 4"] == DEFAULT_ZONE_PRICES["Sector 4"]

    def test_load_zone_prices_ignores_bad_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ZONE_AVG_PRICES_EUR_PER_SQM", "not json")
        assert load_zone_prices() == DEFAULT_ZONE_PRICES