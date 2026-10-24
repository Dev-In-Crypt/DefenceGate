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
    hides). The buyer aggregate: `tenderCount` counts every notice of the default scope of the buyer (WP-96),
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
from collections import defaultdict
from contextvars import ContextVar
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from typing import Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, model_serializer

from . import award_set, cpv_labels
from .classify import (
    CORE_SQL,
    GROUP_CIVIL_DIRECTIVE,
    GROUP_SECURITY_CPV,
    classify,
    military_cpv_codes,
    scope_group_of,
)
from .confidence import CONFIDENCE_SQL, LEVELS, confidence_of_row
from .cpv_labels import codes_for_word, codes_for_words
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
from .search_terms import buyer_names, expand, fold_words
from .suppress import WITHHELD_NAME, removed

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
# WP-87: the anomaly of a notice whose TED twin's (first) deadline has passed while its own, later one has not.
FIRST_DEADLINE_PASSED = "first-deadline-passed"


def shown_deadline(own: datetime | None, twin: datetime | None,
                   now: datetime | None = None) -> tuple[datetime | None, str | None, bool]:
    """(the deadline a notice shows, `deadlineFrom`, whether its TED twin's first deadline has passed).

    A national deadline more than TWIN_DEADLINE_DIFFERS_DAYS from its TED twin's is replaced by the twin's (a typo
    in the national source), except when the twin's has passed and the notice's own is still ahead (WP-87). That is
    a dynamic purchasing system or a framework: TED states the first round's deadline, the national notice the end
    of the system, which takes requests until then. The list's status (`status_conditions`, the notice's own
    deadline) already listed it as open, and the card said "Closed" beside it. Now the card keeps the notice's own
    deadline, stays open and says the first deadline has passed."""
    if own is None or twin is None or abs(own - twin) <= timedelta(days=TWIN_DEADLINE_DIFFERS_DAYS):
        return own, None, False
    now = now or datetime.now(timezone.utc)
    if twin < now <= own:
        return own, None, True
    return twin, "ted_twin", False


def known_params(request: Request) -> None:
    """A dependency that refuses a query parameter the endpoint does not take (422) instead of ignoring it:
    `/v1/changes?cpv=35` answered every change as if the code had been read (WP-87). The answer names the
    parameters the endpoint takes, never the one sent."""
    route = request.scope.get("route")
    if route is None or not hasattr(route, "dependant"):
        return
    names: set[str] = set()
    todo = [route.dependant]
    while todo:                          # the endpoint's own parameters and those of its dependencies
        d = todo.pop()
        names.update(p.alias for p in d.query_params)
        todo.extend(d.dependencies)
    if set(request.query_params) - names:
        raise HTTPException(422, "unknown query parameter; this endpoint takes: " + ", ".join(sorted(names)))
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
# The deepest list position `/v1/tenders` serves (WP-52, T3): 287,634 closed notices were 28,764 pages
# and only the first three could be read before the 5 s budget ran out. A position past it answers with
# no items and says so (`maxOffset`, as `/v1/suppliers` does); narrowing the filters is the way to the rest.
MAX_OFFSET = 10_000
# A count stops here. `total` is then this number and `totalCapped` is true ("10,000 or more"): the
# work of a count is bounded, not the answer made up. A snapshot of the unfiltered views (ops/warm_lists)
# keeps the exact figure, which a deep page of the same filters then repeats.
TOTAL_CAP = 10_000
# The page size of the site's lists: the snapshots are built for it (ops/warm_lists.TENDER_PAGE_SIZE).
SNAPSHOT_PAGE_SIZE = 10

# A version the archive recorded wrongly is annotated, never removed (migration 0006).
# `remapped` (migration 0028): appended by a bulk re-derivation from the same source
# payload; the publisher amended nothing. `history` (migration 0054): written by a command
# that loads the past, so the change is older than the day we saw it.
NOT_AN_AMENDMENT = "('reread', 'out_of_order', 'remapped', 'history')"

CORE = CORE_SQL                         # dgate/classify.py, also api.CORE_SQL


class Confidence(BaseModel):
    level: str
    basis: list[str]
    # WP-95: the level in words, by what it rests on ("Clearly defence", "Defence buyer, ordinary purchase", ...)
    label: str | None = None


class AwardedTo(BaseModel):
    name: str
    slug: str | None                 # the supplier page; null when the winner has none (outside its window)
    country: str | None
    valueAmount: float | None = None # the value given to this winner (a notice naming one winner, a PLACSP lot amount)
    valueCurrency: str | None = None
    valueKind: str | None = None


class AwardValue(BaseModel):
    amount: float
    currency: str
    kind: str                        # contract | framework | estimate (dgate/award_value.py)
    # WP-103: the figure the notice states that its own estimate contradicts (set aside; `kind` is then estimate); left
    # out of the JSON when there is none, so the object is as before for every other notice
    setAside: float | None = None

    @model_serializer(mode="wrap")
    def _without_empty_set_aside(self, handler):
        out = handler(self)
        if out.get("setAside") is None:
            out.pop("setAside", None)
        return out


class ProcedureStage(BaseModel):
    id: str
    slug: str
    noticeId: str
    # the stored status of that notice: `awarded`, `cancelled`, `forthcoming` (a prior information notice), else a call
    status: str | None
    publishedAt: datetime | None


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
    # How sure we are the notice is defence procurement (dgate/confidence.py): `level` is
    # `high`, `medium` or `low`, `basis` the signals behind it in plain words.
    confidence: Confidence | None = None
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
    # The date and kind of the notice this record was last read from (`call`, `prior`,
    # `award`, `formalisation`, `cancellation`, `update`), where the source states them.
    # Never a publication date: a PLACSP folder that holds only its award has
    # `publishedKnown` false and still says "Award notice dated 12 Sep 2026" from these.
    noticeDate: datetime | None = None
    noticeKind: str | None = None
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
    # WP-90, the notice's own page only (`/v1/tenders/{slug}`): the first sentence of the notice's own description,
    # where the source states one and it reads as a commercial subject (`commercial_subject`); null otherwise.
    subject: str | None = None
    # The address of the procurement documents, where a source states it as such: Germany's Bekanntmachungsservice
    # (BT-15, its notices' only link), for the notice itself or its national twin.
    documentsUrl: str | None = None
    # WP-95: the other buyers of a joint procurement, as the notice names them after the first (`buyerName`).
    otherBuyers: list[str] = []
    # WP-95, the notice's own page only: the winners the notice (or its other publication) names that are legal
    # entities, with a link to their supplier page where they have one; natural persons are counted
    # (`awardedPersons`), never named. `awardValue`: what the award states, with its kind (contract, framework,
    # estimate); null where nothing was derived.
    awardedTo: list[AwardedTo] = []
    awardedPersons: int = 0
    awardValue: AwardValue | None = None
    # WP-103: whether the notice (or its other publication) was read for its winners: false, the page says not yet
    winnersRead: bool = False
    # WP-106, the notice's own page only: the other notices of the same procedure (eForms procedure identifier), the call
    # for competition of an award and the award of a call, oldest first (`procedure_stages`).
    stages: list[ProcedureStage] = []
    # WP-106: the official titles of the codes (on the notice's page all of them, in a list the main code's)
    cpvTitles: dict[str, str] = {}


class SearchGroupRef(BaseModel):
    id: str
    label: str
    cpv: list[str]


class TenderPage(BaseModel):
    items: list[Tender]
    total: int
    # True when the count stopped at `TOTAL_CAP`: `total` is then "at least this many".
    totalCapped: bool = False
    page: int
    pageSize: int
    # The list serves no position beyond this (a page past it has no items).
    maxOffset: int = MAX_OFFSET
    # When this page was worked out (a list kept in a snapshot or in memory says when, not when it was asked
    # for): the counts beside a list (`scope-counts`) carry theirs too, so a difference between the two can be
    # read as one of time (WP-52, T13).
    asOf: datetime | None = None
    meta: ListMeta = ListMeta()
    # WP-98: the terms of other languages the search words were also read as, and the product groups they belong to
    # (`search_terms`), so the page can say what else was searched and, with nothing found, offer the group's codes.
    alsoSearched: list[str] = []
    searchGroups: list[SearchGroupRef] = []


def search_info(q: str | None) -> dict[str, Any]:
    """WP-98: `alsoSearched` and `searchGroups` of a search text (empty without one)."""
    e = expand(search_words((q if isinstance(q, str) else "").replace("\x00", "").strip()))
    return {"alsoSearched": e.also, "searchGroups": [{"id": g.id, "label": g.label, "cpv": list(g.cpv)} for g in e.groups]}


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
    # True for a version a history load wrote: `detectedAt` is the day we read it, the
    # change itself was published earlier.
    historic: bool = False
    # True for our own corrected reading of a payload we already held (`remapped`): a state
    # the archive holds, shown as such, and never counted as the publisher's amendment.
    correction: bool = False
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
    # Other organisation rows of the same body shown under this buyer (WP-22, migration
    # 0055): 0 when it has none.
    nameVariants: int = 0
    # The profile of the same body in the networks layer (WP-28), when it took part in funded projects.
    organisationSlug: str | None = None
    # WP-96: the counts are of the list's default scope (All defence); of the open ones, the military goods and works
    # (`scope=core`). Only on the buyer's own page.
    openCoreCount: int | None = None
    scope: str = "relevant"
    # WP-98b: with `cpv=`, the buyer's notices under the codes (each once, as the list shows them); else None.
    cpvCount: int | None = None
    # WP-111: on the buyer's own page, the names its other rows publish under (`variant_names`)
    variantNames: list[str] = []


class BuyerPage(BaseModel):
    items: list[Buyer]
    total: int
    page: int
    pageSize: int
    # WP-98b: false when the counts under the codes could not be collapsed in time (`under_codes`): a notice published in
    # TED and in a national portal may then be counted twice in `cpvCount`.
    cpvCountCollapsed: bool = True


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


CPV_PREFIX = re.compile(r"^[0-9]{2,8}$")
# WP-89: a notice with any CPV code under one of the prefixes (as typed: the tender list's `cpv` reading), over the
# defence-scope GIN index of migration 0099 (`award_set.CPV_MATCH` with the prefixes as given).
CPV_HEADS = "dgate_cpv_heads(o.cpv_codes) && %s::text[]"
# WP-101: the same over the code heads stored for the search (`opportunity_search`, migration 0113)
TS_CPV_HEADS = "ts.cpv_heads && %s::text[]"


def cpv_prefixes(value: str | None, name: str = "cpv") -> list[str]:
    """The CPV prefixes of a `cpv=` parameter: 2 to 8 digits each, a trailing check digit (35120000-1) dropped;
    anything else is a 422, as the other list filters refuse what they cannot read."""
    out: list[str] = []
    for item in _split(value, name, max_length=10):
        code = item[:8] if re.fullmatch(r"[0-9]{8}-[0-9]", item) else item
        if not CPV_PREFIX.match(code):
            raise HTTPException(422, f"{name}: CPV codes or their leading part, 2 to 8 digits")
        if code not in out:
            out.append(code)
    return out


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
    "o.sig_cpv, o.sig_cpv_military, o.sig_buyer, o.sig_linked_defence, o.dual_use, "
    "o.buyer_class, "
    "o.security_clearance_required, o.subcontracting_signal, o.source_url, "
    "o.status, o.ted_ref, o.lot_count, o.value_kind, o.notice_subtype, "
    "o.suppressed, o.buyer_withheld, o.notice_date, o.notice_kind, o.other_buyers"
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
                      AND NOT suppressed AND NOT buyer_withheld
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


def _version_info(conn, ids: list[int]) -> dict[int, tuple[int, datetime | None, int]]:
    """For each notice: how many real versions it has (the first, and each later one that
    changed something a reader can see: see `timeline`) and when the newest of them was
    observed. A bulk re-reading of the same payload (`remapped`, `reread`) is neither:
    "last changed" is when the SOURCE changed the notice, as we saw it, not when we
    reprocessed it (253 of 291 open TED notices said 12 October 17:0x). The third number is
    how many of the later versions are the publisher's own, seen when they happened: a
    version a history load wrote (`history`) is listed but is neither "amended" nor "last
    changed"."""
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
        real = [e for e in entries[1:] if not e.get("historic")]
        last = real[-1] if real else (entries[0] if entries else None)
        out[oid] = (len(entries), last["detectedAt"] if last else None, len(real))
    return out


def _version_counts(conn, ids: list[int]) -> dict[int, int]:
    return {oid: n for oid, (n, _, _) in _version_info(conn, ids).items()}


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
    dual-use: that is `buyer`, never "military product code".

    A notice filed outside `core` for having only one signal from the wrong kind of buyer
    names that instead: `directive_civil_buyer` (the directive's legal basis, from a civil
    buyer) or `security_buyer_cpv` (a military CPV, from a police, prison, border, customs
    or tax body)."""
    group = scope_group_of(
        legal_basis=bool(r.get("sig_legal_basis")),
        military_cpv=bool(r.get("sig_cpv_military")), dual_use=bool(r.get("dual_use")),
        buyer=bool(r.get("sig_buyer")), linked_defence=bool(r.get("sig_linked_defence")),
        buyer_class=r.get("buyer_class"))
    if group == GROUP_CIVIL_DIRECTIVE:
        return [group], []
    out: list[str] = []
    if r.get("sig_legal_basis"):
        out.append("legal_basis")
    codes = military_cpv_codes(cpv) if r.get("sig_cpv_military") else []
    if group == GROUP_SECURITY_CPV:
        return [group], codes
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
              checked: datetime | None = None,
              amended: bool | None = None,
              buyer_page: bool = True,
              last_change_kind: str | None = None,
              buyer_head: int | None = None) -> dict[str, Any]:
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
    deadline, deadline_from, first_passed = shown_deadline(deadline, extra.get("deadline"))
    eff = api.effective_status(r.get("status"), deadline, r.get("published_at"),
                               superseded=superseded, procedure=r.get("procedure_type"))
    notes = anomalies(deadline, r.get("published_at"))
    if deadline_from:
        notes.append("deadline-differs-from-ted-twin")
    if first_passed:
        notes.append(FIRST_DEADLINE_PASSED)
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
    if r.get("buyer_withheld"):
        # An organisation suppressed on request: the notice stays, its buyer is nobody
        # the site can name, link or aggregate.
        org_id, org_name, buyer_name = None, WITHHELD_NAME, WITHHELD_NAME
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
        # Null when the buyer has no page (`buyers_with_page`): a link to a 404 is worse than a name.
        # WP-87: the family's head, whose page it is: a member's own id (/buyers/28871-baainbw) read as a second
        # BAAINBw although its page redirects to the head
        "buyerSlug": (make_slug(buyer_head or org_id, names.get(buyer_head or org_id) or org_name)
                      if org_id and buyer_page else None),
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
        "confidence": confidence_of_row(r),
        "deadline": deadline,
        "deadlineFrom": deadline_from,
        "deadlineKnown": deadline is not None,
        "publishedAt": _day(r.get("published_at")),
        "publishedKnown": r.get("published_at") is not None,
        "noticeDate": _day(r.get("notice_date")),
        "noticeKind": r.get("notice_kind"),
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
        "amended": n_versions > 1 if amended is None else amended,
        "versionCount": n_versions,
        "securityClearance": bool(r.get("security_clearance_required")),
        "subcontracting": bool(r.get("subcontracting_signal")),
        "otherBuyers": [] if r.get("buyer_withheld") else [b for b in (r.get("other_buyers") or []) if b],
        "sameNotice": [{"source": t["source"], "url": t.get("url"), "id": str(t["id"]),
                        "noticeId": t["native_id"]} for t in twins],
        "source": {
            "sourceId": r["source_code"],
            "sourceName": r["source_name"],
            "url": http_url(r.get("source_url")),
            "retrievedAt": observed or datetime.now(timezone.utc),
            "checkedAt": checked,
            # What `retrievedAt` is: `amendment` (the newest change to the notice that we saw it make) or
            # `first_seen` (we have seen no change, so it is when we first collected the notice). The label
            # "last change seen at the source" is true of the first only (WP-52, T11).
            "lastChangeKind": last_change_kind,
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
              AND NOT t.suppressed
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
            WHERE o.id = ANY(%s) AND NOT t.suppressed
              AND (coalesce(o.twin_method, '') NOT IN ('procedure_id', 'heuristic')
                   OR t.status = o.status)""", (ids,)).fetchall()
    return {r["row_id"]: {"procedure": r["procedure_type"], "deadline": r["deadline_at"]}
            for r in got}


def _present(conn, rows: list[dict[str, Any]], *, checked: bool = False) -> list[dict[str, Any]]:
    """`checked`: also say when each notice's source was last collected (`source.checkedAt`).
    Only the API's own endpoints ask: the account role reads no run table."""
    ids = [r["id"] for r in rows]
    orgs = sorted({r["buyer_org_id"] for r in rows if r.get("buyer_org_id")})
    heads = {r["id"]: r["head"] for r in conn.execute(
        "SELECT x.id, dgate_buyer_head(x.id) AS head FROM unnest(%s::bigint[]) AS x(id)", (orgs,)).fetchall()} if orgs else {}
    names = _buyer_names(conn, sorted(set(orgs) | set(heads.values())))
    info = _version_info(conn, ids)
    versions = {i: n for i, (n, _, _) in info.items()}
    twins = _api()._twins(conn, ids)
    span = _observed_span(conn, ids)
    over = _superseded(conn, rows)
    borrowed = _twin_values(conn, rows)
    extras = _twin_extras(conn, rows)
    runs = _source_runs(conn) if checked else {}
    paged = buyers_with_page(conn, rows)
    out = []
    for r in rows:
        seen = info.get(r["id"], (0, None, 0))
        amended = seen[2] > 0 if r["id"] in info else None
        out.append(to_tender(
            r, names, versions, twins.get(r["id"], []),
            seen[1] or span.get(r["id"], (None, None))[1],
            superseded=r["id"] in over, twin_value=borrowed.get(r["id"]),
            first_seen=span.get(r["id"], (None, None))[0], twin_extra=extras.get(r["id"]),
            checked=runs.get(r["source_code"]), amended=amended,
            buyer_page=r.get("buyer_org_id") in paged,
            last_change_kind="amendment" if amended else "first_seen",
            buyer_head=heads.get(r.get("buyer_org_id"))))
    return out


def buyers_with_page(conn, rows: list[dict[str, Any]]) -> set[int]:
    """Of the buyers of these notices, the ones that have a buyer page. A page exists for a buyer family
    with at least one notice of the default scope (`aggregate_sql`; WP-96: All defence, it was the core scope and a buyer
    that only supplies (the armed forces buying food) had none, and a link to it was a 404 for 73 of the 389 buyers of the open list (WP-52, T14).
    A core notice settles it for its own buyer; the others are asked of the database in one query."""
    ids = {r["buyer_org_id"] for r in rows if r.get("buyer_org_id") and not r.get("buyer_withheld")}
    known = {r["buyer_org_id"] for r in rows
             if r.get("buyer_org_id") in ids and _api().row_scope(r) == "core"}
    ask = sorted(ids - known)
    if not ask:
        return known
    got = conn.execute(
        f"""SELECT x.id FROM unnest(%s::bigint[]) AS x(id)
             WHERE EXISTS (SELECT 1 FROM opportunity o
                            WHERE o.buyer_org_id = ANY(dgate_family_ids(x.id))
                              AND o.is_defence AND NOT o.suppressed AND NOT o.buyer_withheld AND {_api().SCOPE_SQL["relevant"]})""",
        (ask,)).fetchall()
    return known | {r["id"] for r in got}


def collapse_clauses(where: list[str], *, same_buyer: bool = False) -> str:
    """The three rules that show a notice once, as one SQL condition over `opportunity o`:
    the filters (`where`, written over `o`) are applied to the notice that would replace
    this one as well, so a filter that keeps a notice and not its twin never makes it vanish.
    `same_buyer` is for an aggregate over every buyer at once: the replacing notice must be
    the same buyer's, which is what `buyer = X` in `where` says for the list. The condition
    carries no parameters of its own: each `%s` of `where` appears once per rule."""
    def extra(alias: str) -> list[str]:
        # The same buyer is the same family (migration 0055): a twin filed under another
        # name variant of the body still replaces the notice.
        return ([f"dgate_buyer_head({alias}.buyer_org_id) = dgate_buyer_head(o.buyer_org_id)"]
                if same_buyer else [])

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
    # A national row linked by procedure identifier is also dropped when ANY TED notice of its procedure with
    # its status is in the result, not only the newest one its `ted_ref` names: in Closed the newest TED stage
    # may still be open (deadline 2 Nov) while the stage the national row copies (deadline 20 Oct) is closed,
    # and the two copies stood side by side (re-audit of the data pages, NEW-3, procedure ef67494e-...).
    rep_where = [re.sub(r"\bo\.", "r.", clause_) for clause_ in where] + extra("r")
    not_republished = ("NOT EXISTS (SELECT 1 FROM opportunity r "
                       "WHERE o.procedure_identifier IS NOT NULL "
                       "AND r.procedure_identifier = o.procedure_identifier "
                       "AND r.status = o.status AND r.id <> o.id "
                       "AND ((r.source_id = o.source_id "
                       "AND (coalesce(r.published_at, 'epoch'::date), r.id) "
                       "> (coalesce(o.published_at, 'epoch'::date), o.id)) "
                       "OR (o.twin_method = 'procedure_id' AND r.source_id <> o.source_id "
                       "AND r.source_id = (SELECT id FROM source WHERE code = 'ted'))) AND "
                       + " AND ".join(rep_where) + ")")
    return " AND ".join((not_collapsed, not_rectified, not_republished))


# -------------------------------------------------------------- endpoints

# Orders a list can run in. Each is the order of a btree index (migration 0091), so a page of any
# depth is a walk that stops after `offset + limit` rows instead of a sort of the whole result.
ORDER_DEADLINE_ASC = "o.deadline_at ASC NULLS LAST, o.id ASC"
# The same order, written so that no index can serve it. For the open notices (2,600 rows, found by
# `opp_open_candidates`) the planner would otherwise walk `opp_list_deadline_asc` from the oldest deadline,
# through 350,000 closed notices, to find the first ten that are open: 2 to 7 s against 0.4 s.
ORDER_OPEN_DEADLINE = "(o.deadline_at IS NULL), o.deadline_at ASC, o.id ASC"
ORDER_DEADLINE_DESC = "o.deadline_at DESC NULLS LAST, o.published_at DESC NULLS LAST, o.id DESC"
ORDER_PUBLISHED_DESC = "coalesce(o.published_at, o.notice_date) DESC NULLS LAST, o.id DESC"
# WP-106 (p02, p04, p07): by value and by code, each over an index of migration 0118. Amounts are never converted, so the
# value order is per currency: EUR first, then each other currency by itself (with a `currency` filter, that one only), the
# largest first; a placeholder amount (`PLACEHOLDER_VALUE_MAX`) or none last. The code order is the main (first) CPV code.
_VALUE_CURRENCY = f"(CASE WHEN o.value_amount > {PLACEHOLDER_VALUE_MAX} THEN o.value_currency END)"
ORDER_VALUE_DESC = (f"({_VALUE_CURRENCY} IS DISTINCT FROM 'EUR'), {_VALUE_CURRENCY} ASC NULLS LAST, "
                    f"(CASE WHEN o.value_amount > {PLACEHOLDER_VALUE_MAX} THEN o.value_amount END) DESC NULLS LAST, o.id DESC")
ORDER_CPV_ASC = "(o.cpv_codes[1]) ASC NULLS LAST, o.id ASC"
SORT_PATTERN = "^(core-first|open-first|deadline-asc|deadline-desc|published-desc|value-desc|cpv-asc)$"


def core_first(status: str, scope: str, sort: str | None) -> bool:
    """WP-87: whether a list leads with its core notices: the default view (open, the defence-relevant scope, no
    sort asked for) and an explicit `core-first`. Musical instruments and stair repairs bought by a defence body
    stood first because their deadline was soonest; a core notice now always comes before them."""
    return status == "open" and scope == "relevant" and sort in (None, "core-first")


def tender_order(sort: str | None, status: str, eff: str) -> str:
    """The ORDER BY of a tenders list. With no sort asked for, open notices run soonest deadline
    first; closed ones the other way, newest deadline first, then newest publication: the soonest of
    a closed list is a notice from years ago. A sort that was asked for is always honoured. (`all`
    with no sort asked for is an open part and the rest: `list_tenders` runs them one after the
    other, so no "open first" key is part of the order.)"""
    if sort == "published-desc":
        # A folder with only its award has no publication date: it sorts by the date of
        # that notice, and the site labels it as such.
        return ORDER_PUBLISHED_DESC
    if sort == "value-desc":
        return ORDER_VALUE_DESC
    if sort == "cpv-asc":
        return ORDER_CPV_ASC
    if sort == "deadline-desc" or (sort is None and status in ("closed", "planned")):
        return ORDER_DEADLINE_DESC
    return ORDER_OPEN_DEADLINE if status == "open" else ORDER_DEADLINE_ASC


SEARCH_SEPARATORS = re.compile(r"[\s\-–—/_.,;:()\"'’]+")
RX_TERMS = 4            # WP-98: terms per regular expression of a synonym group (see `_tender_filters`)
MAX_SEARCH_WORDS = 6


# WP-101: a search that is a TED notice number (220199-2026, 2026/S 203-724451) asks for that notice, whatever its status:
# the global search reads it in every status (`search.opens_on`) and the site's list opens on All for it (web/lib/search.ts).
NOTICE_NUMBER = re.compile(r"^(?:\d{1,8}-(?:19|20)\d{2}|(?:19|20)\d{2}/S \d{1,3}-\d{1,8})$", re.IGNORECASE)


def search_words(text: str) -> list[str]:
    """The words of a search text, split where `dg_fold` splits (migration 0054); a piece
    that is only punctuation is dropped, and at most MAX_SEARCH_WORDS are used."""
    return [w for w in SEARCH_SEPARATORS.split(text or "") if w][:MAX_SEARCH_WORDS]


def status_conditions(status: str, eff: str) -> list[str]:
    """The conditions of a status filter. `open`: effectively open, and (redundant, but the planner can
    use them) the stored status is `open` and the deadline is ahead or not stated: that is 2,600 of 357,000
    rows, found by index, where the expression alone made it read every notice of a search word.
    `closed` is everything that is no longer taking tenders and is not planned; `planned` a notice that
    announces one (`api.EFFECTIVE_STATUS_SQL`); `rest` (internal) is everything but open."""
    if status == "open":
        return [f"{eff} = 'open'", "o.status = 'open'",
                "(o.deadline_at >= now() OR o.deadline_at IS NULL)"]
    if status == "closed":
        return [f"{eff} NOT IN ('open', 'forthcoming')"]
    if status == "planned":
        return [f"{eff} = 'forthcoming'", "o.status = 'forthcoming'"]
    if status == "rest":
        return [f"{eff} <> 'open'"]
    return []


def _tender_filters(q, country, cpv, status, scope, goods, buyer, from_, to, min_, max_, currency,
                    conn=None, *, cpv_main: bool = False, not_cpv: str | None = None):
    """The WHERE conditions (written over `opportunity o`) and their parameters that a tenders
    list or export applies: one place, so the list and the export can never disagree.

    One country, and a buyer whose family is one row, are written as a plain `=` (WP-72): the
    planner then walks the (country | buyer, order) indexes of migration 0096 in the list's order and
    stops after a page. `= ANY(...)` over the same one value made it walk the whole list index and
    filter (the Malta list and a buyer page read most of 290,000 index entries per page)."""
    api = _api()
    # WP-90: an endpoint called as a plain function (a test, a job) passes its `Query(...)` defaults for the filters it leaves out
    cpv_main = cpv_main is True
    not_cpv = not_cpv if isinstance(not_cpv, str) else None
    eff = api.EFFECTIVE_STATUS_SQL
    where = ["o.is_defence = TRUE", "NOT o.suppressed", api.SCOPE_SQL[scope]]
    if goods:
        where.append(api.GOODS_SQL[goods])
    params: list[Any] = []

    where += status_conditions(status, eff)

    text = (q or "").replace("\x00", "").strip()
    words = search_words(text)
    if words:
        # Every word must begin a word of the title (the original, or the English one TED gives) or the buyer's
        # name, accents and punctuation folded on both sides (migration 0054); the notice number is matched
        # as typed. The folded titles are trigram-indexed. WP-90: or the English title of one of the notice's
        # own CPV codes (`cpv_labels`, over the GIN index of migration 0099).
        # WP-98: the words in any order, each slot of `search_terms.expand` filled by the typed words or a term of its group in
        # another language ("fardamento": "uniform", "Bekleidung" ...); a run of words is also read against the English
        # titles of the codes together ("spare parts": 34330000), where one of them alone names too many codes.
        # WP-101: over `opportunity_search` (migration 0113), the same texts folded once when the notice was written: a
        # candidate of the trigram indexes is re-checked against stored text, where `dg_fold` of the title per term made
        # "Drehteile Frästeile" 12.6 s on production. A withheld buyer has no name there. The condition is a correlated
        # EXISTS so that the collapse rules (`collapse_clauses`, which rewrite `o.` for the twin) read the twin's own row.
        per_word = ("(ts.title_en LIKE dg_word_pattern(%s) "
                    "OR ts.title_original LIKE dg_word_pattern(%s) "
                    "OR ts.buyer_name LIKE dg_word_pattern(%s){labels})")
        slots = []
        for alts in expand(words).slots:
            alt_sql = []
            # The typed words stay words in any order (below); the group's other terms are phrases, as written
            singles = alts[1:]
            if singles:
                # The other terms of a group as one regular expression per column ("a word begins with one of them",
                # a term of several words as that phrase, over the same trigram indexes). In chunks of RX_TERMS: over a
                # longer alternation pg_trgm keeps fewer trigrams and the index hands back ten times the matches to
                # re-check (drone: 12,966 candidates for 1,306 matches; 4 terms: exact). Titles only: a product word in
                # another language names no buyer, and over the buyer names the short terms (UAV, UAS) made 15,000 index
                # candidates to re-check (5 s for q=drone&status=all). The code overlaps go last.
                folded = [re.escape(" ".join(fold_words(" ".join(t)))) for t in singles]
                for k in range(0, len(folded), RX_TERMS):
                    rx = " (?:" + "|".join(folded[k:k + RX_TERMS]) + ")"
                    alt_sql.append("ts.title_en ~ %s OR ts.title_original ~ %s")
                    params += [rx] * 2
                codes = sorted({c for t in singles
                                for c in (codes_for_word(t[0]) if len(t) == 1 else codes_for_words(tuple(t)))})
                if codes:
                    alt_sql.append(TS_CPV_HEADS)
                    params.append(codes)
            for alt in alts[:1]:
                ands = []
                for w in alt:
                    codes = codes_for_word(w)
                    ands.append(per_word.format(labels=f" OR {TS_CPV_HEADS}" if codes else ""))
                    params += [w] * 3 + ([list(codes)] if codes else [])
                together = codes_for_words(tuple(alt)) if len(alt) > 1 else ()
                if together:
                    params.append(list(together))
                alt_sql.append("(" + " AND ".join(ands) + ")" + (f" OR {TS_CPV_HEADS}" if together else ""))
            slots.append("(" + " OR ".join(alt_sql) + ")")
        # (one slot of several words has just read them together)
        together = codes_for_words(tuple(words)) if len(words) > 1 and len(slots) > 1 else ()
        if together:
            params.append(list(together))
        where.append("EXISTS (SELECT 1 FROM opportunity_search ts WHERE ts.id = o.id AND ((" + " AND ".join(slots) + ")"
                     + (f" OR {TS_CPV_HEADS}" if together else "") + " OR ts.native_id ILIKE %s))")
        params.append(_like(text))
    countries = _split(country, "country", upper=True, max_length=2)
    if len(countries) == 1:
        where.append("o.country = %s")
        params.append(countries[0])
    elif countries:
        where.append("o.country = ANY(%s)")
        params.append(countries)
    prefixes = _split(cpv, "cpv", max_length=api.MAX_PREFIX_LENGTH)
    if prefixes:
        clauses = []
        for p in prefixes:
            # WP-90: `cpv_main` reads the notice's main code only (the first, as `Tender.cpv`)
            clauses.append("o.cpv_codes[1] LIKE %s" if cpv_main
                           else "EXISTS (SELECT 1 FROM unnest(o.cpv_codes) c WHERE c LIKE %s)")
            params.append(f"{p}%")
        where.append("(" + " OR ".join(clauses) + ")")
    if excluded := cpv_prefixes(not_cpv, "notCpv"):
        # WP-90: no code of the notice under any of these (main code or not): "not 3511", fire extinguishers
        where.append("NOT EXISTS (SELECT 1 FROM unnest(o.cpv_codes) c WHERE c LIKE ANY(%s))")
        params.append([f"{p}%" for p in excluded])
    if buyer is not None:
        # Every organisation row of the buyer's family (any member id gives the family).
        ids = (conn.execute("SELECT dgate_family_ids(%s) AS ids", (buyer,)).fetchone()["ids"]
               if conn is not None else None)
        if ids is not None and len(ids) == 1:
            where.append("o.buyer_org_id = %s")
            params.append(ids[0])
        elif ids:
            where.append("o.buyer_org_id = ANY(%s)")
            params.append(sorted(ids))
        else:
            where.append("o.buyer_org_id = ANY(ARRAY(SELECT unnest(dgate_family_ids(%s))))")
            params.append(buyer)
    if from_:
        where.append("o.deadline_at >= %s")
        params.append(datetime.combine(from_, time(0, 0), tzinfo=timezone.utc))
    if to:
        # The whole of the day in UTC, as `from` is read: `%s::date + 1` was compared with
        # a timestamptz in the session's time zone, so the bound moved with the server.
        where.append("o.deadline_at <= %s")
        params.append(datetime.combine(to, time.max, tzinfo=timezone.utc))
    if min_ is not None or max_ is not None or currency:
        # A currency alone selects the notices that state a value in it; a range is read in it, EUR when none
        # is given. A placeholder (0, 0.01, 1) is "not stated" and must not match "up to EUR 100,000".
        where.append("o.value_currency = %s AND o.value_amount > %s")
        params += [(currency or "EUR").upper(), PLACEHOLDER_VALUE_MAX]
        if min_ is not None:
            where.append("o.value_amount >= %s")
            params.append(min_)
        if max_ is not None:
            where.append("o.value_amount <= %s")
            params.append(max_)
    return where, params, eff


def _confidence_levels(text: str | None) -> list[str]:
    """The levels of a `confidence=high,medium` filter, in the order given; every level, or
    none at all, means no filter. An unknown level is a 422, like any other bad filter."""
    got = [w.strip().lower() for w in (text or "").split(",") if w.strip()]
    bad = [w for w in got if w not in LEVELS]
    if bad:
        raise HTTPException(422, f"confidence must be a comma list of {', '.join(LEVELS)}")
    levels = [lv for lv in LEVELS if lv in got]
    return [] if len(levels) == len(LEVELS) else levels


STATUS_PATTERN = "^(open|closed|planned|all)$"

# ops/warm_lists sets this: its snapshots hold the exact total of the views it computes.
EXACT_TOTALS: ContextVar[bool] = ContextVar("tender_exact_totals", default=False)


# A count is worked out in two steps, each in a time box. The first stops at SMALL_CAP rows and is cheap
# wherever the filters are selective (most searches); the second goes on to TOTAL_CAP. The second is where
# a search word that matches a fifth of the archive (Bundeswehr: 19,000 notices, each one re-tested against
# its twins) costs 25 s: it gives up after COUNT_BUDGET_MS and the list says "at least SMALL_CAP".
SMALL_CAP = 200
COUNT_BUDGET_MS = 1200


def _count_up_to(conn, cond: str, where: list[str], params: list[Any], cap: int, budget_ms: int) -> int | None:
    """How many rows the list has, counting no further than `cap + 1`; None when `budget_ms` ran out."""
    import psycopg

    sql = (f"SELECT count(*) AS n FROM (SELECT 1 FROM opportunity o WHERE {cond} AND {collapse_clauses(where)} "
           "LIMIT %s) c")
    kept = conn.execute("SELECT current_setting('statement_timeout') AS t").fetchone()["t"]
    try:
        # A savepoint when the caller is in a transaction: the cancelled query takes back its own work and the
        # local setting, and nothing the caller did before is lost.
        with conn.transaction():
            conn.execute("SELECT set_config('statement_timeout', %s, true)", (f"{budget_ms}ms",))
            n = conn.execute(sql, params * 4 + [cap + 1]).fetchone()["n"]
            conn.execute("SELECT set_config('statement_timeout', %s, true)", (kept,))
    except psycopg.errors.QueryCanceled:
        return None
    return n


def _count(conn, where: list[str], params: list[Any], extra: list[str] | None = None) -> tuple[int, bool]:
    """(how many notices the list holds, whether that is only "at least"). The collapse rules are the
    list's; `extra` are conditions that are not part of what a twin has to match (the open part of `all`).
    The scan stops after `TOTAL_CAP + 1` rows and after `COUNT_BUDGET_MS`, so the work is bounded."""
    cond = " AND ".join([*where, *(extra or [])])
    if EXACT_TOTALS.get():                  # the worker's snapshot: no cap, no time box
        n = conn.execute(f"SELECT count(*) AS n FROM opportunity o WHERE {cond} AND {collapse_clauses(where)}",
                         params * 4).fetchone()["n"]
        return n, False
    small = _count_up_to(conn, cond, where, params, SMALL_CAP, COUNT_BUDGET_MS)
    if small is None:
        return 0, True                      # not even that in time: the caller knows what it has read
    if small <= SMALL_CAP:
        return small, False
    big = _count_up_to(conn, cond, where, params, TOTAL_CAP, COUNT_BUDGET_MS)
    if big is None:
        return SMALL_CAP, True
    return min(big, TOTAL_CAP), big > TOTAL_CAP


FEW_ROWS = 3000
# A rare word is counted well inside this; a common one gives up early and is read along the index as before.
FEW_BUDGET_MS = 600


def _few(conn, where: list[str], params: list[Any], extra: list[str], order: str, searched: bool) -> int | None:
    """WP-98: how many notices a searched part of a list holds, when that is at most FEW_ROWS (else None). Such a part
    is read by its matches and sorted (`_rows(few=True)`) instead of walked along the order's index: for a rare word
    (`q=drone&status=all`: 686 of 357,000) the walk read most of the closed notices to find a page and ran past the
    5 s statement timeout on production (503, persona round of 23 October 2026). The count is the one the list would
    make anyway, in its time box, and is reused as the part's total."""
    if not searched or order == ORDER_OPEN_DEADLINE or EXACT_TOTALS.get():
        return None                      # the open order is never walked along an index (see ORDER_OPEN_DEADLINE)
    n = _count_up_to(conn, " AND ".join([*where, *extra]), where, params, FEW_ROWS, FEW_BUDGET_MS)
    return n if n is not None and n <= FEW_ROWS else None


def _rows(conn, where: list[str], params: list[Any], extra: list[str], order: str,
          limit: int, offset: int, few: bool = False) -> list[dict[str, Any]]:
    """`limit` notices from position `offset` of one part of a list, in `order`. `few`: the part is small (`_few`); the
    same order, written so that no index can serve it, so the planner reads the matches and sorts them."""
    cond = " AND ".join([*where, *extra])
    if few:
        order = "(o.id IS NULL), " + order
    return conn.execute(
        f"{TENDER_SELECT} WHERE {cond} AND {collapse_clauses(where)} ORDER BY {order} LIMIT %s OFFSET %s",
        params * 4 + [limit, offset]).fetchall()


def _snapshot_total(conn, asked: dict[str, Any]) -> tuple[int, bool] | None:
    """The total the worker stored for the first page of the same filters, if it is recent: a deep page of
    "Closed" then says what page 1 says (287,634), not "10,000 or more". None when there is none."""
    from .listcache import SNAPSHOT_HOURS, snapshot_key

    key = snapshot_key("tenders", {**asked, "page": 1, "pageSize": SNAPSHOT_PAGE_SIZE, "with_meta": True})
    try:
        with conn.transaction():        # a savepoint: a role that may not read the table loses nothing else
            row = conn.execute(
                "SELECT (body->>'total')::bigint AS total, body->>'totalCapped' AS capped FROM list_snapshot "
                "WHERE key = %s AND computed_at > now() - make_interval(hours => %s)",
                (key, SNAPSHOT_HOURS)).fetchone()
    except Exception:  # noqa: BLE001 - a snapshot is a shortcut, never a failure
        return None
    if not row or row["capped"] == "true":
        return None
    return int(row["total"]), False


def _kept_in_snapshot(kwargs: dict[str, Any]) -> bool:
    """The worker keeps the closed and all views; the open ones are read live, so that the counts beside a
    list and the list are of the same moment (a stored open view is up to 8 hours behind the deadlines)."""
    return kwargs.get("status") != "open"


@router.get("/v1/tenders", response_model=TenderPage)
@cache_list("tenders", ttl=5 * 60, snapshot=_kept_in_snapshot)
def list_tenders(
    q: str | None = Query(None, max_length=100),
    country: str | None = Query(None, max_length=200),
    cpv: str | None = Query(None, max_length=400),
    status: str = Query("open", pattern=STATUS_PATTERN),
    scope: str = Query("relevant", pattern="^(relevant|core|supply|all)$"),
    goods: str | None = Query(None, pattern="^defence$"),
    buyer: int | None = Query(None, ge=1, le=MAX_BIGINT),
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    min_: float | None = Query(None, alias="min", ge=0, le=1e13),
    max_: float | None = Query(None, alias="max", ge=0, le=1e13),
    currency: str | None = Query(None, pattern="^[A-Za-z]{3}$"),
    sort: str | None = Query(None, pattern=SORT_PATTERN),
    page: int = Query(1, ge=1, le=1000),
    pageSize: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    confidence: str | None = Query(None, max_length=40),
    cpvMain: bool = Query(False),
    notCpv: str | None = Query(None, max_length=400),
    conn=Depends(get_conn),
    with_meta=Depends(serves_meta),
):
    """A page of the list and its total, with the work bounded (WP-52, T2 and T3):

      - the rows are read `LIMIT`-first in the order of an index, with no window count over the whole
        result, so a page at any depth costs the rows up to it; a position past `MAX_OFFSET` has no items
      - the total is counted up to `TOTAL_CAP`; a longer list says `totalCapped` (or repeats the exact
        total a snapshot holds for the same filters)
      - `all` with no sort, or sorted by deadline, is the open notices (soonest deadline first) and then
        the rest, as two reads: the open part is a few thousand rows, found by index
      - WP-87: the default view (open, the defence-relevant scope, no sort asked for, or `core-first`) leads with
        the core notices (the notice itself is defence), soonest deadline first, then the other purchases of
        defence buyers; the same two-read way. The total is the same list's: only the order changes"""
    where, params, eff = _tender_filters(q, country, cpv, status, scope, goods, buyer, from_,
                                         to, min_, max_, currency, conn=conn, cpv_main=cpvMain, not_cpv=notCpv)
    levels = _confidence_levels(confidence)
    if levels:
        where.append("(" + " OR ".join(CONFIDENCE_SQL[lv] for lv in levels) + ")")
    asked = {"q": q, "country": country, "cpv": cpv, "status": status, "scope": scope, "goods": goods,
             "buyer": buyer, "from_": from_, "to": to, "min_": min_, "max_": max_, "currency": currency,
             "sort": sort, "confidence": confidence, "cpvMain": cpvMain, "notCpv": notCpv}
    start = (page - 1) * pageSize
    served = start < MAX_OFFSET
    if status == "all" and sort in (None, "open-first", "deadline-asc"):
        # WP-106 (p02, p04, p07): after the open notices the rest runs newest deadline first, as the Closed list does; the
        # oldest first (2017 under the open ones) only when `deadline-asc` is asked for
        parts = [(status_conditions("open", eff), ORDER_OPEN_DEADLINE),
                 (status_conditions("rest", eff), ORDER_DEADLINE_ASC if sort == "deadline-asc" else ORDER_DEADLINE_DESC)]
    elif core_first(status, scope, sort):
        parts = [([CORE], ORDER_OPEN_DEADLINE), ([f"NOT ({CORE})"], ORDER_OPEN_DEADLINE)]
    else:
        parts = [([], tender_order(sort, status, eff))]

    rows: list[dict[str, Any]] = []
    total, capped = 0, False
    searched = bool(search_words((q if isinstance(q, str) else "").replace("\x00", "").strip()))
    if len(parts) == 2:
        (open_extra, open_order), (rest_extra, rest_order) = parts
        n_open, open_capped = _count(conn, where, params, open_extra)
        if served and (open_capped or start < n_open):
            rows = _rows(conn, where, params, open_extra, open_order, pageSize, start)
            if open_capped and len(rows) < pageSize and (rows or start == 0):
                n_open, open_capped = start + len(rows), False        # the end of the open part was read
            elif open_capped:
                # The open part is longer than its count could say in time ("at least"): this page is all open
                # notices, and the total is never below them (re-audit of the data pages, NEW-2: "at least 112"
                # for Bundeswehr while the open notices alone were 116).
                n_open = max(n_open, start + len(rows) + 1)
        want = pageSize - len(rows)
        got_rest: list[dict[str, Any]] | None = None
        rest_start = max(0, start - n_open)
        few = _few(conn, where, params, rest_extra, rest_order, searched) if served and want > 0 else None
        if served and want > 0:
            got_rest = _rows(conn, where, params, rest_extra, rest_order, want, rest_start, few=few is not None)
            rows += got_rest
        if few is not None:
            n_rest, capped = few, False                               # counted in full by `_few`
        elif got_rest is not None and len(got_rest) < want and (got_rest or rest_start == 0):
            n_rest, capped = rest_start + len(got_rest), False       # the end of the list was read
        else:
            n_rest, capped = _count(conn, where, params, rest_extra)
        total, capped = n_open + n_rest, capped or open_capped
        if capped and status == "all":
            # "At least" is never below the Open list of the same filters (re-audit of the data pages, NEW-2:
            # "at least 112" for Bundeswehr, Open alone 116). The Open list collapses twins among open notices
            # only; here an open notice whose twin is closed is counted in the rest, which the time box did not
            # finish. Each notice of the Open list is in this list or stands for its twin here, so its count holds.
            o_where, o_params, _ = _tender_filters(q, country, cpv, "open", scope, goods, buyer, from_,
                                                   to, min_, max_, currency, conn=conn, cpv_main=cpvMain,
                                                   not_cpv=notCpv)
            if levels:
                o_where.append("(" + " OR ".join(CONFIDENCE_SQL[lv] for lv in levels) + ")")
            total = max(total, _count(conn, o_where, o_params)[0])
    else:
        extra, order = parts[0]
        fetched = False
        few = _few(conn, where, params, extra, order, searched) if served else None
        if served:
            rows = _rows(conn, where, params, extra, order, pageSize, start, few=few is not None)
            fetched = True
        if few is not None:
            total = few
        elif fetched and len(rows) < pageSize and (rows or start == 0):
            total = start + len(rows)                                # the end of the list was read
        else:
            total, capped = _count(conn, where, params, extra)
    if capped and with_meta is True:
        exact = _snapshot_total(conn, asked)
        if exact is not None:
            total, capped = exact
    if capped and rows:
        # "At least": never fewer than what has been read, and a full page may be followed by another.
        total = max(total, start + len(rows) + (1 if len(rows) >= pageSize else 0))
    from .stats import list_meta  # stats imports this module

    items = _present(conn, rows, checked=with_meta is True)
    if with_meta is True:
        # the account code calls this function directly, as a role that may not read the award tables (see `serves_meta`)
        items = list_item_fields(conn, items)
    return {"items": items, "total": total,
            "totalCapped": capped, "page": page, "pageSize": pageSize, "maxOffset": MAX_OFFSET,
            "asOf": datetime.now(timezone.utc),
            "meta": list_meta(conn, "tender") if with_meta is True else {}, **search_info(q)}


EXPORT_MAX_LIMIT = 2000
EXPORT_DEFAULT_LIMIT = 500


class TenderExportPage(BaseModel):
    items: list[Tender]
    # The cursor of the next call (the id of this call's last row), null when this is the last page.
    nextCursor: str | None = None


def export_sql(where: list[str], limit: int, cursor: int | None) -> tuple[str, int]:
    """The page query of the export: the list's own filters and collapse rules, but keyed on the
    primary key (newest id first) instead of sorted and counted, so a page costs a scan that
    stops after `limit` + 1 rows and never reads the whole result. Returns the SQL and how many
    times the filter parameters repeat in it (the collapse rules carry them three more times)."""
    keyset = " AND o.id < %s" if cursor is not None else ""
    return (f"{TENDER_SELECT} WHERE " + " AND ".join(where) + " AND " + collapse_clauses(where)
            + f"{keyset} ORDER BY o.id DESC LIMIT %s"), 4


@router.get("/v1/tenders/export", response_model=TenderExportPage)
def export_tenders(
    q: str | None = Query(None, max_length=100),
    country: str | None = Query(None, max_length=200),
    cpv: str | None = Query(None, max_length=400),
    status: str = Query("open", pattern=STATUS_PATTERN),
    scope: str = Query("relevant", pattern="^(relevant|core|supply|all)$"),
    goods: str | None = Query(None, pattern="^defence$"),
    buyer: int | None = Query(None, ge=1, le=MAX_BIGINT),
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    min_: float | None = Query(None, alias="min", ge=0, le=1e13),
    max_: float | None = Query(None, alias="max", ge=0, le=1e13),
    currency: str | None = Query(None, pattern="^[A-Za-z]{3}$"),
    cursor: str | None = Query(None, pattern="^[0-9]{1,18}$"),
    limit: int = Query(EXPORT_DEFAULT_LIMIT, ge=1, le=EXPORT_MAX_LIMIT),
    cpvMain: bool = Query(False),
    notCpv: str | None = Query(None, max_length=400),
    publishedFrom: date | None = None,
    publishedTo: date | None = None,
    conn=Depends(get_conn),
):
    """One page of a CSV export: the notices the list would show for the same filters, newest id
    first, `limit` at a time (at most 2,000), with no total (that is the window count that made
    the list too slow for a long result). Call again with `cursor` = `nextCursor` until it is
    null. Rows are read a moment apart: a caller de-duplicates by id. Not cached.

    WP-100: `publishedFrom` / `publishedTo` (inclusive days, UTC) narrow it by publication date, the
    notice date where none is stated (the date the list's "newest published" order reads), so a time
    series can be read a year at a time."""
    where, params, _ = _tender_filters(q, country, cpv, status, scope, goods, buyer, from_,
                                       to, min_, max_, currency, conn=conn, cpv_main=cpvMain, not_cpv=notCpv)
    for bound, op in ((publishedFrom, ">="), (publishedTo, "<=")):
        if bound is not None:
            where.append(f"coalesce(o.published_at, o.notice_date) {op} %s")
            params.append(bound)
    after = int(cursor) if cursor is not None else None
    sql, repeats = export_sql(where, limit, after)
    args = params * repeats + ([after] if after is not None else []) + [limit + 1]
    rows = conn.execute(sql, args).fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": list_item_fields(conn, _present(conn, rows)),
            "nextCursor": str(rows[-1]["id"]) if more and rows else None}


class ScopeCounts(BaseModel):
    relevant: int
    core: int
    supply: int
    # core + supply - relevant: the supply notices that are the national copy of a core notice. The union is
    # shown once (a twin is collapsed when its replacement is in the result), the two lists each count
    # their own, so the three numbers do not add up by exactly this much.
    overlap: int = 0
    # True when a count stopped at `TOTAL_CAP`: the figures are then "at least".
    capped: bool = False
    # When the counts were worked out (a snapshot says when it was made).
    asOf: datetime | None = None


@router.get("/v1/tenders/scope-counts", response_model=ScopeCounts)
@cache_list("tender-scope-counts", ttl=5 * 60, snapshot=_kept_in_snapshot)
def tender_scope_counts(
    q: str | None = Query(None, max_length=100),
    country: str | None = Query(None, max_length=200),
    cpv: str | None = Query(None, max_length=400),
    status: str = Query("open", pattern=STATUS_PATTERN),
    goods: str | None = Query(None, pattern="^defence$"),
    buyer: int | None = Query(None, ge=1, le=MAX_BIGINT),
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    min_: float | None = Query(None, alias="min", ge=0, le=1e13),
    max_: float | None = Query(None, alias="max", ge=0, le=1e13),
    currency: str | None = Query(None, pattern="^[A-Za-z]{3}$"),
    cpvMain: bool = Query(False),
    notCpv: str | None = Query(None, max_length=400),
    conn=Depends(get_conn),
):
    """How many notices the list would show under each scope for the same other filters, with
    the list's own collapse rules, so the counts next to the scope choices are the totals the
    choices lead to (the same predicate, `_count`; `asOf` says when). `all` is not counted: it is not
    a choice the site offers."""
    out: dict[str, Any] = {}
    capped = False
    for scope in ("relevant", "core", "supply"):
        where, params, _ = _tender_filters(q, country, cpv, status, scope, goods, buyer, from_,
                                           to, min_, max_, currency, conn=conn, cpv_main=cpvMain, not_cpv=notCpv)
        out[scope], c = _count(conn, where, params)
        if c and out[scope] == 0:
            # Not even a lower bound in the time allowed (a search word that matches a fifth of the archive,
            # on the closed lists): no numbers is the honest answer, and the site shows the labels without.
            raise HTTPException(503, "the count took too long; narrow the request")
        capped = capped or c
    out["overlap"] = 0 if capped else max(0, out["core"] + out["supply"] - out["relevant"])
    out["capped"] = capped
    out["asOf"] = datetime.now(timezone.utc)
    return out


CALENDAR_LIMIT = 3000


class CalendarItem(BaseModel):
    id: str
    slug: str
    noticeId: str
    title: str
    buyerName: str
    country: str | None
    deadline: datetime
    # True when `deadline` is the TED notice's because the national notice's own is 90 days or more from it.
    deadlineFrom: str | None = None
    scope: str
    status: str
    statusNative: str | None
    anomalies: list[str] = []
    sourceName: str


class CalendarPage(BaseModel):
    items: list[CalendarItem]
    # Every open notice that states a deadline in the range, and whether `items` holds them all.
    total: int
    truncated: bool
    asOf: datetime
    # WP-96: open notices of the same filters that state no deadline, not in `items` (0 with a date range)
    withoutDeadline: int = 0


@router.get("/v1/tenders/calendar", response_model=CalendarPage, dependencies=[Depends(known_params)])
@cache_list("tender-calendar", ttl=5 * 60)
def tender_calendar(
    q: str | None = Query(None, max_length=100),
    country: str | None = Query(None, max_length=200),
    cpv: str | None = Query(None, max_length=400),
    scope: str = Query("relevant", pattern="^(relevant|core|supply|all)$"),
    goods: str | None = Query(None, pattern="^defence$"),
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    min_: float | None = Query(None, alias="min", ge=0, le=1e13),
    max_: float | None = Query(None, alias="max", ge=0, le=1e13),
    currency: str | None = Query(None, pattern="^[A-Za-z]{3}$"),
    maxItems: int = Query(CALENDAR_LIMIT, ge=1, le=CALENDAR_LIMIT),
    cpvMain: bool = Query(False),
    notCpv: str | None = Query(None, max_length=400),
    conn=Depends(get_conn),
):
    """The open notices that state a deadline, soonest first, with nothing but what a calendar draws
    (WP-52, T9). The list endpoint serves 250 notices a page and the calendar read five pages of it: the 500
    earliest of 1,529, so November had no tender. This is the whole range in one answer, in the list's own
    status, scope and collapse rules and with the same deadline the notice's page shows (`shown_deadline`).
    WP-87: the list's own filters (q, country, cpv, scope, goods, dates, value), read by `_tender_filters` as the
    list reads them, so a filtered list and its calendar hold the same notices; any other parameter is a 422."""
    where, params, eff = _tender_filters(q, country, cpv, "open", scope, goods, None, from_, to,
                                         min_, max_, currency, cpv_main=cpvMain, not_cpv=notCpv)
    # WP-96: the open notices of the same filters that state no deadline (a date range holds none of them), so the
    # calendar and its file say how many the list shows and they do not (DE: 57, all of Europe: 76)
    undated = (_count(conn, [*where, "o.deadline_at IS NULL"], params)[0]
               if from_ is None and to is None else 0)
    where.append("o.deadline_at IS NOT NULL")
    rows = _rows(conn, where, params, [], ORDER_OPEN_DEADLINE, maxItems + 1, 0)
    truncated = len(rows) > maxItems
    rows = rows[:maxItems]
    api = _api()
    extras = _twin_extras(conn, rows)
    names = _buyer_names(conn, sorted({r["buyer_org_id"] for r in rows if r.get("buyer_org_id")}))
    items = []
    for r in rows:
        deadline, deadline_from, first_passed = shown_deadline(r["deadline_at"],
                                                               (extras.get(r["id"]) or {}).get("deadline"))
        eff_status = api.effective_status(r.get("status"), deadline, r.get("published_at"),
                                          procedure=r.get("procedure_type"))
        notes = anomalies(deadline, r.get("published_at"))
        if deadline_from:
            notes.append("deadline-differs-from-ted-twin")
        if first_passed:
            notes.append(FIRST_DEADLINE_PASSED)
        if "deadline-more-than-3y" not in notes and deadline > datetime.now(timezone.utc) + timedelta(
                days=TENDER_DEADLINE_HORIZON_DAYS):
            notes.append("deadline-more-than-1y")
        title = redact_emails(r.get("title_en")) or redact_emails(r["title_original"])
        withheld = bool(r.get("buyer_withheld"))
        items.append({
            "id": str(r["id"]), "slug": make_slug(r["id"], title), "noticeId": r["native_id"], "title": title,
            "buyerName": WITHHELD_NAME if withheld else (
                clean_buyer_name(r["buyer_name_raw"]) or names.get(r.get("buyer_org_id")) or ""),
            "country": r.get("country"), "deadline": deadline, "deadlineFrom": deadline_from,
            "scope": api.row_scope(r), "status": "open" if eff_status == "open" else "closed",
            "statusNative": eff_status, "anomalies": notes, "sourceName": r["source_name"],
        })
    total = _count(conn, where, params)[0] if truncated else len(items)
    return {"items": items, "total": total, "truncated": truncated, "asOf": datetime.now(timezone.utc),
            "withoutDeadline": undated}


@router.get("/v1/tenders/slugs")
@cache_list("tender-slugs", ttl=15 * 60, snapshot=True)
def tender_slugs(conn=Depends(get_conn)):
    """The notices a sitemap lists: the open ones and the core ones published in the last year, newest first,
    at most `TENDER_SLUG_LIMIT`. `updatedAt` is when the newest version was observed: the worker works that out
    for the snapshot (3,644 of the 5,000 notices have more than one version, and reading them is 5 s on
    production, the whole of the API's budget); an answer the API works out itself says the publication date,
    which is what the sitemap's last-modified needs to be when the version table is not read (T15)."""
    api = _api()
    since = datetime.now(timezone.utc) - timedelta(days=SLUG_WINDOW_DAYS)
    rows = conn.execute(
        f"""SELECT o.id, COALESCE(o.title_en, o.title_original) AS title, o.published_at, o.current_version
              FROM opportunity o
             WHERE o.is_defence AND NOT o.suppressed AND {api.SCOPE_SQL['core']}
               AND ({api.EFFECTIVE_STATUS_SQL} = 'open' OR o.published_at >= %s)
             ORDER BY o.published_at DESC NULLS LAST, o.id DESC
             LIMIT {TENDER_SLUG_LIMIT}""", (since.date(),)).fetchall()
    seen = _observed(conn, [r["id"] for r in rows if (r["current_version"] or 1) > 1]) if EXACT_TOTALS.get() else {}
    now = datetime.now(timezone.utc)
    return [{"slug": make_slug(r["id"], redact_emails(r["title"]) or ""),
             "updatedAt": seen.get(r["id"]) or _day(r["published_at"]) or now} for r in rows]


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
    if row["suppressed"]:
        raise removed()
    out = _present(conn, [row], checked=True)[0]
    got = conn.execute("SELECT payload->>'description' AS d FROM opportunity_version WHERE opportunity_id = %s "
                       "ORDER BY version DESC LIMIT 1", (tender_id,)).fetchone()
    out["subject"] = commercial_subject(got["d"] if got else None)
    if row["source_code"] in DOCUMENTS_SOURCES:
        out["documentsUrl"] = out["source"]["url"]
    else:
        out["documentsUrl"] = next((t["url"] for t in out["sameNotice"] if t["source"] in DOCUMENTS_SOURCES
                                    and t["url"]), None)
    out.update(awarded(conn, [tender_id] + [int(t["id"]) for t in out["sameNotice"]]))
    out["stages"] = procedure_stages(conn, tender_id, [int(t["id"]) for t in out["sameNotice"]])
    out["cpvTitles"] = cpv_titles(out["cpvCodes"])
    return out


def awarded(conn, ids: list[int]) -> dict[str, Any]:
    """WP-95 (persona round of 23 October 2026, A1.2): who the award notice names, on its own page. The winners of the
    notice and of its other publications (`sameNotice`) that are legal entities (`award_set.WINNERS`: not removed, not a
    natural person, not a placeholder, not superseded), each once, with a link to their supplier page where the
    supplier map lists them (`award_set.scope`), and the persons counted. The value: the notice's own (TED, with its
    kind), else the one winner's.
    WP-103: `winnersRead` says whether any of the notices was read for its winners at all (an `award_notice` row): an
    award page with no winner names says "not read yet" rather than nothing (728479-2026, persona p04); and a figure the
    notice states but its own estimate contradicts is given apart (`awardValue.setAside`, `award_value.contradicted`)."""
    rows = conn.execute(
        f"""SELECT DISTINCT ON (org.id) org.id, a.name_as_stated, a.supplier_country, a.value_amount, a.value_currency,
                   a.value_kind
              FROM award a JOIN opportunity o ON o.id = a.opportunity_id
              JOIN organisation raw_org ON raw_org.id = a.organisation_id
              JOIN organisation org ON org.id = COALESCE(raw_org.merged_into, raw_org.id)
             WHERE a.opportunity_id = ANY(%s) AND NOT o.suppressed AND {award_set.WINNERS}
             ORDER BY org.id, (a.opportunity_id = %s) DESC, a.value_amount IS NULL, a.id""", (ids, ids[0])).fetchall()
    notice = conn.execute(
        """SELECT COALESCE(max(skipped_person), 0) AS persons,
                  (array_agg(value_amount ORDER BY opportunity_id = %s DESC) FILTER (WHERE value_kind IS NOT NULL))[1] AS va,
                  (array_agg(value_currency ORDER BY opportunity_id = %s DESC) FILTER (WHERE value_kind IS NOT NULL))[1] AS vc,
                  (array_agg(value_kind ORDER BY opportunity_id = %s DESC) FILTER (WHERE value_kind IS NOT NULL))[1] AS vk,
                  (array_agg(value_set_aside ORDER BY opportunity_id = %s DESC)
                       FILTER (WHERE value_kind IS NOT NULL))[1] AS sa,
                  count(*) AS read
             FROM award_notice WHERE opportunity_id = ANY(%s)""", (ids[0], ids[0], ids[0], ids[0], ids)).fetchone()
    paged: set[int] = set()
    if rows:
        paged = {r["id"] for r in conn.execute(
            f"SELECT DISTINCT org.id {award_set.FROM} WHERE {award_set.scope()} AND org.id = ANY(%(orgs)s)",
            {"since": award_set.since(), "orgs": [r["id"] for r in rows]}).fetchall()}
    winners = []
    for r in sorted(rows, key=lambda r: (r["name_as_stated"] or "").lower()):
        name = redact_emails(r["name_as_stated"]).strip()
        has_value = r["value_amount"] is not None and r["value_amount"] > PLACEHOLDER_VALUE_MAX and r["value_currency"]
        winners.append({"name": name, "slug": make_slug(r["id"], name) if r["id"] in paged else None,
                        "country": r["supplier_country"],
                        "valueAmount": float(r["value_amount"]) if has_value else None,
                        "valueCurrency": r["value_currency"].strip() if has_value else None,
                        "valueKind": (r["value_kind"] or "contract") if has_value else None})
    value = None
    if notice and notice["vk"] and notice["va"] is not None and notice["va"] > PLACEHOLDER_VALUE_MAX and notice["vc"]:
        value = {"amount": float(notice["va"]), "currency": notice["vc"].strip(), "kind": notice["vk"],
                 "setAside": float(notice["sa"]) if notice["sa"] is not None else None}
    elif len(winners) == 1 and winners[0]["valueAmount"] is not None and not (notice and notice["persons"]):
        value = {"amount": winners[0]["valueAmount"], "currency": winners[0]["valueCurrency"],
                 "kind": winners[0]["valueKind"]}
    return {"awardedTo": winners, "awardedPersons": int(notice["persons"]) if notice else 0, "awardValue": value,
            "winnersRead": bool(notice and notice["read"])}


# ------------------------------------------------------------------ WP-106: list items, procedure stages

STAGES_LIMIT = 10


def procedure_stages(conn, tender_id: int, same: list[int]) -> list[dict[str, Any]]:
    """WP-106 (p06: the call 121371 did not lead to its award 130826): the other notices of the notice's procedure (the same
    eForms procedure identifier), defence and not removed, its own copies in other sources (`same`) left out, oldest first."""
    rows = conn.execute(
        """SELECT r.id, r.native_id, COALESCE(r.title_en, r.title_original) AS title, r.status, r.published_at
             FROM opportunity o
             JOIN opportunity r ON r.procedure_identifier = o.procedure_identifier AND r.id <> o.id
            WHERE o.id = %s AND o.procedure_identifier IS NOT NULL AND r.is_defence AND NOT r.suppressed
              AND r.id <> ALL(%s::bigint[])
            ORDER BY COALESCE(r.published_at, r.notice_date) NULLS LAST, r.id
            LIMIT %s""", (tender_id, same, STAGES_LIMIT)).fetchall()
    return [{"id": str(r["id"]), "slug": make_slug(r["id"], redact_emails(r["title"]) or ""), "noticeId": r["native_id"],
             "status": r["status"], "publishedAt": _day(r["published_at"])} for r in rows]


def award_summaries(conn, keys: dict[int, list[int]]) -> dict[int, dict[str, Any]]:
    """WP-106: what `awarded` gives one notice's page, for a whole list in four queries: for each key (a notice of the list),
    the winners and the value of the notices of `keys[key]` (the notice and its copies in other sources). The same rules
    as `awarded` (a test holds the two equal): legal entities only, each once, persons counted; the value the award notice
    states with its kind, else the one winner's."""
    pairs = [(k, i) for k, ids in keys.items() for i in dict.fromkeys([k, *ids])]
    if not pairs:
        return {}
    ks, oids = [p[0] for p in pairs], [p[1] for p in pairs]
    rows = conn.execute(
        f"""SELECT DISTINCT ON (x.key, org.id) x.key, org.id, a.name_as_stated, a.supplier_country, a.value_amount,
                   a.value_currency, a.value_kind
              FROM unnest(%s::bigint[], %s::bigint[]) AS x(key, oid)
              JOIN award a ON a.opportunity_id = x.oid
              JOIN opportunity o ON o.id = a.opportunity_id
              JOIN organisation raw_org ON raw_org.id = a.organisation_id
              JOIN organisation org ON org.id = COALESCE(raw_org.merged_into, raw_org.id)
             WHERE NOT o.suppressed AND {award_set.WINNERS}
             ORDER BY x.key, org.id, (a.opportunity_id = x.key) DESC, a.value_amount IS NULL, a.id""", (ks, oids)).fetchall()
    notices = {r["key"]: r for r in conn.execute(
        """SELECT x.key, COALESCE(max(n.skipped_person), 0) AS persons,
                  (array_agg(n.value_amount ORDER BY n.opportunity_id = x.key DESC) FILTER (WHERE n.value_kind IS NOT NULL))[1] AS va,
                  (array_agg(n.value_currency ORDER BY n.opportunity_id = x.key DESC) FILTER (WHERE n.value_kind IS NOT NULL))[1] AS vc,
                  (array_agg(n.value_kind ORDER BY n.opportunity_id = x.key DESC) FILTER (WHERE n.value_kind IS NOT NULL))[1] AS vk,
                  (array_agg(n.value_set_aside ORDER BY n.opportunity_id = x.key DESC)
                       FILTER (WHERE n.value_kind IS NOT NULL))[1] AS sa
             FROM unnest(%s::bigint[], %s::bigint[]) AS x(key, oid)
             JOIN award_notice n ON n.opportunity_id = x.oid
            GROUP BY x.key""", (ks, oids)).fetchall()}
    paged: set[int] = set()
    if rows:
        paged = {r["id"] for r in conn.execute(
            f"SELECT DISTINCT org.id {award_set.FROM} WHERE {award_set.scope()} AND org.id = ANY(%(orgs)s)",
            {"since": award_set.since(), "orgs": sorted({r["id"] for r in rows})}).fetchall()}
    by_key: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        by_key.setdefault(r["key"], []).append(r)
    out: dict[int, dict[str, Any]] = {}
    for key in keys:
        winners = []
        for r in sorted(by_key.get(key, []), key=lambda r: (r["name_as_stated"] or "").lower()):
            name = redact_emails(r["name_as_stated"]).strip()
            has_value = r["value_amount"] is not None and r["value_amount"] > PLACEHOLDER_VALUE_MAX and r["value_currency"]
            winners.append({"name": name, "slug": make_slug(r["id"], name) if r["id"] in paged else None,
                            "country": r["supplier_country"],
                            "valueAmount": float(r["value_amount"]) if has_value else None,
                            "valueCurrency": r["value_currency"].strip() if has_value else None,
                            "valueKind": (r["value_kind"] or "contract") if has_value else None})
        n = notices.get(key)
        persons = int(n["persons"]) if n else 0
        value = None
        if n and n["vk"] and n["va"] is not None and n["va"] > PLACEHOLDER_VALUE_MAX and n["vc"]:
            value = {"amount": float(n["va"]), "currency": n["vc"].strip(), "kind": n["vk"],
                     "setAside": float(n["sa"]) if n["sa"] is not None else None}
        elif len(winners) == 1 and winners[0]["valueAmount"] is not None and not persons:
            value = {"amount": winners[0]["valueAmount"], "currency": winners[0]["valueCurrency"],
                     "kind": winners[0]["valueKind"]}
        # WP-103 fields as `awarded` gives them (the test holds the two equal)
        out[key] = {"awardedTo": winners, "awardedPersons": persons, "awardValue": value, "winnersRead": n is not None}
    return out


def latest_descriptions(conn, ids: list[int]) -> dict[int, str | None]:
    """The description of each notice's newest version (what `get_tender` reads for its subject), for a page at once."""
    if not ids:
        return {}
    return {r["opportunity_id"]: r["d"] for r in conn.execute(
        "SELECT DISTINCT ON (opportunity_id) opportunity_id, payload->>'description' AS d FROM opportunity_version "
        "WHERE opportunity_id = ANY(%s) ORDER BY opportunity_id, version DESC", (ids,)).fetchall()}


def list_item_fields(conn, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """WP-106 (p03, p06, p07): what a list item and an export row carry beyond `_present`: the subject in the notice's own
    words (BAAINBw titles are internal numbers) and, for an award, its winners and its value with the value's kind, so a
    list says "Awarded to ..." and "Framework ceiling" instead of "Estimated value"."""
    if not items:
        return items
    ids = [int(t["id"]) for t in items]
    awards = award_summaries(conn, {int(t["id"]): [int(s["id"]) for s in t["sameNotice"]] for t in items})
    texts = latest_descriptions(conn, ids)
    for t in items:
        t.update(awards.get(int(t["id"]), {}))
        t["subject"] = commercial_subject(texts.get(int(t["id"])))
        t["cpvTitles"] = cpv_titles([t["cpv"]] if t.get("cpv") else [])
    return items


@lru_cache(maxsize=1)
def _vocabulary() -> dict[str, str]:
    return json.loads(cpv_labels.DATA.read_text(encoding="utf-8"))["codes"]


def cpv_titles(codes: list[str]) -> dict[str, str]:
    """WP-106 (p03, p04: 34330000 and 24615000 had no name): the official English titles of these codes, from the full
    CPV 2008 vocabulary the search reads (`cpv_labels.DATA`); a code it does not hold is left out."""
    vocabulary = _vocabulary()
    return {c: vocabulary[c] for c in codes if c in vocabulary}


# The sources whose notice link is the address of the procurement documents (BT-15): de_bkms (WP-72).
DOCUMENTS_SOURCES = ("de_bkms",)
SUBJECT_MAX = 300
# What a commercial subject leaves out (docs/CLAUDE.md: commercial market intelligence only, no technical
# specification or performance, no personal data): a figure with a physical unit, the words of a specification, and
# anything that reads as a contact. Such a description is not shown at all, rather than cut into a half sentence.
_TECHNICAL = re.compile(
    r"\d\s*(?:mm|cm|km|kg|kn|kw|mw|kv|hz|khz|mhz|ghz|db|dbm|°|bar|psi|rpm|km/h|m/s|nm|µm|ml|kwh|w|v|m|g|t|l)\b"
    r"|\b(?:specifications?|performance|tolerances?|accuracy|wavelength|frequenc(?:y|ies)|calibre|caliber|mil-std|"
    r"stanag|technische|spezifikation|leistungsbeschreibung|especificaciones|prescriptions techniques)\b",
    re.IGNORECASE)
_CONTACT = re.compile(r"@|\b(?:tel|phone|telefon|tél|tfno|contact|kontakt|contacto)\b|\+?\d[\d\s()/.-]{7,}\d",
                      re.IGNORECASE)


# WP-106: a run of seven or more digits standing alone is a stock, order or part number (the NATO stock number of a
# BAAINBw part, 2520410039852): taken out of the subject, which then reads (it made the whole subject a "contact" before).
# Taking it out also takes out any phone number written as one run of digits.
_LONG_NUMBER = re.compile(r"(?<![\w+(])\d{7,}(?![\d)])-?")
_INTERNATIONAL_PHONE = re.compile(r"\+\s?\d")
# WP-106 (p02, 269322): a description that only says what a notice changed ("Modification de la date limite de réception
# des offres") is not the subject.
_CHANGE_TEXT = re.compile(
    r"^(?:modification|rectificatif|avis rectificatif|report de la date|prolongation|corrigendum|change of|amendment|"
    r"extension of|änderung|berichtigung|verlängerung|modificaci[oó]n|correcci[oó]n|ampliaci[oó]n del plazo|rettifica|"
    r"proroga|wijziging|rectificatie|zmiana|sprostowanie|korekta)\b", re.IGNORECASE)


def commercial_subject(text: str | None) -> str | None:
    """The first sentence of a notice's description, at most SUBJECT_MAX characters (cut at a word), or None when
    there is none, it reads as a specification or a contact (`_TECHNICAL`, `_CONTACT`), or it only says what a notice
    changed (`_CHANGE_TEXT`). Long digit runs (`_LONG_NUMBER`) are taken out first."""
    raw = redact_emails(text) or ""
    if _INTERNATIONAL_PHONE.search(raw):
        return None
    clean = re.sub(r"\s+", " ", _LONG_NUMBER.sub(" ", raw)).strip(" ,;:-–")
    if not clean or _CHANGE_TEXT.match(clean):
        return None
    first = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9])", clean, maxsplit=1)[0]
    if _TECHNICAL.search(first) or _CONTACT.search(first) or "[" in first:
        return None
    if len(first) > SUBJECT_MAX:
        first = first[:SUBJECT_MAX].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return first


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
# `history` is a real state that the publisher did change, seen late: it stays in the
# timeline (and is the baseline of the next change) but is marked, and no count of
# amendments includes it.
HISTORIC_KIND = "history"


def link_host(value: Any) -> str | None:
    """The site a source link points at, for a line a reader can understand."""
    text = str(value or "").strip()
    host = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text, flags=re.I).split("/", 1)[0].split("?", 1)[0]
    host = host.lower().removeprefix("www.")
    return host or None

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


def _fold_remap(out: list[dict[str, Any]], before: dict[str, Any], after: dict[str, Any],
                changed: list[str]) -> None:
    """A `remapped` version is our own corrected reading of a payload we already had: the publisher
    amended nothing, so it is not listed. But a line that an earlier entry drew from the old reading
    (notice 235: "Status changed from Open to Awarded", when the corrected reading is Cancelled, and the
    publication date the feed stamp had moved) would then contradict the notice's headline. The line is
    corrected where it stands: its `after` becomes the corrected value; a line that now says nothing is
    removed, and an entry left with no line, or only the publication date, goes with it (WP-52, T12)."""
    for field in changed:
        if field not in FIELD_LABELS or field == "source_url" or same_value(field, before.get(field), after.get(field)):
            continue
        for entry in reversed(out):
            line = next((c for c in entry["changes"] if c["field"] == field), None)
            if line is None:
                continue
            code = after.get("value_currency") or before.get("value_currency")
            line["after"] = _human(field, after.get(field), code)
            if line["before"] == line["after"]:
                entry["changes"].remove(line)
            break
    out[:] = [e for e in out if e["version"] == out[0]["version"]
              or any(c["field"] != "published_at" for c in e["changes"])]


def timeline(rows: list[dict[str, Any]], *, corrections: bool = False) -> list[dict[str, Any]]:
    """The amendments of one notice, oldest first, from its version rows in order.

    The first version is the notice as first seen. A later version is listed only if it
    changed something a reader can see, and the archive being append-only, the noise
    is filtered here and not there:

      - a line whose two sides render the same is dropped (66 on 12 October 2026: CPV
        re-ordered, the same deadline written with another UTC offset)
      - a version left with no line, or only the publication date, is not an amendment:
        1,292 of 1,693 were the PLACSP feed stamp moving

    A `remapped` version (our own corrected reading) is never an amendment. For the counts
    (`corrections` False) it is folded into the line it corrects (`_fold_remap`, WP-52 T12).
    For the version history a reader sees (`corrections` True) it is an entry of its own,
    dated when we re-read the notice and marked `correction`, so that every state the archive
    holds is shown and no change is dated before it was observed (re-audit of the data pages,
    NEW-1: notice 235 dated its cancellation of 15 Oct on 30 Sep and lost the Awarded state;
    notice 6 hid the deadline it corrected on 12 Oct).
    """
    out: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for r in rows:
        kinds = set(r.get("kinds") or [])
        if kinds & SKIPPED_KINDS:
            continue
        payload = r["payload"] or {}
        remapped = REMAPPED_KIND in kinds
        if previous is None:
            out.append({"version": r["version"], "detectedAt": r["observed_at"],
                        "historic": HISTORIC_KIND in kinds, "correction": False, "changes": []})
        elif remapped and not corrections:
            _fold_remap(out, previous, payload, r["changed_fields"] or [])
        else:
            changes = []
            for field in r["changed_fields"] or []:
                if field not in FIELD_LABELS:
                    continue
                before, after = previous.get(field), payload.get(field)
                if same_value(field, before, after):
                    continue
                if field == "source_url":
                    # A new address on the same site (the publisher's own identifier in the
                    # path) is not a change a reader can use; a move to another site is,
                    # and says which, not the two addresses.
                    host_before, host_after = link_host(before), link_host(after)
                    if host_before == host_after:
                        continue
                    changes.append({"field": field, "label": FIELD_LABELS[field],
                                    "before": host_before, "after": host_after})
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
                            "historic": HISTORIC_KIND in kinds, "correction": remapped,
                            "changes": changes})
        previous = payload
    for number, entry in enumerate(out, 1):
        entry["sequence"] = number
    return out


@router.get("/v1/tenders/{slug}/versions", response_model=list[TenderVersion])
def tender_versions(slug: str, conn=Depends(get_conn)):
    tender_id = _id_of(slug, "tender")
    held = conn.execute("SELECT suppressed, buyer_withheld FROM opportunity "
                        "WHERE id = %s AND is_defence", (tender_id,)).fetchone()
    if not held:
        raise HTTPException(404, "no such tender")
    if held["suppressed"]:
        raise removed()
    rows = conn.execute(TIMELINE_SQL.format(where="v.opportunity_id = %s"),
                        (tender_id,)).fetchall()
    out = list(reversed(timeline(rows, corrections=True)))
    if held["buyer_withheld"]:      # a line about the buyer's name would say the name
        for entry in out:
            entry["changes"] = [c for c in entry["changes"] if c["field"] != "buyer_name_raw"]
    return out


# ----------------------------------------------------------------- buyers

AGGREGATE = f"""
    SELECT o.buyer_org_id AS org_id, count(*) AS n,
           count(*) FILTER (WHERE {{eff}} = 'open') AS open_n,
           max(o.published_at) AS last_published
      FROM opportunity o
     WHERE o.is_defence AND NOT o.suppressed AND NOT o.buyer_withheld
       AND {CORE} AND o.buyer_org_id IS NOT NULL
     GROUP BY o.buyer_org_id
"""  # not used since the family aggregate (WP-22); see DELETION_CANDIDATES.md


def aggregate_sql(*, exact: bool = False) -> str:
    """The buyer aggregate (`org_id`, `n`, `open_n`, `last_published`, `variants`), one row
    per ORGANISATION (WP-111): `family_base` adds the rows of a family up when it is read, so a family the
    worker's stored aggregate predates is counted whole (p07, 24 October 2026: the members merged into Direzione degli
    Armamenti Terrestri after the stored aggregate left it at 177 notices last published 31.01.2024, where its page,
    read live, said 435 with 28 of 2026). `open_n` and `variants` are 0 here: both are read live (`buyer_base`).

    `open_n` is counted as the buyer's own list counts it: the same scope (WP-96: relevant, the list default; it was core) and collapse (a national
    notice and its TED twin, a rectificatif and its parent, a re-publication: one each), so it equals
    `/v1/tenders?buyer=&status=open&scope=relevant` (the default). `n`, with `exact=True`, is counted the same way, and equals
    `status=all`: the 3,329 the list shows for the largest buyer, where the plain count said 5,366 (WP-52, T14).
    The collapse is tested for each of the 68,000 core notices, which is 8 s on an idle server and over 30 s
    on a busy one: the worker runs it (`ops/warm_lists`, stored as `list_snapshot` key `buyer-base`) and the
    API reads that. Without a stored result the API runs the plain count (`exact=False`: 1.2 to 2 s, every core
    notice once, a twin counted twice), which is what it always did. The family is a LEFT JOIN to a table of
    some hundreds of rows, so the scan stays as it was. A notice and its twin under two members of one family are
    counted once (the collapse reads the families of the time it runs): per organisation, the twin that stays is
    counted under its own row."""
    return f"""
    SELECT t.org_id, t.n, 0::bigint AS open_n, t.last_published, 0::bigint AS variants
      FROM ({_totals_sql(exact)}) t
    """


def _core_where() -> list[str]:
    """The notices a buyer's counts are of. WP-96: the tender list's default scope, `relevant` (All defence: military
    goods and works and the other purchases of armed forces), so "Open now" on a buyer page is what the list shows for
    the buyer (NL Ministry of Defence: 5 against the list's 27, all its transport, catering and storage tenders were
    left out). The buyer page counts the military goods and works among the open ones apart (`get_buyer`)."""
    return ["o.is_defence = TRUE", "NOT o.suppressed", "NOT o.buyer_withheld", _api().SCOPE_SQL["relevant"],
            "o.buyer_org_id IS NOT NULL"]


# Counted per organisation first (a plain column, whose statistics give the planner the right number of
# groups: a few thousand), then per family. Grouping by the COALESCE directly made it expect 220,000 groups
# and join them to `organisation` by a hash.
_FAMILY = "LEFT JOIN buyer_family_member m ON m.org_id = x.org_id"
_FAMILY_O = "LEFT JOIN buyer_family_member m ON m.org_id = o.buyer_org_id"


def _totals_sql(exact: bool = False) -> str:
    base = _core_where()
    collapse = f" AND {collapse_clauses(base, same_buyer=True)}" if exact else ""
    return f"""
    SELECT o.buyer_org_id AS org_id, count(*)::bigint AS n, max(o.published_at) AS last_published
      FROM opportunity o
     WHERE {" AND ".join(base)}{collapse}
     GROUP BY o.buyer_org_id"""


def _open_sql() -> str:
    opened = [*_core_where(), f"{_api().EFFECTIVE_STATUS_SQL} = 'open'"]
    return f"""
    SELECT COALESCE(m.head_org_id, x.org_id) AS org_id, sum(x.n)::bigint AS open_n
      FROM (SELECT o.buyer_org_id AS org_id, count(*) AS n
              FROM opportunity o
             WHERE {" AND ".join(opened)} AND {collapse_clauses(opened, same_buyer=True)}
             GROUP BY o.buyer_org_id) x
      {_FAMILY}
     GROUP BY COALESCE(m.head_org_id, x.org_id)"""


def _buyer(r: dict[str, Any], names: dict[int, str]) -> dict[str, Any]:
    name = names.get(r["id"]) or clean_buyer_name(r["canonical_name"])
    return {
        "id": str(r["id"]), "slug": make_slug(r["id"], name), "name": name,
        "country": (r.get("country") or None),
        "tenderCount": r["n"], "openCount": r["open_n"],
        "lastPublishedAt": _day(r.get("last_published")),
        "isDefenceBuyer": bool(r.get("is_defence_buyer")),
        "nameVariants": int(r.get("variants") or 0),
    }


BUYER_BASE_SECONDS = 5 * 60
# The aggregate as a table the filters can read: its rows travel as arrays, in this order and with these types.
_BASE_TYPES = ("bigint", "bigint", "bigint", "date", "bigint")
_BASE_FROM = ("SELECT t.org_id, t.n, t.open_n, t.last_published, t.variants FROM unnest("
              + ", ".join(f"%s::{t}[]" for t in _BASE_TYPES)
              + ") AS t(org_id, n, open_n, last_published, variants)")


BASE_COLUMNS = ("org_id", "n", "open_n", "last_published", "variants")
BUYER_BASE_KEY = "buyer-base"


def compute_buyer_base(conn, *, exact: bool = False) -> list[list[Any]]:
    """The aggregate, run: five columns of values (`_BASE_TYPES`). With `exact` (the worker, which stores it:
    `ops/warm_lists`) the totals are the list's own counts, and take seconds."""
    rows = conn.execute(aggregate_sql(exact=True) if exact else aggregate_sql()).fetchall()
    return [[r[k] for r in rows] for k in BASE_COLUMNS]


def _stored_buyer_base(conn) -> list[list[Any]] | None:
    """The aggregate as the worker stored it (`list_snapshot`, at most `SNAPSHOT_HOURS` old), or None."""
    from .listcache import SNAPSHOT_HOURS, restored

    try:
        with conn.transaction():        # a savepoint: a role that may not read the table loses nothing else
            row = conn.execute("SELECT body FROM list_snapshot WHERE key = %s "
                               "AND computed_at > now() - make_interval(hours => %s)",
                               (BUYER_BASE_KEY, SNAPSHOT_HOURS)).fetchone()
    except Exception:  # noqa: BLE001 - a snapshot is a shortcut, never a failure
        return None
    cols = restored(row["body"]) if row else None
    if not isinstance(cols, list) or len(cols) != len(BASE_COLUMNS):
        return None
    cols[3] = [date.fromisoformat(d) if isinstance(d, str) else d for d in cols[3]]
    return cols


def family_base(conn, cols: list[list[Any]]) -> list[list[Any]]:
    """WP-111: the per-organisation aggregate (`aggregate_sql`) as one row per buyer family of NOW (`buyer_family_member`,
    some thousand rows): the notices added up, the last publication the newest of any member, the variants the members
    counted. The open counts are read live per family (a few thousand notices: the totals move slowly, the open set by
    the hour), so "Open now" is the list's own count. A stored aggregate of the old shape (one row per family of its
    day) is grouped the same way: a family made after it is still counted whole. The list and the buyer page read this
    one result, so they say one number and one date for a family whatever was merged since the worker's last run."""
    head_of = {r["org_id"]: r["head_org_id"] for r in conn.execute(
        "SELECT org_id, head_org_id FROM buyer_family_member").fetchall()}
    totals: dict[int, list[Any]] = {}
    for org, n, last in zip(cols[0], cols[1], cols[3], strict=True):
        head = head_of.get(org, org)
        t = totals.setdefault(head, [0, None])
        t[0] += n or 0
        if last is not None and (t[1] is None or last > t[1]):
            t[1] = last
    variants: dict[int, int] = defaultdict(int)
    for head in head_of.values():
        variants[head] += 1
    live = {r["org_id"]: r["open_n"] for r in conn.execute(_open_sql()).fetchall()}
    heads = sorted(totals)
    return [heads, [totals[h][0] for h in heads], [live.get(h, 0) for h in heads], [totals[h][1] for h in heads],
            [variants.get(h, 0) for h in heads]]


# WP-111 (p04): a family is a defence body when any of its rows is one: Agencja Uzbrojenia's flagged row has no notice of its
# own, and the family's head ("Skarb Panstwa - Agencja Uzbrojenia") carried no badge though RBLog's did.
def family_defence(alias: str) -> str:
    return (f"({alias}.is_defence_buyer OR EXISTS (SELECT 1 FROM buyer_family_member fm JOIN organisation mo "
            f"ON mo.id = fm.org_id WHERE fm.head_org_id = {alias}.id AND mo.is_defence_buyer))")


def buyer_base(conn) -> list[list[Any]]:
    """The buyer aggregate, as five columns of values (`_BASE_TYPES`). It does not depend on any filter of the
    list (they run over its rows afterwards), but it reads every core notice and tests the list's collapse
    rules on each (seconds), and used to be run again for every distinct filter: `/v1/buyers?country=PL` took 5 s
    cold. So the worker computes it (`list_snapshot`, key `buyer-base`, renewed every 4 hours with the other
    snapshots) and the API reads that; with none it runs the query itself. Kept for `BUYER_BASE_SECONDS` in memory,
    one computation shared by the callers that arrive meanwhile; a failure is not kept. The filters, the order
    and the page run over the cached rows, as arrays in the same SQL."""
    from . import stats
    from .config import settings

    def compute() -> list[list[Any]]:
        stored = _stored_buyer_base(conn)
        return family_base(conn, compute_buyer_base(conn) if stored is None else stored)

    if settings().list_cache_seconds <= 0:          # 0 turns the list caches off, this one too
        return compute()
    return stats.cached(("buyer-base",), compute, BUYER_BASE_SECONDS, store=stats._list_cache, limit=stats.LIST_CACHED)


# WP-98b: the time the collapsed count under the codes may take before the plain one is given (the list's budget is 5 s; the
# plain count is the WP-89 step's own 0.06 s). Measured on a synthetic archive of production's size: 0.3 s (343) to 1.1 s (35).
UNDER_CODES_MS = 2500


def under_codes(conn, prefixes: list[str]) -> tuple[dict[int, int], bool]:
    """WP-98b (p02): per buyer family, its counted notices (`_core_where`) under the codes, each once as the list shows it (a
    national notice and its TED twin, a rectificatif and its parent, a re-publication: the collapse rules over the same filters,
    of the same family), and True. The collapse is tested on every notice under the codes (a second for the whole of division
    35); past UNDER_CODES_MS the plain count is given instead, and False: a notice and its copy may then count twice."""
    w = [*_core_where(), CPV_HEADS]
    head = (f"SELECT COALESCE(m.head_org_id, o.buyer_org_id) AS id, count(*) AS n FROM opportunity o {_FAMILY_O} "
            f"WHERE {' AND '.join(w)}")
    budget = conn.execute("SELECT current_setting('statement_timeout') AS t").fetchone()["t"]
    try:
        with conn.transaction():       # a savepoint: a cancelled statement loses nothing else, and its timeout goes with it
            conn.execute("SELECT set_config('statement_timeout', %s, true)", (f"{UNDER_CODES_MS}ms",))
            rows = conn.execute(f"{head} AND {collapse_clauses(w, same_buyer=True)} GROUP BY 1", (prefixes,) * 4).fetchall()
            conn.execute("SELECT set_config('statement_timeout', %s, true)", (budget,))
        return {r["id"]: r["n"] for r in rows}, True
    except psycopg.errors.QueryCanceled:
        return {r["id"]: r["n"] for r in conn.execute(f"{head} GROUP BY 1", (prefixes,)).fetchall()}, False


@router.get("/v1/buyers", response_model=BuyerPage)
@cache_list("buyers", ttl=5 * 60)
def list_buyers(
    q: str | None = Query(None, max_length=100),
    country: str | None = Query(None, max_length=200),
    hasOpen: bool = False,
    sort: str = Query("tenders", pattern="^(tenders|name|cpv)$"),
    page: int = Query(1, ge=1, le=1000),
    pageSize: int = Query(20, ge=1, le=100),
    cpv: str | None = Query(None, max_length=200),
    conn=Depends(get_conn),
):
    agg = _BASE_FROM
    base_args = buyer_base(conn)
    where: list[str] = []
    params: list[Any] = []
    text = (q or "").replace("\x00", "").strip()
    words = search_words(text)
    if words:
        # The normalised name (accents folded, lower case): the 281,000 aliases are
        # not searched, which made a name search take seconds. Folded again by `dg_fold`
        # (migration 0054) so that "Ausrüstung" finds "ausrustung"; each word must begin
        # a word.
        # A family is found by the name of any of its members as well as by its head's.
        def named(ws: list[str] | tuple[str, ...]) -> str:
            like = " AND ".join(["dg_fold({c}) LIKE dg_word_pattern(%s)"] * len(ws))
            params.extend([*ws, *ws])
            return (f"(({like.format(c='org.canonical_name')}) OR org.id IN ("
                    "SELECT fm.head_org_id FROM buyer_family_member fm "
                    f"JOIN organisation mo ON mo.id = fm.org_id WHERE {like.format(c='mo.canonical_name')}))")

        # WP-98: an abbreviation (BAAINBw, DMO, DGA, JAE MALE: `search_terms`) also finds the family by its full name
        full = buyer_names(text)
        if full:
            # The families named in full are found first, on their own, by the trigram index of migration 0111 (as a
            # condition of the list's query each name cost 0.5 s more on the synthetic archive)
            names = " OR ".join("(" + " AND ".join(["dg_fold(o.canonical_name) LIKE dg_word_pattern(%s)"] * len(n)) + ")"
                                for n in full)
            heads = [r["id"] for r in conn.execute(
                "SELECT DISTINCT COALESCE(fm.head_org_id, o.id) AS id FROM organisation o "
                f"LEFT JOIN buyer_family_member fm ON fm.org_id = o.id WHERE {names}",
                [w for n in full for w in n]).fetchall()]
            where.append(f"({named(words)} OR org.id = ANY(%s))")
            params.append(heads)
            first, first_params = "(org.id = ANY(%s))", [heads]
        else:
            where.append(named(words))
            first, first_params = "(dg_fold(org.canonical_name) = dg_fold(%s))", [text]
    countries = _split(country, "country", upper=True, max_length=2)
    if countries:
        where.append("org.country = ANY(%s)")
        params.append(countries)
    if hasOpen:
        where.append("org.open_n > 0")
    prefixes = cpv_prefixes(cpv)
    under: dict[int, int] = {}
    collapsed = True
    if prefixes:
        # WP-89: the buyers (families) with at least one of their counted notices (the core scope the counts are of)
        # under one of the codes; the counts stay all of their notices. The families are read first, on their own
        # (0.06 s over the GIN index on production): as a semi-join inside the list's query the planner ran it past
        # the 5 s statement timeout on 23 October 2026.
        # WP-98b: with how many of them each (`cpvCount`, and the order `sort=cpv`).
        under, collapsed = under_codes(conn, prefixes)
        where.append("org.id = ANY(%s)")
        params.append(list(under))
    # WP-98b: most notices under the codes first (without codes, `cpv` is the default order)
    by_cpv = sort == "cpv" and bool(prefixes)
    # The aggregate and its join to `organisation` are computed first, each as a step of its
    # own (MATERIALIZED), and the filters run over the few thousand families that come out:
    # `?q=de` timed out at 5 s on 16 October 2026 because the name filter was run over all
    # 300,000 organisations before the join. The planner expects 60,000 families, so it would
    # do that again if it were allowed to push the filter down, and read all 350,000 organisations
    # to join them (the ANY over the aggregate's ids makes that an index lookup of each).
    with_a = ("WITH a AS MATERIALIZED (" + agg + "), org AS MATERIALIZED ("
              f"SELECT o.id, o.canonical_name, o.country, {family_defence('o')} AS is_defence_buyer, a.n, a.open_n, "
              "a.last_published, a.variants FROM a JOIN organisation o ON o.id = a.org_id "
              "WHERE o.id = ANY(ARRAY(SELECT org_id FROM a))) ")
    base = "FROM org" + ((" WHERE " + " AND ".join(where)) if where else "")
    order = "org.canonical_name, org.id" if sort == "name" else "org.n DESC, org.id"
    order_params: list[Any] = []
    if by_cpv:
        order = "u.n DESC, org.n DESC, org.id"
        base = base.replace("FROM org", "FROM org JOIN unnest(%s::bigint[], %s::bigint[]) AS u(id, n) ON u.id = org.id", 1)
        params = [list(under), list(under.values()), *params]
    elif words and sort != "name":
        # WP-98: the buyer the words name comes first: the family an abbreviation stands for, else a name that is the
        # search itself ("Ministère de la Défense"), then the rest, most tenders first
        order, order_params = f"{first} DESC, {order}", first_params
    rows = conn.execute(
        f"""{with_a}SELECT org.id, org.canonical_name, org.country, org.is_defence_buyer,
                   org.n, org.open_n, org.last_published, org.variants,
                   count(*) OVER () AS total_rows {base}
             ORDER BY {order} LIMIT %s OFFSET %s""",
        base_args + params + order_params + [pageSize, (page - 1) * pageSize]).fetchall()
    if rows:
        total = rows[0]["total_rows"]
    elif page == 1:
        total = 0
    else:
        total = conn.execute(f"{with_a}SELECT count(*) AS n {base}", base_args + params).fetchone()["n"]
    names = _buyer_names(conn, [r["id"] for r in rows])
    return {"items": [{**_buyer(r, names), "cpvCount": under.get(r["id"], 0) if prefixes else None} for r in rows],
            "cpvCountCollapsed": collapsed, "total": total,
            "page": page, "pageSize": pageSize}


@router.get("/v1/buyers/slugs")
@cache_list("buyer-slugs", ttl=15 * 60, snapshot=True)
def buyer_slugs(conn=Depends(get_conn)):
    """The buyers with an open notice, most first, for the sitemap: read from the aggregate `buyer_base` keeps
    (the per-request aggregate was a 2 s query, and the sitemap went without buyers when it was slow)."""
    org_ids, _, open_n, last_published, _ = buyer_base(conn)
    wanted = sorted((i for i in range(len(org_ids)) if open_n[i]), key=lambda i: (-open_n[i], org_ids[i]))
    wanted = wanted[:BUYER_SLUG_LIMIT]
    ids = [org_ids[i] for i in wanted]
    canonical = {r["id"]: r["canonical_name"] for r in conn.execute(
        "SELECT id, canonical_name FROM organisation WHERE id = ANY(%s)", (ids,)).fetchall()} if ids else {}
    names = _buyer_names(conn, ids)
    now = datetime.now(timezone.utc)
    return [{"slug": make_slug(org_ids[i], names.get(org_ids[i]) or canonical.get(org_ids[i]) or ""),
             "updatedAt": _day(last_published[i]) or now} for i in wanted if org_ids[i] in canonical]


@router.get("/v1/buyers/{slug}", response_model=Buyer)
def get_buyer(slug: str, conn=Depends(get_conn)):
    org_id = _id_of(slug, "buyer")
    # An old link to a member of a family shows the family (migration 0055).
    head = conn.execute("SELECT dgate_buyer_head(%s) AS head", (org_id,)).fetchone()["head"]
    org_ids, counts, open_n, last_published, variants = buyer_base(conn)
    at = org_ids.index(head) if head in org_ids else None
    row = conn.execute(
        f"SELECT org.id, org.canonical_name, org.country, {family_defence('org')} AS is_defence_buyer "
        "FROM organisation org WHERE org.id = %s", (head,)).fetchone() if at is not None else None
    if not row:
        if conn.execute("SELECT 1 FROM organisation WHERE id = %s AND suppressed",
                        (org_id,)).fetchone():
            raise removed()
        raise HTTPException(404, "no such buyer")
    row = {**row, "n": counts[at], "open_n": open_n[at], "last_published": last_published[at],
           "variants": variants[at]}
    out = _buyer(row, _buyer_names(conn, [row["id"]]))
    # WP-96: of the open tenders (the list's default scope), the military goods and works, as `scope=core` counts them
    if row["open_n"]:
        where, params, _ = _tender_filters(None, None, None, "open", "core", None, row["id"], None, None, None,
                                           None, None, conn=conn)
        out["openCoreCount"] = _count(conn, where, params)[0]
    else:
        out["openCoreCount"] = 0
    from .network_api import network_slug_of_buyer
    family = conn.execute("SELECT dgate_family_ids(%s) AS ids", (row["id"],)).fetchone()["ids"]
    out["organisationSlug"] = network_slug_of_buyer(conn, family)
    out["variantNames"] = variant_names(conn, row["id"], family, out["name"])
    return out


def variant_names(conn, head: int, family: list[int] | None, shown: str) -> list[str]:
    """WP-111 (p04): the names the family's other rows publish under (each row's commonest spelling, `_buyer_names`), each
    once (case and accents aside) and not the name the page shows, so a reader sees which notices are this buyer
    ("Agencja Uzbrojenia", "Skarb Panstwa - Agencja Uzbrojenia"). Most notices first."""
    members = [i for i in (family or []) if i != head]
    if not members:
        return []
    names = _buyer_names(conn, members)
    counts = {r["buyer_org_id"]: r["n"] for r in conn.execute(
        "SELECT buyer_org_id, count(*) AS n FROM opportunity WHERE buyer_org_id = ANY(%s) AND is_defence "
        "AND NOT suppressed AND NOT buyer_withheld GROUP BY 1", (members,)).fetchall()}
    seen = {tuple(fold_words(shown))}
    out = []
    for org in sorted(names, key=lambda i: (-counts.get(i, 0), names[i])):
        key = tuple(fold_words(names[org]))
        if names[org] and key not in seen:
            seen.add(key)
            out.append(names[org])
    return out
