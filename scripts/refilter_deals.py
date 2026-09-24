#!/usr/bin/env python3
"""Refilter already-flagged deals against the current pre-filter rules.

The deal criteria evolve faster than the pipeline reruns. This one-shot walks
every pipeline_results row with is_deal=1, re-applies the price floor and the
demisol/subsol level exclusion against the stored page text, and demotes any
listing that no longer qualifies (is_deal=0, status=skipped), recording why in
the result JSON. Safe to re-run: already-flagged deals are simply re-checked.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bs4 import BeautifulSoup

from src.config import load_config
from src.email_listener.db import Database
from src.filters import should_exclude
from src.logging_config import setup_logging
from src.models.listing import Listing, ListingStatus


async def page_text(db: Database, listing: Listing) -> str:
    page = await db.get_page(listing.id)
    if not page or not page.html:
        return ""
    try:
        return BeautifulSoup(page.html, "lxml").get_text(separator=" ", strip=True)
    except Exception:
        return ""


async def main() -> None:
    setup_logging()
    config = load_config()
    db = Database(config.database_path)
    await db.connect()
    try:
        deals = await db.get_deal_listings()
        removed: list[tuple[str, str]] = []
        kept: list[str] = []

        for listing in deals:
            body = await page_text(db, listing)
            verdict = should_exclude(
                listing,
                body,
                min_price_eur=config.deals.min_price_eur,
            )
            if verdict.rejected:
                await db.unflag_deal(listing.id, verdict.reason)
                await db.update_listing_status(listing.id, ListingStatus.SKIPPED)
                removed.append((listing.id, verdict.reason))
            else:
                kept.append(listing.id)

        print(f"\nDeals re-checked: {len(deals)}")
        print(f"  kept:    {len(kept)}")
        print(f"  removed: {len(removed)}")
        for listing_id, reason in removed:
            print(f"    - {listing_id}: {reason}")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())