"""Correct what the buyer-resolution defects of 13 October 2026 left in the organisation table.

Three things, each idempotent, each written down on the row it changes. Nothing is
deleted, no archived version is touched, and no merge is undone.

1. **Unflagged namesakes** (coverage:C1). A defence body's notices that state another
   registration number than the one the flagged organisation holds were filed under a
   new, unflagged organisation of the same name: 137 organisations (41 names) on
   13 October 2026, and BOAMP 57 of 59 notices since 21 September. For each live,
   unflagged organisation whose normalised name and country equal those of a flagged one
   (or of one merged into a flagged one):

   - no registered number on either side, or the same number: merged into the flagged
     one (`merge_organisations`, method `namesake_flagged`, confidence 0.95);
   - two different numbers: flagged as a defence buyer with source `namesake`, reason
     "same name as organisation N", confidence 0.90, and left a separate row (a number is
     a body's own; `--merge-conflicting` merges them as well, the absorbed row keeping its
     number so a notice that states it still reaches the survivor);
   - the flagged one is a shared-identifier organisation (step 3): flagged only, never
     merged into, since that is the wrong merge this tool reports.

2. **Derived flags the current rules reject** (classification:D7). The flag of an
   organisation that a name rule put on the list (`defence_buyer_source = 'derived_rule'`)
   is withdrawn when the name matches an include rule and an exclusion rule now rejects it:
   the Council of Europe's "DGA" (197 notices) and France Travail's. A row a person marked
   `reviewed` in the derived files stays, and so does a seeded buyer. A flag inherited from
   a namesake (`namesake`) goes when no flagged namesake is left.

3. **Shared identifiers** (correctness:D8), read only. A registration number that belongs
   to a ministry-level legal entity was merged with every service that stated it (`merge_method
   = 'identifier'`): organisation 196441, "minarm air siae", holds 33 services and 552
   notices. `db.names_compatible` now refuses that from here on. The merges already made are
   history and stay; this lists them, with the notices whose stated name is not the holder's.

    python -m dgate.ops.buyer_cleanup                     # report, writes nothing
    python -m dgate.ops.buyer_cleanup --yes               # steps 1 and 2
    python -m dgate.ops.buyer_cleanup --yes --merge-conflicting

Run `python -m dgate.reprocess --reclassify-serving --yes` afterwards: the serving rows read
the flag, the merge and the buyer class from the organisation they point at.
"""

from __future__ import annotations

import argparse
import csv
import glob
import logging
import sys
from pathlib import Path
from typing import Any, Callable

from .. import db
from ..buyer_vocab import defence_body
from ..config import settings
from ..normalise import normalise_org_name

log = logging.getLogger("buyer_cleanup")

METHOD_MERGE = "namesake_flagged"
CONF_MERGE = 0.95
DETECTED_BY = "buyer_cleanup"

PLAN_SQL = """
SELECT DISTINCT ON (u.id)
       u.id AS uid, u.country, u.canonical_name, u.national_reg_no AS uident,
       t.id AS tid, t.national_reg_no AS tident, t.canonical_name AS tname
  FROM organisation u
  JOIN organisation n ON n.country = u.country
                     AND lower(n.canonical_name) = lower(u.canonical_name) AND n.id <> u.id
  JOIN organisation t ON t.id = COALESCE(n.merged_into, n.id)
 WHERE u.merged_into IS NULL AND NOT u.is_defence_buyer
   AND t.merged_into IS NULL AND t.is_defence_buyer AND t.id <> u.id
 ORDER BY u.id, (t.national_reg_no IS NOT DISTINCT FROM u.national_reg_no) DESC, t.id
"""


# ------------------------------------------------------- 3. shared identifiers

def shared_identifier_holders(conn) -> dict[int, dict[str, Any]]:
    """Live organisations that absorbed, by identifier, organisations whose names are not
    compatible with theirs (`db.names_compatible`). id -> holder row with `absorbed`."""
    rows = conn.execute(
        """SELECT k.id, k.canonical_name, k.country, k.national_reg_no, k.is_defence_buyer,
                  a.id AS aid, a.canonical_name AS aname
             FROM organisation a JOIN organisation k ON k.id = a.merged_into
            WHERE a.merge_method = 'identifier' AND k.merged_into IS NULL
            ORDER BY k.id, a.id""").fetchall()
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        if db.names_compatible(r["canonical_name"], r["aname"]):
            continue
        h = out.setdefault(r["id"], {
            "id": r["id"], "name": r["canonical_name"], "country": r["country"],
            "identifier": r["national_reg_no"], "flagged": bool(r["is_defence_buyer"]),
            "absorbed": []})
        h["absorbed"].append((r["aid"], r["aname"]))
    return out


def affected_notices(conn, holder: dict[str, Any]) -> list[tuple[str, int]]:
    """(stated buyer name, notices) of the holder's notices whose stated name is not
    compatible with the holder's own: the rows that stand under the wrong buyer."""
    rows = conn.execute(
        """SELECT buyer_name_raw, count(*) AS n FROM opportunity
            WHERE buyer_org_id = %s GROUP BY buyer_name_raw ORDER BY n DESC""",
        (holder["id"],)).fetchall()
    return [(r["buyer_name_raw"], r["n"]) for r in rows
            if not db.names_compatible(normalise_org_name(r["buyer_name_raw"] or ""),
                                       holder["name"])]


# ------------------------------------------------------- 1. unflagged namesakes

def namesake_plan(conn, *, merge_conflicting: bool = False,
                  umbrellas: set[int] | None = None) -> list[dict[str, Any]]:
    """What would be done to each unflagged organisation that has a flagged namesake."""
    umbrellas = umbrellas or set()
    plan = []
    for r in conn.execute(PLAN_SQL).fetchall():
        same_number = r["uident"] is None or r["tident"] is None or r["uident"] == r["tident"]
        if r["tid"] in umbrellas:
            action = "flag"
        elif same_number or merge_conflicting:
            action = "merge"
        else:
            action = "flag"
        plan.append({**r, "action": action, "conflict": not same_number})
    return plan


def apply_namesakes(conn, plan: list[dict[str, Any]], *, merge_conflicting: bool = False
                    ) -> dict[str, int]:
    done = {"merged": 0, "flagged": 0, "notices_moved": 0, "failed": 0}
    for p in plan:
        evidence = (f"{p['canonical_name']!r} in {p['country']}: same name as flagged "
                    f"organisation {p['tid']}"
                    + (f"; numbers {p['uident']} and {p['tident']}" if p["conflict"] else ""))
        try:
            with conn.transaction():
                if p["action"] == "merge":
                    moved = db.merge_organisations(
                        conn, p["tid"], p["uid"], method=METHOD_MERGE, confidence=CONF_MERGE,
                        evidence=evidence, detected_by=DETECTED_BY,
                        allow_identifier_conflict=merge_conflicting and p["conflict"])
                    done["merged"] += 1
                    done["notices_moved"] += moved["notices"]
                else:
                    conn.execute(
                        """UPDATE organisation
                              SET is_defence_buyer = TRUE, defence_buyer_source = 'namesake',
                                  defence_buyer_reason = %s, defence_buyer_confidence = %s
                            WHERE id = %s AND NOT is_defence_buyer""",
                        (f"same name as organisation {p['tid']}", db.CONF_NAMESAKE_FLAG,
                         p["uid"]))
                    if p["conflict"]:
                        db.add_merge_candidate(
                            conn, p["tid"], p["uid"], method="same_name_different_identifier",
                            confidence=0.50, evidence=evidence, detected_by=DETECTED_BY)
                    done["flagged"] += 1
            conn.commit()
        except Exception as exc:  # noqa: BLE001 - one organisation must not stop the rest
            log.error("organisation %s not handled: %s", p["uid"], exc)
            conn.rollback()
            done["failed"] += 1
    return done


# ------------------------------------------------ 2. derived flags the rules reject

def reviewed_names(directory: Path | None = None) -> set[tuple[str, str]]:
    """(country, normalised name) a person decided: derived-list rows marked reviewed, and
    every name of the hand-curated and derived seed list (`defence_buyers.csv`)."""
    from ..pipeline import SEEDS_FILE, load_seed_rows

    directory = directory or SEEDS_FILE.parent
    out: set[tuple[str, str]] = set()
    for (country, canonical), spellings in load_seed_rows().items():
        out.add((country, normalise_org_name(canonical)))
        out.update((country, normalise_org_name(raw)) for raw, _category in spellings)
    for path in sorted(glob.glob(str(directory / "defence_buyers_derived_*.csv"))):
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if (row.get("reviewed") or "").strip().lower() in ("true", "yes", "1"):
                    out.add((row["country"].strip(), normalise_org_name(row["name"])))
    return out


def rejected_flags(conn, keep: set[tuple[str, str]] | None = None) -> list[dict[str, Any]]:
    """Flagged organisations whose flag no rule or namesake supports any longer."""
    keep = keep if keep is not None else reviewed_names()
    out: list[dict[str, Any]] = []
    for r in conn.execute(
            """SELECT id, country, canonical_name, defence_buyer_source AS source
                 FROM organisation
                WHERE is_defence_buyer AND merged_into IS NULL
                  AND defence_buyer_source IN ('derived_rule', 'namesake')
                ORDER BY id""").fetchall():
        if r["source"] == "derived_rule":
            if (r["country"], r["canonical_name"]) in keep:
                continue
            body = defence_body(r["canonical_name"], r["country"])
            # Only a name that an include rule matches and an exclusion rejects: a name
            # no rule matches any more (the vocabulary was narrowed, or a person added it
            # by hand to an earlier file) is left as it is.
            if body.label is None and body.excluded_as:
                out.append({**r, "why": f"excluded as {body.excluded_as} by the name rules"})
        elif db.flagged_namesake(conn, r["id"], None, r["country"]) is None:
            out.append({**r, "why": "no flagged namesake is left"})
    return out


def unflag(conn, rows: list[dict[str, Any]]) -> int:
    n = 0
    for r in rows:
        with conn.transaction():
            n += conn.execute(
                """UPDATE organisation
                      SET is_defence_buyer = FALSE, defence_buyer_source = 'unflagged_by_rule',
                          defence_buyer_reason = left(%s, 200)
                    WHERE id = %s AND is_defence_buyer""",
                (f"was {r['source']}: {r['why']}", r["id"])).rowcount
        conn.commit()
    return n


# ------------------------------------------------------------------ driver

def run(conn, *, apply: bool = False, merge_conflicting: bool = False, top: int = 12,
        report_csv: Path | None = None, out: Callable[[str], None] = print) -> dict[str, int]:
    holders = shared_identifier_holders(conn)
    plan = namesake_plan(conn, merge_conflicting=merge_conflicting, umbrellas=set(holders))
    rejected = rejected_flags(conn)

    out("1. unflagged namesakes of flagged organisations")
    out(f"   {len(plan)} organisations: {sum(p['action'] == 'merge' for p in plan)} to merge, "
        f"{sum(p['action'] == 'flag' for p in plan)} to flag only "
        f"({sum(p['conflict'] for p in plan)} carry another number than the flagged one)")
    for p in plan[:top]:
        out(f"   {p['action']:>5}  {p['uid']} -> {p['tid']}  {p['country']} "
            f"{p['canonical_name'][:60]!r}  {p['uident']} / {p['tident']}")
    out("2. derived flags the current rules reject")
    out(f"   {len(rejected)} organisations")
    for r in rejected[:top]:
        out(f"   {r['id']}  {r['country']} {r['canonical_name'][:70]!r}  ({r['why']})")
    out("3. shared identifiers (read only: the merges stay)")
    rows_out: list[tuple[Any, ...]] = []
    for h in sorted(holders.values(), key=lambda h: -len(h["absorbed"])):
        wrong = affected_notices(conn, h)
        h["affected"] = sum(n for _, n in wrong)
        out(f"   {h['id']}  {h['country']} {h['name'][:48]!r} number {h['identifier']}: "
            f"{len(h['absorbed'])} absorbed services, {h['affected']} notices under another name"
            f" ({len(wrong)} names)")
        for aid, aname in h["absorbed"]:
            rows_out.append((h["id"], h["name"], h["identifier"], "absorbed_organisation",
                             aid, aname, ""))
        for raw, n in wrong:
            rows_out.append((h["id"], h["name"], h["identifier"], "notice_name", "", raw, n))
    if report_csv is not None:
        with report_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["holder_id", "holder_name", "identifier", "kind", "org_id",
                        "name", "notices"])
            w.writerows(rows_out)
        out(f"   report written to {report_csv}")

    result = {"namesakes": len(plan), "rejected_flags": len(rejected),
              "shared_identifier_holders": len(holders)}
    if not apply:
        out("dry run: nothing written (add --yes)")
        return result
    result.update(apply_namesakes(conn, plan, merge_conflicting=merge_conflicting))
    result["unflagged"] = unflag(conn, rejected)
    out(f"applied: {result}")
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="write (default: report only)")
    p.add_argument("--merge-conflicting", action="store_true",
                   help="also merge namesakes whose registered number differs")
    p.add_argument("--report-csv", type=Path, default=None,
                   help="write the shared-identifier report (step 3) here")
    p.add_argument("--top", type=int, default=12)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        run(conn, apply=args.yes, merge_conflicting=args.merge_conflicting, top=args.top,
            report_csv=args.report_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
