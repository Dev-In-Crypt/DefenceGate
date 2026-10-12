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
from datetime import date, datetime, timezone
from typing import Iterator
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import httpx

from ..normalise import Opportunity, tz_from_offset
from . import USER_AGENT, new_client, request_with_retry

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


# CODICE SyndicationTenderingProcessCode (list 2.07) -> the procedure's Spanish name.
# Only codes that were checked are here. The publisher's syndication specification
# (v1.3, 11/02/2020, section 4.12) gives the names and its own example pairs code 3 with
# "Negociado sin publicidad"; the pairing of the other codes is the table published with
# the BquantFinance/licitaciones-espana dataset, checked against 975 live entries of
# 12 October 2026: 9 = every such entry is below the harmonised threshold, has a deadline
# and no request to participate; 4 and 13 = the only entries with a call notice and a
# request-to-participate period besides the restricted ones (13 is Aena's, under the
# utilities directive, 4 the army's, under the defence directive); 3 = 20 of 21 entries
# have no call notice at all; 100 = all six are a state railway company's own rules, 999 =
# buyers outside the usual kinds. The list file itself sits on a host this project does
# not fetch (robots.txt Disallow). Codes 5-8 and 10-12 are in the same published table
# but were seen once or not at all, so they stay as the bare code until verified.
PROCEDURE_NAMES = {
    "1": "Abierto",
    "2": "Restringido",
    "3": "Negociado sin publicidad",
    "4": "Negociado con publicidad",
    "9": "Abierto simplificado",
    "13": "Licitación con negociación",
    "100": "Normas internas",
    "999": "Otros",
}


def map_procedure(code: str | None) -> str | None:
    """The procedure's name for a verified code, else the code as the source gave it."""
    code = (code or "").strip()
    return PROCEDURE_NAMES.get(code, code) or None


# `ProcurementLegislationDocumentReference/ID` is the directive a harmonised contract
# falls under (specification section 4.41: 2014/24/UE, 2014/23/UE, 2014/25/UE,
# 2009/81/CE; "N/A" otherwise). It becomes the CELEX number every other source uses, so
# the defence-directive signal reads the same for Spain as for TED.
_DIRECTIVES = {
    "2009/81": "32009L0081",
    "2014/23": "32014L0023",
    "2014/24": "32014L0024",
    "2014/25": "32014L0025",
}
_DIRECTIVE = re.compile(r"(20\d{2})\s*/\s*(\d{1,3})")

# `ProcurementNationalLegislationCode` (list 2.08) is the national regime. It is not in
# the specification; read off 975 live entries: 3 on every ordinary contract (LCSP), 2 on
# the army economic directorate's notice that cites 2009/81. 0 and 1 were seen but their
# meaning was not verified, so they stay a code.
_NATIONAL_LAW = {
    "3": "Ley 9/2017 (LCSP)",
    "2": "Ley 24/2011 (defensa y seguridad)",
}


def map_legal_basis(directive: str | None, national_code: str | None) -> str | None:
    """CELEX number when the notice names a directive, else the national regime."""
    m = _DIRECTIVE.search(directive or "")
    if m:
        celex = _DIRECTIVES.get(f"{m.group(1)}/{int(m.group(2)):02d}")
        if celex:
            return celex
    code = (national_code or "").strip()
    if not code:
        return None
    return _NATIONAL_LAW.get(code, f"ES legislation code {code}")

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


def _findall(el: ET.Element | None, path: str) -> list[ET.Element]:
    """Every matching element, from the first namespace set that has any."""
    if el is None:
        return []
    for ns in NAMESPACE_SETS:
        found = el.findall(path, ns)
        if found:
            return found
    return []


def _amount(project: ET.Element | None) -> tuple[float | None, str | None]:
    """The contract's value and its currency.

    `EstimatedOverallContractAmount` is the portal's "valor estimado": the whole
    contract without VAT, options and extensions included. `TotalAmount` is the
    budget for the tender's year with VAT, and `TaxExclusiveAmount` the same
    without it; one real 5-year contract carries 35,470.55 against 8,583.87. Those two
    are the fallback, in the order the connector always used, for the entries that
    do not carry the estimate.
    """
    budget = _find(project, "cac:BudgetAmount")
    found: list[tuple[float | None, str | None]] = []
    for name in ("EstimatedOverallContractAmount", "TotalAmount", "TaxExclusiveAmount"):
        el = _find(budget, f"cbc:{name}")
        value = _float(el.text) if el is not None else None
        found.append((value, (el.get("currencyID") or "EUR") if el is not None else None))
    estimate = found[0]
    if estimate[0]:
        return estimate
    for value, currency in found[1:]:
        if value is not None:
            return value, currency
    return estimate


# A call for tenders is what a supplier reads as "published". Prior information
# comes before it; any other notice (award, formalisation, modification) is the
# last resort, for the entries that carry only the notices that followed a call
# published before the feed began.
_CALL_NOTICES = ("DOC_CN",)
_PRIOR_NOTICES = ("DOC_PIN", "DOC_PIN_RTL")


def _publication_date(cfs: ET.Element) -> date | None:
    """When the portal first published the notice.

    Each `ValidNoticeInfo` is one notice type with one `AdditionalPublicationStatus`
    per medium (the buyer profile hosted on PLACSP, DOUE, BOE), and the date is the
    `IssueDate` of its document reference (specification section 4.39). An amended
    notice keeps adding dates, so the earliest date of the call notice is the
    publication, and the portal's own medium wins over a gazette's date, which can be
    a day either side. The Atom `updated` time is when the entry last changed, not
    this, and is kept apart in `source_updated_at`.
    """
    rows: list[tuple[str, bool, date]] = []   # (notice type, portal's own medium, date)
    for info in _findall(cfs, "cac-place-ext:ValidNoticeInfo"):
        kind = (_text(info, "cbc-place-ext:NoticeTypeCode") or "").upper()
        issued = _parse_date(_text(info, "cbc-place-ext:NoticeIssueDate"))
        if issued:
            rows.append((kind, True, issued))
        for status in _findall(info, "cac-place-ext:AdditionalPublicationStatus"):
            medium = (_text(status, "cbc-place-ext:PublicationMediaName") or "").lower()
            for ref in _findall(status, "cac-place-ext:AdditionalPublicationDocumentReference"):
                issued = _parse_date(_text(ref, "cbc:IssueDate")
                                     or _text(ref, "cbc-place-ext:IssueDate"))
                if issued:
                    rows.append((kind, "perfil" in medium, issued))
    for kinds in (_CALL_NOTICES, _PRIOR_NOTICES, None):
        pool = [(own, d) for kind, own, d in rows if kinds is None or kind in kinds]
        if pool:
            return min([d for own, d in pool if own] or [d for _, d in pool])
    return None


_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _procedure_uuid(cfs: ET.Element) -> str | None:
    """The eForms procedure identifier (BT-04) of an entry that was also sent to TED.

    It is `<cbc:UUID schemeName="TED">` directly under the folder status: the same value
    TED publishes as `procedure-identifier`, which is what ties this notice to its TED
    twin. 571 of 1,915 live entries and 134 of the 770 defence notices of October 2026
    carry it; below-threshold ones do not. The DOUE publication entry has only an issue
    date, no number, so there is nothing else to read.
    """
    for child in cfs:
        if child.tag.endswith("}UUID") and child.get("schemeName") == "TED":
            value = (child.text or "").strip().strip("{}").strip().lower()
            return value if _UUID.fullmatch(value) else None
    return None


def _instant(stamp: str | None) -> datetime | None:
    """An `atom:updated` stamp as an aware instant, None when it is not one."""
    if not stamp:
        return None
    try:
        value = datetime.fromisoformat(stamp.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


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

    amount, currency = _amount(project)

    tender_period = _find(cfs, ".//cac:TenderSubmissionDeadlinePeriod")
    deadline = _parse_datetime(
        _text(tender_period, "cbc:EndDate"),
        _text(tender_period, "cbc:EndTime"),
    )

    # Not the Atom `updated` time: that moves with every amendment, and a notice
    # amended after its deadline then read as published after it (1,607 rows).
    published = _publication_date(cfs)

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
        procedure_type=map_procedure(_text(cfs, ".//cac:TenderingProcess/cbc:ProcedureCode")),
        legal_basis=map_legal_basis(
            _text(cfs, "cac:TenderingTerms/cac:ProcurementLegislationDocumentReference/cbc:ID"),
            _text(cfs, "cac:TenderingTerms/cbc:ProcurementNationalLegislationCode")),
        value_amount=amount,
        value_currency=currency if amount is not None else None,
        published_at=published,
        source_updated_at=_instant(_text(entry, "atom:updated")),
        deadline_at=deadline,
        cpv_codes=cpv,
        source_url=url,
        description=_text(project, "cbc:Description"),
        status=map_status(status_native),
        status_native=status_native,
        procedure_identifier=_procedure_uuid(cfs),
    )


def parse_feed(xml_bytes: bytes, source_code: str = "es_placsp",
               *, stamps: list[str] | None = None) -> tuple[list[Opportunity], str | None]:
    """Parse one ATOM file. Returns (opportunities, next_url).

    Pass `stamps` to collect each parsed entry's full `atom:updated` alongside,
    in the same order; `published_at` keeps only the date.
    """
    root = ET.fromstring(xml_bytes)
    out: list[Opportunity] = []
    for entry in root.findall("atom:entry", NS):
        try:
            opp = parse_entry(entry, source_code)
            if opp:
                out.append(opp)
                if stamps is not None:
                    stamps.append(_text(entry, "atom:updated") or "")
        except Exception as exc:  # one bad entry must not kill the batch
            log.warning("PLACSP entry parse failed: %s", exc)

    next_url = None
    for link in root.findall("atom:link", NS):
        if link.get("rel") == "next":
            next_url = link.get("href")
            break
    return out, next_url


# --------------------------------------------------------------- fetching

# Limits on what a monthly archive may hold. A real month is a few hundred members
# of at most a few megabytes.
MAX_ARCHIVE_MEMBERS = 5000
MAX_MEMBER_BYTES = 200 * 1024 * 1024


def _same_site(candidate: str, reference: str) -> bool:
    from urllib.parse import urlsplit

    a, b = urlsplit(candidate), urlsplit(reference)
    return a.scheme == "https" and bool(a.hostname) and a.hostname == b.hostname


# The feeds name themselves, and every next link, under the publisher's portal host,
# `contrataciondelestado.es`, whose robots.txt is `Disallow: /`. The same files are
# served under the syndication host the connector is configured with.
_PORTAL_HOST = "contrataciondelestado.es"


def _own_page(next_url: str, dataset: Dataset) -> str | None:
    """The address of a feed's next page on the dataset's own host, or None.

    A feed is allowed to say where its next page is, not to send the worker
    somewhere else. Links under the publisher's portal name are read from the
    syndication host instead, the path unchanged, so the walk never touches the
    portal host; any other host, or a path outside the dataset's own directory,
    is refused. Before this, the same-host check refused every link the live feed
    carries, so a run read its first page and stopped, with its floor still met.
    """
    from urllib.parse import urlsplit, urlunsplit

    link, own = urlsplit(next_url), urlsplit(dataset.live_feed)
    if link.scheme != "https" or link.hostname not in (own.hostname, _PORTAL_HOST):
        return None
    if not link.path.startswith(own.path.rsplit("/", 1)[0] + "/"):
        return None
    page = urlunsplit(("https", own.netloc, link.path, link.query, ""))
    return page if _same_site(page, dataset.live_feed) else None


def _oldest(stamps: list[str]) -> datetime | None:
    """The oldest stamp that is one; a page with none says nothing about its age."""
    parsed = [_instant(s) for s in stamps]
    return min((p for p in parsed if p is not None), default=None)


def fetch_live(
    dataset: Dataset = MAIN, *, client: httpx.Client | None = None, max_pages: int = 50,
    observe: dict | None = None,
) -> Iterator[Opportunity]:
    """Walk one dataset's live feed, following rel="next".

    max_pages exists because the chain reaches back to 2012. For daily
    incremental runs a handful of pages is enough; the backfill uses the
    archives instead.

    `observe` is both ways. In: `observe["until"]`, the newest entry the previous
    complete run saw, and `observe["hard_cap"]`, the most pages the walk may take.
    With `until` the walk goes past `max_pages` until a page's oldest entry is no
    newer than it, because a provider that froze for days and then published a
    burst (8,272 entries on 9 October 2026, 17 pages) left the oldest of them beyond
    a fixed page count, unread and unnoticed. Out: `observe["newest"]`, the newest
    entry's timestamp, set before the first record is handed on; `["entries"]`;
    `["pages"]`; `["capped"]`, True when the hard cap ended a walk that had not
    yet reached `until`; and `["refused"]`, the link a walk stopped at because it
    left the feed's own directory. Both are gaps the caller has to report.
    """
    owns = client is None
    client = client or new_client(headers={"User-Agent": USER_AGENT},
                                    timeout=60.0, follow_redirects=True)
    walked: list[tuple[str, Opportunity]] = []
    until = (observe or {}).get("until")
    limit = max(max_pages, (observe or {}).get("hard_cap") or 0)
    pages = 0
    capped = False
    refused: str | None = None
    try:
        url = dataset.live_feed
        while True:
            def fetch(target: str = url) -> httpx.Response:
                response = client.get(target)
                response.raise_for_status()
                return response

            r = request_with_retry(fetch, what=f"{dataset.source_code} page {pages + 1}")
            stamps: list[str] = []
            opps, next_url = parse_feed(r.content, dataset.source_code, stamps=stamps)
            pages += 1
            log.info("%s page %s: %s entries", dataset.source_code, pages, len(opps))
            walked.extend(zip(stamps, opps, strict=True))
            if not next_url:
                break
            oldest = _oldest(stamps)
            if pages >= max_pages and (until is None or (oldest is not None and oldest <= until)):
                break
            if pages >= limit:
                capped = until is not None
                log.warning("%s: walk stopped at the cap of %s pages without reaching %s",
                            dataset.source_code, limit, until)
                break
            page_url = _own_page(next_url, dataset)
            if page_url is None:
                refused = next_url[:120]
                log.warning("%s: refusing a next link outside the feed's own directory: %s",
                            dataset.source_code, refused)
                break
            url = page_url
    finally:
        if owns:
            client.close()
    if observe is not None:
        observe["pages"] = pages
        observe["capped"] = capped
        observe["refused"] = refused

    # The chain is served newest first, and one tender appears once per
    # modification. Handed on in that order, a run archived a notice's award
    # and then its earlier call for tenders as though the call came after.
    # Sorting by the source's own full timestamp makes arrival order the order
    # things happened in. It costs holding one run's entries in memory, a few
    # tens of megabytes, and the first record is only handed on once the walk
    # has finished.
    yield from _in_source_order(walked, observe)


def _in_source_order(walked: list[tuple[str, Opportunity]],
                     observe: dict | None) -> Iterator[Opportunity]:
    walked.sort(key=lambda pair: _updated_key(pair[0]))
    if observe is not None:
        observe["newest"] = _updated_key(walked[-1][0]) if walked else None
        observe["entries"] = len(walked)
    for _, opp in walked:
        yield opp


def _updated_key(stamp: str) -> datetime:
    """`atom:updated` as a comparable instant; unparseable sorts first."""
    try:
        value = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def fetch_archive(
    url: str, dataset: Dataset = MAIN, *, client: httpx.Client | None = None,
    observe: dict | None = None, since: datetime | None = None,
) -> Iterator[Opportunity]:
    """Download and walk one annual or monthly ZIP.

    Per the spec the package must be read starting from
    licitacionesPerfilesContratanteCompleto3.atom, with each file linking on to
    the next. In practice reading every .atom member and deduplicating upstream
    is more robust than trusting the chain inside a downloaded archive.
    """
    owns = client is None
    client = client or new_client(headers={"User-Agent": USER_AGENT},
                                    timeout=300.0, follow_redirects=True)
    try:
        def fetch() -> httpx.Response:
            response = client.get(url)
            response.raise_for_status()
            return response

        r = request_with_retry(fetch, what=f"archive {url[-12:]}")
        walked: list[tuple[str, Opportunity]] = []
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            names = [n for n in zf.namelist() if n.endswith(".atom")]
            if len(names) > MAX_ARCHIVE_MEMBERS:
                raise RuntimeError(f"{dataset.source_code}: archive has {len(names)} members")
            for name in names:
                if zf.getinfo(name).file_size > MAX_MEMBER_BYTES:
                    log.warning("PLACSP archive member %s is too large; skipped", name)
                    continue
                try:
                    stamps: list[str] = []
                    opps, _ = parse_feed(zf.read(name), dataset.source_code, stamps=stamps)
                    walked.extend(zip(stamps, opps, strict=True))
                except Exception as exc:
                    log.warning("PLACSP archive member %s failed: %s", name, exc)
        log.info("%s archive %s: %s entries", dataset.source_code, url.rsplit("/", 1)[-1],
                 len(walked))
        if since is not None:
            # The publisher's monthly archives are assembled by a filename
            # match, and the match is loose: both the August and September 2026
            # files carry licitacionesPerfilesContratanteCompleto3_20210930_202609,
            # whose time of day, 20:26:09, contains "202609". That is 1,430
            # entries from September 2021 in every recent archive, and ingesting
            # one put 64 five-year-old notices into the archive as new.
            kept = [pair for pair in walked if _updated_key(pair[0]) >= since]
            if len(kept) != len(walked):
                log.warning("%s archive %s: dropped %s entries updated before %s",
                            dataset.source_code, url.rsplit("/", 1)[-1],
                            len(walked) - len(kept), since.date())
            walked = kept
    finally:
        if owns:
            client.close()
    # Same reason as the live walk: an archive is the same chain, newest first,
    # and read in file order it re-archives history as change.
    yield from _in_source_order(walked, observe)


def backfill_years(
    start: int = 2012, end: int | None = None, dataset: Dataset = MAIN
) -> Iterator[str]:
    """URLs for the historical backfill, oldest first."""
    end = end or date.today().year - 1
    for year in range(start, end + 1):
        yield dataset.annual_archive_url(year)
