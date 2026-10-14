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

from ..accounts import _is_new, run_search
from ..config import settings
from . import mailer

log = logging.getLogger("ops.digest")

MAX_ACCOUNTS_PER_RUN = 200
MAX_ITEMS_PER_SEARCH = 8

DUE_SQL = """
    SELECT s.id, s.owner_id, s.name, s.kind, s.filters, s.cadence, s.created_at,
           s.last_alerted_at, u.email_display
      FROM app_saved_search s JOIN app_user u ON u.id = s.owner_id
     WHERE s.cadence <> 'off'
       AND COALESCE(s.last_alerted_at, s.created_at) <= now() - (CASE s.cadence
              WHEN 'instant' THEN interval '50 minutes'
              WHEN 'daily'   THEN interval '23 hours'
              ELSE interval '6 days 23 hours' END)
     ORDER BY s.owner_id, s.created_at
     LIMIT 1000
"""


def _line(kind: str, item: dict[str, Any], site: str) -> str:
    where = "tenders" if kind == "tender" else "funding"
    who = item.get("buyerName") if kind == "tender" else item.get("issuer")
    deadline = item.get("deadline")
    when = deadline.strftime("%Y-%m-%d") if isinstance(deadline, datetime) else "no deadline stated"
    meta = ", ".join(x for x in (who, item.get("country") or item.get("funderCountry")) if x)
    return f"- {item['title']}\n  {meta} | deadline {when}\n  {site}/{where}/{item['slug']}"


def run_digests(conn) -> dict[str, int]:
    """Send what is due. Returns counts, for the job log."""
    result = {"accounts": 0, "mails": 0, "searches": 0, "failed": 0}
    if not mailer.can_send():
        return result
    site = settings().site_url.rstrip("/")
    by_owner: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in conn.execute(DUE_SQL).fetchall():
        by_owner[row["owner_id"]].append(row)

    for searches in list(by_owner.values())[:MAX_ACCOUNTS_PER_RUN]:
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
                sections.append(f"{s['name']}: {len(fresh)} new\n" + "\n".join(lines))
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
