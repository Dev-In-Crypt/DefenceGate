"""Layer 2 for the user (WP-28): who took part in which funded project, with whom, for how much.

    GET /v1/organisations                      the directory (one row per live organisation in a project)
    GET /v1/organisations/slugs                the biggest, for the sitemap
    GET /v1/organisations/{slug}               the profile
    GET /v1/organisations/{slug}/funding       EU contribution per programme and year
    GET /v1/organisations/{slug}/partners      neighbours: who shared projects with it
    GET /v1/organisations/{slug}/projects      its projects, with role and contribution
    GET /v1/projects/{slug}                    the consortium of one project
    GET /v1/projects/{slug}/history            consortium changes (`consortium_change`)
    GET /v1/projects/slugs                     the EDF projects, for the sitemap
    GET /v1/analytics/ukraine-partners         coordinators with a participant established in Ukraine
    GET /v1/analytics/consortium-gaps          repeat participants of a capability area, none partnered with country X

Rules every endpoint keeps:

  - Organisation-level facts only: a name, a country, the PIC, roles, amounts, years. No contact, no person.
  - An organisation merged into another (`organisation.merged_into`) is its live row everywhere; participations
    are not re-pointed by a merge, so a reader goes through `organisation_merged_live`/`dgate_live_org`.
  - An organisation removed on request (`organisation.suppressed`) has no page (410), is left out of lists and
    is named "Name withheld on request" inside someone else's consortium. One the directory treats as a natural
    person (`organisation.individual_reason`, `individuals.py`, WP-39) is handled the same way, named "Name not
    shown", and is left out of `organisation_network`, which is what the directory, the partner lists and the
    sitemap read.
  - Only `participation.active` counts: a participant a later load no longer finds is history, not a member.
  - The directory reads `organisation_network` (derived, migration 0068, rebuilt after every load); everything
    else reads the participations themselves.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query

from . import textsearch
from .classify import CORE_SQL, DEFENCE_PROGRAMMES
from .funding import get_conn, make_slug
from .listcache import cache_list
from .normalise import http_url, redact_emails
from .suppress import INDIVIDUAL_NAME, WITHHELD_NAME, not_published, removed
from .tenders import _buyer_names, _id_of, search_words

router = APIRouter()

ROLES = ("coordinator", "participant", "partner", "associated_partner", "international_partner",
         "third_party")
PHONE_LIKE = re.compile(r"\d[\d\s().+-]{6,}\d")      # a name that carries a telephone number is not an organisation name
PROGRAMME_CODE = re.compile(r"^[A-Z0-9_-]{1,20}$")
MAX_OFFSET = 10_000          # the deepest position of a list that is served (as in api.py)
COUNT_CAP = 10_000            # a directory total above this is shown as "10,000+" (`totalExact: false`)
MAX_PAGE_SIZE = 100
SLUG_LIMIT = 2000
YEAR = "COALESCE(extract(year FROM p.start_date)::int, p.call_year::int)"
LIVE = "COALESCE(l.live_id, pa.organisation_id)"      # over `participation pa LEFT JOIN organisation_merged_live l`
NAME = "COALESCE(o.display_name, o.canonical_name)"
DEFAULT_SINCE = 2021          # the start of the EDF and of Horizon Europe

SOURCES = ("cordis", "edf_factsheets")
SOURCE_NOTE = {
    "cordis": "Participants and amounts as the Commission's CORDIS database states them (reuse under "
              "Commission Decision 2011/833/EU).",
    "edf_factsheets": "European Defence Fund participants are read from the project factsheets that DG DEFIS "
                      "publishes, by a language model; every name is checked against the factsheet text and a "
                      "name that is not in it is dropped. The factsheets state no amount per participant.",
}
# What an EDF-only number means; shown wherever an amount is.
AMOUNT_NOTE = ("EU contribution is the amount CORDIS's open data pays to the participant. For a participant with "
               "linked third parties it may include their share (the CORDIS page prints the net); an amount the data "
               "does not hold is left out, not counted as zero. EDF factsheets state none per participant, so EDF "
               "projects count as projects but add nothing to the amounts.")


def _num(v: Any) -> float | None:
    return None if v is None else float(v)


def _clean(text: str | None) -> str:
    return redact_emails(text or "")


def _org_name(r: dict[str, Any]) -> str:
    return _clean(r.get("display_name") or r.get("canonical_name"))


def org_ref(r: dict[str, Any], *, id_key: str = "id") -> dict[str, Any]:
    """An organisation as another record names it: id, slug, name, country. One removed on request is
    named as such and carries no link."""
    if r.get("suppressed") or r.get("individual"):
        return {"id": None, "slug": None, "name": INDIVIDUAL_NAME if r.get("individual") else WITHHELD_NAME,
                "country": None}
    oid = r[id_key]
    name = _org_name(r)
    return {"id": str(oid), "slug": make_slug(oid, name), "name": name,
            "country": (r.get("country") or None)}


def _bad(msg: str) -> HTTPException:
    return HTTPException(422, msg)


def _codes(value: str | None, name: str, *, pattern: re.Pattern[str] | None = None,
           allowed: tuple[str, ...] | None = None, upper: bool = True, max_items: int = 10) -> list[str]:
    items = [i.strip() for i in (value or "").split(",") if i.strip()]
    if len(items) > max_items:
        raise _bad(f"{name}: at most {max_items} values")
    out = []
    for i in items:
        i = i.upper() if upper else i.lower()
        if (allowed is not None and i not in allowed) or (pattern is not None and not pattern.match(i)):
            raise _bad(f"{name}: unknown value {i[:20]!r}")
        out.append(i)
    return out


# What the numbers of a directory row are: `defenceProjects` counts the defence programmes only, the others all.
COUNTS_NOTE = ("defenceProjects counts the projects of the defence programmes (European Defence Fund, EDIDP, PADR); "
               "projects, coordinated and euContribution count every programme, civil research included.")


def _sources(conn, codes: tuple[str, ...] = SOURCES) -> list[dict[str, Any]]:
    """Where the data comes from and when it was last read (the newest finished run)."""
    rows = conn.execute(
        """SELECT s.code, s.name, s.licence, s.attribution,
                  max(r.finished_at) FILTER (WHERE r.status IN ('success', 'partial')) AS read_at
             FROM source s LEFT JOIN ingest_run r ON r.source_id = s.id
            WHERE s.code = ANY(%s) GROUP BY s.id ORDER BY s.code""", (list(codes),)).fetchall()
    return [{"code": r["code"], "name": r["name"], "licence": r["licence"],
             "attribution": r["attribution"], "readAt": r["read_at"],
             "note": SOURCE_NOTE.get(r["code"], "")} for r in rows]


# ================================================================== directory

# WP-91 (UX audit 6: a drone start-up could search organisations by name only). The words of a project the topic search reads:
# its acronym, title and EDF capability category, folded as `dg_fold` folds: the stored column and trigram index of migration 0107.
PROJECT_TOPIC_TEXT = "topic_fold"
MAX_TOPIC_WORDS = 4


def topic_alternatives(topic: str | None) -> list[list[str]]:
    """For each word of a topic search (at most MAX_TOPIC_WORDS, stop words dropped), the word and its synonyms
    (textsearch.SYNONYMS): a project matches when its text holds, for every word, one of them at the start of a word."""
    query = textsearch.parse((topic or "").replace("\x00", ""))
    if query is None:
        return []
    return [[" ".join(alt) for alt in group] for group in query.alternatives[:MAX_TOPIC_WORDS]]


def _directory_where(country: str | None, programme: str | None, role: str | None, q: str | None,
                     min_projects: int, topic: str | None = None) -> tuple[str, list[Any]]:
    where, params = ["projects >= %s"], [min_projects]
    countries = _codes(country, "country", pattern=re.compile(r"^[A-Z]{2}$"), max_items=20)
    if countries:
        where.append("country = ANY(%s)")
        params.append(countries)
    programmes = _codes(programme, "programme", pattern=PROGRAMME_CODE)
    if programmes:
        where.append("programmes && %s::text[]")
        params.append(programmes)
    roles = _codes(role, "role", allowed=ROLES, upper=False)
    if roles:
        where.append("roles && %s::text[]")
        params.append(roles)
    for w in search_words((q or "").replace("\x00", "").strip()):
        where.append("dg_fold(name) LIKE dg_word_pattern(%s)")
        params.append(w)
    groups = topic_alternatives(topic)
    if groups:
        # the organisations (live, through merges) with an active participation in a project whose text has every word
        parts: list[str] = []
        for g in groups:
            ors = []
            for alt in g:
                # a word of up to three letters is a whole word (as textsearch: "AI" is not "aircraft"); longer, a word start
                if len(alt) <= 3:
                    ors.append(f"({PROJECT_TOPIC_TEXT} LIKE dg_word_pattern(%s) AND "
                               f"({PROJECT_TOPIC_TEXT} || ' ') LIKE rtrim(dg_word_pattern(%s), '%%') || ' %%')")
                    params.extend([alt, alt])
                else:
                    ors.append(f"{PROJECT_TOPIC_TEXT} LIKE dg_word_pattern(%s)")
                    params.append(alt)
            parts.append("(" + " OR ".join(ors) + ")")
        where.append(f"""organisation_id IN (
            SELECT COALESCE(l.live_id, pa.organisation_id) FROM participation pa
              LEFT JOIN organisation_merged_live l ON l.id = pa.organisation_id
             WHERE pa.active AND pa.project_id IN (SELECT id FROM project WHERE {" AND ".join(parts)}))""")
    return " AND ".join(where), params


def directory_sort(sort: str | None, programme: str | None) -> str:
    """The order of the directory. Asked for outright: `projects` (all programmes), `defence`, `name`. Not asked
    for: by the defence-relevant count when the list is limited to the defence programmes, which is what it is
    about (the all-programme total put CNRS, 4,336 projects of which 10 in the EDF, above the firms that build
    defence projects); otherwise by all projects."""
    if sort:
        return sort
    chosen = _codes(programme, "programme", pattern=PROGRAMME_CODE)
    return "defence" if chosen and set(chosen) <= set(DEFENCE_PROGRAMMES) else "projects"


ORDER = {"name": "name, organisation_id", "projects": "projects DESC, organisation_id",
         "defence": "defence_projects DESC, projects DESC, organisation_id"}


@router.get("/v1/organisations")
@cache_list("organisations", ttl=5 * 60)
def list_organisations(
    country: str | None = Query(None, max_length=200, description="comma-separated ISO-2"),
    programme: str | None = Query(None, max_length=200, description="comma-separated programme codes, e.g. EDF,HORIZON"),
    role: str | None = Query(None, max_length=200, description="coordinator, participant, partner, ..."),
    q: str | None = Query(None, max_length=100),
    topic: str | None = Query(None, max_length=100, description="words of the projects' titles (acronym and EDF category too)"),
    minProjects: int = Query(1, ge=1, le=100_000),
    sort: str | None = Query(None, pattern="^(projects|defence|name)$",
                             description="projects = all programmes; defence = EDF, EDIDP, PADR projects; "
                                         "default: defence when the programme filter is defence-only, else projects"),
    page: int = Query(1, ge=1, le=1000),
    pageSize: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    conn=Depends(get_conn),
):
    if (page - 1) * pageSize > MAX_OFFSET:
        raise _bad(f"page: results beyond the first {MAX_OFFSET:,} are not served; narrow the filters")
    where, params = _directory_where(country, programme, role, q, minProjects, topic if isinstance(topic, str) else None)
    sort = directory_sort(sort, programme)
    order = ORDER[sort]
    rows = conn.execute(
        f"""SELECT organisation_id, name, country, projects, defence_projects, coordinated, eu_contribution, first_year,
                   last_year, programmes, family_variants, refreshed_at
              FROM organisation_network WHERE {where}
             ORDER BY {order} LIMIT %s OFFSET %s""", params + [pageSize, (page - 1) * pageSize]).fetchall()
    if rows and len(rows) < pageSize:
        total = (page - 1) * pageSize + len(rows)
    elif not rows and page == 1:
        total = 0
    else:
        # Capped: counting every match of a broad word ("university") took 1.5 s on 200,000 rows.
        total = conn.execute(
            f"SELECT count(*) AS n FROM (SELECT 1 FROM organisation_network WHERE {where} "
            f"LIMIT {COUNT_CAP + 1}) t", params).fetchone()["n"]
    exact = total <= COUNT_CAP
    refreshed = conn.execute("SELECT refreshed_at FROM organisation_network LIMIT 1").fetchone()
    return {
        "items": [{
            "id": str(r["organisation_id"]),
            "slug": make_slug(r["organisation_id"], _clean(r["name"])),
            "name": _clean(r["name"]), "country": r["country"], "projects": r["projects"],
            "defenceProjects": r["defence_projects"], "coordinated": r["coordinated"], "euContribution": _num(r["eu_contribution"]),
            "firstYear": r["first_year"], "lastYear": r["last_year"], "programmes": r["programmes"],
            "nameVariants": r["family_variants"],
        } for r in rows],
        "total": min(total, COUNT_CAP), "totalExact": exact, "page": page, "pageSize": pageSize,
        "meta": {"updatedAt": refreshed["refreshed_at"] if refreshed else None,
                 "sources": _sources(conn), "amountNote": AMOUNT_NOTE, "sort": sort,
                 "defenceProgrammes": list(DEFENCE_PROGRAMMES), "countsNote": COUNTS_NOTE},
    }


@router.get("/v1/organisations/slugs")
def organisation_slugs(conn=Depends(get_conn)):
    """The organisations with the most projects (at least three), for the sitemap."""
    rows = conn.execute(
        """SELECT organisation_id, name, refreshed_at FROM organisation_network
            WHERE projects >= 3 ORDER BY projects DESC, organisation_id LIMIT %s""", (SLUG_LIMIT,)).fetchall()
    return [{"slug": make_slug(r["organisation_id"], _clean(r["name"])), "updatedAt": r["refreshed_at"]}
            for r in rows]


# ================================================================== one organisation

def live_organisation(conn, slug: str) -> dict[str, Any]:
    """The organisation behind a slug, followed through `merged_into` to its live row, with the ids whose
    participations are its own (itself and everything merged into it, minus any removed on request).
    404 when there is none or it has no participation; 410 when it was removed on request or is a natural person."""
    org_id = _id_of(slug, "organisation")
    row = conn.execute(
        """SELECT o.id, o.canonical_name, o.display_name, o.country, o.country_basis, o.country_sites, o.eu_pic,
                  o.pic_method, o.pic_confidence, o.suppressed, o.individual_reason
             FROM organisation o WHERE o.id = dgate_live_org(%s)""", (org_id,)).fetchone()
    if not row:
        raise HTTPException(404, "no such organisation")
    if row["suppressed"]:
        raise removed()
    if row["individual_reason"]:
        raise not_published()
    family = [r["id"] for r in conn.execute(
        "SELECT id FROM organisation WHERE id = ANY(dgate_merged_in(%s)) AND NOT suppressed "
        "AND individual_reason IS NULL", (row["id"],)).fetchall()]
    row["merged"] = len(family)
    # Name variants (WP-41): rows the directory shows under this one, never merged. Their participations are
    # counted for the head's profile (the directory card says "includes N name variants" and must equal it).
    variants = conn.execute(
        """SELECT fm.org_id, fm.method, fm.confidence, o.canonical_name, o.display_name, o.country,
                  (SELECT count(DISTINCT pa.project_id) FROM participation pa
                    WHERE pa.organisation_id = ANY(dgate_merged_in(fm.org_id)) AND pa.active) AS projects
             FROM organisation_family_member fm JOIN organisation o ON o.id = fm.org_id
            WHERE fm.head_org_id = %s AND NOT o.suppressed AND o.individual_reason IS NULL AND o.merged_into IS NULL
            ORDER BY projects DESC, fm.org_id""", (row["id"],)).fetchall()
    row["variants"] = [v for v in variants if v["projects"]]
    for v in row["variants"]:
        family += [r["id"] for r in conn.execute(
            "SELECT id FROM organisation WHERE id = ANY(dgate_merged_in(%s)) AND NOT suppressed "
            "AND individual_reason IS NULL", (v["org_id"],)).fetchall()]
    row["family"] = family
    head = conn.execute(
        """SELECT o.id, o.canonical_name, o.display_name, o.country, fm.method, fm.confidence
             FROM organisation_family_member fm JOIN organisation o ON o.id = fm.head_org_id
            WHERE fm.org_id = %s AND NOT o.suppressed AND o.merged_into IS NULL""", (row["id"],)).fetchone()
    row["variant_of"] = head
    return row


def _require_member(conn, org: dict[str, Any]) -> None:
    if not conn.execute("SELECT 1 FROM participation WHERE organisation_id = ANY(%s) AND active LIMIT 1",
                        (org["family"],)).fetchone():
        raise HTTPException(404, "no such organisation")


# WP-88: plain words (the UX audit of 22 Oct 2026 found "alias", "exact normalised name" and "Lowest confidence 0.95").
RESOLUTION_WORDS = {
    "pic": "matched by its PIC, the participant identification code the source states",
    "alias": "matched to a spelling of its name that was linked to it before",
    "exact_name": "matched by the same name (ignoring accents, capitals and the legal form) in the same country",
    "exact_name_ambiguous": "matched by a name that more than one organisation of the country carries; "
                            "the best known was chosen and the pair is queued for a person to check",
    "national_id": "matched by a national registration number",
    "vat": "matched by a VAT number",
}


def resolution_note(methods: dict[str, int], lowest: float | None, pic: str | None) -> str:
    """One sentence on how this organisation was recognised in the projects: the share of
    participations per method, in words."""
    total = sum(methods.values())
    if not total:
        return "No participation is held for this organisation."
    parts = []
    for m, n in sorted(methods.items(), key=lambda kv: (-kv[1], kv[0])):
        what = RESOLUTION_WORDS.get(m, f"matched by {m.replace('_', ' ')}")
        parts.append(f"all {n} {what}" if n == total else f"{n} of {total} {what}")
    note = "Participations: " + "; ".join(parts) + "."
    if lowest is not None:
        note += f" How sure the least certain match is: {lowest:.2f} on a scale to 1 (1 is certain)."
    if not pic:
        note += " The sources give it no PIC, so it was recognised by its name."
    return note


def _buyer_link(conn, org_id: int) -> dict[str, Any] | None:
    """The buyer page of the same body, when it is also a procurement buyer with defence notices."""
    head = conn.execute("SELECT dgate_buyer_head(%s) AS h", (org_id,)).fetchone()["h"]
    n = conn.execute(
        f"""SELECT count(*) AS n FROM opportunity o
             WHERE o.buyer_org_id = ANY(ARRAY(SELECT unnest(dgate_family_ids(%s))))
               AND o.is_defence AND NOT o.suppressed AND NOT o.buyer_withheld AND {CORE_SQL}""",
        (org_id,)).fetchone()["n"]
    if not n:
        return None
    names = _buyer_names(conn, [head])
    name = names.get(head) or ""
    if not name:
        r = conn.execute("SELECT canonical_name FROM organisation WHERE id = %s", (head,)).fetchone()
        name = r["canonical_name"] if r else ""
    return {"slug": make_slug(head, name), "name": _clean(name), "tenderCount": n}


def network_slug_of_buyer(conn, family_ids: list[int]) -> str | None:
    """For a buyer page: the profile of the organisation that took part in projects, if one of the
    buyer's family did (the one with most participations). None when none did."""
    row = conn.execute(
        """SELECT dgate_live_org(pa.organisation_id) AS org, count(*) AS n
             FROM participation pa WHERE pa.organisation_id = ANY(%s) AND pa.active
            GROUP BY 1 ORDER BY n DESC, 1 LIMIT 1""", (family_ids,)).fetchone()
    if not row:
        return None
    o = conn.execute("SELECT id, canonical_name, display_name, suppressed, individual_reason FROM organisation "
                     "WHERE id = %s", (row["org"],)).fetchone()
    if not o or o["suppressed"] or o["individual_reason"]:
        return None
    return make_slug(o["id"], _org_name(o))


@router.get("/v1/organisations/{slug}")
def get_organisation(slug: str, conn=Depends(get_conn)):
    org = live_organisation(conn, slug)
    fam = org["family"]
    totals = conn.execute(
        f"""SELECT count(*) AS participations, count(DISTINCT pa.project_id) AS projects,
                   count(DISTINCT pa.project_id) FILTER (WHERE pa.role = 'coordinator') AS coordinated,
                   sum(pa.contribution) AS eu, min({YEAR}) AS y0, max({YEAR}) AS y1,
                   min(pa.resolution_confidence) AS lowest
              FROM participation pa JOIN project p ON p.id = pa.project_id
             WHERE pa.organisation_id = ANY(%s) AND pa.active""", (fam,)).fetchone()
    if not totals["participations"]:
        raise HTTPException(404, "no such organisation")
    by_programme = conn.execute(
        f"""SELECT COALESCE(pr.code, '') AS code, COALESCE(pr.name, 'Programme not stated') AS name,
                   count(DISTINCT pa.project_id) AS projects, sum(pa.contribution) AS eu,
                   min({YEAR}) AS y0, max({YEAR}) AS y1
              FROM participation pa JOIN project p ON p.id = pa.project_id
              LEFT JOIN programme pr ON pr.id = p.programme_id
             WHERE pa.organisation_id = ANY(%s) AND pa.active
             GROUP BY 1, 2 ORDER BY projects DESC, code""", (fam,)).fetchall()
    methods = {r["resolution_method"]: r["n"] for r in conn.execute(
        """SELECT resolution_method, count(*) AS n FROM participation
            WHERE organisation_id = ANY(%s) AND active GROUP BY 1""", (fam,)).fetchall()}
    aliases = conn.execute(
        """SELECT a.raw_name, a.match_method, a.confidence, a.first_seen, s.code AS source
             FROM organisation_alias a LEFT JOIN source s ON s.id = a.source_id
            WHERE a.organisation_id = ANY(%s) AND length(a.raw_name) <= 200
            ORDER BY a.confidence DESC, a.first_seen, a.id LIMIT 60""", (fam,)).fetchall()
    alias_total = conn.execute(
        "SELECT count(DISTINCT raw_name) AS n FROM organisation_alias "
        "WHERE organisation_id = ANY(%s) AND length(raw_name) <= 200", (fam,)).fetchone()["n"]
    seen: set[str] = set()
    alias_items = []
    for a in aliases:
        nm = _clean(a["raw_name"])
        if nm in seen or PHONE_LIKE.search(nm):
            continue
        seen.add(nm)
        alias_items.append({"name": nm, "method": a["match_method"], "confidence": _num(a["confidence"]),
                            "firstSeen": a["first_seen"], "source": a["source"]})
    name = _org_name(org)
    pic = None
    if org["eu_pic"]:
        pic = {"value": org["eu_pic"], "method": org["pic_method"],
               "confidence": _num(org["pic_confidence"])}
    src_codes = [r["code"] for r in conn.execute(
        """SELECT DISTINCT s.code FROM participation pa JOIN project p ON p.id = pa.project_id
             JOIN source s ON s.id = p.source_id
            WHERE pa.organisation_id = ANY(%s) AND pa.active""", (fam,)).fetchall()]
    return {
        "id": str(org["id"]), "slug": make_slug(org["id"], name), "name": name, "country": org["country"],
        "countryBasis": org["country_basis"], "countrySites": [c.strip() for c in org["country_sites"] or []],
        "pic": pic,
        "counts": {"projects": totals["projects"], "participations": totals["participations"],
                   "coordinated": totals["coordinated"], "euContribution": _num(totals["eu"]),
                   "firstYear": totals["y0"], "lastYear": totals["y1"]},
        "programmes": [{"code": r["code"], "name": r["name"], "projects": r["projects"],
                        "euContribution": _num(r["eu"]), "firstYear": r["y0"], "lastYear": r["y1"]}
                       for r in by_programme],
        "resolution": {"note": resolution_note(methods, _num(totals["lowest"]), org["eu_pic"]),
                       "participations": methods, "lowestConfidence": _num(totals["lowest"])},
        "aliases": {"total": alias_total, "items": alias_items},
        "mergedFrom": org["merged"] - 1,
        "nameVariants": {
            "total": len(org["variants"]),
            "note": ("These rows carry a name of this organisation that no rule could prove to be the same legal body "
                     "(different spelling, or the same name under another registration). They are not merged; "
                     "their projects are counted here and each keeps its own page."),
            "items": [{"organisation": org_ref({**v, "id": v["org_id"]}), "projects": v["projects"],
                       "method": v["method"], "confidence": _num(v["confidence"])} for v in org["variants"]],
        } if org["variants"] else None,
        "variantOf": {"organisation": org_ref(org["variant_of"]), "method": org["variant_of"]["method"],
                      "confidence": _num(org["variant_of"]["confidence"])} if org["variant_of"] else None,
        "buyer": _buyer_link(conn, org["id"]),
        "sources": _sources(conn, tuple(c for c in SOURCES if c in src_codes) or SOURCES),
        "amountNote": AMOUNT_NOTE,
    }


@router.get("/v1/organisations/{slug}/funding")
def organisation_funding(slug: str, conn=Depends(get_conn)):
    org = live_organisation(conn, slug)
    rows = conn.execute(
        f"""SELECT COALESCE(pr.code, '') AS programme, {YEAR} AS year,
                   count(DISTINCT pa.project_id) AS projects, sum(pa.contribution) AS eu,
                   count(DISTINCT pa.project_id) FILTER (WHERE pa.contribution IS NULL) AS without_amount
              FROM participation pa JOIN project p ON p.id = pa.project_id
              LEFT JOIN programme pr ON pr.id = p.programme_id
             WHERE pa.organisation_id = ANY(%s) AND pa.active
             GROUP BY 1, 2 ORDER BY 2 NULLS LAST, 1""", (org["family"],)).fetchall()
    if not rows:
        raise HTTPException(404, "no such organisation")
    return {
        "organisation": org_ref(org),
        "rows": [{"programme": r["programme"], "year": r["year"], "projects": r["projects"],
                  "euContribution": _num(r["eu"]), "projectsWithoutAmount": r["without_amount"]}
                 for r in rows],
        "totals": {"projects": conn.execute(
            "SELECT count(DISTINCT project_id) AS n FROM participation WHERE organisation_id = ANY(%s) AND active",
            (org["family"],)).fetchone()["n"],
            "euContribution": _num(sum((r["eu"] or Decimal(0)) for r in rows)) if any(
                r["eu"] is not None for r in rows) else None},
        "amountNote": AMOUNT_NOTE,
    }


@router.get("/v1/organisations/{slug}/partners")
@cache_list("organisation_partners", ttl=5 * 60)
def organisation_partners(
    slug: str,
    country: str | None = Query(None, max_length=200),
    programme: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1, le=500),
    pageSize: int = Query(20, ge=1, le=50),
    conn=Depends(get_conn),
):
    """The organisations that shared the most projects with this one, most projects first, most recent
    year next. `shared` counts projects, not participations; the projects are the evidence."""
    org = live_organisation(conn, slug)
    _require_member(conn, org)
    fam = org["family"]
    countries = _codes(country, "country", pattern=re.compile(r"^[A-Z]{2}$"), max_items=20)
    programmes = _codes(programme, "programme", pattern=PROGRAMME_CODE)
    ctes, args = _partner_ctes(fam, org["id"], programmes, countries)
    rows = conn.execute(
        f"""WITH {ctes}
            SELECT sel.*, count(*) OVER () AS total_rows, (SELECT count(DISTINCT country) FROM sel) AS countries
              FROM sel ORDER BY shared DESC, last_year DESC NULLS LAST, id LIMIT %s OFFSET %s""",
        args + [pageSize, (page - 1) * pageSize]).fetchall()
    total = rows[0]["total_rows"] if rows else (0 if page == 1 else conn.execute(
        f"WITH {ctes} SELECT count(*) AS n FROM sel", args).fetchone()["n"])
    evidence = _shared_projects(conn, fam, [r["id"] for r in rows]) if rows else {}
    return {
        "organisation": org_ref(org),
        "items": [{
            "organisation": org_ref(r), "shared": r["shared"], "firstYear": r["first_year"],
            "lastYear": r["last_year"], "programmes": r["programmes"] or [],
            "projects": evidence.get(r["id"], []),
        } for r in rows],
        "total": total, "countries": rows[0]["countries"] if rows else 0,
        "page": page, "pageSize": pageSize,
        "note": "Partners are the organisations that were active in a project this organisation was active in. "
                "The shared projects shown are the most recent five.",
    }


def _partner_ctes(fam: list[int], live: int, programmes: list[str], countries: list[str]
                  ) -> tuple[str, list[Any]]:
    """The neighbours of an organisation, as CTEs and their arguments: `mine` its own projects, `nb` the other
    participants in them, `agg` one row per live partner, `sel` with the partner's row (the join to
    `organisation` is made on the few thousand partners, never the 400,000 organisations: the planner had
    hashed the whole table, 2.5 s for the biggest). Measured on a production-sized copy: 0.45 s on a loaded
    host for an organisation with 2,600 projects and 9,900 partners."""
    prog_sql = " AND pr.code = ANY(%s)" if programmes else ""
    ctry_sql = " AND o.country = ANY(%s)" if countries else ""
    sql = f"""mine AS MATERIALIZED (
        SELECT me.project_id, {YEAR} AS yr, pr.code AS prog
          FROM participation me JOIN project p ON p.id = me.project_id
          LEFT JOIN programme pr ON pr.id = p.programme_id
         WHERE me.organisation_id = ANY(%s) AND me.active{prog_sql}),
    nb AS MATERIALIZED (
        SELECT {LIVE} AS org, mine.project_id, mine.yr, mine.prog
          FROM mine JOIN participation pa ON pa.project_id = mine.project_id AND pa.active
          LEFT JOIN organisation_merged_live l ON l.id = pa.organisation_id
         WHERE pa.project_id = ANY(ARRAY(SELECT project_id FROM mine))   -- steers the planner to the project index
           AND NOT (pa.organisation_id = ANY(%s)) AND {LIVE} <> %s AND NOT COALESCE(l.suppressed, FALSE)),
    agg AS MATERIALIZED (
        SELECT org, count(DISTINCT project_id) AS shared, max(yr) AS last_year, min(yr) AS first_year,
               array_agg(DISTINCT prog) FILTER (WHERE prog IS NOT NULL) AS programmes
          FROM nb GROUP BY org),
    sel AS MATERIALIZED (
        SELECT o.organisation_id AS id, o.name AS canonical_name, o.name AS display_name, o.country, a.shared,
               a.last_year, a.first_year, a.programmes
          FROM agg a JOIN organisation_network o ON o.organisation_id = a.org WHERE TRUE{ctry_sql})"""
    args: list[Any] = [fam] + ([programmes] if programmes else []) + [fam, live] + (
        [countries] if countries else [])
    return sql, args


def _shared_projects(conn, fam: list[int], partner_ids: list[int], per_partner: int = 5
                     ) -> dict[int, list[dict[str, Any]]]:
    """For each partner on the page, up to five shared projects, newest first."""
    members = conn.execute(
        """SELECT id, live_id FROM organisation_merged_live WHERE live_id = ANY(%s) AND NOT suppressed""",
        (partner_ids,)).fetchall()
    live_of = {r["id"]: r["live_id"] for r in members}
    ids = list({*partner_ids, *live_of})
    rows = conn.execute(
        f"""SELECT pa.organisation_id AS raw, p.id, p.acronym, p.title, pr.code AS programme,
                   {YEAR} AS year
              FROM participation me
              JOIN participation pa ON pa.project_id = me.project_id AND pa.active
              JOIN project p ON p.id = me.project_id
              LEFT JOIN programme pr ON pr.id = p.programme_id
             WHERE me.organisation_id = ANY(%s) AND me.active AND pa.organisation_id = ANY(%s)
             ORDER BY {YEAR} DESC NULLS LAST, p.id DESC""", (fam, ids)).fetchall()
    out: dict[int, list[dict[str, Any]]] = {}
    seen: set[tuple[int, int]] = set()
    for r in rows:
        live = live_of.get(r["raw"], r["raw"])
        if (live, r["id"]) in seen:
            continue
        seen.add((live, r["id"]))
        lst = out.setdefault(live, [])
        if len(lst) < per_partner:
            lst.append(_project_ref(r))
    return out


def _project_ref(r: dict[str, Any]) -> dict[str, Any]:
    label = _clean(r.get("acronym") or r.get("title"))
    return {"slug": make_slug(r["id"], label), "acronym": _clean(r.get("acronym")) or None,
            "title": _clean(r.get("title")), "programme": r.get("programme"), "year": r.get("year")}


@router.get("/v1/organisations/{slug}/projects")
def organisation_projects(
    slug: str,
    programme: str | None = Query(None, max_length=200),
    role: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1, le=1000),
    pageSize: int = Query(20, ge=1, le=100),
    conn=Depends(get_conn),
):
    org = live_organisation(conn, slug)
    _require_member(conn, org)
    programmes = _codes(programme, "programme", pattern=PROGRAMME_CODE)
    roles = _codes(role, "role", allowed=ROLES, upper=False)
    where, params = "", []
    if programmes:
        where += " AND pr.code = ANY(%s)"
        params.append(programmes)
    if roles:
        where += " AND pa.role = ANY(%s)"
        params.append(roles)
    rows = conn.execute(
        f"""SELECT p.id, p.acronym, p.title, p.total_cost, p.eu_contribution, p.status, p.topic_code,
                   p.category, pr.code AS programme, {YEAR} AS year, pa.role, pa.contribution,
                   count(*) OVER () AS total_rows
              FROM participation pa JOIN project p ON p.id = pa.project_id
              LEFT JOIN programme pr ON pr.id = p.programme_id
             WHERE pa.organisation_id = ANY(%s) AND pa.active{where}
             ORDER BY {YEAR} DESC NULLS LAST, p.id DESC LIMIT %s OFFSET %s""",
        [org["family"]] + params + [pageSize, (page - 1) * pageSize]).fetchall()
    total = rows[0]["total_rows"] if rows else (0 if page == 1 else conn.execute(
        f"""SELECT count(*) AS n FROM participation pa JOIN project p ON p.id = pa.project_id
              LEFT JOIN programme pr ON pr.id = p.programme_id
             WHERE pa.organisation_id = ANY(%s) AND pa.active{where}""",
        [org["family"]] + params).fetchone()["n"])
    return {
        "organisation": org_ref(org),
        "items": [{**_project_ref(r), "role": r["role"], "contribution": _num(r["contribution"]),
                   "status": r["status"], "topic": r["topic_code"], "category": r["category"],
                   "totalCost": _num(r["total_cost"]), "projectEuContribution": _num(r["eu_contribution"])}
                  for r in rows],
        "total": total, "page": page, "pageSize": pageSize,
    }


# ================================================================== one project

PROJECT_SELECT = """
    SELECT p.id, p.native_id, p.ga_number, p.acronym, p.title, p.call_code, p.topic_code, p.action_type,
           p.category, p.call_year, p.status, p.total_cost, p.eu_contribution, p.start_date, p.end_date,
           p.duration_months, p.factsheet_url, p.first_seen, pr.code AS programme_code,
           pr.name AS programme_name, s.code AS source_code, s.name AS source_name, s.licence,
           s.attribution
      FROM project p JOIN source s ON s.id = p.source_id
      LEFT JOIN programme pr ON pr.id = p.programme_id
     WHERE p.id = %s"""

# What an EDF factsheet reading dropped or corrected, in words (the keys of `project_factsheet.dropped`).
DROPPED_WORDS = {
    "not_in_text": "names the model returned that are not in the factsheet text (dropped)",
    "duplicate": "duplicate entries (folded)",
    "no_country": "participants with no recognisable country",
    "country_corrected": "countries replaced by the one printed beside the name",
    "missing_from_answer": "table rows the model left out",
    "coordinator_doubtful": "projects where more than one coordinator was returned (none is believed)",
}


def project_row(conn, slug: str) -> dict[str, Any]:
    row = conn.execute(PROJECT_SELECT, (_id_of(slug, "project"),)).fetchone()
    if not row:
        raise HTTPException(404, "no such project")
    return row


def _project_slug(r: dict[str, Any]) -> str:
    return make_slug(r["id"], _clean(r.get("acronym") or r.get("title")))


@router.get("/v1/projects/slugs")
def project_slugs(conn=Depends(get_conn)):
    """The EDF projects (a few hundred), for the sitemap. The 80,000 CORDIS projects are reachable but not listed."""
    rows = conn.execute(
        """SELECT p.id, p.acronym, p.title, p.first_seen FROM project p
             JOIN programme pr ON pr.id = p.programme_id WHERE pr.code = 'EDF'
            ORDER BY p.id LIMIT %s""", (SLUG_LIMIT,)).fetchall()
    return [{"slug": _project_slug(r), "updatedAt": datetime.combine(r["first_seen"], datetime.min.time(),
                                                                       tzinfo=timezone.utc)} for r in rows]


def _role_rank(role: str) -> int:
    return ROLES.index(role) if role in ROLES else len(ROLES)


def _members(conn, project_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""SELECT {LIVE} AS org_id, o.canonical_name, o.display_name, o.country,
                   (o.suppressed OR COALESCE(l.suppressed, FALSE) OR o.individual_reason IS NOT NULL) AS suppressed,
                   (o.individual_reason IS NOT NULL) AS individual,
                   pa.role, pa.contribution, pa.contribution_note, pa.resolution_method, pa.resolution_confidence
              FROM participation pa
              LEFT JOIN organisation_merged_live l ON l.id = pa.organisation_id
              JOIN organisation o ON o.id = {LIVE}
             WHERE pa.project_id = %s AND pa.active""", (project_id,)).fetchall()
    merged: dict[int, dict[str, Any]] = {}
    for r in rows:             # two rows that are one live organisation (a merge after both took part) are one member
        held = merged.get(r["org_id"])
        if held is None:
            merged[r["org_id"]] = dict(r)
            continue
        if _role_rank(r["role"]) < _role_rank(held["role"]):
            held["role"] = r["role"]
        if r["contribution"] is not None:
            held["contribution"] = (held["contribution"] or 0) + r["contribution"]
        held["resolution_confidence"] = min(held["resolution_confidence"], r["resolution_confidence"])
    out = list(merged.values())
    out.sort(key=lambda m: (m["role"] != "coordinator", bool(m["suppressed"]), m["country"] or "~",
                            _org_name(m).lower(), m["org_id"]))
    return out


def _factsheet_note(conn, project_id: int) -> dict[str, Any] | None:
    r = conn.execute(
        """SELECT extracted_at, pages, dropped, prompt_version FROM project_factsheet
            WHERE project_id = %s ORDER BY extracted_at DESC LIMIT 1""", (project_id,)).fetchone()
    if not r:
        return None
    dropped = {k: v for k, v in (r["dropped"] or {}).items() if v}
    return {
        "readBy": "language model", "readAt": r["extracted_at"], "pages": r["pages"],
        "dropped": [{"kind": k, "count": v, "meaning": DROPPED_WORDS.get(k, k)} for k, v in dropped.items()],
        "note": ("The participants were read from the factsheet by a language model. Every name was checked against "
                 "the factsheet text; one that is not in it was dropped. Countries come from the factsheet's own "
                 "table where it could be read without the model. The factsheet states no amount per participant."),
    }


@router.get("/v1/projects/{slug}")
def get_project(slug: str, conn=Depends(get_conn)):
    p = project_row(conn, slug)
    members = _members(conn, p["id"])
    coordinator = next((m for m in members if m["role"] == "coordinator"), None)
    edf = p["source_code"] == "edf_factsheets"
    ga = p["ga_number"]
    return {
        "id": str(p["id"]), "slug": _project_slug(p), "acronym": _clean(p["acronym"]) or None,
        "title": _clean(p["title"]),
        "programme": {"code": p["programme_code"], "name": p["programme_name"]} if p["programme_code"] else None,
        "grantNumber": ga, "call": p["call_code"], "topic": p["topic_code"], "actionType": p["action_type"],
        "category": p["category"], "callYear": p["call_year"], "status": p["status"],
        "startDate": p["start_date"], "endDate": p["end_date"], "durationMonths": p["duration_months"],
        "totalCost": _num(p["total_cost"]), "euContribution": _num(p["eu_contribution"]),
        "coordinator": org_ref(coordinator, id_key="org_id") if coordinator else None,
        # A natural person's name is not shown, and neither is what they received.
        "members": [{"organisation": org_ref(m, id_key="org_id"), "role": m["role"],
                     "contribution": None if m.get("individual") else _num(m["contribution"]),
                     "contributionNote": None if m.get("individual") else m["contribution_note"],
                     "resolution": {"method": m["resolution_method"],
                                    "confidence": _num(m["resolution_confidence"])}} for m in members],
        "memberCount": len(members),
        "countryCount": len({m["country"] for m in members if m["country"] and not m["suppressed"]}),
        "source": {"code": p["source_code"], "name": p["source_name"], "licence": p["licence"],
                   "attribution": p["attribution"],
                   "url": http_url(p["factsheet_url"]) if edf else (
                       http_url(f"https://cordis.europa.eu/project/id/{quote(ga, safe='')}") if ga else None),
                   "urlLabel": "EDF project factsheet" if edf else "Project page on CORDIS"},
        "factsheet": _factsheet_note(conn, p["id"]) if edf else None,
        "readAt": (_sources(conn, (p["source_code"],)) or [{}])[0].get("readAt"),
        "amountNote": AMOUNT_NOTE,
    }


@router.get("/v1/projects/{slug}/history")
def project_history(slug: str, conn=Depends(get_conn)):
    """The consortium changes we have seen: one entry per monthly snapshot that differed from the one before."""
    p = project_row(conn, slug)
    first = conn.execute(
        """SELECT observed_at, member_count, country_count FROM consortium_snapshot
            WHERE project_id = %s ORDER BY observed_at, id LIMIT 1""", (p["id"],)).fetchone()
    changes = conn.execute(
        """SELECT observed_at, added_org_ids, removed_org_ids, coordinator_before, coordinator_after
             FROM consortium_change WHERE project_id = %s ORDER BY observed_at DESC, id DESC LIMIT 50""",
        (p["id"],)).fetchall()
    ids = {i for c in changes for i in (*c["added_org_ids"], *c["removed_org_ids"], c["coordinator_before"],
                                        c["coordinator_after"]) if i}
    refs: dict[int, dict[str, Any]] = {}
    if ids:
        for o in conn.execute(
                """SELECT r.id AS asked, o.id, o.canonical_name, o.display_name, o.country,
                          (o.suppressed OR o.individual_reason IS NOT NULL) AS suppressed,
                          (o.individual_reason IS NOT NULL) AS individual
                     FROM unnest(%s::bigint[]) r(id) JOIN organisation o ON o.id = dgate_live_org(r.id)""",
                (list(ids),)).fetchall():
            refs[o["asked"]] = org_ref(o)

    def ref(i: int | None) -> dict[str, Any] | None:
        return refs.get(i) if i else None

    return {
        "project": {"slug": _project_slug(p), "acronym": _clean(p["acronym"]) or None, "title": _clean(p["title"])},
        "firstObserved": ({"observedAt": first["observed_at"], "memberCount": first["member_count"],
                           "countryCount": first["country_count"]} if first else None),
        "changes": [{"observedAt": c["observed_at"],
                     "added": [x for x in map(ref, c["added_org_ids"]) if x],
                     "removed": [x for x in map(ref, c["removed_org_ids"]) if x],
                     "coordinatorBefore": ref(c["coordinator_before"]),
                     "coordinatorAfter": ref(c["coordinator_after"])} for c in changes],
        "note": "A snapshot of each project's members is taken once a month; a change is recorded when a snapshot "
                "differs from the one before. A project with no change listed has had the same members since "
                "it was first observed.",
    }


# ================================================================== analytics

MAX_AREA_PROJECTS = 4000      # a capability area larger than this is not an area: narrow the topic


def _org_rows(conn, ids: set[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    return {r["id"]: r for r in conn.execute(
        "SELECT id, canonical_name, display_name, country, (suppressed OR individual_reason IS NOT NULL) AS suppressed, "
        "(individual_reason IS NOT NULL) AS individual FROM organisation WHERE id = ANY(%s)",
        (list(ids),)).fetchall()}


# WP-91 (UX audit 6: with no defence-programme project, the page opened on civil research only). Which projects of the wider
# view are defence-relevant: the defence programmes (2), and the research our funding list labels dual-use (1), read from the
# project's call code as the EU portal connector reads a call (`sources/eu_portal.py`: Cluster 3 Civil Security, Cluster 4 Digital,
# Industry and Space, the EIC) and their predecessors' security calls (Horizon 2020 Secure Societies, FP7 Security).
DUAL_USE_CALLS = re.compile(r"^(HORIZON-CL3|HORIZON-CL4|HORIZON-EIC|H2020-SU-|H2020-SEC-|H2020-BES-|H2020-DRS-|H2020-FCT-|H2020-DS-|FP7-SEC)")


def relevance(programme: str | None, call_code: str | None) -> int:
    """2 for a project of a defence programme, 1 for one of the dual-use calls above, 0 otherwise."""
    if (programme or "") in DEFENCE_PROGRAMMES:
        return 2
    return 1 if DUAL_USE_CALLS.match((call_code or "").upper()) else 0


@router.get("/v1/analytics/ukraine-partners")
@cache_list("ukraine_partners", ttl=15 * 60)
def ukraine_partners(
    since: int = Query(DEFAULT_SINCE, ge=1990, le=2100),
    programme: str | None = Query(None, max_length=100, description="comma-separated programme codes, e.g. EDF,EDIDP; empty: all"),
    q: str | None = Query(None, max_length=100, description="words of the projects' acronyms and titles (the funding search's synonyms)"),
    conn=Depends(get_conn),
):
    """Coordinators (the prime of a funded project) whose project had a participant established in Ukraine. WP-99 (p08): `q` keeps
    the projects whose acronym or title has every word (drone also finds unmanned, UAS, UAV), so the table is the topic's."""
    programmes = _codes(programme, "programme", pattern=PROGRAMME_CODE)
    # One row per (project, Ukrainian participant): a few thousand at most, aggregated here.
    pairs = conn.execute(
        f"""WITH ua AS MATERIALIZED (SELECT id FROM organisation WHERE country = 'UA' AND merged_into IS NULL AND NOT suppressed
                                                AND individual_reason IS NULL),
                 fam AS MATERIALIZED (SELECT id, id AS live FROM ua
                         UNION ALL SELECT m.id, m.live_id FROM organisation_merged_live m JOIN ua ON ua.id = m.live_id
                          WHERE NOT m.suppressed),
                 -- ANY over the ids, not a join: the planner joined all 380,000 participations to their projects first (4.7 s)
                 mine AS MATERIALIZED (SELECT pa.project_id, pa.organisation_id AS raw, pa.role FROM participation pa
                                        WHERE pa.organisation_id = ANY(ARRAY(SELECT id FROM fam)) AND pa.active)
            SELECT mine.project_id, fam.live AS ua_org, mine.role AS ua_role, p.id, p.acronym, p.title,
                   pr.code AS programme, p.call_code, {YEAR} AS year,
                   CASE WHEN cl.suppressed THEN NULL ELSE COALESCE(cl.live_id, c.organisation_id) END AS coord
              FROM mine JOIN fam ON fam.id = mine.raw
              JOIN project p ON p.id = mine.project_id
              LEFT JOIN programme pr ON pr.id = p.programme_id
              LEFT JOIN participation c ON c.project_id = mine.project_id AND c.role = 'coordinator' AND c.active
              LEFT JOIN organisation_merged_live cl ON cl.id = c.organisation_id
             WHERE {YEAR} >= %s""", (since,)).fetchall()
    # the keyword first: the counts per programme below are then the keyword's too
    query = textsearch.parse(q.replace("\x00", "")) if isinstance(q, str) and q.strip() else None
    if query is not None:
        pairs = [r for r in pairs if query.matches(f"{r['acronym'] or ''} {r['title'] or ''}")]
    # What each programme holds, before the filter: the page offers "all programmes" with these counts beside it (U10).
    seen: dict[str, set[int]] = {}
    for r in pairs:
        seen.setdefault(r["programme"] or "", set()).add(r["project_id"])
    by_programme = sorted(({"code": c, "projects": len(ids)} for c, ids in seen.items() if c),
                          key=lambda x: (-x["projects"], x["code"]))
    if programmes:
        pairs = [r for r in pairs if r["programme"] in programmes]
    orgs = _org_rows(conn, {r["ua_org"] for r in pairs} | {r["coord"] for r in pairs if r["coord"]})
    projects: dict[int, dict[str, Any]] = {}
    by_coord: dict[int, dict[str, Any]] = {}
    by_ua: dict[int, dict[str, Any]] = {}
    for r in pairs:
        projects[r["project_id"]] = r
        u = by_ua.setdefault(r["ua_org"], {"projects": set(), "coordinated": set(), "last": 0, "relevant": set()})
        u["projects"].add(r["project_id"])
        if relevance(r["programme"], r["call_code"]):
            u["relevant"].add(r["project_id"])
        u["last"] = max(u["last"], r["year"] or 0)
        coord = r["coord"]
        if coord == r["ua_org"]:
            u["coordinated"].add(r["project_id"])
        if coord is None or orgs[coord]["country"] == "UA":
            continue
        c = by_coord.setdefault(coord, {"projects": {}, "ua": {}, "programmes": set(), "last": 0})
        c["projects"][r["project_id"]] = r
        c["ua"].setdefault(r["ua_org"], set()).add(r["project_id"])
        c["programmes"].add(r["programme"])
        c["last"] = max(c["last"], r["year"] or 0)
    ukrainian_led = {pid for pid, r in projects.items() if r["coord"] and orgs[r["coord"]]["country"] == "UA"}
    def relevant(c: dict[str, Any]) -> tuple[int, int]:
        """(defence-programme projects, dual-use projects) of a coordinator."""
        marks = [relevance(r["programme"], r["call_code"]) for r in c["projects"].values()]
        return marks.count(2), marks.count(1)

    # WP-91: defence projects first, then dual-use ones, then the rest; within each, most projects first as before
    ranked = sorted(by_coord.items(), key=lambda kv: (tuple(-n for n in relevant(kv[1])), -len(kv[1]["projects"]),
                                                      -len(kv[1]["ua"]), kv[0]))
    ranked = [kv for kv in ranked if not orgs[kv[0]]["suppressed"]][:50]
    ua_ranked = sorted(by_ua.items(), key=lambda kv: (-len(kv[1]["relevant"]), -len(kv[1]["projects"]), kv[0]))[:20]
    return {
        "since": since, "programme": programmes, "byProgramme": by_programme,
        "q": query.terms if query else None, "alsoSearched": query.also if query else [],
        "definition": "A coordinator is the organisation that leads a funded project (the prime of its consortium). "
                      "It is listed when a project it coordinated, started in or after the year given, had an "
                      "active participant whose country of establishment, as the source states it, is Ukraine. "
                      "Ukrainian coordinators are counted apart. This says who partnered with Ukrainian "
                      "organisations, not who controls them or what they supplied.",
        "order": "Coordinators with projects of the defence programmes come first, then those with projects of the calls we label "
                 "dual-use (Horizon Europe Clusters 3 and 4 and the EIC, Horizon 2020 Secure Societies and Digital Security, FP7 "
                 "Security), then the rest; within each, most projects first.",
        "totals": {"projects": len(projects), "coordinators": len(by_coord),
                   "ukrainianOrganisations": len(by_ua), "projectsCoordinatedFromUkraine": len(ukrainian_led)},
        "coordinators": [{
            "organisation": org_ref({**orgs[cid], "id": cid}), "projects": len(c["projects"]),
            "ukrainianOrganisations": len(c["ua"]), "lastYear": c["last"] or None,
            "programmes": sorted(x for x in c["programmes"] if x),
            "ukrainianParticipants": [
                {"organisation": org_ref({**orgs[uid], "id": uid}), "projects": len(pids)}
                for uid, pids in sorted(c["ua"].items(), key=lambda kv: (-len(kv[1]), kv[0]))[:5]],
            "defenceProjects": relevant(c)[0], "dualUseProjects": relevant(c)[1],
            "recentProjects": [_project_ref(r) for r in sorted(
                c["projects"].values(), key=lambda r: (relevance(r["programme"], r["call_code"]), r["year"] or 0, r["id"]),
                reverse=True)[:3]],
        } for cid, c in ranked],
        "ukrainianOrganisations": [{"organisation": org_ref({**orgs[uid], "id": uid}), "projects": len(u["projects"]),
                                    "relevantProjects": len(u["relevant"]),
                                    "coordinated": len(u["coordinated"]), "lastYear": u["last"] or None}
                                   for uid, u in ua_ranked if not orgs[uid]["suppressed"]],
        "limits": ["Country is the country of establishment that CORDIS or the EDF factsheet states for the participant.",
                   "CORDIS in the copy we read lags the newest Horizon Europe starts; EDF projects are those of the "
                   "factsheets published so far.",
                   "A project counts from the year it started (call year for EDF).",
                   "A project whose coordinator the source does not state is counted in the project total but not under "
                   "any coordinator."],
        "sources": _sources(conn),
    }


EDF_PROGRAMMES = ("EDF", "EDIDP", "PADR")


@router.get("/v1/analytics/consortium-gaps")
@cache_list("consortium_gaps", ttl=15 * 60)
def consortium_gaps(
    programme: str = Query("EDF", max_length=100),
    topic: str | None = Query(None, max_length=60),
    lacking: str = Query("UA", pattern="^[A-Za-z]{2}$"),
    minProjects: int = Query(2, ge=2, le=50),
    conn=Depends(get_conn),
):
    """Organisations funded at least `minProjects` times in a capability area, none of whose projects in
    that area had a participant established in the `lacking` country."""
    programmes = _codes(programme, "programme", pattern=PROGRAMME_CODE)
    if not programmes:
        raise _bad("programme: give at least one")
    topic = (topic or "").strip().upper() or None
    if not topic and not set(programmes) <= set(EDF_PROGRAMMES):
        raise _bad("topic: give a topic code prefix for a programme other than the EDF ones; the whole of "
                   "Horizon is not an area")
    lack = lacking.upper()

    def like(prefix: str) -> str:
        return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"

    # The code a visitor types is the call's or topic's own (HORIZON-CL3-2023-DRS); the stored topic codes of
    # CORDIS carry a framework prefix (HORIZON_HORIZON-CL3-2023-DRS-01-01, H2020_SEC-2015-1). Both are matched,
    # and the call code, which is the clean one (WP-41, N9).
    forms = [topic] if topic else []
    if topic and topic.startswith("HORIZON-"):
        forms.append("HORIZON_" + topic)
    if topic and re.match(r"(H2020|FP7)-", topic):
        forms.append(topic.replace("-", "_", 1))
    prm: dict[str, Any] = {"programmes": programmes, "topic": topic, "likes": [like(f) for f in forms]}
    area = conn.execute(
        f"""SELECT p.id, p.acronym, p.title, p.category, pr.code AS programme, {YEAR} AS year
              FROM project p JOIN programme pr ON pr.id = p.programme_id
             WHERE pr.code = ANY(%(programmes)s)
               AND (%(topic)s::text IS NULL OR upper(p.category) = %(topic)s
                    OR upper(p.topic_code) LIKE ANY(%(likes)s) OR upper(p.call_code) LIKE ANY(%(likes)s))
             LIMIT {MAX_AREA_PROJECTS + 1}""", prm).fetchall()
    if len(area) > MAX_AREA_PROJECTS:
        raise _bad(f"topic: that area holds more than {MAX_AREA_PROJECTS} projects; give a narrower topic")
    members = conn.execute(
        f"""SELECT pa.project_id, {LIVE} AS org, o.country, (o.suppressed OR o.individual_reason IS NOT NULL) AS suppressed
              FROM participation pa LEFT JOIN organisation_merged_live l ON l.id = pa.organisation_id
              JOIN organisation o ON o.id = {LIVE}
             WHERE pa.active AND NOT COALESCE(l.suppressed, FALSE) AND pa.project_id = ANY(%s)""", ([a["id"] for a in area],)).fetchall()
    by_project: dict[int, list[dict[str, Any]]] = {}
    for m in members:
        by_project.setdefault(m["project_id"], []).append(m)
    with_lack = {pid for pid, ms in by_project.items() if any(m["country"] == lack for m in ms)}
    projects_of: dict[int, set[int]] = {}
    for m in members:
        projects_of.setdefault(m["org"], set()).add(m["project_id"])
    country_of = {m["org"]: m["country"] for m in members}
    hidden = {m["org"] for m in members if m["suppressed"]}
    hit = sorted(((o, ps) for o, ps in projects_of.items()
                  if len(ps) >= minProjects and not (ps & with_lack) and o not in hidden
                  and country_of[o] != lack), key=lambda kv: (-len(kv[1]), kv[0]))[:100]
    names = _org_rows(conn, {o for o, _ in hit})
    meta = {a["id"]: a for a in area}
    areas = conn.execute(
        """SELECT p.category AS code, count(*) AS projects FROM project p JOIN programme pr ON pr.id = p.programme_id
            WHERE pr.code = ANY(%s) AND p.category IS NOT NULL GROUP BY 1 ORDER BY 2 DESC, 1""",
        (list(EDF_PROGRAMMES),)).fetchall()
    items = []
    for o, ps in hit:
        mine = sorted(ps, key=lambda pid: (meta[pid]["year"] or 0, pid), reverse=True)
        items.append({
            "organisation": org_ref({**names[o], "id": o}), "projects": len(ps),
            "partnerCountries": sorted({m["country"] for pid in ps for m in by_project[pid]
                                        if m["org"] != o and m["country"]} - {country_of[o]}),
            "recentProjects": [{**_project_ref(meta[pid]), "category": meta[pid]["category"],
                                "countries": sorted({m["country"] for m in by_project[pid] if m["country"]})}
                               for pid in mine[:5]],
        })
    return {
        "programme": programmes, "topic": topic, "lacking": lack, "minProjects": minProjects,
        "projectsInArea": len(area),
        "definition": ("Capability area: the projects of the programme(s) named, narrowed by the topic you give, which "
                       "is the EDF capability category (for example CYBER, GROUND) or the start of a topic code. The "
                       "data holds no finer taxonomy. Country: where a participant is established (its country of "
                       f"establishment), as the source states it. An organisation is listed when it took part in at least "
                       f"{minProjects} projects of the area and no project of the area it took part in had a "
                       f"participant established in {lack}. Consortia as such are not listed: the data does not "
                       "identify a consortium beyond the projects its members share."),
        "items": items,
        "areas": [{"code": a["code"], "projects": a["projects"]} for a in areas],
        "limits": ([f"No project of the programme matches the topic {topic!r}. Give the call or topic code as "
                    "the programme prints it (HORIZON-CL3-2023-DRS, H2020-SEC-2015, an EDF category such as CYBER) "
                    "or its start."] if not area else []) + ([] if with_lack or not area else [
            f"No project of this area has a participant established in {lack} at all, so the list is every "
            "organisation funded that often in it, not a gap."]) + ([
                   "The EDF factsheets are read by a language model; a participant missed or misplaced would "
                   "show a gap that is not there."] if set(programmes) & set(EDF_PROGRAMMES) else []) + [
                   "Participants are those the source lists for the project today (active); a participant that "
                   "left is not counted.",
                   "An organisation removed on request is left out of the list but its country still counts "
                   "as a participant of its projects."],
        "sources": _sources(conn),
    }
