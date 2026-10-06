"""NCBR connector (Poland, Narodowe Centrum Badan i Rozwoju).

Endpoint:  GET https://www.gov.pl/api/data/competition-search?type=NCBR&language=pl
Auth:      none
Operator:  Narodowe Centrum Badan i Rozwoju (National Centre for Research and Development)
Licence:   NCBR's reuse policy: commercial reuse allowed, attribution required; the text
           of the site is CC BY-SA 4.0

Where it came from. The competitions page of NCBR is a single-page application whose
list is not in the HTML. Its script, `competition-searcher-front_pl.js`, calls a JSON
API that is public and needs no key, and that is the source: 364 competitions, each
with status, budget, who may apply, thematic areas and the dates that matter. Found by
reading the page's own script on 6 October 2026.

Three measured properties decided the design.

1. **The publisher's own defence tags are the signal, and they mean two things.**
   `programmeTypes` carries `defence_security` on nine competitions in six years --
   PERUN, SZAFIR, the 2020 and 2022 defence rounds -- none announced in 2026; the last,
   PERUN 1/2023, has sat "in evaluation" since early 2024. `thematicAreas` carries
   `defence_and_security` on 53, and on the ones that matter now it is not a defence
   programme at all but a horizontal one that names defence among the fields it funds:
   SMART at PLN 350 million for large enterprises and consortia, Eurostars for SMEs. A
   Polish defence manufacturer applies to those, and one of them closes on 16 October
   2026. The first tag makes the regime `defence`, the second `dual_use`.

2. **Paging is unstable and sorting does not fix it.** Walking 50 per page returned 414
   rows for 364 competitions, with `sort=path,asc` and without; the union of the pages
   was still all 364. So rows are deduplicated by path and a walk whose distinct count
   falls short of `totalElements` is retried at another page size, and an error if it
   still falls short. A short walk recorded as complete is a silent hole.

3. **The text of a competition is CC BY-SA.** Descriptions are landed in the raw archive
   and not served: a share-alike licence on text carried into the product would reach
   the product. What is served is the structured facts -- who may apply, the sums, the
   dates, the status -- and a link to the original.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from . import USER_AGENT, request_with_retry

log = logging.getLogger(__name__)

SOURCE_CODE = "pl_ncbr"
SEARCH_URL = "https://www.gov.pl/api/data/competition-search"
SITE = "https://www.gov.pl"
WARSAW = ZoneInfo("Europe/Warsaw")
REQUEST_PAUSE = 1.0
PAGE_SIZES = (50, 100, 25)          # a short walk is retried at the next size

DEFENCE_PROGRAMME = "defence_security"        # in programmeTypes
DEFENCE_AREA = "defence_and_security"         # in thematicAreas

# Who counts as a supplier. Natural persons, researchers and non-governmental bodies
# alone are NAWA fellowships and LIDER UP, not something a company answers.
ENTERPRISE = {"sme", "micro", "large_enterprise", "consortium"}

APPLICANT_LABELS = {
    "sme": "small and medium enterprise", "micro": "micro enterprise",
    "large_enterprise": "large enterprise", "consortium": "consortium",
    "research_unit": "research unit", "university": "university", "ngo": "non-governmental body",
    "public_institution": "public institution", "scientist": "researcher", "individual": "natural person",
}
AREA_LABELS = {
    "defence_and_security": "defence and security", "innovative_technologies": "innovative technologies",
    "healthy_society": "healthy society", "sustainable_energy": "sustainable energy",
    "circular_economy": "circular economy", "agri_food": "agri-food", "education": "education",
    "accessibility": "accessibility", "others": "other",
}

_MONEY = re.compile(
    r"(?P<num>\d[\d\s .,]*\d|\d)\s*(?P<cur>z[lł]|PLN|z[lł]otych|euro|EUR|€)\b", re.I)


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                        follow_redirects=True)


# ---------------------------------------------------------------- fetching

def _walk(client: httpx.Client, size: int) -> tuple[dict[str, dict[str, Any]], int]:
    found: dict[str, dict[str, Any]] = {}
    total = 0
    for page in range(0, 200):
        def send(page: int = page) -> httpx.Response:
            response = client.get(SEARCH_URL, params={"type": "NCBR", "language": "pl",
                                                       "page": page, "size": size}, timeout=90.0)
            response.raise_for_status()
            return response

        payload = request_with_retry(send, attempts=6, max_delay=60.0,
                                     what=f"{SOURCE_CODE} page {page}").json()
        if not isinstance(payload, dict) or "content" not in payload or "totalElements" not in payload:
            raise ValueError("expected a page of competitions with `content` and `totalElements`; "
                             "the shape changed")
        total = int(payload["totalElements"])
        for record in payload["content"]:
            if record.get("path"):
                found[record["path"]] = record
        if payload.get("last") or not payload["content"]:
            return found, total
        time.sleep(REQUEST_PAUSE)
    raise RuntimeError(f"{SOURCE_CODE}: 200 pages and still more; the walk was cut short")


def fetch_all(*, client: httpx.Client | None = None) -> list[dict[str, Any]]:
    """Every competition NCBR lists, once each, and provably all of them.

    Rows repeat across pages and the sort parameter does not prevent it, so the walk is
    judged by the number of distinct competitions against the total the API states. A
    short count is retried at another page size, and results are pooled across tries: a
    competition missed at one size is not missed at every one.
    """
    owns = client is None
    client = client or _client()
    pooled: dict[str, dict[str, Any]] = {}
    total = 0
    try:
        for size in PAGE_SIZES:
            found, total = _walk(client, size)
            pooled.update(found)
            if len(pooled) >= total:
                return list(pooled.values())
            log.warning("%s: %s distinct of %s at page size %s; trying another size",
                        SOURCE_CODE, len(pooled), total, size)
        raise RuntimeError(f"{SOURCE_CODE}: only {len(pooled)} distinct competitions of the "
                           f"{total} the API states, after {len(PAGE_SIZES)} walks; "
                           f"the list was cut short, not complete")
    finally:
        if owns:
            client.close()


# ------------------------------------------------------------------ parsing

def _list(value: Any) -> list[str]:
    """The API gives its arrays as JSON text inside a string."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return [str(v) for v in parsed] if isinstance(parsed, list) else []


def programme_types(record: dict[str, Any]) -> list[str]:
    return _list(record.get("programmeTypes"))


def thematic_areas(record: dict[str, Any]) -> list[str]:
    return _list(record.get("thematicAreas"))


def applicant_types(record: dict[str, Any]) -> list[str]:
    return _list(record.get("typesOfApplicant"))


def sources_of_funding(record: dict[str, Any]) -> list[str]:
    return _list(record.get("sourcesOfFunding"))


def regime(record: dict[str, Any]) -> str | None:
    """`defence` for NCBR's own defence programmes, `dual_use` for a horizontal
    programme that names defence among its fields, None for everything else."""
    if DEFENCE_PROGRAMME in programme_types(record):
        return "defence"
    if DEFENCE_AREA in thematic_areas(record):
        return "dual_use"
    return None


def _moment(value: Any) -> datetime | None:
    """A local Warsaw time from the API, as UTC. Deadlines are stated at 16:00 or 12:00
    local, and reading them as UTC would move them by one or two hours."""
    if not value:
        return None
    try:
        naive = datetime.fromisoformat(str(value)[:19])
    except ValueError:
        return None
    return naive.replace(tzinfo=WARSAW).astimezone(UTC)


def opens_at(record: dict[str, Any]) -> date | None:
    start = _moment(record.get("applicationsStartDate"))
    return start.astimezone(WARSAW).date() if start else None


def deadline(record: dict[str, Any]) -> datetime | None:
    return _moment(record.get("applicationsEndDate"))


def status(record: dict[str, Any], *, now: datetime | None = None) -> str:
    """The portal's status where it is unambiguous, the dates where it is not.

    `APPLICATIONS_IN_EVALUATION` and `FINISHED` both mean applications are over, which is
    all the product's `closed` says; the portal's own word is kept in `conditions_raw`.
    """
    now = now or datetime.now(UTC)
    native = record.get("status")
    if native == "APPLICATIONS_IN_PROGRESS":
        return "open"
    start, end = _moment(record.get("applicationsStartDate")), deadline(record)
    if start and start > now:
        return "forthcoming"
    if native is None and end and end > now:
        return "open"
    return "closed"


def parse_budget(text: Any) -> tuple[float | None, str | None]:
    """The sum and its currency from the budget text, or nothing.

    The field is prose: "350 000 000 zl", "1 950 000 euro", "120 000 000,00 zl",
    "nie ma okreslonej alokacji", "100% kosztow kwalifikowanych". A sum is read only when
    a currency follows it directly, so a percentage is never taken for money. Polish
    separates thousands with a space and decimals with a comma.
    """
    match = _MONEY.search(str(text or ""))
    if not match:
        return None, None
    raw = re.sub(r"[\s ]", "", match.group("num"))
    if "," in raw:
        whole, _, fraction = raw.rpartition(",")
        raw = whole.replace(".", "") + "." + fraction if len(fraction) <= 2 else raw.replace(",", "")
    elif raw.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", raw):
        raw = raw.replace(".", "")
    try:
        amount = float(raw)
    except ValueError:
        return None, None
    currency = "EUR" if match.group("cur").lower() in ("euro", "eur", "€") else "PLN"
    return amount, currency


def in_scope(record: dict[str, Any], *, today: date | None = None) -> bool:
    """A competition a supplier could answer, tagged by the publisher, still of interest."""
    today = today or date.today()
    if regime(record) is None or not record.get("path") or not record.get("name"):
        return False
    if not ENTERPRISE & set(applicant_types(record)):
        return False
    now = datetime.combine(today, datetime.min.time(), tzinfo=WARSAW)
    if status(record, now=now) in ("open", "forthcoming"):
        return True
    end = deadline(record)
    if end is not None:
        return end.year == today.year
    announced = _moment(record.get("announcementDate"))
    return bool(announced and announced.year == today.year)


# ----------------------------------------------------------------- the fields

def call_url(record: dict[str, Any]) -> str:
    return f"{SITE}{record['path']}"


def eligibility_text(record: dict[str, Any]) -> str:
    """Who may apply and on what basis, from the structured fields only.

    Never from the competition's own prose: that is CC BY-SA text, and carrying it into
    the product would carry the licence with it.
    """
    parts: list[str] = []
    applicants = [APPLICANT_LABELS.get(a, a) for a in applicant_types(record)]
    if applicants:
        parts.append("Applicants: " + "; ".join(applicants) + ".")
    areas = [AREA_LABELS.get(a, a) for a in thematic_areas(record)]
    if areas:
        parts.append("Thematic areas: " + "; ".join(areas) + ".")
    funding = [f.replace("_", " ") for f in sources_of_funding(record)]
    if funding:
        parts.append("Funding: " + "; ".join(funding) + ".")
    return " ".join(parts)


def conditions(record: dict[str, Any]) -> dict[str, Any]:
    """The structured side of the call. Deliberately without the description."""
    dates: list[dict[str, Any]] = []
    try:
        dates = [{"name": d.get("name"), "value": d.get("value")}
                 for d in json.loads(record.get("dates") or "[]")]
    except (TypeError, ValueError):
        pass
    return {
        "status_native": record.get("status"),
        "programme_types": programme_types(record),
        "thematic_areas": thematic_areas(record),
        "applicant_types": applicant_types(record),
        "sources_of_funding": sources_of_funding(record),
        "budget_text": " ".join(str(record.get("budget") or "").split()) or None,
        "announced": record.get("announcementDate"),
        "results_expected": record.get("resultsDate"),
        "dates": dates,
        "published": record.get("publishDate"),
    }
