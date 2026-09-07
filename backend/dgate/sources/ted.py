"""TED Search API connector.

Endpoint:  POST https://api.ted.europa.eu/v3/notices/search
Auth:      none. The Search API is anonymous for published notices.
Docs:      https://docs.ted.europa.eu/api/latest/search.html
Fields:    https://docs.ted.europa.eu/ODS/latest/reuse/field-list.html
Licence:   Commission Decision 2011/833/EU. Notices freely reusable, including
           commercially. Metadata CC0 1.0.

Retention note: TED keeps notices on the website for ten years, then moves them
to a non-public internal archive. Anything we ingest today outlives the source.

Personal data note: notices carry contact person names, emails and phone
numbers, and award notices can name natural persons as contractors. Those
fields are dropped in normalise.py and never reach the serving layer.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterator

import httpx

from . import USER_AGENT

log = logging.getLogger(__name__)

TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"
PAGE_SIZE = 250          # API maximum is higher, but this keeps payloads sane
MAX_PAGES = 400          # hard stop so a bad query cannot run forever

# Exactly the fields we map in normalise.py. Requesting a narrow set keeps
# responses small and makes schema drift visible immediately.
TED_FIELDS = [
    "notice-identifier",
    "notice-title",
    "notice-type",
    "notice-subtype",
    "notice-version",
    "publication-number",
    "buyer-name",
    "buyer-identifier",
    "buyer-country",
    "official-language",
    "dispatch-date",
    "deadline-receipt-tender-date-lot",
    "deadline-receipt-tender-time-lot",
    "deadline-receipt-request-date-lot",
    "classification-cpv",
    "estimated-value-lot",
    "estimated-value-cur-lot",
    "estimated-value-proc",
    "estimated-value-cur-proc",
    "legal-basis",
    "contract-nature",
    "description-lot",
    "description-proc",
    "main-activity",
    "csecurity-clearance-description-lot",
    "non-disclosure-agreement-lot",
    "links",
]


@dataclass
class TedQuery:
    """An expert query plus paging state."""

    query: str
    fields: list[str]
    page: int = 1
    limit: int = PAGE_SIZE
    scope: str = "ALL"


def defence_query(since: date, until: date | None = None) -> str:
    """Build the TED expert query for defence-relevant notices.

    Three independent signals ORed together, matching classify.py:
      - legal basis is the defence directive
      - CPV sits in division 35
      - a security clearance requirement is stated (BT-732)

    The buyer-list signal cannot be expressed in the query language, so it is
    applied downstream after ingestion.
    """
    until = until or date.today()
    # Expert search dates are YYYYMMDD. An ISO date is rejected outright with
    # QUERY_INVALID_FIELD_FORMAT, which is how every live run failed until this
    # was checked against the API rather than against a fixture.
    window = (f"publication-date>={since.strftime('%Y%m%d')} AND "
              f"publication-date<={until.strftime('%Y%m%d')}")
    signals = " OR ".join(
        [
            'legal-basis IN ("32009L0081")',
            'classification-cpv=35*',
            'csecurity-clearance-description-lot=*',
        ]
    )
    return f"({window}) AND ({signals})"


def _post(client: httpx.Client, payload: dict[str, Any]) -> dict[str, Any]:
    r = client.post(
        TED_SEARCH_URL,
        json=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json()


def search(
    query: str,
    fields: list[str] | None = None,
    *,
    client: httpx.Client | None = None,
    max_pages: int = MAX_PAGES,
) -> Iterator[dict[str, Any]]:
    """Yield raw notice records, following pagination.

    Yields the notice dicts exactly as TED returns them. Normalisation happens
    elsewhere, so that the raw payload can be archived unmodified and any
    downstream logic can be re-run against it without refetching.
    """
    fields = fields or TED_FIELDS
    owns_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT})
    try:
        page = 1
        seen = 0
        while page <= max_pages:
            payload = {
                "query": query,
                "fields": fields,
                "page": page,
                "limit": PAGE_SIZE,
                "scope": "ALL",
            }
            data = _post(client, payload)
            notices = data.get("notices") or data.get("results") or []
            if not notices:
                break
            for n in notices:
                seen += 1
                yield n
            total = data.get("totalNoticeCount") or data.get("total")
            log.info("TED page %s: %s notices (running total %s of %s)",
                     page, len(notices), seen, total)
            if total is not None and seen >= total:
                break
            if len(notices) < PAGE_SIZE:
                break
            page += 1
    finally:
        if owns_client:
            client.close()


def fetch_window(days_back: int = 1, **kw) -> Iterator[dict[str, Any]]:
    """Daily incremental pull. Overlaps by design to survive a missed run."""
    since = date.today() - timedelta(days=days_back)
    yield from search(defence_query(since), **kw)


def content_hash(notice: dict[str, Any]) -> str:
    """Stable hash for change detection.

    Sorted keys so that key ordering in the response cannot produce a spurious
    new version. This is what stops the archive filling with noise.
    """
    blob = json.dumps(notice, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
