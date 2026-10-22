"""Read-only report (WP-61): how many awards TED and PLACSP both publish, how the twin rule matched them, what it may
have missed, and how long the supplier map takes with the PLACSP winners on. Writes nothing.

    python -m dgate.ops.supplier_twins              # the counts
    python -m dgate.ops.supplier_twins --time       # and the three endpoints timed, with the PLACSP switch on
    python -m dgate.ops.supplier_twins --refresh    # how far the stored pairs are from the view (WP-75)
    python -m dgate.ops.supplier_twins --refresh --yes   # rewrite them (worker container: its role writes)

Run it in the API container (its role reads only): `--time` calls the endpoints in-process with
DGATE_PLACSP_AWARDS_PUBLIC=true for this process alone; the running API is not touched. The map reads the pairs
from `award_twin_set` (migration 0098), which the award loads and the worker rewrite; `--refresh --yes` is for
a load run by hand outside them.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

from .. import db
from ..config import settings

# Procedures both sources publish, where each side names exactly one winner and the twin rule found no pair: the
# candidates for a winner the cascade put on two organisations without a shared number (read them by hand).
MISSED = """
WITH s AS (SELECT id, code FROM source WHERE code IN ('ted', 'es_placsp', 'es_placsp_agg')),
one AS (SELECT a.id, o.procedure_identifier AS pid, s.code = 'ted' AS is_ted
          FROM award a JOIN opportunity o ON o.id = a.opportunity_id JOIN s ON s.id = o.source_id
         WHERE a.superseded_at IS NULL AND a.excluded_reason IS NULL AND o.procedure_identifier IS NOT NULL
           AND a.winners_in_notice = 1)
SELECT count(*) AS n FROM one t JOIN one p ON p.pid = t.pid AND t.is_ted AND NOT p.is_ted
 WHERE NOT EXISTS (SELECT 1 FROM award_twin w WHERE (w.award_id, w.preferred_id) IN ((t.id, p.id), (p.id, t.id)))"""


def report(conn) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["twins"] = [dict(r) for r in conn.execute(
        """SELECT procedure_method, winner_method, count(*) AS n FROM award_twin GROUP BY 1, 2 ORDER BY 1, 2""")]
    out["dropped_by_source"] = [dict(r) for r in conn.execute(
        """SELECT s.code, count(DISTINCT tw.award_id) AS n FROM award_twin tw JOIN award a ON a.id = tw.award_id
             JOIN opportunity o ON o.id = a.opportunity_id JOIN source s ON s.id = o.source_id GROUP BY 1 ORDER BY 1""")]
    # A pair filed under two CPV divisions: a CPV filter finds the award under the preferred row's division only.
    out["cpv_division_differs"] = conn.execute(
        """SELECT count(*) AS n FROM award_twin tw JOIN award d ON d.id = tw.award_id JOIN award k ON k.id = tw.preferred_id
            WHERE left(d.cpv_main, 2) IS DISTINCT FROM left(k.cpv_main, 2)""").fetchone()["n"]
    out["single_winner_pairs_not_matched"] = conn.execute(MISSED).fetchone()["n"]
    return out


PAIR_COLUMNS = "award_id, preferred_id, procedure_method, winner_method"


def refresh(conn, *, write: bool = False) -> dict[str, int]:
    """The stored pairs against the view: how many are stored, how many the view gives, how many differ; with
    `write`, the stored ones rewritten (`awards.refresh_award_twins`) and committed."""
    from ..awards import refresh_award_twins

    out = {k: conn.execute(f"SELECT count(*) AS n FROM ({q}) d").fetchone()["n"] for k, q in {
        "stored": "SELECT 1 FROM award_twin_set",
        "view": "SELECT 1 FROM award_twin",
        "differ": f"""(SELECT {PAIR_COLUMNS} FROM award_twin EXCEPT SELECT {PAIR_COLUMNS} FROM award_twin_set)
                      UNION ALL
                      (SELECT {PAIR_COLUMNS} FROM award_twin_set EXCEPT SELECT {PAIR_COLUMNS} FROM award_twin)"""}.items()}
    if write:
        out["written"] = refresh_award_twins(conn)
        conn.commit()
    return out


def timings() -> dict[str, float]:
    """The three endpoints in-process, the switch on for this process, the list cache off: cold timings."""
    os.environ["DGATE_PLACSP_AWARDS_PUBLIC"] = "true"
    os.environ["DGATE_LIST_CACHE_SECONDS"] = "0"
    os.environ["DGATE_RATE_LIMIT"] = "0"
    from ..config import reset_cache

    reset_cache()
    from fastapi.testclient import TestClient

    from .. import api

    got: dict[str, float] = {}
    with TestClient(api.app) as client:
        for path in ("/v1/suppliers", "/v1/suppliers?country=ES", "/v1/suppliers/summary"):
            started = time.monotonic()
            r = client.get(path)
            got[path] = round(time.monotonic() - started, 3)
            if path == "/v1/suppliers?country=ES" and r.status_code == 200 and r.json()["items"]:
                slug = r.json()["items"][0]["slug"]
                started = time.monotonic()
                client.get(f"/v1/suppliers/{slug}")
                got[f"/v1/suppliers/{slug}"] = round(time.monotonic() - started, 3)
    return got


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dgate.ops.supplier_twins", description=__doc__.split("\n\n")[0])
    p.add_argument("--time", action="store_true", help="also time the endpoints with the PLACSP switch on")
    p.add_argument("--refresh", action="store_true", help="compare the stored twin pairs with the view")
    p.add_argument("--yes", action="store_true", help="with --refresh: rewrite the stored pairs")
    a = p.parse_args(argv)
    if a.refresh:
        with db.connect(settings().dsn) as conn:
            print("award_twin_set", refresh(conn, write=a.yes), "" if a.yes else "(dry run: --yes to write)")
        return 0
    with db.connect(settings().dsn) as conn:
        conn.execute("SET default_transaction_read_only = on")
        conn.execute("SET statement_timeout = '30s'")
        conn.commit()                         # the next transaction, the report's, is read-only
        for k, v in report(conn).items():
            print(k, v)
    if a.time:
        for k, v in timings().items():
            print("time", k, v, "s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
