from __future__ import annotations

import pytest

from src.seismic.risk import (
    is_excluded,
    seismic_component,
    seismic_risk_score,
)


class TestSeismicRiskScore:
    def test_explicit_risk_class_wins(self) -> None:
        # Ad-stated Romanian class trumps year-storeys guessing entirely.
        assert seismic_risk_score(explicit_class=1, construction_year=2010, storeys=3) == 5
        assert seismic_risk_score(explicit_class=2, construction_year=2010, storeys=3) == 4
        assert seismic_risk_score(explicit_class=3) == 3
        assert seismic_risk_score(explicit_class=4) == 2

    def test_pre_1945_tall_building_automatic_max(self) -> None:
        assert seismic_risk_score(construction_year=1938, storeys=4) == 5
        assert seismic_risk_score(construction_year=1900, storeys=3) == 5

    def test_pre_1945_low_rise_high_but_not_excluded(self) -> None:
        assert seismic_risk_score(construction_year=1938, storeys=1) == 4
        assert seismic_risk_score(construction_year=1938) == 4

    def test_1977_1989_era_is_very_low_risk(self) -> None:
        assert seismic_risk_score(construction_year=1977) == 1
        assert seismic_risk_score(construction_year=1985) == 1
        assert seismic_risk_score(construction_year=1989) == 1

    def test_2007_present_is_very_low_risk(self) -> None:
        assert seismic_risk_score(construction_year=2007) == 1
        assert seismic_risk_score(construction_year=2024) == 1

    def test_turbulent_1989_2007_is_low_risk(self) -> None:
        assert seismic_risk_score(construction_year=1990) == 2
        assert seismic_risk_score(construction_year=2000) == 2

    def test_pre_1977_code_medium_risk(self) -> None:
        assert seismic_risk_score(construction_year=1945) == 3
        assert seismic_risk_score(construction_year=1960) == 3
        assert seismic_risk_score(construction_year=1976) == 3

    def test_unknown_year_uses_height_fallback(self) -> None:
        assert seismic_risk_score(storeys=15) == 3
        assert seismic_risk_score(storeys=4) == 2
        assert seismic_risk_score(storeys=2) == 1

    def test_unknown_everything_is_neutral(self) -> None:
        assert seismic_risk_score() == 3

    def test_tall_fallback_even_for_height_only(self) -> None:
        # A 10+ storey block of unknown era is treated as elevated risk.
        assert seismic_risk_score(storeys=10) == 3
        assert seismic_risk_score(storeys=9) == 2


class TestExclusion:
    def test_risk_5_is_excluded(self) -> None:
        for risk in (5,):
            assert is_excluded(risk)

    def test_lower_risks_keep_processing(self) -> None:
        for risk in (None, 1, 2, 3, 4):
            assert not is_excluded(risk)


class TestSeismicComponent:
    def test_linear_safety_curve(self) -> None:
        assert seismic_component(1) == pytest.approx(1.0)
        assert seismic_component(2) == pytest.approx(0.75)
        assert seismic_component(3) == pytest.approx(0.5)
        assert seismic_component(4) == pytest.approx(0.25)
        assert seismic_component(5) == pytest.approx(0.0)

    def test_unknown_is_neutral(self) -> None:
        assert seismic_component(None) == pytest.approx(0.5)

    def test_out_of_range_clamped(self) -> None:
        assert seismic_component(0) == pytest.approx(1.0)
        assert seismic_component(99) == pytest.approx(0.0)