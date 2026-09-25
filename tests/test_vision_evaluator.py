from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest

from src.config import Config, EmailConfig, TargetConfig, VisionConfig
from src.email_listener.db import Database
from src.models.listing import Listing, ListingStatus, VisionAnalysis
from src.vision_evaluator.evaluator import (
    VisionError,
    VisionEvaluator,
    parse_analysis_response,
)
from src.vision_evaluator.images import ImageDownloader, to_base64, validate_image
from src.vision_evaluator.prompts import SYSTEM_PROMPT, build_user_prompt, vision_json_schema

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNg"
    "AAIAAAUAAXpeqz8AAAAASUVORK5CYII="
)
HTML_BYTES = b"<html><body>not an image</body></html>"

PNG_URL = "https://cdn.test/pic.png"
_IMAGE_RESPONSE = httpx.Response(
    200, content=PNG_BYTES, headers={"content-type": "image/png"}
)


def make_config(max_retries: int = 3) -> Config:
    return Config(
        email=EmailConfig(user="u", password="p"),
        target=TargetConfig(),
        vision=VisionConfig(
            ollama_host="http://ollama.test",
            ollama_model="gemma4:26b",
            timeout=5.0,
            max_retries=max_retries,
            temperature=0.0,
        ),
    )


def make_listing(image_urls: list[str] | None = None) -> Listing:
    return Listing(
        id="t1",
        url="https://www.storia.ro/ro/oferta/apartament-abc",
        title="Apartament 2 camere, Pipera",
        description="Renovat partial, centrala proprie.",
        price_eur=85000,
        sqm=55,
        rooms=2,
        neighborhood="Pipera",
        status=ListingStatus.EXTRACTED,
        image_urls=image_urls or [PNG_URL],
    )


def valid_ollama_content() -> str:
    return json.dumps(
        {
            "condition_tier": "habitable_dated",
            "estimated_renovation_cost_eur_per_sqm": 320,
            "heating_type_visible": "gas_boiler",
            "window_type": "modern_pvc",
            "deal_breakers": ["old_fuse_box"],
            "image_score": 6.5,
            "natural_light_score": 2,
            "natural_light_notes": "Good daylight from the living-room windows.",
            "reasoning": "Dated but functional finishes.",
        }
    )


class TestImages:
    def test_validate_image_accepts_real_photo(self):
        assert validate_image(PNG_BYTES, "image/png")
        assert validate_image(PNG_BYTES, "")

    def test_validate_image_rejects_html_and_random_bytes(self):
        assert not validate_image(HTML_BYTES, "text/html")
        assert not validate_image(b"\x00\x01\x02\x03", "")
        assert not validate_image(b"", "")

    def test_to_base64_roundtrip(self):
        assert base64.b64decode(to_base64(PNG_BYTES)) == PNG_BYTES

    def test_download_returns_only_valid_photos(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "cdn.test":
                return _IMAGE_RESPONSE
            return httpx.Response(200, content=HTML_BYTES, headers={"content-type": "text/html"})

        downloader = ImageDownloader(VisionConfig(), transport=httpx.MockTransport(handler))
        photos = asyncio.run(
            downloader.download(["https://cdn.test/a.png", "https://other.test/a.html"])
        )
        assert photos == [PNG_BYTES]

    def test_download_respects_max_images(self):
        downloader = ImageDownloader(
            VisionConfig(max_images=2), transport=httpx.MockTransport(lambda r: _IMAGE_RESPONSE)
        )
        photos = asyncio.run(
            downloader.download([f"https://cdn.test/{i}.png" for i in range(5)])
        )
        assert len(photos) == 2


class TestPrompts:
    def test_build_user_prompt_includes_listing_context(self):
        prompt = build_user_prompt(
            title="Apartament 2 camere",
            description="Renovat integral, centrala termica.",
            price_eur=85000,
            sqm=55,
            rooms=2,
            neighborhood="Bucuresti, Pipera",
        )
        assert "Apartament 2 camere" in prompt
        assert "85000" in prompt
        assert "Pipera" in prompt
        assert "centrala termica" in prompt

    def test_vision_json_schema_has_required_fields(self):
        assert "never artificial lighting" in SYSTEM_PROMPT
        schema = vision_json_schema()
        props = schema["properties"]
        assert schema["type"] == "object"
        for field in (
            "condition_tier",
            "estimated_renovation_cost_eur_per_sqm",
            "heating_type_visible",
            "window_type",
            "deal_breakers",
            "image_score",
            "natural_light_score",
            "natural_light_notes",
            "reasoning",
        ):
            assert field in props


class TestParseResponse:
    def test_ok(self):
        analysis = parse_analysis_response(valid_ollama_content(), "t1")
        assert isinstance(analysis, VisionAnalysis)
        assert analysis.condition_tier == "habitable_dated"
        assert analysis.image_score == 6.5
        assert analysis.heating_type_visible == "gas_boiler"
        assert analysis.deal_breakers == ["old_fuse_box"]
        assert analysis.natural_light_score == 2
        assert analysis.natural_light_notes.startswith("Good daylight")

    def test_strips_markdown_fence(self):
        content = '```json\n{"condition_tier": "luxury", "image_score": 9}\n```'
        analysis = parse_analysis_response(content, "t1")
        assert analysis.condition_tier == "luxury"
        assert analysis.image_score == 9.0

    def test_defaults_and_clamps(self):
        content = json.dumps({"image_score": 15, "estimated_renovation_cost_eur_per_sqm": -3})
        analysis = parse_analysis_response(content, "t1")
        assert analysis.image_score == 10.0
        assert analysis.estimated_renovation_cost_eur_per_sqm == 0
        assert analysis.condition_tier == "unknown"

    @pytest.mark.parametrize("value", [0, 6, 3.5, "bad"])
    def test_invalid_natural_light_score_is_unknown(self, value):
        content = json.dumps({"natural_light_score": value})
        analysis = parse_analysis_response(content, "t1")
        assert analysis.natural_light_score is None

    def test_rejects_enum_out_of_choices(self):
        content = json.dumps({"condition_tier": "banana", "image_score": 5})
        allowed = {"condition_tier": ["needs_total_renovation", "luxury"]}
        analysis = parse_analysis_response(content, "t1", allowed=allowed)
        assert analysis.condition_tier == "unknown"

    def test_rejects_non_json(self):
        with pytest.raises(VisionError):
            parse_analysis_response("totally not json", "t1")


class TestEvaluator:
    def test_full_pass_returns_analysis(self):
        transport = httpx.MockTransport(
            lambda req: valid_ollama_response()
            if req.url.path == "/api/chat"
            else _IMAGE_RESPONSE
        )
        evaluator = VisionEvaluator(make_config(), Database(":memory:"), transport=transport)
        analysis = asyncio.run(evaluator.evaluate_listing(make_listing()))
        assert analysis is not None
        assert analysis.condition_tier == "habitable_dated"
        assert analysis.image_score == 6.5
        assert analysis.deal_breakers == ["old_fuse_box"]
        assert analysis.natural_light_score == 2

    def test_empty_narrative_is_retried(self):
        calls = {"n": 0}
        empty = json.loads(valid_ollama_content())
        empty["reasoning"] = ""
        empty["natural_light_notes"] = ""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/chat":
                calls["n"] += 1
                content = json.dumps(empty) if calls["n"] == 1 else valid_ollama_content()
                return httpx.Response(200, json={"message": {"content": content}})
            return _IMAGE_RESPONSE

        evaluator = VisionEvaluator(
            make_config(), Database(":memory:"), transport=httpx.MockTransport(handler)
        )
        analysis = asyncio.run(evaluator.evaluate_listing(make_listing()))
        assert calls["n"] == 2
        assert analysis is not None
        assert analysis.reasoning

    def test_no_images_returns_none_without_calling_llm(self):
        transport = httpx.MockTransport(lambda req: pytest.fail("unexpected call"))
        evaluator = VisionEvaluator(make_config(), Database(":memory:"), transport=transport)
        analysis = asyncio.run(evaluator.evaluate_listing(make_listing(image_urls=[])))
        assert analysis is None

    def test_retries_then_succeeds_on_transient_500(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/chat":
                calls["n"] += 1
                if calls["n"] < 2:
                    return httpx.Response(500, text="server busy")
                return valid_ollama_response()
            return _IMAGE_RESPONSE

        evaluator = VisionEvaluator(
            make_config(), Database(":memory:"), transport=httpx.MockTransport(handler)
        )
        analysis = asyncio.run(evaluator.evaluate_listing(make_listing()))
        assert calls["n"] == 2
        assert analysis.condition_tier == "habitable_dated"

    def test_fails_after_max_retries_on_persistent_500(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/chat":
                return httpx.Response(500, text="boom")
            return _IMAGE_RESPONSE

        evaluator = VisionEvaluator(
            make_config(), Database(":memory:"), transport=httpx.MockTransport(handler)
        )
        with pytest.raises(VisionError):
            asyncio.run(evaluator.evaluate_listing(make_listing()))

    def test_invalid_json_retried_then_fails(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/chat":
                calls["n"] += 1
                return httpx.Response(200, json={"message": {"content": "not json"}})
            return _IMAGE_RESPONSE

        evaluator = VisionEvaluator(
            make_config(), Database(":memory:"), transport=httpx.MockTransport(handler)
        )
        with pytest.raises(VisionError):
            asyncio.run(evaluator.evaluate_listing(make_listing()))
        assert calls["n"] == 3


def valid_ollama_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={"message": {"role": "assistant", "content": valid_ollama_content()}},
    )


class TestDbPersistence:
    def test_save_and_load_vision_analysis(self, tmp_path):
        db = Database(tmp_path / "test.db")

        async def run():
            await db.connect()
            await db.save_listing(Listing(id="x1", url="https://example.test/"))
            analysis = VisionAnalysis(
                listing_id="x1",
                condition_tier="luxury",
                image_score=9.1,
                natural_light_score=1,
                natural_light_notes="Bright rooms with large windows.",
                reasoning="High-end finish.",
            )
            await db.save_vision_analysis("x1", analysis, model="gemma4:26b", images_used=3)
            loaded = await db.get_vision_analysis("x1")
            assert loaded is not None
            assert loaded.condition_tier == "luxury"
            assert loaded.image_score == 9.1
            assert loaded.natural_light_score == 1
            assert loaded.natural_light_notes == "Bright rooms with large windows."
            assert loaded.reasoning == "High-end finish."
            await db.close()

        asyncio.run(run())

    def test_process_new_marks_listings_analyzed(self, tmp_path):
        db = Database(tmp_path / "test.db")

        async def run():
            await db.connect()
            listing = make_listing()
            listing.status = ListingStatus.EXTRACTED
            await db.save_listing(listing)
            evaluator = VisionEvaluator(make_config(), db, transport=httpx.MockTransport(
                lambda req: valid_ollama_response()
                if req.url.path == "/api/chat"
                else _IMAGE_RESPONSE
            ))
            assert await evaluator.process_new() == 1
            await db.connect()  # process_new closes its connection
            rows = await db.get_listings_by_status(ListingStatus.ANALYZED)
            assert len(rows) == 1
            assert rows[0].id == listing.id
            assert await db.get_vision_analysis(listing.id) is not None
            await db.close()

        asyncio.run(run())