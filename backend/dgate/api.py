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

import functools
import re
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import classify, db
from .config import require_production_secrets, settings
from .hardening import BodyLimit, ETag, HeadAsGet, RateLimit, SecurityHeaders
from .listcache import cache_list
from .normalise import http_url, normalise_org_name, redact_emails
from .suppress import WITHHELD_NAME, removed

# A source whose last successful run is older than this is reported stale.
# Every connector in Phase 1 runs daily, so a day and a half allows one missed
# run without crying wolf, and catches two.
STALE_AFTER_HOURS = 36

# The interactive documentation and the OpenAPI document describe every
# parameter to anyone who asks; they are for development (DGATE_DOCS=1).
_docs = settings().docs_enabled


@asynccontextmanager
async def _lifespan(_: FastAPI):
    # A production API without its internal secret does not start (QA M10). At server start,
    # not at import: the worker imports parts of this module and holds no such secret.
    require_production_secrets()
    yield


app = FastAPI(
    title="EU Defence Access Portal API",
    version="0.1.0",
    description="Defence and dual-use procurement opportunities across the EU.",
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
    lifespan=_lifespan,
)
app.add_middleware(BodyLimit)         # innermost: its 413 still gets the security headers
app.add_middleware(ETag)              # WP-114: inside the headers, so a 304 carries them too
app.add_middleware(SecurityHeaders)
app.add_middleware(RateLimit)
app.add_middleware(HeadAsGet)         # outermost: a HEAD is routed, charged and secured as the GET it stands for

# Largest values a request may carry, and how many items a list parameter may
# have. Chosen well above anything the frontend sends; a request beyond them is
# refused with 422 rather than turned into a query. One request with a thousand
# CPV prefixes took the database for 50 to 100 seconds (12 October 2026).
MAX_OFFSET = 10_000
MAX_LIST_ITEMS = 20
MAX_PREFIX_LENGTH = 8
MAX_BIGINT = 9_223_372_036_854_775_807


def refused(msg: str, loc: tuple[str, ...] = ("query",), headers: dict[str, str] | None = None) -> JSONResponse:
    """A 422 in the contract's one error shape, `{detail: [{loc, msg, type}]}` (docs/design/API_CONTRACT.md),
    the shape FastAPI gives its own validation errors."""
    return JSONResponse({"detail": [{"loc": list(loc), "msg": msg, "type": "value_error"}]},
                        status_code=422, headers=headers)


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException) -> Any:
    # Every hand-raised `HTTPException(422, "text")` of every router answers in the contract's shape
    # (QA M8: a client parsing `detail[]` broke on them). Other statuses are FastAPI's own.
    if exc.status_code == 422 and isinstance(exc.detail, str):
        return refused(exc.detail, headers=getattr(exc, "headers", None))
    return await http_exception_handler(request, exc)


@app.exception_handler(psycopg.errors.DataError)
def _bad_value(_: Request, __: psycopg.errors.DataError) -> JSONResponse:
    # A value the database cannot store (a NUL character, a number out of range).
    return refused("invalid value in request")


@app.exception_handler(db.PoolBusy)
@app.exception_handler(psycopg.errors.TooManyConnections)
def _busy(_: Request, __: Exception) -> JSONResponse:
    # Every connection of this process (or the role) is taken: a retry in a moment finds one. Not a 500.
    return JSONResponse({"detail": "the service is busy; retry shortly"}, status_code=503, headers={"Retry-After": "2"})


@app.exception_handler(psycopg.errors.QueryCanceled)
def _too_slow(_: Request, __: psycopg.errors.QueryCanceled) -> JSONResponse:
    return JSONResponse({"detail": "the query took too long; narrow the request"},
                        status_code=503, headers={"Retry-After": "5"})


def day_start(d: date) -> datetime:
    """A date filter's lower bound: the day's first instant in UTC, as the contract states, never the
    session's time zone (QA M15)."""
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def day_end(d: date) -> datetime:
    """A date filter's upper bound, inclusive: the whole of the day in UTC. A bare date compared with a
    timestamptz was midnight at the start of it, so a deadline at 17:00 on the stated day was left out."""
    return datetime.combine(d, time.max, tzinfo=timezone.utc)


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
    # The API's own, read-only role when one is configured (migration 0024). At most `api_connections` at once in this
    # process; a request over that waits `pool_wait_ms`, then is answered 503 (`_busy`).
    with db.api_connect() as conn:
        yield conn


def get_conn_reserved():
    """For the health check: its own small bound (`db.HEALTH_CONNECTIONS`) in the headroom the API bound leaves in
    the role, so a saturated pool cannot make the container look dead, and a burst on /v1/health cannot exhaust the role."""
    with db.api_connect(health=True) as conn:
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
          JOIN opportunity b ON b.id <> a.id AND b.is_defence AND NOT b.suppressed AND (
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
            "organisation_id": None if r.get("buyer_withheld") else r.get("buyer_org_id"),
            "name": (WITHHELD_NAME if r.get("buyer_withheld")
                     else redact_emails(r["buyer_name_raw"])),
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
        status=r["eff_status"] if "eff_status" in r else effective_status(
            r.get("status"), r.get("deadline_at"), r.get("published_at"), procedure=r.get("procedure_type")),
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

# A notice that states no deadline is only "open" by the rule above, which is a guess:
# 110 of the 129 French notices served open on 13 October 2026 had no deadline and a TED
# twin whose deadline had passed. So a notice with no deadline of its own is not served
# open when the rest of its procedure says it is over:
#   - the TED notice it was forwarded as (`ted_ref`) is awarded, cancelled, closed, or open
#     with a passed deadline
#   - another notice of the same procedure is an award or a cancellation published on or
#     after it
#   - a rectificatif names it (`related_native_id`): the newer notice stands for it, and
#     it is listed itself when it is open
# A notice that states its own deadline is never judged by its twin: the two sources may
# differ for a reason (an extension) and the national portal is the one that is read.
# The rule is the database function of migration 0041, not subqueries written here: in
# the status expression they made the tenders list 40 times slower.
SUPERSEDED_SQL = ("dgate_superseded(o.id, o.source_id, o.native_id, o.ted_ref, "
                  "o.procedure_identifier, o.published_at)")

# A planned notice (`forthcoming`: a prior information notice) is not closed while its deadline, if it
# states one, is ahead (WP-52, T8): it is neither open for tenders nor closed, so it is listed under
# `status=planned` and `all`, and a passed deadline makes it `expired` like any other.
# WP-103 (personas p03, p07, p10): a planned notice that states no deadline is not planned forever: one published over
# PLANNED_WITHOUT_DEADLINE_DAYS ago is `expired` too (a prior information notice announces a call within twelve months:
# "Planned" stood on BAAINBw notices of 2017 to 2020 and on 4,613 of the 5,196 planned TED notices of 24 October 2026).
# And an open notice of a procedure without a call for competition (`*-wo-call`: the German "Verhandlungsvergabe ohne
# Teilnahmewettbewerb" and the like, de_bkms 283577) that states no deadline is not open to anyone who reads it: the
# buyer invites whom it chooses. It is served `expired` (listed as closed), never "Open" with no deadline and no call.
PLANNED_WITHOUT_DEADLINE_DAYS = 365
NO_CALL_PROCEDURE = "wo-call"           # the end of the procedure code
EFFECTIVE_STATUS_SQL = f"""(CASE
    WHEN o.status = 'open' AND (
         o.deadline_at < now()
      OR (o.deadline_at IS NULL
          AND (o.published_at < (now() - interval '{OPEN_WITHOUT_DEADLINE_DAYS} days')
               OR right(o.procedure_type, {len(NO_CALL_PROCEDURE)}) = '{NO_CALL_PROCEDURE}'
               OR {SUPERSEDED_SQL})))
    THEN 'expired'
    WHEN o.status = 'forthcoming' AND o.deadline_at < now() THEN 'expired'
    WHEN o.status = 'forthcoming' AND o.deadline_at IS NULL
         AND o.published_at < (now() - interval '{PLANNED_WITHOUT_DEADLINE_DAYS} days') THEN 'expired'
    ELSE o.status END)"""


def effective_status(status: str | None, deadline_at: datetime | None,
                     published_at: date | None, now: datetime | None = None,
                     superseded: bool = False, procedure: str | None = None) -> str | None:
    """The Python twin of EFFECTIVE_STATUS_SQL, for a row already fetched. `superseded`
    is SUPERSEDED_SQL for that row (it needs the other rows, so the caller asks the
    database); it only counts for a notice with no deadline of its own. `procedure`: the
    stored `procedure_type` (WP-103: a procedure without a call)."""
    now = now or datetime.now(timezone.utc)
    if status == "forthcoming":
        if deadline_at is not None:
            return "expired" if deadline_at < now else status
        old = published_at is not None and published_at < (now - timedelta(days=PLANNED_WITHOUT_DEADLINE_DAYS)).date()
        return "expired" if old else status
    if status != "open":
        return status
    if deadline_at is not None:
        return "expired" if deadline_at < now else "open"
    if superseded or (procedure or "").endswith(NO_CALL_PROCEDURE):
        return "expired"
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
#
# Two further groups leave `core` for `supply` (owner decision of 14 October 2026):
# the directive as the only signal from a civil buyer (`directive_civil_buyer`), and a
# military CPV as the only signal from a police, prison, border, customs or tax body
# (`security_buyer_cpv`). The definition is dgate/classify.py's, written once.
CORE_SQL = classify.CORE_SQL
GOODS_SQL = {"defence": classify.GOODS_DEFENCE_SQL}      # the `goods` parameter
SCOPE_SQL = {
    "core": CORE_SQL,
    "supply": classify.SUPPLY_SQL,
    # The site's default (owner decision of 16 October 2026): the two together, `core` and
    # `supply`, which do not overlap (SUPPLY_SQL excludes CORE_SQL). Not `all`: a military
    # CPV bought by a municipality or a hospital (`dual_use`) is in neither.
    "relevant": f"({CORE_SQL} OR {classify.SUPPLY_SQL})",
    "all": "TRUE",
}


def row_scope(r: dict[str, Any]) -> str:
    """The Python twin of SCOPE_SQL for a row already fetched: `core` or `supply`."""
    return "core" if classify.in_core(
        legal_basis=bool(r.get("sig_legal_basis")),
        military_cpv=bool(r.get("sig_cpv_military")), dual_use=bool(r.get("dual_use")),
        buyer=bool(r.get("sig_buyer")), linked_defence=bool(r.get("sig_linked_defence")),
        buyer_class=r.get("buyer_class")) else "supply"


BASE_SELECT = f"""
    SELECT o.*, s.code AS source_code, s.attribution AS source_attribution,
           org.confidence AS org_confidence, {EFFECTIVE_STATUS_SQL} AS eff_status
      FROM opportunity o
      JOIN source s ON s.id = o.source_id
      LEFT JOIN organisation org ON org.id = o.buyer_org_id
"""


@app.get("/v1/opportunities", response_model=list[OpportunityOut])
@cache_list("opportunities")
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
                                   "supply: only the buyer is a defence body, or one of the two "
                                   "groups (directive from a civil buyer, military CPV from "
                                   "a security body); all: both"),
    collapse: bool = Query(True, description="show a national notice once: hide it when "
                                             "the TED notice it was forwarded as is also "
                                             "in this result (see `same_notice`)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
    conn=Depends(get_conn),
):
    where = ["o.is_defence = TRUE", "NOT o.suppressed", f"{EFFECTIVE_STATUS_SQL} = %s",
             SCOPE_SQL[scope]]
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
        params.append(day_start(deadline_after))
    if deadline_before:
        where.append("o.deadline_at <= %s")
        params.append(day_end(deadline_before))
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
    # Defence rows only, as `/v1/tenders/{id}` and the list: 268 notices that are held and
    # not (or no longer) defence were served here with their archive (audit L1, X-8).
    row = conn.execute(BASE_SELECT + " WHERE o.id = %s AND o.is_defence", (opp_id,)).fetchone()
    if not row:
        raise HTTPException(404, "not found")
    if row["suppressed"]:
        raise removed()
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


def public_snapshot(payload: dict[str, Any] | None, *, buyer_withheld: bool = False
                    ) -> dict[str, Any]:
    """A stored version payload as it may be served: allow-listed and redacted."""
    kept = {k: v for k, v in (payload or {}).items() if k in SNAPSHOT_FIELDS}
    if buyer_withheld and "buyer_name_raw" in kept:
        kept["buyer_name_raw"] = WITHHELD_NAME
    if "source_url" in kept:
        kept["source_url"] = http_url(kept["source_url"])
    return redact_emails(kept)


# WP-119: the main CPV code is the serving row's (its first code). A CPV list is a set to the archive (`db.same_value`), so
# a corrected main code (TenderNed's flagged one, WP-113: 145 of 481 notices) is no new version and the stored versions
# keep the order they were read in; a snapshot that holds the serving row's main code lists it first, with this note.
MAIN_CODE_NOTE = {"kind": "main_code", "note": "Main CPV code as the notice page states it, listed first; the archive "
                                               "stores the codes of a version as a set, in the order first read."}


def main_code_first(snapshot: dict[str, Any], main: str | None) -> bool:
    """Put `main` first in the snapshot's CPV list when the list holds it elsewhere; whether it moved."""
    codes = snapshot.get("cpv_codes")
    if not main or not isinstance(codes, list) or not codes or codes[0] == main or main not in codes:
        return False
    snapshot["cpv_codes"] = [main, *(c for c in codes if c != main)]
    return True


@app.get("/v1/opportunities/{opp_id}/versions")
def get_versions(opp_id: int = Path(ge=1, le=MAX_BIGINT), conn=Depends(get_conn)):
    """The archive: full observation timeline for one notice.

    Deadline extensions, value revisions and scope amendments, each with the
    observation timestamp and the list of fields that changed. Not available
    from any upstream source.
    """
    gone = conn.execute("SELECT suppressed, buyer_withheld, cpv_codes[1] AS main FROM opportunity "
                        "WHERE id = %s AND is_defence", (opp_id,)).fetchone()
    if gone and gone["suppressed"]:
        raise removed()
    withheld = bool(gone and gone["buyer_withheld"])
    main = gone["main"] if gone else None
    rows = conn.execute(
        """SELECT v.version, v.observed_at, v.valid_from, v.valid_to,
                  v.changed_fields, v.payload,
                  coalesce(json_agg(json_build_object('kind', n.kind, 'note', n.note))
                           FILTER (WHERE n.id IS NOT NULL), '[]') AS notes
             FROM opportunity_version v
             JOIN opportunity o ON o.id = v.opportunity_id AND o.is_defence
             LEFT JOIN opportunity_version_note n ON n.opportunity_version_id = v.id
            WHERE v.opportunity_id = %s
            GROUP BY v.id
            ORDER BY v.version""",
        (opp_id,),
    ).fetchall()
    if not rows:
        raise HTTPException(404, "not found")
    versions = []
    for r in rows:
        snapshot = public_snapshot(r["payload"], buyer_withheld=withheld)
        notes = redact_emails(r["notes"])
        if main_code_first(snapshot, main):
            notes = [*notes, MAIN_CODE_NOTE]
        versions.append({
            "version": r["version"],
            "observed_at": r["observed_at"],
            "valid_from": r["valid_from"],
            "valid_to": r["valid_to"],
            "changed_fields": r["changed_fields"] or [],
            "snapshot": snapshot,
            # A version the archive recorded wrongly is annotated, never
            # removed: see migration 0006. Clients should not present a
            # `reread`, `out_of_order` or `remapped` version as a real amendment.
            "notes": notes,
        })
    return {
        "opportunity_id": opp_id,
        "version_count": len(rows),
        # Not `len(rows) > 1`: a version that only re-read old content, arrived out
        # of order, is one of our own re-mappings, only moved the publication date or
        # left lines that read the same is not an amendment. The timeline's own rule,
        # so the flag and the list on the tender page cannot disagree.
        "amended": any(not e.get("historic") for e in _tenders.timeline([
            {"version": r["version"], "observed_at": r["observed_at"],
             "changed_fields": r["changed_fields"], "payload": r["payload"],
             "kinds": [n["kind"] for n in (r["notes"] or [])]}
            for r in rows])[1:]),
        "versions": versions,
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
           c.suppressed, s.code AS source_code, s.attribution AS source_attribution
      FROM call c JOIN programme p ON p.id = c.programme_id
      LEFT JOIN source s ON s.id = c.source_id
"""


def _call_select() -> str:
    from .funding import EFFECTIVE_STATUS

    return CALL_SELECT.replace("c.status,", f"c.status, {EFFECTIVE_STATUS} AS effective_status,", 1)


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
        # The status the dates settle (funding.EFFECTIVE_STATUS), not the source's word: a call the
        # portal still lists as forthcoming after its opening day is open (QA audit, 21 Oct 2026).
        status=r.get("effective_status", r.get("status")),
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
    from .funding import EFFECTIVE_STATUS

    where: list[str] = ["NOT c.suppressed AND NOT c.out_of_scope"]   # WP-109: migration 0121
    params: list[Any] = []
    if status == "evaluated":       # the source's own word; the effective status calls it closed
        where.append("c.status = 'evaluated'")
    elif status != "all":
        where.append(f"{EFFECTIVE_STATUS} = %s")
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
        params.append(day_start(deadline_after))
    if deadline_before:
        where.append("c.deadline_at <= %s")
        params.append(day_end(deadline_before))

    sql = (_call_select()
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
        _call_select().replace("c.first_seen_at",
                            "c.eligibility_text, c.conditions_raw, c.details_seen_at, "
                            "s.commercial_ok AS source_commercial_ok, c.first_seen_at")
        + " WHERE c.id = %s", (call_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="no such call")
    if row["suppressed"]:
        raise removed()
    base = _call_to_out(row)
    # The source's own words go out under the rule of /v1/funding/{slug} (WP-71, QA H2): a
    # source on SOURCE_TEXT_SOURCES whose licence row says commercial reuse is allowed, with
    # e-mail addresses redacted. BDNS and NCBR text is not served; unsetting the flag withdraws it.
    from .funding import SOURCE_TEXT_SOURCES

    may_serve = (row.get("source_code") in SOURCE_TEXT_SOURCES
                 and row.get("source_commercial_ok") is True)
    return CallDetailOut(**base.model_dump(),
                         eligibility_text=redact_emails(row.get("eligibility_text")) if may_serve else None,
                         conditions=redact_emails(row.get("conditions_raw")) if may_serve else None,
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
            WHERE a.normalised_name = %s AND a.country_hint = %s AND NOT o.suppressed
              AND o.individual_reason IS NULL      -- a natural person is not confirmed as "known" (WP-39, N2)
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


HEALTH_COUNTS_SECONDS = 600


def _read_archive_counts(conn) -> tuple[int | None, int | None, Any]:
    """(defence rows, archive versions, oldest observation). Measured on production, 17 October
    2026: counting the versions took 4.8 s and `min(observed_at)` 5.2 s (parallel scans of 650k
    rows, both over the API role's 5 s budget on a busy host), the defence count 1.4 s. So the
    versions are the planner's own estimate (`pg_class.reltuples`, kept current by autovacuum;
    the exact count where the table was never analysed, which is a small table), and the oldest
    observation reads the index of migration 0074."""
    estimate = conn.execute(
        "SELECT reltuples::bigint AS n FROM pg_class WHERE oid = 'opportunity_version'::regclass").fetchone()["n"]
    versions = estimate if estimate >= 0 else conn.execute(
        "SELECT count(*) AS n FROM opportunity_version").fetchone()["n"]
    oldest = conn.execute("SELECT min(observed_at) AS t FROM opportunity_version").fetchone()["t"]
    try:        # a sequential scan (1.4 s measured, over 5 s on a busy host): the one figure that may be missing
        defence = conn.execute("SELECT count(*) AS n FROM opportunity "
                               "WHERE is_defence AND NOT suppressed").fetchone()["n"]
    except psycopg.errors.QueryCanceled:
        conn.rollback()
        defence = None
    return defence, versions, oldest


def _archive_counts(conn) -> tuple[int | None, int | None, Any]:
    """The three figures of `_read_archive_counts`, kept for `HEALTH_COUNTS_SECONDS` and read by one
    request at a time (`stats.cached`, single flight): a public endpoint must not turn into one
    scan per caller, and the container health check asks every 30 seconds. A read that does not
    finish in the API role's budget gives no figures (None) and is not tried again for
    `RETRY_SECONDS`: the health report must not fail for want of its counts. 0 seconds, as in
    the tests, reads them every time."""
    from . import stats

    ttl = HEALTH_COUNTS_SECONDS if settings().list_cache_seconds > 0 else 0
    try:
        return stats.cached("health-archive-counts", lambda: _read_archive_counts(conn), ttl)
    except psycopg.errors.QueryCanceled:
        conn.rollback()
        with stats._lock:
            stats._put("health-archive-counts", (None, None, None), stats.RETRY_SECONDS)
        return None, None, None


def _completeness_line(check: dict[str, Any]) -> dict[str, Any]:
    """One line for the health page: the newest day compared and whether any day was short."""
    days = check.get("days") or {}
    newest = max(days) if days else None
    row = days.get(newest, {}) if newest else {}
    return {"day": newest, "landed": row.get("landed"), "official": row.get("official"),
            "short": bool(check.get("short"))}


_FLOOR_MESSAGE = re.compile(r"fetched \d+ below floor \d+$")


def _under_floor(error: str | None) -> bool:
    """Whether a partial run is partial because it collected less than its floor (`db.finish_run`'s
    own message), or gave no reason at all."""
    return not error or bool(_FLOOR_MESSAGE.match(error))


# WP-114: this many newest runs in a row with nothing fetched (and a minimum expected) make a source unhealthy
ZERO_RUNS_UNHEALTHY = 2


def _last_jobs(conn) -> dict[str, Any]:
    """The newest run of each job in `job_run` (migration 0126): when it started and finished, how it ended. Not its
    detail: a failed job's is an exception text, which can name an object-store address (as the run errors above)."""
    try:
        with conn.transaction():       # a savepoint: before the migration the table is not there
            rows = conn.execute(
                """SELECT DISTINCT ON (job) job, started_at, finished_at, status
                     FROM job_run ORDER BY job, started_at DESC""").fetchall()
    except psycopg.Error:
        return {}
    return {r["job"]: {"started_at": r["started_at"], "finished_at": r["finished_at"], "status": r["status"]}
            for r in rows}


@app.get("/v1/health")
def health(conn=Depends(get_conn_reserved)):
    """Coverage health, not just liveness.

    Reports the last run per source and flags anything not successful. A green
    process with a dead connector is the failure this endpoint exists to catch.
    """
    # LEFT JOIN from source, not an inner join from ingest_run: a source that
    # has never run at all must appear here. Reporting "ok" because there are
    # no failed runs, when there are no runs, is precisely the green tick this
    # endpoint exists to prevent.
    #
    # The latest *finished* run is what is judged (QA M1): a PLACSP run takes forty minutes,
    # and judging the one in progress made the answer `degraded` for the whole of it. A run
    # still going is reported beside it, and is a problem only past `db.STALE_RUN_HOURS`.
    rows = conn.execute(
        """SELECT s.code, s.active, f.status, f.finished_at, f.started_at,
                  f.records_fetched, f.error_message, f.detail, r.started_at AS running_since
             FROM source s
             LEFT JOIN LATERAL (SELECT status, finished_at, started_at, records_fetched,
                                       error_message, detail
                                  FROM ingest_run WHERE source_id = s.id AND status <> 'running'
                                 ORDER BY started_at DESC LIMIT 1) f ON TRUE
             LEFT JOIN LATERAL (SELECT started_at FROM ingest_run
                                 WHERE source_id = s.id AND status = 'running'
                                 ORDER BY started_at DESC LIMIT 1) r ON TRUE
            WHERE s.active
            ORDER BY s.code"""
    ).fetchall()
    total, versions, oldest = _archive_counts(conn)

    backup = db.backup_freshness(conn, settings().backup_stale_hours)

    stale_after = timedelta(hours=STALE_AFTER_HOURS)
    now = datetime.now(timezone.utc)
    sources: list[dict[str, Any]] = []
    unhealthy: list[str] = []
    warnings: list[str] = []
    stuck_after = timedelta(hours=db.STALE_RUN_HOURS)
    from .funding import control_alerts, run_signals

    signals = run_signals(conn, now)
    alerts = control_alerts(conn)
    for r in rows:
        # Only what a reader of the coverage needs. The run's error text is a
        # `str(exception)` and has held an object-store URL; it stays in the table.
        item = {"code": r["code"], "active": r["active"], "status": r["status"],
                "finished_at": r["finished_at"], "records_fetched": r["records_fetched"]}
        running = r["running_since"]
        if running is not None:
            item["running_since"] = running
        check = (r["detail"] or {}).get("completeness")
        if check:
            # Latest complete days against the portal's own day totals (ops/controls.py).
            item["completeness"] = _completeness_line(check)
        sig = signals.get(r["code"], {})
        if sig.get("refusedSince"):
            item["refused_since"] = sig["refusedSince"]
        if running is not None and now - running > stuck_after:
            item["health"] = "unhealthy"            # a run nobody finished
        elif sig.get("refusedSince") or sig.get("zeroRuns", 0) >= ZERO_RUNS_UNHEALTHY:
            # WP-114: the source refuses us, or its last runs fetched nothing at all: not a warning (pl_ezam, 24 Oct)
            item["health"] = "unhealthy"
        elif r["status"] is None:
            item["status"] = "running" if running is not None else "never_run"
            item["health"] = "running" if running is not None else "unhealthy"
        elif r["status"] == "partial" and not _under_floor(r["error_message"]):
            # Partial for a stated reason (a portal day short of its own total, a feed the
            # source left stale): a warning, not an outage. Under its floor is unhealthy.
            item["health"] = "warning"
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
        if item["health"] == "warning":
            warnings.append(r["code"])
        elif item["health"] not in ("healthy", "running"):
            unhealthy.append(r["code"])
        sources.append(item)

    return {
        # A backup that is stale is a degraded service: the archive timeline exists
        # nowhere else. Ages only, never a file name or a path (`db.backup_freshness`).
        # WP-114: a data check in alert degrades it too (placsp_links was in alert while this said "ok")
        "status": "degraded" if unhealthy or backup["status"] == "stale" or alerts else "ok",
        "unhealthy_sources": unhealthy,
        "warning_sources": warnings,
        "alerting_controls": [a["control"] for a in alerts],
        # WP-114: the last run of every scheduled job (`job_run`), so a slot a restart skipped shows
        "jobs": _last_jobs(conn),
        "backup": backup,
        "controls": {c["control"]: {"status": c["status"], "checked_at": c["checked_at"],
                                    **c["detail"]}
                     for c in conn.execute(
                         "SELECT control, status, checked_at, detail FROM control_check"
                     ).fetchall()},
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

from . import tenders as _tenders  # noqa: E402
from .tenders import router as _tenders_router  # noqa: E402

app.include_router(_tenders_router)

# What changed in the last 14 days (changes.py): new notices and real amendments.
from .changes import router as _changes_router  # noqa: E402

app.include_router(_changes_router)

# The weekly digest (weekly_digest.py): the same data as /v1/changes and the funding list, by ISO week.
from .weekly_digest import router as _digest_router  # noqa: E402

app.include_router(_digest_router)

# Partner suggestions for a funding call and the document facts of the fit badge (partners.py, WP-32).
from .partners import router as _partners_router  # noqa: E402

app.include_router(_partners_router)

# Market overview and the buyer profile: cached counts of notices (stats.py).
from .stats import router as _stats_router  # noqa: E402

app.include_router(_stats_router)

# Accounts: reached only by the site's own server over the internal network, never routed
# by Caddy (docs/design/ACCOUNT_CONTRACT.md).
from .accounts import AccountError, account_error_handler  # noqa: E402
from .accounts import internal_router as _internal_router  # noqa: E402
from .accounts import router as _account_router  # noqa: E402

app.include_router(_account_router)
app.include_router(_internal_router)
app.add_exception_handler(AccountError, account_error_handler)

# Layer 3, readiness (dgate/readiness): the public requirements catalogue and the stateless
# assessment. A refused request is not echoed back: see `_validation_error`.
from fastapi.exceptions import RequestValidationError  # noqa: E402

from .readiness.api import router as _readiness_router  # noqa: E402

app.include_router(_readiness_router)

# The regulatory tracker (dgate/regulation): sourced entries about the rules that matter to a supplier.
from .regulation import router as _regulation_router  # noqa: E402

app.include_router(_regulation_router)


@functools.lru_cache(maxsize=4)
def _schema_names(application: FastAPI) -> frozenset[str]:
    """Every name the API itself defines: the properties of its models and its parameters."""
    names: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("properties"), dict):
                names.update(node["properties"])
            if "in" in node and isinstance(node.get("name"), str):
                names.add(node["name"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    try:
        walk(application.openapi())
    except Exception:  # noqa: BLE001 - no schema: every name is hidden, the refusal still answers
        return frozenset()
    return frozenset(names)


# Layer 2 for the user (network_api.py): organisations, projects, analytics. After `resolve` above, so that
# `/v1/organisations/resolve` is not taken for a slug.
from .network_api import router as _network_router  # noqa: E402

app.include_router(_network_router)


# The supplier map (suppliers.py, WP-37): the winners of the award set (award_set.py, WP-85), as the demand answer counts them.
from .suppliers import router as _suppliers_router  # noqa: E402

app.include_router(_suppliers_router)

# The demand map of the supplier report (demand.py, WP-66): stateless, the CPV codes come in the body.
from .demand import router as _demand_router  # noqa: E402

app.include_router(_demand_router)

# One search box over the five lists (search.py, WP-86): each group is the list endpoint itself.
from .search import router as _search_router  # noqa: E402

app.include_router(_search_router)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    """The 422 for a refused request, on every route: where it was wrong and why, never what was
    sent. The framework's own answer repeats the input (3,000 characters of a query value came
    back, and with them anything a body held) and an unknown key of a body is part of its
    location. Here a location keeps the names of the API's own fields and parameters and indexes;
    any other name (a key someone invented, a key of a dictionary field) becomes `*`. The
    readiness assessment takes the profile of a company, so for it this matters most
    (WP-34 C6, verifier V-C)."""
    known = _schema_names(request.app) | {"body", "query", "path", "header", "cookie"}
    def where(e):
        loc = [p if isinstance(p, int) or p in known else "*" for p in e["loc"]]
        # The readiness assessment takes a company's profile: an unknown key there is named as such.
        if e["type"] == "extra_forbidden" and request.url.path.startswith("/v1/readiness"):
            return loc[:-1] + ["(unknown field)"]
        return loc

    problems = [{"loc": where(e), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return JSONResponse({"detail": problems}, status_code=422)
