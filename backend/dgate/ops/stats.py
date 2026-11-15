"""Visit statistics for the owner (WP-169): the visit counter's table (`app_hit_daily`) printed as plain tables.

Internal, never served (no admin sign-in exists, so no route either). Read-only session with a statement timeout. On
production through the worker image (the worker role reads the table since migration 0042):

    docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps -T worker python -m dgate.ops.stats --days 30

Every table has two columns: the last 7 days and the last --days days (UTC, today included). Paths, referrer hosts and
countries exist only for the days counted with DGATE_STATS_DETAIL=1; before that a path is its page key (`/tenders/[slug]`)
and a referrer is the allow-list's name or `other`. Countries are their own daily totals (`app_hit_country_daily`), never
combined with a page, a referrer or a device. `internal` is a view that came from our own site, an empty referrer a
direct visit. Aggregates only: the table holds no address, no identifier and no user agent.
"""

from __future__ import annotations

import argparse
import sys

from .. import db
from ..config import settings

# label, the table, the expression grouped on
TABLES = [
    ("Pages (exact path where kept, else the page key)", "app_hit_daily", "COALESCE(NULLIF(path, ''), route)"),
    ("Referrer hosts", "app_hit_daily", "COALESCE(NULLIF(referrer, ''), '(direct)')"),
    ("Devices", "app_hit_daily", "device"),
    ("Countries (their own totals, days counted with the detail on only)", "app_hit_country_daily", "country"),
]


def _since(days: int) -> str:
    return f"(now() AT TIME ZONE 'UTC')::date - {int(days) - 1}"


def report(conn, days: int = 30, top: int = 20) -> str:
    out: list[str] = []
    totals = conn.execute(
        f"""SELECT coalesce(sum(hits) FILTER (WHERE day >= {_since(7)}), 0) AS w,
                   coalesce(sum(hits), 0) AS n
              FROM app_hit_daily WHERE day >= {_since(days)}""").fetchone()
    out.append(f"Page views: last 7 days {totals['w']:,}, last {days} days {totals['n']:,}")
    for title, table, expr in TABLES:
        rows = conn.execute(
            f"""SELECT {expr} AS k, sum(hits) FILTER (WHERE day >= {_since(7)}) AS w, sum(hits) AS n
                  FROM {table} WHERE day >= {_since(days)}
                 GROUP BY 1 ORDER BY n DESC, k LIMIT %s""", (top,)).fetchall()
        out.append(_table(f"{title}, top {top}", ["", "7 days", f"{days} days"],
                          [[r["k"], f"{r['w'] or 0:,}", f"{r['n']:,}"] for r in rows]))
    rows = conn.execute(
        f"""SELECT day, sum(hits) AS n, sum(hits) FILTER (WHERE device = 'mobile') AS m
              FROM app_hit_daily WHERE day >= {_since(days)} GROUP BY day ORDER BY day DESC""").fetchall()
    out.append(_table("Daily totals", ["day", "views", "of which mobile"],
                      [[str(r["day"]), f"{r['n']:,}", f"{r['m'] or 0:,}"] for r in rows]))
    return "\n\n".join(out) + "\n"


def _table(title: str, head: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return f"{title}\n  (none)"
    cells = [head, *rows]
    width = [max(len(r[i]) for r in cells) for i in range(len(head))]
    lines = ["  ".join(c.ljust(width[0]) if i == 0 else c.rjust(width[i]) for i, c in enumerate(r)) for r in cells]
    return "\n".join([title, *("  " + line for line in lines)])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m dgate.ops.stats", description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=30, choices=range(1, 367), metavar="1..366")
    ap.add_argument("--top", type=int, default=20, choices=range(1, 501), metavar="1..500")
    a = ap.parse_args(argv)
    with db.connect(settings().dsn) as conn:
        conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        conn.execute("SET statement_timeout = '30s'")
        try:
            text = report(conn, a.days, a.top)
        finally:
            conn.rollback()
    sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
