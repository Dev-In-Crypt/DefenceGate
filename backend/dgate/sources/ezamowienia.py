"""e-Zamowienia connector (Poland, Biuletyn Zamowien Publicznych).

Endpoint:  GET https://ezamowienia.gov.pl/mo-board/api/v1/Board/Search
Auth:      none
Operator:  Urzad Zamowien Publicznych (UZP)
Licence:   open public sector information

Discovered by observation on 8 September 2026, because the endpoint named in the
project's own source appendix, `/mo-client-board/api/notices/`, is not an API at
all: it returns the single-page application's HTML shell with HTTP 200. The real
one is reachable from the portal's startup config at `/mo-board/api/v1/Config`.

Three properties of this API shape everything below.

1. **The page size is capped at 10.** Asking for 100, 500 or 1000 returns 10.
   The connector used to issue targeted defence queries to avoid scanning, and
   so never collected the notices a listed defence buyer published outside CPV
   division 35 -- the buyer list covers 56 Polish bodies, the queries two. Since
   15 September 2026 it collects everything, one publication day at a time:
   measured, a Monday is 2,667 notices (267 requests, under four minutes), a
   Saturday 36, a Sunday 61. Every notice is landed; classification decides
   what becomes an opportunity, as for Atlas and PLACSP.

2. **`cpvCode` matches as a substring, not a prefix.** `cpvCode=35` also returns
   `09135100` and `71355000`, and a dashed code matches nothing. So the query
   narrows the set server-side and the connector filters properly afterwards.

3. **`organizationNationalId` filters, `organizationName` does not.** Catching a
   defence buyer that purchases outside CPV division 35 therefore needs its tax
   identifier, which is why `DEFENCE_BUYER_TAX_IDS` exists and why it is honest
   about being incomplete.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from datetime import time as time_of_day
from typing import Any, Iterable, Iterator

import httpx

from ..normalise import PIN_AS_CALL
from . import USER_AGENT, new_client, request_with_retry

log = logging.getLogger(__name__)

API_BASE = "https://ezamowienia.gov.pl/mo-board/api/v1"
SEARCH_URL = f"{API_BASE}/Board/Search"
GLOSSARY_URL = f"{API_BASE}/glossary"
NOTICE_URL = "https://ezamowienia.gov.pl/mp-client/search/list/ogloszenia/{object_id}"

SOURCE_CODE = "pl_ezam"

# The API ignores anything larger. Measured, not assumed.
PAGE_SIZE = 10
# A hard stop so a bad query cannot walk forever -- and, since a day is walked
# whole, reaching it means the day was cut short, which search() raises on
# rather than returning a truncated day as if it were complete. The busiest day
# measured needed 574 pages.
MAX_PAGES = 2000

# Paging is only stable on a unique sort key. Sorted by PublicationDate -- the
# obvious choice, and what this connector used -- notices sharing a timestamp
# change places between requests: one walk of 10 September 2026 repeated 256
# records and returned 5,478 distinct, against 5,733 when sorted by
# NoticeNumber, which repeated none and returned the identical set twice. The
# date sort silently lost about 4.5% of notices.
SORT_COLUMN = "NoticeNumber"
SORT_DIRECTION = "ASC"
REQUEST_PAUSE = 0.25     # seconds between requests; this is a public service

# The three BZP notice types that exist to publish under the defence and
# security directive. Their presence is the Polish equivalent of TED's
# legal-basis signal.
DEFENCE_NOTICE_TYPES = (
    "PriorInformationNoticeForContractsInTheFieldOfDefenceAndSecurityEU",
    "ContractNoticeForContractsInTheFieldOfDefenceAndSecurityEU",
    "ContractAwardNoticeForContractsInTheFieldOfDefenceAndSecurityEU",
)

# Tax identifiers (NIP) of Polish defence buyers, used because the API filters
# on the identifier and not on the name. Deliberately short and honest: a buyer
# absent from this list is only caught when it buys under CPV division 35.
# Verified against live notices on 8 September 2026.
DEFENCE_BUYER_TAX_IDS: tuple[str, ...] = (
    "5261038122",   # Agencja Mienia Wojskowego
    "5750009108",   # Jednostka Wojskowa Nr 4101
)

# Lifecycle. BZP expresses the state of a procedure through the notice type
# rather than a status field, so the mapping lives here. Decision of 12 October
# 2026 (docs/DATA_QUALITY_PLAN): a call that can be acted on is `open`, a prior
# information or planning notice is `forthcoming`, award, modification and
# intention-to-conclude notices (TED's can-*, veat) are `awarded`.
NOTICE_TYPE_STATUS = {
    "ContractNotice": "open",
    "ContractNoticeForContractsInTheFieldOfDefenceAndSecurityEU": "open",
    # A call for offers below the thresholds. Both live records had a future
    # deadline, which is what makes it a call and not a record of one.
    "SmallContractNotice": "open",
    "CompetitionNotice": "open",
    # Was `open`: a prior information notice is not a call for competition.
    "PriorInformationNoticeForContractsInTheFieldOfDefenceAndSecurityEU": "forthcoming",
    # The procurement plan of a buyer: what it intends to buy, not a tender.
    "TenderPlanNotice": "forthcoming",
    # "Intention to conclude a contract" is published before a direct award: the
    # equivalent of TED's veat, which the decision maps to `awarded`. Was `open`.
    "NoticeOfIntentionToConcludeAContract": "awarded",
    "AgreementIntentionNotice": "awarded",
    "TenderResultNotice": "awarded",
    "ContractAwardNotice": "awarded",
    "ContractAwardNoticeForContractsInTheFieldOfDefenceAndSecurityEU": "awarded",
    "ContractPerformingNotice": "awarded",
    "AgreementUpdateNotice": "awarded",
    # Deliberately `unknown`. A change notice carries no deadline of its own and
    # restates a notice that is listed in its own right (the re-read keeps that
    # one current); giving the copy the original's status would list the same
    # procurement twice as open.
    "NoticeUpdateNotice": "unknown",
}

# The notices the bulletin republishes from TED carry `noticeType = null` and
# the TED form in `noticeTypeTed` instead (`eforms-16`, or the TED type name on
# older forms). Subtype -> TED `notice-type`, established on 12 October 2026 by
# joining 3,906 such records to their TED twins (`pdfUrl` -> publication number)
# and reading the twin's `notice-subtype` and `notice-type`; every pair below was
# seen, none is from memory. A subtype not listed stays unmapped: `unknown`.
TED_SUBTYPE_TYPE = {
    "1": "pin-buyer", "7": "pin-rtl", "8": "pin-rtl", "15": "qu-sy",
    "16": "cn-standard", "17": "cn-standard", "18": "cn-standard", "E3": "cn-standard",
    "20": "cn-social", "21": "cn-social",
    "25": "veat", "26": "veat", "27": "veat",
    "29": "can-standard", "30": "can-standard", "31": "can-standard", "E4": "can-standard",
    "33": "can-social", "34": "can-social", "36": "can-desg",
    "38": "can-modif", "39": "can-modif",
    "T01": "pin-tran",
    # Added on 13 October 2026 from the same join on the 1,899 records with a TED twin that
    # state a subtype the table lacked: 4 -> pin-only (27 of 27 twins), 9 -> pin-rtl (2 of 2),
    # E5 -> compl (1 of 1), E6 -> can-modif (2 of 2). 32 rows were `unknown`.
    "4": "pin-only", "9": "pin-rtl", "E5": "compl", "E6": "can-modif",
}

# TED notice-type -> lifecycle, the decision's rule: cn-* open, pin-* forthcoming,
# can-* and veat awarded. `qu-sy` (a qualification system) is none of those.
# `pin-cfc-*` is a prior-information notice used as a call: forthcoming here, `open`
# when the record states a deadline (`map_status(..., has_deadline=True)`), the same
# rule `normalise.ted_status` applies to TED's own notices.
TED_TYPE_STATUS = {
    "cn-standard": "open", "cn-social": "open", "cn-desg": "open",
    "pin-only": "forthcoming", "pin-buyer": "forthcoming", "pin-rtl": "forthcoming",
    "pin-tran": "forthcoming", "pin-cfc-standard": "forthcoming",
    "pin-cfc-social": "forthcoming",
    "can-standard": "awarded", "can-social": "awarded", "can-desg": "awarded",
    "can-modif": "awarded", "veat": "awarded", "compl": "awarded",
}


def ted_notice_type(value: str | None) -> str | None:
    """The TED `notice-type` named by a `noticeTypeTed` value, if it names one."""
    text = (value or "").strip()
    if text.lower().startswith("eforms-"):
        return TED_SUBTYPE_TYPE.get(text[len("eforms-"):].upper())
    return text.lower() if text.lower() in TED_TYPE_STATUS else None


def map_status(notice_type: str | None, has_deadline: bool = False) -> str:
    """Normalised lifecycle. An unknown type is `unknown`, never a fake `open`.

    Takes a BZP notice type (`ContractNotice`) or a TED form (`eforms-16`,
    `can-standard`), whichever the record carries. `has_deadline` is whether the
    record states a deadline for offers: it makes a prior-information notice used as
    a call for competition (`pin-cfc-*`) a call that can be acted on.
    """
    if not notice_type:
        return "unknown"
    text = str(notice_type).strip()
    if text in NOTICE_TYPE_STATUS:
        return NOTICE_TYPE_STATUS[text]
    ted_type = ted_notice_type(text) or ""
    if ted_type in PIN_AS_CALL and has_deadline:
        return "open"
    return TED_TYPE_STATUS.get(ted_type, "unknown")


# `procedureResult` is the outcome of a result notice, one `;`-separated entry
# per part (lot): `zawarcieUmowy` (contract concluded), `uniewaznienie` (the
# procedure was annulled), `nieRozstrzygnieto` (not decided). On notices
# republished from TED it holds the word `Unijna`, which is not an outcome.
_RESULT_AWARDED = "zawarcieumowy"
_RESULT_CANCELLED = {"uniewaznienie"}
_RESULT_UNDECIDED = {"nierozstrzygnieto", "zamknięte bez wyboru wykonawcy"}


def result_status(procedure_result: str | None) -> str | None:
    """What a result notice says about the procedure, or None when it says
    nothing that changes `awarded`.

    One part with a contract is enough for `awarded`; a notice whose parts were
    all annulled or undecided awarded nothing and is `cancelled`, as TED states the
    same outcome (`clos-nw`). It was `closed` for undecided ones until 14 October 2026,
    a word outside the vocabulary: 564 Atlas and e-Zamowienia rows said `closed` where
    TED's twin said `cancelled` (data-correctness DC6).
    """
    parts = {p.strip().lower() for p in str(procedure_result or "").split(";") if p.strip()}
    if not parts or _RESULT_AWARDED in parts:
        return None
    if parts <= _RESULT_CANCELLED | _RESULT_UNDECIDED:
        return "cancelled"
    return None


def record_status(record: dict[str, Any]) -> str:
    """Lifecycle of one board record: its BZP type, else its TED form, with an
    annulled result notice shown as `cancelled` rather than `awarded`."""
    status = map_status(record.get("noticeType") or record.get("noticeTypeTed"),
                        has_deadline=bool(record.get("hasDeadline")
                                          or record.get("submittingOffersDate")))
    if status == "awarded":
        return result_status(record.get("procedureResult")) or status
    return status


# `tenderType` is a word on the notices republished from TED (the eForms
# `procedure-type` code list, seen: open, restricted, neg-w-call, neg-wo-call,
# comp-dial, oth-single, oth-mult, comp-tend) and a dotted number on a notice
# filed in the bulletin itself (1.1.1, 1.1.2, 2.1, 1.4.1.7 ...). The numbers are
# the bulletin's own form sections; the only place that explains them is a glossary
# endpoint whose use is not documented (`/glossary` answers 500 without a
# parameter nobody publishes), so they are kept as stated and labelled as codes.
PROCEDURE_WORDS = {
    "open": "Open procedure",
    "restricted": "Restricted procedure",
    "neg-w-call": "Negotiated procedure with a call for competition",
    "neg-wo-call": "Negotiated procedure without a call for competition",
    "comp-dial": "Competitive dialogue",
    "innovation": "Innovation partnership",
    "oth-single": "Other single-stage procedure",
    "oth-mult": "Other multi-stage procedure",
    "comp-tend": "Competitive tendering",
}


# The bulletin's numeric `tenderType` codes, named. The publisher's own client
# (`/mo-client-board/main-es2015.*.js`, read on 13 October 2026) holds the dictionary the
# codes come from: every entry is a `SelectOption(<dictionary key>, <code>)`, and the key
# names the procedure and the article of the Public Procurement Law (PZP) it rests on --
# `BELOW_EU.BASIC_ORDER_BASED_ON_275_1` is 1.1.1, `ABOVE_EU.OPEN_TENDER_132` is 2.1,
# `ABOVE_EU.NEGOTIATED_WITHOUT_ANNOUNCEMENT_208_209_1_1` is 2.6.1. The names below are
# those keys, in the vocabulary TED's codes already have here (`PROCEDURE_WORDS`) where
# the procedure is the same one. A code or a prefix not listed (1.2 "partner order",
# art. 297, whose English name is not certain; 2.9; anything new) stays a labelled code.
# Longest prefix wins; the dotted structure is the publisher's own.
BZP_PROCEDURE_NAMES = {
    "1.1.1": "Basic procedure (art. 275 pt 1)",
    "1.1.2": "Basic procedure (art. 275 pt 2)",
    "1.1.3": "Basic procedure (art. 275 pt 3)",
    "1.3": "Negotiated procedure without publication",
    "1.4": "Free-hand award (direct award)",
    "2.1": "Open procedure",
    "2.2": "Restricted procedure",
    "2.3": "Negotiated procedure with a call for competition",
    "2.4": "Competitive dialogue",
    "2.5": "Innovation partnership",
    "2.6": "Negotiated procedure without a call for competition",
    "2.7": "Free-hand award (direct award)",
    "2.8.1": "Open procedure (utilities)",
    "2.8.2": "Restricted procedure (utilities)",
    "2.8.3": "Negotiated procedure with a call for competition (utilities)",
    "2.8.4": "Competitive dialogue (utilities)",
    "2.8.5": "Innovation partnership (utilities)",
    "2.8.6": "Negotiated procedure without a call for competition (utilities)",
    "2.8.7": "Free-hand award (direct award, utilities)",
    "2.10": "Free-hand award (direct award, defence and security)",
    "2.11": "Free-hand award (direct award, defence and security)",
    "2.12": "Free-hand award (direct award, defence and security)",
    "11": "Framework agreement (below EU thresholds)",
    "12": "Framework agreement (above EU thresholds)",
    "20.1": "Dynamic purchasing system",
}


def bzp_procedure_name(code: str) -> str | None:
    """The name of a numeric bulletin code, by the longest listed prefix on a dot boundary."""
    parts = code.split(".")
    for n in range(len(parts), 0, -1):
        name = BZP_PROCEDURE_NAMES.get(".".join(parts[:n]))
        if name:
            return name
    return None


def procedure_label(tender_type: Any) -> str | None:
    """The procedure as a reader can use it: a verified word, a numeric bulletin code
    named by the publisher's own dictionary (`BZP_PROCEDURE_NAMES`), a code nobody
    has named stated as one ("BZP 1.2"), or nothing. Never the notice type, which
    names the document and not the procedure."""
    text = str(tender_type).strip() if tender_type not in (None, "") else ""
    if not text:
        return None
    word = PROCEDURE_WORDS.get(text.lower())
    if word:
        return word
    if all(ch.isdigit() or ch == "." for ch in text):
        return bzp_procedure_name(text) or f"BZP {text}"
    return text


def notice_url(record: dict[str, Any]) -> str | None:
    object_id = record.get("objectId") or record.get("moIdentifier")
    return NOTICE_URL.format(object_id=object_id) if object_id else None


# ------------------------------------------------------------------ queries

def _iso(day: date, end_of_day: bool = False) -> str:
    moment = datetime.combine(
        day, time_of_day(23, 59, 59) if end_of_day else time_of_day(0, 0, 0),
        tzinfo=timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def defence_queries(
    since: date,
    until: date | None = None,
    buyer_tax_ids: Iterable[str] = DEFENCE_BUYER_TAX_IDS,
) -> list[dict[str, Any]]:
    """The set of searches that together cover Polish defence procurement.

    One query per angle rather than one scan of everything: division 35 by CPV,
    the three defence notice types, and each known defence buyer by tax id.
    """
    until = until or date.today()
    window = {
        "publicationDateFrom": _iso(since),
        "publicationDateTo": _iso(until, end_of_day=True),
        "SortingColumnName": SORT_COLUMN,
        "SortingDirection": SORT_DIRECTION,
        "PageSize": PAGE_SIZE,
    }
    queries: list[dict[str, Any]] = [{**window, "cpvCode": "35"}]
    queries += [{**window, "noticeType": t} for t in DEFENCE_NOTICE_TYPES]
    queries += [{**window, "organizationNationalId": nip} for nip in buyer_tax_ids]
    return queries


# ----------------------------------------------------------------- fetching

def _page(client: httpx.Client, params: dict[str, Any], page: int,
          attempts: int = 4) -> list[dict[str, Any]]:
    def send() -> httpx.Response:
        response = client.get(SEARCH_URL, params={**params, "PageNumber": page}, timeout=90.0)
        response.raise_for_status()
        return response

    response = request_with_retry(send, what=f"{SOURCE_CODE} page {page}", attempts=attempts)
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError(f"expected a list of notices, got {type(payload).__name__}")
    return payload


def search(
    params: dict[str, Any], *, client: httpx.Client | None = None, max_pages: int = MAX_PAGES,
    pause: float = REQUEST_PAUSE, attempts: int = 4,
) -> Iterator[dict[str, Any]]:
    """Yield raw records for one query, following pages until the list empties.

    A page that still fails after `attempts` tries raises: a walk that stops
    quietly would be recorded as a smaller day.
    """
    owns = client is None
    client = client or new_client(headers={"User-Agent": USER_AGENT,
                                             "Accept": "application/json"},
                                    follow_redirects=True)
    try:
        for page in range(1, max_pages + 1):
            records = _page(client, params, page, attempts)
            if not records:
                return
            yield from records
            if len(records) < PAGE_SIZE:
                return
            time.sleep(pause)
        raise RuntimeError(
            f"{SOURCE_CODE}: query still returning full pages after {max_pages} pages; "
            f"the result was cut short, not complete ({params})")
    finally:
        if owns:
            client.close()


def day_query(day: date) -> dict[str, Any]:
    """Every notice published on one day, in a stable order.

    Both bounds are that day's midnight. The API reads `publicationDateTo` as a
    whole date and ignores its time, so `23:59:59` reaches into the next day:
    measured on 15 September 2026, the 14th asked that way returned 2,667
    notices from the 14th and 2,449 from the 15th, and a midnight bound returned
    the 14th alone (latest 23:49:46).
    """
    return {
        "publicationDateFrom": _iso(day),
        "publicationDateTo": _iso(day),
        "SortingColumnName": SORT_COLUMN,
        "SortingDirection": SORT_DIRECTION,
        "PageSize": PAGE_SIZE,
    }


def official_total(day: date, *, client: httpx.Client) -> int:
    """The portal's own count of notices published on `day`: `TotalCount` in the
    `X-Pagination` response header of a one-page query (measured 8-14 October 2026:
    3,217, 2,813, 26, 49, 2,993, 2,983, 3,069)."""
    def send() -> httpx.Response:
        response = client.get(SEARCH_URL, params={**day_query(day), "PageSize": 10,
                                                  "PageNumber": 1}, timeout=90.0)
        response.raise_for_status()
        return response

    header = request_with_retry(send, what=f"{SOURCE_CODE} total {day}").headers
    return int(json.loads(header["X-Pagination"])["TotalCount"])


def fetch_window(
    days_back: int = 2,
    *,
    client: httpx.Client | None = None,
    max_pages: int = MAX_PAGES,
    today: date | None = None,
    failed: list[date] | None = None,
) -> Iterator[dict[str, Any]]:
    """Every notice published from `days_back` days ago to today, deduplicated.

    One query per publication day. The API ignores the time of day in its date
    filter, so a day is the smallest window that can be asked for; a day is
    also small enough to walk whole, and walking it whole is the only way to
    know it was complete. A notice repeated at a day boundary is yielded once.

    A day that cannot be walked to its end raises, which ends the window. With
    `failed` given, the day is appended to it instead and the remaining days are
    still walked: on 7 October 2026 a 503 on page 301 of the 6th ended the run
    and the 7th was never read. The caller must treat a non-empty list as a
    window that is not complete.
    """
    today = today or date.today()
    owns = client is None
    client = client or new_client(headers={"User-Agent": USER_AGENT,
                                             "Accept": "application/json"},
                                    follow_redirects=True)
    seen: set[str] = set()
    try:
        for offset in range(days_back, -1, -1):
            day = today - timedelta(days=offset)
            count = 0
            try:
                for record in search(day_query(day), client=client, max_pages=max_pages):
                    key = str(record.get("noticeNumber") or record.get("objectId") or "")
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    count += 1
                    yield record
            except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                if failed is None:
                    raise
                failed.append(day)
                log.error("%s: %s could not be read to its end after %s notices: %s",
                          SOURCE_CODE, day, count, exc)
                continue
            log.info("%s: %s notices published %s", SOURCE_CODE, count, day)
    finally:
        if owns:
            client.close()


# ------------------------------------------------- history and re-reads

# A historical load asks for one day at a time at one request a second (the
# owner's rule for every backfill), and sits out a rate limit rather than
# giving up on the first 429: six tries wait about a minute in total, after
# which the load stops and resumes from the day marker.
HISTORY_PAUSE = 1.0
HISTORY_ATTEMPTS = 6

# The re-read of open notices: at most this many per run, at one request a
# second, and nothing read within the last REFRESH_MIN_AGE_HOURS. About 300 are
# open at any time (311 on 12 October 2026), so 200 a day reaches each of them
# at least every second day, inside the three-day bound.
REFRESH_PAUSE = 1.0
REFRESH_LIMIT = 200
REFRESH_MIN_AGE_HOURS = 20.0


def fetch_day(
    day: date, *, client: httpx.Client | None = None, max_pages: int = MAX_PAGES,
    pause: float = HISTORY_PAUSE, attempts: int = HISTORY_ATTEMPTS,
) -> Iterator[dict[str, Any]]:
    """Every notice published on one day, each once, paced for a backfill.

    The caller marks the day done only after this generator is exhausted, so a
    503 on page 301 propagates as an exception and the day is asked for again
    from page 1: there is no way to finish a day short.
    """
    seen: set[str] = set()
    for record in search(day_query(day), client=client, max_pages=max_pages,
                         pause=pause, attempts=attempts):
        key = str(record.get("noticeNumber") or record.get("objectId") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        yield record


def fetch_notice(
    notice_number: str, *, client: httpx.Client | None = None,
) -> dict[str, Any] | None:
    """One notice by its number, as the board serves it now, or None.

    `noticeNumber` is an exact filter (measured on 12 October 2026: one record
    for `2026/BZP 00448576/01`; `BzpNumber` is ignored and returns the whole
    board). The same query `ops/spot_check` uses to compare a stored notice with
    the live one. A change made in place -- a deadline moved -- keeps the notice
    number and its publication date, so no publication-day window ever sees it.
    """
    for record in search({"noticeNumber": notice_number, "PageSize": PAGE_SIZE},
                         client=client, max_pages=1):
        if str(record.get("noticeNumber") or "").strip() == notice_number:
            return record
    return None
