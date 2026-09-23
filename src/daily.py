"""Daily run entrypoint: ingest fresh alert emails, then process the pipeline.

One-shot companion to the always-on listener (Stage 9 'run on schedule').
Safe to invoke from cron/systemd every day:

    1. poll the inbox once for unread alert emails and store new listings
    2. run the LangGraph batch over every listing still in status='new'
    3. the batch already dispatches the aggregated email digest on completion

Exit code is the number of listings processed by the pipeline (0 when idle)
so a scheduler can detect failures from the logs.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from src.config import load_config
from src.email_listener.db import Database
from src.email_listener.listener import EmailListener
from src.logging_config import setup_logging
from src.pipeline import run_pipeline

logger = logging.getLogger(__name__)


async def run_daily(ingest: bool = True) -> int:
    config = load_config()

    ingested = 0
    if ingest:
        db = Database(config.database_path)
        await db.connect()
        listener = EmailListener(config.email, db)
        try:
            ingested = await listener.process_once()
        finally:
            listener.disconnect()
            await db.close()
        logger.info("Ingest pass done: %d new listing(s) discovered", ingested)

    processed = await run_pipeline()
    logger.info("Daily run complete: %d ingested, %d processed", ingested, processed)
    return processed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Daily run: ingest alert emails then process the deal pipeline"
    )
    parser.add_argument(
        "--no-ingest",
        action="store_true",
        help="Skip the inbox poll; only process listings already in status='new'",
    )
    args = parser.parse_args()

    setup_logging()
    exit_code = asyncio.run(run_daily(ingest=not args.no_ingest))
    raise SystemExit(0 if exit_code >= 0 else 1)


if __name__ == "__main__":
    main()