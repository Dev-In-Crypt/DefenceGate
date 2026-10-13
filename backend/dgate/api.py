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

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import db
from .config import settings
from .hardening import BodyLimit, RateLimit, SecurityHeaders
from .normalise import http_url, normalise_org_name, redact_emails

# A source whose last successful run is older than this is reported stale.
# Every connector in Phase 1 runs daily, so a day and a half allows one missed
# run without crying wolf, and catches two.
STALE_AFTER_HOURS = 36

# The interactive documentation and the OpenAPI document describe every
# parameter to anyone who asks; they are for development (DGATE_DOCS=1).
_docs = settings().docs_enabled
app = FastAPI(
    title="EU Defence Access Portal API",
    version="0.1.0",
    description="Defence and dual-use procurement opportunities across the EU.",
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)
app.add_middleware(BodyLimit)         # innermost: its 413 still gets the security headers
app.add_middleware(SecurityHeaders)
app.add_middleware(RateLimit)

# Largest values a request may carry, and how many items a list parameter may
# have. Chosen well above anything the frontend sends; a request beyond them is
# refused with 422 rather than turned into a query. One request with a thousand
# CPV prefixes took the database for 50 to 100 seconds (12 October 2026).
MAX_OFFSET = 10_000
MAX_LIST_ITEMS = 20
MAX_PREFIX_LENGTH = 8
MAX_BIGINT = 9_223_372_036_854_775_807


@app.exception_handler(psycopg.errors.DataError)
def _bad_value(_: Request, __: psycopg.errors.DataError) -> JSONResponse:
    # A value the database cannot store (a NUL character, a number out of range).
    return JSONResponse({"detail": "invalid value in request"}, status_code=422)


@app.exception_handler(psycopg.errors.QueryCanceled)
def _too_slow(_: Request, __: psycopg.errors.QueryCanceled) -> JSONResponse:
    return JSONResponse({"detail": "the query took too long; narrow the request"},
                        status_code=503, headers={"Retry-After": "5"})


def _split(value: str | None, name: str, *, upper: bool = False,
           max_length: int = 64) -> list[str]:
    """A comma-separated list parameter, bounded."""
    items = [i.strip() for i in (value or "").split(",") if i.strip()]
    if len(items) > MAX_LIST_ITEMS:
        raise HTTPException(422, f"{name}: at most {MAX_LIST_ITEMS} values")
    for item in items:
        if len(item) > max_length or "\x00" in item:
            raise HTTPException(422, f"{name}: value too long")
    return [i.upper() for i in items] if upper else items

ATTRIBUTION = {
    "ted": "Source: TED (Tenders Electronic Daily), © European Union",
    "es_placsp": "Source: Plataforma de Contratación del Sector Público, "
                 "Ministerio de Hacienda, Spain",
    "eu_portal": "Source: European Commission, Funding and Tenders Portal",
    "pl_ncbr": "Zrodlo: Narodowe Centrum Badan i Rozwoju (NCBR), gov.pl",
    "es_bdns": "Origen de los datos: Intervención General de la Administración del Estado "
               "(Base de Datos Nacional de Subvenciones, Ministerio de Hacienda)",
    "se_vinnova": "Källa: Vinnova, öppna data (CC0)",
    "nl_tenderned": "Bron: TenderNed (PIANOo), Nederland",
}


def _attribution(row: dict[str, Any], default: str = "") -> str:
    """The credit line the source's own row states, so that adding a source cannot
    leave it unattributed. The map above is the fallback for a row that carries none.

    It used to be the map alone, and four sources were served with an empty line: the
    Polish bulletin, the Polish tenders dataset (CC BY 4.0, where attribution is a
    condition of the licence), the regional Spanish platforms and the French bulletin
    (Licence Ouverte).
    """
    return (row.get("source_attribution")
            or ATTRIBUTION.get(row.get("source_code") or "", default))


def get_conn():
    # The API's own, read-only role when one is configured (migration 0024).
    cfg = settings()
    with db.connect(cfg.api_dsn or cfg.dsn) as conn:
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
    # What kind of body the buyer is (defence, security, municipal, health, education,
    # fire_rescue, other), and whether a military CPV was demoted because that body
    # buys for itself. Additive: `scope` keeps its two values.
    buyer_class: str | None = None
    dual_use: bool = False
    # As of now: an open call whose deadline has passed is `expired`. The
    # source's own code is kept alongside, so the mapping stays checkable.
    status: str | None = None
    status_native: str | None = None
    # The same notice as another source published it: a national notice and the
    # TED notice it was forwarded as. Joined on the publication number the
    # national source itself states; nothing is matched by name or title.
    same_notice: list[dict[str, Any]] = []


def _twins(conn, ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """For a page of rows, the same notice in the other sources, by TED number."""
    if not ids:
        return {}
    rows = conn.execute(
        """
        SELECT a.id AS row_id, b.id, bs.code AS source, b.native_id, b.source_url
          FROM opportunity a
          JOIN opportunity b ON b.id <> a.id AND b.is_defence AND (
                (b.source_id = (SELECT id FROM source WHERE code = 'ted')
                   AND b.native_id = a.ted_ref)
             OR (a.source_id = (SELECT id FROM source WHERE code = 'ted')
                   AND b.ted_ref = a.native_id)
             OR (a.ted_ref IS NOT NULL AND b.ted_ref = a.ted_ref))
          JOIN source bs ON bs.id = b.source_id
         WHERE a.id = ANY(%s)
         ORDER BY a.id, bs.code, b.native_id
        """,
        (ids,),
    ).fetchall()
    out: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["row_id"], []).append({
            "id": r["id"], "source": r["source"],
            "native_id": r["native_id"], "url": http_url(r["source_url"]),
        })
    return out


def _row_to_out(r: dict[str, Any], same_notice: list[dict[str, Any]] | None = None
                ) -> OpportunityOut:
    return OpportunityOut(
        id=r["id"],
        source=r["source_code"],
        native_id=r["native_id"],
        buyer={
            "organisation_id": r.get("buyer_org_id"),
            "name": redact_emails(r["buyer_name_raw"]),
            "resolution_confidence": float(r["org_confidence"])
            if r.get("org_confidence") is not None else None,
        },
        country=r.get("country"),
        title_original=redact_emails(r["title_original"]),
        title_en=redact_emails(r.get("title_en")),
        summary_en=redact_emails(r.get("summary_en")),
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
        source_url=http_url(r.get("source_url")),
        version=r.get("current_version") or 1,
        attribution=_attribution(r),
        scope=row_scope(r),
        buyer_class=r.get("buyer_class"),
        dual_use=bool(r.get("dual_use")),
        status=effective_status(r.get("status"), r.get("deadline_at"), r.get("published_at")),
        status_native=r.get("status_native"),
        same_notice=same_notice or [],
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


# `core` is the notice itself saying defence: the 2009/81/EC legal basis, or a
# military CPV that its buyer's own needs do not explain. A civil security CPV
# (fire extinguishers, groups 351 and 352) no longer makes `core` on its own or
# with a clearance flag; the columns stay and corroborate. A military CPV bought
# by a municipality, a hospital, a school or a fire brigade is `dual_use` and
# leaves `core`; it is still reachable through `all`.
CORE_SQL = "(o.sig_legal_basis OR (o.sig_cpv_military AND NOT o.dual_use))"
SCOPE_SQL = {
    "core": CORE_SQL,
    "supply": f"((o.sig_buyer OR o.sig_linked_defence) AND NOT {CORE_SQL})",
    "all": "TRUE",
}


def row_scope(r: dict[str, Any]) -> str:
    """The Python twin of SCOPE_SQL for a row already fetched: `core` or `supply`."""
    if r.get("sig_legal_basis") or (r.get("sig_cpv_military") and not r.get("dual_use")):
        return "core"
    return "supply"


BASE_SELECT = """
    SELECT o.*, s.code AS source_code, s.attribution AS source_attribution,
           org.confidence AS org_confidence
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
    value_min: float | None = Query(None, ge=0, le=1e13),
    subcontracting: bool | None = None,
    status: str = Query("open", max_length=20),
    scope: str = Query("core", pattern="^(core|supply|all)$",
                       description="core: the notice itself is defence (default); "
                                   "supply: only the buyer is a defence body; all: both"),
    collapse: bool = Query(True, description="show a national notice once: hide it when "
                                             "the TED notice it was forwarded as is also "
                                             "in this result (see `same_notice`)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
    conn=Depends(get_conn),
):
    where = ["o.is_defence = TRUE", f"{EFFECTIVE_STATUS_SQL} = %s", SCOPE_SQL[scope]]
    params: list[Any] = [status]

    if country:
        codes = _split(country, "country", upper=True, max_length=2)
        where.append("o.country = ANY(%s)")
        params.append(codes)
    if cpv:
        prefixes = _split(cpv, "cpv", max_length=MAX_PREFIX_LENGTH)
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

    matched = BASE_SELECT + " WHERE " + " AND ".join(where)
    # The twin is dropped only when it is in the same result, so a filter that
    # keeps the national row and not its TED notice (another CPV, another
    # status) never makes the notice vanish.
    if collapse:
        sql = (f"WITH matched AS ({matched}) SELECT m.* FROM matched m"
               " WHERE NOT (m.ted_ref IS NOT NULL AND EXISTS ("
               "   SELECT 1 FROM matched t"
               "    WHERE t.source_code = 'ted' AND t.native_id = m.ted_ref))")
    else:
        sql = f"SELECT m.* FROM ({matched}) m WHERE TRUE"
    sql += " ORDER BY m.published_at DESC NULLS LAST, m.id DESC LIMIT %s OFFSET %s"
    rows = conn.execute(sql, params + [limit, offset]).fetchall()
    twins = _twins(conn, [r["id"] for r in rows])
    return [_row_to_out(r, twins.get(r["id"])) for r in rows]


@app.get("/v1/opportunities/{opp_id}", response_model=OpportunityOut)
def get_opportunity(opp_id: int = Path(ge=1, le=MAX_BIGINT), conn=Depends(get_conn)):
    row = conn.execute(BASE_SELECT + " WHERE o.id = %s", (opp_id,)).fetchone()
    if not row:
        raise HTTPException(404, "not found")
    return _row_to_out(row, _twins(conn, [opp_id]).get(opp_id))


# What a version's snapshot may show. An allow-list, because the stored payload
# is the whole record: it also holds the notice's full text, which is not part of
# the product and has carried personal data (e-mail addresses in 108 versions
# observed before the sweep of 22 September 2026). A field added to the record
# later is not served until someone decides it should be.
SNAPSHOT_FIELDS = (
    "source_code", "native_id", "buyer_name_raw", "title_original", "title_en",
    "summary_en", "country", "original_language", "procedure_type", "legal_basis",
    "value_amount", "value_currency", "published_at", "deadline_at", "cpv_codes",
    "source_url", "notice_version", "status", "status_native", "ted_ref",
)


def public_snapshot(payload: dict[str, Any] | None) -> dict[str, Any]:
    """A stored version payload as it may be served: allow-listed and redacted."""
    kept = {k: v for k, v in (payload or {}).items() if k in SNAPSHOT_FIELDS}
    if "source_url" in kept:
        kept["source_url"] = http_url(kept["source_url"])
    return redact_emails(kept)


@app.get("/v1/opportunities/{opp_id}/versions")
def get_versions(opp_id: int = Path(ge=1, le=MAX_BIGINT), conn=Depends(get_conn)):
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
        # Not `len(rows) > 1`: a version that only re-read old content, arrived out
        # of order or is one of our own re-mappings is not an amendment.
        "amended": any(
            r["version"] > 1
            and not any(n["kind"] in db.NOT_AMENDMENT_NOTES for n in (r["notes"] or []))
            for r in rows),
        "versions": [
            {
                "version": r["version"],
                "observed_at": r["observed_at"],
                "valid_from": r["valid_from"],
                "valid_to": r["valid_to"],
                "changed_fields": r["changed_fields"] or [],
                "snapshot": public_snapshot(r["payload"]),
                # A version the archive recorded wrongly is annotated, never
                # removed: see migration 0006. Clients should not present a
                # `reread`, `out_of_order` or `remapped` version as a real amendment.
                "notes": redact_emails(r["notes"]),
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
    # Whose budget that is: `topic` when the portal states a figure for this
    # topic alone, `call` when the same figure is the pot several sibling topics
    # compete for -- all eleven topics of the 2026 EDF development call carry
    # EUR 422 million between them. Null when no figure was published.
    budget_scope: str | None = None
    # ISO 4217 of `budget`: euro for the EU programmes and Spain, zloty or euro for
    # Poland. Never converted: a rate is a judgement the product should not make.
    currency: str | None = None
    # How many members the call requires, and from how many countries. Null when
    # the programme states them in a PDF instead of in the conditions text --
    # every EDF topic does -- because a number read from the regulation rather
    # than from this call would be a guess wearing a fact's clothes.
    min_consortium_size: int | None = None
    min_member_states: int | None = None
    opens_at: date | None
    # The day the source itself dates the call, where it does (BDNS: received by the
    # register). Not the day we saw it: that is `first_seen_at`.
    published_at: date | None = None
    deadline_at: datetime | None
    # Days from now to the deadline. A negative number means it has passed; the
    # portal keeps a call `open` on the day it closes, and a supplier deciding
    # whether to start writing needs the number, not the date arithmetic.
    days_left: int | None
    source_url: str | None
    # National sources only: the ISO-2 country of the issuing body and the body
    # itself as the source names it. An EU programme call has neither -- it is
    # open to every member state.
    country: str | None = None
    issuer: str | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    attribution: str


CALL_SELECT = """
    SELECT c.id, p.code AS programme, c.native_id, c.topic_code, c.call_identifier,
           c.title, c.regime, c.status, c.type_of_action, c.budget, c.budget_scope, c.currency,
           c.min_consortium_size, c.min_member_states, c.opens_at, c.published_at, c.deadline_at,
           c.source_url, c.country, c.issuer, c.first_seen_at, c.last_seen_at,
           s.code AS source_code, s.attribution AS source_attribution
      FROM call c JOIN programme p ON p.id = c.programme_id
      LEFT JOIN source s ON s.id = c.source_id
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
        title=redact_emails(r["title"]),
        regime=r["regime"],
        status=r.get("status"),
        type_of_action=r.get("type_of_action"),
        budget=float(r["budget"]) if r.get("budget") is not None else None,
        budget_scope=r.get("budget_scope"),
        currency=r.get("currency"),
        min_consortium_size=r.get("min_consortium_size"),
        min_member_states=r.get("min_member_states"),
        opens_at=r.get("opens_at"),
        published_at=r.get("published_at"),
        deadline_at=deadline,
        days_left=days_left,
        source_url=http_url(r.get("source_url")),
        country=r.get("country"),
        issuer=redact_emails(r.get("issuer")),
        first_seen_at=r["first_seen_at"],
        last_seen_at=r["last_seen_at"],
        attribution=_attribution(r, default=ATTRIBUTION["eu_portal"]),
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
    country: str | None = Query(None, description="comma-separated ISO-2 of the issuing body; "
                                                 "national grants only, EU programmes have none"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
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
        codes = _split(programme, "programme", upper=True)
        where.append("p.code = ANY(%s)")
        params.append(codes)
    if country:
        where.append("c.country = ANY(%s)")
        params.append(_split(country, "country", upper=True, max_length=2))
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


class CallDetailOut(CallOut):
    # The conditions as the portal words them, and the budget line behind the
    # total: "two grants of EUR 3 million" and "EUR 110 million across an
    # unknown number of grants" are different propositions to a small supplier.
    eligibility_text: str | None = None
    conditions: dict[str, Any] | None = None
    details_seen_at: datetime | None = None


@app.get("/v1/calls/{call_id}", response_model=CallDetailOut)
def get_call(call_id: int = Path(ge=1, le=MAX_BIGINT), conn=Depends(get_conn)):
    row = conn.execute(
        CALL_SELECT.replace("c.first_seen_at",
                            "c.eligibility_text, c.conditions_raw, c.details_seen_at, "
                            "c.first_seen_at")
        + " WHERE c.id = %s", (call_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="no such call")
    base = _call_to_out(row)
    return CallDetailOut(**base.model_dump(), eligibility_text=row.get("eligibility_text"),
                         conditions=row.get("conditions_raw"),
                         details_seen_at=row.get("details_seen_at"))


@app.get("/v1/organisations/resolve")
def resolve(name: str = Query(min_length=1, max_length=200),
            country: str = Query(min_length=2, max_length=2),
            conn=Depends(get_conn)):
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
        # Only what a reader of the coverage needs. The run's error text is a
        # `str(exception)` and has held an object-store URL; it stays in the table.
        item = {"code": r["code"], "active": r["active"], "status": r["status"],
                "finished_at": r["finished_at"], "records_fetched": r["records_fetched"]}
        if r["status"] is None:
            item["status"] = "never_run"
            item["health"] = "unhealthy"
        elif r["status"] != "success":
            item["health"] = "unhealthy"
        elif r["code"] not in settings().floors:
            # A source with no daily rhythm (the one-off historical load) is not
            # late for not having run today; a floor is what says "daily".
            item["health"] = "healthy"
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


# The funding hub's own view of the calls; see docs/design/API_CONTRACT.md. Included
# last because it reads `_attribution` from this module.
from .funding import router as _funding_router  # noqa: E402

app.include_router(_funding_router)

from .tenders import router as _tenders_router  # noqa: E402

app.include_router(_tenders_router)

# Accounts: reached only by the site's own server over the internal network, never routed
# by Caddy (docs/design/ACCOUNT_CONTRACT.md).
from .accounts import AccountError, account_error_handler  # noqa: E402
from .accounts import internal_router as _internal_router  # noqa: E402
from .accounts import router as _account_router  # noqa: E402

app.include_router(_account_router)
app.include_router(_internal_router)
app.add_exception_handler(AccountError, account_error_handler)
