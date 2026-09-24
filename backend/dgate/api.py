"""Serving layer.

Run: uvicorn dgate.api:app --reload

Two endpoints matter more than the rest.

  /v1/opportunities/{id}/versions
      The archive. This is the one thing no competitor can offer, because
      history cannot be backfilled. It is also why archive depth is the
      natural boundary between the free and paid tiers.

  /v1/organisations/resolve
      Entity resolution exposed as a service. An internal capability sold as a
      product to anyone maintaining their own supplier lists.

Two deliberate design choices:
  - original-language fields are always returned alongside translations,
    because a supplier submitting a bid needs the authoritative text
  - resolution confidence is exposed rather than hidden, because pretending to
    certainty the system does not have is how data products lose trust
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from . import db
from .config import settings
from .normalise import normalise_org_name

# A source whose last successful run is older than this is reported stale.
# Every connector in Phase 1 runs daily, so a day and a half allows one missed
# run without crying wolf, and catches two.
STALE_AFTER_HOURS = 36

app = FastAPI(
    title="EU Defence Access Portal API",
    version="0.1.0",
    description="Defence and dual-use procurement opportunities across the EU.",
)

ATTRIBUTION = {
    "ted": "Source: TED (Tenders Electronic Daily), © European Union",
    "es_placsp": "Source: Plataforma de Contratación del Sector Público, "
                 "Ministerio de Hacienda, Spain",
    "eu_portal": "Source: European Commission, Funding and Tenders Portal",
}


def get_conn():
    with db.connect(settings().dsn) as conn:
        yield conn


class Money(BaseModel):
    amount: float | None = None
    currency: str | None = None


class Signals(BaseModel):
    legal_basis: bool
    cpv: bool
    buyer: bool
    clearance: bool


class OpportunityOut(BaseModel):
    id: int
    source: str
    native_id: str
    buyer: dict[str, Any]
    country: str | None
    title_original: str
    title_en: str | None
    summary_en: str | None
    original_language: str | None
    value: Money
    published_at: date | None
    deadline_at: datetime | None
    cpv_codes: list[str]
    legal_basis: str | None
    signals: Signals
    subcontracting_signal: bool
    security_clearance_required: bool
    source_url: str | None
    version: int
    attribution: str
    # Why the notice is here: `core` when the notice itself carries a defence
    # signal, `supply` when only the buyer does -- the armed forces buying
    # anything. See SCOPE_SQL.
    scope: str
    # As of now: an open call whose deadline has passed is `expired`. The
    # source's own code is kept alongside, so the mapping stays checkable.
    status: str | None = None
    status_native: str | None = None


def _row_to_out(r: dict[str, Any]) -> OpportunityOut:
    return OpportunityOut(
        id=r["id"],
        source=r["source_code"],
        native_id=r["native_id"],
        buyer={
            "organisation_id": r.get("buyer_org_id"),
            "name": r["buyer_name_raw"],
            "resolution_confidence": float(r["org_confidence"])
            if r.get("org_confidence") is not None else None,
        },
        country=r.get("country"),
        title_original=r["title_original"],
        title_en=r.get("title_en"),
        summary_en=r.get("summary_en"),
        original_language=r.get("original_language"),
        value=Money(amount=float(r["value_amount"]) if r.get("value_amount") else None,
                    currency=r.get("value_currency")),
        published_at=r.get("published_at"),
        deadline_at=r.get("deadline_at"),
        cpv_codes=r.get("cpv_codes") or [],
        legal_basis=r.get("legal_basis"),
        signals=Signals(
            legal_basis=bool(r.get("sig_legal_basis")),
            cpv=bool(r.get("sig_cpv")),
            buyer=bool(r.get("sig_buyer")),
            clearance=bool(r.get("sig_clearance")),
        ),
        subcontracting_signal=bool(r.get("subcontracting_signal")),
        security_clearance_required=bool(r.get("security_clearance_required")),
        source_url=r.get("source_url"),
        version=r.get("current_version") or 1,
        attribution=ATTRIBUTION.get(r["source_code"], ""),
        scope="core" if (r.get("sig_legal_basis") or r.get("sig_cpv")) else "supply",
        status=effective_status(r.get("status"), r.get("deadline_at"), r.get("published_at")),
        status_native=r.get("status_native"),
    )


# The defence slice has two populations, and they are not the same product.
#
# `core`: the notice itself says defence -- the 2009/81/EC legal basis, or a CPV
# code in division 35 -- whoever the buyer is.
#
# `supply`: only the buyer does. A listed defence body qualifies a notice on its
# own, whatever it buys, and after the buyer list went from empty to 111
# organisations on 13 September 2026 these became 90% of the slice: garrison
# maintenance, construction, food, cleaning, office supplies, with real defence
# items among them. Valuable to a supplier trying to get into the forces'
# supply chain, noise to one looking for defence contracts, so they are served
# only when asked for.
# The status a notice carries is the one it was published or last amended with,
# and a source rarely publishes "this call has now closed". Served as stored,
# "open" meant open-when-seen: on 14 September 2026, 12,539 of 13,412 notices
# served as open had a passed deadline, or no deadline and a publication date
# over a year old -- mostly 2024 and 2025 calls from the Polish backfill. The
# stored value is versioned history and stays as it is; what is served is the
# status as of now.
OPEN_WITHOUT_DEADLINE_DAYS = 365
EFFECTIVE_STATUS_SQL = f"""(CASE
    WHEN o.status = 'open' AND (
         o.deadline_at < now()
      OR (o.deadline_at IS NULL
          AND o.published_at < (now() - interval '{OPEN_WITHOUT_DEADLINE_DAYS} days')))
    THEN 'expired' ELSE o.status END)"""


def effective_status(status: str | None, deadline_at: datetime | None,
                     published_at: date | None, now: datetime | None = None) -> str | None:
    """The Python twin of EFFECTIVE_STATUS_SQL, for a row already fetched."""
    if status != "open":
        return status
    now = now or datetime.now(timezone.utc)
    if deadline_at is not None:
        return "expired" if deadline_at < now else "open"
    if published_at is not None and published_at < (now - timedelta(
            days=OPEN_WITHOUT_DEADLINE_DAYS)).date():
        return "expired"
    return "open"


SCOPE_SQL = {
    "core": "(o.sig_legal_basis OR o.sig_cpv)",
    "supply": "(o.sig_buyer AND NOT o.sig_legal_basis AND NOT o.sig_cpv)",
    "all": "TRUE",
}


BASE_SELECT = """
    SELECT o.*, s.code AS source_code, org.confidence AS org_confidence
      FROM opportunity o
      JOIN source s ON s.id = o.source_id
      LEFT JOIN organisation org ON org.id = o.buyer_org_id
"""


@app.get("/v1/opportunities", response_model=list[OpportunityOut])
def list_opportunities(
    country: str | None = Query(None, description="comma-separated ISO-2"),
    cpv: str | None = Query(None, description="comma-separated CPV prefixes"),
    deadline_after: date | None = None,
    deadline_before: date | None = None,
    value_min: float | None = None,
    subcontracting: bool | None = None,
    status: str = "open",
    scope: str = Query("core", pattern="^(core|supply|all)$",
                       description="core: the notice itself is defence (default); "
                                   "supply: only the buyer is a defence body; all: both"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    conn=Depends(get_conn),
):
    where = ["o.is_defence = TRUE", f"{EFFECTIVE_STATUS_SQL} = %s", SCOPE_SQL[scope]]
    params: list[Any] = [status]

    if country:
        codes = [c.strip().upper() for c in country.split(",") if c.strip()]
        where.append("o.country = ANY(%s)")
        params.append(codes)
    if cpv:
        prefixes = [c.strip() for c in cpv.split(",") if c.strip()]
        clauses = []
        for p in prefixes:
            clauses.append("EXISTS (SELECT 1 FROM unnest(o.cpv_codes) c WHERE c LIKE %s)")
            params.append(f"{p}%")
        where.append("(" + " OR ".join(clauses) + ")")
    if deadline_after:
        where.append("o.deadline_at >= %s")
        params.append(deadline_after)
    if deadline_before:
        where.append("o.deadline_at <= %s")
        params.append(deadline_before)
    if value_min is not None:
        where.append("o.value_amount >= %s")
        params.append(value_min)
    if subcontracting is not None:
        where.append("o.subcontracting_signal = %s")
        params.append(subcontracting)

    sql = (BASE_SELECT + " WHERE " + " AND ".join(where)
           + " ORDER BY o.published_at DESC NULLS LAST, o.id DESC"
           + " LIMIT %s OFFSET %s")
    rows = conn.execute(sql, params + [limit, offset]).fetchall()
    return [_row_to_out(r) for r in rows]


@app.get("/v1/opportunities/{opp_id}", response_model=OpportunityOut)
def get_opportunity(opp_id: int, conn=Depends(get_conn)):
    row = conn.execute(BASE_SELECT + " WHERE o.id = %s", (opp_id,)).fetchone()
    if not row:
        raise HTTPException(404, "not found")
    return _row_to_out(row)


@app.get("/v1/opportunities/{opp_id}/versions")
def get_versions(opp_id: int, conn=Depends(get_conn)):
    """The archive: full observation timeline for one notice.

    Deadline extensions, value revisions and scope amendments, each with the
    observation timestamp and the list of fields that changed. Not available
    from any upstream source.
    """
    rows = conn.execute(
        """SELECT v.version, v.observed_at, v.valid_from, v.valid_to,
                  v.changed_fields, v.payload,
                  coalesce(json_agg(json_build_object('kind', n.kind, 'note', n.note))
                           FILTER (WHERE n.id IS NOT NULL), '[]') AS notes
             FROM opportunity_version v
             LEFT JOIN opportunity_version_note n ON n.opportunity_version_id = v.id
            WHERE v.opportunity_id = %s
            GROUP BY v.id
            ORDER BY v.version""",
        (opp_id,),
    ).fetchall()
    if not rows:
        raise HTTPException(404, "not found")
    return {
        "opportunity_id": opp_id,
        "version_count": len(rows),
        "amended": len(rows) > 1,
        "versions": [
            {
                "version": r["version"],
                "observed_at": r["observed_at"],
                "valid_from": r["valid_from"],
                "valid_to": r["valid_to"],
                "changed_fields": r["changed_fields"] or [],
                "snapshot": r["payload"],
                # A version the archive recorded wrongly is annotated, never
                # removed: see migration 0006. Clients should not present a
                # `reread` or `out_of_order` version as a real amendment.
                "notes": r["notes"],
            }
            for r in rows
        ],
    }


class CallOut(BaseModel):
    id: int
    programme: str
    native_id: str
    topic_code: str | None
    call_identifier: str | None
    title: str
    # Why the call is in this database: published under a defence programme, or
    # a civil programme whose subject the agreed scope treats as dual-use.
    regime: str
    status: str | None
    type_of_action: str | None = None
    budget: float | None
    opens_at: date | None
    deadline_at: datetime | None
    # Days from now to the deadline. A negative number means it has passed; the
    # portal keeps a call `open` on the day it closes, and a supplier deciding
    # whether to start writing needs the number, not the date arithmetic.
    days_left: int | None
    source_url: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    attribution: str


CALL_SELECT = """
    SELECT c.id, p.code AS programme, c.native_id, c.topic_code, c.call_identifier,
           c.title, c.regime, c.status, c.type_of_action, c.budget, c.opens_at, c.deadline_at,
           c.source_url, c.first_seen_at, c.last_seen_at
      FROM call c JOIN programme p ON p.id = c.programme_id
"""


def _call_to_out(r: dict[str, Any]) -> CallOut:
    deadline = r.get("deadline_at")
    days_left = None
    if deadline is not None:
        days_left = (deadline - datetime.now(timezone.utc)).days
    return CallOut(
        id=r["id"],
        programme=r["programme"],
        native_id=r["native_id"],
        topic_code=r.get("topic_code"),
        call_identifier=r.get("call_identifier"),
        title=r["title"],
        regime=r["regime"],
        status=r.get("status"),
        type_of_action=r.get("type_of_action"),
        budget=float(r["budget"]) if r.get("budget") is not None else None,
        opens_at=r.get("opens_at"),
        deadline_at=deadline,
        days_left=days_left,
        source_url=r.get("source_url"),
        first_seen_at=r["first_seen_at"],
        last_seen_at=r["last_seen_at"],
        attribution=ATTRIBUTION["eu_portal"],
    )


@app.get("/v1/calls", response_model=list[CallOut])
def list_calls(
    programme: str | None = Query(None, description="comma-separated codes, e.g. EDF,HORIZON"),
    regime: str = Query("all", pattern="^(defence|dual_use|all)$",
                        description="defence: funded by a defence programme or "
                                    "carrying the STEP defence seal (default view "
                                    "for a defence supplier); dual_use: civil "
                                    "programmes in scope; all: both"),
    status: str = Query("open", pattern="^(open|forthcoming|closed|evaluated|all)$"),
    deadline_before: date | None = None,
    deadline_after: date | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    conn=Depends(get_conn),
):
    """Grant calls, soonest deadline first.

    Sorted by deadline ascending and not by publication date, which is the one
    difference from the opportunities endpoint that matters: a call is useful
    while it is open, and what an applicant needs first is the one closing next.
    """
    where: list[str] = []
    params: list[Any] = []
    if status != "all":
        where.append("c.status = %s")
        params.append(status)
    if regime != "all":
        where.append("c.regime = %s")
        params.append(regime)
    if programme:
        codes = [c.strip().upper() for c in programme.split(",") if c.strip()]
        where.append("p.code = ANY(%s)")
        params.append(codes)
    if deadline_after:
        where.append("c.deadline_at >= %s")
        params.append(deadline_after)
    if deadline_before:
        where.append("c.deadline_at <= %s")
        params.append(deadline_before)

    sql = (CALL_SELECT
           + (" WHERE " + " AND ".join(where) if where else "")
           + " ORDER BY c.deadline_at ASC NULLS LAST, c.id"
           + " LIMIT %s OFFSET %s")
    rows = conn.execute(sql, params + [limit, offset]).fetchall()
    return [_call_to_out(r) for r in rows]


@app.get("/v1/organisations/resolve")
def resolve(name: str, country: str, conn=Depends(get_conn)):
    """Entity resolution as a service.

    Returns a match with its confidence and the method that produced it, or a
    null match. Never guesses silently.
    """
    norm = normalise_org_name(name)
    row = conn.execute(
        """SELECT a.organisation_id, a.match_method, a.confidence,
                  o.canonical_name, o.country, o.ncage_code, o.is_defence_buyer
             FROM organisation_alias a
             JOIN organisation o ON o.id = a.organisation_id
            WHERE a.normalised_name = %s AND a.country_hint = %s
            ORDER BY a.confidence DESC LIMIT 1""",
        (norm, country.upper()),
    ).fetchone()
    if not row:
        return {"query": {"name": name, "country": country},
                "normalised": norm, "match": None}
    return {
        "query": {"name": name, "country": country},
        "normalised": norm,
        "match": {
            "organisation_id": row["organisation_id"],
            "canonical_name": row["canonical_name"],
            "country": row["country"],
            "ncage_code": row["ncage_code"],
            "is_defence_buyer": row["is_defence_buyer"],
            "confidence": float(row["confidence"]),
            "method": row["match_method"],
        },
    }


@app.get("/v1/health")
def health(conn=Depends(get_conn)):
    """Coverage health, not just liveness.

    Reports the last run per source and flags anything not successful. A green
    process with a dead connector is the failure this endpoint exists to catch.
    """
    # LEFT JOIN from source, not an inner join from ingest_run: a source that
    # has never run at all must appear here. Reporting "ok" because there are
    # no failed runs, when there are no runs, is precisely the green tick this
    # endpoint exists to prevent.
    rows = conn.execute(
        """SELECT DISTINCT ON (s.code)
                  s.code, s.active, r.status, r.finished_at, r.started_at,
                  r.records_fetched, r.records_new, r.records_changed,
                  r.error_message
             FROM source s
             LEFT JOIN ingest_run r ON r.source_id = s.id
            WHERE s.active
            ORDER BY s.code, r.started_at DESC NULLS LAST"""
    ).fetchall()
    total = conn.execute(
        "SELECT count(*) AS n FROM opportunity WHERE is_defence"
    ).fetchone()["n"]
    versions = conn.execute(
        "SELECT count(*) AS n FROM opportunity_version"
    ).fetchone()["n"]
    oldest = conn.execute(
        "SELECT min(observed_at) AS t FROM opportunity_version"
    ).fetchone()["t"]

    stale_after = timedelta(hours=STALE_AFTER_HOURS)
    now = datetime.now(timezone.utc)
    sources: list[dict[str, Any]] = []
    unhealthy: list[str] = []
    for r in rows:
        item = dict(r)
        if r["status"] is None:
            item["status"] = "never_run"
            item["health"] = "unhealthy"
        elif r["status"] != "success":
            item["health"] = "unhealthy"
        elif r["finished_at"] is None or (now - r["finished_at"]) > stale_after:
            # A connector that succeeded once a month ago is not healthy today.
            item["health"] = "stale"
        else:
            item["health"] = "healthy"
        if item["health"] != "healthy":
            unhealthy.append(r["code"])
        sources.append(item)

    return {
        "status": "degraded" if unhealthy else "ok",
        "unhealthy_sources": unhealthy,
        "defence_opportunities": total,
        "archive_versions": versions,
        "archive_oldest_observation": oldest,
        "stale_after_hours": STALE_AFTER_HOURS,
        "sources": sources,
    }
