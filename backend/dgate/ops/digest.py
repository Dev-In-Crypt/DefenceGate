"""Alert digests: one plain-text mail per account listing what is new for its saved searches.

Runs hourly in the worker. A search is due when its cadence has elapsed since it was last
alerted (or created: a new search never mails the history). "New" is decided by the same
function the dashboard uses, so an alert and the page never disagree.

Nothing is marked as sent unless the relay accepted the message, so a failed send is retried
by the next run. With no relay configured nothing happens at all.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

from ..accounts import (
    ASSOC_PLAN_SQL,
    WS_JOIN_SQL,
    WS_PLAN_SQL,
    _is_new,
    run_search,
    search_kind_allowed,
)
from ..billing import may, search_limit
from ..config import settings
from ..expiring import period_text
from . import mailer

log = logging.getLogger("ops.digest")

MAX_ACCOUNTS_PER_RUN = 200
MAX_ITEMS_PER_SEARCH = 8

DUE_SQL = f"""
    SELECT s.id, s.owner_id, s.name, s.kind, s.filters, s.cadence, s.created_at,
           s.last_alerted_at, u.email_display,
           (SELECT count(*) FROM app_saved_search e WHERE e.owner_id = s.owner_id
               AND (e.created_at, e.id) < (s.created_at, s.id)) AS plan_rank,
           b.plan AS sub_plan, b.status AS sub_status, b.current_period_end AS sub_period_end, {ASSOC_PLAN_SQL},
           {WS_PLAN_SQL}
      FROM app_saved_search s JOIN app_user u ON u.id = s.owner_id
      LEFT JOIN billing_subscription b ON b.account_id = u.id
      -- WP-157: a workspace member has its owner's plan (billing.plan_of)
      {WS_JOIN_SQL}
     WHERE s.cadence <> 'off'
       AND COALESCE(s.last_alerted_at, s.created_at) <= now() - (CASE s.cadence
              WHEN 'instant' THEN interval '50 minutes'
              WHEN 'daily'   THEN interval '23 hours'
              ELSE interval '6 days 23 hours' END)
     ORDER BY s.owner_id, s.created_at
     LIMIT 1000
"""


def _line(kind: str, item: dict[str, Any], site: str) -> str:
    if kind == "ending":
        # WP-160: a contract that entered the search's window: its end and where the end comes from, the winners named
        meta = ", ".join(x for x in (item.get("buyerName"), item.get("country")) if x)
        won = ", ".join(w["name"] for w in item.get("awardedTo") or [])
        return (f"- {item['title']}\n  {meta} | {period_text(item.get('contractPeriod'))}"
                + (f"\n  awarded to {won}" if won else "") + f"\n  {site}/tenders/{item['slug']}")
    where ="tenders" if kind == "tender" else "funding"
    who = item.get("buyerName") if kind == "tender" else item.get("issuer")
    deadline = item.get("deadline")
    when = deadline.strftime("%Y-%m-%d") if isinstance(deadline, datetime) else "no deadline stated"
    meta = ", ".join(x for x in (who, item.get("country") or item.get("funderCountry")) if x)
    return f"- {item['title']}\n  {meta} | deadline {when}\n  {site}/{where}/{item['slug']}"


def run_digests(conn) -> dict[str, int]:
    """Send what is due. Returns counts, for the job log."""
    result = {"accounts": 0, "mails": 0, "searches": 0, "failed": 0}
    if not mailer.ready():           # configured and the relay passed its health check (WP-123)
        return result
    site = settings().site_url.rstrip("/")
    by_owner: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in conn.execute(DUE_SQL).fetchall():
        by_owner[row["owner_id"]].append(row)

    for searches in list(by_owner.values())[:MAX_ACCOUNTS_PER_RUN]:
        if not may(searches[0], "email_alerts"):
            # WP-124: no plan with alerts (any more): nothing is sent, and the window moves on so the
            # search is not due again every hour and a later plan does not mail the backlog.
            conn.execute("UPDATE app_saved_search SET last_alerted_at = now() WHERE id = ANY(%s)",
                         ([s["id"] for s in searches],))
            conn.commit()
            result["skipped"] = result.get("skipped", 0) + 1
            continue
        # WP-155: the searches over the plan's number (kept after a move to a smaller plan) are paused the same way
        limit = search_limit(searches[0])
        over = [s["id"] for s in searches if s["plan_rank"] >= limit]
        if over:
            conn.execute("UPDATE app_saved_search SET last_alerted_at = now() WHERE id = ANY(%s)", (over,))
            conn.commit()
            searches = [s for s in searches if s["plan_rank"] < limit]
            if not searches:
                continue
        # WP-160: a search of contracts ending soon alerts only with accounts open (built dark) and `expiring_contracts`
        # (Pro); otherwise its window moves on the same way, so nothing is mailed later as a backlog
        held = [s["id"] for s in searches
                if s["kind"] == "ending" and not (settings().accounts_open and search_kind_allowed(s, "ending"))]
        if held:
            conn.execute("UPDATE app_saved_search SET last_alerted_at = now() WHERE id = ANY(%s)", (held,))
            conn.commit()
            searches = [s for s in searches if s["id"] not in held]
            if not searches:
                continue
        result["accounts"] += 1
        sections, total = [], 0
        evaluated: list[Any] = []       # only these may move their window on (audit M3)
        for s in searches:
            since = s["last_alerted_at"] or s["created_at"]
            try:
                found = run_search(conn, s["kind"], s["filters"], full=True)
            except Exception as exc:  # noqa: BLE001 - one broken search must not stop the others
                log.warning("digest: search %s skipped: %s", s["id"], type(exc).__name__)
                continue
            evaluated.append(s["id"])
            fresh = [i for i in found["items"] if _is_new(s["kind"], i, since)]
            if fresh:
                total += len(fresh)
                lines = [_line(s["kind"], i, site) for i in fresh[:MAX_ITEMS_PER_SEARCH]]
                more = len(fresh) - len(lines)
                if more > 0:
                    lines.append(f"  ... and {more} more")
                what = (f"{len(fresh)} {'contract' if len(fresh) == 1 else 'contracts'} newly ending within "
                        f"{s['filters'].get('within', '12')} months" if s["kind"] == "ending" else f"{len(fresh)} new")
                sections.append(f"{s['name']}: {what}\n" + "\n".join(lines))
        if sections:
            body = (
                "New for your saved searches on DefenceGate\n\n" + "\n\n".join(sections) +
                "\n\nCheck the original notice before you act on any of these. DefenceGate is "
                "an information service, not an official source.\n"
                f"Change or stop these alerts: {site}/app/searches\n")
            subject = f"DefenceGate: {total} new for your saved searches"
            if not mailer.send_mail(searches[0]["email_display"], subject, body):
                result["failed"] += 1
                continue                      # not marked as sent: the next run tries again
            result["mails"] += 1
        # The window moves on whether or not there was anything to say, but only for the
        # searches that were actually looked at: a search that raised (a statement timeout
        # is enough) keeps its window, so the next run covers what this one missed.
        if evaluated:
            conn.execute("UPDATE app_saved_search SET last_alerted_at = now() WHERE id = ANY(%s)",
                         (evaluated,))
            conn.commit()
        result["searches"] += len(evaluated)
    return result
