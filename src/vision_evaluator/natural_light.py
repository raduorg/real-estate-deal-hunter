from __future__ import annotations

NATURAL_LIGHT_MIN_SCORE = 1
NATURAL_LIGHT_MAX_SCORE = 5
NATURAL_LIGHT_EXCLUSION_SCORE = 4
NATURAL_LIGHT_WEIGHT = 0.25

NATURAL_LIGHT_LABELS: dict[int, str] = {
    1: "abundant",
    2: "good",
    3: "adequate",
    4: "very little",
    5: "none",
}


def natural_light_component(score: int | None) -> float:
    if score is None:
        return 0.5
    return max(
        0.0,
        min(1.0, (NATURAL_LIGHT_MAX_SCORE - score) / 4.0),
    )


def is_natural_light_excluded(score: int | None) -> bool:
    return score is not None and score >= NATURAL_LIGHT_EXCLUSION_SCORE


def natural_light_label(score: int | None) -> str:
    if score is None:
        return "Unknown"
    return NATURAL_LIGHT_LABELS.get(score, "Unknown")


__all__ = [
    "NATURAL_LIGHT_EXCLUSION_SCORE",
    "NATURAL_LIGHT_LABELS",
    "NATURAL_LIGHT_MAX_SCORE",
    "NATURAL_LIGHT_MIN_SCORE",
    "NATURAL_LIGHT_WEIGHT",
    "is_natural_light_excluded",
    "natural_light_component",
    "natural_light_label",
]
