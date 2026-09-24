"""EU Funding and Tenders Portal: calls for proposals (grants).

Endpoint:  GET https://ec.europa.eu/info/funding-tenders/opportunities/data/referenceData/grantsTenders.json
Auth:      none
Operator:  European Commission (SEDIA)
Licence:   Commission Decision 2011/833/EU on the reuse of Commission documents

Why this source is the first one of the grant layer and not the fourth. One
anonymous request returns the portal's entire reference data: 11,163 calls and
topics, 10,164 of them grants, and it is the same document the portal's own
search screen is built on. Measured on 24 September 2026: 219 topics open, 279
forthcoming, and every European Defence Fund topic of the 2026 call among them,
closing on 29 September. There is no key to obtain, no paging to walk and no
rate limit to respect -- one request a day replaces a connector per programme.

The search API at `api.tech.ec.europa.eu/search-api` is the documented
alternative and was tried first; it answered every query with HTTP 500 on
24 September 2026, including the minimal one from its own documentation. The
reference-data document needs no key and no query language, so it is what the
connector reads. The search API stays the route to a topic's conditions text,
which the reference data does not carry.

What the document gives per topic: the portal's numeric `ccm2Id`, the topic code
(`EDF-2026-RA-SENS-MSDT`), the call it belongs to, title, framework programme,
programme division, status, planned opening and deadline dates, type of action
and tags such as `STEP-Defence`. What it does not give, checked across all
10,164 grant topics: no budget, no conditions of participation, and no CPV code
on a single one of them -- CPV appears only on the Commission's own procurement
objects. Those three live on the topic page, which is a separate fetch and a
separate task; a row with a null budget is honest, an invented one is not.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from typing import Any, Iterator

import httpx

from . import USER_AGENT, request_with_retry

log = logging.getLogger(__name__)

SOURCE_CODE = "eu_portal"
SNAPSHOT_URL = ("https://ec.europa.eu/info/funding-tenders/opportunities/data/"
                "referenceData/grantsTenders.json")

# The document is 124 MiB of JSON. It is fetched whole because the portal offers
# no filter on it, and it is fetched once a day.
FETCH_TIMEOUT = 600.0

TYPE_GRANT = 1          # 1 = call for proposals, 0 = Commission procurement

# Published under a defence programme: in scope by the regulation it is funded
# from, whatever its subject.
DEFENCE_PROGRAMMES = {"EDF", "EDIDP", "EDIP"}

# A civil programme whose subject is routinely dual-use. Cluster 3 is Civil
# Security for Society, and its topic codes say so; the divisions are Digital,
# Industry and Space (2.4), Civil Security (2.3) and the European Innovation
# Council (3.1), whose Accelerator is where a defence-adjacent SME applies
# alone rather than in a consortium.
DUAL_USE_DIVISIONS = ("HORIZON.2.3", "HORIZON.2.4", "HORIZON.3.1")
DUAL_USE_PREFIXES = ("HORIZON-CL3",)
DUAL_USE_PROGRAMMES = {"DIGITAL"}

# The portal's own tag for topics that carry the Strategic Technologies for
# Europe Platform defence seal. It appears on civil programmes too, which is
# exactly why it is read as a defence signal rather than a programme name.
STEP_DEFENCE_TAG = "STEP-Defence"

OPEN_STATUSES = {"Open", "Forthcoming"}


def _one(value: Any) -> dict[str, Any]:
    """The portal gives some fields as an object and some as a list of one."""
    if isinstance(value, list):
        value = value[0] if value else {}
    return value if isinstance(value, dict) else {}


def programme_code(record: dict[str, Any]) -> str | None:
    return _one(record.get("frameworkProgramme")).get("abbreviation")


def division_code(record: dict[str, Any]) -> str:
    return _one(record.get("programmeDivision")).get("abbreviation") or ""


def status_name(record: dict[str, Any]) -> str | None:
    return (record.get("status") or {}).get("abbreviation")


def _epoch_day(value: Any) -> date | None:
    try:
        return datetime.fromtimestamp(int(value) / 1000, UTC).date()
    except (TypeError, ValueError, OSError):
        return None


def deadline(record: dict[str, Any]) -> datetime | None:
    """The earliest deadline of the topic's actions.

    A topic can have several deadlines -- a two-stage call has one per stage --
    and the one that matters to somebody deciding whether to apply is the next
    one. Later stages stay in the payload.
    """
    stamps: list[int] = []
    for action in record.get("actions") or []:
        for value in action.get("deadlineDates") or []:
            try:
                stamps.append(int(value))
            except (TypeError, ValueError):
                continue
    if not stamps:
        return None
    return datetime.fromtimestamp(min(stamps) / 1000, UTC)


def opens_at(record: dict[str, Any]) -> date | None:
    for action in record.get("actions") or []:
        day = _epoch_day(action.get("plannedOpeningDate"))
        if day:
            return day
    return _epoch_day((record.get("plannedOpeningDateLong") or [None])[0]
                      if isinstance(record.get("plannedOpeningDateLong"), list)
                      else record.get("plannedOpeningDateLong"))


def regime(record: dict[str, Any]) -> str | None:
    """Why this call belongs in the database, or None if it does not.

    Two reasons and no third: the money comes from a defence programme, or the
    subject is one the agreed scope calls dual-use. Anything else is somebody
    else's product.
    """
    if programme_code(record) in DEFENCE_PROGRAMMES:
        return "defence"
    if STEP_DEFENCE_TAG in (record.get("tags") or []):
        return "defence"
    identifier = record.get("identifier") or ""
    if identifier.startswith(DUAL_USE_PREFIXES):
        return "dual_use"
    if division_code(record).startswith(DUAL_USE_DIVISIONS):
        return "dual_use"
    if programme_code(record) in DUAL_USE_PROGRAMMES:
        return "dual_use"
    return None


def in_scope(record: dict[str, Any], *, today: date | None = None) -> bool:
    """Grants in scope: open, forthcoming, or closed within the current year.

    The current year rather than all of history, because a closed 2026 call is
    what tells a supplier when the next one opens, while a closed 2021 call
    belongs to the participant-network work and is collected with it.
    """
    today = today or date.today()
    if record.get("type") != TYPE_GRANT:
        return False
    if not record.get("identifier") or not regime(record):
        return False
    if status_name(record) in OPEN_STATUSES:
        return True
    due = deadline(record)
    return bool(due and due.year == today.year)


def parse_snapshot(document: Any, *, today: date | None = None) -> list[dict[str, Any]]:
    """The in-scope grant topics of one reference-data document.

    Raises rather than returning nothing when the shape is not what it was: an
    empty result from a source that publishes 150 calls is a silent outage, and
    a run that records it as success is worse than a run that fails.
    """
    if not isinstance(document, dict):
        raise ValueError(f"expected a JSON object, got {type(document).__name__}")
    funding = document.get("fundingData")
    if not isinstance(funding, dict) or "GrantTenderObj" not in funding:
        raise ValueError("reference data has no fundingData.GrantTenderObj; the shape changed")
    records = funding["GrantTenderObj"]
    if not isinstance(records, list) or not records:
        raise ValueError("reference data carries no calls at all")
    return [r for r in records if isinstance(r, dict) and in_scope(r, today=today)]


def fetch_snapshot(*, client: httpx.Client | None = None) -> Any:
    owns = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT,
                                            "Accept": "application/json"},
                                   follow_redirects=True)
    try:
        def send() -> httpx.Response:
            response = client.get(SNAPSHOT_URL, timeout=FETCH_TIMEOUT)
            response.raise_for_status()
            return response

        response = request_with_retry(send, attempts=4, what=f"{SOURCE_CODE} reference data")
        log.info("%s: reference data is %.1f MiB", SOURCE_CODE, len(response.content) / 1048576)
        return json.loads(response.content)
    finally:
        if owns:
            client.close()


def fetch_calls(*, client: httpx.Client | None = None,
                today: date | None = None) -> Iterator[dict[str, Any]]:
    """Every in-scope grant topic the portal is publishing right now."""
    calls = parse_snapshot(fetch_snapshot(client=client), today=today)
    log.info("%s: %s calls in scope", SOURCE_CODE, len(calls))
    yield from calls


def topic_url(record: dict[str, Any]) -> str | None:
    identifier = record.get("identifier")
    if not identifier:
        return None
    return ("https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/"
            f"opportunities/topic-details/{identifier.lower()}")
