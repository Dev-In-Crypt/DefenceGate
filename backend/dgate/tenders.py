"""Tenders and buyers: the shape docs/design/API_CONTRACT.md fixes for the site.

The sibling of `funding.py` for procurement notices (`opportunity`) and the bodies
that publish them (`organisation`). `/v1/opportunities` stays as it is: that is the
data model's own view, this is the page's.

Decisions that shape it:

  - a notice is `open` as of now: a passed deadline, or no deadline and a publication
    date over a year old, is `closed` (the stored status is the one it was published
    with, which a source rarely corrects)
  - a national notice whose TED twin is in the same result is shown once; so is a
    BOAMP parent whose rectificatif is in the same result, and a TED procedure's
    re-publications (the newest that matches the filters wins; the rectificatif never
    hides). The buyer aggregate: `tenderCount` counts every core notice of the buyer,
    collapsed or not; `openCount` applies the list's own collapse and status rule
    (`collapse_clauses`), so it equals what `/v1/tenders?buyer=` lists as open
  - amounts are never converted; a value range selects one currency
  - a notice with no deadline of its own is not served open when its procedure is over
    (its TED twin's deadline has passed, an award follows it, a rectificatif replaces
    it: `api.SUPERSEDED_SQL`); `deadlineKnown` says whether the deadline is stated at all
  - a national notice that states no value borrows the value of its TED twin at read
    time, and says so (`valueFrom: "ted_twin"`); the stored row is never changed
  - the same for the procedure (`procedureFrom`), and for a deadline that differs from its
    TED twin's by more than 90 days (`deadlineFrom`: a typo in the national source, 6 of 211
    Spanish twin pairs more than a year apart); nothing is invented, the twin's own is shown
  - a tender names its buyer the way the notice itself does (`buyerName`); the buyers
    catalogue, and `buyerCanonicalName` beside it, use the organisation's commonest
    spelling rather than the normalised key the entity resolver uses
  - versions the archive annotated as `reread`, `out_of_order` or `remapped` are not
    amendments and are neither counted nor listed; neither is a version that moved only
    the publication date (the PLACSP feed stamp: 76% of the amendments on 12 October
    2026), nor one whose changes read the same before and after
"""

from __future__ import annotations

import ast
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .classify import classify, military_cpv_codes
from .db import same_value
from .funding import (
    Budget,
    ListMeta,
    SourceAttribution,
    _like,
    anomalies,
    get_conn,
    make_slug,
    serves_meta,
)
from .listcache import cache_list
from .normalise import http_url, redact_emails

router = APIRouter()

SLUG_RE = re.compile(r"^([0-9]{1,9})(?:-|$)", re.ASCII)
MAX_BIGINT = 9_223_372_036_854_775_807
# A value of 1 or less is how a notice says "not known" (0.01, 1.00, 0, -1: 5,771 TED rows
# on 13 October 2026), never a price. It is not shown, not borrowed from, and not matched
# by a value range.
PLACEHOLDER_VALUE_MAX = 1
# A national deadline this far from its TED twin's is read as a typo in the national source
# (data-correctness DC2/DC8, 14 October 2026), and the twin's is shown with its provenance.
TWIN_DEADLINE_DIFFERS_DAYS = 90
# A tender deadline further ahead than this is flagged (`deadline-more-than-1y`): 8.3 % of
# the open set on 14 October 2026, most of it a typo in the source. Calls keep the 3-year
# rule of `funding.anomalies`: a grant's cut-offs are legitimately far ahead.
TENDER_DEADLINE_HORIZON_DAYS = 365
# Each page of the list evaluates the whole filtered set once (the total rides on it), so a
# 2,000-row export in pages of 100 was 20 passes over up to 200,000 notices; 250 makes it 8.
MAX_PAGE_SIZE = 250
MAX_LIST_ITEMS = 20
SLUG_WINDOW_DAYS = 365
TENDER_SLUG_LIMIT = 5000
BUYER_SLUG_LIMIT = 2000

# A version the archive recorded wrongly is annotated, never removed (migration 0006).
# `remapped` (migration 0028): appended by a bulk re-derivation from the same source
# payload; the publisher amended nothing.
NOT_AN_AMENDMENT = "('reread', 'out_of_order', 'remapped')"

CORE = "(o.sig_legal_basis OR (o.sig_cpv_military AND NOT o.dual_use))"   # api.CORE_SQL


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
    # `ted_twin` when `procedure` is the TED notice's: the national notice states none.
    procedureFrom: str | None = None
    legalBasis: str | None
    scope: str
    buyerClass: str | None = None
    dualUse: bool = False
    # What qualified the notice, from the stored signals: `legal_basis` (2009/81/EC),
    # `military_cpv` (a military product code; `militaryCpv` lists the codes that are),
    # `buyer` (only its buyer's being on the defence list keeps it: without the buyer it
    # would be demoted as dual-use). A page says "military product code" only for the second.
    qualifiedBy: list[str] = []
    militaryCpv: list[str] = []
    deadline: datetime | None
    # `ted_twin` when `deadline` is the TED notice's because the national notice's own is
    # more than 90 days from it (a typo in the national source); null: the notice's own.
    deadlineFrom: str | None = None
    # False when the notice states no deadline: `status` is then a judgement (see
    # `api.SUPERSEDED_SQL`, `api.OPEN_WITHOUT_DEADLINE_DAYS`) and the site says "deadline
    # not stated" rather than showing nothing.
    deadlineKnown: bool = True
    publishedAt: datetime | None
    # False when the source states no publication date (a PLACSP entry that carries only
    # award notices): the row is listed all the same, and the site says "not stated".
    publishedKnown: bool = True
    # When the notice was first collected (the observed time of its first version).
    firstSeenAt: datetime | None = None
    estimatedValue: Budget | None
    # `ted_twin` when `estimatedValue` is the value of the TED notice this one is the same
    # procurement as and the notice itself states none; null when it is the notice's own.
    # `valueKind` then describes the twin's figure.
    valueFrom: str | None = None
    lots: int | None = None
    valueKind: str | None = None
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
    meta: ListMeta = ListMeta()


class FieldChange(BaseModel):
    field: str
    label: str
    before: str | None
    after: str | None


class TenderVersion(BaseModel):
    version: int
    # 1 for the notice as first seen, then one per listed change: the number a reader
    # counts by. `version` is the archive's own row number and has gaps (v11 of 2 listed).
    sequence: int = 0
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
    # A bare number, a one or two character legacy code ("V", "4") and a BZP form code
    # ("BZP 1.1.1") are source codes, not words a reader knows; they stay in the data.
    if not text or text.isdigit() or len(text) <= 2 or re.fullmatch(r"BZP [0-9.]+", text):
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
    "o.sig_cpv, o.sig_cpv_military, o.sig_buyer, o.dual_use, o.buyer_class, "
    "o.security_clearance_required, o.subcontracting_signal, o.source_url, "
    "o.status, o.ted_ref, o.lot_count, o.value_kind, o.notice_subtype"
)

TENDER_SELECT = f"""
    SELECT {TENDER_COLUMNS}, s.code AS source_code, s.name AS source_name,
           s.licence AS source_licence, s.attribution AS source_attribution
      FROM opportunity o
      JOIN source s ON s.id = o.source_id
"""


_SOURCE_SUFFIX = re.compile(r"(?<=[^\W\d_])_\d{1,6}$")


def clean_buyer_name(name: str | None) -> str:
    """A buyer name as a person writes it: the Irish eTenders buyer id that TED carries
    after the name ("Irish Defence Forces_1144", 403 notices) is not part of it. Read side
    only: the stored name stays what the source stated."""
    return _SOURCE_SUFFIX.sub("", redact_emails(name) or "").strip()


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
    return {r["buyer_org_id"]: clean_buyer_name(r["buyer_name_raw"]) for r in rows}


def _observed_span(conn, ids: list[int]) -> dict[int, tuple[datetime, datetime]]:
    """(first, last) time each notice was observed: its oldest and newest version's
    observation time. Read for the page only, never inside the filtered query."""
    if not ids:
        return {}
    rows = conn.execute(
        "SELECT opportunity_id, min(observed_at) AS first, max(observed_at) AS last "
        "FROM opportunity_version WHERE opportunity_id = ANY(%s) GROUP BY opportunity_id",
        (ids,)).fetchall()
    return {r["opportunity_id"]: (r["first"], r["last"]) for r in rows}


def _observed(conn, ids: list[int]) -> dict[int, datetime]:
    """When each notice was last observed: its newest version's observation time."""
    return {i: last for i, (_, last) in _observed_span(conn, ids).items()}


def _version_info(conn, ids: list[int]) -> dict[int, tuple[int, datetime | None]]:
    """For each notice: how many real versions it has (the first, and each later one that
    changed something a reader can see: see `timeline`) and when the newest of them was
    observed. A bulk re-reading of the same payload (`remapped`, `reread`) is neither:
    "last changed" is when the SOURCE changed the notice, as we saw it, not when we
    reprocessed it (253 of 291 open TED notices said 12 October 17:0x)."""
    if not ids:
        return {}
    rows = conn.execute(TIMELINE_SQL.format(where="v.opportunity_id = ANY(%s)"),
                        (ids,)).fetchall()
    by_notice: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        by_notice.setdefault(r["opportunity_id"], []).append(r)
    out = {}
    for oid, group in by_notice.items():
        entries = timeline(group)
        out[oid] = (len(entries), entries[-1]["detectedAt"] if entries else None)
    return out


def _version_counts(conn, ids: list[int]) -> dict[int, int]:
    return {oid: n for oid, (n, _) in _version_info(conn, ids).items()}


def _source_runs(conn) -> dict[str, datetime]:
    """When each source's newest successful or partial collection run finished: what
    "we last looked at this source" means (`ingest_run` is a few hundred rows)."""
    from .config import settings
    from .stats import LAST_RUN_SECONDS, cached  # stats imports this module

    def read() -> dict[str, datetime] | None:
        got = conn.execute(
            """SELECT s.code, max(r.finished_at) AS t
                 FROM ingest_run r JOIN source s ON s.id = r.source_id
                WHERE r.status IN ('success', 'partial') AND r.finished_at IS NOT NULL
                GROUP BY s.code""").fetchall()
        return {r["code"]: r["t"] for r in got} or None      # None is never kept
    # The list cache's own switch (0 in the test suite) turns this one off too.
    ttl = 0 if settings().list_cache_seconds <= 0 else LAST_RUN_SECONDS
    return cached(("source-runs",), read, ttl) or {}


def _qualified_by(r: dict[str, Any], cpv: list[str]) -> tuple[list[str], list[str]]:
    """(signals that qualified the notice, the military codes among its CPV codes). A
    military code that is one of many on a civil buyer's notice was counted because the
    buyer is on the defence list when, without the buyer, the notice would be demoted as
    dual-use: that is `buyer`, never "military product code"."""
    out: list[str] = []
    if r.get("sig_legal_basis"):
        out.append("legal_basis")
    codes = military_cpv_codes(cpv) if r.get("sig_cpv_military") else []
    if codes:
        without_buyer = classify(legal_basis=r.get("legal_basis"), cpv_codes=cpv,
                                 buyer_is_defence=False, buyer_class=r.get("buyer_class"))
        if r.get("sig_buyer") and not r.get("sig_legal_basis") and without_buyer.dual_use:
            out.append("buyer")
            codes = []
        else:
            out.append("military_cpv")
    elif r.get("sig_buyer"):
        out.append("buyer")
    return out, codes


def to_tender(r: dict[str, Any], names: dict[int, str], versions: dict[int, int],
              twins: list[dict[str, Any]], observed: datetime | None, *,
              superseded: bool = False, twin_value: dict[str, Any] | None = None,
              first_seen: datetime | None = None,
              twin_extra: dict[str, Any] | None = None,
              checked: datetime | None = None) -> dict[str, Any]:
    api = _api()
    title_en = redact_emails(r.get("title_en"))
    original = redact_emails(r["title_original"])
    heading = title_en or original
    other = original if title_en and original and original.strip() != title_en.strip() else None
    procedure, procedure_from = procedure_label(r.get("procedure_type")), None
    deadline, deadline_from = r.get("deadline_at"), None
    extra = twin_extra or {}
    if procedure is None and extra.get("procedure"):
        procedure = procedure_label(extra["procedure"])
        procedure_from = "ted_twin" if procedure else None
    if (deadline is not None and extra.get("deadline") is not None
            and abs(deadline - extra["deadline"]) > timedelta(days=TWIN_DEADLINE_DIFFERS_DAYS)):
        deadline, deadline_from = extra["deadline"], "ted_twin"
    eff = api.effective_status(r.get("status"), deadline, r.get("published_at"),
                               superseded=superseded)
    notes = anomalies(deadline, r.get("published_at"))
    if deadline_from:
        notes.append("deadline-differs-from-ted-twin")
    if (deadline is not None and "deadline-more-than-3y" not in notes and deadline
            > datetime.now(timezone.utc) + timedelta(days=TENDER_DEADLINE_HORIZON_DAYS)):
        notes.append("deadline-more-than-1y")
    org_id = r.get("buyer_org_id")
    # The notice's own spelling is what the notice says; the organisation's commonest
    # spelling is what the organisation is called. 15,937 TED rows were being shown
    # under the second, which merges a sub-unit into its parent.
    own_name = clean_buyer_name(r["buyer_name_raw"])
    org_name = names.get(org_id) or own_name
    buyer_name = own_name or org_name
    n_versions = versions.get(r["id"], 1) or 1
    cpv = r.get("cpv_codes") or []
    qualified, military = _qualified_by(r, cpv)
    amount = r.get("value_amount")
    value_from, value_kind = None, r.get("value_kind")
    currency = r.get("value_currency")
    if not amount or amount <= PLACEHOLDER_VALUE_MAX:
        amount, value_kind = None, None
        if twin_value:                      # the notice's own value always wins
            amount, currency = twin_value["amount"], twin_value["currency"]
            value_from, value_kind = "ted_twin", twin_value["kind"]
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
        "procedure": procedure,
        "procedureFrom": procedure_from,
        "legalBasis": r.get("legal_basis"),
        "scope": api.row_scope(r),
        "buyerClass": r.get("buyer_class"),
        "dualUse": bool(r.get("dual_use")),
        "qualifiedBy": qualified,
        "militaryCpv": military,
        "deadline": deadline,
        "deadlineFrom": deadline_from,
        "deadlineKnown": deadline is not None,
        "publishedAt": _day(r.get("published_at")),
        "publishedKnown": r.get("published_at") is not None,
        # When we first saw the notice. "New since" compares this, never `publishedAt`: a
        # publication date is a day, and 55 % of TED notices are collected a day or more
        # after it (internal audit H3, 14 October 2026).
        "firstSeenAt": first_seen,
        "estimatedValue": ({"amount": float(amount), "currency": currency or "EUR"}
                           if amount else None),
        "valueFrom": value_from,
        "lots": r.get("lot_count"),
        "valueKind": value_kind,
        "anomalies": notes,
        "status": "open" if eff == "open" else "closed",
        "statusNative": eff,
        "amended": n_versions > 1,
        "versionCount": n_versions,
        "securityClearance": bool(r.get("security_clearance_required")),
        "subcontracting": bool(r.get("subcontracting_signal")),
        "sameNotice": [{"source": t["source"], "url": t.get("url"), "id": str(t["id"]),
                        "noticeId": t["native_id"]} for t in twins],
        "source": {
            "sourceId": r["source_code"],
            "sourceName": r["source_name"],
            "url": http_url(r.get("source_url")),
            "retrievedAt": observed or datetime.now(timezone.utc),
            "checkedAt": checked,
            "licence": r["source_licence"] or "",
            "attribution": api._attribution(r),
        },
    }


def _superseded(conn, rows: list[dict[str, Any]]) -> set[int]:
    """Of a page's stored-open notices that state no deadline, the ones whose procedure is
    over (`api.SUPERSEDED_SQL`): what the list's own status filter already knows in SQL."""
    ids = [r["id"] for r in rows if r.get("status") == "open" and r.get("deadline_at") is None]
    if not ids:
        return set()
    got = conn.execute(
        f"SELECT o.id FROM opportunity o WHERE o.id = ANY(%s) AND {_api().SUPERSEDED_SQL}",
        (ids,)).fetchall()
    return {r["id"] for r in got}


def _twin_values(conn, rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """For a page's notices that state no value but name a TED twin, the twin's value.

    Only where the figure says the same thing about the same procurement:
      - not `first_lot` (the first of several lots: one part, not the notice)
      - not a placeholder (`PLACEHOLDER_VALUE_MAX`) and with its currency
      - a link made by procedure identifier or by the heuristic ties the row to the newest
        TED notice of the procedure, which may be another stage of it: the twin must then
        have the row's own status (the rule `list_tenders` collapses by), or the value of
        a call would be shown on its award
    A stated TED number is the same notice and needs no such check."""
    ids = [r["id"] for r in rows
           if r.get("ted_ref") and not (r.get("value_amount")
                                        and r["value_amount"] > PLACEHOLDER_VALUE_MAX)]
    if not ids:
        return {}
    got = conn.execute(
        """SELECT o.id AS row_id, t.value_amount, t.value_currency, t.value_kind
             FROM opportunity o
             JOIN opportunity t ON t.source_id = (SELECT id FROM source WHERE code = 'ted')
                               AND t.native_id = o.ted_ref
            WHERE o.id = ANY(%s) AND t.value_amount > %s AND t.value_currency IS NOT NULL
              AND t.value_kind IS DISTINCT FROM 'first_lot'
              AND (coalesce(o.twin_method, '') NOT IN ('procedure_id', 'heuristic')
                   OR t.status = o.status)""", (ids, PLACEHOLDER_VALUE_MAX)).fetchall()
    return {r["row_id"]: {"amount": r["value_amount"], "currency": r["value_currency"],
                          "kind": r["value_kind"]} for r in got}


def _twin_extras(conn, rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """For a page's notices that name a TED twin: the twin's procedure and deadline, to be
    shown where the notice states no procedure, or a deadline 90 days from it. The same twin
    rule as `_twin_values` (a link made by procedure identifier or by the heuristic ties the
    row to the newest TED notice of the procedure, which may be another stage of it)."""
    ids = [r["id"] for r in rows if r.get("ted_ref")]
    if not ids:
        return {}
    got = conn.execute(
        """SELECT o.id AS row_id, t.procedure_type, t.deadline_at
             FROM opportunity o
             JOIN opportunity t ON t.source_id = (SELECT id FROM source WHERE code = 'ted')
                               AND t.native_id = o.ted_ref
            WHERE o.id = ANY(%s)
              AND (coalesce(o.twin_method, '') NOT IN ('procedure_id', 'heuristic')
                   OR t.status = o.status)""", (ids,)).fetchall()
    return {r["row_id"]: {"procedure": r["procedure_type"], "deadline": r["deadline_at"]}
            for r in got}


def _present(conn, rows: list[dict[str, Any]], *, checked: bool = False) -> list[dict[str, Any]]:
    """`checked`: also say when each notice's source was last collected (`source.checkedAt`).
    Only the API's own endpoints ask: the account role reads no run table."""
    ids = [r["id"] for r in rows]
    names = _buyer_names(conn, sorted({r["buyer_org_id"] for r in rows if r.get("buyer_org_id")}))
    info = _version_info(conn, ids)
    versions = {i: n for i, (n, _) in info.items()}
    twins = _api()._twins(conn, ids)
    span = _observed_span(conn, ids)
    over = _superseded(conn, rows)
    borrowed = _twin_values(conn, rows)
    extras = _twin_extras(conn, rows)
    runs = _source_runs(conn) if checked else {}
    return [to_tender(r, names, versions, twins.get(r["id"], []),
                      info.get(r["id"], (0, None))[1] or span.get(r["id"], (None, None))[1],
                      superseded=r["id"] in over, twin_value=borrowed.get(r["id"]),
                      first_seen=span.get(r["id"], (None, None))[0],
                      twin_extra=extras.get(r["id"]),
                      checked=runs.get(r["source_code"]))
            for r in rows]


def collapse_clauses(where: list[str], *, same_buyer: bool = False) -> str:
    """The three rules that show a notice once, as one SQL condition over `opportunity o`:
    the filters (`where`, written over `o`) are applied to the notice that would replace
    this one as well, so a filter that keeps a notice and not its twin never makes it vanish.
    `same_buyer` is for an aggregate over every buyer at once: the replacing notice must be
    the same buyer's, which is what `buyer = X` in `where` says for the list. The condition
    carries no parameters of its own: each `%s` of `where` appears once per rule."""
    def extra(alias: str) -> list[str]:
        return [f"{alias}.buyer_org_id = o.buyer_org_id"] if same_buyer else []

    # A national notice is shown once: it is dropped when the TED notice it was forwarded
    # as would itself be in this result (same filters), so a filter that keeps the national
    # row and not its TED twin never makes the notice vanish. Only rows that carry a TED
    # reference are tested, and that column is rare and indexed.
    twin_where = [re.sub(r"\bo\.", "t.", clause) for clause in where] + extra("t")
    # Written as a plain NOT EXISTS on (source, number) so the planner makes it an
    # anti-join and can still scan in parallel: with the `ted_ref IS NOT NULL AND` guard
    # and a join to `source` it was a restricted subplan and cost 0.7 s a page. A row
    # with no ted_ref matches nothing, so it is kept, as it should be.
    # A link made by procedure identifier or by the heuristic ties a row to the newest TED
    # notice of the procedure, which may be another stage of it (an award under the call
    # for competition): there the TED row has to have the row's own status as well, or
    # the award would be hidden beneath an expired call. A stated reference keeps its rule.
    not_collapsed = ("NOT EXISTS (SELECT 1 FROM opportunity t "
                     "WHERE t.source_id = (SELECT id FROM source WHERE code = 'ted') "
                     "AND t.native_id = o.ted_ref "
                     "AND (coalesce(o.twin_method, '') NOT IN ('procedure_id', 'heuristic') "
                     "OR t.status = o.status) AND " + " AND ".join(twin_where) + ")")
    # A BOAMP rectificatif repeats its parent notice, and the newest wins like a
    # re-publication: the parent is dropped when a rectificatif of it that matches these
    # same filters is in the result; the rectificatif is never dropped. A parent whose
    # correction is filtered out (expired while the parent is open, another status) is
    # listed itself, so the notice never vanishes. (`related_native_id` is null for every
    # other row: no match.)
    rect_where = [re.sub(r"\bo\.", "c.", clause_) for clause_ in where] + extra("c")
    not_rectified = ("NOT EXISTS (SELECT 1 FROM opportunity c "
                     "WHERE o.related_native_id IS NULL AND c.related_native_id IS NOT NULL "
                     "AND c.source_id = o.source_id "
                     "AND c.related_native_id = o.native_id AND c.id <> o.id AND "
                     + " AND ".join(rect_where) + ")")
    # A TED re-publication or corrigendum carries a new publication number but the same
    # procedure identifier: only the newest of the same status that matches these filters
    # is shown. (Award notices of a procedure have another status, so they are not hidden
    # by the call for competition, and the reverse.)
    rep_where = [re.sub(r"\bo\.", "r.", clause_) for clause_ in where] + extra("r")
    not_republished = ("NOT EXISTS (SELECT 1 FROM opportunity r "
                       "WHERE o.procedure_identifier IS NOT NULL "
                       "AND r.procedure_identifier = o.procedure_identifier "
                       "AND r.source_id = o.source_id AND r.status = o.status AND r.id <> o.id "
                       "AND (coalesce(r.published_at, 'epoch'::date), r.id) "
                       "> (coalesce(o.published_at, 'epoch'::date), o.id) AND "
                       + " AND ".join(rep_where) + ")")
    return " AND ".join((not_collapsed, not_rectified, not_republished))


# -------------------------------------------------------------- endpoints

def tender_order(sort: str | None, status: str, eff: str) -> str:
    """The ORDER BY of a tenders list. With no sort asked for, open and all notices run
    soonest deadline first (open ones before the rest); closed ones run the other way,
    newest deadline first, then newest publication: the soonest of a closed list is a
    notice from years ago. A sort that was asked for is always honoured."""
    if sort == "published-desc":
        return "o.published_at DESC NULLS LAST, o.id DESC"
    if sort == "deadline-desc" or (sort is None and status == "closed"):
        return "o.deadline_at DESC NULLS LAST, o.published_at DESC NULLS LAST, o.id DESC"
    return f"({eff} <> 'open') ASC, o.deadline_at IS NULL, o.deadline_at ASC, o.id"


@router.get("/v1/tenders", response_model=TenderPage)
@cache_list("tenders")
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
    sort: str | None = Query(None, pattern="^(deadline-asc|deadline-desc|published-desc)$"),
    page: int = Query(1, ge=1, le=1000),
    pageSize: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    conn=Depends(get_conn),
    with_meta=Depends(serves_meta),
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
        # The whole of the day in UTC, as `from` is read: `%s::date + 1` was compared with
        # a timestamptz in the session's time zone, so the bound moved with the server.
        where.append("o.deadline_at <= %s")
        params.append(datetime.combine(to, time.max, tzinfo=timezone.utc))
    if min_ is not None or max_ is not None:
        # A placeholder (0, 0.01, 1) is "not stated" and must not match "up to EUR 100,000".
        where.append("o.value_currency = %s AND o.value_amount > %s")
        params += [currency.upper(), PLACEHOLDER_VALUE_MAX]
        if min_ is not None:
            where.append("o.value_amount >= %s")
            params.append(min_)
        if max_ is not None:
            where.append("o.value_amount <= %s")
            params.append(max_)

    clause = (" WHERE " + " AND ".join(where) + " AND " + collapse_clauses(where))
    args = params + params + params + params

    order = tender_order(sort, status, eff)
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
    from .stats import cached_last_run  # stats imports this module

    return {"items": _present(conn, rows, checked=with_meta is True), "total": total,
            "page": page, "pageSize": pageSize,
            "meta": {"updatedAt": cached_last_run(conn, "tender") if with_meta is True else None}}


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
    return _present(conn, [row], checked=True)[0]


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


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

STATUS_WORDS = {
    "open": "Open", "closed": "Closed", "awarded": "Awarded", "cancelled": "Cancelled",
    "canceled": "Cancelled", "forthcoming": "Planned", "planned": "Planned",
    "expired": "Closed", "evaluated": "Under evaluation", "unknown": "Status unknown",
}

LEGAL_BASIS_WORDS = {
    "32009L0081": "Directive 2009/81/EC (defence and security procurement)",
    "32014L0024": "Directive 2014/24/EU (public procurement)",
    "32014L0025": "Directive 2014/25/EU (utilities procurement)",
    "32014L0023": "Directive 2014/23/EU (concessions)",
}


def _day_text(day: date) -> str:
    return f"{day.day} {_MONTHS[day.month - 1]} {day.year}"


def _when(value: Any) -> str | None:
    """A date as "10 Sep 2026", a moment as "10 Sep 2026, 14:05 UTC" (converted, not
    relabelled). A moment at exactly 00:00 UTC is how a source that states only a day
    arrives, so it reads as the day. None when the value is not a date at all."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return _day_text(value)
    elif isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            try:
                return _day_text(date.fromisoformat(text))
            except ValueError:
                return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00").replace(" UTC", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    if parsed.hour == 0 and parsed.minute == 0:
        return _day_text(parsed.date())
    return f"{_day_text(parsed.date())}, {parsed:%H:%M} UTC"


# The longest stored text `_plain` will try to read back as a list or mapping: a CPV list
# or a value object is a few hundred characters; the display is capped at 300 anyway.
PLAIN_MAX_CHARS = 20_000


def _plain(value: Any) -> Any:
    """A value the archive stored as the text of a Python or JSON list or mapping
    ("['35200000', '35810000']") read back as the list or mapping it was."""
    # Capped before it is parsed: a stored string is not ours to trust, and a deeply
    # nested one costs the parser its stack (RecursionError) or the process its memory.
    if (isinstance(value, str) and len(value) <= PLAIN_MAX_CHARS
            and value.strip()[:1] in ("[", "{")):
        for load in (json.loads, ast.literal_eval):
            try:
                return load(value)
            except (ValueError, SyntaxError, RecursionError, MemoryError):
                continue
    return value


def _number_text(amount: Any) -> str | None:
    try:
        number = float(amount)
    except (TypeError, ValueError):
        return None
    return f"{number:,.0f}" if number.is_integer() else f"{number:,.2f}"


def _human(field: str, value: Any, currency: Any = None) -> str | None:
    """What one side of a changed line says, for a person: dates as dates, a status as
    a word, an amount with its currency, a list as a comma list; never the repr of a
    Python or JSON value. `_show` stays the comparison key (it is what the archive
    guards against re-orderings with)."""
    value = _plain(value)
    if value in (None, "", [], {}):
        return None
    if isinstance(value, dict):
        amount, code = _number_text(value.get("amount")), value.get("currency")
        if amount is not None and code:
            return f"{code} {amount}"
        return redact_emails("; ".join(f"{k}: {v}" for k, v in value.items()))[:300]
    if isinstance(value, (list, tuple, set)):
        return redact_emails(", ".join(str(v).strip() for v in value if str(v).strip()))[:300] or None
    if field in ("deadline_at", "published_at"):
        shown = _when(value)
        if shown:
            return shown
    elif field == "status":
        word = str(value).strip().lower()
        return STATUS_WORDS.get(word) or word.replace("_", " ").replace("-", " ").capitalize()
    elif field == "procedure_type":
        return procedure_label(str(value))
    elif field == "value_amount":
        amount = _number_text(value)
        if amount is not None:
            return f"{currency} {amount}" if currency else amount
    elif field == "legal_basis":
        return LEGAL_BASIS_WORDS.get(str(value).strip().upper()) or _show(field, value)
    return _show(field, value)


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
                # An amount is read with the currency of the version it belongs to.
                old_code = previous.get("value_currency") or payload.get("value_currency")
                new_code = payload.get("value_currency") or old_code
                human_before = _human(field, before, old_code)
                human_after = _human(field, after, new_code)
                if human_before == human_after:       # two spellings of one word
                    continue
                changes.append({"field": field, "label": FIELD_LABELS[field],
                                "before": human_before, "after": human_after})
            if any(c["field"] != "published_at" for c in changes):
                out.append({"version": r["version"], "detectedAt": r["observed_at"],
                            "changes": changes})
        previous = payload
    for number, entry in enumerate(out, 1):
        entry["sequence"] = number
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


def aggregate_sql() -> str:
    """The buyer aggregate (`org_id`, `n`, `open_n`, `last_published`) with `open_n` counted
    as the buyer's own list counts it: the same status rule, and the same collapse (a national
    notice and its TED twin, a rectificatif and its parent, a re-publication: one each). 201
    against 169 listed on 14 October 2026. Two aggregates, so that the one over every core
    notice stays free of sub-queries (they hold a scan back from running in parallel) and the
    collapse is tested only on the few hundred notices that are open."""
    eff = _api().EFFECTIVE_STATUS_SQL
    where = ["o.is_defence = TRUE", CORE, f"{eff} = 'open'"]
    return f"""
    SELECT t.org_id, t.n, COALESCE(op.open_n, 0) AS open_n, t.last_published
      FROM (SELECT o.buyer_org_id AS org_id, count(*) AS n, max(o.published_at) AS last_published
              FROM opportunity o
             WHERE o.is_defence AND {CORE} AND o.buyer_org_id IS NOT NULL
             GROUP BY o.buyer_org_id) t
      LEFT JOIN (SELECT o.buyer_org_id AS org_id, count(*) AS open_n
                   FROM opportunity o
                  WHERE {" AND ".join(where)} AND o.buyer_org_id IS NOT NULL
                    AND {collapse_clauses(where, same_buyer=True)}
                  GROUP BY o.buyer_org_id) op ON op.org_id = t.org_id
    """


def _buyer(r: dict[str, Any], names: dict[int, str]) -> dict[str, Any]:
    name = names.get(r["id"]) or clean_buyer_name(r["canonical_name"])
    return {
        "id": str(r["id"]), "slug": make_slug(r["id"], name), "name": name,
        "country": (r.get("country") or None),
        "tenderCount": r["n"], "openCount": r["open_n"],
        "lastPublishedAt": _day(r.get("last_published")),
        "isDefenceBuyer": bool(r.get("is_defence_buyer")),
    }


@router.get("/v1/buyers", response_model=BuyerPage)
@cache_list("buyers", ttl=5 * 60)
def list_buyers(
    q: str | None = Query(None, max_length=100),
    country: str | None = Query(None, max_length=200),
    hasOpen: bool = False,
    sort: str = Query("tenders", pattern="^(tenders|name)$"),
    page: int = Query(1, ge=1, le=1000),
    pageSize: int = Query(20, ge=1, le=100),
    conn=Depends(get_conn),
):
    agg = aggregate_sql()
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
    agg = aggregate_sql()
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
    agg = aggregate_sql()
    row = conn.execute(
        f"""SELECT org.id, org.canonical_name, org.country, org.is_defence_buyer,
                   a.n, a.open_n, a.last_published
              FROM organisation org JOIN ({agg}) a ON a.org_id = org.id
             WHERE org.id = %s""", (org_id,)).fetchone()
    if not row:
        raise HTTPException(404, "no such buyer")
    return _buyer(row, _buyer_names(conn, [org_id]))
