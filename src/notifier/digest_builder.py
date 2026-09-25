# ruff: noqa: E501 -- inline HTML/CSS markup is exempt from line-length
"""Stage 7: HTML digest generator — responsive email cards for deal batches.

Pure presentation: takes typed pipeline results and renders one
mobile-friendly HTML email. No I/O. Kept out of `mailer.py` so the markup
can be unit-tested without hitting SMTP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape

from src.deal_calculator.valuator import DealScore
from src.geocoding.zones import ZoneMatch
from src.models.listing import Listing, VisionAnalysis
from src.vision_evaluator.natural_light import (
    is_natural_light_excluded,
    natural_light_label,
)

_PLACEHOLDER_IMAGE = "https://via.placeholder.com/300x200?text=No+Photo"

_DEAL_GOOD_THRESHOLD = 70.0  # DealScore is 0..100; >= 70 renders a green badge

# Badge / accent colors used across the card markup.
_BADGE_GOOD = "#16a34a"
_BADGE_MODERATE = "#ca8a04"
_BADGE_RISK = "#b91c1c"
_LINK_BLUE = "#2563eb"


@dataclass(frozen=True)
class DigestDeal:
    """Everything digest_builder needs about one qualifying listing."""

    listing: Listing
    deal: DealScore
    zone: ZoneMatch | None = None
    vision: VisionAnalysis | None = None

    @property
    def zone_label(self) -> str:
        if self.zone and self.zone.zone:
            return self.zone.zone
        return self.listing.neighborhood or "Unknown Zone"

    @property
    def condition_label(self) -> str:
        tier = self.deal.condition_tier or "N/A"
        return tier.replace("_", " ").title()

    @property
    def flaws(self) -> list[str]:
        return list(self.vision.deal_breakers) if self.vision else []

    @property
    def zone_avg_price_sqm(self) -> float:
        if self.zone and self.zone.avg_price_sqm:
            return self.zone.avg_price_sqm
        return self.deal.market_average_per_sqm

    @property
    def seismic_label(self) -> str:
        risk = self.deal.seismic_risk
        return f"{risk}/5" if risk else "n/a"

    @property
    def seismic_color(self) -> str:
        risk = self.deal.seismic_risk
        if risk is None:
            return "#6b7280"
        if risk <= 2:
            return _BADGE_GOOD
        if risk == 3:
            return _BADGE_MODERATE
        return _BADGE_RISK

    @property
    def natural_light_score(self) -> int | None:
        score = self.deal.natural_light_score
        if score is None and self.vision is not None:
            score = self.vision.natural_light_score
        return score

    @property
    def natural_light_display(self) -> str:
        score = self.natural_light_score
        label = natural_light_label(score)
        return f"{score}/5 ({label})" if score is not None else label

    @property
    def natural_light_color(self) -> str:
        score = self.natural_light_score
        if score is None:
            return "#6b7280"
        if score <= 2:
            return _BADGE_GOOD
        if score == 3:
            return _BADGE_MODERATE
        return _BADGE_RISK

    @property
    def natural_light_excluded(self) -> bool:
        return self.deal.natural_light_excluded or is_natural_light_excluded(
            self.natural_light_score
        )

    @property
    def natural_light_notes(self) -> str:
        if self.vision and self.vision.natural_light_notes:
            return self.vision.natural_light_notes
        return "No daylight notes returned."

    @property
    def vision_reasoning(self) -> str:
        if self.vision and self.vision.reasoning:
            return self.vision.reasoning
        return "No general vision notes returned."

    @property
    def image_url(self) -> str:
        return (self.listing.image_urls or [_PLACEHOLDER_IMAGE])[0]


def is_digest_eligible(deal: DigestDeal) -> bool:
    return deal.deal.is_deal and not deal.natural_light_excluded


def _price_sqm(price_eur: int | None, sqm: float | None) -> float:
    price = price_eur or 0
    area = sqm or 1
    return price / area


def _card_html(idx: int, deal: DigestDeal) -> str:
    price_eur = deal.listing.price_eur or 0
    sqm = deal.listing.sqm or 0
    price_sqm = int(_price_sqm(deal.listing.price_eur, deal.listing.sqm))
    renovation = deal.deal.total_renovation_cost
    adjusted_total = price_eur + renovation
    adjusted_sqm = deal.deal.adjusted_price_per_sqm or 0
    zone_avg = deal.zone_avg_price_sqm
    discount = deal.deal.discount_percentage
    score = deal.deal.deal_score
    badge_color = _BADGE_GOOD if score >= _DEAL_GOOD_THRESHOLD else _BADGE_MODERATE
    flaws = escape(", ".join(deal.flaws) if deal.flaws else "None observed")
    light_notes = escape(deal.natural_light_notes)
    vision_notes = escape(deal.vision_reasoning)

    return f"""
        <div style="background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 24px; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
            <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
                <tr>
                    <td width="35%" style="vertical-align: top; background: #f3f4f6;">
                        <img src="{deal.image_url}" alt="Listing photo" style="width: 100%; height: 210px; object-fit: cover; display: block;" />
                    </td>
                    <td width="65%" style="padding: 16px 20px; vertical-align: top;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <span style="font-size: 18px; font-weight: 700; color: #111827;">#{idx}. {deal.zone_label}</span>
                            <span style="background: {badge_color}; color: #ffffff; padding: 3px 8px; border-radius: 4px; font-size: 13px; font-weight: 600;">Score: {score:.0f}</span>
                        </div>
                        <div style="font-size: 15px; color: #374151; margin-bottom: 12px;">
                            <strong>€{price_eur:,.0f}</strong> ({sqm:.0f} m² &bull; €{price_sqm:,.0f}/m²)
                        </div>
                        <table style="font-size: 13px; color: #4b5563; line-height: 1.6; margin-bottom: 14px;">
                            <tr>
                                <td style="padding-right: 12px;"><strong>Condition:</strong></td>
                                <td>{deal.condition_label}</td>
                            </tr>
                            <tr>
                                <td style="padding-right: 12px;"><strong>Seismic Risk:</strong></td>
                                <td><strong style="color: {deal.seismic_color};">{deal.seismic_label}</strong></td>
                            </tr>
                            <tr>
                                <td style="padding-right: 12px;"><strong>Natural Light:</strong></td>
                                <td><strong style="color: {deal.natural_light_color};">{deal.natural_light_display}</strong></td>
                            </tr>
                            <tr>
                                <td style="padding-right: 12px;"><strong>Daylight Notes:</strong></td>
                                <td>{light_notes}</td>
                            </tr>
                            <tr>
                                <td style="padding-right: 12px;"><strong>Vision Notes:</strong></td>
                                <td>{vision_notes}</td>
                            </tr>
                            <tr>
                                <td style="padding-right: 12px;"><strong>Est. Renovation:</strong></td>
                                <td>€{renovation:,.0f} (Total: €{adjusted_total:,.0f} &bull; €{adjusted_sqm:,.0f}/m²)</td>
                            </tr>
                            <tr>
                                <td style="padding-right: 12px;"><strong>Zone Avg / Upside:</strong></td>
                                <td>€{zone_avg:,.0f}/m² &bull; <strong style="color: {_BADGE_GOOD};">{discount:.1f}% below avg</strong></td>
                            </tr>
                            <tr>
                                <td style="padding-right: 12px;"><strong>Issues:</strong></td>
                                <td style="color: #991b1b;">{flaws}</td>
                            </tr>
                        </table>
                        <a href="{deal.listing.url}" target="_blank" style="display: inline-block; background: {_LINK_BLUE}; color: #ffffff; text-decoration: none; padding: 7px 14px; border-radius: 5px; font-size: 13px; font-weight: 600;">View Listing &rarr;</a>
                    </td>
                </tr>
            </table>
        </div>
        """


def build_digest_html(deals: list[DigestDeal], total_scanned: int) -> str:
    """Generates a clean, mobile-friendly HTML digest email."""
    eligible_deals = [deal for deal in deals if is_digest_eligible(deal)]
    now_str = datetime.now().strftime("%d %b %Y, %H:%M")
    cards_html = "".join(
        _card_html(idx, deal) for idx, deal in enumerate(eligible_deals, 1)
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="background-color: #f9fafb; margin: 0; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
        <div style="max-width: 680px; margin: 0 auto;">
            <div style="margin-bottom: 20px;">
                <h2 style="margin: 0 0 6px 0; color: #111827; font-size: 22px;">🏠 Real Estate Deal Digest</h2>
                <p style="margin: 0; color: #6b7280; font-size: 14px;">Generated on {now_str} &bull; {total_scanned} listings scanned &bull; <strong>{len(eligible_deals)} qualifying deals</strong></p>
            </div>
            {cards_html}
            <p style="text-align: center; color: #9ca3af; font-size: 12px; margin-top: 32px;">Automated Real Estate Ingestion Pipeline &bull; Local Gemma4 Vision</p>
        </div>
    </body>
    </html>
    """


__all__ = ["DigestDeal", "build_digest_html", "is_digest_eligible"]
