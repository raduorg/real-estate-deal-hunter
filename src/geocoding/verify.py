"""Stage 3b: verify the zone stated in the location fields against the
listing's own prose.

Agents occasionally list a premium zone in the location field (title /
neighbourhood / address / email subject) while the real, worse zone is named
inside the description. Page bodies also contain portal chrome (breadcrumbs,
h1) that mirrors the chosen location field, so a name present in the prose but
absent from the location fields is treated as the honest signal and wins —
the property is then priced against that zone instead of the clickbait one.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.geocoding.zones import (
    Neighborhood,
    neighborhood_candidates_in_text,
    sectors_in_text,
)
from src.models.listing import Listing

# City-wide default; every listing names it, so it carries no signal.
_NON_ACTIONABLE_ZONES = {"Bucuresti"}


def zones_in_text(
    text: str | None,
    known_zones: set[str] | None = None,
    *,
    include_neighborhoods: bool = False,
) -> list[str]:
    """Canonical zones explicitly named in free text, in order of appearance."""
    if not text:
        return []
    sector_zones = [
        zone
        for zone in sectors_in_text(text, known_zones)
        if zone not in _NON_ACTIONABLE_ZONES
    ]
    if not include_neighborhoods:
        return sector_zones

    neighborhood_zones = [
        neighborhood.value
        for neighborhood in neighborhood_candidates_in_text(text, known_zones)
    ]
    return list(dict.fromkeys([*neighborhood_zones, *sector_zones]))


@dataclass(frozen=True)
class ZoneVerification:
    """Outcome of comparing the clickbait-prone fields against the prose."""

    field_zones: tuple[str, ...] = ()
    described_zones: tuple[str, ...] = ()
    corrected_zone: str | None = None
    discrepancy: bool = False


def _zones_compatible(left: str, right: str) -> bool:
    if left == right:
        return True
    left_neighborhood = Neighborhood.parse(left)
    right_neighborhood = Neighborhood.parse(right)
    if left_neighborhood is not None and right_neighborhood is not None:
        return left_neighborhood.sector == right_neighborhood.sector
    if left_neighborhood is not None:
        return left_neighborhood.sector is not None and left_neighborhood.sector.value == right
    if right_neighborhood is not None:
        return right_neighborhood.sector is not None and left == right_neighborhood.sector.value
    return False


def verify_zone_mentions(
    listing: Listing,
    *,
    body_text: str = "",
    known_zones: set[str] | None = None,
    include_neighborhoods: bool = False,
) -> ZoneVerification:
    """Detect a location-field vs description zone mismatch.

    The `description` field is usually portal metadata mirroring the selected
    location, so once a page body exists it is counted as part of the location
    field. The described zones are those the page prose names that are not
    already claimed by the location fields — the honest signal when the two
    disagree, and a fallback source when the location fields are silent.
    """
    fields = [listing.title, listing.neighborhood, listing.address, listing.email_subject]
    if body_text.strip():
        fields.append(listing.description)
        described_parts = [body_text]
    else:
        described_parts = [listing.description] if listing.description.strip() else []

    field_zones = zones_in_text(
        " ".join(p for p in fields if p),
        known_zones,
        include_neighborhoods=include_neighborhoods,
    )
    described_zones = zones_in_text(
        " ".join(described_parts),
        known_zones,
        include_neighborhoods=include_neighborhoods,
    )

    if include_neighborhoods:
        extra = [
            zone
            for zone in described_zones
            if not any(_zones_compatible(zone, field_zone) for field_zone in field_zones)
        ]
    else:
        extra = [z for z in described_zones if z not in field_zones]
    if not extra:
        return ZoneVerification(tuple(field_zones), tuple(described_zones))
    return ZoneVerification(
        field_zones=tuple(field_zones),
        described_zones=tuple(described_zones),
        corrected_zone=extra[0],
        discrepancy=bool(field_zones),
    )


__all__ = ["ZoneVerification", "verify_zone_mentions", "zones_in_text"]