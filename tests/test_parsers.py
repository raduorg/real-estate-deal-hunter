from src.extractor.parsers import (
    _coords_from_text,
    _price_from_text,
    _rooms_from_text,
    _sqm_from_text,
    source_from_url,
)


class TestPriceFromText:
    def test_euro_thousands_with_dot(self):
        assert _price_from_text("Apartament 2 camere, 60 mp, 89.000 Euro") == 89000

    def test_euro_thousands_with_space(self):
        assert _price_from_text("Pret: 139 500 EUR negociabil") == 139500

    def test_euro_prefix_symbol(self):
        assert _price_from_text("Pret de vanzare: € 79.500") == 79500

    def test_ron_converted(self):
        assert _price_from_text("Pret: 450.000 lei") == 90000

    def test_compact_number(self):
        assert _price_from_text("Solicit numai 89000 euro") == 89000

    def test_no_currency_ignored(self):
        assert _price_from_text("Telefon 0722 123 456, an 2005") is None


class TestSqmFromText:
    def test_sqm_squared_symbol(self):
        assert _sqm_from_text("Suprafata: 60 m²") == 60

    def test_sqm_plain_m2(self):
        assert _sqm_from_text("58 m2 etaj 4") == 58

    def test_sqm_mp_abbreviation(self):
        assert _sqm_from_text("60 mp, 2 camere") == 60

    def test_sqm_decimal_comma(self):
        assert _sqm_from_text("52,5 m²") == 52.5

    def test_sqm_not_ml(self):
        assert _sqm_from_text("Volum 85 ml") is None


class TestRoomsFromText:
    def test_rooms_ro(self):
        assert _rooms_from_text("3 camere, 2 bai") == 3

    def test_rooms_en(self):
        assert _rooms_from_text("2 rooms apartment") == 2


class TestCoordsFromText:
    def test_coordinate_keys(self):
        html = """<script>var map = {"latitude": 44.44610, "longitude": 26.09800};</script>"""
        assert _coords_from_text(html) == (44.4461, 26.098)

    def test_out_of_range_ignored(self):
        html = """{"lat": 99.12345, "lng": 260.12345, "lat": 44.12345, "lon": 26.12345}"""
        assert _coords_from_text(html) == (44.12345, 26.12345)


class TestSourceFromUrl:
    def test_portal_detection(self):
        assert source_from_url("https://www.imobiliare.ro/apartament...") == "imobiliare"
        assert source_from_url("https://www.storia.ro/ro/oferta/...") == "storia"
        assert source_from_url("https://www.olx.ro/d/oferta/...") == "olx"
        assert source_from_url("https://www.publi24.ro/anunt/...") == "publi24"
        assert source_from_url("https://example.com/x") == "unknown"
