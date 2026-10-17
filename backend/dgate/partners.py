"""Layer 1 meets layer 2 (WP-32): who took part in earlier projects of the same area as a funding call,
and the document facts the call lists need for the "fits my profile" badge.

    GET /v1/funding/{slug}/partners?country=XX&limit=20   organisations of earlier projects in the call's area
    GET /v1/fit/facts?ids=1,2,3                           the facts the badge compares, for up to 100 calls

Deterministic, no model. Nothing about a visitor is read or stored: the profile stays in the browser
and the badge is computed there; this module only serves public facts about calls and projects.

"Same area", defined (and said in the response, `area.rule`):

  EDF and EDIP calls   the capability category in the topic code (SPACE, CYBER, AIR ...) against the
                       category of the EDF projects read from the factsheets (2023 to 2025 name it;
                       the 2021 and 2022 factsheets do not, so those projects count only at the
                       broader level). A call whose code names no category (the EDIP calls) is
                       compared with all EDF projects.
  Horizon Europe calls the part of the topic code before the year (CL3, EIC, JU-EUROHPC ...) and the
                       destination after it (BM, DRS, FCT ...) against the topic codes of the
                       Horizon Europe projects in CORDIS; the part alone if the destination has too
                       few organisations.
  anything else        no area: Digital Europe, CEF and the national programmes have no project
                       data here, and the answer says so.

The narrower level is used when it holds at least MIN_ORGS organisations, otherwise the broader one,
and the response names the level it used. Organisations are read through `merged_into`, an
organisation removed on request is left out, and only organisations are named (never a person).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from . import db, eligibility
from .config import settings
from .funding import SOURCE_TEXT_SOURCES, make_slug
from .listcache import cache_list
from .normalise import redact_emails
from .sources import edf_factsheets
from .suppress import removed

router = APIRouter()

MIN_ORGS = 5                 # the narrower level needs this many organisations, or the broader one is used
MAX_LIMIT = 50
MAX_FIT_IDS = 100
EVIDENCE_PER_PARTNER = 3

# The facts the "fits my profile" badge compares (lib/eligibility-check.ts reads these and no others).
FIT_FACTS = ("eligible_countries", "sme_only", "natural_persons_allowed", "consortium_required",
             "min_entities", "min_countries", "ownership_control_restriction")

_SAFE = re.compile(r"^[A-Z0-9-]{1,40}$")
_YEAR = re.compile(r"^20\d\d$")


def get_conn():
    cfg = settings()
    with db.connect(cfg.api_dsn or cfg.dsn) as conn:
        yield conn


# ----------------------------------------------------------------------------- the area of a call

@dataclass(frozen=True)
class Area:
    kind: str            # edf-category | edf | horizon-destination | horizon-family
    label: str           # said to the visitor
    rule: str            # how projects are matched, in a sentence
    source: str          # the source whose projects are compared
    category: str | None = None
    like: str | None = None      # upper-case LIKE prefix of the project's topic code
    regex: str | None = None     # upper-case regular expression on the project's topic code


def areas_of(topic_code: str | None) -> list[Area]:
    """The areas a call belongs to, narrowest first. Empty when its code names no area the project
    data can be compared with."""
    tokens = (topic_code or "").upper().strip().split("-")
    if len(tokens) < 3 or any(not t or not re.fullmatch(r"[A-Z0-9]+", t) for t in tokens):
        return []
    if tokens[0] == "EDF":
        category = next((t for t in tokens[1:] if t in edf_factsheets.CATEGORIES), None)
        broad = Area("edf", "all projects of the European Defence Fund",
                     "All EDF projects read from the factsheets of the call results, 2021 onwards.",
                     edf_factsheets.SOURCE_CODE)
        if category is None:
            return [broad]
        return [Area("edf-category", f"EDF capability category {category}",
                     f"EDF projects whose factsheet file name names the category {category}, as this call's topic code does.",
                     edf_factsheets.SOURCE_CODE, category=category), broad]
    if tokens[0] == "HORIZON":
        year = next((i for i, t in enumerate(tokens) if i >= 2 and _YEAR.match(t)), None)
        if year is None:
            return []
        family = "-".join(tokens[1:year])
        if not _SAFE.match(family):
            return []
        rest = tokens[year + 1:]
        if len(rest) > 1 and re.fullmatch(r"\d{2}", rest[0]) and rest[1].isalpha():
            rest = rest[1:]                     # the call round: 2026-01-BM-01 is round 01, destination BM
        wide = Area("horizon-family", f"Horizon Europe, {family}",
                    f"Horizon Europe projects in CORDIS whose topic code starts HORIZON-{family}-<year>.",
                    "cordis", like=f"HORIZON-{family}-%", regex=rf"^HORIZON-{family}-[0-9]{{4}}-")
        dest = rest[0] if rest and rest[0].isalpha() else None
        if dest is None:
            return [wide]
        return [Area("horizon-destination", f"Horizon Europe, {family}, destination {dest}",
                     f"Horizon Europe projects in CORDIS whose topic code reads HORIZON-{family}-<year>-{dest}-..., as this call's does.",
                     "cordis", like=f"HORIZON-{family}-%",
                     regex=rf"^HORIZON-{family}-[0-9]{{4}}-([0-9]{{2}}-)?{dest}-"), wide]
    return []


def area_label(topic_code: str | None) -> str | None:
    """The narrowest area of a call as a label, from its code alone (no database): what the call
    page needs to decide whether to offer partner suggestions."""
    found = areas_of(topic_code)
    return found[0].label if found else None


# ----------------------------------------------------------------------------- the queries

_YEAR_EXPR = "COALESCE(EXTRACT(YEAR FROM pr.start_date)::int, pr.call_year)"
_LIVE = """
  FROM project pr
  JOIN participation pa ON pa.project_id = pr.id AND pa.active
  JOIN organisation o ON o.id = pa.organisation_id AND NOT o.suppressed
  JOIN organisation head ON head.id = COALESCE(o.merged_into, o.id)
 WHERE head.merged_into IS NULL AND NOT head.suppressed AND {where}"""


def _where(area: Area, source_id: int) -> tuple[str, list[Any]]:
    clauses, params = ["pr.source_id = %s"], [source_id]
    if area.category:
        clauses.append("pr.category = %s")
        params.append(area.category)
    if area.like:
        clauses.append("upper(pr.topic_code) LIKE %s")
        params.append(area.like)
    if area.regex:
        clauses.append("upper(pr.topic_code) ~ %s")
        params.append(area.regex)
    return " AND ".join(clauses), params


def _pick(conn, areas: list[Area]) -> tuple[Area, dict[str, int], list[Any], str] | None:
    """The narrowest area with enough organisations (else the broadest that has any): the area,
    its organisations by country, and the SQL condition that selects its projects."""
    sources = {r["code"]: r["id"] for r in conn.execute(
        "SELECT id, code FROM source WHERE code = ANY(%s)", ([a.source for a in areas],)).fetchall()}
    chosen = None
    for i, area in enumerate(areas):
        if area.source not in sources:
            continue
        where, params = _where(area, sources[area.source])
        by_country = {r["country"]: r["n"] for r in conn.execute(
            f"SELECT head.country, count(DISTINCT head.id) AS n{_LIVE.format(where=where)} "
            "GROUP BY head.country ORDER BY n DESC, head.country", params).fetchall()}
        chosen = (area, by_country, params, where)
        if sum(by_country.values()) >= MIN_ORGS or i == len(areas) - 1:
            break
    # The areas are nested (a category is part of the programme, a destination part of its cluster), so an
    # empty broadest area means there is nothing at any level.
    return chosen if chosen and chosen[1] else None


def partners_of(conn, topic_code: str | None, *, country: str | None = None, limit: int = 20) -> dict[str, Any]:
    areas = areas_of(topic_code)
    base: dict[str, Any] = {"area": None, "partners": [], "countries": [], "total": 0, "country": country}
    if not areas:
        base["note"] = ("No earlier projects can be compared with this call: the funding programmes of Digital Europe, "
                        "CEF and the national calls are not in the project data we hold.")
        return base
    picked = _pick(conn, areas)
    if picked is None:
        base["area"] = {"kind": areas[0].kind, "label": areas[0].label, "rule": areas[0].rule, "projects": 0,
                        "organisations": 0, "firstYear": None, "lastYear": None, "broaderThanCall": False}
        base["note"] = "No earlier project of this area is held yet."
        return base
    area, by_country, params, where = picked
    live = _LIVE.format(where=where)
    span = conn.execute(
        f"SELECT count(DISTINCT pr.id) AS n, min({_YEAR_EXPR}) AS first, max({_YEAR_EXPR}) AS last{live}", params).fetchone()
    flt, fparams = ("AND head.country = %s", [country]) if country else ("", [])
    rows = conn.execute(
        f"""SELECT head.id, head.display_name, head.canonical_name, head.country,
                   count(DISTINCT pr.id) AS projects,
                   count(DISTINCT pr.id) FILTER (WHERE pa.role = 'coordinator') AS coordinated,
                   min({_YEAR_EXPR}) AS first, max({_YEAR_EXPR}) AS last{live} {flt}
             GROUP BY head.id
             ORDER BY projects DESC, max({_YEAR_EXPR}) DESC NULLS LAST, coordinated DESC, head.id
             LIMIT %s""", [*params, *fparams, limit]).fetchall()
    ids = [r["id"] for r in rows]
    evidence: dict[int, list[dict[str, Any]]] = {i: [] for i in ids}
    if ids:
        for e in conn.execute(
                f"""SELECT * FROM (
                      SELECT x.*, row_number() OVER (PARTITION BY org ORDER BY year DESC NULLS LAST, project DESC) AS rn
                        FROM (SELECT DISTINCT ON (head.id, pr.id) head.id AS org, pr.id AS project, pr.acronym,
                                     left(pr.title, 160) AS title, {_YEAR_EXPR} AS year, pa.role{live}
                                 AND head.id = ANY(%s)
                               ORDER BY head.id, pr.id, (pa.role = 'coordinator') DESC) x) y
                     WHERE rn <= %s ORDER BY org, rn""",
                [*params, ids, EVIDENCE_PER_PARTNER]).fetchall():
            evidence[e["org"]].append({"projectId": str(e["project"]), "acronym": e["acronym"], "title": e["title"],
                                       "year": e["year"], "role": e["role"]})
    total_orgs = sum(by_country.values())
    return {
        "area": {"kind": area.kind, "label": area.label, "rule": area.rule, "projects": span["n"],
                 "organisations": total_orgs, "firstYear": span["first"], "lastYear": span["last"],
                 # The narrower area had too few organisations, so the broader one answered.
                 "broaderThanCall": area is not areas[0]},
        "partners": [{
            "organisationId": str(r["id"]),
            "slug": make_slug(r["id"], r["display_name"] or r["canonical_name"]),
            "name": redact_emails(r["display_name"] or r["canonical_name"]),
            "country": r["country"], "projects": r["projects"], "coordinated": r["coordinated"],
            "firstYear": r["first"], "lastYear": r["last"], "evidence": evidence[r["id"]],
        } for r in rows],
        "countries": [{"country": c, "organisations": n} for c, n in list(by_country.items())[:40]],
        "total": by_country.get(country, 0) if country else total_orgs,
        "country": country,
        "note": None,
    }


def _sources_read_at(conn) -> dict[str, Any]:
    r = conn.execute(
        """SELECT max(r.finished_at) AS at FROM ingest_run r JOIN source s ON s.id = r.source_id
            WHERE s.code IN ('cordis', 'edf_factsheets') AND r.status IN ('success', 'partial')""").fetchone()
    return {"readAt": r["at"] if r else None,
            "sources": ["CORDIS, European Commission", "European Commission, DG DEFIS, EDF results factsheets"],
            "licence": "Commission Decision 2011/833/EU (reuse of Commission documents)"}


def _id_of(slug: str) -> int:
    m = re.match(r"^([0-9]{1,9})(?:-|$)", slug, re.ASCII)
    if not m:
        raise HTTPException(404, "no such call")
    return int(m.group(1))


@router.get("/v1/funding/{slug}/partners")
@cache_list("partners", ttl=10 * 60)
def get_partners(
    slug: str,
    country: str | None = Query(None, pattern=r"^[A-Za-z]{2}$"),
    limit: int = Query(20, ge=1, le=MAX_LIMIT),
    conn=Depends(get_conn),
):
    row = conn.execute(
        "SELECT c.id, c.title, c.topic_code, c.suppressed FROM call c WHERE c.id = %s", (_id_of(slug),)).fetchone()
    if not row:
        raise HTTPException(404, "no such call")
    if row["suppressed"]:
        raise removed()
    out = partners_of(conn, row["topic_code"], country=country.upper() if country else None, limit=limit)
    out["call"] = {"id": str(row["id"]), "slug": make_slug(row["id"], row["title"]), "topic": row["topic_code"]}
    out["source"] = _sources_read_at(conn)
    return out


# ----------------------------------------------------------------------------- facts for the badge

@router.get("/v1/fit/facts")
def fit_facts(ids: str = Query(..., min_length=1, max_length=1200, pattern=r"^[0-9]{1,9}(,[0-9]{1,9})*$"),
              conn=Depends(get_conn)):
    """The document facts the browser compares with the saved profile, for the calls of one list page.
    The same facts, under the same source rule, as the call page serves; without the quotes."""
    wanted = list(dict.fromkeys(int(i) for i in ids.split(",")))
    if len(wanted) > MAX_FIT_IDS:
        raise HTTPException(422, f"at most {MAX_FIT_IDS} calls at a time")
    rows = conn.execute(
        """SELECT c.id, c.conditions_raw, c.eligibility_text, s.code AS source_code, s.commercial_ok
             FROM call c LEFT JOIN source s ON s.id = c.source_id
            WHERE c.id = ANY(%s) AND NOT c.suppressed""", (wanted,)).fetchall()
    servable = [r for r in rows if r["source_code"] in SOURCE_TEXT_SOURCES and r["commercial_ok"] is True]
    read = eligibility.read_many(conn, [(r["id"], r["conditions_raw"] or {}, r["eligibility_text"]) for r in servable]) \
        if servable else {}
    items: dict[str, Any] = {}
    for r in rows:
        got = read.get(r["id"])
        if got is None:
            items[str(r["id"])] = {"state": "no_source", "basis": None, "facts": {}}
            continue
        items[str(r["id"])] = {
            "state": got["state"], "basis": got["basis"],
            "facts": {k: {"value": f["value"], "note": redact_emails(f.get("note")), "scope": f["scope"]}
                      for k, f in got["facts"].items() if k in FIT_FACTS},
        }
    return {"items": items}
