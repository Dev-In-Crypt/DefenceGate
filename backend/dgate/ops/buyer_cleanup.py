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
   a namesake (`namesake`) goes when no flagged namesake is left (a namesake merged into a
   flagged organisation counts). Neither goes when the classifier itself reads the name as a
   defence body (`buyer_class_of`: its precedence, not the exclusion lists') or when the
   organisation's notices are filed under the 2009/81/EC legal basis (14 October 2026: the
   Spanish Army contracting board 311783 and a French ministry service 331798).

3. **Shared identifiers** (correctness:D8), read only. A registration number that belongs
   to a ministry-level legal entity was merged with every service that stated it (`merge_method
   = 'identifier'`): organisation 196441, "minarm air siae", holds 33 services and 552
   notices. `db.names_compatible` now refuses that from here on. The merges already made are
   history and stay; this lists them, with the notices whose stated name is not the holder's.

    python -m dgate.ops.buyer_cleanup                     # report, writes nothing
    python -m dgate.ops.buyer_cleanup --yes               # steps 1 and 2
    python -m dgate.ops.buyer_cleanup --yes --merge-conflicting

4. **A ministry that changed its name** (site-qa2:N9), same tool, same safeguards. The French
   Ministry of Defence (MINDEF) became the Ministry of the Armed Forces (MINARM); BOAMP
   notices still say either, so one unit was two buyers: 47 of the 800 largest buyers on
   14 October 2026. A live organisation named `mindef <path>` is merged (method
   `ministry_rename`, confidence 0.90) into the live `minarm <path>` of the same country when
   there is exactly one, the two registered numbers do not contradict, and the survivor is
   not a shared-identifier holder (step 3). Several candidates (three `minarm dga do s2a`
   with other establishment numbers), none, or a different number: left as they are and
   listed, because a number is a body's own and the name alone does not decide which one.

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
from ..buyer_vocab import buyer_class_of, defence_body
from ..config import settings
from ..normalise import normalise_org_name

log = logging.getLogger("buyer_cleanup")

METHOD_MERGE = "namesake_flagged"
CONF_MERGE = 0.95
DETECTED_BY = "buyer_cleanup"

# The renames of a ministry's short name, per country: {country: {old: new}}. A path
# after the name ("mindef dga do s2a") must be equal on both sides.
MINISTRY_RENAMES = {"FR": {"mindef": "minarm"}}
METHOD_RENAME = "ministry_rename"
CONF_RENAME = 0.90

RENAME_SQL = """
SELECT d.id AS did, d.canonical_name AS dname, d.national_reg_no AS dident,
       a.id AS aid, a.national_reg_no AS aident,
       (SELECT count(*) FROM opportunity o WHERE o.buyer_org_id = d.id) AS notices
  FROM organisation d
  LEFT JOIN organisation a
         ON a.country = d.country AND a.merged_into IS NULL AND a.id <> d.id
        AND a.canonical_name = %(new)s || substr(d.canonical_name, length(%(old)s) + 1)
 WHERE d.merged_into IS NULL AND d.country = %(country)s
   AND (d.canonical_name = %(old)s OR d.canonical_name LIKE %(old)s || ' %%')
 ORDER BY d.id, a.id
"""

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


# ------------------------------------------------------- 4. renamed ministry

def rename_plan(conn, umbrellas: set[int] | None = None) -> list[dict[str, Any]]:
    """One entry per live organisation that carries a retired ministry name: what to do
    (`merge`, `ambiguous`, `distinct`, `none`, `umbrella`) and the candidates it was
    decided from. Read only."""
    umbrellas = umbrellas or set()
    plan: list[dict[str, Any]] = []
    for country, names in MINISTRY_RENAMES.items():
        for old, new in names.items():
            by_org: dict[int, dict[str, Any]] = {}
            for r in conn.execute(RENAME_SQL, {"old": old, "new": new,
                                               "country": country}).fetchall():
                e = by_org.setdefault(r["did"], {
                    "did": r["did"], "country": country, "name": r["dname"],
                    "identifier": r["dident"], "notices": r["notices"], "candidates": []})
                if r["aid"] is not None:
                    e["candidates"].append({"id": r["aid"], "identifier": r["aident"]})
            for e in by_org.values():
                cands = e["candidates"]
                fit = [c for c in cands if e["identifier"] is None or c["identifier"] is None
                       or c["identifier"] == e["identifier"]]
                if not cands:
                    e["action"] = "none"
                elif len(fit) > 1:
                    e["action"] = "ambiguous"
                elif not fit:
                    e["action"] = "distinct"
                elif fit[0]["id"] in umbrellas:
                    e["action"] = "umbrella"
                else:
                    e["action"] = "merge"
                    e["keep"] = fit[0]["id"]
                plan.append(e)
    return plan


def apply_renames(conn, plan: list[dict[str, Any]]) -> dict[str, int]:
    done = {"renamed_merged": 0, "renamed_notices_moved": 0, "renamed_failed": 0}
    for e in plan:
        if e["action"] != "merge":
            continue
        evidence = (f"{e['name']!r} in {e['country']}: the retired ministry name; "
                    f"same path as organisation {e['keep']}")
        try:
            with conn.transaction():
                moved = db.merge_organisations(
                    conn, e["keep"], e["did"], method=METHOD_RENAME, confidence=CONF_RENAME,
                    evidence=evidence, detected_by=DETECTED_BY)
            conn.commit()
            done["renamed_merged"] += 1
            done["renamed_notices_moved"] += moved["notices"]
        except Exception as exc:  # noqa: BLE001 - one organisation must not stop the rest
            log.error("organisation %s not handled: %s", e["did"], exc)
            conn.rollback()
            done["renamed_failed"] += 1
    return done


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


def _flagged_through_merge(conn, org_id: int, country: str, name: str) -> bool:
    """A flagged, live organisation that a same-named row (the organisation itself, or one
    merged into it) stands for: `db.flagged_namesake` finds the flagged row named the same,
    not the one a same-named row was merged into. 311783 ("junta de contratacion del
    ejercito de tierra") inherited its flag from 49680, which was then merged into 2146."""
    return conn.execute(
        """SELECT 1 FROM organisation n JOIN organisation t ON t.id = COALESCE(n.merged_into, n.id)
            WHERE n.country = %s AND lower(n.canonical_name) = lower(%s) AND n.id <> %s
              AND t.merged_into IS NULL AND t.is_defence_buyer AND t.id <> %s LIMIT 1""",
        (country, name, org_id, org_id)).fetchone() is not None


def _with_defence_legal_basis(conn, org_ids: list[int]) -> set[int]:
    """The organisations among `org_ids` whose notices are listed under the defence
    procurement directive: the notice itself says defence, whatever the name says."""
    if not org_ids:
        return set()
    return {r["buyer_org_id"] for r in conn.execute(
        """SELECT DISTINCT buyer_org_id FROM opportunity
            WHERE buyer_org_id = ANY(%s) AND sig_legal_basis""", (org_ids,)).fetchall()}


def rejected_flags(conn, keep: set[tuple[str, str]] | None = None) -> list[dict[str, Any]]:
    """Flagged organisations whose flag no rule or namesake supports any longer.

    A flag is withdrawn only when nothing the classifier honours stands behind it. The
    classifier reads a name that begins with the ministry, an armed force, an agency or a
    unit as a defence body (`buyer_class_of`, first include at 0.85 or more) before any
    municipal, property or health vocabulary, so this does too: 'junta de contratacion
    del ejercito de tierra' is the Army's contracting board and 'minarm sga dcsid esid
    toulon service achats infrastructure' is a service of the Ministry of the Armed
    Forces, although "junta de" and "infrastructure" are municipal and property words.
    And an organisation whose notices carry the 2009/81/EC legal basis keeps its flag."""
    keep = keep if keep is not None else reviewed_names()
    candidates: list[dict[str, Any]] = []
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
                candidates.append({**r, "why": f"excluded as {body.excluded_as} by the name rules"})
        elif (db.flagged_namesake(conn, r["id"], None, r["country"]) is None
              and not _flagged_through_merge(conn, r["id"], r["country"], r["canonical_name"])):
            candidates.append({**r, "why": "no flagged namesake is left"})
    # the classifier's own precedence, then the notices' legal basis
    candidates = [c for c in candidates
                  if buyer_class_of(c["canonical_name"], c["country"]) != "defence"]
    protected = _with_defence_legal_basis(conn, [c["id"] for c in candidates])
    return [c for c in candidates if c["id"] not in protected]


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
    renames = rename_plan(conn, umbrellas=set(holders))

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
    out("4. a ministry that changed its name (retired name -> current name, same path)")
    kinds = {k: sum(e["action"] == k for e in renames)
             for k in ("merge", "ambiguous", "distinct", "umbrella", "none")}
    out(f"   {len(renames)} organisations: {kinds['merge']} to merge, {kinds['ambiguous']} with "
        f"several candidates, {kinds['distinct']} with another number, {kinds['umbrella']} "
        f"whose candidate is a shared-identifier holder, {kinds['none']} with no current-name twin")
    for e in sorted(renames, key=lambda e: -e["notices"])[:top]:
        out(f"   {e['action']:>9}  {e['did']} -> {[c['id'] for c in e['candidates']]}  "
            f"{e['name'][:60]!r}  {e['notices']} notices")
    if report_csv is not None:
        with report_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["holder_id", "holder_name", "identifier", "kind", "org_id",
                        "name", "notices"])
            w.writerows(rows_out)
            w.writerow([])
            w.writerow(["rename_org_id", "name", "action", "candidates", "notices"])
            for e in renames:
                w.writerow([e["did"], e["name"], e["action"],
                            " ".join(str(c["id"]) for c in e["candidates"]), e["notices"]])
        out(f"   report written to {report_csv}")

    result = {"namesakes": len(plan), "rejected_flags": len(rejected),
              "shared_identifier_holders": len(holders), "ministry_renames": kinds["merge"],
              "ministry_renames_unresolved": len(renames) - kinds["merge"]}
    if not apply:
        out("dry run: nothing written (add --yes)")
        return result
    result.update(apply_namesakes(conn, plan, merge_conflicting=merge_conflicting))
    result["unflagged"] = unflag(conn, rejected)
    result.update(apply_renames(conn, renames))
    out(f"applied: {result}")
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="write (default: report only)")
    p.add_argument("--merge-conflicting", action="store_true",
                   help="also merge namesakes whose registered number differs")
    p.add_argument("--report-csv", type=Path, default=None,
                   help="write the shared-identifier report (step 3) and the rename plan "
                        "(step 4) here")
    p.add_argument("--top", type=int, default=12)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        run(conn, apply=args.yes, merge_conflicting=args.merge_conflicting, top=args.top,
            report_csv=args.report_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
