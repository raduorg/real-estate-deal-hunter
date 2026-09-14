from __future__ import annotations

import json
import logging
from pathlib import Path

import aiosqlite

from src.models.extraction import ListingPage, PageExtraction
from src.models.listing import Listing, ListingStatus

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'unknown',
    title TEXT DEFAULT '',
    description TEXT DEFAULT '',
    price_eur INTEGER,
    sqm REAL,
    rooms INTEGER,
    city TEXT DEFAULT '',
    neighborhood TEXT DEFAULT '',
    address TEXT DEFAULT '',
    latitude REAL,
    longitude REAL,
    image_urls TEXT DEFAULT '[]',
    status TEXT DEFAULT 'new',
    discovered_at TEXT NOT NULL,
    email_subject TEXT DEFAULT '',
    email_date TEXT
);

CREATE TABLE IF NOT EXISTS listing_pages (
    listing_id TEXT PRIMARY KEY REFERENCES listings(id),
    fetched_url TEXT NOT NULL,
    http_status INTEGER NOT NULL DEFAULT 0,
    bot_blocked INTEGER NOT NULL DEFAULT 0,
    html TEXT NOT NULL DEFAULT '',
    extraction TEXT NOT NULL DEFAULT '{}',
    fetched_at TEXT NOT NULL,
    extracted_at TEXT
);

CREATE TABLE IF NOT EXISTS processed_emails (
    message_id TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status);
CREATE INDEX IF NOT EXISTS idx_listings_source ON listings(source);
"""

# Columns added in later stages; applied to older DBs via PRAGMA check + ALTER TABLE.
_LISTING_COLUMNS = {
    "description": "TEXT DEFAULT ''",
    "latitude": "REAL",
    "longitude": "REAL",
}


class Database:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._migrate_columns()
        await self._db.commit()
        logger.info("Connected to database: %s", self.db_path)

    async def _migrate_columns(self) -> None:
        if not self._db:
            return
        existing = {
            row[1]
            for row in await (await self._db.execute("PRAGMA table_info(listings)")).fetchall()
        }
        for column, ddl in _LISTING_COLUMNS.items():
            if column not in existing:
                await self._db.execute(f"ALTER TABLE listings ADD COLUMN {column} {ddl}")
                logger.info("Added column listings.%s", column)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def is_email_processed(self, message_id: str) -> bool:
        async with self._db.execute(
            "SELECT 1 FROM processed_emails WHERE message_id = ?", (message_id,)
        ) as cur:
            return await cur.fetchone() is not None

    async def mark_email_processed(self, message_id: str) -> None:
        from datetime import datetime, timezone

        await self._db.execute(
            "INSERT OR IGNORE INTO processed_emails (message_id, processed_at) VALUES (?, ?)",
            (message_id, datetime.now(timezone.utc).isoformat()),
        )
        await self._db.commit()

    async def listing_exists(self, listing_id: str) -> bool:
        async with self._db.execute("SELECT 1 FROM listings WHERE id = ?", (listing_id,)) as cur:
            return await cur.fetchone() is not None

    async def save_listing(self, listing: Listing) -> bool:
        if await self.listing_exists(listing.id):
            logger.debug("Listing already exists, skipping: %s", listing.id)
            return False

        await self._db.execute(
            """INSERT INTO listings
               (id, url, source, title, description, price_eur, sqm, rooms, city,
                neighborhood, address, latitude, longitude, image_urls, status,
                discovered_at, email_subject, email_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                listing.id,
                listing.url,
                listing.source.value,
                listing.title,
                listing.description,
                listing.price_eur,
                listing.sqm,
                listing.rooms,
                listing.city,
                listing.neighborhood,
                listing.address,
                listing.latitude,
                listing.longitude,
                json.dumps(listing.image_urls),
                listing.status.value,
                listing.discovered_at.isoformat(),
                listing.email_subject,
                listing.email_date.isoformat() if listing.email_date else None,
            ),
        )
        await self._db.commit()
        logger.info("Saved listing: %s [%s]", listing.title or listing.id, listing.source.value)
        return True

    async def get_listings_by_status(self, status: ListingStatus) -> list[Listing]:
        async with self._db.execute(
            "SELECT * FROM listings WHERE status = ?", (status.value,)
        ) as cur:
            rows = await cur.fetchall()
            return [self._row_to_listing(row) for row in rows]

    async def update_listing_status(self, listing_id: str, status: ListingStatus) -> None:
        await self._db.execute(
            "UPDATE listings SET status = ? WHERE id = ?", (status.value, listing_id)
        )
        await self._db.commit()

    async def save_page(self, page: ListingPage) -> None:
        await self._db.execute(
            """INSERT OR REPLACE INTO listing_pages
               (listing_id, fetched_url, http_status, bot_blocked, html, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                page.listing_id,
                page.fetched_url,
                page.http_status,
                int(page.bot_blocked),
                page.html,
                page.fetched_at.isoformat(),
            ),
        )
        await self._db.commit()

    async def get_page(self, listing_id: str) -> ListingPage | None:
        async with self._db.execute(
            "SELECT * FROM listing_pages WHERE listing_id = ?", (listing_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return ListingPage(
            listing_id=row["listing_id"],
            fetched_url=row["fetched_url"],
            http_status=row["http_status"],
            bot_blocked=bool(row["bot_blocked"]),
            html=row["html"],
            fetched_at=row["fetched_at"],
        )

    async def apply_extraction(
        self, listing_id: str, extraction: PageExtraction, new_status: ListingStatus
    ) -> None:
        from datetime import datetime, timezone

        await self._db.execute(
            """UPDATE listings SET title = ?, description = ?, price_eur = ?, sqm = ?,
               rooms = ?, city = ?, neighborhood = ?, address = ?,
               latitude = ?, longitude = ?, image_urls = ?, status = ?
               WHERE id = ?""",
            (
                extraction.title,
                extraction.description,
                extraction.price_eur,
                extraction.sqm,
                extraction.rooms,
                extraction.city,
                extraction.neighborhood,
                extraction.address,
                extraction.latitude,
                extraction.longitude,
                json.dumps(extraction.image_urls),
                new_status.value,
                listing_id,
            ),
        )
        await self._db.execute(
            "UPDATE listing_pages SET extraction = ?, extracted_at = ? WHERE listing_id = ?",
            (
                json.dumps(extraction.model_dump(mode="json")),
                datetime.now(timezone.utc).isoformat(),
                listing_id,
            ),
        )
        await self._db.commit()
        logger.info(
            "Applied extraction for %s (price=%s, sqm=%s, images=%d, confidence=%.2f)",
            listing_id,
            extraction.price_eur,
            extraction.sqm,
            len(extraction.image_urls),
            extraction.confidence,
        )

    def _row_to_listing(self, row: aiosqlite.Row) -> Listing:
        return Listing(
            id=row["id"],
            url=row["url"],
            source=row["source"],
            title=row["title"],
            description=row["description"],
            price_eur=row["price_eur"],
            sqm=row["sqm"],
            rooms=row["rooms"],
            city=row["city"],
            neighborhood=row["neighborhood"],
            address=row["address"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            image_urls=json.loads(row["image_urls"]),
            status=row["status"],
            discovered_at=row["discovered_at"],
            email_subject=row["email_subject"],
            email_date=row["email_date"],
        )
