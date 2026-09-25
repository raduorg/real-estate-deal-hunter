"""Vision evaluation via local Ollama (Stage 5)."""

from src.vision_evaluator.evaluator import (
    VisionAnalysis,
    VisionError,
    VisionEvaluator,
    parse_analysis_response,
)
from src.vision_evaluator.images import ImageDownloader, to_base64, validate_image
from src.vision_evaluator.natural_light import (
    NATURAL_LIGHT_EXCLUSION_SCORE,
    NATURAL_LIGHT_LABELS,
    NATURAL_LIGHT_MAX_SCORE,
    NATURAL_LIGHT_MIN_SCORE,
    NATURAL_LIGHT_WEIGHT,
    is_natural_light_excluded,
    natural_light_component,
    natural_light_label,
)
from src.vision_evaluator.prompts import (
    SYSTEM_PROMPT,
    build_user_prompt,
    vision_json_schema,
)

__all__ = [
    "SYSTEM_PROMPT",
    "NATURAL_LIGHT_EXCLUSION_SCORE",
    "NATURAL_LIGHT_LABELS",
    "NATURAL_LIGHT_MAX_SCORE",
    "NATURAL_LIGHT_MIN_SCORE",
    "NATURAL_LIGHT_WEIGHT",
    "is_natural_light_excluded",
    "natural_light_component",
    "natural_light_label",
    "VisionAnalysis",
    "VisionError",
    "VisionEvaluator",
    "ImageDownloader",
    "build_user_prompt",
    "parse_analysis_response",
    "to_base64",
    "validate_image",
    "vision_json_schema",
]