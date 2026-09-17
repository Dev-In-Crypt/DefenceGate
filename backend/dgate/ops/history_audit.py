"""Did the history load actually get everything?

The load walks one publication day at a time, and a day that comes back short
is indistinguishable from a quiet day: both are just a number. The only
independent evidence is the source's own count over a wider window, which the
API gives for free -- `totalNoticeCount` on a query costs one request whatever
the window.

So this compares, month by month, the notices we recorded for each day against
what TED says the whole month holds. Agreement across a month is evidence no
day inside it was cut short; disagreement names the month to reload.

    python -m dgate.ops.history_audit                       every loaded month
    python -m dgate.ops.history_audit --from 2019-01 --to 2019-12
    python -m dgate.ops.history_audit --reset-mismatched    forget those months,
                                                            so the loader asks
                                                            for their days again
"""

from __future__ import annotations

import argparse
import calendar
import logging
import sys
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterator

from .. import db
from ..config import settings

log = logging.getLogger("history-audit")

SOURCE_CODE = "ted"


@dataclass
class Month:
    first: date
    last: date
    loaded: int
    days_loaded: int
    reported: int | None

    @property
    def complete(self) -> bool:
        """A month nobody can count is not a month that disagrees."""
        return self.reported is None or self.loaded == self.reported

    @property
    def missing(self) -> int:
        return 0 if self.reported is None else self.reported - self.loaded

    def __str__(self) -> str:
        verdict = "ok" if self.complete else f"MISSING {self.missing}"
        return (f"{self.first:%Y-%m}  loaded {self.loaded:>7} over {self.days_loaded:>2} days"
                f"  api {self.reported if self.reported is not None else '-':>7}  {verdict}")


def loaded_months(conn: Any, start: date | None = None,
                  end: date | None = None) -> list[tuple[date, int, int]]:
    """Per month: the first day, what we recorded, and how many days we have."""
    rows = conn.execute(
        """SELECT date_trunc('month', day)::date AS first,
                  sum(notices)::int              AS loaded,
                  count(*)::int                  AS days
             FROM backfill_day
            WHERE source_code = %s
              AND (%s::date IS NULL OR day >= %s)
              AND (%s::date IS NULL OR day <= %s)
         GROUP BY 1 ORDER BY 1""",
        (SOURCE_CODE, start, start, end, end),
    ).fetchall()
    return [(row["first"], row["loaded"], row["days"]) for row in rows]


def reported_total(first: date, last: date, client: Any = None) -> int | None:
    """What TED says the window holds, in one request."""
    from ..sources import ted

    query = (f"publication-date>={first:%Y%m%d} AND "
             f"publication-date<={last:%Y%m%d}")
    payload = {"query": query, "fields": ["publication-number"],
               "page": 1, "limit": 1, "scope": "ALL"}
    if client is None:
        import httpx

        from ..sources import USER_AGENT

        with httpx.Client(headers={"User-Agent": USER_AGENT}) as owned:
            data = ted._post(owned, payload)
    else:
        data = ted._post(client, payload)
    return data.get("totalNoticeCount") or data.get("total")


def audit(conn: Any, start: date | None = None, end: date | None = None,
          client: Any = None) -> Iterator[Month]:
    for first, loaded, days in loaded_months(conn, start, end):
        last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
        yield Month(first, last, loaded, days, reported_total(first, last, client))


def forget(conn: Any, months: list[Month]) -> int:
    """Delete the day markers of the named months, so the loader asks again.

    Only the markers: the payloads already landed stay where they are, and a
    reload of a day whose content has not changed writes no second version.
    """
    removed = 0
    for month in months:
        removed += conn.execute(
            "DELETE FROM backfill_day WHERE source_code = %s AND day BETWEEN %s AND %s",
            (SOURCE_CODE, month.first, month.last),
        ).rowcount
    conn.commit()
    return removed


def _month(value: str) -> date:
    return date.fromisoformat(f"{value}-01")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="dgate-history-audit")
    parser.add_argument("--from", dest="start", type=_month, default=None,
                        help="first month, YYYY-MM")
    parser.add_argument("--to", dest="end", type=_month, default=None,
                        help="last month, YYYY-MM")
    parser.add_argument("--reset-mismatched", action="store_true",
                        help="forget the day markers of months that disagree")
    args = parser.parse_args(argv)

    end = None
    if args.end is not None:
        end = args.end.replace(day=calendar.monthrange(args.end.year, args.end.month)[1])

    with db.connect(settings().dsn) as conn:
        months = list(audit(conn, args.start, end))
        for month in months:
            print(month)
        bad = [m for m in months if not m.complete]
        print(f"{len(months)} months checked, {len(bad)} incomplete, "
              f"{sum(m.missing for m in bad)} notices missing")
        if bad and args.reset_mismatched:
            print(f"forgot {forget(conn, bad)} day markers; the loader will ask again")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
