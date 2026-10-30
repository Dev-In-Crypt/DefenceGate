"""The two exports of the owner's plan split (WP-155, built in WP-156), for a signed-in account:

    GET /v1/account/suppliers/export      the supplier map's list under its filters, up to EXPORT_MAX rows (`supplier_map_csv`,
                                          Team and Consultant); the site turns it into a CSV (web/app/(public)/suppliers/export.csv)
    GET /v1/account/eligibility/calls     every open call with the facts the eligibility check compares (`eligibility_export`,
                                          Pro and up); the site's cabinet builds the results pack from it in the browser

Both are gated by `billing.require` (402 `plan_required`): while no plan is on sale nobody is refused (WP-124), and nobody
reaches either while accounts are closed (DGATE_ACCOUNTS_OPEN), since both need a session.

The supplier export is the public list (`suppliers.supplier_rows`, same filters, same order, same award set of
`award_set.py`: legal entities only, a natural person is never named) without the list's MAX_OFFSET: the walk the public list
prices is what the plan sells. It is capped at EXPORT_MAX rows, and the file says when it was cut.

The eligibility pack never sends the profile anywhere: this answer is the same for every account (public calls and the public
facts of /v1/fit/facts); the browser compares them with the profile it holds, as the list badges do (web/lib/fit.ts callFit).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from . import accounts, billing
from .accounts import throttled
from .funding import get_conn, list_funding
from .partners import facts_of
from .suppliers import supplier_rows

account_router = APIRouter(prefix="/v1/account", dependencies=[Depends(accounts.internal_only), Depends(accounts.no_store)])

EXPORT_MAX = 5000              # rows of one supplier-map CSV
PACK_MAX = 1000                # open calls in one eligibility pack; the answer says how many were open (`total`)
_PAGE = 500                    # list_funding's largest page


@account_router.get("/suppliers/export")
def supplier_export(
    q: str | None = Query(None, max_length=100),
    country: str | None = Query(None, max_length=200),
    cpv: str | None = Query(None, max_length=200),
    buyerCountry: str | None = Query(None, max_length=200),
    group: str | None = Query(None, max_length=40),
    sort: str = Query("awards", pattern="^(awards|name|value-[A-Z]{3})$"),
    source: str | None = Query(None, pattern="^ted$"),
    user=Depends(throttled), conn=Depends(get_conn),
):
    billing.require(user, "supplier_map_csv")
    out = supplier_rows(conn, q, country, cpv, buyerCountry, group, sort, source, EXPORT_MAX, 0)
    accounts._audit("supplier_export", user["id"], rows=len(out["items"]))      # O3: capped and logged with the account id
    return {"items": out["items"], "total": out["total"], "cap": EXPORT_MAX, "placsp": out["placsp"],
            "asOf": datetime.now(timezone.utc).date().isoformat()}


def open_calls(conn) -> tuple[list[dict[str, Any]], int]:
    """The open calls as the public list gives them (status `open`, deadline first), up to PACK_MAX, and how many are open."""
    items: list[dict[str, Any]] = []
    total = 0
    for page in range(1, PACK_MAX // _PAGE + 1):
        # every parameter explicitly: called as a plain function, a default left out would be its Query object
        got = list_funding(q=None, programme=None, regime=None, country=None, status="open", from_=None, to=None, min_=None,
                           max_=None, currency=None, sort="deadline-asc", cascade=None, ukraine=None, uaNoFunding=None, who=None,
                           page=page, pageSize=_PAGE, conn=conn, with_meta=False)
        items += got["items"]
        total = got["total"]
        if len(items) >= total:
            break
    return items, total


@account_router.get("/eligibility/calls")
def eligibility_calls(user=Depends(throttled), conn=Depends(get_conn)):
    billing.require(user, "eligibility_export")
    calls, total = open_calls(conn)
    accounts._audit("eligibility_export", user["id"], rows=len(calls))         # O3
    facts = facts_of(conn, [int(c["id"]) for c in calls]) if calls else {}
    keep = ("id", "slug", "title", "programme", "programmeName", "topicId", "deadline", "deadlineIsDate", "rolling")
    items = [{**{k: c[k] for k in keep}, "sourceUrl": c["source"]["url"], "sourceName": c["source"]["sourceName"],
              "fit": facts.get(c["id"])} for c in calls]
    return {"items": items, "total": total, "cap": PACK_MAX, "asOf": datetime.now(timezone.utc).isoformat()}
