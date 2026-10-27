"""Money in the market overview (WP-105, persona round of 24 October 2026, p07: "no spending totals by country, CPV or buyer").

The contract values of the supplier map's award set (`award_set.scope`: defence scope, three years, legal-entity winners, a
TED+PLACSP twin once), each contract of each winner once, valued exactly as the supplier pages value it
(`suppliers.value_of`, the row `suppliers.best` picks: a contract value before a ceiling before an estimate, a PLACSP
awarded amount before TED's), and summed only when it is a contract value that is no unit price (`suppliers.is_suspect`):
framework ceilings and estimates are never added. So the sum over any slice is the sum of its suppliers' contract values,
per currency, never converted.

Summing the whole set costs seconds (the value of every award row, WP-98c: 4-6 s on production), so the worker stores one
row per contract and winner in `list_snapshot` (key `contract-values`, renewed with the supplier value orders: after every
award load, every four hours and at the worker's start) and the market reads that. A removal on request drops every
snapshot (`ops.suppress.drop_derived`): the money is then not shown until the next round, never shown stale.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from . import award_set
from .award_set import FROM, KEY_HASH
from .award_value import CONTRACT
from .config import settings

MONEY_KEY = "contract-values"
MONEY_SECONDS = 5 * 60
TOP_BUYERS = 10
TOP_GROUPS = 12


def compute(conn) -> dict[str, Any]:
    """One row per contract (`award_set.KEY`) and winner of the set: its buyer, buyer family, buyer country, day, CPV codes, and
    its contract value when it is summed (currency and amount, else null), as `suppliers.contract_values_sql` sums it. WP-152:
    with the contract's key (`k`, `award_set.KEY_HASH`), so a slice counts a contract of several winners once (`competition`)."""
    from .suppliers import _RANK_V, SUSPECT_VALUE_MAX, _twins, value_of

    rows = conn.execute(
        f"""SELECT DISTINCT ON (org.id, {KEY_HASH}) org.id AS org, {KEY_HASH} AS k,
                   CASE WHEN o.buyer_withheld THEN NULL ELSE o.buyer_org_id END AS buyer,
                   CASE WHEN o.buyer_withheld THEN NULL ELSE COALESCE(f.head_org_id, o.buyer_org_id) END AS head,
                   o.country, COALESCE(o.published_at, o.notice_date)::date AS day, o.cpv_codes, v.va, v.vc, v.vk, v.vp
              {FROM} LEFT JOIN buyer_family_member f ON f.org_id = o.buyer_org_id {value_of("a.id", _twins(False))}
             WHERE {award_set.scope()}
             ORDER BY org.id, {KEY_HASH}, (v.va IS NULL), {_RANK_V}, NOT COALESCE(v.vp, FALSE), v.va DESC NULLS LAST""",
        {"since": award_set.since()}).fetchall()
    cols: dict[str, list[Any]] = {k: [] for k in ("org", "k", "buyer", "head", "country", "day", "cpv", "cur", "amt")}
    for r in rows:
        summed = (r["va"] is not None and r["vk"] == CONTRACT and (r["vp"] or float(r["va"]) >= SUSPECT_VALUE_MAX))
        for k, v in (("org", r["org"]), ("k", r["k"]), ("buyer", r["buyer"]), ("head", r["head"]), ("country", r["country"]),
                     ("day", r["day"].isoformat() if r["day"] else None), ("cpv", list(r["cpv_codes"] or [])),
                     ("cur", r["vc"].strip() if summed else None), ("amt", round(float(r["va"]), 2) if summed else None)):
            cols[k].append(v)
    return {"placspPublic": settings().placsp_awards_public, "since": award_set.since().isoformat(), **cols}


def store(conn) -> None:
    """Compute and write the snapshot, in the caller's transaction."""
    from psycopg.types.json import Jsonb

    conn.execute(
        """INSERT INTO list_snapshot (key, body, computed_at) VALUES (%s, %s, now())
           ON CONFLICT (key) DO UPDATE SET body = EXCLUDED.body, computed_at = EXCLUDED.computed_at""",
        (MONEY_KEY, Jsonb(compute(conn))))


def stored(conn) -> tuple[dict[str, Any], datetime] | None:
    """The snapshot (at most `listcache.SNAPSHOT_HOURS` old, computed under today's PLACSP switch) with its time, or None.
    Kept MONEY_SECONDS in memory, one read shared by concurrent callers."""
    from . import stats
    from .listcache import SNAPSHOT_HOURS

    def read() -> tuple[dict[str, Any], datetime] | None:
        try:
            with conn.transaction():
                row = conn.execute("SELECT body, computed_at FROM list_snapshot WHERE key = %s "
                                   "AND computed_at > now() - make_interval(hours => %s)",
                                   (MONEY_KEY, SNAPSHOT_HOURS)).fetchone()
        except Exception:  # noqa: BLE001 - a snapshot is a shortcut, never a failure
            return None
        if not row or row["body"].get("placspPublic") != settings().placsp_awards_public:
            return None
        return row["body"], row["computed_at"]

    if settings().list_cache_seconds <= 0:
        return read()
    return stats.cached(("contract-values",), read, MONEY_SECONDS, store=stats._list_cache, limit=stats.LIST_CACHED)


def totals(body: dict[str, Any], idx: list[int]) -> dict[str, Any]:
    """The contract values of the rows `idx`, per currency (largest count first), out of how many contracts."""
    by: dict[str, dict[str, Any]] = {}
    for i in idx:
        cur = body["cur"][i]
        if cur is None:
            continue
        s = by.setdefault(cur, {"currency": cur, "amount": 0.0, "count": 0, "lotEstimates": 0})
        s["amount"] += body["amt"][i]
        s["count"] += 1
    out = [{**s, "amount": round(s["amount"], 2)} for s in by.values()]
    out.sort(key=lambda s: (-s["count"], s["currency"]))
    return {"byCurrency": out, "of": len(idx), "withoutValue": len(idx) - sum(s["count"] for s in out)}


def _under(codes: list[str], prefixes: list[str] | None) -> bool:
    return not prefixes or any(c.startswith(p) for c in codes for p in prefixes)


def market_money(conn, since: date, until: date, country: str | None = None,
                 prefixes: list[str] | None = None) -> dict[str, Any] | None:
    """The contract values of the set's contracts published from `since` to `until` (the market's window, cut to the set's
    three years), of one buyer country and under CPV prefixes when asked: in all, by buyer country, by CPV group (the first
    three digits of every code of a notice: a contract in several groups is in each) and for the TOP_BUYERS buyer families
    with the most valued contracts. None when no snapshot is stored."""
    from .funding import make_slug
    from .tenders import _buyer_names

    got = stored(conn)
    if got is None:
        return None
    body, at = got
    start = max(since.isoformat(), body["since"])
    end = until.isoformat()
    idx = [i for i, d in enumerate(body["day"]) if d and start <= d <= end
           and (country is None or body["country"][i] == country) and _under(body["cpv"][i], prefixes)]
    by_country: dict[str, list[int]] = {}
    by_group: dict[str, list[int]] = {}
    by_head: dict[int, list[int]] = {}
    for i in idx:
        by_country.setdefault(body["country"][i] or "", []).append(i)
        for g in {c[:3] for c in body["cpv"][i] if len(c) >= 3}:
            if not prefixes or any(g.startswith(p[:3]) for p in prefixes):
                by_group.setdefault(g, []).append(i)
        if body["head"][i] is not None:
            by_head.setdefault(body["head"][i], []).append(i)

    def valued(xs: list[int]) -> int:
        return sum(1 for i in xs if body["cur"][i] is not None)

    heads = sorted(by_head, key=lambda h: (-valued(by_head[h]), h))[:TOP_BUYERS]
    names = _buyer_names(conn, heads)
    return {
        "asOf": at, "since": start, "until": end, "total": totals(body, idx),
        "byCountry": sorted(({"country": c, **totals(body, xs)} for c, xs in by_country.items() if c),
                            key=lambda x: (-x["of"], x["country"])),
        "byCpvGroup": sorted(({"group": g, **totals(body, xs)} for g, xs in by_group.items()),
                             key=lambda x: (-(x["of"] - x["withoutValue"]), x["group"]))[:TOP_GROUPS],
        "byBuyer": [{"slug": make_slug(h, names.get(h) or ""), "name": names.get(h) or "Buyer",
                     "country": body["country"][by_head[h][0]], **totals(body, by_head[h])} for h in heads if names.get(h)],
    }
