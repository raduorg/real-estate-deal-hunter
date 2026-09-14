import argparse
import asyncio
import json
import logging

from src.config import load_config
from src.extractor.fetcher import PageFetcher
from src.extractor.parsers import extract_from_html, source_from_url
from src.logging_config import setup_logging

logger = logging.getLogger(__name__)


async def run_batch(limit: int | None) -> None:
    from src.extractor.extractor import Extractor

    config = load_config()
    await Extractor.from_config(config).process_new(limit)


async def run_single(url: str) -> None:
    """Debug helper: fetch one URL and print the parsed extraction (no DB writes)."""
    config = load_config()
    fetcher = PageFetcher(config.extractor)
    try:
        result = await fetcher.fetch(url)
    finally:
        await fetcher.close()

    if result.bot_blocked or not result.success:
        reason = result.bot_blocked and "bot challenge" or result.error
        logger.error("Fetch failed: HTTP %d (%s)", result.status, reason)
        return

    extraction = extract_from_html(
        result.html,
        listing_id="debug",
        url=url,
        source=source_from_url(url),
        max_images=config.extractor.max_images,
    )
    print(json.dumps(extraction.model_dump(mode="json"), indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 2: listing page extraction & enrichment")
    parser.add_argument("--url", help="Fetch and parse a single listing page (no DB writes)")
    parser.add_argument(
        "--limit", type=int, default=None, help="Cap how many new listings to process"
    )
    args = parser.parse_args()

    setup_logging()
    if args.url:
        asyncio.run(run_single(args.url))
    else:
        asyncio.run(run_batch(args.limit))


if __name__ == "__main__":
    main()
