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
class Config:
    email: EmailConfig
    vision: VisionConfig
    target: TargetConfig
    extractor: ExtractorConfig = field(default_factory=ExtractorConfig)
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
        database_path=Path(os.getenv("DATABASE_PATH", "data/listings.db")),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
    )
