from __future__ import annotations

import pytest

from src.deal_calculator.valuator import (
    DealScore,
    adjusted_price_per_sqm,
    condition_component,
    deal_score,
    discount_component,
    discount_percent,
    evaluate_deal,
    total_renovation_cost,
)
from src.models.listing import Listing, VisionAnalysis

SECTOR_3_AVG = 1925.0


def make_listing(
    price: int | None = 100_000,
    sqm: float | None = 55,
    seismic_risk: int | None = 1,
) -> Listing:
    return Listing(
        id="deal-test",
        url="https://example.test/",
        price_eur=price,
        sqm=sqm,
        seismic_risk=seismic_risk,
    )


def make_analysis(
    renovation: int = 200, tier: str = "habitable_dated"
) -> VisionAnalysis:
    return VisionAnalysis(
        listing_id="deal-test",
        condition_tier=tier,
        estimated_renovation_cost_eur_per_sqm=renovation,
    )


class TestArithmetic:
    def test_total_renovation_cost(self) -> None:
        assert total_renovation_cost(200, 55) == 11_000
        assert total_renovation_cost(0, 55) == 0
        assert total_renovation_cost(200, 0) == 0

    def test_adjusted_price_per_sqm(self) -> None:
        # (100_000 + 11_000) / 55
        assert adjusted_price_per_sqm(100_000, 11_000, 55) == pytest.approx(2018.18)
        assert adjusted_price_per_sqm(None, 11_000, 55) is None
        assert adjusted_price_per_sqm(100_000, 11_000, None) is None

    def test_discount_percent_positive_when_cheaper(self) -> None:
        # adjusted 1818 vs market 1925 => ~5.56% cheaper
        assert discount_percent(1925.0, 1818.18) == pytest.approx(5.55, rel=1e-2)
        assert discount_percent(None, 1818.18) is None
        assert discount_percent(1925.0, None) is None

    def test_discount_component_clamps(self) -> None:
        assert discount_component(15.0, 40.0) == pytest.approx(0.375)
        assert discount_component(-5.0, 40.0) == 0.0
        assert discount_component(60.0, 40.0) == 1.0

    def test_condition_component(self) -> None:
        assert condition_component("needs_total_renovation") == pytest.approx(0.25)
        assert condition_component("habitable_dated") == pytest.approx(0.5)
        assert condition_component("luxury") == 1.0
        assert condition_component("unknown") == 0.0


class TestDealScore:
    def test_weighted_blend_with_no_seismic_risk(self) -> None:
        # 15% discount -> 0.375; habitable_dated -> 0.5; unknown seismic -> 0.5
        # 100 * (0.6*0.375 + 0.15*0.5 + 0.25*0.5) / 1.0 = 42.5
        assert deal_score(15.0, "habitable_dated", None) == pytest.approx(42.5)

    def test_seismic_risk_moves_the_score(self) -> None:
        # Same discount/condition; seismic 1 (safest) vs 4 (risky).
        assert deal_score(15.0, "habitable_dated", 1) == pytest.approx(55.0)
        assert deal_score(15.0, "habitable_dated", 4) == pytest.approx(36.2)
        assert deal_score(15.0, "habitable_dated", 1) > deal_score(
            15.0, "habitable_dated", 4
        )

    def test_no_market_reference_scores_condition_and_seismic_only(self) -> None:
        # discount unknown -> discount weight dropped; 0.5 condition, 0.5 seismic
        # 100 * (0.15*0.5 + 0.25*0.5) / 0.4 = 50
        assert deal_score(None, "habitable_dated", None) == pytest.approx(50.0)

    def test_overpriced_clamps_to_condition_and_seismic(self) -> None:
        # discount clamped to 0; risk 1 (safe) keeps a floor on the score.
        assert deal_score(-10.0, "needs_total_renovation", 1) == pytest.approx(28.7)


class TestEvaluateDeal:
    def test_real_deal_flagged(self) -> None:
        # price 80k, 55sqm, reno 200/sqm => adjusted 1654.5; market 1925 => 14.05% off
        result = evaluate_deal(
            make_listing(80_000, 55, seismic_risk=1),
            make_analysis(renovation=200, tier="renovated_standard"),
            SECTOR_3_AVG,
        )
        assert isinstance(result, DealScore)
        assert result.total_renovation_cost == 11_000
        assert result.adjusted_price_per_sqm == pytest.approx(1654.55, abs=0.01)
        assert result.discount_percentage == pytest.approx(14.05, abs=0.01)
        assert result.is_deal
        assert result.condition_tier == "renovated_standard"
        assert result.seismic_risk == 1
        # 100 * (0.6 * 14.05/40 + 0.15 * 0.75 + 0.25 * 1.0) = 57.3
        assert result.deal_score == pytest.approx(57.3, abs=0.1)

    def test_reno_wipes_discount_no_deal(self) -> None:
        # 100k + 300/sqm reno on 55sqm => adjusted 2118; market 1925 => -10% (overpriced)
        result = evaluate_deal(
            make_listing(100_000, 55, seismic_risk=2),
            make_analysis(renovation=300, tier="needs_total_renovation"),
            SECTOR_3_AVG,
        )
        assert not result.is_deal
        assert result.discount_percentage < 0
        assert result.seismic_risk == 2
        # condition 0.25, seismic 2 -> 0.75: 100*(0.15*0.25+0.25*0.75) = 22.5
        assert result.deal_score == pytest.approx(22.5)

    def test_seismic_risk_poor_building_needs_more_discount(self) -> None:
        # Same deal with a risky (4/5) building scores lower than a safe one.
        safe = evaluate_deal(
            make_listing(80_000, 55, seismic_risk=1),
            make_analysis(renovation=200, tier="renovated_standard"),
            SECTOR_3_AVG,
        )
        risky = evaluate_deal(
            make_listing(80_000, 55, seismic_risk=4),
            make_analysis(renovation=200, tier="renovated_standard"),
            SECTOR_3_AVG,
        )
        assert safe.deal_score > risky.deal_score

    def test_custom_threshold(self) -> None:
        # 5% discount is a deal only when threshold is low enough
        listing, analysis = make_listing(85_000, 55), make_analysis(renovation=50)
        strict = evaluate_deal(listing, analysis, SECTOR_3_AVG, deal_threshold_percent=20.0)
        lenient = evaluate_deal(listing, analysis, SECTOR_3_AVG, deal_threshold_percent=4.0)
        assert not strict.is_deal
        assert lenient.is_deal

    def test_no_market_avg_never_a_deal(self) -> None:
        result = evaluate_deal(make_listing(seismic_risk=None), make_analysis(), None)
        assert not result.is_deal
        assert result.discount_percentage == 0.0
        assert result.deal_score > 0  # condition + seismic still contribute

    def test_missing_price_sqm_defensive(self) -> None:
        assert not evaluate_deal(make_listing(None, 55), make_analysis(), SECTOR_3_AVG).is_deal
        assert not evaluate_deal(make_listing(100_000, None), make_analysis(), SECTOR_3_AVG).is_deal
        assert not evaluate_deal(make_listing(100_000, 0), make_analysis(), SECTOR_3_AVG).is_deal

    def test_custom_weights(self) -> None:
        result = evaluate_deal(
            make_listing(80_000, 55),
            make_analysis(renovation=200, tier="renovated_standard"),
            SECTOR_3_AVG,
            discount_weight=0.5,
            condition_weight=0.5,
            seismic_weight=0.0,
        )
        assert result.is_deal
        # 100 * (0.5*0.351 + 0.5*0.75) = 55.06
        assert result.deal_score == pytest.approx(55.1)