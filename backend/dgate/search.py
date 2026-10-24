"""One search box over the site's five lists (WP-86).

    GET /v1/search?q=&limit=   the first `limit` matches of each list, and each list's own total

No search engine of its own: each group is the list endpoint itself (`list_tenders`, `list_funding`, `list_buyers`,
`list_suppliers`, `list_organisations`), called with the filters the site's list opens on (`OPENS_ON`, else the
endpoint's defaults) and `q`, so a group says what the list's "see all" link will show (tenders and funding: open ones,
organisations: the defence programmes). The lists' own response caches apply.

The groups run one after another on the request's one connection, inside a budget (`BUDGET_MS`): each statement is
given what is left of it less `RESERVE_MS` for each group after it (`SET LOCAL statement_timeout`), and a group that
does not finish in time, or is not
reached, answers `{"error": "slow"}` instead of failing the whole search. A group that refuses the words (a list's
own 422) answers `{"error": "refused"}`.
"""

from __future__ import annotations

import inspect
import time
from typing import Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .classify import DEFENCE_PROGRAMMES
from .funding import get_conn, list_funding
from .network_api import list_organisations
from .search_terms import buyer_names, fold_words
from .suppliers import list_suppliers
from .tenders import NOTICE_NUMBER, list_buyers, list_tenders, search_info

router = APIRouter()

# The API role's own statement limit is 5 s; the whole search stays under it.
BUDGET_MS = 4500
MIN_STATEMENT_MS = 200
RESERVE_MS = 300
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
    # WP-98: the first buyer is the one the words name (an abbreviation's family, or the name itself)
    buyerNamed: bool = False


@router.get("/v1/search", response_model=SearchOut)
def search(q: str = Query(min_length=2, max_length=100), limit: int = Query(5, ge=1, le=10),
           conn=Depends(get_conn)):
    q = q.replace("\x00", "").strip()
    if len(q) < 2:
        raise HTTPException(422, "q: at least two characters")
    start = time.monotonic()
    out: dict[str, Any] = {"q": q}
    for n, (name, fn) in enumerate(GROUPS.items()):
        # What is left of the budget, less a reserve for each group still to come: one slow list does not starve the rest.
        left = BUDGET_MS - int((time.monotonic() - start) * 1000) - RESERVE_MS * (len(GROUPS) - n - 1)
        if left < MIN_STATEMENT_MS:
            out[name] = {"error": "slow"}
            continue
        try:
            with conn.transaction():
                conn.execute(f"SET LOCAL statement_timeout = {left}")
                page = fn(**{**_defaults(fn), **opens_on(name, q), "q": q, "pageSize": limit}, conn=conn)
        except psycopg.errors.QueryCanceled:
            out[name] = {"error": "slow"}
            continue
        except HTTPException:
            out[name] = {"error": "refused"}
            continue
        at_least = bool(page.get("totalCapped")) or page.get("totalExact") is False
        out[name] = {"total": page["total"], "atLeast": at_least, "items": page["items"][:limit]}
    first = (out["buyers"].get("items") or [None])[0]
    out["buyerNamed"] = first is not None and (
        bool(buyer_names(q)) or "".join(fold_words(first.get("name") or "")) == "".join(fold_words(q)))
    out["tookMs"] = int((time.monotonic() - start) * 1000)
    return {**out, **search_info(q)}
