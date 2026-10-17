"""CORDIS, the Commission's research project database, through its public SPARQL service.

Why SPARQL and not the bulk files: the CSV, JSON and XML packages that data.europa.eu lists for
Horizon Europe, Horizon 2020 and FP7 all live under https://cordis.europa.eu/data/, which the
site's robots.txt disallows for every crawler. This connector therefore never asks for that path
(`check_robots` refuses to start if the SPARQL path is ever disallowed as well), and reads the same
data from the documented endpoint instead: https://cordis.europa.eu/datalab/sparql (read-only
queries, anonymous, no key). What was found and measured is in docs/sources/cordis.md.

The connector yields pages of plain result rows and does nothing else. Three kinds, each read by a
keyset (the key of the last row of the page), so a page can never skip or repeat a row when the
service answers with its ceiling of 10,000 rows:

    organisations   one row per organisation: PIC, CORDIS record number, legal name, VAT, country
    projects        one row per project: record number, grant number, acronym, title, dates, cost
    roles           one row per participation: project, organisation, role, EU contribution

Nothing of the projects' abstracts, keywords or results is asked for: only commercial facts.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.robotparser import RobotFileParser

import httpx

from . import USER_AGENT, new_client, request_with_retry

log = logging.getLogger(__name__)

SOURCE_CODE = "cordis"
SPARQL_URL = "https://cordis.europa.eu/datalab/sparql"
ROBOTS_URL = "https://cordis.europa.eu/robots.txt"
MIN_INTERVAL = 1.0           # seconds between two requests
PAGE_SIZE = {"organisations": 5000, "projects": 2000, "roles": 5000}

NS = "http://data.europa.eu/s66"
PREFIX = f"PREFIX e: <{NS}#>\n"
_BASE = {"organisations": f"{NS}/resource/organisations/", "projects": f"{NS}/resource/projects/",
         "roles": f"{NS}/resource/organisationroles/"}


_KEY = re.compile(r"[0-9A-Za-z._-]{1,80}")


class RobotsDisallowed(RuntimeError):
    """robots.txt does not allow the path we are about to read."""


def _query(kind: str, after: str, limit: int) -> str:
    base = _BASE[kind]
    keyset = f'FILTER (STR(?x) > "{base}{after}")' if after else ""
    if kind == "organisations":
        return PREFIX + f"""
SELECT (STRAFTER(STR(?x), "{base}") AS ?key) (MIN(?pic) AS ?pic) (MIN(?rcn) AS ?rcn)
       (MIN(?name) AS ?name) (MIN(?vat) AS ?vat) (MIN(?cc) AS ?country)
WHERE {{
  ?x a e:Organisation .
  OPTIONAL {{ ?x e:identifier ?pic }} OPTIONAL {{ ?x e:rcn ?rcn }}
  OPTIONAL {{ ?x e:legalName ?name }} OPTIONAL {{ ?x e:vatNumber ?vat }}
  OPTIONAL {{ ?x e:hasSite ?s . ?s e:hasAddress ?a . ?a e:addressCountry ?cc }}
  {keyset}
}} GROUP BY ?x ORDER BY STR(?x) LIMIT {limit}"""
    if kind == "projects":
        return PREFIX + f"""
SELECT (STRAFTER(STR(?x), "{base}") AS ?key) (MIN(?rcn) AS ?rcn) (MIN(?ga) AS ?ga)
       (MIN(?title) AS ?title) (MIN(?acr) AS ?acronym) (MIN(?sd) AS ?start) (MIN(?ed) AS ?end)
       (MIN(?dur) AS ?duration) (MIN(?st) AS ?status) (MIN(?cost) AS ?cost)
       (MIN(?fund) AS ?fund) (MIN(?call) AS ?call) (MIN(?topic) AS ?topic)
WHERE {{
  ?x a e:Project .
  OPTIONAL {{ ?x e:rcn ?rcn }} OPTIONAL {{ ?x e:identifier ?ga }} OPTIONAL {{ ?x e:title ?title }}
  OPTIONAL {{ ?x e:hasAcronym ?ac . ?ac e:shortForm ?acr }}
  OPTIONAL {{ ?x e:startDate ?sd }} OPTIONAL {{ ?x e:endDate ?ed }}
  OPTIONAL {{ ?x e:duration ?dur }} OPTIONAL {{ ?x e:projectStatus ?st }}
  OPTIONAL {{ ?x e:hasTotalCost ?tc . ?tc e:value ?cost }}
  OPTIONAL {{ ?x e:isFundedBy ?g .
    OPTIONAL {{ ?g e:hasFundingAmount ?fa . ?fa e:value ?fund }}
    OPTIONAL {{ ?g e:hasFundingSchemeCall ?c . ?c e:identifier ?call }}
    OPTIONAL {{ ?g e:hasFundingSchemeTopic ?t . ?t e:identifier ?topic }} }}
  {keyset}
}} GROUP BY ?x ORDER BY STR(?x) LIMIT {limit}"""
    return PREFIX + f"""
SELECT (STRAFTER(STR(?x), "{base}") AS ?key) (MIN(?prcn) AS ?project)
       (MIN(STRAFTER(STR(?o), "{_BASE['organisations']}")) AS ?org) (MIN(?label) AS ?role)
       (SUM(?amt) AS ?amount)
WHERE {{
  ?x a e:OrganisationRole ; e:isInvolvedIn ?p ; e:isRoleOf ?o ; e:roleLabel ?label .
  ?p e:rcn ?prcn .
  OPTIONAL {{ ?x e:isRecipientOf ?gp . ?gp e:hasPaymentAmount ?m . ?m e:value ?amt }}
  {keyset}
}} GROUP BY ?x ORDER BY STR(?x) LIMIT {limit}"""


def _count_query(kind: str) -> str:
    cls = {"organisations": "Organisation", "projects": "Project", "roles": "OrganisationRole"}[kind]
    return PREFIX + f"SELECT (COUNT(DISTINCT ?x) AS ?n) WHERE {{ ?x a e:{cls} }}"


class Sparql:
    """A polite client of the SPARQL service: robots.txt first, one request a second, retries."""

    def __init__(self, client: httpx.Client | None = None, *, min_interval: float = MIN_INTERVAL,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._own = client is None
        self.http = client or new_client(timeout=180, follow_redirects=True,
                                         headers={"User-Agent": USER_AGENT})
        self.min_interval = min_interval
        self._sleep, self._clock = sleep, clock
        self._last = -1e9
        self.requests = 0

    def close(self) -> None:
        if self._own:
            self.http.close()

    def check_robots(self) -> None:
        r = self.http.get(ROBOTS_URL)
        if r.status_code != 200:
            raise RobotsDisallowed(f"robots.txt answered HTTP {r.status_code}; not reading CORDIS")
        parser = RobotFileParser()
        parser.parse(r.text.splitlines())
        if not parser.can_fetch(USER_AGENT, SPARQL_URL):
            raise RobotsDisallowed(f"robots.txt disallows {SPARQL_URL}")

    def select(self, query: str) -> list[dict[str, str]]:
        wait = self.min_interval - (self._clock() - self._last)
        if wait > 0:
            self._sleep(wait)
        self._last = self._clock()
        self.requests += 1

        def send() -> httpx.Response:
            r = self.http.get(SPARQL_URL, params={"query": query},
                              headers={"Accept": "application/sparql-results+json"})
            r.raise_for_status()
            return r

        body = request_with_retry(send, what="cordis sparql").json()
        return [{k: v.get("value", "") for k, v in row.items()}
                for row in body["results"]["bindings"]]

    def count(self, kind: str) -> int:
        return int(self.select(_count_query(kind))[0]["n"])

    def pages(self, kind: str, *, limit: int | None = None) -> Iterator[dict[str, Any]]:
        """Pages of `kind`, each {"kind", "after", "rows"}. Ends on a page shorter than the limit."""
        limit = limit or PAGE_SIZE[kind]
        after = ""
        while True:
            rows = self.select(_query(kind, after, limit))
            if not rows:
                return
            yield {"kind": kind, "after": after, "rows": rows}
            if len(rows) < limit:
                return
            after = rows[-1]["key"]
            if not _KEY.fullmatch(after):
                # the key goes back into the next query as text: only what an identifier looks like
                raise ValueError(f"cordis: unexpected key {after[:40]!r} in a result page")


# ------------------------------------------------------------------ normalisation

_CC = {"UK": "GB", "EL": "GR"}          # CORDIS writes the country codes of the Commission
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]+")
_ROLE = {"coordinator": "coordinator", "participant": "participant", "thirdParty": "third_party",
         "partner": "partner", "associatedPartner": "associated_partner",
         "internationalPartner": "international_partner"}
_PROGRAMME_PREFIX = (("HORIZON", "HORIZON"), ("H2020", "H2020"), ("FP7", "FP7"))


def clean_text(value: Any, limit: int) -> str | None:
    s = _CONTROL.sub(" ", str(value or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit] or None


def _num(value: Any) -> float | None:
    try:
        return round(float(value), 2) if value not in (None, "") else None
    except ValueError:
        return None


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


@dataclass
class OrgRecord:
    key: str                 # the service's own identifier of the organisation, meaningful in one run
    pic: str | None
    name: str
    vat: str | None
    country: str | None


@dataclass
class ProjectRecord:
    rcn: str
    ga_number: str | None
    acronym: str | None
    title: str
    start: date | None
    end: date | None
    duration_months: int | None
    status: str | None
    total_cost: float | None
    eu_contribution: float | None
    call_code: str | None
    topic_code: str | None
    programme: str | None


@dataclass
class RoleRecord:
    project_rcn: str
    org_key: str
    role: str
    contribution: float | None


def country_of(value: Any) -> str | None:
    s = str(value or "").strip().upper()
    if len(s) != 2 or not s.isalpha():
        return None
    return _CC.get(s, s)


def programme_of(topic: str | None, call: str | None, ga: str | None, start: date | None) -> str | None:
    """The framework programme: the topic's prefix, else the call's, else the grant number and
    the start year. The topic and call identifiers say it outright for 99 per cent of projects; the
    rest are older FP7 records that carry neither."""
    for ident in (topic, call):
        head = re.split(r"[_-]", ident or "", maxsplit=1)[0].upper()
        for prefix, code in _PROGRAMME_PREFIX:
            if head == prefix:
                return code
    if start:
        if ga and len(ga) == 9 and ga.startswith("101") and start.year >= 2021:
            return "HORIZON"
        if start.year <= 2013:
            return "FP7"
        if start.year <= 2020:
            return "H2020"
    return None


def org_record(row: dict[str, str]) -> OrgRecord | None:
    name = clean_text(row.get("name"), 300)
    if not row.get("key") or not name:
        return None
    pic = re.sub(r"\D", "", row.get("pic") or "")
    return OrgRecord(row["key"], pic if len(pic) == 9 else None, name,
                     clean_text(row.get("vat"), 30), country_of(row.get("country")))


def project_record(row: dict[str, str]) -> ProjectRecord | None:
    title = clean_text(row.get("title"), 600)
    rcn = (row.get("rcn") or "").strip()
    if not rcn or not title:
        return None
    start = _date(row.get("start"))
    ga = clean_text(row.get("ga"), 20)
    topic, call = clean_text(row.get("topic"), 120), clean_text(row.get("call"), 120)
    cost, fund = _num(row.get("cost")), _num(row.get("fund"))
    dur = _num(row.get("duration"))
    return ProjectRecord(
        rcn=rcn, ga_number=ga, acronym=clean_text(row.get("acronym"), 100), title=title,
        start=start, end=_date(row.get("end")), duration_months=int(dur) if dur else None,
        status=clean_text(row.get("status"), 20), total_cost=cost or None, eu_contribution=fund,
        call_code=call, topic_code=topic, programme=programme_of(topic, call, ga, start))


def role_record(row: dict[str, str]) -> RoleRecord | None:
    role = _ROLE.get(row.get("role") or "")
    if not (row.get("project") and row.get("org") and role):
        return None
    return RoleRecord(row["project"].strip(), row["org"], role, _num(row.get("amount")))
