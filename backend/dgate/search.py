"""One search box over the site's five lists (WP-86).

    GET /v1/search?q=&limit=   the first `limit` matches of each list, and each list's own total

No search engine of its own: each group is the list endpoint itself (`list_tenders`, `list_funding`, `list_buyers`,
`list_suppliers`, `list_organisations`), called with the filters the site's list opens on (`OPENS_ON`, else the
endpoint's defaults) and `q`, so a group says what the list's "see all" link will show (tenders and funding: open ones,
organisations: the defence programmes). The lists' own response caches apply.

WP-110 (round-4 re-check of 24 October 2026: "The search is not available right now" in about one load of three, and
"Regionalna Baza Logistyczna" 11.5 s with three parts "took too long"): the groups run AT THE SAME TIME, each on a
connection of its own taken inside the API's bound (`db.bounded_connect`, the same gate as every request) and inside the
search's own (`PART_CONNECTIONS`, so searches never hold more than that many of the API's connections), each with the
whole budget (`BUDGET_MS`) as its statement limit and as a wall-clock deadline. A group that has not answered at the
deadline is cancelled (`Connection.cancel`) and answers `{"error": "slow"}`; one that found no free connection in time
answers `{"error": "busy"}`; a group that refuses the words (a list's own 422) `{"error": "refused"}`. The search itself
takes no connection, so it never answers 503 for a busy pool: each part degrades alone. Before, the parts ran one after the
other on one connection, `statement_timeout` bounded each statement and not the part (the tender part's three statements
of 1.2 s each used the whole budget on production, idle: funding and buyers "slow"), and the request's own connection
was a 503 when the pool was full.
"""

from __future__ import annotations

import inspect
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait as wait_for
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import db
from .classify import DEFENCE_PROGRAMMES
from .config import settings
from .funding import list_funding
from .network_api import list_organisations
from .search_terms import buyer_names, fold_words
from .suppliers import list_suppliers
from .tenders import NOTICE_NUMBER, list_buyers, list_tenders, search_info

router = APIRouter()
log = logging.getLogger(__name__)

# The API role's own statement limit is 5 s; the whole search stays under it.
BUDGET_MS = 4500
MIN_STATEMENT_MS = 200
# What the answer itself takes after the parts (the hints, the JSON): the parts get the budget less this
FINISH_MS = 150
# At most this many connections are held by search parts at once, of the API's 24 (`config.api_connections`): two
# searches at once run whole, a third waits for a part to finish; the rest of the site keeps the other connections.
PART_CONNECTIONS = 10
_PART_GATE = threading.BoundedSemaphore(PART_CONNECTIONS)
_EXECUTOR = ThreadPoolExecutor(max_workers=PART_CONNECTIONS * 2, thread_name_prefix="search")
GROUPS = {"tenders": list_tenders, "funding": list_funding, "buyers": list_buyers,
          "suppliers": list_suppliers, "organisations": list_organisations}
# Where the site's list opens on something other than the endpoint's default: the organisation directory opens on the
# defence programmes (web/lib/networks.ts DEFENCE_PROGRAMMES), so its "see all" link and this group count the same.
OPENS_ON = {"organisations": {"programme": ",".join(DEFENCE_PROGRAMMES)}}


def opens_on(name: str, q: str) -> dict[str, Any]:
    """The filters the list `name` opens on for these words. WP-101: a notice number is looked for in every status (the
    site's tender list opens on All for it as well): Open hid an awarded notice (220199-2026)."""
    out = dict(OPENS_ON.get(name, {}))
    if name == "tenders" and NOTICE_NUMBER.match(q):
        out["status"] = "all"
    return out


def _defaults(fn) -> dict[str, Any]:
    """Every parameter of a list endpoint at its default (as FastAPI would pass them), the connection left out."""
    fn = getattr(fn, "__wrapped__", fn)
    out: dict[str, Any] = {}
    for name, p in inspect.signature(fn).parameters.items():
        if name != "conn":
            out[name] = getattr(p.default, "default", p.default)
    if "with_meta" in out:
        out["with_meta"] = False          # no "data updated at" line: the search page does not show one
    return out


class Group(BaseModel):
    total: int | None = None
    # The list's total is a floor ("at least"): tenders past their count cap, organisations past 10,000.
    atLeast: bool = False
    items: list[dict[str, Any]] = []
    error: str | None = None


class SearchOut(BaseModel):
    q: str
    tenders: Group
    funding: Group
    buyers: Group
    suppliers: Group
    organisations: Group
    tookMs: int
    # WP-98: the tender part's other-language terms and their product groups (`tenders.search_info`)
    alsoSearched: list[str] = []
    searchGroups: list[dict[str, Any]] = []
    # WP-110: "Did you mean CPV 31611000 Wiring sets?" (`tenders.cpv_hints`)
    cpvHints: list[dict[str, Any]] = []
    # WP-98: the first buyer is the one the words name (an abbreviation's family, or the name itself)
    buyerNamed: bool = False


def _names_all(words: list[str], name: str | None) -> bool:
    have = fold_words(name or "")
    return all(any(h.startswith(w) for h in have) for w in words)


def named_first(conn, q: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """WP-110 (p07: "Leonardo" listed Polish Megmar second, unexplained): the companies whose own name holds the words first,
    then those found by a name they were published under, each with that name (`matchedAs`: "Konsorcjum: MEGMAR Logistics &
    Consulting Sp. z o.o. Leonardo Poland Sp. z o.o."), so the page can say why it is there. Same companies, same total."""
    words = fold_words(q)
    hits = [i for i in items if _names_all(words, i.get("name"))]
    others = [i for i in items if not _names_all(words, i.get("name"))]
    if others:
        ids = [int(i["id"]) for i in others]
        rows = conn.execute(
            "SELECT DISTINCT COALESCE(x.merged_into, x.id) AS id, a.name_as_stated AS n FROM award a "
            "JOIN organisation x ON x.id = a.organisation_id WHERE x.id = ANY(%s) OR x.merged_into = ANY(%s) "
            "ORDER BY 2", (ids, ids)).fetchall()
        for i in others:
            stated = next((r["n"] for r in rows if r["id"] == int(i["id"]) and _names_all(words, r["n"])), None)
            if stated:
                i["matchedAs"] = stated
    return hits + others


class _Part:
    """One group of one search: run on a connection of its own, cancelled from outside at the deadline."""

    def __init__(self, name: str, fn, q: str, limit: int, deadline: float) -> None:
        self.name, self.fn, self.q, self.limit, self.deadline = name, fn, q, limit, deadline
        self.conn: psycopg.Connection | None = None
        self.late = False                      # the search answered without it: it must not start any more work
        self.lock = threading.Lock()

    def left_ms(self) -> int:
        return int((self.deadline - time.monotonic()) * 1000)

    def run(self) -> dict[str, Any]:
        if self.left_ms() < MIN_STATEMENT_MS or not _PART_GATE.acquire(timeout=max(0.0, self.left_ms() / 1000)):
            return {"error": "busy" if self.left_ms() >= MIN_STATEMENT_MS else "slow"}
        try:
            cfg = settings()
            left = self.left_ms()
            if left < MIN_STATEMENT_MS:
                return {"error": "slow"}
            with db.bounded_connect(cfg.api_dsn or cfg.dsn, cfg.api_connections, min(cfg.pool_wait_ms, left) / 1000) as conn:
                with self.lock:
                    if self.late:
                        return {"error": "slow"}
                    self.conn = conn
                left = self.left_ms()
                if left < MIN_STATEMENT_MS:
                    return {"error": "slow"}
                conn.execute(f"SET statement_timeout = {left}")
                page = self.fn(**{**_defaults(self.fn), **opens_on(self.name, self.q), "q": self.q, "pageSize": self.limit},
                               conn=conn)
                if self.name == "suppliers":
                    page["items"] = named_first(conn, self.q, page["items"][:self.limit])
                with self.lock:
                    self.conn = None
        except psycopg.errors.QueryCanceled:
            return {"error": "slow"}
        except (db.PoolBusy, psycopg.errors.TooManyConnections):
            return {"error": "busy"}
        except HTTPException:
            return {"error": "refused"}
        finally:
            _PART_GATE.release()
        at_least = bool(page.get("totalCapped")) or page.get("totalExact") is False
        return {"total": page["total"], "atLeast": at_least, "items": page["items"][:self.limit]}

    def cancel(self) -> None:
        with self.lock:
            self.late = True
            if self.conn is not None:
                try:
                    self.conn.cancel()
                except psycopg.Error:
                    pass


@router.get("/v1/search", response_model=SearchOut)
def search(q: str = Query(min_length=2, max_length=100), limit: int = Query(5, ge=1, le=10)):
    q = q.replace("\x00", "").strip()
    if len(q) < 2:
        raise HTTPException(422, "q: at least two characters")
    start = time.monotonic()
    out: dict[str, Any] = {"q": q}
    deadline = start + (BUDGET_MS - FINISH_MS) / 1000
    parts = [_Part(name, fn, q, limit, deadline) for name, fn in GROUPS.items()]
    futures = {_EXECUTOR.submit(p.run): p for p in parts}
    done, _ = wait_for(futures, timeout=max(0.0, deadline - time.monotonic()))
    for f, p in futures.items():
        if f in done:
            try:
                out[p.name] = f.result()
            except Exception:              # one part's failure is that part's, never the whole search's
                log.exception("search part %s failed", p.name)
                out[p.name] = {"error": "busy"}
        else:
            p.cancel()
            out[p.name] = {"error": "slow"}
    first = (out["buyers"].get("items") or [None])[0]
    out["buyerNamed"] = first is not None and (
        bool(buyer_names(q)) or "".join(fold_words(first.get("name") or "")) == "".join(fold_words(q)))
    out["tookMs"] = int((time.monotonic() - start) * 1000)
    return {**out, **search_info(q)}
