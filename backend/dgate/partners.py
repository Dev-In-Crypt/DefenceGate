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
                       destination after it (BM, DRS, FCT ...) against the call codes of the
                       Horizon Europe projects in CORDIS (`HORIZON-CL3-2023-BM-01`; their topic codes
                       carry a `HORIZON_` prefix, so the call code is the clean one); the part alone
                       if the destination has too few organisations.
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
from .funding import SOURCE_TEXT_SOURCES, make_slug, programme_of
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
FIT_FACTS = ("eligible_countries", "entity_types", "sme_only", "natural_persons_allowed", "consortium_required",
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
    like: str | None = None      # upper-case LIKE prefix of the project's call code
    regex: str | None = None     # upper-case regular expression on the project's call code


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
                    f"Horizon Europe projects in CORDIS whose call code starts HORIZON-{family}-<year>.",
                    "cordis", like=f"HORIZON-{family}-%", regex=rf"^HORIZON-{family}-[0-9]{{4}}-")
        dest = rest[0] if rest and rest[0].isalpha() else None
        if dest is None:
            return [wide]
        return [Area("horizon-destination", f"Horizon Europe, {family}, destination {dest}",
                     f"Horizon Europe projects in CORDIS whose call code reads HORIZON-{family}-<year>-{dest}-..., as this call's topic code does.",
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


def _area_projects(conn, area: Area, source_id: int) -> list[dict[str, Any]]:
    """The projects of an area: one light query on `project` (the indexes of migration 0070), at most a few
    thousand rows. The heavy join then starts from these ids."""
    clauses, params = ["pr.source_id = %s"], [source_id]
    if area.category:
        clauses.append("pr.category = %s")
        params.append(area.category)
    if area.like:
        clauses.append("upper(pr.call_code) LIKE %s")
        params.append(area.like)
    if area.regex:
        clauses.append("upper(pr.call_code) ~ %s")
        params.append(area.regex)
    return conn.execute(f"SELECT pr.id, {_YEAR_EXPR} AS year FROM project pr WHERE {' AND '.join(clauses)}", params).fetchall()


def _organisations(conn, project_ids: list[int]) -> list[dict[str, Any]]:
    """Every live organisation that took part in these projects, once: its projects, those it coordinated, its years, and
    the ids of the rows merged into it (their participations count for it, a project once). One query; the ranking
    and the country filter are done on its rows, so the cost does not grow with the number of countries asked for."""
    return conn.execute(
        f"""SELECT head.id, head.display_name, head.canonical_name, head.country,
                   count(DISTINCT pr.id) AS projects,
                   count(DISTINCT pr.id) FILTER (WHERE pa.role = 'coordinator') AS coordinated,
                   min({_YEAR_EXPR}) AS first, max({_YEAR_EXPR}) AS last,
                   array_agg(DISTINCT o.id) AS members
              FROM project pr
              JOIN participation pa ON pa.project_id = pr.id AND pa.active
              JOIN organisation o ON o.id = pa.organisation_id AND NOT o.suppressed
              JOIN organisation head ON head.id = COALESCE(o.merged_into, o.id)
             WHERE pr.id = ANY(%s) AND head.merged_into IS NULL AND NOT head.suppressed
             GROUP BY head.id""", (project_ids,)).fetchall()


def _evidence(conn, project_ids: list[int], heads: dict[int, list[int]]) -> dict[int, list[dict[str, Any]]]:
    """The newest projects of each listed organisation: from its own participations (an index on the organisation),
    not from a second pass over the whole area."""
    owner = {m: h for h, members in heads.items() for m in members}
    rows = conn.execute(
        f"""SELECT DISTINCT ON (pa.organisation_id, pr.id) pa.organisation_id AS member, pr.id AS project, pr.acronym,
                   left(pr.title, 160) AS title, {_YEAR_EXPR} AS year, pa.role
              FROM participation pa JOIN project pr ON pr.id = pa.project_id
             WHERE pa.organisation_id = ANY(%s) AND pa.active AND pr.id = ANY(%s)
             ORDER BY pa.organisation_id, pr.id""", (list(owner), project_ids)).fetchall()
    seen: dict[int, dict[int, dict[str, Any]]] = {h: {} for h in heads}
    for r in rows:
        head = owner[r["member"]]
        known = seen[head].get(r["project"])
        if known is None or (r["role"] == "coordinator" and known["role"] != "coordinator"):
            seen[head][r["project"]] = {"projectId": str(r["project"]), "acronym": r["acronym"], "title": r["title"],
                                        "year": r["year"], "role": r["role"]}
    return {h: sorted(found.values(), key=lambda e: (-(e["year"] or 0), -int(e["projectId"])))[:EVIDENCE_PER_PARTNER]
            for h, found in seen.items()}


def partners_of(conn, topic_code: str | None, *, country: str | None = None, limit: int = 20) -> dict[str, Any]:
    areas = areas_of(topic_code)
    base: dict[str, Any] = {"area": None, "partners": [], "countries": [], "total": 0, "country": country}
    if not areas:
        base["note"] = ("No earlier projects can be compared with this call: the funding programmes of Digital Europe, "
                        "CEF and the national calls are not in the project data we hold.")
        return base
    sources = {r["code"]: r["id"] for r in conn.execute(
        "SELECT id, code FROM source WHERE code = ANY(%s)", ([a.source for a in areas],)).fetchall()}
    # The narrowest area with enough organisations; else the broadest. The areas are nested (a category is part of the
    # programme, a destination part of its cluster), so an empty broadest area means there is nothing at any level.
    chosen = None
    for i, area in enumerate(areas):
        if area.source not in sources:
            continue
        found = _area_projects(conn, area, sources[area.source])
        orgs = _organisations(conn, [r["id"] for r in found]) if found else []
        chosen = (area, found, orgs)
        if len(orgs) >= MIN_ORGS or i == len(areas) - 1:
            break
    if chosen is None or not chosen[2]:
        base["area"] = {"kind": areas[0].kind, "label": areas[0].label, "rule": areas[0].rule, "projects": 0,
                        "organisations": 0, "firstYear": None, "lastYear": None, "broaderThanCall": False}
        base["note"] = "No earlier project of this area is held yet."
        return base
    area, found, orgs = chosen
    by_country: dict[str, int] = {}
    for o in orgs:
        by_country[o["country"]] = by_country.get(o["country"], 0) + 1
    listed = sorted((o for o in orgs if not country or o["country"] == country),
                    key=lambda o: (-o["projects"], -(o["last"] or 0), -o["coordinated"], o["id"]))[:limit]
    evidence = _evidence(conn, [r["id"] for r in found], {o["id"]: o["members"] for o in listed}) if listed else {}
    years = [r["year"] for r in found if r["year"]]
    return {
        "area": {"kind": area.kind, "label": area.label, "rule": area.rule, "projects": len(found),
                 "organisations": len(orgs), "firstYear": min(years, default=None), "lastYear": max(years, default=None),
                 # The narrower area had too few organisations, so the broader one answered.
                 "broaderThanCall": area is not areas[0]},
        "partners": [{
            "organisationId": str(o["id"]),
            "slug": make_slug(o["id"], o["display_name"] or o["canonical_name"]),
            "name": redact_emails(o["display_name"] or o["canonical_name"]),
            "country": o["country"], "projects": o["projects"], "coordinated": o["coordinated"],
            "firstYear": o["first"], "lastYear": o["last"], "evidence": evidence[o["id"]],
        } for o in listed],
        "countries": [{"country": c, "organisations": n}
                      for c, n in sorted(by_country.items(), key=lambda kv: (-kv[1], kv[0]))[:40]],
        "total": by_country.get(country, 0) if country else len(orgs),
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
    """The document facts the browser compares with the saved profile, for the calls of one list page, and the
    programme and topic code of each call (which decide whose rules apply to it). The same facts, under the same
    source rule, as the call page serves; without the quotes."""
    wanted = list(dict.fromkeys(int(i) for i in ids.split(",")))
    if len(wanted) > MAX_FIT_IDS:
        raise HTTPException(422, f"at most {MAX_FIT_IDS} calls at a time")
    rows = conn.execute(
        """SELECT c.id, c.topic_code, c.conditions_raw, c.eligibility_text, pr.code AS programme_code,
                  s.code AS source_code, s.commercial_ok
             FROM call c JOIN programme pr ON pr.id = c.programme_id LEFT JOIN source s ON s.id = c.source_id
            WHERE c.id = ANY(%s) AND NOT c.suppressed""", (wanted,)).fetchall()
    servable = [r for r in rows if r["source_code"] in SOURCE_TEXT_SOURCES and r["commercial_ok"] is True]
    read = eligibility.read_many(conn, [(r["id"], r["conditions_raw"] or {}, r["eligibility_text"]) for r in servable]) \
        if servable else {}
    items: dict[str, Any] = {}
    for r in rows:
        # Which programme's rules judge the call is decided by the browser from these two (lib/fit.ts programmesOfCall).
        which = {"programme": programme_of(r["programme_code"]), "topic": r["topic_code"]}
        got = read.get(r["id"])
        if got is None:
            items[str(r["id"])] = {"state": "no_source", "basis": None, "facts": {}, **which}
            continue
        items[str(r["id"])] = {
            **which, "state": got["state"], "basis": got["basis"],
            "facts": {k: {"value": f["value"], "note": redact_emails(f.get("note")), "scope": f["scope"]}
                      for k, f in got["facts"].items() if k in FIT_FACTS},
        }
    return {"items": items}
