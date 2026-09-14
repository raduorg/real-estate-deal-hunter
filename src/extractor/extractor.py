from __future__ import annotations

import logging

from src.config import Config
from src.email_listener.db import Database
from src.extractor.fetcher import PageFetcher
from src.extractor.parsers import extract_from_html
from src.models.extraction import ListingPage, PageExtraction
from src.models.listing import Listing, ListingStatus

logger = logging.getLogger(__name__)


class Extractor:
    """Stage 2: fetch listing pages and enrich rows with structured metadata."""

    def __init__(self, fetcher: PageFetcher, db: Database, max_images: int = 15) -> None:
        self.fetcher = fetcher
        self.db = db
        self.max_images = max_images

    @classmethod
    def from_config(cls, config: Config) -> Extractor:
        db = Database(config.database_path)
        fetcher = PageFetcher(config.extractor)
        return cls(fetcher, db, max_images=config.extractor.max_images)

    async def process_new(self, limit: int | None = None) -> int:
        """Fetch and enrich every listing still in status='new'."""
        await self.db.connect()
        try:
            listings = await self.db.get_listings_by_status(ListingStatus.NEW)
            if limit is not None:
                listings = listings[:limit]
            if not listings:
                logger.info("No new listings to extract")
                return 0

            extracted = 0
            for listing in listings:
                try:
                    result = await self.extract(listing)
                    if result is not None:
                        extracted += 1
                except Exception:
                    logger.exception(
                        "Extraction failed for listing %s (%s)", listing.id, listing.url
                    )
            logger.info(
                "Extraction pass finished: %d/%d listings enriched",
                extracted,
                len(listings),
            )
            return extracted
        finally:
            await self.fetcher.close()
            await self.db.close()

    async def extract(self, listing: Listing) -> PageExtraction | None:
        result = await self.fetcher.fetch(listing.url)

        page = ListingPage(
            listing_id=listing.id,
            fetched_url=result.url,
            http_status=result.status,
            bot_blocked=result.bot_blocked,
            html=result.html,
        )
        await self.db.save_page(page)

        if result.bot_blocked or not result.success:
            logger.warning(
                "Skipping %s: %s (HTTP %d)",
                listing.id,
                result.bot_blocked and "bot challenge" or result.error,
                result.status,
            )
            await self.db.update_listing_status(listing.id, ListingStatus.SKIPPED)
            return None

        extraction = extract_from_html(
            result.html,
            listing_id=listing.id,
            url=listing.url,
            source=listing.source,
            max_images=self.max_images,
        )
        await self.db.apply_extraction(listing.id, extraction, ListingStatus.EXTRACTED)
        return extraction
