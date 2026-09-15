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
   measured, a Thursday is 5,733 notices (574 requests, about seven minutes), a
   Saturday 97, a Sunday 2,728. Every notice is landed; classification decides
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

import logging
import time
from datetime import date, datetime, timedelta, timezone
from datetime import time as time_of_day
from typing import Any, Iterable, Iterator

import httpx

from . import USER_AGENT, request_with_retry

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
# rather than a status field, so the mapping lives here.
NOTICE_TYPE_STATUS = {
    "ContractNotice": "open",
    "ContractNoticeForContractsInTheFieldOfDefenceAndSecurityEU": "open",
    "PriorInformationNoticeForContractsInTheFieldOfDefenceAndSecurityEU": "open",
    "NoticeOfIntentionToConcludeAContract": "open",
    "CompetitionNotice": "open",
    "TenderResultNotice": "awarded",
    "ContractAwardNotice": "awarded",
    "ContractAwardNoticeForContractsInTheFieldOfDefenceAndSecurityEU": "awarded",
    "ContractPerformingNotice": "awarded",
    "AgreementUpdateNotice": "awarded",
}


def map_status(notice_type: str | None) -> str:
    """Normalised lifecycle. An unknown type is `unknown`, never a fake `open`."""
    if not notice_type:
        return "unknown"
    return NOTICE_TYPE_STATUS.get(notice_type.strip(), "unknown")


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

def _page(client: httpx.Client, params: dict[str, Any], page: int) -> list[dict[str, Any]]:
    def send() -> httpx.Response:
        response = client.get(SEARCH_URL, params={**params, "PageNumber": page}, timeout=90.0)
        response.raise_for_status()
        return response

    response = request_with_retry(send, what=f"{SOURCE_CODE} page {page}")
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError(f"expected a list of notices, got {type(payload).__name__}")
    return payload


def search(
    params: dict[str, Any], *, client: httpx.Client | None = None, max_pages: int = MAX_PAGES
) -> Iterator[dict[str, Any]]:
    """Yield raw records for one query, following pages until the list empties."""
    owns = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT,
                                             "Accept": "application/json"},
                                    follow_redirects=True)
    try:
        for page in range(1, max_pages + 1):
            records = _page(client, params, page)
            if not records:
                return
            yield from records
            if len(records) < PAGE_SIZE:
                return
            time.sleep(REQUEST_PAUSE)
        raise RuntimeError(
            f"{SOURCE_CODE}: query still returning full pages after {max_pages} pages; "
            f"the result was cut short, not complete ({params})")
    finally:
        if owns:
            client.close()


def day_query(day: date) -> dict[str, Any]:
    """Every notice published on one day, in a stable order."""
    return {
        "publicationDateFrom": _iso(day),
        "publicationDateTo": _iso(day, end_of_day=True),
        "SortingColumnName": SORT_COLUMN,
        "SortingDirection": SORT_DIRECTION,
        "PageSize": PAGE_SIZE,
    }


def fetch_window(
    days_back: int = 2,
    *,
    client: httpx.Client | None = None,
    max_pages: int = MAX_PAGES,
    today: date | None = None,
) -> Iterator[dict[str, Any]]:
    """Every notice published from `days_back` days ago to today, deduplicated.

    One query per publication day. The API ignores the time of day in its date
    filter, so a day is the smallest window that can be asked for; a day is
    also small enough to walk whole, and walking it whole is the only way to
    know it was complete. A notice repeated at a day boundary is yielded once.
    """
    today = today or date.today()
    owns = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT,
                                             "Accept": "application/json"},
                                    follow_redirects=True)
    seen: set[str] = set()
    try:
        for offset in range(days_back, -1, -1):
            day = today - timedelta(days=offset)
            count = 0
            for record in search(day_query(day), client=client, max_pages=max_pages):
                key = str(record.get("noticeNumber") or record.get("objectId") or "")
                if not key or key in seen:
                    continue
                seen.add(key)
                count += 1
                yield record
            log.info("%s: %s notices published %s", SOURCE_CODE, count, day)
    finally:
        if owns:
            client.close()
