"""Stage 3b: zone-verification against listing prose tests."""

from __future__ import annotations

from src.geocoding.verify import verify_zone_mentions, zones_in_text
from src.models.listing import Listing


def make_listing(
    *,
    title: str = "",
    neighborhood: str = "",
    address: str = "",
    description: str = "",
    email_subject: str = "",
) -> Listing:
    return Listing(
        id="v1",
        url="https://example.test/",
        title=title,
        neighborhood=neighborhood,
        address=address,
        description=description,
        email_subject=email_subject,
    )


class TestZonesInText:
    def test_plain_sector(self) -> None:
        assert zones_in_text("apartament Sector 2 central") == ["Sector 2"]

    def test_inflected_sectorul(self) -> None:
        assert zones_in_text("situat in sectorul 5, la Piata Sudului") == ["Sector 5"]

    def test_multiple_zones_in_order(self) -> None:
        assert zones_in_text("sectorul 1 apoi sectorul 6") == ["Sector 1", "Sector 6"]

    def test_bare_digits_not_matched(self) -> None:
        assert zones_in_text("etaj 2, 3 camere, 55 mp") == []

    def test_city_name_is_not_actionable(self) -> None:
        assert zones_in_text("Bucuresti, sector 4") == ["Sector 4"]
        assert zones_in_text("bucuresti, cartierul dorobanti") == []

    def test_unknown_zone_filtered(self) -> None:
        text = "sectorul 5 si sectorul 4"
        assert zones_in_text(text, known_zones={"Sector 5"}) == ["Sector 5"]

    def test_empty_text(self) -> None:
        assert zones_in_text("") == []
        assert zones_in_text(None) == []


class TestVerifyZoneMentions:
    def test_discrepancy_body_overrides_field(self) -> None:
        listing = make_listing(
            title="Apartament 2 camere - Bucuresti, Sector 1",
            description="Apartament de vanzare, Bucuresti, Sector 1",
            email_subject="Apartamente Sector 1",
        )
        check = verify_zone_mentions(listing, body_text="apartamentul este in sectorul 5")
        assert check.discrepancy
        assert check.field_zones == ("Sector 1",)
        assert check.described_zones == ("Sector 5",)
        assert check.corrected_zone == "Sector 5"

    def test_consistent_mentions_no_correction(self) -> None:
        listing = make_listing(
            title="Apartament - Sector 3",
            description="Apartament de vanzare, Sector 3",
        )
        check = verify_zone_mentions(listing, body_text="in sectorul 3, aproape de metrou")
        assert not check.discrepancy
        assert check.corrected_zone is None

    def test_body_missing_uses_description_as_prose(self) -> None:
        listing = make_listing(
            title="Apartament - Sector 1",
            description="Apartament situat in sectorul 4, langa metrou.",
        )
        check = verify_zone_mentions(listing)
        assert check.field_zones == ("Sector 1",)
        assert check.described_zones == ("Sector 4",)
        assert check.discrepancy
        assert check.corrected_zone == "Sector 4"

    def test_no_field_zone_takes_description_zone(self) -> None:
        listing = make_listing(description="apartament in sectorul 4")
        check = verify_zone_mentions(listing)
        assert not check.discrepancy
        assert check.described_zones == ("Sector 4",)
        assert check.corrected_zone == "Sector 4"

    def test_neighborhood_discrepancy_can_be_corrected(self) -> None:
        listing = make_listing(title="Apartament - Primăverii")
        check = verify_zone_mentions(
            listing,
            body_text="Proprietatea este in cartierul Giulești",
            known_zones={"Primăverii", "Giulești"},
            include_neighborhoods=True,
        )
        assert check.discrepancy
        assert check.corrected_zone == "Giulești"

    def test_neighborhood_and_its_sector_are_compatible(self) -> None:
        listing = make_listing(title="Apartament - Sector 1")
        check = verify_zone_mentions(
            listing,
            body_text="Proprietatea este in cartierul Primăverii",
            known_zones={"Sector 1", "Primăverii"},
            include_neighborhoods=True,
        )
        assert not check.discrepancy
        assert check.corrected_zone is None

    def test_no_prose_no_correction(self) -> None:
        listing = make_listing(title="Apartament - Sector 2")
        check = verify_zone_mentions(listing)
        assert check.field_zones == ("Sector 2",)
        assert check.described_zones == ()
        assert check.corrected_zone is None

    def test_known_zones_restricts_correction(self) -> None:
        listing = make_listing(
            title="Apartament - Sector 1",
            description="in sectorul 5",
        )
        check = verify_zone_mentions(listing, known_zones={"Sector 1"})
        assert check.described_zones == ()
        assert check.corrected_zone is None

    def test_description_mirrors_field_but_body_contradicts(self) -> None:
        listing = make_listing(
            title="Apartament - Bucuresti, Sector 1",
            description="Apartament de vanzare, Bucuresti, Sector 1, la 90.000 Euro",
        )
        check = verify_zone_mentions(
            listing, body_text="apartamentul se afla la marginea orasului, sectorul 6"
        )
        assert check.discrepancy
        assert check.corrected_zone == "Sector 6"

    def test_chrome_mirroring_field_is_ignored(self) -> None:
        # Breadcrumbs/h1 repeat the clickbait zone; the prose names the real one.
        listing = make_listing(
            title="Apartament - Bucuresti, Sector 3",
            description="Apartament de vanzare, 55 mp, Bucuresti, Sector 3",
        )
        body = "Apartament - Sector 3 ... Bucuresti > Sector 3 > Straduintei " \
            "apartamentul se afla in sectorul 5, la doua minute de Piata Sudului"
        check = verify_zone_mentions(listing, body_text=body)
        assert check.discrepancy
        assert check.field_zones == ("Sector 3",)
        assert check.corrected_zone == "Sector 5"

    def test_prose_agreeing_only_with_field_no_correction(self) -> None:
        listing = make_listing(
            title="Apartament - Sector 1",
            description="in sectorul 1",
        )
        check = verify_zone_mentions(listing, body_text="aproape de Piata Victoriei, sectorul 1")
        assert not check.discrepancy
        assert check.corrected_zone is None