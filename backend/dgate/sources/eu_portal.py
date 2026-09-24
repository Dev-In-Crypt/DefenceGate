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

import html
import json
import logging
import re
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


# ----------------------------------------------------------- topic details

# The calendar says a call exists; this says whether it is worth applying to.
# One document per topic, same host, same absence of a key:
#   GET .../data/topicDetails/edf-2026-ra-sens-msdt.json
# The identifier must be lower case -- the portal answers 404 to the very code
# it publishes everywhere else in upper case.
TOPIC_URL = ("https://ec.europa.eu/info/funding-tenders/opportunities/data/"
             "topicDetails/{identifier}.json")

# One request a second. These are 20 to 50 KiB documents from a public
# administration endpoint and there are about 150 of them; there is nothing to
# be gained by asking faster, and the French portal already showed what a burst
# from one address is answered with.
DETAIL_PAUSE = 1.0

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

# What counts as a member of a consortium. Deliberately a closed list: "at least
# three letters of support" and "at least two pages" are the same sentence shape
# and neither is a consortium rule.
_MEMBER_NOUNS = ("entities", "organisations", "organizations", "participants",
                 "applicants", "beneficiaries", "partners", "legal entities")

_AT_LEAST = r"at least\s+(\d+|" + "|".join(_NUMBER_WORDS) + r")\s+"
_CONSORTIUM_SIZE = re.compile(
    _AT_LEAST + r"(?:\w+\s+){0,3}?(?:" + "|".join(_MEMBER_NOUNS) + r")\b",
    re.IGNORECASE)
_MEMBER_STATES = re.compile(
    _AT_LEAST + r"(?:different\s+)?(?:EU\s+)?[Mm]ember [Ss]tates", re.IGNORECASE)


def _count(word: str) -> int | None:
    word = word.strip().lower()
    if word.isdigit():
        return int(word)
    return _NUMBER_WORDS.get(word)


def conditions_text(details: dict[str, Any]) -> str | None:
    """The conditions block as readable text rather than as markup."""
    raw = details.get("conditions")
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"\s+", " ", text).strip(' "\'>')
    return text or None


def consortium_rule(text: str | None) -> tuple[int | None, int | None]:
    """How many members, and from how many countries, the call requires.

    Read from the conditions text and only when the text states it in the
    standard form -- "at least 3 organisations from at least 3 different EU
    Member States". Horizon topics state it; EDF topics say "described in
    section 6 of the call document" and point at a PDF, so for those the answer
    is None and stays None. A default of three, which is what the EDF regulation
    requires in general, would be a rule read from the regulation and presented
    as a fact about this call.
    """
    if not text:
        return None, None
    size = _CONSORTIUM_SIZE.search(text)
    states = _MEMBER_STATES.search(text)
    return (_count(size.group(1)) if size else None,
            _count(states.group(1)) if states else None)


def _year_total(action: dict[str, Any]) -> float:
    total = 0.0
    for amount in (action.get("budgetYearMap") or {}).values():
        try:
            total += float(amount)
        except (TypeError, ValueError):
            continue
    return total


def topic_budget(details: dict[str, Any],
                 identifier: str) -> tuple[float | None, dict[str, Any], int]:
    """This topic's budget line, and how many topics share that figure.

    The budget map is keyed by call and each key lists every topic in that call,
    so the topic's own line is found by its identifier -- taking the first line
    would hand over a sibling's money.

    The third value is what stops the figure being read as more than it is. The
    portal repeats one amount across sibling topics when they compete for a
    single pot: measured on 24 September 2026, all eleven topics of the 2026 EDF
    development call carry `422000000`, which is the call's budget and not any
    topic's. Reported as a topic budget, that tells a twenty-person supplier
    there is EUR 422 million behind the one topic it was reading. So the count
    travels with the number, and `detail_fields` turns it into a scope.
    """
    overview = details.get("budgetOverviewJSONItem") or {}
    by_call = overview.get("budgetTopicActionMap") or {}
    for actions in by_call.values():
        for action in actions or []:
            if not str(action.get("action") or "").startswith(identifier):
                continue
            total = _year_total(action)
            sharing = sum(1 for other in actions or []
                          if _year_total(other) == total) if total else 0
            return (total or None), action, sharing
    return None, {}, 0


def fetch_topic_details(identifier: str, *,
                        client: httpx.Client | None = None) -> dict[str, Any]:
    """The detail document of one topic. Raises if it is not one."""
    owns = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT,
                                            "Accept": "application/json"},
                                   follow_redirects=True)
    try:
        def send() -> httpx.Response:
            response = client.get(TOPIC_URL.format(identifier=identifier.lower()),
                                  timeout=120.0)
            response.raise_for_status()
            return response

        payload = request_with_retry(send, attempts=5,
                                     what=f"{SOURCE_CODE} topic {identifier}").json()
    finally:
        if owns:
            client.close()
    details = payload.get("TopicDetails") if isinstance(payload, dict) else None
    if not isinstance(details, dict):
        raise ValueError(f"{identifier}: no TopicDetails in the document; the shape changed")
    return details


def detail_fields(details: dict[str, Any], identifier: str) -> dict[str, Any]:
    """Everything the detail document adds to a call, as the call's own columns.

    `conditions_raw` keeps the budget line verbatim -- expected number of grants,
    minimum and maximum contribution, the year the money sits in -- because
    "EUR 110 million across an unknown number of grants" and "two grants of
    EUR 3 million" are different propositions to a twenty-person supplier, and
    the difference is in that line rather than in the total.
    """
    text = conditions_text(details)
    budget, line, sharing = topic_budget(details, identifier)
    size, states = consortium_rule(text)
    return {
        "budget": budget,
        # Whose budget the number is. `topic` when the portal states a figure for
        # this topic alone, `call` when the same figure is repeated across sibling
        # topics competing for one pot. Served alongside the amount, because the
        # amount alone is misleading in the second case and there is no way to
        # split a shared pot honestly.
        "budget_scope": None if budget is None else ("topic" if sharing <= 1 else "call"),
        "eligibility_text": text,
        "min_consortium_size": size,
        "min_member_states": states,
        "conditions_raw": {
            "budget_line": line or None,
            "topics_sharing_budget": sharing or None,
            "expected_grants": line.get("expectedGrants") or None,
            "min_contribution": line.get("minContribution") or None,
            "max_contribution": line.get("maxContribution") or None,
            "deadline_model": line.get("deadlineModel"),
            "mga": [m.get("abbreviation") for m in (details.get("topicMGAs") or [])],
            "tags": details.get("tags") or [],
            "for_smes": bool(details.get("sme")),
            "submission_urls": [link.get("url") for link in (details.get("links") or [])
                                if link.get("url")],
        },
    }
