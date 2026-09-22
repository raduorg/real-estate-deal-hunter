import asyncio
import logging

from src.config import load_config
from src.email_listener.db import Database
from src.email_listener.listener import EmailListener
from src.logging_config import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    config = load_config()
    db = Database(config.database_path)
    await db.connect()

    listener = EmailListener(config.email, db)
    try:
        await listener.run_forever()
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
