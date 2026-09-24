from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class EmailConfig:
    user: str
    password: str
    imap_server: str = "imap.gmail.com"
    imap_port: int = 993
    poll_interval: int = 60


@dataclass(frozen=True)
class VisionConfig:
    """Stage 5 multimodal evaluation via local Ollama (free, offline)."""

    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma4:26b"
    timeout: float = 300.0
    max_retries: int = 3
    max_images: int = 10
    image_timeout: float = 20.0
    max_image_bytes: int = 15 * 1024 * 1024
    temperature: float = 0.2
    openai_api_key: str = ""
    google_ai_api_key: str = ""


@dataclass(frozen=True)
class TargetConfig:
    city: str = "Bucharest"
    max_price_eur: int = 150_000
    min_sqm: int = 50


@dataclass(frozen=True)
class ExtractorConfig:
    """Conservative page-fetch settings to stay under anti-bot radar."""

    min_delay: float = 6.0
    max_delay: float = 12.0
    timeout: float = 30.0
    max_retries: int = 3
    max_images: int = 15
    proxy_url: str = ""


@dataclass(frozen=True)
class ZoneConfig:
    """Stage 3-4 geospatial verification and early-exit math gate."""

    geojson_path: Path = field(default_factory=lambda: Path("data/zones/bucharest_sectors.geojson"))
    ceiling_multiplier: float = 1.30
    floor_multiplier: float = 0.50
    fallback_city: str = "Bucuresti"


@dataclass(frozen=True)
class NotifierConfig:
    """Stage 7 email digest dispatch via Zoho SMTP (SSL)."""

    smtp_host: str = "smtp.zoho.eu"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    recipient: str = "radu@orghidan.ro"


@dataclass(frozen=True)
class DealConfig:
    """Stage 6 valuation & deal scoring thresholds (pure arithmetic).

    discount_weight + condition_weight + seismic_weight should sum to 1.0;
    seismic carries ~25% by default per the Bucharest earthquake rationale.
    """

    deal_threshold_percent: float = 10.0
    max_discount_percent: float = 40.0
    discount_weight: float = 0.60
    condition_weight: float = 0.15
    seismic_weight: float = 0.25
    min_price_eur: int = 10_000


@dataclass(frozen=True)
class Config:
    email: EmailConfig
    vision: VisionConfig
    target: TargetConfig
    extractor: ExtractorConfig = field(default_factory=ExtractorConfig)
    zones: ZoneConfig = field(default_factory=ZoneConfig)
    deals: DealConfig = field(default_factory=DealConfig)
    notifier: NotifierConfig = field(default_factory=NotifierConfig)
    database_path: Path = field(default_factory=lambda: Path("data/listings.db"))
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


def load_config(env_path: str | Path | None = None) -> Config:
    if env_path is None:
        env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)

    def _require(key: str) -> str:
        val = os.getenv(key)
        if not val:
            raise ValueError(f"Missing required environment variable: {key}")
        return val

    return Config(
        email=EmailConfig(
            user=_require("EMAIL_USER"),
            password=_require("EMAIL_PASSWORD"),
            imap_server=os.getenv("IMAP_SERVER", "imap.gmail.com"),
            imap_port=int(os.getenv("IMAP_PORT", "993")),
            poll_interval=int(os.getenv("EMAIL_POLL_INTERVAL_SECONDS", "60")),
        ),
        vision=VisionConfig(
            ollama_host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=os.getenv("OLLAMA_VISION_MODEL", "gemma4:26b"),
            timeout=float(os.getenv("VISION_TIMEOUT_SECONDS", "300")),
            max_retries=int(os.getenv("VISION_MAX_RETRIES", "3")),
            max_images=int(os.getenv("VISION_MAX_IMAGES", "10")),
            image_timeout=float(os.getenv("VISION_IMAGE_TIMEOUT_SECONDS", "20")),
            max_image_bytes=int(os.getenv("VISION_MAX_IMAGE_BYTES", str(15 * 1024 * 1024))),
            temperature=float(os.getenv("VISION_TEMPERATURE", "0.2")),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            google_ai_api_key=os.getenv("GOOGLE_AI_API_KEY", ""),
        ),
        target=TargetConfig(
            city=os.getenv("TARGET_CITY", "Bucharest"),
            max_price_eur=int(os.getenv("MAX_PRICE_EUR", "150000")),
            min_sqm=int(os.getenv("MIN_SQM", "50")),
        ),
        extractor=ExtractorConfig(
            min_delay=float(os.getenv("FETCH_MIN_DELAY_SECONDS", "6")),
            max_delay=float(os.getenv("FETCH_MAX_DELAY_SECONDS", "12")),
            timeout=float(os.getenv("HTTP_TIMEOUT_SECONDS", "30")),
            max_retries=int(os.getenv("FETCH_MAX_RETRIES", "3")),
            max_images=int(os.getenv("MAX_IMAGES_PER_LISTING", "15")),
            proxy_url=os.getenv("PROXY_URL", ""),
        ),
        zones=ZoneConfig(
            geojson_path=Path(
                os.getenv("ZONE_BOUNDARIES_PATH", "data/zones/bucharest_sectors.geojson")
            ),
            ceiling_multiplier=float(os.getenv("EARLY_EXIT_CEILING_MULTIPLIER", "1.30")),
            floor_multiplier=float(os.getenv("EARLY_EXIT_FLOOR_MULTIPLIER", "0.50")),
            fallback_city=os.getenv("ZONE_FALLBACK_CITY", "Bucuresti"),
        ),
        deals=DealConfig(
            deal_threshold_percent=float(os.getenv("DEAL_THRESHOLD_PERCENT", "10")),
            max_discount_percent=float(os.getenv("DEAL_MAX_DISCOUNT_PERCENT", "40")),
            discount_weight=float(os.getenv("DEAL_DISCOUNT_WEIGHT", "0.60")),
            condition_weight=float(os.getenv("DEAL_CONDITION_WEIGHT", "0.15")),
            seismic_weight=float(os.getenv("DEAL_SEISMIC_WEIGHT", "0.25")),
            min_price_eur=int(os.getenv("DEAL_MIN_PRICE_EUR", "10000")),
        ),
        notifier=NotifierConfig(
            smtp_host=os.getenv("SMTP_HOST", "smtp.zoho.eu"),
            smtp_port=int(os.getenv("SMTP_PORT", "465")),
            smtp_user=os.getenv("EMAIL_USER", ""),
            smtp_password=os.getenv("EMAIL_PASSWORD", ""),
            recipient=os.getenv("DIGEST_RECIPIENT_EMAIL", "radu@orghidan.ro"),
        ),
        database_path=Path(os.getenv("DATABASE_PATH", "data/listings.db")),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
    )
