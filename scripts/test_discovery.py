#!/usr/bin/env python3
"""One-shot end-to-end test: fetch real email alerts → extract listings → save to DB."""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config
from src.email_listener.db import Database
from src.email_listener.listener import EmailListener
from src.extractor.extractor import Extractor
from src.logging_config import setup_logging

logger = logging.getLogger(__name__)


async def run_email_discovery(config, db: Database) -> int:
    """Connect to IMAP, parse all unread emails, save listings to DB."""
    listener = EmailListener(config.email, db)
    listener.connect()

    try:
        count = await listener.process_once()
        return count
    finally:
        listener.disconnect()


async def run_extraction(config, db: Database, limit: int = 5) -> int:
    """Run the page extractor on newly discovered listings."""
    from src.extractor.fetcher import PageFetcher

    fetcher = PageFetcher(config.extractor)
    extractor = Extractor(fetcher, db, max_images=config.extractor.max_images)
    count = await extractor.process_new(limit=limit)
    return count


async def show_db_summary(db: Database) -> None:
    """Print a summary of what's in the database."""
    from src.models.listing import ListingStatus

    for status in ListingStatus:
        listings = await db.get_listings_by_status(status)
        if listings:
            print(f"\n{'='*60}")
            print(f"  Status: {status.value} ({len(listings)} listing(s))")
            print(f"{'='*60}")
            for i, listing in enumerate(listings, 1):
                print(f"\n  [{i}] {listing.title or '(no title)'}")
                print(f"      URL:     {listing.url}")
                print(f"      Source:  {listing.source.value}")
                print(f"      Price:   {listing.price_eur} EUR"
                      if listing.price_eur else "      Price:   -")
                print(f"      Sqm:     {listing.sqm}" if listing.sqm else "      Sqm:     -")
                print(f"      Rooms:   {listing.rooms}" if listing.rooms else "      Rooms:   -")
                print(f"      City:    {listing.city}" if listing.city else "      City:    -")
                print(f"      Images:  {len(listing.image_urls)}")
                if listing.email_subject:
                    print(f"      Subject: {listing.email_subject[:80]}")


async def main() -> None:
    setup_logging()
    config = load_config()

    db_path = Path("data/test_discovery.db")
    db = Database(db_path)
    await db.connect()

    try:
        # Phase 1: Email discovery
        print("\n--- Phase 1: Email Discovery ---")
        count = await run_email_discovery(config, db)
        print(f"Discovered {count} new listing(s) from email alerts")

        # Phase 2: Show what we found
        await show_db_summary(db)

# Phase 3: Extraction (fetch pages, parse metadata)
        if count > 0:
            print("\n--- Phase 2: Page Extraction ---")
            from src.models.listing import ListingStatus

            new_listings = await db.get_listings_by_status(ListingStatus.NEW)
            if new_listings:
                print(f"Will extract up to {min(len(new_listings), 3)} listing(s)...")
                extracted = await run_extraction(config, db, limit=3)
                print(f"Extracted metadata from {extracted} listing(s)")

                # process_new closed the DB; reconnect before showing summary
                await db.connect()
                await show_db_summary(db)
            else:
                print("No 'new' listings to extract")
        else:
            print("No new listings found — checking ALL listings in DB:")
            await show_db_summary(db)

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
