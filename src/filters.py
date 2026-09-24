"""Deterministic deal pre-filters (applied before any zone/financial/vision spend).

Cheap, pure-math rules mirroring the seismic early-exit gate:
- asking price < 10k EUR = almost certainly a mislisted rental, always excluded.
  Monthly rents (3-4 plain digits like "850 €/luna") are not captured by the
  extractor's sale-price regex, so the filter falls back to the price embedded
  in the listing's own og-description.
- demisol / subsol level = dark, damp, hard to finance, always excluded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.models.listing import Listing

# Below this asking price a listing is a mislisted rental, not a sale.
MIN_SALE_PRICE_EUR = 10_000

# Lowest plausible rent used by the description fallback (~100 EUR/month).
_MIN_FALLBACK_PRICE = 100

# Price with mandatory currency, accepting plain small amounts the sale-parser
# rejects: "850 €", "850€/luna", "300 euro", "88 900 €", "88.900 €".
_PRICE_IN_TEXT_RE = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[ .,']\d{3})*|\d{4,6})\s*(?:eur|€|euro)(?!\w)",
    re.IGNORECASE,
)

# Ground/basement levels. Substring match (no \b) so inflected forms are caught
# too: subsolul, subsoluri, demisolului — all below-grade and always excluded.
_BASEMENT_RE = re.compile(r"demisol|subsol", re.IGNORECASE)


@dataclass(frozen=True)
class ListingFilterResult:
    rejected: bool = False
    reason: str = ""


def mentions_basement(*texts: str) -> bool:
    """True if any free-text source flags the apartment as a basement level."""
    return any(text and _BASEMENT_RE.search(text) for text in texts)


def _fallback_price(text: str) -> int | None:
    """First plausible currency-priced amount in a metadata string, or None."""
    if not text:
        return None
    for m in _PRICE_IN_TEXT_RE.finditer(text):
        amount = m.group(1).replace(" ", "").replace(".", "").replace(",", "").replace("'", "")
        try:
            value = int(amount)
        except ValueError:
            continue
        if _MIN_FALLBACK_PRICE <= value <= 5_000_000:
            return value
    return None


def effective_price(listing: Listing) -> int | None:
    """Best-known asking price: stored figure, else from og-description text."""
    if listing.price_eur is not None:
        return listing.price_eur
    return _fallback_price(listing.description) or _fallback_price(listing.email_subject)


def should_exclude(
    listing: Listing,
    *extra_texts: str,
    min_price_eur: int = MIN_SALE_PRICE_EUR,
) -> ListingFilterResult:
    """Return a rejection reason when a listing must be dropped, else pass."""
    price = effective_price(listing)
    if price is not None and price < min_price_eur:
        return ListingFilterResult(
            rejected=True,
            reason=(
                f"asking {price} EUR below {min_price_eur} EUR minimum "
                "(likely mislisted rental)"
            ),
        )
    if mentions_basement(
        listing.title,
        listing.description,
        listing.address,
        listing.email_subject,
        *extra_texts,
    ):
        return ListingFilterResult(rejected=True, reason="demisol/subsol level excluded")
    return ListingFilterResult()