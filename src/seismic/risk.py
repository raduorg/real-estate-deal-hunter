"""Seismic risk scoring for Bucharest apartments — pure logic, no I/O.

The score is a 1..5 scale where 1 = no meaningful risk and 5 = highest risk.
It is used in two places:

* as an exclusion gate: risk 5 listings are skipped before any vision spend
* as a ~25% component of the Stage 6 deal score

Signals come from the ad text / structured JSON of a listing page: an explicit
Romanian seismic risk class ("risc seismic 1"), the construction year and the
building height in storeys. The rationale follows the Bucharest earthquake
history:

* 1977 Vrancea quake triggered the first stringent seismic code; everything
  built 1977-1989 is treated as very low risk.
* 2007+ (post EU-accession eurocodes) is also very low risk.
* 1989-2007 is a turbulent era where enforcement was laxer -> low-ish risk.
* 1945-1977 predates the stringent code -> medium risk.
* Interwar/pre-1945 unreinforced masonry is the classic collapse type, and
  pre-1945 buildings with >=3 storeys are effectively the worst case.
* Taller buildings are more vulnerable than low-rise; height is a fallback
  signal when the construction year is unknown.
"""

from __future__ import annotations

# Score threshold at which a listing is excluded before any further spend.
EXCLUSION_RISK = 5

# Share of the Stage 6 deal score governed by seismic safety.
SEISMIC_WEIGHT = 0.25

_DEFAULT_RISK = 3  # completely unknown signals -> neutral score


def seismic_component(risk: int | None) -> float:
    """0..1 seismic *safety*: 1 = low risk, 0 = worst case, unknown = neutral."""
    if risk is None:
        return 0.5
    return max(0.0, min(1.0, (EXCLUSION_RISK - risk) / 4.0))


def _risk_from_year(year: int) -> int:
    if year < 1945:
        return 4  # interwar + older low-rise masonry
    if year < 1977:
        return 3  # pre-stringent 1977 code
    if year <= 1989:
        return 1  # 1977-1989: built under the stringent code
    if year < 2007:
        return 2  # 1989-2007: turbulent, laxer enforcement
    return 1  # 2007-present: modern eurocode era


def _risk_from_height(storeys: int | None) -> int:
    """Fallback when the construction year is unknown: taller = more exposed."""
    if storeys is None:
        return _DEFAULT_RISK
    if storeys >= 10:
        return 3
    if storeys >= 3:
        return 2
    return 1


def seismic_risk_score(
    explicit_class: int | None = None,
    construction_year: int | None = None,
    storeys: int | None = None,
) -> int:
    """1..5 seismic risk score.

    Precedence:
    1. Ad-stated Romanian risk class  (class 1 -> 5, class 2 -> 4, 3 -> 3, 4 -> 2)
    2. Pre-1945 building with >=3 storeys -> 5 (excluded)
    3. Construction-year band
    4. Height heuristic when the year is unknown
    """
    if explicit_class is not None:
        return 6 - explicit_class
    if construction_year is not None:
        if construction_year < 1945 and storeys is not None and storeys >= 3:
            return EXCLUSION_RISK
        return _risk_from_year(construction_year)
    return _risk_from_height(storeys)


def is_excluded(risk: int | None) -> bool:
    """True when a listing must be dropped before any vision spend."""
    return risk == EXCLUSION_RISK


__all__ = [
    "EXCLUSION_RISK",
    "SEISMIC_WEIGHT",
    "is_excluded",
    "seismic_component",
    "seismic_risk_score",
]