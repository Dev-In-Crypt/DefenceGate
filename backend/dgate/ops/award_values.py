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

WP-103 (persona round of 24 October 2026):

    python -m dgate.ops.award_values --all          # step 1 for every TED notice with winners, not only those without
                                                    # a kind: the kinds a --no-fetch run took from the titles are
                                                    # asked again (asks TED; refused with --no-fetch)

  3. (no TED request) TED notices whose held figure its own estimate contradicts (`award_value.contradicted`, a billion
     or more and over a hundred times the estimate): the estimate stands as the value, kind estimate, and the figure is
     kept in `award_notice.value_set_aside`.
  4. (no TED request) PLACSP award rows held as a framework ceiling whose title reads as a call-off under the widened
     rule ("CB Cuarto AM", "5º Basado AM", "CB Nº2 Acuerdo Marco"): a contract.
  5. (WP-119, no TED request) every figure set aside by the lots or the procedure check is checked again under the
     narrowed rules (`award_value.unit_error_of`: a lot sum replaces a total only when the total is a clean unit
     error of it; a procedure's estimate below a billion only so too): where they no longer choose the standing
     value, the set-aside original (`award_notice.value_set_aside`) stands again. Expected on production (25 October
     2026, read-only): 12 notices, 12 award rows (Marine Alutech 676175-2026 and 639939-2025 EUR 76 m / 35 m again,
     Surcom, Embraer, PIT-RADWAR, CONCEPT, WIL, DSA, 494823-2026, 175814-2025, 542411-2026, and 451107-2025 the
     framework of EUR 22,922,861); FASER, 107790-2025, 677494-2026, 313429-2026, 142545-2026 and INCM stay set aside.
  After a write the supplier value orders are renewed (`awards.refresh_award_twins`).

Expected on production (read-only counts of 24 October 2026, docs/verification/round3/wp103-selfcheck.md): step 3
World Aviation 220199-2026 (EUR 7,274,615,930 set aside, EUR 7,317,073.17 estimate); step 4 the 29 Indra call-offs of
persona p07 (EUR 59.5 m back in Indra's contract sum) among the PLACSP rows held as framework; --all STRABAG 638010-2024
(EUR 280 m) and Arquus 38915-2026 (EUR 2,449,392,735) framework ceilings, about 90 requests for the 8,887 TED notices
with winners.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from typing import Any

from .. import db
from ..award_set import PLACSP_IDS
from ..award_value import (
    CONTRACT,
    ESTIMATE,
    FRAMEWORK,
    SET_ASIDE_ESTIMATE,
    SET_ASIDE_LOTS,
    SET_ASIDE_PROCEDURE,
    TED_VALUE_FIELDS,
    THOUSANDFOLD_FROM,
    _checked,
    _usable,
    contradicted,
    kind_of_title,
    placsp_kind,
    procedure_set_aside,
    ted_value,
    ted_value_set_aside,
    ted_value_set_aside_reason,
)
from ..awards import VALUE_COLUMNS, refresh_award_twins
from ..config import settings
from ..placsp_awards import framework_of
from ..sources import USER_AGENT, new_client, ted

_TED_ROWS = f"""SELECT n.opportunity_id AS id, o.native_id, n.value_amount AS n_va, n.value_currency AS n_vc,
                       n.value_kind AS n_vk, n.value_set_aside AS n_sa, n.value_set_aside_reason AS n_sr,
                       n.winners_seen, {VALUE_COLUMNS}
                  FROM award_notice n JOIN opportunity o ON o.id = n.opportunity_id
                 WHERE o.source_id = (SELECT id FROM source WHERE code = 'ted')"""


def _ted_rows(conn, every: bool = False) -> list[dict[str, Any]]:
    # not derived yet: a loaded or written kind is never replaced, unless `every` (WP-103 --all: asked again)
    pending = "" if every else " AND n.value_kind IS NULL"
    return conn.execute(f"{_TED_ROWS} AND n.winners_kept > 0{pending} ORDER BY n.opportunity_id").fetchall()


def _same(held: Any, new: float | None) -> bool:
    return held is None if new is None else held is not None and float(held) == new


def _write_ted(conn, r: dict[str, Any], value: tuple, c: Counter, write: bool, set_aside: float | None = None,
               reason: str | None = None) -> None:
    va, vc, vk = value
    reason = reason if set_aside is not None else None
    same = (r["n_vk"] == vk and r["n_vc"] == vc and _same(r["n_va"], va) and _same(r.get("n_sa"), set_aside)
            and r.get("n_sr") == reason)
    c[f"ted_{vk or 'none'}"] += 1
    if reason:
        c[f"ted_set_aside_{reason}"] += 1
    if same:
        return
    c["ted_notices_changed"] += 1
    if r["n_vk"] and vk != r["n_vk"]:
        c[f"ted_{r['n_vk']}_to_{vk or 'none'}"] += 1
    if not write:
        return
    conn.execute("UPDATE award_notice SET value_amount = %s, value_currency = %s, value_kind = %s, value_set_aside = %s, "
                 "value_set_aside_reason = %s WHERE opportunity_id = %s", (va, vc, vk, set_aside, reason, r["id"]))
    if r["winners_seen"] == 1:
        c["ted_award_rows"] += conn.execute(
            """UPDATE award SET value_amount = %s, value_currency = %s, value_kind = %s
                WHERE opportunity_id = %s AND (value_amount IS DISTINCT FROM %s::numeric
                      OR value_currency IS DISTINCT FROM %s OR value_kind IS DISTINCT FROM %s)""",
            (va, vc, vk, r["id"], va, vc, vk)).rowcount


def run_ted(conn, *, fetch: bool, write: bool, pause: float = 1.0, examples: list[str] | None = None,
            every: bool = False) -> Counter:
    c: Counter = Counter()
    rows = _ted_rows(conn, every)
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
                _write_ted(conn, r, value, c, write, ted_value_set_aside(rec, r), ted_value_set_aside_reason(rec, r))
            if write:
                conn.commit()
    finally:
        if client is not None:
            client.close()
    return c


def run_set_aside(conn, *, write: bool, examples: list[str] | None = None) -> Counter:
    """WP-103, step 3: a held TED figure that the notice's own estimate contradicts is set aside; the estimate stands.
    WP-108: and one implausible against the estimate another notice of its procedure states
    (`award_value.procedure_set_aside`); that estimate stands, as an estimate."""
    c: Counter = Counter()
    rows = conn.execute(f"""{_TED_ROWS} AND n.value_kind IN ('{CONTRACT}', '{FRAMEWORK}')
                             AND n.value_amount >= {THOUSANDFOLD_FROM} ORDER BY n.opportunity_id""").fetchall()
    for r in rows:
        held = float(r["n_va"])
        if contradicted(held, r):
            reason, value = SET_ASIDE_ESTIMATE, (float(r["value_amount"]), r["value_currency"], ESTIMATE)
        else:
            proc = procedure_set_aside(held, r, r["n_vc"])
            if proc is None:
                continue
            reason, value = SET_ASIDE_PROCEDURE, (*proc, ESTIMATE)
        c["ted_values_set_aside"] += 1
        c[f"ted_values_set_aside_{reason}"] += 1
        if examples is not None and len(examples) < 40:
            examples.append(f"{r['native_id']}: {r['n_vk']} {r['n_va']} {r['n_vc']} set aside ({reason}), "
                            f"{value[0]} {value[1]} stands")
        _write_ted(conn, r, value, Counter(), write, held, reason)
    if write:
        conn.commit()
    return c


def run_recheck(conn, *, write: bool, examples: list[str] | None = None) -> Counter:
    """WP-119, step 5 (no TED request): every figure set aside by the lots or the procedure check is checked again under
    today's rules from what the row holds (the set-aside figure is the notice's original; for `lots` the value standing
    is the sum of the parts). Where the rules no longer choose the standing value, the original stands again (or what the
    other checks now choose for it), and the award row of a one-winner notice with it. A kind the procedure check
    replaced by `estimate` is read again from the title (`kind_of_title`), as for a notice without eForms fields."""
    c: Counter = Counter()
    rows = conn.execute(f"""{_TED_ROWS} AND n.value_set_aside_reason IN ('{SET_ASIDE_LOTS}', '{SET_ASIDE_PROCEDURE}')
                             ORDER BY n.opportunity_id""").fetchall()
    for r in rows:
        held, cur = float(r["n_sa"]), r["n_vc"]
        stored = float(r["value_amount"]) if r["value_amount"] is not None else None
        estimate = (stored, cur, ESTIMATE) if _usable(stored) and cur else (None, None, None)
        if r["n_sr"] == SET_ASIDE_LOTS:
            parts, kind = float(r["n_va"]), r["n_vk"]
        else:
            parts, kind = None, kind_of_title(r["title_original"], r["title_en"]) or CONTRACT
        out = _checked(held, cur, kind, parts, r, estimate)
        c[f"recheck_{r['n_sr']}"] += 1
        if (out[3], out[4]) == (held, r["n_sr"]):
            continue
        c[f"recheck_{r['n_sr']}_restored"] += 1
        if examples is not None:
            examples.append(f"{r['native_id']}: {r['n_va']} {r['n_vc']} {r['n_vk']} ({r['n_sr']}) -> {out[0]} {out[1]} "
                            f"{out[2]}" + (f", {out[3]} set aside ({out[4]})" if out[3] is not None else ""))
        w: Counter = Counter()
        _write_ted(conn, r, out[:3], w, write, out[3], out[4])
        c["recheck_award_rows"] += w["ted_award_rows"]
    if write:
        conn.commit()
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
        elif r["value_kind"] == FRAMEWORK and kind_of_title(r["title_original"]) == CONTRACT:
            # WP-103, step 4: a call-off the narrower title rule of WP-95 read as its framework's ceiling
            c["placsp_call_offs_framework_to_contract"] += 1
            c["placsp_call_offs_amount_eur"] += round(float(r["value_amount"]))
            if write:
                conn.execute("UPDATE award SET value_kind = %s WHERE id = %s", (CONTRACT, r["id"]))
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
    p.add_argument("--all", action="store_true", help="WP-103: ask TED again for every notice with winners, not only "
                                                      "those without a kind (needs the fetch)")
    a = p.parse_args(argv)
    if a.all and a.no_fetch:
        p.error("--all asks TED again; it cannot run with --no-fetch")
    examples: list[str] = []
    links: list[str] = []
    set_aside: list[str] = []
    rechecked: list[str] = []
    with db.connect(settings().dsn) as conn:
        c = run_ted(conn, fetch=not a.no_fetch, write=a.yes, examples=examples, every=a.all)
        c.update(run_recheck(conn, write=a.yes, examples=rechecked))
        c.update(run_set_aside(conn, write=a.yes, examples=set_aside))
        c.update(run_placsp(conn, write=a.yes, examples=links))
        if a.yes:
            c["award_twin_pairs"] = refresh_award_twins(conn)      # and the supplier value orders (WP-98c)
            conn.commit()
        else:
            conn.rollback()
    print("written" if a.yes else "report only (add --yes to write)")
    for k in sorted(c):
        print(f"  {k}: {c[k]}")
    if examples:
        print("TED ceilings and estimates (first 15):")
        for e in examples:
            print("  " + e)
    if rechecked:
        print("TED set-asides the rules of WP-119 no longer choose (every one):")
        for e in rechecked:
            print("  " + e)
    if set_aside:
        print("TED figures set aside as implausible (first 40):")
        for e in set_aside:
            print("  " + e)
    if links:
        print("PLACSP call-offs linked to their framework (first 30):")
        for e in links:
            print("  " + e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
