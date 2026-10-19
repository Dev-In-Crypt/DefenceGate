"""Pre-compute the slow tender views and keep them in `list_snapshot` (speed, 17 October 2026).

The closed and the "all" lists cost seconds on a cold read (a quarter of a million notices, collapsed),
and the API's budget is five. This computes what people open: for status closed and all, no country and
every country that has defence notices, the first three pages, and the scope counts beside them. The
totals in them are exact (`tenders.EXACT_TOTALS`; the live list stops counting at 10,000 and says so, and a
deeper page of the same filters repeats the exact total from here). Open lists and their counts are not
kept: a few thousand rows, read live, so that the counts beside a list are the list's own at the same
time (WP-52, T13). Also kept here: the sitemap's tender and buyer slugs (T15), and the buyer aggregate, a
pass over every core notice that the buyer pages and the directory read (T14). The API
(`listcache.cache_list` with `snapshot=True`) reads a row by key when its memory has no answer. Derived data:
a snapshot never replaces the live query for a filter that was not computed, and an old one (over
`SNAPSHOT_HOURS`) is ignored.

Rows of countries that no longer have notices are deleted (this table only). The body is the
endpoint's own response, so the page cannot differ from what the live query would say, apart
from its age.

    python -m dgate.ops.warm_lists            # report what would be computed
    python -m dgate.ops.warm_lists --yes
"""

from __future__ import annotations

import argparse
import inspect
import logging
import sys
import time

from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb

from .. import changes, db, tenders
from ..config import settings
from ..listcache import snapshot_key, stored

log = logging.getLogger("warm_lists")

TENDER_PAGE_SIZE = 10          # the page size of the site (web/lib/filters.ts)
PAGES = (1, 2, 3)
LIST_STATUSES = ("closed", "all")
COUNT_STATUSES = ("closed", "all")
CHANGE_PAGE_SIZES = (25, 100)  # the page (web/lib/filters.ts CHANGE_PAGE_SIZE) and the Atom feed


def _defaults(endpoint) -> dict:
    """Every parameter of the endpoint at its default (FastAPI passes them all, so the key a
    request builds names them all)."""
    out = {}
    for name, p in inspect.signature(endpoint).parameters.items():
        if name == "conn":
            continue
        d = p.default
        out[name] = getattr(d, "default", d) if hasattr(d, "default") else d
    return out


def views(countries: list[str]) -> list[tuple[str, str, dict]]:
    """(endpoint name, snapshot key, arguments) of every view to compute."""
    out = []
    for fn, name in ((tenders.list_tenders, "tenders"), (tenders.tender_scope_counts, "tender-scope-counts")):
        base = _defaults(fn.__wrapped__)
        if "with_meta" in base:
            base["with_meta"] = True
        for status in (LIST_STATUSES if name == "tenders" else COUNT_STATUSES):
            for country in [None, *countries]:
                kw = {**base, "status": status, "country": country}
                if name == "tender-scope-counts":
                    out.append((name, snapshot_key(name, kw), kw))
                    continue
                for page in PAGES:
                    kw2 = {**kw, "page": page, "pageSize": TENDER_PAGE_SIZE}
                    out.append((name, snapshot_key(name, kw2), kw2))
    base = _defaults(changes.list_changes.__wrapped__)
    base["with_meta"] = True
    for size in CHANGE_PAGE_SIZES:
        kw = {**base, "pageSize": size}
        out.append(("changes", snapshot_key("changes", kw), kw))
    out.append(("buyer-base", tenders.BUYER_BASE_KEY, {}))        # before the slugs, which read it
    for name in ("tender-slugs", "buyer-slugs"):
        out.append((name, snapshot_key(name, {}), {}))
    return out


def run(conn, *, write: bool = False) -> dict[str, int]:
    countries = [r["country"] for r in conn.execute(
        """SELECT DISTINCT country FROM opportunity
            WHERE is_defence AND NOT suppressed AND country IS NOT NULL ORDER BY country""").fetchall()]
    todo = views(countries)
    done = failed = 0
    kept: list[str] = []
    exact = tenders.EXACT_TOTALS.set(True)
    try:
        done, failed = _write_views(conn, todo, kept, write)
    finally:
        tenders.EXACT_TOTALS.reset(exact)
    removed = 0
    if write and kept:
        removed = len(conn.execute("DELETE FROM list_snapshot WHERE key <> ALL(%s) RETURNING 1",
                                   (kept,)).fetchall())
        conn.commit()
    return {"views": len(todo), "written": done, "failed": failed, "removed": removed}


FUNCTIONS = {"tenders": tenders.list_tenders, "changes": changes.list_changes,
             "tender-slugs": tenders.tender_slugs, "buyer-slugs": tenders.buyer_slugs}


def _write_views(conn, todo, kept: list[str], write: bool) -> tuple[int, int]:
    done = failed = 0
    for name, key, kw in todo:
        kept.append(key)
        if not write:
            continue
        fn = FUNCTIONS.get(name, tenders.tender_scope_counts)
        try:
            if name == "buyer-base":
                # One pass over every core notice, tested for twins (seconds): the buyer pages read it.
                body = jsonable_encoder(tenders.compute_buyer_base(conn, exact=True))
            else:
                body = jsonable_encoder(fn.__wrapped__(**kw, conn=conn))
            conn.execute(
                """INSERT INTO list_snapshot (key, body, computed_at) VALUES (%s, %s, now())
                   ON CONFLICT (key) DO UPDATE SET body = EXCLUDED.body, computed_at = EXCLUDED.computed_at""",
                (key, Jsonb(stored(body))))
            conn.commit()
            done += 1
        except Exception:  # noqa: BLE001 - one view failing leaves the older snapshot, not the job
            conn.rollback()
            failed += 1
            log.exception("view %s failed", key)
    return done, failed


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="warm-lists", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="compute and write (default: report)")
    a = p.parse_args(argv)
    started = time.monotonic()
    with db.connect(settings().dsn) as conn:
        result = run(conn, write=a.yes)
    print(result, f"{time.monotonic() - started:.0f}s")
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
