"""Competitor intelligence for one company of the supplier map (WP-152, owner request of 27 October 2026).

    GET /v1/suppliers/{slug}/competition   who it competes with, where it wins, its share

Every number is read from the rows the market overview already sums (`money.compute`, list_snapshot `contract-values`):
one row per contract (`award_set.KEY`) and winner of the award set (`award_set.scope`: defence scope, three years, legal
entities only, a TED+PLACSP twin once), with its buyer family, buyer country, CPV codes and, when the supplier pages sum
it, its contract value (`suppliers.value_of` / `best` / `is_suspect`: contract values only, never a ceiling, an estimate or
a unit price). So a company's count here is its count on its page and on the supplier list, and a value is the one its
page sums; nothing here is a second definition of an award or a contract.

  Competitors   the other legal entities that won a contract of the same buyer (buyer family, `dgate_buyer_head`) under
                the same CPV class (the first four digits of any code of the notice, as the list's product-code filter
                reads codes) in the same window. A "market" is one buyer and one class; the overlap is the number of the
                other company's contracts in the markets the two share, then the number of shared markets.
  Where it wins by buyer country and by CPV class (a contract under codes of two classes is in both), and the typical
                stated contract value: the median of its contract values in its commonest currency, with how many of its
                contracts state none.
  Its share     per its top CPV classes and buyer countries: its contracts out of every contract of the set there, and its
                contract value out of the slice's contract values in the slice's commonest currency (never converted).

What is not done: no organisation row is merged. One company can sit under several rows (the same name under different
registration numbers, WP-111); such a row is then listed among the competitors and is marked (`sameName`), as is a company
of the same curated group (`sameGroup`). A natural person is never in the set, so never named or counted as a competitor.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from statistics import median
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from . import money
from .config import settings
from .funding import get_conn, make_slug
from .listcache import cache_list
from .ops.company_groups import GROUPS
from .suppliers import _name, _resolve, shown
from .tenders import _id_of

router = APIRouter()

COMPETITORS = 20
TOP = 5               # classes and countries of "its share"
WHERE_ROWS = 15       # rows of each "where it wins" table


def classes(codes: list[str]) -> set[str]:
    """The CPV classes (first four digits) of a notice's codes."""
    return {c[:4] for c in codes if len(c) >= 4 and c[:4].isdigit()}


class _Index:
    """What every company's answer reads, built once per snapshot: rows by winner and by buyer family, each row's classes,
    and per class and per buyer country the contracts (keys, a contract of several winners once) and the value sums."""

    def __init__(self, body: dict[str, Any]) -> None:
        self.body = body
        self.cls = [classes(c or []) for c in body["cpv"]]
        self.by_org: dict[int, list[int]] = {}
        self.by_head: dict[int, list[int]] = {}
        self.slices: dict[tuple[str, str], tuple[set[int], dict[str, list[float]]]] = {}
        for i, org in enumerate(body["org"]):
            self.by_org.setdefault(org, []).append(i)
            if body["head"][i] is not None:
                self.by_head.setdefault(body["head"][i], []).append(i)
            for key in [("class", c) for c in self.cls[i]] + ([("country", body["country"][i])] if body["country"][i] else []):
                keys, values = self.slices.setdefault(key, (set(), {}))
                keys.add(body["k"][i])
                if body["cur"][i] is not None:
                    s = values.setdefault(body["cur"][i], [0.0, 0])
                    s[0] += body["amt"][i]
                    s[1] += 1


_last: list[tuple[datetime | None, _Index]] = []


def index(body: dict[str, Any], at: datetime | None = None) -> _Index:
    """The index of a snapshot, rebuilt when the snapshot is renewed (`at`, its time), not each time `money.stored` reads
    it again (about a second for 250,000 rows, measured on the laptop)."""
    if _last:
        seen, ix = _last[0]
        if (at is not None and seen == at) or ix.body is body:
            return ix
    _last[:] = [(at, _Index(body))]
    return _last[0][1]


def analyse(ix: _Index, org: int) -> dict[str, Any] | None:
    """The answer for winner `org` without names (ids only), or None when it has no row in the snapshot."""
    b = ix.body
    mine = ix.by_org.get(org)
    if not mine:
        return None
    markets = {(b["head"][i], c) for i in mine if b["head"][i] is not None for c in ix.cls[i]}
    rivals: dict[int, list[Any]] = {}            # org -> [contracts in shared markets, shared markets, buyers]
    for head in {h for h, _ in markets}:
        for i in ix.by_head[head]:
            other = b["org"][i]
            if other == org:
                continue
            hit = {(head, c) for c in ix.cls[i]} & markets
            if hit:
                r = rivals.setdefault(other, [0, set()])
                r[0] += 1
                r[1] |= hit
    top = sorted(rivals, key=lambda o: (-rivals[o][0], -len(rivals[o][1]), o))[:COMPETITORS]
    competitors = []
    for o in top:
        shared = rivals[o][1]
        competitors.append({
            "org": o, "overlap": rivals[o][0], "markets": len(shared), "buyers": len({h for h, _ in shared}),
            # this company's own contracts in the same markets
            "ours": sum(1 for i in mine if any((b["head"][i], c) in shared for c in ix.cls[i]))})

    by_country = Counter(b["country"][i] for i in mine if b["country"][i])
    by_class = Counter(c for i in mine for c in ix.cls[i])
    valued = Counter(b["cur"][i] for i in mine if b["cur"][i] is not None)
    size = None
    if valued:
        cur = sorted(valued, key=lambda c: (-valued[c], c))[0]
        amounts = [b["amt"][i] for i in mine if b["cur"][i] == cur]
        size = {"currency": cur, "median": round(median(amounts), 2), "valued": len(amounts),
                "otherCurrencies": sum(valued.values()) - len(amounts)}

    def share(kind: str, key: str, rows: list[int]) -> dict[str, Any]:
        keys, values = ix.slices[(kind, key)]
        out: dict[str, Any] = {"key": key, "contracts": len(rows), "total": len(keys), "currency": None}
        if values:
            cur = sorted(values, key=lambda c: (-values[c][1], c))[0]
            own = [b["amt"][i] for i in rows if b["cur"][i] == cur]
            out.update({"currency": cur, "value": round(sum(own), 2), "valued": len(own),
                        "valueTotal": round(values[cur][0], 2), "valuedTotal": values[cur][1]})
        return out

    def ranked(c: Counter) -> list[tuple[str, int]]:
        return sorted(c.items(), key=lambda x: (-x[1], x[0]))

    return {
        "contracts": len(mine), "markets": len(markets), "competitorCount": len(rivals), "competitors": competitors,
        "byCountry": [{"key": k, "contracts": n} for k, n in ranked(by_country)[:WHERE_ROWS]],
        "byClass": [{"key": k, "contracts": n} for k, n in ranked(by_class)[:WHERE_ROWS]],
        "size": size, "withoutValue": len(mine) - sum(valued.values()),
        "shareByClass": [share("class", k, [i for i in mine if k in ix.cls[i]]) for k, _ in ranked(by_class)[:TOP]],
        "shareByCountry": [share("country", k, [i for i in mine if b["country"][i] == k])
                           for k, _ in ranked(by_country)[:TOP]],
    }


class Competitor(BaseModel):
    slug: str
    name: str
    country: str | None
    overlap: int              # its contracts in the markets (buyer and CPV class) it shares with this company
    markets: int              # the markets they share
    buyers: int               # the buyers of those markets
    ours: int                 # this company's contracts in the same markets
    sameName: bool = False    # the same name in the same country: possibly this company under another record (WP-111)
    sameGroup: str | None = None   # the curated company group both are listed under (`ops.company_groups`)


class Tally(BaseModel):
    key: str
    contracts: int


class TypicalSize(BaseModel):
    currency: str
    median: float
    valued: int               # its contracts with a contract value in this currency
    otherCurrencies: int      # with a contract value in another currency


class Share(BaseModel):
    key: str                  # a CPV class (4 digits) or a buyer country
    contracts: int            # this company's contracts there
    total: int                # every contract of the set there
    currency: str | None      # the commonest currency of the contract values there; None: none states one
    value: float | None = None
    valued: int | None = None
    valueTotal: float | None = None
    valuedTotal: int | None = None


class Competition(BaseModel):
    available: bool           # False: the stored rows are being renewed; nothing else is filled
    asOf: datetime | None = None
    since: str | None = None
    contracts: int = 0
    markets: int = 0
    competitorCount: int = 0
    competitors: list[Competitor] = []
    byCountry: list[Tally] = []
    byClass: list[Tally] = []
    size: TypicalSize | None = None
    withoutValue: int = 0
    shareByClass: list[Share] = []
    shareByCountry: list[Share] = []
    reportOpen: bool = False  # the paid company report exists (DGATE_COMPANY_REPORT_OPEN)


@router.get("/v1/suppliers/{slug}/competition", response_model=Competition)
@cache_list("supplier_competition", ttl=5 * 60)
def get_competition(slug: str, conn=Depends(get_conn)):
    org, org_id, _base, _p = _resolve(conn, _id_of(slug, "supplier"))
    report = settings().company_report_open
    got = money.stored(conn)
    # a snapshot stored before WP-152 has no contract keys: unavailable until the worker's next round renews it
    out = analyse(index(got[0], got[1]), org_id) if got and "k" in got[0] else None
    if out is None:
        return {"available": False, "reportOpen": report}
    ids = [c["org"] for c in out["competitors"]]
    rows = {r["id"]: r for r in conn.execute(
        f"SELECT m.id, m.canonical_name, m.country, {shown()} AS shown FROM organisation m WHERE m.id = ANY(%s)",
        (ids,)).fetchall()} if ids else {}
    groups: dict[int, str] = {r["org_id"]: r["group_key"] for r in conn.execute(
        "SELECT org_id, group_key FROM company_group_member WHERE org_id = ANY(%s)", (ids + [org_id],)).fetchall()}
    names = {g.key: g.name for g in GROUPS}
    mine = (org["canonical_name"] or "").lower(), org["country"]
    competitors = []
    for c in out.pop("competitors"):
        r = rows.get(c.pop("org"))
        if not r:
            continue
        name = _name(r)
        g = groups.get(r["id"])
        competitors.append({**c, "slug": make_slug(r["id"], name), "name": name, "country": (r["country"] or "").strip() or None,
                            "sameName": ((r["canonical_name"] or "").lower(), r["country"]) == mine,
                            "sameGroup": names.get(g) if g and g == groups.get(org_id) else None})
    return {**out, "available": True, "asOf": got[1], "since": got[0]["since"], "competitors": competitors,
            "reportOpen": report}
