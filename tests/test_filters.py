from src.filters import effective_price, mentions_basement, should_exclude
from src.models.listing import Listing, ListingSource


def make_listing(**overrides) -> Listing:
    defaults = dict(
        id="t1",
        url="https://www.storia.ro/ro/oferta/apartament-1",
        source=ListingSource.STORIA,
        price_eur=80_000,
        title="Apartament 2 camere, etaj 3",
        description="Apartament de vanzare, renovat, central",
    )
    defaults.update(overrides)
    return Listing(**defaults)


class TestPriceFloor:
    def test_below_floor_rejected(self) -> None:
        result = should_exclude(make_listing(price_eur=9_999))
        assert result.rejected
        assert "rental" in result.reason

    def test_at_floor_accepted(self) -> None:
        assert not should_exclude(make_listing(price_eur=10_000)).rejected

    def test_above_floor_accepted(self) -> None:
        assert not should_exclude(make_listing(price_eur=45_000)).rejected

    def test_unknown_price_passes_price_rule(self) -> None:
        result = should_exclude(make_listing(price_eur=None))
        assert not result.rejected

    def test_custom_floor(self) -> None:
        result = should_exclude(make_listing(price_eur=30_000), min_price_eur=50_000)
        assert result.rejected


class TestPriceFallbackFromDescription:
    """Rentals carry a per-month price the extractor never stores; the filter
    must derive it from the listing's own og-description text."""

    def test_monthly_rent_in_description_rejected(self) -> None:
        listing = make_listing(
            price_eur=None,
            title="Apartament 2 camere de inchiriat - Bucuresti, Sector 3",
            description="Vezi acest apartament de inchiriat in Bucuresti, la 850 €/luna.",
        )
        assert effective_price(listing) == 850
        result = should_exclude(listing)
        assert result.rejected
        assert "rental" in result.reason

    def test_bare_small_price_in_description_rejected(self) -> None:
        listing = make_listing(price_eur=None, description="Apartament la 300 euro")
        assert should_exclude(listing).rejected

    def test_sale_price_in_description_accepted(self) -> None:
        listing = make_listing(
            price_eur=None, description="Excelent apartament de vanzare la 88 900 €."
        )
        assert effective_price(listing) == 88900
        assert not should_exclude(listing).rejected

    def test_grouped_price_in_description(self) -> None:
        listing = make_listing(price_eur=None, description="Pret 98.500 Euro")
        assert effective_price(listing) == 98500

    def test_no_price_in_description(self) -> None:
        listing = make_listing(price_eur=None, description="Apartament spatios")
        assert effective_price(listing) is None
        assert not should_exclude(listing).rejected


class TestBasementLevel:
    def test_demisol_in_title_rejected(self) -> None:
        listing = make_listing(title="Apartament 2 camere, demisol, Sector 4")
        assert should_exclude(listing).rejected
        assert "demisol" in should_exclude(listing).reason

    def test_subsol_in_description_rejected(self) -> None:
        listing = make_listing(description="Apartament la subsol, 2 camere")
        assert should_exclude(listing).rejected

    def test_subsol_in_address_rejected(self) -> None:
        listing = make_listing(address="Str. X, apartamentul iese la subsolul blocului")
        assert should_exclude(listing).rejected

    def test_extra_text_scan_rejected(self) -> None:
        result = should_exclude(make_listing(), "apartament la demisol, 55 mp")
        assert result.rejected

    def test_plain_listing_accepted(self) -> None:
        listing = make_listing(price_eur=80_000)
        assert not should_exclude(listing).rejected


class TestMentionsBasement:
    def test_case_insensitive(self) -> None:
        assert mentions_basement("Etaj Demisol Block 5")
        assert mentions_basement("SUBSOLUL BLOCULUI")

    def test_no_match(self) -> None:
        assert not mentions_basement("etaj 3", "parter")

    def test_empty_texts(self) -> None:
        assert not mentions_basement("", None, " ")