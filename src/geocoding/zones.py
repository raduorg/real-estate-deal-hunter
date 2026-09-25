from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from shapely.geometry import MultiPolygon, Point, shape

from src.models.listing import Listing

logger = logging.getLogger(__name__)

_SECTOR_RE = re.compile(r"\bsector(?:ul)?\s*([1-6])\b", re.IGNORECASE)
_CITY_ALIASES = {"bucuresti": "Bucuresti", "bucharest": "Bucuresti"}


def _normalize_text(value: object) -> str:
    raw = value.value if isinstance(value, Enum) else str(value)
    decomposed = unicodedata.normalize("NFKD", raw).casefold()
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())


class Sector(str, Enum):
    SECTOR_1 = "Sector 1"
    SECTOR_2 = "Sector 2"
    SECTOR_3 = "Sector 3"
    SECTOR_4 = "Sector 4"
    SECTOR_5 = "Sector 5"
    SECTOR_6 = "Sector 6"

    ONE = SECTOR_1
    TWO = SECTOR_2
    THREE = SECTOR_3
    FOUR = SECTOR_4
    FIVE = SECTOR_5
    SIX = SECTOR_6

    @property
    def number(self) -> int:
        return int(self.value.rsplit(" ", 1)[1])

    @classmethod
    def parse(cls, raw: object) -> Sector | None:
        if isinstance(raw, cls):
            return raw
        key = _normalize_text(raw)
        match = re.fullmatch(r"sector(?:ul)?\s*([1-6])", key)
        if not match:
            return None
        return cls(f"Sector {int(match.group(1))}")


class Neighborhood(str, Enum):
    CISMIGIU = "Cișmigiu"
    AVIATORILOR = "Aviatorilor"
    BANEASA = "Băneasa"
    BUCHARESTII_NOI = "Bucureștii Noi"
    CALEA_VICTORIEI = "Calea Victoriei"
    DAMAROAIA = "Dămăroaia"
    DOMENII = "Domenii"
    DOROBANTI = "Dorobanți"
    GRIVITA = "Grivița"
    HERASTRAU_BORDEI = "Herăstrău / Bordei"
    KISELEFF = "Kiseleff"
    PAJURA = "Pajura"
    PIATA_ROMANA = "Piața Romană"
    PIATA_VICTORIEI = "Piața Victoriei"
    PRIMAVERII = "Primăverii"
    SALA_PALATULUI = "Sala Palatului"
    STRAULESTI = "Străulești"
    UNIVERSITATE = "Universitate"

    ONE_MAI = "1 Mai"
    ANDRONACHE = "Andronache"
    BAICULUI = "Baicului"
    BARBU_VACARESCU = "Barbu Văcărescu"
    COLENTINA = "Colentina"
    DACIA = "Dacia"
    DOAMNA_GHICA = "Doamna Ghica"
    EMINESCU = "Eminescu"
    FLOREASCA = "Floreasca"
    FUNDENI = "Fundeni"
    IANCULUI = "Iancului"
    LACUL_TEI = "Lacul Tei"
    MOSILOR = "Moșilor"
    OBOR = "Obor"
    PANTELIMON = "Pantelimon"
    STEFAN_CEL_MARE = "Ștefan cel Mare"
    TEI = "Tei"
    VATRA_LUMINOASA = "Vatra Luminoasă"

    ONE_DECEMBRIE_1918 = "1 Decembrie 1918"
    TWENTY_THREE_AUGUST = "23 August"
    ALBA_IULIA_PIATA_ALBA_IULIA = "Alba Iulia (Piața Alba Iulia)"
    BALTA_ALBA = "Balta Albă"
    BASARABIA = "Basarabia"
    CALARASI_CALEA_CALARASIILOR = "Călărași / Calea Călărașilor"
    CATELU = "Cățelu"
    CENTRUL_ISTORIC_LIPSCANI = "Centrul Istoric (Lipscani)"
    DECEBAL = "Decebal"
    DRISTOR = "Dristor"
    DUDESTI = "Dudești"
    MUNCII_PIATA_MUNCII = "Muncii (Piața Muncii)"
    NERVA_TRAIAN = "Nerva Traian"
    NICOLAE_GRIGORESCU = "Nicolae Grigorescu"
    OZANA = "Ozana"
    REPUBLICA = "Republica"
    SALAJAN = "Sălăjan"
    THEODOR_PALLADY = "Theodor Pallady"
    TIMPURI_NOI = "Timpuri Noi"
    TITAN = "Titan"
    TRAPEZULUI = "Trapezului"
    UNIRII = "Unirii"
    VITAN = "Vitan"
    VITAN_MALL = "Vitan Mall"
    VITAN_BARZESTI = "Vitan-Bârzești"

    APARATORII_PATRIEI = "Apărătorii Patriei"
    BERCENI = "Berceni"
    BRANCOVEANU = "Brâncoveanu"
    DIMITRIE_CANTEMIR = "Dimitrie Cantemir"
    EROII_REVOLUTIEI_PIEPTANARI = "Eroii Revoluției / Pieptănari"
    GIURGIULUI = "Giurgiului"
    METALURGIEI_GRAND_ARENA = "Metalurgiei / Grand Arena"
    OLTENITEI = "Olteniței"
    PIATA_RESITA = "Piața Reșița"
    PROGRESUL = "Progresul"
    SINCAI = "Șincai"
    TINERETULUI = "Tineretului"
    VACARESTI = "Văcărești"

    THIRTEEN_SEPTEMBRIE = "13 Septembrie"
    ALEXANDRIEI_SOSEAUA_ALEXANDRIEI = "Alexandriei (Șoseaua Alexandriei)"
    ANTIAERIANA = "Antiaeriană"
    COTROCENI_SOUTH_EAST_SECTION = "Cotroceni (South/East section)"
    EROILOR = "Eroilor"
    FERENTARI = "Ferentari"
    GHENCEA_EASTERN_BORDERS = "Ghencea (Eastern borders)"
    IZVOR = "Izvor"
    MARGEANULUI = "Mărgeanului"
    PANDURI_MARRIOTT = "Panduri / Marriott"
    PETRE_ISPIRESCU = "Petre Ispirescu"
    RAHOVA = "Rahova"
    SALAJ = "Sălaj"
    SEBASTIAN = "Sebastian"
    TUDOR_VLADIMIRESCU = "Tudor Vladimirescu"
    ZETARILOR = "Zețarilor"

    APUSULUI = "Apusului"
    BRANCUSI = "Brâncuși"
    CARTIERUL_LATIN = "Cartierul Latin"
    CRANGASI = "Crângași"
    DRUMUL_TABEREI = "Drumul Taberei"
    FAVORIT = "Favorit"
    GHENCEA = "Ghencea"
    GIULESTI = "Giulești"
    GORJULUI = "Gorjului"
    GROZAVESTI = "Grozăvești"
    LUJERULUI = "Lujerului"
    MILITARI = "Militari"
    ORIZONT = "Orizont"
    PACII = "Păcii"
    POLITEHNICA = "Politehnica"
    PRELUNGIREA_GHENCEA = "Prelungirea Ghencea"
    REGIE = "Regie"
    UVERTURII = "Uverturii"
    VIRTUTII = "Virtuții"

    HERASTRAU = HERASTRAU_BORDEI
    BORDEI = HERASTRAU_BORDEI
    COTROCENI = COTROCENI_SOUTH_EAST_SECTION
    LIPSCANI = CENTRUL_ISTORIC_LIPSCANI
    GHENCEA_EAST = GHENCEA_EASTERN_BORDERS
    PRIMAVERIE = PRIMAVERII
    ALBA_IULIA = ALBA_IULIA_PIATA_ALBA_IULIA
    ALEXANDRIEI = ALEXANDRIEI_SOSEAUA_ALEXANDRIEI
    BUCURESTII_NOI = BUCHARESTII_NOI
    CALARASI = CALARASI_CALEA_CALARASIILOR
    CALEA_CALARASIILOR = CALARASI_CALEA_CALARASIILOR
    MUNCII = MUNCII_PIATA_MUNCII
    PIATA_MUNCII = MUNCII_PIATA_MUNCII
    PIEPTANARI = EROII_REVOLUTIEI_PIEPTANARI
    PANDURI = PANDURI_MARRIOTT
    RESITA = PIATA_RESITA

    @property
    def sector(self) -> Sector | None:
        return NEIGHBORHOOD_TO_SECTOR.get(self)

    @classmethod
    def parse(cls, raw: object) -> Neighborhood | None:
        if isinstance(raw, cls):
            return raw
        matches = neighborhood_candidates_in_text(str(raw))
        if not matches:
            return None
        return matches[0]


class ZoneKind(str, Enum):
    NEIGHBORHOOD = "neighborhood"
    SECTOR = "sector"


ZoneType = ZoneKind

NEIGHBORHOODS_BY_SECTOR: dict[Sector, tuple[Neighborhood, ...]] = {
    Sector.SECTOR_1: (
        Neighborhood.CISMIGIU,
        Neighborhood.AVIATORILOR,
        Neighborhood.BANEASA,
        Neighborhood.BUCHARESTII_NOI,
        Neighborhood.CALEA_VICTORIEI,
        Neighborhood.DAMAROAIA,
        Neighborhood.DOMENII,
        Neighborhood.DOROBANTI,
        Neighborhood.GRIVITA,
        Neighborhood.HERASTRAU_BORDEI,
        Neighborhood.KISELEFF,
        Neighborhood.PAJURA,
        Neighborhood.PIATA_ROMANA,
        Neighborhood.PIATA_VICTORIEI,
        Neighborhood.PRIMAVERII,
        Neighborhood.SALA_PALATULUI,
        Neighborhood.STRAULESTI,
        Neighborhood.UNIVERSITATE,
    ),
    Sector.SECTOR_2: (
        Neighborhood.ONE_MAI,
        Neighborhood.ANDRONACHE,
        Neighborhood.BAICULUI,
        Neighborhood.BARBU_VACARESCU,
        Neighborhood.COLENTINA,
        Neighborhood.DACIA,
        Neighborhood.DOAMNA_GHICA,
        Neighborhood.EMINESCU,
        Neighborhood.FLOREASCA,
        Neighborhood.FUNDENI,
        Neighborhood.IANCULUI,
        Neighborhood.LACUL_TEI,
        Neighborhood.MOSILOR,
        Neighborhood.OBOR,
        Neighborhood.PANTELIMON,
        Neighborhood.STEFAN_CEL_MARE,
        Neighborhood.TEI,
        Neighborhood.VATRA_LUMINOASA,
    ),
    Sector.SECTOR_3: (
        Neighborhood.ONE_DECEMBRIE_1918,
        Neighborhood.TWENTY_THREE_AUGUST,
        Neighborhood.ALBA_IULIA_PIATA_ALBA_IULIA,
        Neighborhood.BALTA_ALBA,
        Neighborhood.BASARABIA,
        Neighborhood.CALARASI_CALEA_CALARASIILOR,
        Neighborhood.CATELU,
        Neighborhood.CENTRUL_ISTORIC_LIPSCANI,
        Neighborhood.DECEBAL,
        Neighborhood.DRISTOR,
        Neighborhood.DUDESTI,
        Neighborhood.MUNCII_PIATA_MUNCII,
        Neighborhood.NERVA_TRAIAN,
        Neighborhood.NICOLAE_GRIGORESCU,
        Neighborhood.OZANA,
        Neighborhood.REPUBLICA,
        Neighborhood.SALAJAN,
        Neighborhood.THEODOR_PALLADY,
        Neighborhood.TIMPURI_NOI,
        Neighborhood.TITAN,
        Neighborhood.TRAPEZULUI,
        Neighborhood.UNIRII,
        Neighborhood.VITAN,
        Neighborhood.VITAN_MALL,
        Neighborhood.VITAN_BARZESTI,
    ),
    Sector.SECTOR_4: (
        Neighborhood.APARATORII_PATRIEI,
        Neighborhood.BERCENI,
        Neighborhood.BRANCOVEANU,
        Neighborhood.DIMITRIE_CANTEMIR,
        Neighborhood.EROII_REVOLUTIEI_PIEPTANARI,
        Neighborhood.GIURGIULUI,
        Neighborhood.METALURGIEI_GRAND_ARENA,
        Neighborhood.OLTENITEI,
        Neighborhood.PIATA_RESITA,
        Neighborhood.PROGRESUL,
        Neighborhood.SINCAI,
        Neighborhood.TINERETULUI,
        Neighborhood.VACARESTI,
    ),
    Sector.SECTOR_5: (
        Neighborhood.THIRTEEN_SEPTEMBRIE,
        Neighborhood.ALEXANDRIEI_SOSEAUA_ALEXANDRIEI,
        Neighborhood.ANTIAERIANA,
        Neighborhood.COTROCENI_SOUTH_EAST_SECTION,
        Neighborhood.EROILOR,
        Neighborhood.FERENTARI,
        Neighborhood.GHENCEA_EASTERN_BORDERS,
        Neighborhood.IZVOR,
        Neighborhood.MARGEANULUI,
        Neighborhood.PANDURI_MARRIOTT,
        Neighborhood.PETRE_ISPIRESCU,
        Neighborhood.RAHOVA,
        Neighborhood.SALAJ,
        Neighborhood.SEBASTIAN,
        Neighborhood.TUDOR_VLADIMIRESCU,
        Neighborhood.ZETARILOR,
    ),
    Sector.SECTOR_6: (
        Neighborhood.APUSULUI,
        Neighborhood.BRANCUSI,
        Neighborhood.CARTIERUL_LATIN,
        Neighborhood.CRANGASI,
        Neighborhood.DRUMUL_TABEREI,
        Neighborhood.FAVORIT,
        Neighborhood.GHENCEA,
        Neighborhood.GIULESTI,
        Neighborhood.GORJULUI,
        Neighborhood.GROZAVESTI,
        Neighborhood.LUJERULUI,
        Neighborhood.MILITARI,
        Neighborhood.ORIZONT,
        Neighborhood.PACII,
        Neighborhood.POLITEHNICA,
        Neighborhood.PRELUNGIREA_GHENCEA,
        Neighborhood.REGIE,
        Neighborhood.UVERTURII,
        Neighborhood.VIRTUTII,
    ),
}

NEIGHBORHOOD_TO_SECTOR: dict[Neighborhood, Sector] = {
    neighborhood: sector
    for sector, neighborhoods in NEIGHBORHOODS_BY_SECTOR.items()
    for neighborhood in neighborhoods
}
NEIGHBORHOOD_SECTORS: dict[Neighborhood, tuple[Sector, ...]] = {}
for _sector, _neighborhoods in NEIGHBORHOODS_BY_SECTOR.items():
    for _neighborhood in _neighborhoods:
        NEIGHBORHOOD_SECTORS.setdefault(_neighborhood, ())
        if _sector not in NEIGHBORHOOD_SECTORS[_neighborhood]:
            NEIGHBORHOOD_SECTORS[_neighborhood] += (_sector,)
NEIGHBORHOODS_BY_SECTOR_NAME: dict[str, tuple[str, ...]] = {
    sector.value: tuple(neighborhood.value for neighborhood in neighborhoods)
    for sector, neighborhoods in NEIGHBORHOODS_BY_SECTOR.items()
}
NEIGHBORHOOD_TO_SECTOR_NAME: dict[str, str] = {
    neighborhood.value: sector.value for neighborhood, sector in NEIGHBORHOOD_TO_SECTOR.items()
}

_CANONICAL_ZONE_LIST_PATH = Path(__file__).resolve().parents[2] / "canonical_zone_list.txt"


def _neighborhood_from_label(label: str) -> Neighborhood | None:
    normalized = _normalize_text(label)
    for neighborhood in Neighborhood:
        if _normalize_text(neighborhood.value) == normalized:
            return neighborhood
    return None


def load_canonical_zone_list(
    path: str | Path | None = None,
) -> dict[Sector, tuple[Neighborhood, ...]]:
    """Load and validate the neighborhood catalog from the canonical text file."""
    catalog_path = Path(path) if path is not None else _CANONICAL_ZONE_LIST_PATH
    entries: dict[Sector, list[Neighborhood]] = {sector: [] for sector in Sector}
    current_sector: Sector | None = None
    try:
        lines = catalog_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("Canonical zone list not found: %s (%s)", catalog_path, exc)
        return NEIGHBORHOODS_BY_SECTOR
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        header = re.fullmatch(r"Sector\s+([1-6])", line, re.IGNORECASE)
        if header:
            current_sector = Sector(f"Sector {int(header.group(1))}")
            continue
        if current_sector is None:
            continue
        neighborhood = _neighborhood_from_label(line)
        if neighborhood is not None and neighborhood not in entries[current_sector]:
            entries[current_sector].append(neighborhood)
    if any(not entries[sector] for sector in Sector):
        return NEIGHBORHOODS_BY_SECTOR
    return {sector: tuple(values) for sector, values in entries.items()}


try:
    CANONICAL_NEIGHBORHOODS_BY_SECTOR = load_canonical_zone_list()
except Exception:
    CANONICAL_NEIGHBORHOODS_BY_SECTOR = NEIGHBORHOODS_BY_SECTOR


def _label_aliases(label: str) -> set[str]:
    aliases = {_normalize_text(label)}
    without_parentheses = re.sub(r"\s*\([^)]*\)", "", label).strip()
    if without_parentheses:
        aliases.add(_normalize_text(without_parentheses))
    for part in re.split(r"\s*/\s*", label):
        if part.strip():
            aliases.add(_normalize_text(part))
    for parenthetical in re.findall(r"\(([^)]*)\)", label):
        if parenthetical.strip():
            aliases.add(_normalize_text(parenthetical))
    normalized = _normalize_text(label)
    for prefix in ("cartierul ", "cartier ", "zona "):
        if normalized.startswith(prefix):
            aliases.add(normalized[len(prefix) :])
    if normalized.startswith("1 decembrie 1918"):
        aliases.update({"1 decembrie", "1 decembrie 1918"})
    if normalized.startswith("13 septembrie"):
        aliases.update({"13 sep", "13 september"})
    if normalized.startswith("primaverii"):
        aliases.add("primaverie")
    return {alias for alias in aliases if alias}


def _build_neighborhood_aliases() -> dict[str, tuple[Neighborhood, ...]]:
    candidates: dict[str, list[Neighborhood]] = {}
    for neighborhoods in CANONICAL_NEIGHBORHOODS_BY_SECTOR.values():
        for neighborhood in neighborhoods:
            for alias in _label_aliases(neighborhood.value):
                candidates.setdefault(alias, []).append(neighborhood)
    return {
        alias: tuple(dict.fromkeys(values))
        for alias, values in sorted(candidates.items(), key=lambda item: item[0])
    }


_NEIGHBORHOOD_ALIASES = _build_neighborhood_aliases()


def _is_known_neighborhood(
    neighborhood: Neighborhood,
    known_neighborhoods: set[object] | None,
) -> bool:
    if known_neighborhoods is None:
        return True
    known_normalized = {
        _normalize_text(value.value if isinstance(value, Enum) else value)
        for value in known_neighborhoods
    }
    return (
        _normalize_text(neighborhood.value) in known_normalized
        or neighborhood in known_neighborhoods
    )


def neighborhood_candidates_in_text(
    text: str | None,
    known_neighborhoods: set[object] | None = None,
) -> list[Neighborhood]:
    """Return canonical neighborhoods explicitly present in text, in order."""
    if not text:
        return []
    normalized_text = _normalize_text(text)
    matches: list[tuple[int, int, int, Neighborhood]] = []
    for alias, neighborhoods in _NEIGHBORHOOD_ALIASES.items():
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])")
        for match in pattern.finditer(normalized_text):
            for priority, neighborhood in enumerate(neighborhoods):
                if not _is_known_neighborhood(neighborhood, known_neighborhoods):
                    continue
                exact_priority = 0 if _normalize_text(neighborhood.value) == alias else 1
                matches.append(
                    (match.start(), match.end(), exact_priority * 100 + priority, neighborhood)
                )
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))
    selected: list[Neighborhood] = []
    occupied: list[tuple[int, int]] = []
    for start, end, _priority, neighborhood in matches:
        if any(start < other_end and end > other_start for other_start, other_end in occupied):
            continue
        if neighborhood in selected:
            continue
        selected.append(neighborhood)
        occupied.append((start, end))
    return selected


def neighborhoods_in_text(
    text: str | None,
    known_neighborhoods: set[object] | None = None,
) -> list[str]:
    return [
        neighborhood.value
        for neighborhood in neighborhood_candidates_in_text(text, known_neighborhoods)
    ]


def canonical_neighborhood_name(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    candidates = neighborhood_candidates_in_text(text)
    if not candidates:
        return None
    normalized = _normalize_text(text)
    for neighborhood in candidates:
        if _normalize_text(neighborhood.value) == normalized:
            return neighborhood.value
    return candidates[0].value


def canonical_sector_name(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    sector = Sector.parse(text)
    if sector:
        return sector.value
    match = _SECTOR_RE.search(text)
    if match:
        return Sector(f"Sector {int(match.group(1))}").value
    return None


def canonical_zone_name(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    normalized = _normalize_text(text)
    if normalized in _CITY_ALIASES:
        return _CITY_ALIASES[normalized]
    neighborhood = canonical_neighborhood_name(text)
    if neighborhood:
        return neighborhood
    sector = canonical_sector_name(text)
    if sector:
        return sector
    return text


def sectors_in_text(text: str | None, known_zones: set[object] | None = None) -> list[str]:
    """Return explicitly named Bucharest sectors in order of appearance."""
    if not text:
        return []
    found: list[str] = []
    for match in _SECTOR_RE.finditer(text):
        sector = Sector(f"Sector {int(match.group(1))}")
        if known_zones is not None:
            known_normalized = {
                _normalize_text(value.value if isinstance(value, Enum) else value)
                for value in known_zones
            }
            if _normalize_text(sector.value) not in known_normalized and sector not in known_zones:
                continue
        if sector.value not in found:
            found.append(sector.value)
    return found


@dataclass(frozen=True)
class ZoneMatch:
    """Result of resolving a listing to a neighborhood or sector fallback."""

    zone: str = ""
    avg_price_sqm: float | None = None
    matched: bool = False
    method: str = ""
    sector: str | None = None
    neighborhood: str | None = None

    @property
    def kind(self) -> ZoneKind:
        return ZoneKind.NEIGHBORHOOD if self.neighborhood else ZoneKind.SECTOR

    @property
    def zone_kind(self) -> ZoneKind:
        return self.kind

    @property
    def zone_type(self) -> ZoneKind:
        return self.kind


class ZoneIndex:
    """Point-in-polygon index over Bucharest sector boundaries."""

    def __init__(self, geojson_path: str | Path) -> None:
        self.geojson_path = Path(geojson_path)
        self._polygons: dict[str, MultiPolygon] = {}
        self._load()

    def _load(self) -> None:
        if not self.geojson_path.exists():
            logger.warning("Zone boundaries not found: %s", self.geojson_path)
            return
        data = json.loads(self.geojson_path.read_text(encoding="utf-8"))
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            geom = feature.get("geometry")
            if not geom:
                continue
            name = canonical_zone_name(props.get("name") or props.get("shapeName"))
            if not name:
                continue
            try:
                poly = shape(geom)
            except (TypeError, ValueError) as exc:
                logger.warning("Skipping unreadable geometry for %s: %s", name, exc)
                continue
            if isinstance(poly, MultiPolygon):
                self._polygons[name] = poly
            else:
                self._polygons[name] = MultiPolygon([poly])

    @property
    def zone_names(self) -> list[str]:
        return sorted(self._polygons)

    @property
    def sector_names(self) -> list[str]:
        return self.zone_names

    def zone_for_point(self, latitude: float, longitude: float) -> str | None:
        if not self._polygons:
            return None
        point = Point(longitude, latitude)
        for name, poly in self._polygons.items():
            if poly.contains(point):
                return name
        return None

    def sector_for_point(self, latitude: float, longitude: float) -> str | None:
        return self.zone_for_point(latitude, longitude)


class ZoneResolver:
    """Resolve a listing to a canonical neighborhood, falling back to sector."""

    def __init__(
        self,
        zone_index: ZoneIndex | None = None,
        prices: Mapping[str, float] | None = None,
        fallback_city: str = "Bucuresti",
    ) -> None:
        self.zone_index = zone_index
        self.fallback_city = canonical_zone_name(fallback_city) or fallback_city
        self.replace_prices(prices or {})

    @staticmethod
    def _build_price_lookup(prices: dict[str, float]) -> dict[str, float]:
        lookup: dict[str, float] = {}
        for key, value in prices.items():
            raw = key.value if isinstance(key, Enum) else str(key)
            lookup[_normalize_text(raw)] = value
            for candidate in (canonical_zone_name(raw), canonical_neighborhood_name(raw)):
                if candidate:
                    lookup[_normalize_text(candidate)] = value
        return lookup

    def replace_prices(self, prices: Mapping[str, float]) -> None:
        self.prices = dict(prices)
        self._price_lookup = self._build_price_lookup(self.prices)

    @property
    def price_keys(self) -> set[str]:
        return {
            key.value if isinstance(key, Enum) else str(key)
            for key in self.prices
        }

    def _price_for(
        self,
        zone: str | Sector | Neighborhood | None,
        sector: str | Sector | None,
    ) -> float | None:
        for candidate in (zone, sector, self.fallback_city):
            if not candidate:
                continue
            raw = candidate.value if isinstance(candidate, Enum) else str(candidate)
            value = self.prices.get(raw)
            if value is not None:
                return value
            value = self._price_lookup.get(_normalize_text(raw))
            if value is not None:
                return value
        return None

    def price_for(
        self,
        zone: str | Sector | Neighborhood | None,
        sector: str | Sector | None = None,
    ) -> float | None:
        return self._price_for(zone, sector)

    def _sector_for_listing(self, listing: Listing) -> Sector | None:
        if self.zone_index is None or listing.latitude is None or listing.longitude is None:
            return None
        name = self.zone_index.zone_for_point(listing.latitude, listing.longitude)
        return Sector.parse(name) if name else None

    @staticmethod
    def _field_text(listing: Listing) -> str:
        return " ".join(
            part
            for part in (
                listing.neighborhood,
                listing.address,
                listing.title,
                listing.description,
                listing.email_subject,
            )
            if part
        )

    @staticmethod
    def _choose_neighborhood(
        field_candidates: list[Neighborhood],
        body_candidates: list[Neighborhood],
        coordinate_sector: Sector | None,
        text_sectors: list[str],
    ) -> Neighborhood | None:
        candidates = field_candidates or body_candidates
        if not candidates:
            return None
        if field_candidates:
            extras = [
                candidate
                for candidate in body_candidates
                if candidate not in field_candidates
            ]
            if len(extras) == 1:
                candidates = extras
        if coordinate_sector is not None:
            for candidate in candidates:
                if coordinate_sector in NEIGHBORHOOD_SECTORS.get(candidate, ()):
                    return candidate
        for sector_text in text_sectors:
            sector = Sector.parse(sector_text)
            if sector is None:
                continue
            for candidate in candidates:
                if sector in NEIGHBORHOOD_SECTORS.get(candidate, ()):
                    return candidate
        return candidates[0]

    @staticmethod
    def _sector_for_neighborhood(
        neighborhood: Neighborhood,
        coordinate_sector: Sector | None,
        text_sectors: list[str],
    ) -> Sector:
        sectors = NEIGHBORHOOD_SECTORS.get(neighborhood, ())
        if not sectors:
            return coordinate_sector or Sector.SECTOR_1
        if len(sectors) == 1:
            return sectors[0]
        if coordinate_sector in sectors:
            return coordinate_sector
        for sector_text in text_sectors:
            sector = Sector.parse(sector_text)
            if sector in sectors:
                return sector
        return sectors[0]

    def resolve(self, listing: Listing, body_text: str = "") -> ZoneMatch:
        field_text = self._field_text(listing)
        field_neighborhoods = neighborhood_candidates_in_text(field_text)
        body_neighborhoods = neighborhood_candidates_in_text(body_text)
        field_sectors = sectors_in_text(field_text)
        body_sectors = sectors_in_text(body_text)
        text_sectors = field_sectors or body_sectors
        coordinate_sector = self._sector_for_listing(listing)

        neighborhood = self._choose_neighborhood(
            field_neighborhoods,
            body_neighborhoods,
            coordinate_sector,
            text_sectors,
        )
        if neighborhood is not None:
            sector = self._sector_for_neighborhood(neighborhood, coordinate_sector, text_sectors)
            return ZoneMatch(
                zone=neighborhood.value,
                avg_price_sqm=self._price_for(neighborhood.value, sector.value),
                matched=True,
                method="neighborhood",
                sector=sector.value,
                neighborhood=neighborhood.value,
            )

        if coordinate_sector is not None:
            return ZoneMatch(
                zone=coordinate_sector.value,
                avg_price_sqm=self._price_for(None, coordinate_sector.value),
                matched=True,
                method="coords",
                sector=coordinate_sector.value,
            )

        if text_sectors:
            sector = Sector.parse(text_sectors[0])
            if sector:
                return ZoneMatch(
                    zone=sector.value,
                    avg_price_sqm=self._price_for(None, sector.value),
                    matched=True,
                    method="sector_text",
                    sector=sector.value,
                )

        if (
            self.zone_index is not None
            and listing.latitude is not None
            and listing.longitude is not None
        ):
            return ZoneMatch(method="coords_outside")
        return ZoneMatch(method="no_coords")


__all__ = [
    "CANONICAL_NEIGHBORHOODS_BY_SECTOR",
    "NEIGHBORHOODS_BY_SECTOR",
    "NEIGHBORHOODS_BY_SECTOR_NAME",
    "NEIGHBORHOOD_SECTORS",
    "NEIGHBORHOOD_TO_SECTOR",
    "NEIGHBORHOOD_TO_SECTOR_NAME",
    "Neighborhood",
    "Sector",
    "ZoneIndex",
    "ZoneKind",
    "ZoneMatch",
    "ZoneResolver",
    "ZoneType",
    "canonical_neighborhood_name",
    "canonical_sector_name",
    "canonical_zone_name",
    "load_canonical_zone_list",
    "neighborhood_candidates_in_text",
    "neighborhoods_in_text",
    "sectors_in_text",
]
