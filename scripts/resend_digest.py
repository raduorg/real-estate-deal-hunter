#!/usr/bin/env python3
"""Resend the deal digest for the current is_deal=1 batch.

After a filter change demotes listings, the stored pipeline results still hold
the full deal/zone/vision detail — this script rebuilds DigestDeal objects from
the DB and re-dispatches the HTML email, reflecting only surviving deals.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config
from src.email_listener.db import Database
from src.geocoding.zones import ZoneMatch
from src.logging_config import setup_logging
from src.models.listing import DealScore, Listing
from src.notifier.digest_builder import DigestDeal, is_digest_eligible
from src.notifier.mailer import send_digest_email

TOTAL_SCANNED_SOURCE_RUN = 172


async def main() -> None:
    setup_logging()
    config = load_config()
    db = Database(config.database_path)
    await db.connect()
    try:
        deals: list[DigestDeal] = []
        for listing in await db.get_deal_listings():
            item = await digest_deal(db, listing)
            if item:
                deals.append(item)

        if not deals:
            print("No qualifying deals in DB; nothing to send")
            return

        sent = await asyncio.to_thread(
            send_digest_email,
            deals,
            TOTAL_SCANNED_SOURCE_RUN,
            config.notifier,
        )
        print(f"Sent digest with {len(deals)} deals: {sent}")
    finally:
        await db.close()


async def digest_deal(db: Database, listing: Listing) -> DigestDeal | None:
    result = await db.get_pipeline_result(listing.id)
    if not result or not result.get("deal"):
        return None
    deal = DealScore.model_validate(result["deal"])
    if not deal.is_deal:
        return None
    zone_raw = result.get("zone_match") or {}
    zone = ZoneMatch(
        zone=zone_raw.get("zone") or "",
        avg_price_sqm=zone_raw.get("avg_price_sqm"),
        matched=zone_raw.get("matched") or False,
        method=zone_raw.get("method") or "",
        sector=zone_raw.get("sector"),
        neighborhood=zone_raw.get("neighborhood"),
    )
    vision = await db.get_vision_analysis(listing.id)
    candidate = DigestDeal(listing=listing, deal=deal, zone=zone, vision=vision)
    return candidate if is_digest_eligible(candidate) else None


if __name__ == "__main__":
    asyncio.run(main())