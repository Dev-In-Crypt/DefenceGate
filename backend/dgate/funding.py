"""The funding hub's API: the shape docs/design/API_CONTRACT.md fixes.

Separate from `/v1/calls`, which stays as it is: that is the data model's own view,
this is the page's. What differs is deliberate and decided with the owner on
12 October 2026:

  - amounts are never converted; a budget filter matches one currency at a time
  - a call that has not opened is `forthcoming`, not folded into open
  - the heading is English where the source publishes an English title, otherwise
    the source's own language, labelled; nothing is translated here
  - a call with no stated deadline has `deadline: null`
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from . import db
from .config import settings
from .normalise import http_url, redact_emails

router = APIRouter()


def get_conn():
    cfg = settings()
    with db.connect(cfg.api_dsn or cfg.dsn) as conn:
        yield conn


MAX_LIST_ITEMS = 20

CLOSING_SOON_DAYS = 30

# The design's programme chips. Every national source is NATIONAL; the programme's
# own name travels in `programmeName`. EDIDP, the predecessor of the defence fund,
# has no calls and sits under EDF.
EU_PROGRAMMES = {"EDF": "EDF", "EDIDP": "EDF", "EDIP": "EDIP",
                 "HORIZON": "HORIZON", "DIGITAL": "DIGITAL"}
NATIONAL_PROGRAMME = re.compile(r"^[A-Z]{2}-")

# The language a national source writes in, by the funder country.
LANGUAGE_BY_COUNTRY = {"ES": "es", "PL": "pl", "FR": "fr", "SE": "sv", "FI": "fi",
                       "DE": "de", "IT": "it", "NL": "nl"}

# `eligibility_text` is the source's own words for these two only; the other
# connectors assemble it from structured fields, which are already in the rows.
SOURCE_TEXT_SOURCES = {"eu_portal", "se_vinnova"}

EFFECTIVE_STATUS = """(CASE
    WHEN c.status = 'open' AND c.deadline_at < now() THEN 'closed'
    WHEN c.status = 'evaluated' OR c.status IS NULL THEN 'closed'
    ELSE c.status END)"""


class Budget(BaseModel):
    amount: float
    currency: str


class Row(BaseModel):
    label: str
    value: str


class SourceAttribution(BaseModel):
    sourceId: str
    sourceName: str
    url: str | None
    retrievedAt: datetime
    licence: str
    attribution: str


class FundingCall(BaseModel):
    id: str
    slug: str
    programme: str
    programmeName: str
    callId: str | None
    topicId: str
    title: str
    titleLanguage: str
    originalTitle: str | None
    originalLanguage: str | None
    regime: str
    funderCountry: str
    issuer: str | None
    status: str
    openingDate: datetime | None
    deadline: datetime | None
    budget: Budget | None
    budgetScope: str | None
    actionType: str | None
    fundingRate: str | None
    scope: list[str]
    eligibility: list[Row]
    publishedAt: datetime | None
    firstSeenAt: datetime
    lastSeenAt: datetime
    source: SourceAttribution


class FundingCallDetail(FundingCall):
    conditionsText: str | None = None


class FundingPage(BaseModel):
    items: list[FundingCall]
    total: int
    page: int
    pageSize: int


class SourceHealth(BaseModel):
    id: str
    name: str
    country: str | None
    type: str
    url: str | None
    lastRunAt: datetime | None
    status: str
    records: int
    coverage: float | None
    licence: str
    attribution: str


class Health(BaseModel):
    generatedAt: datetime
    sources: list[SourceHealth]


# ----------------------------------------------------------------- mapping

def slugify(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")


def make_slug(call_id: int, title: str) -> str:
    words = slugify(title)[:60].strip("-")
    return f"{call_id}-{words}" if words else str(call_id)


def programme_of(code: str) -> str:
    """The design's programme chip for a stored programme code."""
    if NATIONAL_PROGRAMME.match(code):
        return "NATIONAL"
    return EU_PROGRAMMES.get(code, "HORIZON")


def _day(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time(0, 0), tzinfo=timezone.utc)
    return None


def _money(amount: Any, currency: str | None) -> str:
    return f"{currency or 'EUR'} {float(amount):,.0f}"


# The Polish register's applicant codes, said the way an applicant would say them.
APPLICANT_LABELS = {"sme": "SME", "micro": "Micro-enterprise", "ngo": "NGO",
                    "large_enterprise": "Large enterprise", "research_unit": "Research unit",
                    "public_institution": "Public institution", "university": "University",
                    "consortium": "Consortium"}


def _nice(value: str) -> str:
    return APPLICANT_LABELS.get(value) or value.replace("_", " ").strip().capitalize()


def _iso_day(value: Any) -> str | None:
    return str(value)[:10] if value else None


def eligibility_rows(programme_code: str, cond: dict[str, Any], row: dict[str, Any]) -> list[dict[str, str]]:
    """Label/value rows from what the connector structured. Never prose."""
    out: list[dict[str, str]] = []

    def add(label: str, value: Any) -> None:
        if value in (None, "", [], {}):
            return
        if isinstance(value, list):
            value = ", ".join(str(v).strip() for v in value if v)
        out.append({"label": label, "value": str(value).strip()})

    if not NATIONAL_PROGRAMME.match(programme_code):
        add("Expected number of grants", cond.get("expected_grants"))
        low, high = cond.get("min_contribution"), cond.get("max_contribution")
        if low is not None and high is not None and low != high:
            add("Contribution per grant", f"{_money(low, 'EUR')} to {_money(high, 'EUR')}")
        elif high is not None or low is not None:
            add("Contribution per grant", _money(high if high is not None else low, "EUR"))
        if cond.get("for_smes"):
            add("SME-focused", "Yes")
        add("Deadline model", _nice(str(cond["deadline_model"])) if cond.get("deadline_model") else None)
        size, states = row.get("min_consortium_size"), row.get("min_member_states")
        if size or states:
            parts = []
            if size:
                parts.append(f"{size} legal entities")
            if states:
                parts.append(f"from {states} Member States")
            add("Minimum consortium", " ".join(parts))
    elif programme_code == "PL-NCBR":
        add("Applicants", [_nice(v) for v in cond.get("applicant_types") or []])
        add("Source of funding", [_nice(v) for v in cond.get("sources_of_funding") or []])
        add("Programme type", [v.upper() if len(v) <= 3 else _nice(v) for v in cond.get("programme_types") or []])
    elif programme_code == "SE-VINNOVA":
        add("Programme", cond.get("programme"))
        add("Decision expected", _iso_day(cond.get("decision_expected")))
        start_a, start_b = _iso_day(cond.get("project_start_earliest")), _iso_day(cond.get("project_start_latest"))
        both = start_a and start_b and start_a != start_b
        add("Project start", f"{start_a} to {start_b}" if both else start_a or start_b)
        add("Project ends at the latest", _iso_day(cond.get("project_end_latest")))
    elif programme_code == "FR-AID":
        if cond.get("max_aid_eur_per_project"):
            add("Maximum aid per project", _money(cond["max_aid_eur_per_project"], "EUR"))
    elif programme_code == "ES-BDNS":
        add("Beneficiaries", [str(v).strip() for v in cond.get("beneficiary_types") or []])
        add("Regions", [str(v).strip() for v in cond.get("regions") or []])
        add("Instruments", [str(v).strip() for v in cond.get("instruments") or []])
        add("Call type", cond.get("call_type"))
        add("Regulation", cond.get("regulation"))
    return out


def scope_keywords(programme_code: str, cond: dict[str, Any]) -> list[str]:
    if not NATIONAL_PROGRAMME.match(programme_code):
        return [str(t) for t in cond.get("tags") or [] if isinstance(t, str)][:12]
    if programme_code == "PL-NCBR":
        return [_nice(v) for v in cond.get("thematic_areas") or []]
    if programme_code == "ES-BDNS":
        return [s["name"].strip() for s in cond.get("sectors") or [] if isinstance(s, dict) and s.get("name")]
    return []


def titles(programme_code: str, country: str | None, title: str,
           cond: dict[str, Any]) -> tuple[str, str, str | None, str | None]:
    """(heading, its language, other title, its language)."""
    if not NATIONAL_PROGRAMME.match(programme_code):
        return title, "en", None, None
    national = LANGUAGE_BY_COUNTRY.get(country or "", "en")
    original = cond.get("title_sv") if programme_code == "SE-VINNOVA" else None
    if original and original.strip() != title.strip():
        # the connector took the English title the source publishes
        return title, "en", original.strip(), national
    return title, national, None, None


def to_call(r: dict[str, Any], *, detail: bool = False) -> dict[str, Any]:
    from .api import _attribution  # api includes this router, so import it late

    cond = r.get("conditions_raw") or {}
    prog = r["programme_code"]
    heading, lang, original, original_lang = titles(prog, r.get("country"), r["title"], cond)
    status = r["effective_status"]
    out = {
        "id": str(r["id"]),
        "slug": make_slug(r["id"], r["title"]),
        "programme": programme_of(prog),
        "programmeName": r["programme_name"],
        "callId": r.get("call_identifier"),
        "topicId": r.get("topic_code") or r["native_id"],
        "title": redact_emails(heading),
        "titleLanguage": lang,
        "originalTitle": redact_emails(original),
        "originalLanguage": original_lang,
        "regime": "dual-use" if r["regime"] == "dual_use" else r["regime"],
        "funderCountry": r.get("country") or "EU",
        "issuer": redact_emails(r.get("issuer")),
        "status": status,
        "openingDate": _day(r.get("opens_at")),
        "deadline": r.get("deadline_at"),
        "budget": ({"amount": float(r["budget"]), "currency": r["currency"] or "EUR"}
                   if r.get("budget") is not None else None),
        "budgetScope": r.get("budget_scope"),
        "actionType": r.get("type_of_action"),
        "fundingRate": None,
        "scope": scope_keywords(prog, cond),
        "eligibility": redact_emails(eligibility_rows(prog, cond, r)),
        "publishedAt": _day(r.get("published_at")),
        "firstSeenAt": r["first_seen_at"],
        "lastSeenAt": r["last_seen_at"],
        "source": {
            "sourceId": r["source_code"],
            "sourceName": r["source_name"],
            "url": http_url(r.get("source_url")),
            "retrievedAt": r["last_seen_at"],
            "licence": r["source_licence"] or "",
            "attribution": _attribution(r),
        },
    }
    if detail:
        # The source's own words are served only where it is on the list AND its
        # licence row says commercial reuse is allowed. NULL is "unknown", which is
        # not a yes: setting the flag withdraws the text without a deploy.
        may_serve = r["source_code"] in SOURCE_TEXT_SOURCES and r.get("source_commercial_ok") is True
        text = r.get("eligibility_text") if may_serve else None
        out["conditionsText"] = redact_emails(text.strip()) if text and text.strip() else None
    return out


SELECT = f"""
    SELECT c.*, {EFFECTIVE_STATUS} AS effective_status,
           p.code AS programme_code, p.name AS programme_name,
           s.code AS source_code, s.name AS source_name, s.licence AS source_licence,
           s.attribution AS source_attribution, s.commercial_ok AS source_commercial_ok
      FROM call c
      JOIN programme p ON p.id = c.programme_id
      LEFT JOIN source s ON s.id = c.source_id
"""


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _csv(value: str | None) -> list[str]:
    items = [v.strip() for v in (value or "").split(",") if v.strip()]
    if len(items) > MAX_LIST_ITEMS or any(len(i) > 32 or "\x00" in i for i in items):
        raise HTTPException(422, "too many or too long values in a list parameter")
    return items


# --------------------------------------------------------------- endpoints

@router.get("/v1/funding", response_model=FundingPage)
def list_funding(
    q: str | None = Query(None, max_length=100),
    programme: str | None = Query(None, max_length=200),
    regime: str | None = Query(None, max_length=100),
    country: str | None = Query(None, max_length=200),
    status: str = Query("open", pattern="^(open|forthcoming|closing-soon|closed|all)$"),
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    min_: float | None = Query(None, alias="min", ge=0, le=1e13),
    max_: float | None = Query(None, alias="max", ge=0, le=1e13),
    currency: str = Query("EUR", pattern="^[A-Za-z]{3}$"),
    sort: str = Query("deadline-asc", pattern="^(deadline-asc|deadline-desc|budget-desc)$"),
    page: int = Query(1, ge=1, le=1000),
    pageSize: int = Query(10, ge=1, le=500),
    conn=Depends(get_conn),
):
    where: list[str] = []
    params: list[Any] = []

    if status == "closing-soon":
        where.append(f"{EFFECTIVE_STATUS} = 'open' AND c.deadline_at <= now() + interval '{CLOSING_SOON_DAYS} days'")
    elif status != "all":
        where.append(f"{EFFECTIVE_STATUS} = %s")
        params.append(status)

    if q and q.replace("\x00", "").strip():
        like = _like(q.replace("\x00", "").strip())
        where.append("(c.title ILIKE %s OR c.topic_code ILIKE %s OR c.call_identifier ILIKE %s "
                     "OR c.issuer ILIKE %s OR c.conditions_raw->>'title_sv' ILIKE %s)")
        params += [like] * 5

    wanted = [c.upper() for c in _csv(programme)]
    if wanted:
        clauses: list[str] = []
        stored = [code for code, chip in EU_PROGRAMMES.items() if chip in wanted]
        if stored:
            clauses.append("p.code = ANY(%s)")
            params.append(stored)
        if "NATIONAL" in wanted:
            clauses.append("p.code ~ '^[A-Z]{2}-'")
        if clauses:
            where.append("(" + " OR ".join(clauses) + ")")

    regimes = [r.replace("-", "_") for r in _csv(regime) if r in ("defence", "dual-use")]
    if regimes:
        where.append("c.regime = ANY(%s)")
        params.append(regimes)

    countries = [c.upper() for c in _csv(country)]
    if countries:
        where.append("COALESCE(c.country, 'EU') = ANY(%s)")
        params.append(countries)

    if from_:
        where.append("c.deadline_at >= %s")
        params.append(datetime.combine(from_, time(0, 0), tzinfo=timezone.utc))
    if to:
        where.append("c.deadline_at < %s::date + 1")
        params.append(to)

    cur = currency.upper()
    if min_ is not None or max_ is not None:
        # An amount is only comparable with another in the same currency, so the
        # range selects that currency and says nothing about the others.
        where.append("c.currency = %s AND c.budget IS NOT NULL")
        params.append(cur)
        if min_ is not None:
            where.append("c.budget >= %s")
            params.append(min_)
        if max_ is not None:
            where.append("c.budget <= %s")
            params.append(max_)

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(
        f"SELECT count(*) AS n FROM ({SELECT}{clause}) c", params).fetchone()["n"]

    closed_last = f"({EFFECTIVE_STATUS} = 'closed') ASC"
    if sort == "budget-desc":
        order = (f"{closed_last}, (c.currency = %s AND c.budget IS NOT NULL) DESC, "
                 "CASE WHEN c.currency = %s THEN c.budget END DESC NULLS LAST, "
                 "c.deadline_at ASC NULLS LAST, c.id")
        order_params = [cur, cur]
    elif sort == "deadline-desc":
        order = f"{closed_last}, c.deadline_at IS NULL, c.deadline_at DESC, c.id"
        order_params = []
    else:
        order = f"{closed_last}, c.deadline_at IS NULL, c.deadline_at ASC, c.id"
        order_params = []

    rows = conn.execute(
        f"{SELECT}{clause} ORDER BY {order} LIMIT %s OFFSET %s",
        params + order_params + [pageSize, (page - 1) * pageSize]).fetchall()
    return {"items": [to_call(r) for r in rows], "total": total,
            "page": page, "pageSize": pageSize}


@router.get("/v1/funding/slugs")
def funding_slugs(conn=Depends(get_conn)):
    rows = conn.execute("SELECT c.id, c.title, c.last_seen_at FROM call c ORDER BY c.id").fetchall()
    return [{"slug": make_slug(r["id"], r["title"]), "updatedAt": r["last_seen_at"]} for r in rows]


@router.get("/v1/funding/{slug}", response_model=FundingCallDetail)
def get_funding(slug: str, conn=Depends(get_conn)):
    m = re.match(r"^([0-9]{1,9})(?:-|$)", slug, re.ASCII)
    if not m:
        raise HTTPException(404, "no such call")
    row = conn.execute(SELECT + " WHERE c.id = %s", (int(m.group(1)),)).fetchone()
    if not row:
        raise HTTPException(404, "no such call")
    return to_call(row, detail=True)


@router.get("/v1/sources", response_model=Health)
def list_sources(conn=Depends(get_conn)):
    from .api import _attribution  # api includes this router, so import it late

    rows = conn.execute(
        """SELECT DISTINCT ON (s.code)
                  s.code, s.name, s.country, s.kind, s.base_url, s.licence, s.attribution,
                  r.status, r.finished_at, r.records_fetched, r.expected_min
             FROM source s
             LEFT JOIN ingest_run r ON r.source_id = s.id AND r.finished_at IS NOT NULL
            WHERE s.active
            ORDER BY s.code, r.started_at DESC NULLS LAST""").fetchall()
    sources = []
    for r in rows:
        floor, fetched = r["expected_min"], r["records_fetched"] or 0
        sources.append({
            "id": r["code"], "name": r["name"], "country": r["country"],
            "type": "grants" if r["kind"] == "grant" else "tenders",
            "url": r["base_url"], "lastRunAt": r["finished_at"],
            "status": {"success": "ok", "partial": "partial", "failed": "failed"}.get(
                r["status"], "never"),
            "records": fetched,
            "coverage": min(1.0, fetched / floor) if floor else None,
            "licence": r["licence"] or "", "attribution": _attribution(
                {"source_attribution": r["attribution"], "source_code": r["code"]}),
        })
    return {"generatedAt": datetime.now(timezone.utc), "sources": sources}

