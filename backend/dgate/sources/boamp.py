"""BOAMP connector (France, Bulletin officiel des annonces de marches publics).

Endpoint:  GET https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records
Auth:      none
Operator:  DILA (Direction de l'information legale et administrative), Premier ministre
Licence:   Licence Ouverte / Open Licence (Etalab)

Why France after TED. TED carries what is above the European thresholds, which
for a twenty-person manufacturer is the contract somebody else wins and they
subcontract into. What is below the thresholds is published nationally, and that
is the size of work this product exists to find. BOAMP holds 1,708,130 notices
from 2 March 2015 to today, 87,739 of them published in 2026 alone.

Four properties decided the design, each measured on 22 September 2026.

1. **The defence directive is a field, not a guess.** `perimetre` says which
   regime a notice is published under: 4,650 notices carry `DIRECTIVE-81`
   (Directive 2009/81/EC) and 1,145 the older French `CMP-2006-DEFENSE`. That
   is the same legal-basis signal the TED connector uses, stated by the source.

2. **Paging is capped at 10,000 results per query** (`offset + limit <= 10000`,
   and `limit` above 100 is rejected). A day is 120 to 431 notices, so a day is
   the window: three to five requests, never near the cap.

3. **The notice itself is a JSON string in `donnees`.** The record's own columns
   carry the administrative shell -- buyer, dates, procedure, thematic
   descriptors -- while CPV codes, the description and the contact details live
   inside `donnees`, in eForms shape for recent notices and an older schema
   before that. So the connector keeps the record whole and normalisation reads
   both levels.

4. **Contact details are in there.** `donnees` carries MAIL, TEL and named
   contacts; they are removed by `strip_personal_data` before anything is
   stored, as for every other source.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, timedelta
from typing import Any, Iterator

import httpx

from . import USER_AGENT, request_with_retry

log = logging.getLogger(__name__)

SOURCE_CODE = "fr_boamp"
SEARCH_URL = ("https://boamp-datadila.opendatasoft.com/api/explore/v2.1/"
              "catalog/datasets/boamp/records")
PAGE_SIZE = 100          # 1000 is rejected with InvalidRESTParameterError
MAX_OFFSET = 10_000      # the API's hard cap on offset + limit

# The edge in front of this API limits by rate, not only by daily quota. The
# historical load stopped on 23 September 2026 at its 2,087th publication day
# with HTTP 429 that did not clear inside the default four-attempt, 14-second
# ladder, and a burst of thirty requests from one address is answered with 403.
# A decade of days is a one-off walk, so it goes slower and waits far longer:
# one request a second, and up to four minutes of patience before a page is
# called lost. Neither costs anything a historical load cannot afford.
REQUEST_PAUSE = 1.0
PAGE_ATTEMPTS = 8
PAGE_MAX_DELAY = 128.0

# The regimes that are the defence and security directive, or its French
# predecessor. Recorded as CELEX 32009L0081 like every other source's legal
# basis; the native value stays in procedure_type.
DEFENCE_PERIMETERS = {"DIRECTIVE-81", "CMP-2006-DEFENSE"}


def day_query(day: date) -> dict[str, Any]:
    """Every notice published on one day, oldest first within the day.

    Ordered by `idweb` rather than by date: within a single day the dates are
    equal, and an unstable order across pages is how the Polish connector lost
    4.5% of a day before this was understood.
    """
    return {
        "where": f"dateparution = date'{day.isoformat()}'",
        "order_by": "idweb",
        "limit": PAGE_SIZE,
    }


def _page(client: httpx.Client, params: dict[str, Any], offset: int) -> dict[str, Any]:
    def send() -> httpx.Response:
        response = client.get(SEARCH_URL, params={**params, "offset": offset}, timeout=90.0)
        response.raise_for_status()
        return response

    payload = request_with_retry(send, attempts=PAGE_ATTEMPTS, max_delay=PAGE_MAX_DELAY,
                                 what=f"{SOURCE_CODE} offset {offset}").json()
    if not isinstance(payload, dict) or "results" not in payload:
        raise ValueError(f"expected a record page, got {type(payload).__name__}")
    return payload


def search(params: dict[str, Any], *, client: httpx.Client | None = None,
           max_offset: int = MAX_OFFSET) -> Iterator[dict[str, Any]]:
    """Yield raw records for one query, following offsets until they run out."""
    owns = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT,
                                             "Accept": "application/json"},
                                    follow_redirects=True)
    try:
        offset = 0
        while offset < max_offset:
            page = _page(client, params, offset)
            records = page.get("results") or []
            if not records:
                return
            yield from records
            offset += len(records)
            total = page.get("total_count")
            if total is not None and offset >= total:
                return
            if len(records) < params.get("limit", PAGE_SIZE):
                return
            time.sleep(REQUEST_PAUSE)
        raise RuntimeError(
            f"{SOURCE_CODE}: query reached the API's {max_offset} result cap; "
            f"the result was cut short, not complete ({params})")
    finally:
        if owns:
            client.close()


def fetch_window(days_back: int = 2, *, client: httpx.Client | None = None,
                 today: date | None = None) -> Iterator[dict[str, Any]]:
    """Every notice published from `days_back` days ago to today, deduplicated.

    One query per publication day, for the same reason as Poland: a day is the
    smallest window the filter expresses, and small enough to walk whole.
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
            for record in search(day_query(day), client=client):
                key = str(record.get("idweb") or record.get("id") or "")
                if not key or key in seen:
                    continue
                seen.add(key)
                count += 1
                yield record
            log.info("%s: %s notices published %s", SOURCE_CODE, count, day)
    finally:
        if owns:
            client.close()


def notice_body(record: dict[str, Any]) -> dict[str, Any]:
    """The notice inside `donnees`, parsed. Empty when it is missing or broken.

    Empty rather than raising: the administrative columns alone still make a
    usable opportunity, and a notice whose body fails to parse must still land
    and still be visible, not disappear.
    """
    raw = record.get("donnees")
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        log.warning("%s: notice %s has an unparsable body", SOURCE_CODE, record.get("idweb"))
        return {}
    return parsed if isinstance(parsed, dict) else {}


def notice_url(record: dict[str, Any]) -> str | None:
    idweb = record.get("idweb")
    return f"https://www.boamp.fr/pages/avis/?q=idweb:%22{idweb}%22" if idweb else None
