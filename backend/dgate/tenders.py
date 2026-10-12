"""Tenders and buyers: the shape docs/design/API_CONTRACT.md fixes for the site.

The sibling of `funding.py` for procurement notices (`opportunity`) and the bodies
that publish them (`organisation`). `/v1/opportunities` stays as it is: that is the
data model's own view, this is the page's.

Decisions that shape it:

  - a notice is `open` as of now: a passed deadline, or no deadline and a publication
    date over a year old, is `closed` (the stored status is the one it was published
    with, which a source rarely corrects)
  - a national notice whose TED twin is in the same result is shown once
  - amounts are never converted; a value range selects one currency
  - a tender names its buyer the way the notice itself does (`buyerName`); the buyers
    catalogue, and `buyerCanonicalName` beside it, use the organisation's commonest
    spelling rather than the normalised key the entity resolver uses
  - versions the archive annotated as `reread`, `out_of_order` or `remapped` are not
    amendments and are neither counted nor listed; neither is a version that moved only
    the publication date (the PLACSP feed stamp: 76% of the amendments on 12 October
    2026), nor one whose changes read the same before and after
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .db import same_value
from .funding import Budget, SourceAttribution, _like, anomalies, get_conn, make_slug
from .normalise import http_url, redact_emails

router = APIRouter()

SLUG_RE = re.compile(r"^([0-9]{1,9})(?:-|$)", re.ASCII)
MAX_BIGINT = 9_223_372_036_854_775_807
MAX_LIST_ITEMS = 20
SLUG_WINDOW_DAYS = 365
TENDER_SLUG_LIMIT = 5000
BUYER_SLUG_LIMIT = 2000

# A version the archive recorded wrongly is annotated, never removed (migration 0006).
# `remapped` (migration 0028): appended by a bulk re-derivation from the same source
# payload; the publisher amended nothing.
NOT_AN_AMENDMENT = "('reread', 'out_of_order', 'remapped')"

CORE = "(o.sig_legal_basis OR o.sig_cpv)"


class Tender(BaseModel):
    id: str
    slug: str
    noticeId: str
    title: str
    titleLanguage: str | None
    originalTitle: str | None
    originalLanguage: str | None
    buyerId: str | None
    buyerSlug: str | None
    buyerName: str
    buyerCanonicalName: str | None = None
    country: str | None
    cpv: str | None
    cpvCodes: list[str]
    procedure: str | None
    legalBasis: str | None
    scope: str
    deadline: datetime | None
    publishedAt: datetime | None
    estimatedValue: Budget | None
    lots: int | None = None
    anomalies: list[str] = []
    status: str
    statusNative: str | None
    amended: bool
    versionCount: int
    securityClearance: bool
    subcontracting: bool
    sameNotice: list[dict[str, Any]]
    source: SourceAttribution


class TenderPage(BaseModel):
    items: list[Tender]
    total: int
    page: int
    pageSize: int


class FieldChange(BaseModel):
    field: str
    label: str
    before: str | None
    after: str | None


class TenderVersion(BaseModel):
    version: int
    detectedAt: datetime
    changes: list[FieldChange]


class Buyer(BaseModel):
    id: str
    slug: str
    name: str
    country: str | None
    tenderCount: int
    openCount: int
    lastPublishedAt: datetime | None
    isDefenceBuyer: bool


class BuyerPage(BaseModel):
    items: list[Buyer]
    total: int
    page: int
    pageSize: int


def _api():
    """The API module's helpers; it includes this router, so they are read late."""
    from . import api
    return api


def _split(value: str | None, name: str, *, upper: bool = False, max_length: int = 64) -> list[str]:
    items = [i.strip() for i in (value or "").split(",") if i.strip()]
    if len(items) > MAX_LIST_ITEMS:
        raise HTTPException(422, f"{name}: at most {MAX_LIST_ITEMS} values")
    for item in items:
        if len(item) > max_length or "\x00" in item:
            raise HTTPException(422, f"{name}: value too long")
    return [i.upper() for i in items] if upper else items


def _day(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time(0, 0), tzinfo=timezone.utc)
    return None


_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")

# TED's procedure-type codes (eForms codelist `procurement-procedure-type`), said in
# English. These are the notice's own words in the Publications Office's vocabulary, not
# a translation of someone's text.
TED_PROCEDURES = {
    "open": "Open procedure",
    "restricted": "Restricted procedure",
    "neg-w-call": "Negotiated procedure with prior call for competition",
    "neg-wo-call": "Negotiated procedure without prior call for competition",
    "comp-dial": "Competitive dialogue",
    "innovation": "Innovation partnership",
    "oth-single": "Other single-stage procedure",
    "oth-mult": "Other multi-stage procedure",
    "comp-tend": "Competitive tendering",
}


def procedure_label(value: str | None) -> str | None:
    """The procedure as the source states it, readable. A bare number (the numeric
    TED subtype, `16`, `29`) names nothing a reader knows and would be a guess to
    translate, so it is left out; a TED procedure-type code is spelled out; a word such
    as `ContractNotice` is split into words; anything else keeps the source's casing
    ("Procédure NC" is not "Procédure nc")."""
    text = (value or "").strip()
    if not text or text.isdigit():
        return None
    known = TED_PROCEDURES.get(text.lower())
    if known:
        return known
    if "_" in text or _CAMEL.search(text):
        return _CAMEL.sub(" ", text).replace("_", " ").capitalize()
    return text[0].upper() + text[1:]


# ---------------------------------------------------------------- mapping

# The columns a tender needs and no more: `o.*` carries the search vector, and carrying
# it through the window count and the sort made the default page take over a second.
TENDER_COLUMNS = (
    "o.id, o.native_id, o.buyer_org_id, o.buyer_name_raw, o.country, o.title_original, "
    "o.title_en, o.original_language, o.procedure_type, o.legal_basis, o.value_amount, "
    "o.value_currency, o.published_at, o.deadline_at, o.cpv_codes, o.sig_legal_basis, "
    "o.sig_cpv, o.security_clearance_required, o.subcontracting_signal, o.source_url, "
    "o.status, o.ted_ref, o.lot_count"
)

TENDER_SELECT = f"""
    SELECT {TENDER_COLUMNS}, s.code AS source_code, s.name AS source_name,
           s.licence AS source_licence, s.attribution AS source_attribution
      FROM opportunity o
      JOIN source s ON s.id = o.source_id
"""


def _buyer_names(conn, org_ids: list[int]) -> dict[int, str]:
    """The commonest spelling of each organisation's name among its notices."""
    if not org_ids:
        return {}
    rows = conn.execute(
        """SELECT DISTINCT ON (buyer_org_id) buyer_org_id, buyer_name_raw
             FROM (SELECT buyer_org_id, buyer_name_raw, count(*) AS n
                     FROM opportunity
                    WHERE buyer_org_id = ANY(%s) AND is_defence
                    GROUP BY buyer_org_id, buyer_name_raw) t
            ORDER BY buyer_org_id, n DESC, buyer_name_raw""",
        (org_ids,)).fetchall()
    return {r["buyer_org_id"]: redact_emails(r["buyer_name_raw"]) for r in rows}


def _observed(conn, ids: list[int]) -> dict[int, datetime]:
    """When each notice was last observed: its newest version's observation time.
    Read for the page only, never inside the filtered query."""
    if not ids:
        return {}
    rows = conn.execute(
        "SELECT opportunity_id, max(observed_at) AS seen FROM opportunity_version "
        "WHERE opportunity_id = ANY(%s) GROUP BY opportunity_id", (ids,)).fetchall()
    return {r["opportunity_id"]: r["seen"] for r in rows}


def _version_counts(conn, ids: list[int]) -> dict[int, int]:
    """How many real versions each notice has: the first, and each later one that
    changed something a reader can see (see `timeline`)."""
    if not ids:
        return {}
    rows = conn.execute(TIMELINE_SQL.format(where="v.opportunity_id = ANY(%s)"),
                        (ids,)).fetchall()
    by_notice: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        by_notice.setdefault(r["opportunity_id"], []).append(r)
    return {oid: len(timeline(group)) for oid, group in by_notice.items()}


def to_tender(r: dict[str, Any], names: dict[int, str], versions: dict[int, int],
              twins: list[dict[str, Any]], observed: datetime | None) -> dict[str, Any]:
    api = _api()
    title_en = redact_emails(r.get("title_en"))
    original = redact_emails(r["title_original"])
    heading = title_en or original
    other = original if title_en and original and original.strip() != title_en.strip() else None
    eff = api.effective_status(r.get("status"), r.get("deadline_at"), r.get("published_at"))
    org_id = r.get("buyer_org_id")
    # The notice's own spelling is what the notice says; the organisation's commonest
    # spelling is what the organisation is called. 15,937 TED rows were being shown
    # under the second, which merges a sub-unit into its parent.
    own_name = redact_emails(r["buyer_name_raw"])
    org_name = names.get(org_id) or own_name
    buyer_name = own_name or org_name
    n_versions = versions.get(r["id"], 1) or 1
    cpv = r.get("cpv_codes") or []
    amount = r.get("value_amount")
    return {
        "id": str(r["id"]),
        "slug": make_slug(r["id"], heading),
        "noticeId": r["native_id"],
        "title": heading,
        "titleLanguage": "en" if title_en else r.get("original_language"),
        "originalTitle": other,
        "originalLanguage": r.get("original_language") if other else None,
        "buyerId": str(org_id) if org_id else None,
        "buyerSlug": make_slug(org_id, org_name) if org_id else None,
        "buyerName": buyer_name,
        "buyerCanonicalName": org_name if org_id else None,
        "country": r.get("country"),
        "cpv": cpv[0] if cpv else None,
        "cpvCodes": cpv,
        "procedure": procedure_label(r.get("procedure_type")),
        "legalBasis": r.get("legal_basis"),
        "scope": "core" if (r.get("sig_legal_basis") or r.get("sig_cpv")) else "supply",
        "deadline": r.get("deadline_at"),
        "publishedAt": _day(r.get("published_at")),
        "estimatedValue": ({"amount": float(amount), "currency": r.get("value_currency") or "EUR"}
                           if amount else None),
        "lots": r.get("lot_count"),
        "anomalies": anomalies(r.get("deadline_at"), r.get("published_at")),
        "status": "open" if eff == "open" else "closed",
        "statusNative": eff,
        "amended": n_versions > 1,
        "versionCount": n_versions,
        "securityClearance": bool(r.get("security_clearance_required")),
        "subcontracting": bool(r.get("subcontracting_signal")),
        "sameNotice": [{"source": t["source"], "url": t.get("url")} for t in twins],
        "source": {
            "sourceId": r["source_code"],
            "sourceName": r["source_name"],
            "url": http_url(r.get("source_url")),
            "retrievedAt": observed or datetime.now(timezone.utc),
            "licence": r["source_licence"] or "",
            "attribution": api._attribution(r),
        },
    }


def _present(conn, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = [r["id"] for r in rows]
    names = _buyer_names(conn, sorted({r["buyer_org_id"] for r in rows if r.get("buyer_org_id")}))
    versions = _version_counts(conn, ids)
    twins = _api()._twins(conn, ids)
    seen = _observed(conn, ids)
    return [to_tender(r, names, versions, twins.get(r["id"], []), seen.get(r["id"]))
            for r in rows]


# -------------------------------------------------------------- endpoints

@router.get("/v1/tenders", response_model=TenderPage)
def list_tenders(
    q: str | None = Query(None, max_length=100),
    country: str | None = Query(None, max_length=200),
    cpv: str | None = Query(None, max_length=400),
    status: str = Query("open", pattern="^(open|closed|all)$"),
    scope: str = Query("core", pattern="^(core|supply|all)$"),
    buyer: int | None = Query(None, ge=1, le=MAX_BIGINT),
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    min_: float | None = Query(None, alias="min", ge=0, le=1e13),
    max_: float | None = Query(None, alias="max", ge=0, le=1e13),
    currency: str = Query("EUR", pattern="^[A-Za-z]{3}$"),
    sort: str = Query("deadline-asc", pattern="^(deadline-asc|published-desc)$"),
    page: int = Query(1, ge=1, le=1000),
    pageSize: int = Query(20, ge=1, le=100),
    conn=Depends(get_conn),
):
    api = _api()
    eff = api.EFFECTIVE_STATUS_SQL
    where = ["o.is_defence = TRUE", api.SCOPE_SQL[scope]]
    params: list[Any] = []

    if status == "open":
        where.append(f"{eff} = 'open'")
    elif status == "closed":
        where.append(f"{eff} <> 'open'")

    text = (q or "").replace("\x00", "").strip()
    if text:
        like = _like(text)
        where.append("(o.title_en ILIKE %s OR o.title_original ILIKE %s "
                     "OR o.buyer_name_raw ILIKE %s OR o.native_id ILIKE %s)")
        params += [like] * 4
    countries = _split(country, "country", upper=True, max_length=2)
    if countries:
        where.append("o.country = ANY(%s)")
        params.append(countries)
    prefixes = _split(cpv, "cpv", max_length=api.MAX_PREFIX_LENGTH)
    if prefixes:
        clauses = []
        for p in prefixes:
            clauses.append("EXISTS (SELECT 1 FROM unnest(o.cpv_codes) c WHERE c LIKE %s)")
            params.append(f"{p}%")
        where.append("(" + " OR ".join(clauses) + ")")
    if buyer is not None:
        where.append("o.buyer_org_id = %s")
        params.append(buyer)
    if from_:
        where.append("o.deadline_at >= %s")
        params.append(datetime.combine(from_, time(0, 0), tzinfo=timezone.utc))
    if to:
        where.append("o.deadline_at < %s::date + 1")
        params.append(to)
    if min_ is not None or max_ is not None:
        where.append("o.value_currency = %s AND o.value_amount IS NOT NULL")
        params.append(currency.upper())
        if min_ is not None:
            where.append("o.value_amount >= %s")
            params.append(min_)
        if max_ is not None:
            where.append("o.value_amount <= %s")
            params.append(max_)

    # A national notice is shown once: it is dropped when the TED notice it was forwarded
    # as would itself be in this result (same filters), so a filter that keeps the national
    # row and not its TED twin never makes the notice vanish. Only rows that carry a TED
    # reference are tested, and that column is rare and indexed.
    twin_where = [re.sub(r"\bo\.", "t.", clause) for clause in where]
    # Written as a plain NOT EXISTS on (source, number) so the planner makes it an
    # anti-join and can still scan in parallel: with the `ted_ref IS NOT NULL AND` guard
    # and a join to `source` it was a restricted subplan and cost 0.7 s a page. A row
    # with no ted_ref matches nothing, so it is kept, as it should be.
    not_collapsed = ("NOT EXISTS (SELECT 1 FROM opportunity t "
                     "WHERE t.source_id = (SELECT id FROM source WHERE code = 'ted') "
                     "AND t.native_id = o.ted_ref AND " + " AND ".join(twin_where) + ")")
    clause = " WHERE " + " AND ".join(where) + " AND " + not_collapsed
    args = params + params

    if sort == "published-desc":
        order = "o.published_at DESC NULLS LAST, o.id DESC"
    else:
        order = f"({eff} <> 'open') ASC, o.deadline_at IS NULL, o.deadline_at ASC, o.id"
    # The total rides on the same pass (a window count), so the table is read once.
    rows = conn.execute(
        f"{TENDER_SELECT.replace(TENDER_COLUMNS, TENDER_COLUMNS + ', count(*) OVER () AS total_rows', 1)}"
        f"{clause} ORDER BY {order} LIMIT %s OFFSET %s",
        args + [pageSize, (page - 1) * pageSize]).fetchall()
    if rows:
        total = rows[0]["total_rows"]
    elif page == 1:
        total = 0
    else:                       # a page past the end still reports how many there are
        total = conn.execute(
            f"SELECT count(*) AS n FROM opportunity o{clause}", args).fetchone()["n"]
    return {"items": _present(conn, rows), "total": total, "page": page, "pageSize": pageSize}


@router.get("/v1/tenders/slugs")
def tender_slugs(conn=Depends(get_conn)):
    api = _api()
    since = datetime.now(timezone.utc) - timedelta(days=SLUG_WINDOW_DAYS)
    rows = conn.execute(
        f"""SELECT o.id, COALESCE(o.title_en, o.title_original) AS title,
                   (SELECT max(v.observed_at) FROM opportunity_version v
                     WHERE v.opportunity_id = o.id) AS updated
              FROM opportunity o
             WHERE o.is_defence AND {api.SCOPE_SQL['core']}
               AND ({api.EFFECTIVE_STATUS_SQL} = 'open' OR o.published_at >= %s)
             ORDER BY o.published_at DESC NULLS LAST, o.id DESC
             LIMIT {TENDER_SLUG_LIMIT}""", (since.date(),)).fetchall()
    return [{"slug": make_slug(r["id"], redact_emails(r["title"]) or ""),
             "updatedAt": r["updated"] or datetime.now(timezone.utc)} for r in rows]


def _id_of(slug: str, what: str) -> int:
    m = SLUG_RE.match(slug)
    if not m or int(m.group(1)) > MAX_BIGINT:
        raise HTTPException(404, f"no such {what}")
    return int(m.group(1))


@router.get("/v1/tenders/{slug}", response_model=Tender)
def get_tender(slug: str, conn=Depends(get_conn)):
    tender_id = _id_of(slug, "tender")
    row = conn.execute(f"{TENDER_SELECT} WHERE o.id = %s AND o.is_defence", (tender_id,)).fetchone()
    if not row:
        raise HTTPException(404, "no such tender")
    return _present(conn, [row])[0]


# What the timeline may say about a changed field. An allow-list with a label each:
# a field added to the record later is not shown until someone decides it should be.
FIELD_LABELS = {
    "status": "Status", "deadline_at": "Deadline", "published_at": "Published",
    "cpv_codes": "CPV codes", "value_amount": "Estimated value", "value_currency": "Currency",
    "title_original": "Title", "title_en": "Title (English)", "buyer_name_raw": "Buyer",
    "legal_basis": "Legal basis", "procedure_type": "Procedure", "country": "Country",
    "source_url": "Source link",
}


def _utc_text(text: str) -> str | None:
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _show(field: str, value: Any) -> str | None:
    if value in (None, "", []):
        return None
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)                      # 1000000.0 and 1000000 read the same
    text = str(value)
    if field == "deadline_at" and len(text) > 10:
        # Stored with the source's own offset (86 of 89 deadline changes carry +01 or
        # +02); printed as UTC it has to be converted, not relabelled.
        text = _utc_text(text) or text
    return redact_emails(text)[:300]


# The versions a reader should not see as amendments, and what they leave behind.
# `reread` and `out_of_order` recorded content that was not a state of the notice, so
# they are skipped without moving the baseline. `remapped` is a real state (a corrected
# reading of the same payload) that nobody amended: not listed, but it is the baseline
# the next change is measured from.
SKIPPED_KINDS = {"reread", "out_of_order"}
REMAPPED_KIND = "remapped"

# Only the allow-listed fields of each payload: the description and the rest are never
# needed to draw a timeline, and a notice with sixty versions carries sixty copies.
PAYLOAD_SUBSET = "jsonb_build_object(" + ", ".join(
    f"'{k}', v.payload->'{k}'" for k in FIELD_LABELS) + ")"
TIMELINE_SQL = """
    SELECT v.opportunity_id, v.version, v.observed_at, v.changed_fields,
           """ + PAYLOAD_SUBSET + """ AS payload,
           COALESCE((SELECT array_agg(n.kind) FROM opportunity_version_note n
                      WHERE n.opportunity_version_id = v.id), '{{}}') AS kinds
      FROM opportunity_version v
     WHERE {where}
     ORDER BY v.opportunity_id, v.version"""


def timeline(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The amendments of one notice, oldest first, from its version rows in order.

    The first version is the notice as first seen. A later version is listed only if it
    changed something a reader can see, and the archive being append-only, the noise
    is filtered here and not there:

      - a line whose two sides render the same is dropped (66 on 12 October 2026: CPV
        re-ordered, the same deadline written with another UTC offset)
      - a version left with no line, or only the publication date, is not an amendment:
        1,292 of 1,693 were the PLACSP feed stamp moving
    """
    out: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for r in rows:
        kinds = set(r.get("kinds") or [])
        if kinds & SKIPPED_KINDS:
            continue
        payload = r["payload"] or {}
        if previous is None:
            out.append({"version": r["version"], "detectedAt": r["observed_at"], "changes": []})
        elif REMAPPED_KIND not in kinds:
            changes = []
            for field in r["changed_fields"] or []:
                if field not in FIELD_LABELS:
                    continue
                before, after = previous.get(field), payload.get(field)
                if same_value(field, before, after):
                    continue
                shown_before, shown_after = _show(field, before), _show(field, after)
                if shown_before == shown_after:
                    continue
                changes.append({"field": field, "label": FIELD_LABELS[field],
                                "before": shown_before, "after": shown_after})
            if any(c["field"] != "published_at" for c in changes):
                out.append({"version": r["version"], "detectedAt": r["observed_at"],
                            "changes": changes})
        previous = payload
    return out


@router.get("/v1/tenders/{slug}/versions", response_model=list[TenderVersion])
def tender_versions(slug: str, conn=Depends(get_conn)):
    tender_id = _id_of(slug, "tender")
    if not conn.execute("SELECT 1 FROM opportunity WHERE id = %s AND is_defence",
                        (tender_id,)).fetchone():
        raise HTTPException(404, "no such tender")
    rows = conn.execute(TIMELINE_SQL.format(where="v.opportunity_id = %s"),
                        (tender_id,)).fetchall()
    return list(reversed(timeline(rows)))


# ----------------------------------------------------------------- buyers

AGGREGATE = f"""
    SELECT o.buyer_org_id AS org_id, count(*) AS n,
           count(*) FILTER (WHERE {{eff}} = 'open') AS open_n,
           max(o.published_at) AS last_published
      FROM opportunity o
     WHERE o.is_defence AND {CORE} AND o.buyer_org_id IS NOT NULL
     GROUP BY o.buyer_org_id
"""


def _buyer(r: dict[str, Any], names: dict[int, str]) -> dict[str, Any]:
    name = names.get(r["id"]) or redact_emails(r["canonical_name"])
    return {
        "id": str(r["id"]), "slug": make_slug(r["id"], name), "name": name,
        "country": (r.get("country") or None),
        "tenderCount": r["n"], "openCount": r["open_n"],
        "lastPublishedAt": _day(r.get("last_published")),
        "isDefenceBuyer": bool(r.get("is_defence_buyer")),
    }


@router.get("/v1/buyers", response_model=BuyerPage)
def list_buyers(
    q: str | None = Query(None, max_length=100),
    country: str | None = Query(None, max_length=200),
    hasOpen: bool = False,
    sort: str = Query("tenders", pattern="^(tenders|name)$"),
    page: int = Query(1, ge=1, le=1000),
    pageSize: int = Query(20, ge=1, le=100),
    conn=Depends(get_conn),
):
    agg = AGGREGATE.format(eff=_api().EFFECTIVE_STATUS_SQL)
    where: list[str] = []
    params: list[Any] = []
    text = (q or "").replace("\x00", "").strip()
    if text:
        # The normalised name (accents folded, lower case): the 281,000 aliases are
        # not searched, which made a name search take seconds.
        where.append("org.canonical_name ILIKE %s")
        params.append(_like(text))
    countries = _split(country, "country", upper=True, max_length=2)
    if countries:
        where.append("org.country = ANY(%s)")
        params.append(countries)
    if hasOpen:
        where.append("a.open_n > 0")
    base = ("FROM organisation org JOIN (" + agg + ") a ON a.org_id = org.id"
            + ((" WHERE " + " AND ".join(where)) if where else ""))
    order = "org.canonical_name, org.id" if sort == "name" else "a.n DESC, org.id"
    rows = conn.execute(
        f"""SELECT org.id, org.canonical_name, org.country, org.is_defence_buyer,
                   a.n, a.open_n, a.last_published, count(*) OVER () AS total_rows {base}
             ORDER BY {order} LIMIT %s OFFSET %s""",
        params + [pageSize, (page - 1) * pageSize]).fetchall()
    if rows:
        total = rows[0]["total_rows"]
    elif page == 1:
        total = 0
    else:
        total = conn.execute(f"SELECT count(*) AS n {base}", params).fetchone()["n"]
    names = _buyer_names(conn, [r["id"] for r in rows])
    return {"items": [_buyer(r, names) for r in rows], "total": total,
            "page": page, "pageSize": pageSize}


@router.get("/v1/buyers/slugs")
def buyer_slugs(conn=Depends(get_conn)):
    agg = AGGREGATE.format(eff=_api().EFFECTIVE_STATUS_SQL)
    rows = conn.execute(
        f"""SELECT org.id, org.canonical_name, a.last_published
              FROM organisation org JOIN ({agg}) a ON a.org_id = org.id
             WHERE a.open_n > 0
             ORDER BY a.open_n DESC, org.id LIMIT {BUYER_SLUG_LIMIT}""").fetchall()
    names = _buyer_names(conn, [r["id"] for r in rows])
    return [{"slug": make_slug(r["id"], names.get(r["id"]) or r["canonical_name"]),
             "updatedAt": _day(r["last_published"]) or datetime.now(timezone.utc)} for r in rows]


@router.get("/v1/buyers/{slug}", response_model=Buyer)
def get_buyer(slug: str, conn=Depends(get_conn)):
    org_id = _id_of(slug, "buyer")
    agg = AGGREGATE.format(eff=_api().EFFECTIVE_STATUS_SQL)
    row = conn.execute(
        f"""SELECT org.id, org.canonical_name, org.country, org.is_defence_buyer,
                   a.n, a.open_n, a.last_published
              FROM organisation org JOIN ({agg}) a ON a.org_id = org.id
             WHERE org.id = %s""", (org_id,)).fetchone()
    if not row:
        raise HTTPException(404, "no such buyer")
    return _buyer(row, _buyer_names(conn, [org_id]))
