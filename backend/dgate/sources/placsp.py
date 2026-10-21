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

import logging
import pickle
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterator
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import httpx

from ..normalise import PLACEHOLDER_AMOUNT_MAX, Opportunity, tz_from_offset
from . import USER_AGENT, ResponseTooLarge, new_client, request_with_retry

SPAIN_TZ = ZoneInfo("Europe/Madrid")

# CODICE ContractFolderStatusCode -> our normalised lifecycle value.
# Source: especificacion-sindicacion.pdf, code list ContractFolderStatusCode.
# Anything unmapped becomes "unknown" rather than silently "open": an unknown
# code must be visible, not disguised as an open tender.
STATUS_MAP = {
    "PRE": "forthcoming",  # anuncio previo: a prior-information notice, not a call
    "PUB": "open",       # publicada
    "EV": "open",        # en evaluacion, still live for the archive timeline
    "ADJ": "awarded",    # adjudicada
    "RES": "awarded",    # resuelta / formalizada
    "ANUL": "cancelled",  # anulada
    "DES": "cancelled",  # desierta
}


def map_status(code: str | None) -> str:
    if not code:
        return "unknown"        # an entry that states no status is not a call we can act on
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
    are the fallback for the entries that do not carry the estimate, the one without VAT
    first: the connector read `TotalAmount` first until 14 October 2026, and 25 of 103
    September 2026 twin pairs held exactly 1.21 times the TED value (data-correctness DC1).
    """
    budget = _find(project, "cac:BudgetAmount")
    found: list[tuple[float | None, str | None]] = []
    for name in ("EstimatedOverallContractAmount", "TaxExclusiveAmount", "TotalAmount"):
        el = _find(budget, f"cbc:{name}")
        value = _float(el.text) if el is not None else None
        found.append((value, (el.get("currencyID") or "EUR") if el is not None else None))
    # A budget of 0.00 states nothing (45 stored entries): the next figure is used, and
    # when there is none the entry has no value, not a value of zero.
    for value, currency in found:
        if value is not None and value > PLACEHOLDER_AMOUNT_MAX:
            return value, currency
    return None, None


# A call for tenders is what a supplier reads as "published". Prior information
# comes before it. Any other notice (award, formalisation, modification) is not the
# tender's publication: an entry that carries only those is a call published before the
# feed began, and the date of its award is not when it was published (288 of 1,349 entries
# read again on 13 October 2026 were "published" after their deadline). Its publication
# date is not stated, and is left empty.
_CALL_NOTICES = ("DOC_CN",)
_PRIOR_NOTICES = ("DOC_PIN", "DOC_PIN_RTL")


def _notice_rows(cfs: ET.Element) -> list[tuple[str, bool, date]]:
    """(notice type, portal's own medium, date) for every date a ValidNoticeInfo states."""
    rows: list[tuple[str, bool, date]] = []
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
    return rows


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
    rows = _notice_rows(cfs)
    for kinds in (_CALL_NOTICES, _PRIOR_NOTICES):
        pool = [(own, d) for kind, own, d in rows if kind in kinds]
        if pool:
            return min([d for own, d in pool if own] or [d for _, d in pool])
    return None


# What a notice is, as the site labels it. Not a publication date: an award or a
# cancellation is dated and named, never presented as the tender's publication.
NOTICE_KINDS = ("call", "prior", "award", "formalisation", "cancellation", "update")
_KIND_OF_STATUS = {"PUB": "call", "PRE": "prior", "ADJ": "award", "RES": "award",
                   "ANUL": "cancellation", "EV": "update"}


def notice_kind_of_status(status_native: str | None) -> str:
    return _KIND_OF_STATUS.get((status_native or "").upper(), "update")


def _kind_of_notice_type(code: str) -> str:
    if code in _CALL_NOTICES:
        return "call"
    if code in _PRIOR_NOTICES:
        return "prior"
    if "ANUL" in code or "DESIST" in code or "RENUNC" in code:
        return "cancellation"
    if "ADJ" in code:
        return "award"
    if "FORM" in code:
        return "formalisation"
    return "update"


def _own_notice(cfs: ET.Element, status_native: str | None,
                updated: datetime | None) -> tuple[date | None, str | None]:
    """The date and kind of the notice this entry was written for.

    The entry lists every notice of its folder so far, so its own is the newest of them.
    Where it lists none the date is the day of its update stamp and the kind is read from
    the folder's status code. Dated by the entry itself, never a publication date.
    """
    rows = _notice_rows(cfs)
    if rows:
        newest = max(d for _, _, d in rows)
        kinds = sorted({k for k, _, d in rows if d == newest})
        # Several notices on one day: the one the status code names, else the last listed.
        named = notice_kind_of_status(status_native)
        kind = next((_kind_of_notice_type(k) for k in kinds
                     if _kind_of_notice_type(k) == named), _kind_of_notice_type(kinds[-1]))
        return newest, kind
    if updated is not None:
        return updated.date(), notice_kind_of_status(status_native)
    return None, None


# `cac:TenderResult/cbc:ResultCode` of a folder in `ADJ` or `RES`. Read off the live feed of
# 13 October 2026 (350 entries, 683 results): 8 and 9 (the best offer, the formalised
# contract) all name a winning party; 3 never does and states "se declara desierto" /
# "inexistencia de ofertas" (87 of 87), and 4 is the withdrawal of the buyer, in every case
# with a DESISTIMIENTO notice and no winning party (3 of 3). A folder whose every result is
# one of those awarded nothing, which TED states as `clos-nw` and the mapper maps to
# `cancelled`. A folder with any other result, or none, stays awarded.
_NO_AWARD_RESULT_CODES = frozenset({"3", "4"})


def _no_winner(cfs: ET.Element) -> bool:
    codes = [(_text(t, "cbc:ResultCode") or "") for t in _findall(cfs, "cac:TenderResult")]
    return bool(codes) and all(c in _NO_AWARD_RESULT_CODES for c in codes)


def _int(raw: str | None) -> int | None:
    try:
        return int(float(raw)) if raw else None
    except ValueError:
        return None


def parse_results(cfs: ET.Element) -> list[dict]:
    """The award results of a folder, one per `cac:TenderResult` (in practice one per lot), as stated.

    Read into a payload of their own and never into the `Opportunity`: every PLACSP content hash is
    taken over `opportunity_payload`, so an award field there would move the hash of every held
    record and archive about 30,000 false "changed" versions. Paths measured on the live feed of
    20 October 2026 (85 results): `WinningParty` with `PartyIdentification/ID` (`schemeName` NIF or
    OTROS; a natural person's NIF arrives masked by the publisher, "***1234**"), `PartyName/Name`
    and `PhysicalLocation/Address/Country/IdentificationCode`. The result's free-text `Description`,
    the winner's street, city and postcode are not read: nothing here needs them, and a sole
    trader's address is personal data. What is returned still holds persons' names and numbers;
    `dgate.placsp_awards.redact` blanks them before anything is landed.
    """
    out: list[dict] = []
    for tr in _findall(cfs, "cac:TenderResult"):
        project = _find(tr, "cac:AwardedTenderedProject")
        total = _find(project, "cac:LegalMonetaryTotal")
        net = _find(total, "cbc:TaxExclusiveAmount")
        winners = []
        for party in _findall(tr, "cac:WinningParty"):
            ident = _find(party, "cac:PartyIdentification/cbc:ID")
            winners.append({
                "name": _text(party, "cac:PartyName/cbc:Name"),
                "identifier": (ident.text or "").strip() or None if ident is not None else None,
                "scheme": ident.get("schemeName") if ident is not None else None,
                "country": _text(party, "cac:PhysicalLocation/cac:Address/cac:Country/cbc:IdentificationCode"),
            })
        out.append({
            "result_code": _text(tr, "cbc:ResultCode"),
            "lot_id": _text(project, "cbc:ProcurementProjectLotID"),
            "award_date": _text(tr, "cbc:AwardDate"),
            "received_tenders": _int(_text(tr, "cbc:ReceivedTenderQuantity")),
            "sme_awarded": _text(tr, "cbc:SMEAwardedIndicator"),
            "owner_nationality": _text(tr, "cbc:AwardedOwnerNationalityCode"),
            "value": _float(net.text) if net is not None else None,
            "value_with_vat": _float(_text(total, "cbc:PayableAmount")),
            "currency": (net.get("currencyID") or "EUR") if net is not None and net.text else None,
            "winners": winners,
        })
    return out


def award_payload(entry: ET.Element, source_code: str = "es_placsp") -> dict | None:
    """The award results of one entry with what places them (folder, status, update stamp), or None
    when the entry states no result. Personal data is still in it: see `parse_results`."""
    cfs = _folder(entry)
    if cfs is None:
        return None
    results = parse_results(cfs)
    if not results:
        return None
    return {"source": source_code, "folder_id": _text(cfs, "cbc:ContractFolderID"),
            "status_native": _text(cfs, "cbc-place-ext:ContractFolderStatusCode"),
            "updated": _text(entry, "atom:updated"), "results": results}


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

def _folder(entry: ET.Element) -> ET.Element | None:
    cfs = _find(entry, ".//cac-place-ext:ContractFolderStatus")
    if cfs is None:
        # Some entries wrap the payload without the ext namespace prefix.
        for child in entry:
            if child.tag.endswith("ContractFolderStatus"):
                return child
    return cfs


def parse_entry(entry: ET.Element, source_code: str = "es_placsp") -> Opportunity | None:
    """Map one ATOM entry containing a CODICE ContractFolderStatus."""
    cfs = _folder(entry)
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
    updated = _instant(_text(entry, "atom:updated"))
    notice_date, notice_kind = _own_notice(cfs, status_native, updated)
    status = map_status(status_native)
    if status == "awarded" and _no_winner(cfs):
        status = "cancelled"
    # A folder that lists no lot is a single contract and says nothing: None, not 1.
    lots = len(_findall(cfs, "cac:ProcurementProjectLot")) or None

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
        source_updated_at=updated,
        notice_date=notice_date,
        notice_kind=notice_kind,
        deadline_at=deadline,
        cpv_codes=cpv,
        source_url=url,
        description=_text(project, "cbc:Description"),
        status=status,
        status_native=status_native,
        procedure_identifier=_procedure_uuid(cfs),
        lot_count=lots,
    )


def parse_feed(xml_bytes: bytes, source_code: str = "es_placsp",
               *, stamps: list[str] | None = None,
               results: list[dict | None] | None = None,
               counts: dict | None = None) -> tuple[list[Opportunity], str | None]:
    """Parse one ATOM file. Returns (opportunities, next_url).

    Pass `stamps` to collect each parsed entry's full `atom:updated` alongside,
    in the same order; `published_at` keeps only the date. Pass `results` to collect
    each parsed entry's award payload (`award_payload`, None for an entry without one)
    the same way. Pass `counts` to have `counts["entries_failed"]` raised by each entry
    that could not be parsed (WP-71, QA M7: they were dropped with a log line only).
    """
    root = ET.fromstring(xml_bytes)
    out: list[Opportunity] = []
    for entry in root.findall("atom:entry", NS):
        try:
            opp = parse_entry(entry, source_code)
            if opp:
                award = award_payload(entry, source_code) if results is not None else None
                out.append(opp)
                if stamps is not None:
                    stamps.append(_text(entry, "atom:updated") or "")
                if results is not None:
                    results.append(award)
        except Exception as exc:  # one bad entry must not kill the batch
            log.warning("PLACSP entry parse failed (quarantined): %s", exc)
            if counts is not None:
                counts["entries_failed"] = counts.get("entries_failed", 0) + 1

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
    observe: dict | None = None, with_results: bool = False,
) -> Iterator[Any]:
    """Walk one dataset's live feed, following rel="next".

    With `with_results` each item is `(opportunity, award payload or None)`, as from `fetch_archive`
    (WP-61: the nightly walk collects the award results with the archive loader's code path).

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
    walked: list[tuple[str, Any]] = []
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
            found: list[dict | None] | None = [] if with_results else None
            opps, next_url = parse_feed(r.content, dataset.source_code, stamps=stamps, results=found,
                                        counts=observe)
            pages += 1
            log.info("%s page %s: %s entries", dataset.source_code, pages, len(opps))
            walked.extend(zip(stamps, list(zip(opps, found, strict=True)) if found is not None else opps,
                              strict=True))
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


def _in_source_order(walked: list[tuple[str, Any]],
                     observe: dict | None) -> Iterator[Any]:
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


# What a monthly archive may weigh on disk. The largest so far (September 2026) is a few
# hundred MiB; past this it is not an archive of PLACSP.
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024


class DiskLow(RuntimeError):
    """Free space on the temporary directory's disk fell under the floor a caller set."""


def check_disk(min_free_bytes: int | None, what: str) -> None:
    if min_free_bytes is None:
        return
    free = shutil.disk_usage(tempfile.gettempdir()).free
    if free < min_free_bytes:
        raise DiskLow(f"{what}: {free / 2**30:.2f} GiB free, under the floor of "
                      f"{min_free_bytes / 2**30:.2f} GiB")


def _download(client: httpx.Client, url: str, what: str, min_free_bytes: int | None = None):
    """The response body of `url` in an anonymous temporary file, rewound.

    Counted as it arrives (decoded), so a body that passes MAX_ARCHIVE_BYTES is cut off
    and the file is closed -- and with it removed -- rather than filling the disk. With
    `min_free_bytes` the free space is checked every 64 MiB as well, and the download
    stops the same way (`DiskLow`) when it falls under that floor.
    Retried like every other request; each attempt starts a new file.
    """
    def fetch():
        out = tempfile.TemporaryFile(prefix="placsp-archive-")
        try:
            total = 0
            with client.stream("GET", url) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_ARCHIVE_BYTES:
                        raise ResponseTooLarge(
                            f"{what}: body passed {MAX_ARCHIVE_BYTES} bytes")
                    if total % (64 * 1024 * 1024) < len(chunk):
                        check_disk(min_free_bytes, what)
                    out.write(chunk)
            out.seek(0)
            return out
        except BaseException:
            out.close()
            raise

    return request_with_retry(fetch, what=what)


def fetch_archive(
    url: str, dataset: Dataset = MAIN, *, client: httpx.Client | None = None,
    observe: dict | None = None, since: datetime | None = None,
    with_results: bool = False, min_free_bytes: int | None = None,
) -> Iterator[Any]:
    """Download and walk one annual or monthly ZIP.

    Per the spec the package must be read starting from
    licitacionesPerfilesContratanteCompleto3.atom, with each file linking on to
    the next. In practice reading every .atom member and deduplicating upstream
    is more robust than trusting the chain inside a downloaded archive.

    With `with_results` each item is `(opportunity, award payload or None)`: the award
    results travel next to the record, never inside it (see `parse_results`).
    `min_free_bytes` stops the walk with `DiskLow` before the disk under the temporary
    files falls below it (checked while downloading and while spooling).
    """
    owns = client is None
    # Plain httpx, not `new_client`: its response hook reads the body into memory under the
    # global ceiling, and an archive is streamed to disk under its own (MAX_ARCHIVE_BYTES).
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT},
                                    timeout=300.0, follow_redirects=True)
    # The parsed entries are spooled to a second temporary file and only (stamp, offset)
    # is kept in memory: a month is a few hundred thousand entries, each with its text,
    # and holding them all to sort them was most of a 2 GiB worker for the September 2026
    # archive. Both files are this function's own and go with it.
    spool = tempfile.TemporaryFile(prefix="placsp-entries-")
    index: list[tuple[datetime, int]] = []
    dropped = 0
    # What could not be read is counted, not only logged (QA M7): a unit with any of it is not
    # complete, and the caller must not mark it done.
    lost: dict = {"entries_failed": 0, "members_skipped": 0}
    name_tail = url.rsplit("/", 1)[-1]
    try:
        with _download(client, url, f"archive {url[-12:]}", min_free_bytes) as archive, \
                zipfile.ZipFile(archive) as zf:
            names = [n for n in zf.namelist() if n.endswith(".atom")]
            if len(names) > MAX_ARCHIVE_MEMBERS:
                raise RuntimeError(f"{dataset.source_code}: archive has {len(names)} members")
            for name in names:
                if zf.getinfo(name).file_size > MAX_MEMBER_BYTES:
                    log.warning("PLACSP archive member %s is too large; skipped", name)
                    lost["members_skipped"] += 1
                    continue
                try:
                    stamps: list[str] = []
                    found: list[dict | None] | None = [] if with_results else None
                    opps, _ = parse_feed(zf.read(name), dataset.source_code, stamps=stamps,
                                         results=found, counts=lost)
                except Exception as exc:
                    log.warning("PLACSP archive member %s failed: %s", name, exc)
                    lost["members_skipped"] += 1
                    continue
                check_disk(min_free_bytes, f"archive {name_tail}")
                awards = found if found is not None else [None] * len(opps)
                for stamp, opp, award in zip(stamps, opps, awards, strict=True):
                    key = _updated_key(stamp)
                    # The publisher's monthly archives are assembled by a filename
                    # match, and the match is loose: both the August and September 2026
                    # files carry licitacionesPerfilesContratanteCompleto3_20210930_202609,
                    # whose time of day, 20:26:09, contains "202609". That is 1,430
                    # entries from September 2021 in every recent archive, and ingesting
                    # one put 64 five-year-old notices into the archive as new.
                    if since is not None and key < since:
                        dropped += 1
                        continue
                    index.append((key, spool.tell()))
                    pickle.dump((opp, award) if with_results else opp, spool,
                                protocol=pickle.HIGHEST_PROTOCOL)
        log.info("%s archive %s: %s entries", dataset.source_code, name_tail,
                 len(index) + dropped)
        if dropped:
            log.warning("%s archive %s: dropped %s entries updated before %s",
                        dataset.source_code, name_tail, dropped,
                        since.date() if since else None)
        if lost["entries_failed"] or lost["members_skipped"]:
            log.warning("%s archive %s: %s entries could not be parsed, %s members skipped",
                        dataset.source_code, name_tail, lost["entries_failed"], lost["members_skipped"])
    except BaseException:
        spool.close()
        raise
    finally:
        if owns:
            client.close()
    # Same reason as the live walk: an archive is the same chain, newest first,
    # and read in file order it re-archives history as change. The sort is stable, so
    # entries of one instant keep the order they were read in.
    index.sort(key=lambda pair: pair[0])
    if observe is not None:
        observe["newest"] = index[-1][0] if index else None
        observe["entries"] = len(index)
        observe.update(lost)
    try:
        for _, offset in index:
            spool.seek(offset)
            yield pickle.load(spool)        # noqa: S301 - our own temporary file
    finally:
        spool.close()


def backfill_years(
    start: int = 2012, end: int | None = None, dataset: Dataset = MAIN
) -> Iterator[str]:
    """URLs for the historical backfill, oldest first."""
    end = end or date.today().year - 1
    for year in range(start, end + 1):
        yield dataset.annual_archive_url(year)
