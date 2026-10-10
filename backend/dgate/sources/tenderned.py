"""TenderNed connector (Netherlands, the national procurement platform).

Endpoint:  GET https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties
Detail:    GET https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties/<id>
Auth:      none
Operator:  PIANOo / Ministry of Economic Affairs, with TenderNed
Licence:   CC0 1.0 for the dataset "Aankondigingen van overheidsopdrachten -
           TenderNed" on data.overheid.nl. The endpoint used here is the
           portal's own, the one its public pages call; the documented XML API
           needs credentials from TenderNed's functional management. See
           docs/sources/nl_tenderned.md.

What this is for. TED carries what the Netherlands publishes above the European
thresholds. TenderNed also carries what is below them and national-only, which
for Defensie was 23 of 435 notices in 2026. It is procurement, not grants: no
SBIR Defensie call was published here in 2026.

Four properties decided the design, each measured on 10 October 2026.

1. **The defence directive is in the list.** `publicatiecode` names the form:
   "... defensierichtlijn ..." is Directive 2009/81/EC (EF06, EF18, EF27, EF31).
   162 notices in 2026, 144 of them Defensie's and 9 the police's. No detail
   request is needed to know it, which is the same legal-basis signal TED and
   BOAMP give.

2. **Paging dies at 10,000 rows** (page 100 of 100 is HTTP 400), and a year is
   22,016. A publication day is 2 to 190, so a day is the window. The date
   filters are inclusive on both ends.

3. **The list has no CPV codes.** They are on the detail page, one request per
   notice, so the connector reads it for every notice: about 100 a day. The
   merged record is what is landed, under `detail`.

4. **Two fields move without the notice changing.** `aantalDagenTotSluitingsDatum`
   and `numberOfDaysBeforeAanmeldenInschrijven` count the days to the deadline.
   Hashed, they would make every re-read of a notice a "change" and land it
   again each night, so they are dropped here and derived from the deadline.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any, Iterator

import httpx

from . import USER_AGENT, request_with_retry

log = logging.getLogger(__name__)

SOURCE_CODE = "nl_tenderned"
LIST_URL = "https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties"
PAGE_SIZE = 100          # 500 is rejected with HTTP 400
MAX_PAGES = 100          # page 100 and beyond is rejected: 10,000 rows per query
REQUEST_PAUSE = 0.15     # a pause per detail request; the site is a public one

# Counters of days to the deadline. Derived, so not source data; see (4) above.
VOLATILE_FIELDS = ("aantalDagenTotSluitingsDatum", "numberOfDaysBeforeAanmeldenInschrijven",
                   "score")


def _get(client: httpx.Client, url: str, what: str, params: dict[str, Any] | None = None):
    def send() -> httpx.Response:
        response = client.get(url, params=params, timeout=60.0)
        response.raise_for_status()
        return response

    return request_with_retry(send, attempts=5, max_delay=60.0, what=what).json()


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                        follow_redirects=True)


def fetch_day_list(day: date, *, client: httpx.Client) -> list[dict[str, Any]]:
    """Every publication of one day, from the list. Raises if the day is short.

    A day whose distinct rows are fewer than the count the API reports would be
    recorded as complete and hold a hole, which is the one outcome a daily
    collection cannot afford. So it is an error, and the day is asked for again.
    """
    seen: dict[str, dict[str, Any]] = {}
    page = 0
    total = 0
    while True:
        payload = _get(client, LIST_URL, f"{SOURCE_CODE} {day} page {page}",
                       {"page": page, "size": PAGE_SIZE,
                        "publicatieDatumVanaf": day.isoformat(),
                        "publicatieDatumTot": day.isoformat()})
        if not isinstance(payload, dict) or "content" not in payload:
            raise ValueError(f"expected a publication page, got {type(payload).__name__}")
        total = int(payload.get("totalElements") or 0)
        for record in payload["content"]:
            key = str(record.get("publicatieId") or "")
            if key:
                seen.setdefault(key, record)
        page += 1
        if page >= int(payload.get("totalPages") or 0):
            break
        if page >= MAX_PAGES:
            raise RuntimeError(f"{SOURCE_CODE}: {day} reached the {MAX_PAGES}-page cap; "
                               f"the result was cut short, not complete")
    if len(seen) != total:
        raise RuntimeError(f"{SOURCE_CODE}: {day} returned {len(seen)} of {total} "
                           f"publications; the day is not complete")
    return list(seen.values())


def fetch_detail(publication_id: str, *, client: httpx.Client) -> dict[str, Any]:
    payload = _get(client, f"{LIST_URL}/{publication_id}", f"{SOURCE_CODE} {publication_id}")
    if not isinstance(payload, dict) or "publicatieId" not in payload:
        raise ValueError(f"expected a publication, got {type(payload).__name__}")
    return payload


def _drop_volatile(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k not in VOLATILE_FIELDS}


def merge_detail(record: dict[str, Any], detail: dict[str, Any] | None,
                 error: str | None = None) -> dict[str, Any]:
    """The list row with its detail page under `detail`.

    A detail that could not be read leaves the list row alone and says why in
    `detailError`: the notice is still worth landing, and the reason it is
    thinner than the others stays visible in the archive.
    """
    merged = _drop_volatile(record)
    if detail is not None:
        merged["detail"] = _drop_volatile(detail)
    if error:
        merged["detailError"] = error
    return merged


def fetch_day(day: date, *, client: httpx.Client | None = None,
              pause: float = REQUEST_PAUSE) -> Iterator[dict[str, Any]]:
    """Every publication of one day, each with its detail page."""
    owns = client is None
    client = client or _client()
    try:
        for record in fetch_day_list(day, client=client):
            try:
                detail, error = fetch_detail(str(record["publicatieId"]), client=client), None
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                log.warning("%s: no detail for %s: %s", SOURCE_CODE, record.get("publicatieId"), exc)
                detail, error = None, f"{type(exc).__name__}: {exc}"[:200]
            yield merge_detail(record, detail, error)
            time.sleep(pause)
    finally:
        if owns:
            client.close()


def fetch_window(days_back: int = 2, *, client: httpx.Client | None = None,
                 today: date | None = None) -> Iterator[dict[str, Any]]:
    """Every publication from `days_back` days ago to today, one day at a time."""
    today = today or date.today()
    owns = client is None
    client = client or _client()
    try:
        for offset in range(days_back, -1, -1):
            day = today - timedelta(days=offset)
            count = 0
            for record in fetch_day(day, client=client):
                count += 1
                yield record
            log.info("%s: %s publications on %s", SOURCE_CODE, count, day)
    finally:
        if owns:
            client.close()


def notice_url(record: dict[str, Any]) -> str | None:
    link = record.get("link")
    if isinstance(link, dict) and link.get("href"):
        return str(link["href"])
    pid = record.get("publicatieId")
    return f"https://www.tenderned.nl/aankondigingen/overzicht/{pid}" if pid else None
