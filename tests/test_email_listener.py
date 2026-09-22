from src.email_listener.parsers import (
    decode_imobiliare_tracking,
    extract_listing_urls,
    is_tracking_url,
    normalize_listing_url,
)
from src.extractor.parsers import extract_from_html, source_from_url


class TestDecodeImobiliareTracking:
    def test_decodes_click_link(self):
        url = (
            "https://link.imobiliare.ro/click/6aaa4deda13b5f107f05d671/"
            "aHR0cHM6Ly93d3cuaW1vYmlsaWFyZS5yby9vZmVydGEvb2ZlcnRhLWFwYXJ0YW1lbnQvOTk9"
        )
        # aHR0cHM6Ly93d3cuaW1vYmlsaWFyZS5yby9vZmVydGEv... = https://www.imobiliare.ro/oferta/
        assert decode_imobiliare_tracking(url).startswith("https://www.imobiliare.ro/")

    def test_rejects_external_link(self):
        url = (
            "https://link.imobiliare.ro/external/6aaa4deda13b5f107f05d671/"
            "aHR0cHM6Ly93d3cuZmFjZWJvb2suY29tL3BhZ2VzL2ltb2JpbGlhcmVybz1="
        )
        assert decode_imobiliare_tracking(url) is None

    def test_rejects_non_tracking_domain(self):
        assert decode_imobiliare_tracking("https://www.imobiliare.ro/oferta/x-123") is None


class TestIsTrackingUrl:
    def test_storia_tracking(self):
        assert is_tracking_url("https://clicks.alerts.storia.ro/f/a/abc/AAAHahA~/xyz")

    def test_imobiliare_tracking(self):
        assert is_tracking_url("https://link.imobiliare.ro/click/abc/def")

    def test_direct_listing_is_not_tracking(self):
        assert not is_tracking_url("https://www.storia.ro/ro/oferta/apartament-IDabc")


class TestNormalizeListingUrl:
    def test_strips_tracking_params(self):
        url = (
            "https://www.storia.ro/ro/oferta/apartament-IDabc?lid=eh8y8oelm1sz"
            "&utm_medium=email&utm_source=braze&utm_campaign=all&utm_id=abc&utm_content=Variant%201"
        )
        assert normalize_listing_url(url) == "https://www.storia.ro/ro/oferta/apartament-IDabc"

    def test_keeps_relevant_params(self):
        url = "https://www.storia.ro/ro/oferta/apartament-IDabc?q=2&req=1"
        assert normalize_listing_url(url) == url


class TestExtractListingUrlsFromEmail:
    def test_collects_storia_tracking_links(self):
        html = """
        <a href="https://clicks.alerts.storia.ro/f/a/tok1/AAAHahA~/h">Listing</a>
        <a href="https://clicks.alerts.storia.ro/f/a/tok2/AAAHahA~/h"></a>
        <a href="https://www.storia.ro/ro/oferta/">back</a>
        <a href="https://storia.ro">home</a>
        """
        urls = extract_listing_urls(html)
        assert "https://clicks.alerts.storia.ro/f/a/tok1/AAAHahA~/h" in urls
        assert "https://clicks.alerts.storia.ro/f/a/tok2/AAAHahA~/h" in urls
        assert "https://www.storia.ro/" not in urls


class TestExtractionNoNumericNeighborhood:
    """A numeric `area` JSON key (usable sqm) must not be picked up as a neighborhood."""

    def test_area_number_not_neighborhood(self):
        html = """
        <html><head>
        <meta property="og:title" content="Apartament 2 camere 60mp - Bucuresti, Floreasca">
        <script type="application/ld+json">
        {"@context": "https://schema.org/", "type": "RealEstateListing",
         "name": "Apartament", "offers": {"price": "98000", "priceCurrency": "EUR"},
         "floorSize": {"value": 60, "unitCode": "MTK"},
         "area": 39.36, "city": "Bucuresti"}
        </script>
        </head></html>
        """
        extraction = extract_from_html(html, listing_id="x", url="https://storia.ro/ro/oferta/a-IDx")
        assert extraction.neighborhood != "39.36"
        assert extraction.sqm is not None


class TestTrackingSourceDetection:
    def test_storia_tracking_resolves_source(self):
        # source detection from the *decoded* URL must say storia
        assert source_from_url("https://www.storia.ro/ro/oferta/apartament-IDx") == "storia"
        assert source_from_url("https://www.imobiliare.ro/oferta/apartament-123") == "imobiliare"