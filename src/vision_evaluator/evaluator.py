"""Stage 5: Structured vision evaluation via local Ollama (gemma4).

A single constrained inference pass over a listing's photos. The respondent
must return JSON matching the rigid schema in `prompts.py`; Ollama's `format`
enforces it server-side. No agent orchestration, no cloud spend.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

from src.config import Config, VisionConfig
from src.email_listener.db import Database
from src.models.listing import Listing, ListingStatus, VisionAnalysis
from src.vision_evaluator.images import ImageDownloader, to_base64
from src.vision_evaluator.natural_light import (
    NATURAL_LIGHT_MAX_SCORE,
    NATURAL_LIGHT_MIN_SCORE,
)
from src.vision_evaluator.prompts import (
    SYSTEM_PROMPT,
    build_user_prompt,
    vision_json_schema,
)

logger = logging.getLogger(__name__)


class VisionError(Exception):
    """Raised when a vision pass cannot produce a valid assessment."""


def _strip_code_fence(content: str) -> str:
    content = content.strip()
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.MULTILINE)


def parse_analysis_response(
    content: str, listing_id: str, allowed: dict[str, list[str]] | None = None
) -> VisionAnalysis:
    """Parse the model's JSON reply into a validated VisionAnalysis.

    The model is asked for JSON only, but gemma-class models occasionally wrap
    the object in markdown fences or trailing prose; tolerate that. Invalid /
    non-JSON output raises VisionError so the caller can retry.
    """
    allowed = allowed or {}
    text = _strip_code_fence(content)
    try:
        data: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VisionError(f"model returned non-JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise VisionError(f"model returned non-object JSON: {type(data).__name__}")

    def _enum(key: str, fallback: str = "unknown") -> str:
        value = data.get(key)
        choices = allowed.get(key)
        if choices and value in choices:
            return value
        if choices:
            logger.warning("Vision %s invalid (%r), defaulting to %s", key, value, fallback)
            return fallback
        return value or fallback

    try:
        score = float(data.get("image_score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(10.0, score))

    try:
        renovation = int(data.get("estimated_renovation_cost_eur_per_sqm", 0))
    except (TypeError, ValueError):
        renovation = 0
    renovation = max(0, min(1500, renovation))

    light_score: int | None = None
    light_raw = data.get("natural_light_score")
    if light_raw is not None and not isinstance(light_raw, bool):
        try:
            light_value = float(light_raw)
        except (TypeError, ValueError):
            light_value = -1.0
        if (
            light_value.is_integer()
            and NATURAL_LIGHT_MIN_SCORE <= light_value <= NATURAL_LIGHT_MAX_SCORE
        ):
            light_score = int(light_value)
        else:
            logger.warning(
                "Vision invalid natural_light_score=%r; defaulting to unknown",
                light_raw,
            )

    breakers_raw = data.get("deal_breakers", [])
    breakers = (
        [str(b).strip() for b in breakers_raw if str(b).strip()]
        if isinstance(breakers_raw, list)
        else []
    )

    return VisionAnalysis(
        listing_id=listing_id,
        condition_tier=_enum("condition_tier"),
        estimated_renovation_cost_eur_per_sqm=renovation,
        heating_type_visible=_enum("heating_type_visible"),
        window_type=_enum("window_type"),
        deal_breakers=breakers,
        image_score=score,
        natural_light_score=light_score,
        natural_light_notes=str(data.get("natural_light_notes") or "").strip(),
        reasoning=str(data.get("reasoning") or "").strip(),
    )


class VisionEvaluator:
    """Runs the vision pass and persists results to the database."""

    def __init__(
        self,
        config: Config,
        db: Database,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.vision: VisionConfig = config.vision
        self.db = db
        self._transport = transport
        self.images = ImageDownloader(config.vision, transport=transport)
        self.allowed: dict[str, list[str]] = {
            "condition_tier": ["needs_total_renovation", "habitable_dated",
                               "renovated_standard", "luxury"],
            "heating_type_visible": ["gas_boiler", "district_radiators",
                                     "electric", "heat_pump", "unknown"],
            "window_type": ["modern_pvc", "old_wood", "mixed", "unknown"],
        }

    async def evaluate_listing(self, listing: Listing) -> VisionAnalysis | None:
        """Full pass: download photos -> one Ollama call -> parsed analysis.

        Returns None when there is nothing to evaluate (no usable images).
        """
        photos = await self.images.download(listing.image_urls, referer=listing.url)
        if not photos:
            logger.info("No usable photos for %s; skipping vision", listing.id)
            return None

        prompt = build_user_prompt(
            title=listing.title,
            description=listing.description,
            price_eur=listing.price_eur,
            sqm=listing.sqm,
            rooms=listing.rooms,
            neighborhood=listing.neighborhood,
        )

        content = await self._chat_once(prompt, photos)
        if not content:
            raise VisionError("model returned empty reply")

        analysis = parse_analysis_response(content, listing.id, allowed=self.allowed)
        logger.info(
            "Vision %s: tier=%s score=%.1f reno=%d EUR/sqm light=%s breakers=%d",
            listing.id,
            analysis.condition_tier,
            analysis.image_score,
            analysis.estimated_renovation_cost_eur_per_sqm,
            analysis.natural_light_score,
            len(analysis.deal_breakers),
        )
        return analysis

    async def _chat_once(self, prompt: str, photos: list[bytes]) -> str:
        payload = {
            "model": self.vision.ollama_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": prompt,
                    "images": [to_base64(p) for p in photos],
                },
            ],
            "stream": False,
            "format": vision_json_schema(),
            "keep_alive": "30m",
            "options": {"temperature": self.vision.temperature},
        }

        last_error: BaseException | None = None
        for attempt in range(1, self.vision.max_retries + 1):
            try:
                response = await self._post("/api/chat", payload)
                if response.status_code != httpx.codes.OK:
                    raise VisionError(f"ollama HTTP {response.status_code}: {response.text[:300]}")
                body = response.json()
                message = body.get("message", {}) or {}
                content = message.get("content", "") or ""
                # Thinking models may put prose only in `thinking`; content is
                # the final answer — empty final answer is a failure.
                if not content.strip():
                    raise VisionError("empty assistant content")
                # The reply must already be valid JSON for the schema to matter;
                # a malformed reply is worth a retry (transient model slip).
                parsed = json.loads(_strip_code_fence(content))
                if not isinstance(parsed, dict):
                    raise VisionError("model returned non-object JSON")
                for field in ("reasoning", "natural_light_notes"):
                    value = parsed.get(field)
                    if not isinstance(value, str) or not value.strip():
                        raise VisionError(f"model returned empty {field}")
                return content.strip()
            except (httpx.HTTPError, VisionError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.vision.max_retries:
                    delay = 2.0 ** attempt + (attempt * 1.5)
                    logger.warning(
                        "Vision attempt %d/%d failed: %s: %s; retrying in %.1fs",
                        attempt, self.vision.max_retries, type(exc).__name__, exc, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
        raise VisionError(f"vision failed after {self.vision.max_retries} attempts: {last_error}")

    async def _post(self, path: str, payload: dict[str, Any]):
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=httpx.Timeout(self.vision.timeout),
        ) as client:
            return await client.post(f"{self.vision.ollama_host}{path}", json=payload)

    async def process_new(self, limit: int | None = None) -> int:
        """Evaluate every listing stuck in status='extracted'."""
        await self.db.connect()
        try:
            listings = await self.db.get_listings_by_status(ListingStatus.EXTRACTED)
            if limit is not None:
                listings = listings[:limit]
            if not listings:
                logger.info("No extracted listings awaiting vision")
                return 0

            evaluated = 0
            for listing in listings:
                try:
                    analysis = await self.evaluate_listing(listing)
                except VisionError as exc:
                    # Revert so a later pass re-tries; do not burn the row.
                    await self.db.update_listing_status(listing.id, ListingStatus.EXTRACTED)
                    logger.error("Vision failed for %s: %s", listing.id, exc)
                    continue
                except Exception:
                    await self.db.update_listing_status(listing.id, ListingStatus.EXTRACTED)
                    logger.exception("Unexpected vision failure for %s", listing.id)
                    continue

                if analysis is None:
                    await self.db.update_listing_status(listing.id, ListingStatus.SKIPPED)
                    continue
                await self.db.save_vision_analysis(
                    listing_id=listing.id,
                    analysis=analysis,
                    model=self.vision.ollama_model,
                    images_used=min(len(listing.image_urls), self.vision.max_images),
                )
                await self.db.update_listing_status(listing.id, ListingStatus.ANALYZED)
                evaluated += 1
            logger.info("Vision pass finished: %d/%d analyzed", evaluated, len(listings))
            return evaluated
        finally:
            await self.db.close()

    @classmethod
    def from_config(cls, config: Config) -> VisionEvaluator:
        return cls(config, Database(config.database_path))


__all__ = ["VisionAnalysis", "VisionEvaluator", "VisionError", "parse_analysis_response"]