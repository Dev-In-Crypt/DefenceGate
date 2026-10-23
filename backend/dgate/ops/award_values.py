"""Owner-run: the kind of every award value already held, and the frameworks of call-offs (WP-95, A1.1).

    python -m dgate.ops.award_values                # report: what would change (asks TED: run on the server)
    python -m dgate.ops.award_values --yes          # write
    python -m dgate.ops.award_values --no-fetch     # no TED request: the kinds the stored values and titles give

What it does, each step idempotent (a second run writes nothing):

  1. TED result notices with winners held (`award_notice`) and no kind yet: their value fields (`award_value.TED_VALUE_FIELDS`) are
     asked by publication number, a hundred a request, one request a second, and `award_value.ted_value` gives the
     notice's value and kind: `award_notice.value_*`, and `award.value_*` of a notice naming one winner. With
     `--no-fetch` the stored value is read as the mapper chose it (a total a contract value unless the title says
     framework, a sum of lot estimates an estimate): the eForms framework maxima are found only by asking.
  2. PLACSP award rows with an awarded amount and no kind yet: the kind from the title (`award_value.placsp_kind`: a framework agreement
     or dynamic purchasing system is a ceiling, a contrato basado a contract); the landed payloads before WP-95 carry
     no contracting-system code. A call-off whose title quotes its framework's file number gets `framework_id`.

Expected effect (persona audit of 23 October 2026): Rheinmetall Landsysteme 390572-2026 (EUR 11.93 m) and Safran
854350-2025 (DKK 97 m) become framework ceilings; 712069-2026 (EUR 1.16 m) an estimate; the MADZEAL IVECO framework
(TED 389204-2026 / PLACSP 2025/AR43U/00001894E) a ceiling with its call-off 2026/AR43U/00002206E linked to it. The
contract sums of the suppliers fall by what those were; the ceilings and estimates are shown apart.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from typing import Any

from .. import db
from ..award_set import PLACSP_IDS
from ..award_value import TED_VALUE_FIELDS, placsp_kind, ted_value
from ..awards import VALUE_COLUMNS
from ..config import settings
from ..placsp_awards import framework_of
from ..sources import USER_AGENT, new_client, ted


def _ted_rows(conn) -> list[dict[str, Any]]:
    return conn.execute(
        f"""SELECT n.opportunity_id AS id, o.native_id, n.value_amount AS n_va, n.value_currency AS n_vc,
                   n.value_kind AS n_vk, n.winners_seen, {VALUE_COLUMNS}
              FROM award_notice n JOIN opportunity o ON o.id = n.opportunity_id
             WHERE o.source_id = (SELECT id FROM source WHERE code = 'ted') AND n.winners_kept > 0
               AND n.value_kind IS NULL           -- not derived yet: a loaded or written kind is never replaced
             ORDER BY n.opportunity_id""").fetchall()


def _write_ted(conn, r: dict[str, Any], value: tuple, c: Counter, write: bool) -> None:
    va, vc, vk = value
    same = (r["n_vk"] == vk and r["n_vc"] == vc
            and (r["n_va"] is None if va is None else r["n_va"] is not None and float(r["n_va"]) == va))
    c[f"ted_{vk or 'none'}"] += 1
    if same:
        return
    c["ted_notices_changed"] += 1
    if not write:
        return
    conn.execute("UPDATE award_notice SET value_amount = %s, value_currency = %s, value_kind = %s "
                 "WHERE opportunity_id = %s", (va, vc, vk, r["id"]))
    if r["winners_seen"] == 1:
        c["ted_award_rows"] += conn.execute(
            """UPDATE award SET value_amount = %s, value_currency = %s, value_kind = %s
                WHERE opportunity_id = %s AND (value_amount IS DISTINCT FROM %s::numeric
                      OR value_currency IS DISTINCT FROM %s OR value_kind IS DISTINCT FROM %s)""",
            (va, vc, vk, r["id"], va, vc, vk)).rowcount


def run_ted(conn, *, fetch: bool, write: bool, pause: float = 1.0, examples: list[str] | None = None) -> Counter:
    c: Counter = Counter()
    rows = _ted_rows(conn)
    c["ted_notices"] = len(rows)
    client = new_client(headers={"User-Agent": USER_AGENT}) if fetch else None
    try:
        for i in range(0, len(rows), ted.AWARD_BATCH):
            batch = [r for r in rows[i:i + ted.AWARD_BATCH] if ted.PUBLICATION_NUMBER.fullmatch(r["native_id"])]
            got: dict[str, dict[str, Any]] = {}
            if fetch and batch:
                if i:
                    time.sleep(pause)
                got = ted.fetch_by_numbers([r["native_id"] for r in batch], fields=["publication-number"]
                                           + TED_VALUE_FIELDS, client=client)
            for r in batch:
                rec = got.get(r["native_id"]) if fetch else None
                if fetch and rec is None:
                    c["ted_not_returned"] += 1
                    continue
                value = ted_value(rec, r)
                if examples is not None and value[2] in ("framework", "estimate") and len(examples) < 15:
                    examples.append(f"{r['native_id']}: {value[2]} {value[0]} {value[1]} (stored {r['value_amount']} "
                                    f"{r['value_kind']})")
                _write_ted(conn, r, value, c, write)
            if write:
                conn.commit()
    finally:
        if client is not None:
            client.close()
    return c


def run_placsp(conn, *, write: bool, examples: list[str] | None = None) -> Counter:
    c: Counter = Counter()
    rows = conn.execute(
        f"""SELECT a.id, a.opportunity_id, a.value_amount, a.value_kind, o.title_original, o.native_id,
                   n.framework_id
              FROM award a JOIN opportunity o ON o.id = a.opportunity_id
              LEFT JOIN award_notice n ON n.opportunity_id = a.opportunity_id
             WHERE o.source_id IN {PLACSP_IDS} AND a.superseded_at IS NULL
             ORDER BY a.opportunity_id, a.id""").fetchall()
    c["placsp_award_rows"] = len(rows)
    seen: set[int] = set()
    for r in rows:
        if r["value_amount"] is not None and r["value_kind"] is None:   # a kind already derived stays
            kind = placsp_kind(None, r["title_original"])
            c[f"placsp_{kind}"] += 1
            if kind != r["value_kind"]:
                c["placsp_rows_changed"] += 1
                if write:
                    conn.execute("UPDATE award SET value_kind = %s WHERE id = %s", (kind, r["id"]))
        if r["opportunity_id"] in seen:
            continue
        seen.add(r["opportunity_id"])
        fw = framework_of(conn, r["opportunity_id"], r["title_original"])
        if fw is not None:
            c["placsp_call_offs_linked"] += 1
            if examples is not None and len(examples) < 30:
                examples.append(f"{r['native_id']} -> framework notice {fw}")
        if fw is not None and r["framework_id"] is None:
            c["placsp_framework_links_new"] += 1
            if write:
                conn.execute("UPDATE award_notice SET framework_id = %s WHERE opportunity_id = %s",
                             (fw, r["opportunity_id"]))
    if write:
        conn.commit()
    return c


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dgate.ops.award_values", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write (the default is a report)")
    p.add_argument("--no-fetch", action="store_true", help="ask TED nothing: the stored values and titles only")
    a = p.parse_args(argv)
    examples: list[str] = []
    links: list[str] = []
    with db.connect(settings().dsn) as conn:
        c = run_ted(conn, fetch=not a.no_fetch, write=a.yes, examples=examples)
        c.update(run_placsp(conn, write=a.yes, examples=links))
        if not a.yes:
            conn.rollback()
    print("written" if a.yes else "report only (add --yes to write)")
    for k in sorted(c):
        print(f"  {k}: {c[k]}")
    if examples:
        print("TED ceilings and estimates (first 15):")
        for e in examples:
            print("  " + e)
    if links:
        print("PLACSP call-offs linked to their framework (first 30):")
        for e in links:
            print("  " + e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
