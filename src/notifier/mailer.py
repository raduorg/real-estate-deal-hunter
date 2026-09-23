"""Stage 7: SMTP dispatch of the deal digest via Zoho SMTP (SSL).

Pure stdlib `smtplib`, no new dependency. Called once at the end of a batch:
aggregates all qualifying deals into a single email and sends it to the
configured personal address.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.config import NotifierConfig
from src.notifier.digest_builder import DigestDeal, build_digest_html

logger = logging.getLogger(__name__)


def send_digest_email(
    deals: list[DigestDeal],
    total_scanned: int,
    cfg: NotifierConfig,
) -> bool:
    """Sends the compiled HTML digest via Zoho SMTP.

    Graceful no-ops: an empty batch or missing credentials return False with a
    log line instead of raising, so a notifier misconfiguration never fails the
    whole pipeline pass.
    """
    if not deals:
        logger.info("No qualifying deals in this batch; email skipped")
        return False

    if not all([cfg.smtp_user, cfg.smtp_password, cfg.recipient]):
        logger.error("Missing SMTP or recipient credentials in config")
        return False

    sorted_deals = sorted(deals, key=lambda d: d.deal.deal_score, reverse=True)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"🎯 {len(sorted_deals)} New Property Deals Found ({datetime.now().strftime('%d %b')})"
    )
    msg["From"] = cfg.smtp_user
    msg["To"] = cfg.recipient
    msg.attach(MIMEText(build_digest_html(sorted_deals, total_scanned), "html"))

    try:
        with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=20) as server:
            server.login(cfg.smtp_user, cfg.smtp_password)
            server.sendmail(cfg.smtp_user, [cfg.recipient], msg.as_string())
    except Exception:
        logger.exception("Failed to dispatch digest to %s", cfg.recipient)
        return False

    logger.info("Successfully dispatched digest (%d deals) to %s", len(sorted_deals), cfg.recipient)
    return True


__all__ = ["send_digest_email"]