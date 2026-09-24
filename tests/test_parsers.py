from src.extractor.parsers import (
    _coords_from_text,
    _price_from_text,
    _rooms_from_text,
    _seismic_class_from_text,
    _sqm_from_text,
    _storeys_from_text,
    _year_from_text,
    extract_from_html,
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


class TestYearFromText:
    def test_romanian_phrases(self):
        assert _year_from_text("an constructie 1968") == 1968
        assert _year_from_text("anul de construire 1972") == 1972
        assert _year_from_text("construit in 1930") == 1930
        assert _year_from_text("bloc din 1963") == 1963
        assert _year_from_text("anul 1955") == 1955
        assert _year_from_text("an 2005") == 2005

    def test_built_in_english(self):
        assert _year_from_text("apartment built in 2008") == 2008

    def test_ignores_phone_numbers(self):
        assert _year_from_text("Telefon 0722 123 456") is None

    def test_ignores_unrealistic_years(self):
        assert _year_from_text("an constructie 1500") is None


class TestStoreysFromText:
    def test_regim_inaltime(self):
        assert _storeys_from_text("bloc P+3") == 4
        assert _storeys_from_text("regim de inaltime P+2+M") == 3

    def test_plural_etaje(self):
        assert _storeys_from_text("bloc cu 5 etaje") == 5
        assert _storeys_from_text("cladire de 10 niveluri") == 10

    def test_apartment_floor_singular_ignored(self):
        assert _storeys_from_text("apartament la etaj 4") is None

    def test_english_plural(self):
        assert _storeys_from_text("building with 6 floors") == 6


class TestSeismicClassFromText:
    def test_arabic_numerals(self):
        assert _seismic_class_from_text("bloc cu risc seismic 1") == 1
        assert _seismic_class_from_text("risc seismic 2") == 2

    def test_roman_numerals(self):
        assert _seismic_class_from_text("clasa de risc seismic I") == 1
        assert _seismic_class_from_text("risc seismic II") == 2
        assert _seismic_class_from_text("incadrata risc seismic IV") == 4

    def test_r_prefix(self):
        assert _seismic_class_from_text("risc seismic R1") == 1

    def test_english(self):
        assert _seismic_class_from_text("seismic risk class 3") == 3

    def test_missing_phrase_returns_none(self):
        assert _seismic_class_from_text("apartament luminos, etaj 2") is None


class TestSeismicExtractionFromHtml:
    def test_extracts_year_and_risk_class_from_description(self):
        html = """<html><head><meta property="og:description"
          content="Bloc din 1960, 3 etaje, risc seismic 2, central" />
        </head><body><h1>Apartament</h1></body></html>"""
        ext = extract_from_html(html, listing_id="x1", url="https://www.storia.ro/x")
        assert ext.construction_year == 1960
        assert ext.storeys == 3
        assert ext.seismic_risk_class == 2
        assert "storeys_text" in ext.parse_methods
        assert "seismic_text" in ext.parse_methods

    def test_extracts_from_json_state(self):
        html = """<html><head></head><body>
          <script>window.__STATE__ = {"yearBuilt": 2015, "storeys": 7,
            "riscSeismic": "R1"};</script>
        </body></html>"""
        ext = extract_from_html(html, listing_id="x1", url="https://www.storia.ro/x")
        assert ext.construction_year == 2015
        assert ext.storeys == 7
        assert ext.seismic_risk_class == 1

    def test_no_seismic_signals_stays_none(self):
        html = """<html><head></head><body><h1>Apartament</h1></body></html>"""
        ext = extract_from_html(html, listing_id="x1", url="https://www.storia.ro/x")
        assert ext.construction_year is None
        assert ext.storeys is None
        assert ext.seismic_risk_class is None
