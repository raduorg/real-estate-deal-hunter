"""Stage 8: orchestration entry — drive fresh listings through the LangGraph.

Consumes every listing stuck in status='new', runs it through
extract -> verify_zone -> financial -> [vision -> value], and persists the
final deal verdict per listing. Run periodically (cron/systemd) after the
email listener has filled the inbox.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from src.config import load_config
from src.logging_config import setup_logging
from src.models.listing import ListingStatus
from src.notifier.digest_builder import DigestDeal
from src.notifier.mailer import send_digest_email
from src.orchestration.graph import PipelineBuilder

logger = logging.getLogger(__name__)


async def run_pipeline(limit: int | None = None) -> int:
    config = load_config()
    builder = PipelineBuilder.from_config(config)
    await builder.db.connect()
    try:
        fresh = await builder.db.get_listings_by_status(ListingStatus.NEW)
        total_scanned = len(fresh)
        if limit is not None:
            fresh = fresh[:limit]
        if not fresh:
            logger.info("No new listings to process")
            return 0

        graph = builder.build_graph()
        processed = 0
        qualifying_deals: list[DigestDeal] = []
        for listing in fresh:
            try:
                final_state = await graph.ainvoke({"listing": listing})
            except Exception:
                logger.exception("Pipeline failed for %s (%s)", listing.id, listing.url)
                continue
            deal = final_state.get("deal")
            verdict = final_state.get("financial")
            processed += 1
            logger.info(
                "Pipeline done for %s: verdict=%s deal=%s",
                listing.id,
                verdict.verdict.value if verdict else "?",
                bool(deal and deal.is_deal),
            )
            if deal and deal.is_deal:
                qualifying_deals.append(
                    DigestDeal(
                        listing=final_state.get("listing", listing),
                        deal=deal,
                        zone=final_state.get("zone_match"),
                        vision=final_state.get("vision"),
                    )
                )
        logger.info(
            "Pipeline pass finished: %d/%d listings processed",
            processed,
            len(fresh),
        )

        if qualifying_deals:
            sent = await asyncio.to_thread(
                send_digest_email,
                qualifying_deals,
                total_scanned,
                config.notifier,
            )
            if sent:
                for item in qualifying_deals:
                    await builder.db.update_listing_status(item.listing.id, ListingStatus.ALERTED)
                logger.info(
                    "Marked %d qualifying listings as alerted",
                    len(qualifying_deals),
                )
            else:
                logger.error(
                    "Digest dispatch failed; %d qualifying deals not alerted",
                    len(qualifying_deals),
                )
        elif total_scanned:
            logger.info("No qualifying deals in this batch; digest skipped")

        return processed
    finally:
        await builder.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage 8: orchestrate new listings through the deal pipeline"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Cap how many new listings to process"
    )
    args = parser.parse_args()

    setup_logging()
    asyncio.run(run_pipeline(args.limit))


if __name__ == "__main__":
    main()