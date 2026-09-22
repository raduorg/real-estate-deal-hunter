from __future__ import annotations

import asyncio
import email
import email.header
import imaplib
import logging

from src.config import EmailConfig
from src.email_listener.db import Database
from src.email_listener.parsers import (
    build_listings,
    extract_listing_urls,
)
from src.email_listener.resolver import TrackingResolver

logger = logging.getLogger(__name__)


class EmailListener:
    def __init__(self, config: EmailConfig, db: Database) -> None:
        self.config = config
        self.db = db
        self._mail: imaplib.IMAP4_SSL | None = None

    def connect(self) -> None:
        logger.info(
            "Connecting to %s:%s as %s",
            self.config.imap_server,
            self.config.imap_port,
            self.config.user,
        )
        self._mail = imaplib.IMAP4_SSL(self.config.imap_server, self.config.imap_port)
        self._mail.login(self.config.user, self.config.password)
        self._mail.select("INBOX")
        logger.info("Connected and selected INBOX")

    def disconnect(self) -> None:
        if self._mail:
            try:
                self._mail.logout()
            except Exception:
                pass
            self._mail = None

    def _decode_header(self, raw: str | None) -> str:
        if not raw:
            return ""
        decoded_parts = email.header.decode_header(raw)
        parts = []
        for data, charset in decoded_parts:
            if isinstance(data, bytes):
                parts.append(data.decode(charset or "utf-8", errors="replace"))
            else:
                parts.append(data)
        return " ".join(parts)

    def _get_message_id(self, msg: email.message.Message) -> str:
        mid = msg.get("Message-ID", "")
        if mid:
            return mid.strip("<>")
        # fallback: use subject + date
        return f"{self._decode_header(msg.get('Subject', ''))}_{msg.get('Date', '')}"

    def _extract_body(self, msg: email.message.Message) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")
            # fallback to text/plain
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return ""

    def _search_unread(self) -> list[bytes]:
        _, data = self._mail.search(None, "UNSEEN")
        return data[0].split() if data[0] else []

    def _fetch_email(self, msg_id: bytes) -> email.message.Message | None:
        _, msg_data = self._mail.fetch(msg_id, "(RFC822)")
        if not msg_data or not msg_data[0]:
            return None
        raw = msg_data[0][1]
        return email.message_from_bytes(raw)

    def _mark_as_read(self, msg_id: bytes) -> None:
        self._mail.store(msg_id, "+FLAGS", "\\Seen")

    async def process_once(self) -> int:
        if not self._mail:
            self.connect()

        msg_ids = self._search_unread()
        if not msg_ids:
            logger.debug("No unread emails")
            return 0

        logger.info("Found %d unread email(s)", len(msg_ids))
        new_listings = 0
        resolver = TrackingResolver()

        try:
            for raw_id in msg_ids:
                msg = self._fetch_email(raw_id)
                if not msg:
                    continue

                message_id = self._get_message_id(msg)

                if await self.db.is_email_processed(message_id):
                    logger.debug("Already processed: %s", message_id[:40])
                    continue

                subject = self._decode_header(msg.get("Subject", ""))
                date_str = msg.get("Date", "")

                html_body = self._extract_body(msg)
                if not html_body:
                    logger.warning("No HTML body in email: %s", subject[:60])
                    await self.db.mark_email_processed(message_id)
                    continue

                candidate_urls = extract_listing_urls(html_body)
                listing_urls = await resolver.resolve_many(candidate_urls)

                from bs4 import BeautifulSoup

                listings = build_listings(
                    listing_urls,
                    BeautifulSoup(html_body, "lxml").get_text(separator=" "),
                    subject=subject,
                    email_date=date_str,
                )

                saved = 0
                for listing in listings:
                    if await self.db.save_listing(listing):
                        saved += 1

                new_listings += saved
                await self.db.mark_email_processed(message_id)
                logger.info(
                    "Processed email '%s' -> %d new listing(s)", subject[:60], saved
                )
        finally:
            await resolver.close()
        return new_listings

    async def run_forever(self) -> None:
        logger.info("Starting email listener (poll every %ds)", self.config.poll_interval)
        self.connect()
        try:
            while True:
                try:
                    count = await self.process_once()
                    if count:
                        logger.info("Discovered %d new listing(s)", count)
                except imaplib.IMAP4.abort:
                    logger.warning("IMAP connection lost, reconnecting...")
                    self.disconnect()
                    self.connect()
                except Exception:
                    logger.exception("Error during email poll")
                await asyncio.sleep(self.config.poll_interval)
        except KeyboardInterrupt:
            logger.info("Shutting down email listener")
        finally:
            self.disconnect()
