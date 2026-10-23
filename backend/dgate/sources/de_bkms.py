"""Germany: the national notice service (Bekanntmachungsservice, BKMS) day files.

Endpoint:  GET https://oeffentlichevergabe.de/api/notice-exports?pubDay=YYYY-MM-DD&format=eforms.zip
Auth:      none
Operator:  Beschaffungsamt des BMI (BeschA), Datenservice Oeffentlicher Einkauf
Licence:   NOT VERIFIED. The interface is open; the licence text could not be read. The
           source row is seeded inactive and with `commercial_ok` NULL (migration 0050)
           until the owner has the answer; see docs/sources/de_national.md and
           docs/legal/OPEN_ITEMS_FOR_LAWYER.md.

What a day file is: one zip with one eForms UBL XML per notice version, named
`<notice-id>-<version>.xml`, the same schema as TED. 500 to 1,050 files, 3 to 5 MB. The
file of a day is regenerated, so it also holds late arrivals and new versions; the
connector is idempotent over it (the pipeline hashes content).

Three properties decided the design, each measured on 13 October 2026.

1. **Not every file is eForms.** 1,035 files that day; legacy national forms (SDK 0.1)
   have a numeric id, an empty `ContractFolderID`, and no organisation block. The record
   keeps the file as it came and the mapper copes with both.
2. **The files carry personal data**: `cac:Contact` of buyers, winners and service
   providers (name, telephone, e-mail), ultimate beneficial owners, jury members. The
   boundary is `normalise.strip_personal_data`, which takes an XML record apart before it
   is landed; nothing here keeps a contact.
3. **A zip is untrusted input.** The download is streamed to a temporary file under a byte
   ceiling, entries are read one at a time under their own ceiling, and the total
   uncompressed size is bounded, so a day cannot take the worker's memory.
"""

from __future__ import annotations

import logging
import re
import tempfile
import time
import zipfile
from contextlib import AbstractContextManager
from datetime import date, timedelta
from typing import Any, Iterator
from xml.etree import ElementTree as ET

import httpx

from . import USER_AGENT, RateLimited, retry_after

log = logging.getLogger(__name__)

SOURCE_CODE = "de_bkms"
EXPORT_URL = "https://oeffentlichevergabe.de/api/notice-exports"
HISTORY_FROM = date(2023, 10, 25)      # before this the files are not eForms
REQUEST_PAUSE = 1.0

MAX_ZIP_BYTES = 64 * 1024 * 1024        # measured days: 3 to 5 MB
MAX_ENTRY_BYTES = 8 * 1024 * 1024       # largest seen: 0.7 MB
MAX_TOTAL_BYTES = 400 * 1024 * 1024     # measured days: 27 MB unpacked
MAX_ENTRIES = 20_000

# WP-96: the notice's page in the service's own search, by its eForms notice id (a UUID). The legacy national forms
# have a numeric id and no such page. ponytail: the address form is the service's UI as of October 2026, not read from
# a fetched page (no portal is called from the laptop); one constant to change if it moves.
NOTICE_PAGE = "https://oeffentlichevergabe.de/ui/de/search/details?noticeId={notice_id}"
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def notice_page(notice_id: str | None) -> str | None:
    """The notice's page on oeffentlichevergabe.de, or None for an id that is not an eForms notice id."""
    return NOTICE_PAGE.format(notice_id=notice_id.lower()) if notice_id and _UUID.match(notice_id) else None


_NAME = re.compile(r"^(?P<id>[0-9A-Za-z-]{1,64}?)-(?P<version>\d{1,4})\.xml$")
_UNSAFE_MARKUP = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


def split_name(name: str) -> tuple[str, str] | None:
    """`<notice-id>-<version>.xml` -> (notice id, version), or None for any other name."""
    m = _NAME.match(name.rsplit("/", 1)[-1])
    return (m.group("id"), m.group("version")) if m else None


class DayFile(AbstractContextManager):
    """One downloaded day: `entries` is the zip's own count, `records()` its notices."""

    def __init__(self, day: date, tmp, archive: zipfile.ZipFile, infos: list[zipfile.ZipInfo]):
        self.day, self._tmp, self._zip, self._infos = day, tmp, archive, infos
        self.entries = len(infos)

    def records(self) -> Iterator[dict[str, Any]]:
        """One record per XML entry, in name order, so a notice's versions arrive in order.

        An entry that cannot be used is still a record, with `unreadable` saying why and no
        `xml`: it is landed and counted, and never silently dropped.
        """
        total = 0
        for info in self._infos:
            parts = split_name(info.filename)
            base = {"file": info.filename.rsplit("/", 1)[-1],
                    "notice_id": parts[0] if parts else None,
                    "version": parts[1] if parts else None}
            total += info.file_size
            if info.file_size > MAX_ENTRY_BYTES or total > MAX_TOTAL_BYTES:
                yield {**base, "unreadable": f"entry too large ({info.file_size} bytes)"}
                continue
            with self._zip.open(info) as fh:
                data = fh.read(MAX_ENTRY_BYTES + 1)
            if len(data) > MAX_ENTRY_BYTES:
                yield {**base, "unreadable": "entry larger than its stated size"}
            elif _UNSAFE_MARKUP.search(data):
                yield {**base, "unreadable": "document type declaration refused"}
            else:
                try:
                    yield {**base, "xml": data.decode("utf-8")}
                except UnicodeDecodeError:
                    yield {**base, "unreadable": "not UTF-8"}

    def __exit__(self, *exc) -> None:
        self._zip.close()
        self._tmp.close()


def _client() -> httpx.Client:
    # Not `new_client`: its body hook reads the whole response into memory, and a day is
    # streamed to disk here instead.
    return httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True,
                        timeout=httpx.Timeout(60.0, read=120.0))


def open_day(day: date, *, client: httpx.Client, attempts: int = 4) -> DayFile | None:
    """Download one publication day. None when the source has no file for it yet (404).

    A rate refusal raises `RateLimited` after the retry ladder; any other failure raises.
    """
    params = {"pubDay": day.isoformat(), "format": "eforms.zip"}
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        tmp = tempfile.TemporaryFile()
        try:
            with client.stream("GET", EXPORT_URL, params=params) as response:
                # The service answers 400 for today's day (and 404 for a day it has none for):
                # neither is a failure, the file simply is not there yet (16 Oct 2026).
                if response.status_code == 404 or (response.status_code == 400
                                                   and day >= date.today()):
                    tmp.close()
                    return None
                if response.status_code in (429, 403):
                    raise RateLimited(f"{SOURCE_CODE} {day}: HTTP {response.status_code}",
                                      retry_after(response))
                response.raise_for_status()
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_ZIP_BYTES:
                        raise RuntimeError(f"{SOURCE_CODE} {day}: day file passed "
                                           f"{MAX_ZIP_BYTES} bytes")
                    tmp.write(chunk)
            tmp.seek(0)
            try:
                archive = zipfile.ZipFile(tmp)
            except zipfile.BadZipFile as exc:
                raise ValueError(f"{SOURCE_CODE} {day}: not a zip file") from exc
            infos = sorted((i for i in archive.infolist() if i.filename.lower().endswith(".xml")),
                           key=lambda i: i.filename)
            if len(infos) > MAX_ENTRIES:
                raise RuntimeError(f"{SOURCE_CODE} {day}: {len(infos)} entries")
            return DayFile(day, tmp, archive, infos)
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            tmp.close()
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                raise
            last = exc
            if attempt < attempts:
                delay = min(60.0, 2.0 * 2 ** (attempt - 1))
                log.warning("%s %s failed (%s), attempt %s of %s, retrying in %.0fs",
                            SOURCE_CODE, day, type(exc).__name__, attempt, attempts, delay)
                time.sleep(delay)
        except BaseException:
            tmp.close()
            raise
    assert last is not None
    raise last


def window_days(days_back: int = 2, today: date | None = None) -> list[date]:
    """Oldest first: a notice's versions must be seen in the order they were issued."""
    today = today or date.today()
    return [today - timedelta(days=n) for n in range(days_back, -1, -1)]


def fetch_day(day: date, *, client: httpx.Client | None = None) -> Iterator[dict[str, Any]]:
    """Every notice file of one day (the history loader's shape). A missing day is an error:
    marking it done would leave a hole nobody sees."""
    owns = client is None
    client = client or _client()
    try:
        opened = open_day(day, client=client)
        if opened is None:
            raise RuntimeError(f"{SOURCE_CODE}: no file for {day}")
        with opened as df:
            yield from df.records()
        time.sleep(REQUEST_PAUSE)
    finally:
        if owns:
            client.close()


# ------------------------------------------------------------------ parsing
#
# The XML is read into the field names TED's own search API uses, so the one TED mapper
# (`normalise.from_ted`: status rules, value rules, deadline, lots) is the mapper for
# Germany too. Matching is by local name because the prefixes vary between files (`cbc` in
# one, `ns3` in the next).

def _ln(el: ET.Element) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _kids(el: ET.Element, *names: str) -> list[ET.Element]:
    return [c for c in el if _ln(c) in names]


def _walk(el: ET.Element, *names: str) -> list[ET.Element]:
    """Elements below `el` (el excluded) whose local name is one of `names`."""
    return [c for c in el.iter() if c is not el and _ln(c) in names]


def _path(el: ET.Element | None, *names: str) -> list[ET.Element]:
    cur = [el] if el is not None else []
    for name in names:
        cur = [c for e in cur for c in _kids(e, name)]
    return cur


def _t(el: ET.Element | None) -> str | None:
    text = (el.text or "").strip() if el is not None else ""
    return text or None


def _first_text(els: list[ET.Element]) -> str | None:
    for e in els:
        if _t(e):
            return _t(e)
    return None


def _amount(el: ET.Element | None) -> tuple[str | None, str | None]:
    return (_t(el), el.get("currencyID")) if el is not None else (None, None)


def parse(xml: str) -> ET.Element:
    if _UNSAFE_MARKUP.search(xml.encode("utf-8", "replace")):
        raise ValueError("document type declaration refused")
    return ET.fromstring(xml)


def ted_fields(xml: str) -> dict[str, Any]:
    """The notice as a TED-shaped field dict, plus `_notice_id`, `_folder_id`, `_ted_ref`."""
    root = parse(xml)
    out: dict[str, Any] = {}

    notice_id = _first_text([c for c in _kids(root, "ID") if c.get("schemeName") in (None, "notice-id")])
    folder = _first_text(_kids(root, "ContractFolderID"))
    out["_notice_id"] = notice_id
    out["_folder_id"] = folder.lower() if folder else None
    out["notice-identifier"] = notice_id
    out["notice-version"] = _first_text(_kids(root, "VersionID"))
    out["notice-type"] = _first_text(_kids(root, "NoticeTypeCode"))
    out["legal-basis"] = _first_text(_kids(root, "RegulatoryDomain"))
    lang = (_first_text(_kids(root, "NoticeLanguageCode")) or "DEU").lower()
    out["official-language"] = lang
    out["dispatch-date"] = _first_text(_kids(root, "IssueDate"))
    out["procedure-identifier"] = out["_folder_id"]
    out["procedure-type"] = _first_text(_path(root, "TenderingProcess", "ProcedureCode"))
    out["notice-subtype"] = _first_text(_walk(root, "SubTypeCode"))

    pubs = _walk(root, "Publication")
    out["publication-date"] = _first_text([c for p in pubs for c in _kids(p, "PublicationDate")])
    out["_ted_ref"] = _first_text([c for p in pubs for c in _kids(p, "NoticePublicationID")
                                   if c.get("schemeName") == "ojs-notice-id"])

    # Buyer: the organisation the contracting party points at, else the party's own name.
    party = _path(root, "ContractingParty", "Party")
    buyer_ref = _first_text(_path(party[0], "PartyIdentification", "ID")) if party else None
    companies = [c for o in _walk(root, "Organization") for c in _kids(o, "Company")]
    match = next((c for c in companies
                  if buyer_ref and _first_text(_path(c, "PartyIdentification", "ID")) == buyer_ref),
                 None)
    if match is not None:
        out["buyer-name"] = _first_text(_path(match, "PartyName", "Name"))
        out["buyer-identifier"] = _first_text(_path(match, "PartyLegalEntity", "CompanyID"))
        out["buyer-country"] = _first_text(_path(match, "PostalAddress", "Country", "IdentificationCode"))
    elif party:
        out["buyer-name"] = _first_text(_path(party[0], "PartyName", "Name"))
    out["buyer-country"] = out.get("buyer-country") or "DEU"

    # Procedure level and lots.
    proc = next(iter(_kids(root, "ProcurementProject")), None)
    lots = _kids(root, "ProcurementProjectLot")
    lot_projects = [p for lot in lots for p in _kids(lot, "ProcurementProject")]
    title_el = next((n for p in [proc, *lot_projects] if p is not None
                     for n in _kids(p, "Name") if _t(n)), None)
    if title_el is not None:
        out["notice-title"] = {(title_el.get("languageID") or lang).lower(): _t(title_el)}
    desc_proc = _first_text(_kids(proc, "Description")) if proc is not None else None
    if desc_proc:
        out["description-proc"] = {lang: desc_proc}
    lot_desc = [d for p in lot_projects if (d := _first_text(_kids(p, "Description")))]
    if lot_desc:
        out["description-lot"] = {lang: lot_desc}

    cpv: list[str] = []
    for p in [proc, *lot_projects]:
        if p is None:
            continue
        for c in _kids(p, "MainCommodityClassification", "AdditionalCommodityClassification"):
            for code in _kids(c, "ItemClassificationCode"):
                if code.get("listName", "cpv") == "cpv" and _t(code) and _t(code) not in cpv:
                    cpv.append(_t(code))  # type: ignore[arg-type]
    out["classification-cpv"] = cpv

    # Deadlines: the tender deadline and the request-to-participate deadline, per lot.
    stamps = []
    for period in _walk(root, "TenderSubmissionDeadlinePeriod", "ParticipationRequestReceptionPeriod"):
        end, hour = _first_text(_kids(period, "EndDate")), _first_text(_kids(period, "EndTime"))
        if end:
            stamps.append((end, hour))
    out["_deadlines"] = stamps

    # BT-15, the address of the procurement documents: the notice on the buyer's tendering platform
    # (evergabe-online, vergabe.niedersachsen.de, BWI ...), stated by the notice itself. The day files
    # name no page of their own on oeffentlichevergabe.de, so this is the notice's only link (WP-72).
    out["_documents_url"] = next(
        (u for ref in _walk(root, "CallForTendersDocumentReference")
         for u in (_t(e) for e in _path(ref, "Attachment", "ExternalReference", "URI"))
         if u and u.lower().startswith(("http://", "https://"))), None)

    est, cur = _amount(next(iter(_path(proc, "RequestedTenderTotal", "EstimatedOverallContractAmount")), None))
    out["estimated-value-proc"], out["estimated-value-cur-proc"] = est, cur
    lot_values, lot_cur = [], []
    for p in lot_projects:
        v, c = _amount(next(iter(_path(p, "RequestedTenderTotal", "EstimatedOverallContractAmount")), None))
        if v:
            lot_values.append(v)
            if c and c not in lot_cur:
                lot_cur.append(c)
    out["estimated-value-lot"], out["estimated-value-cur-lot"] = lot_values, lot_cur
    total = next((t for r in _walk(root, "NoticeResult") for t in _kids(r, "TotalAmount")), None)
    out["total-value"], out["total-value-cur"] = _amount(total)
    out["winner-selection-status"] = [
        _t(c) for r in _walk(root, "LotResult") for c in _kids(r, "TenderResultCode") if _t(c)]

    # BT-732: a security clearance the lot requires (`Code` true).
    for term in _walk(root, "SecurityClearanceTerm"):
        if (_first_text(_kids(term, "Code")) or "").lower() == "true":
            out["csecurity-clearance-description-lot"] = (
                _first_text(_kids(term, "Description")) or "required")
            break
    out["_lots"] = len(lots)
    return out
