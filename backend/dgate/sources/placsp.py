"""PLACSP connector (Spain).

Live feed:  https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/
            licitacionesPerfilesContratanteCompleto3.atom
Archives:   .../licitacionesPerfilesContratanteCompleto3_YYYY.zip   (annual, 2012+)
            .../licitacionesPerfilesContratanteCompleto3_YYYYMM.zip (monthly, current year)
Spec:       https://contrataciondelsectorpublico.gob.es/datosabiertos/especificacion-sindicacion.pdf
Format:     ATOM envelope, CODICE 2.x XML payload per entry
Paging:     max 500 entries per file, chained via atom:link[@rel="next"]
Licence:    open public sector information, commercial reuse permitted

Two behaviours worth knowing before reading the code:

1. The same tender appears once per modification. That is not a bug to
   deduplicate away, it is the version history, and it feeds the archive
   directly.

2. Dataset 1 (contracting profiles hosted on PLACSP) misses regional buyers,
   who reach PLACSP through the aggregation mechanism in dataset 2. Ingesting
   only dataset 1 silently loses the autonomous communities.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterator
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import httpx

from ..normalise import Opportunity, tz_from_offset
from . import USER_AGENT

SPAIN_TZ = ZoneInfo("Europe/Madrid")

# CODICE ContractFolderStatusCode -> our normalised lifecycle value.
# Source: especificacion-sindicacion.pdf, code list ContractFolderStatusCode.
# Anything unmapped becomes "unknown" rather than silently "open": an unknown
# code must be visible, not disguised as an open tender.
STATUS_MAP = {
    "PRE": "open",       # anuncio previo
    "PUB": "open",       # publicada
    "EV": "open",        # en evaluacion, still live for the archive timeline
    "ADJ": "awarded",    # adjudicada
    "RES": "awarded",    # resuelta / formalizada
    "ANUL": "cancelled",  # anulada
    "DES": "cancelled",  # desierta
}


def map_status(code: str | None) -> str:
    if not code:
        return "open"
    return STATUS_MAP.get(code.strip().upper(), "unknown")

log = logging.getLogger(__name__)

BASE = "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643"
LIVE_FEED = f"{BASE}/licitacionesPerfilesContratanteCompleto3.atom"
ENTRY_FILE = "licitacionesPerfilesContratanteCompleto3.atom"

# Dataset 2: regional and aggregated buyers, published through a different
# sindicacion path. Spanish autonomous communities run their own platforms and
# reach PLACSP through this aggregation, so ingesting only dataset 1 silently
# loses every regional buyer.
BASE_AGG = "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1044"
LIVE_FEED_AGG = f"{BASE_AGG}/PlataformasAgregadasSinMenores.atom"
ENTRY_FILE_AGG = "PlataformasAgregadasSinMenores.atom"


@dataclass(frozen=True)
class Dataset:
    """One PLACSP dataset. Both share the parser; only the URLs differ."""

    source_code: str
    base: str
    live_feed: str
    entry_file: str
    archive_stem: str

    def annual_archive_url(self, year: int) -> str:
        return f"{self.base}/{self.archive_stem}_{year}.zip"

    def monthly_archive_url(self, year: int, month: int) -> str:
        return f"{self.base}/{self.archive_stem}_{year}{month:02d}.zip"


MAIN = Dataset("es_placsp", BASE, LIVE_FEED, ENTRY_FILE,
               "licitacionesPerfilesContratanteCompleto3")
AGGREGATED = Dataset("es_placsp_agg", BASE_AGG, LIVE_FEED_AGG, ENTRY_FILE_AGG,
                     "PlataformasAgregadasSinMenores")
DATASETS = {d.source_code: d for d in (MAIN, AGGREGATED)}

# PLACSP publishes CODICE under the Spanish `dgpe` namespaces, not the OASIS
# UBL ones. Getting this wrong is silent: the `place-ext` lookups still match,
# so a notice parses and carries a status while every CPV code, deadline, value
# and identifier comes back empty. Verified against the live feed on
# 7 September 2026, where 405 of 405 entries parsed with zero CPV codes.
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "cbc": "urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2",
    "cac-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2",
    "cbc-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2",
}

# Older archive packages were published under the OASIS UBL namespaces, so both
# are tried before a field is called absent.
NS_FALLBACK = {
    **NS,
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}
NAMESPACE_SETS = (NS, NS_FALLBACK)


def annual_archive_url(year: int, dataset: Dataset = MAIN) -> str:
    return dataset.annual_archive_url(year)


def monthly_archive_url(year: int, month: int, dataset: Dataset = MAIN) -> str:
    return dataset.monthly_archive_url(year, month)


# ------------------------------------------------------------- XML helpers

def _find(el: ET.Element | None, path: str) -> ET.Element | None:
    """Find one element, trying each known namespace set in turn."""
    if el is None:
        return None
    for ns in NAMESPACE_SETS:
        found = el.find(path, ns)
        if found is not None:
            return found
    return None


def _text(el: ET.Element | None, path: str) -> str | None:
    found = _find(el, path)
    if found is None or found.text is None:
        return None
    val = found.text.strip()
    return val or None


def _findall_text(el: ET.Element | None, path: str) -> list[str]:
    if el is None:
        return []
    for ns in NAMESPACE_SETS:
        found = [n.text.strip() for n in el.findall(path, ns)
                 if n is not None and n.text and n.text.strip()]
        if found:
            return found
    return []


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw.strip())
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def _parse_datetime(d: str | None, t: str | None) -> datetime | None:
    """Timezone-aware deadline.

    CODICE usually states an offset on EndTime. When it does not, Spanish
    tenders are stated in Spanish local time, so Europe/Madrid is the correct
    default rather than UTC: in summer the difference is two hours, which is
    the difference between meeting a deadline and missing it.
    """
    day = _parse_date(d)
    if day is None:
        return None
    hh, mm = 23, 59
    if t:
        m = re.match(r"(\d{2}):(\d{2})", t.strip())
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
    return datetime(day.year, day.month, day.day, hh, mm,
                    tzinfo=tz_from_offset(t, d) or SPAIN_TZ)


def _float(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return float(raw.strip())
    except ValueError:
        return None


# ---------------------------------------------------------------- parsing

def parse_entry(entry: ET.Element, source_code: str = "es_placsp") -> Opportunity | None:
    """Map one ATOM entry containing a CODICE ContractFolderStatus."""
    cfs = _find(entry, ".//cac-place-ext:ContractFolderStatus")
    if cfs is None:
        # Some entries wrap the payload without the ext namespace prefix.
        for child in entry:
            if child.tag.endswith("ContractFolderStatus"):
                cfs = child
                break
    if cfs is None:
        return None

    native_id = _text(cfs, "cbc:ContractFolderID")
    if not native_id:
        native_id = _text(entry, "atom:id")
    if not native_id:
        return None

    project = _find(cfs, "cac:ProcurementProject")
    party = _find(cfs, ".//cac-place-ext:LocatedContractingParty/cac:Party")
    if party is None:
        party = _find(cfs, ".//cac:ContractingParty/cac:Party")

    buyer = (_text(party, "cac:PartyName/cbc:Name")
             or _text(entry, "atom:title")
             or "UNKNOWN")

    title = _text(project, "cbc:Name") or _text(entry, "atom:title") or ""

    cpv = _findall_text(
        project, "cac:RequiredCommodityClassification/cbc:ItemClassificationCode"
    )
    cpv = [re.sub(r"\D", "", c)[:8] for c in cpv if re.search(r"\d", c)]
    cpv = [c for c in cpv if len(c) == 8]

    amount = _float(_text(project, "cac:BudgetAmount/cbc:TotalAmount"))
    if amount is None:
        amount = _float(_text(project, "cac:BudgetAmount/cbc:TaxExclusiveAmount"))

    tender_period = _find(cfs, ".//cac:TenderSubmissionDeadlinePeriod")
    deadline = _parse_datetime(
        _text(tender_period, "cbc:EndDate"),
        _text(tender_period, "cbc:EndTime"),
    )

    published = _parse_date(_text(entry, "atom:updated"))

    link_el = _find(entry, "atom:link[@rel='alternate']")
    if link_el is None:
        link_el = _find(entry, "atom:link")
    url = link_el.get("href") if link_el is not None else None

    status_native = _text(cfs, "cbc-place-ext:ContractFolderStatusCode")

    return Opportunity(
        source_code=source_code,
        native_id=str(native_id),
        buyer_name_raw=buyer,
        title_original=title,
        country="ES",
        original_language="ES",
        procedure_type=_text(cfs, ".//cac:TenderingProcess/cbc:ProcedureCode"),
        value_amount=amount,
        value_currency="EUR" if amount is not None else None,
        published_at=published,
        deadline_at=deadline,
        cpv_codes=cpv,
        source_url=url,
        description=_text(project, "cbc:Description"),
        status=map_status(status_native),
        status_native=status_native,
    )


def parse_feed(xml_bytes: bytes, source_code: str = "es_placsp") -> tuple[list[Opportunity], str | None]:
    """Parse one ATOM file. Returns (opportunities, next_url)."""
    root = ET.fromstring(xml_bytes)
    out: list[Opportunity] = []
    for entry in root.findall("atom:entry", NS):
        try:
            opp = parse_entry(entry, source_code)
            if opp:
                out.append(opp)
        except Exception as exc:  # one bad entry must not kill the batch
            log.warning("PLACSP entry parse failed: %s", exc)

    next_url = None
    for link in root.findall("atom:link", NS):
        if link.get("rel") == "next":
            next_url = link.get("href")
            break
    return out, next_url


# --------------------------------------------------------------- fetching

def fetch_live(
    dataset: Dataset = MAIN, *, client: httpx.Client | None = None, max_pages: int = 50
) -> Iterator[Opportunity]:
    """Walk one dataset's live feed, following rel="next".

    max_pages exists because the chain reaches back to 2012. For daily
    incremental runs a handful of pages is enough; the backfill uses the
    archives instead.
    """
    owns = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT},
                                    timeout=60.0, follow_redirects=True)
    try:
        url = dataset.live_feed
        for page in range(max_pages):
            r = client.get(url)
            r.raise_for_status()
            opps, next_url = parse_feed(r.content, dataset.source_code)
            log.info("%s page %s: %s entries", dataset.source_code, page + 1, len(opps))
            yield from opps
            if not next_url:
                break
            url = next_url
    finally:
        if owns:
            client.close()


def fetch_archive(
    url: str, dataset: Dataset = MAIN, *, client: httpx.Client | None = None
) -> Iterator[Opportunity]:
    """Download and walk one annual or monthly ZIP.

    Per the spec the package must be read starting from
    licitacionesPerfilesContratanteCompleto3.atom, with each file linking on to
    the next. In practice reading every .atom member and deduplicating upstream
    is more robust than trusting the chain inside a downloaded archive.
    """
    owns = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT},
                                    timeout=300.0, follow_redirects=True)
    try:
        r = client.get(url)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            names = [n for n in zf.namelist() if n.endswith(".atom")]
            # entry file first, matching the documented reading order
            names.sort(key=lambda n: (not n.endswith(dataset.entry_file), n))
            for name in names:
                try:
                    opps, _ = parse_feed(zf.read(name), dataset.source_code)
                    yield from opps
                except Exception as exc:
                    log.warning("PLACSP archive member %s failed: %s", name, exc)
    finally:
        if owns:
            client.close()


def backfill_years(
    start: int = 2012, end: int | None = None, dataset: Dataset = MAIN
) -> Iterator[str]:
    """URLs for the historical backfill, oldest first."""
    end = end or date.today().year - 1
    for year in range(start, end + 1):
        yield dataset.annual_archive_url(year)
