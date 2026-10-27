"""WP-151: one French buyer, one organisation, across BOAMP's 2024 eForms switch.

The retender check of 27 October 2026 found that of the BOAMP notices published from 2024 only
343 of 2,365 (15%) resolve to a buyer organisation that also has a BOAMP notice of 2015-2023; for
2023 against 2021-22 it is 96%. The record's `nomacheteur` is written differently in the two eras
(the older schemas' service label "MINARM/DGA/DO/S2A", then the eForms name, with HTML character
references such as "l&#039;Oise" in it), resolution was by name alone because the BOAMP mapper read
no buyer number, and so each eForms-era name opened an organisation of its own. Every BOAMP shape
states the buyer's SIRET (`normalise._fr_buyer_identifier`); new notices now resolve by it. This
repairs the rows already split:

  * by SIRET     the landed payloads are read (one notice of each organisation, from the fewest
                 bundles, `backfill_buyer_identifiers.collect_identifiers`). A number stated by
                 exactly two live French organisations (its registered holder counted), one with
                 BOAMP notices before 2024 and one with BOAMP notices from 2024 only, is one pair:
                 method `boamp_siret`, confidence 0.90. The names are not compared: that they differ
                 is the defect. Anything else is left out and said why: one eForms-era buyer and
                 several older ones (or the reverse, or several of each: a ministry's number stated
                 by its services, D8), both rows on one side of the switch, a holder with no BOAMP
                 notice, two different registered numbers.
  * by name      the same rule over `normalise_org_name` of the stated names (`organisation_alias`),
                 which now decodes HTML references: method `boamp_exact_name`, confidence 0.95.
  * a number     stated by one organisation only is attached to it (method `boamp_siret`, 0.90), so
                 the next notice of that buyer resolves by number whatever its name says.

The older row is kept (it holds the history); the eForms-era row is merged into it through
`db.merge_organisations` (aliases and serving rows re-pointed, the absorbed row kept with
`merged_into`, a `merged` candidate row with method and confidence; archived versions untouched).
Each pair is its own transaction. The undo is `ops.undo_merges`' logic over this run's window and
methods, plus the numbers this run attached (logged in `organisation_repair`).

    python -m dgate.ops.boamp_buyer_ids                          # report: changes nothing
    python -m dgate.ops.boamp_buyer_ids --yes                    # merge and attach; prints the undo
    python -m dgate.ops.boamp_buyer_ids --undo FROM TO [--yes]   # undo one run
    python -m dgate.ops.boamp_buyer_ids --groups FILE [--yes]    # merge groups a person reviewed (method boamp_siret_review)

Afterwards: `python -m dgate.reprocess --reclassify-serving --yes` (the serving rows read the flag
and the buyer class from the organisation they point at).
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import sys
from dataclasses import dataclass
from datetime import date
from typing import Any

from .. import db, networks
from ..config import settings
from ..normalise import _fr_buyer_identifier, normalise_org_name
from ..rawstore import RawStore, build_store, split_record_key
from ..sources import boamp
from . import backfill_buyer_identifiers as backfill
from . import buyer_families, undo_merges

log = logging.getLogger("boamp_buyer_ids")

METHOD_ID = "boamp_siret"
METHOD_NAME = "boamp_exact_name"
METHOD_REVIEW = "boamp_siret_review"           # a group the owner reviewed (--groups FILE)
METHODS = (METHOD_ID, METHOD_NAME, METHOD_REVIEW)
CONF_ID = 0.90
CONF_NAME = db.CONF_EXACT_NAME
CONF_REVIEW = 0.95
DETECTED_BY = "ops.boamp_buyer_ids"
ATTACHED = "boamp_identifier_attached"       # organisation_repair action of a number this run attached
SWITCH = date(2024, 1, 1)                    # BOAMP's eForms notices start in 2024


@dataclass
class Org:
    id: int
    name: str
    reg_no: str | None
    old: int            # BOAMP notices published before SWITCH
    new: int            # BOAMP notices published from SWITCH
    notices: int        # every notice it holds, any source: the rows that move
    aliases: int = 0

    @property
    def side(self) -> str:
        return "old" if self.old else ("new" if self.new else "none")


@dataclass
class Pair:
    keep: Org
    absorbed: Org
    method: str
    confidence: float
    evidence: str
    number: str | None = None       # the SIRET of a `boamp_siret` pair


def record_identifier(record: dict[str, Any], _country: str | None = None) -> str | None:
    """The buyer SIRET of one landed BOAMP record (the record as the connector returned it)."""
    return _fr_buyer_identifier(boamp.notice_body(record))


def load(conn) -> tuple[dict[int, Org], dict[int, list[tuple[str, int, str]]]]:
    """Live French organisations holding BOAMP notices, and where each notice's payload is."""
    src = db.source_id(conn, boamp.SOURCE_CODE)
    orgs = {r["id"]: Org(r["id"], r["canonical_name"], r["national_reg_no"], r["old"], r["new"], r["n"], r["aliases"])
            for r in conn.execute(
                """SELECT g.id, g.canonical_name, g.national_reg_no,
                          count(*) FILTER (WHERE o.published_at < %s) AS old,
                          count(*) FILTER (WHERE o.published_at >= %s) AS new,
                          (SELECT count(*) FROM opportunity x WHERE x.buyer_org_id = g.id) AS n,
                          (SELECT count(*) FROM organisation_alias a WHERE a.organisation_id = g.id) AS aliases
                     FROM organisation g JOIN opportunity o ON o.buyer_org_id = g.id
                    WHERE o.source_id = %s AND g.country = 'FR' AND g.merged_into IS NULL
                    GROUP BY g.id""", (SWITCH, SWITCH, src)).fetchall()}
    per: dict[int, list[tuple[str, int, str]]] = collections.defaultdict(list)
    for r in conn.execute(
            """SELECT DISTINCT ON (o.id) o.buyer_org_id AS org_id, r.storage_key
                 FROM opportunity o
                 JOIN raw_ingest r ON r.source_id = o.source_id AND r.native_id = o.native_id
                WHERE o.source_id = %s AND o.buyer_org_id IS NOT NULL
                ORDER BY o.id, r.id DESC""", (src,)).fetchall():
        if r["org_id"] in orgs and r["storage_key"]:
            bundle, line = split_record_key(r["storage_key"])
            per[r["org_id"]].append((bundle, line if line is not None else 0, "FR"))
    return orgs, per


def _reader(store: RawStore):
    """Lines of a bundle; a plain object (line 0 in the plan) is read as a bundle of one."""
    def read(key: str) -> list[str]:
        if key.endswith(".jsonl.gz"):
            return store._bundle_lines(key)
        return [json.dumps(store.get(key))]
    return read


def _pair_or_reason(members: list[Org]) -> tuple[Org, Org] | str:
    """The (older, eForms-era) pair a group of organisations sharing a number or a name is, or why it is not one."""
    old = [o for o in members if o.side == "old"]
    new = [o for o in members if o.side == "new"]
    none = [o for o in members if o.side == "none"]
    numbers = {o.reg_no for o in members if o.reg_no}
    if len(numbers) > 1:
        return "two different registered numbers"
    if none:
        return "the number's holder holds no BOAMP notice"
    if len(old) == 1 and len(new) == 1:
        return old[0], new[0]
    if not new:
        return "every row holds notices from before 2024"
    if not old:
        return "every row holds eForms-era notices only"
    if len(new) == 1:
        return f"one eForms-era buyer, {len(old)} older ones"
    if len(old) == 1:
        return f"{len(new)} eForms-era buyers, one older one"
    return f"{len(new)} eForms-era buyers, {len(old)} older ones"


def plan(orgs: dict[int, Org], idents: dict[int, collections.Counter], holders: dict[str, Org],
         names: dict[int, set[str]]) -> dict[str, Any]:
    """Pairs, attachments and the groups left out, from what was read.

    `idents`: org id -> the SIRETs its notices state; `holders`: SIRET -> the live French
    organisation that carries it (any source); `names`: org id -> normalised stated names.
    """
    key_of: dict[int, str] = {}
    conflicting = 0
    for oid, org in orgs.items():
        stated = idents.get(oid)
        read = stated.most_common(1)[0][0] if stated else None
        if org.reg_no and read and read != org.reg_no:
            conflicting += 1
        key = org.reg_no or read           # the registered number is what resolution reads
        if key:
            key_of[oid] = key
    by_id: dict[str, dict[int, Org]] = collections.defaultdict(dict)
    for oid, key in key_of.items():
        by_id[key][oid] = orgs[oid]
    for key, holder in holders.items():
        if key in by_id:
            by_id[key][holder.id] = holder

    pairs: list[Pair] = []
    left: list[tuple[str, str, list[Org]]] = []       # (method, reason, members)
    attach: list[tuple[Org, str]] = []
    used: set[int] = set()
    for key, group in sorted(by_id.items()):
        members = sorted(group.values(), key=lambda o: o.id)
        if len(members) == 1:
            if members[0].reg_no is None:
                attach.append((members[0], key))
            continue
        got = _pair_or_reason(members)
        if isinstance(got, str):
            left.append((METHOD_ID, got, members))
            continue
        keep, absorbed = got
        pairs.append(Pair(keep, absorbed, METHOD_ID, CONF_ID, f"SIRET {key} stated on BOAMP notices of both rows",
                          key))
        used.update((keep.id, absorbed.id))

    by_name: dict[str, dict[int, Org]] = collections.defaultdict(dict)
    for oid, keys in names.items():
        if oid in orgs and oid not in used:
            for nk in keys:
                by_name[nk][oid] = orgs[oid]
    name_pairs: dict[tuple[int, int], str] = {}
    for key, group in sorted(by_name.items()):
        members = sorted(group.values(), key=lambda o: o.id)
        if len(members) < 2:
            continue
        got = _pair_or_reason(members)
        if isinstance(got, str):
            left.append((METHOD_NAME, got, members))
        else:
            name_pairs.setdefault((got[0].id, got[1].id), key)
    seen = collections.Counter(i for p in name_pairs for i in p)
    for (ko, ab), name in name_pairs.items():
        if seen[ko] > 1 or seen[ab] > 1:
            left.append((METHOD_NAME, "a row in two name pairs", [orgs[ko], orgs[ab]]))
            continue
        pairs.append(Pair(orgs[ko], orgs[ab], METHOD_NAME, CONF_NAME, f"exact normalised name {name!r}"))
    return {"pairs": pairs, "left": left, "attach": attach, "conflicting": conflicting}


def stated_names(conn, ids: list[int]) -> dict[int, set[str]]:
    """Normalised stated names of each organisation, by today's `normalise_org_name`."""
    out: dict[int, set[str]] = collections.defaultdict(set)
    for r in conn.execute("SELECT organisation_id, raw_name FROM organisation_alias WHERE organisation_id = ANY(%s)",
                          (ids,)).fetchall():
        key = normalise_org_name(r["raw_name"])
        if key:
            out[r["organisation_id"]].add(key)
    return out


def registered_holders(conn, numbers: set[str], orgs: dict[int, Org]) -> dict[str, Org]:
    out: dict[str, Org] = {}
    for r in conn.execute(
            """SELECT g.id, g.canonical_name, g.national_reg_no,
                      (SELECT count(*) FROM opportunity x WHERE x.buyer_org_id = g.id) AS n
                 FROM organisation g
                WHERE g.country = 'FR' AND g.merged_into IS NULL AND g.national_reg_no = ANY(%s)""",
            (sorted(numbers),)).fetchall():
        out[r["national_reg_no"]] = orgs.get(r["id"]) or Org(r["id"], r["canonical_name"], r["national_reg_no"],
                                                              0, 0, r["n"])
    return out


def _merge(conn, p: Pair, key: str | None) -> bool:  # key: the pair's SIRET, attached to the kept row if neither has one
    """One pair, read again first: a row merged since, or a number that contradicts, is left."""
    live = {r["id"]: r for r in conn.execute(
        "SELECT id, national_reg_no, merged_into FROM organisation WHERE id = ANY(%s) FOR UPDATE",
        ([p.keep.id, p.absorbed.id],)).fetchall()}
    k, a = live.get(p.keep.id), live.get(p.absorbed.id)
    if not k or not a or k["merged_into"] is not None or a["merged_into"] is not None:
        return False
    if k["national_reg_no"] and a["national_reg_no"] and k["national_reg_no"] != a["national_reg_no"]:
        return False
    db.merge_organisations(conn, p.keep.id, p.absorbed.id, method=p.method, confidence=p.confidence,
                           evidence=p.evidence, detected_by=DETECTED_BY)
    if key and not (k["national_reg_no"] or a["national_reg_no"]):
        _attach(conn, p.keep.id, key)
    return True


def _attach(conn, org_id: int, key: str) -> bool:
    done = conn.execute(
        """UPDATE organisation SET national_reg_no = %s, identifier_method = %s, identifier_confidence = %s
            WHERE id = %s AND national_reg_no IS NULL
              AND NOT EXISTS (SELECT 1 FROM organisation x WHERE x.country = 'FR' AND x.national_reg_no = %s)
           RETURNING id""", (key, METHOD_ID, CONF_ID, org_id, key)).fetchone()
    if done:
        db.log_repair(conn, org_id, ATTACHED, old_value=None, new_value=key, method=METHOD_ID, detected_by=DETECTED_BY)
    return bool(done)


def run(conn, store: RawStore, *, apply: bool = False, max_bundles: int | None = None, rounds: int = 3,
        examples: int = 15, out=print) -> dict[str, Any]:
    orgs, per = load(conn)
    sides = collections.Counter(o.side for o in orgs.values())
    both = sum(1 for o in orgs.values() if o.old and o.new)
    out(f"BOAMP buyer organisations: {len(orgs)} (with notices before 2024: {sides['old']}, of which "
        f"{both} also from 2024; from 2024 only: {sides['new']})")
    idents, stats = backfill.collect_identifiers(per, _reader(store), rounds=rounds, max_bundles=max_bundles,
                                                 identify=record_identifier)
    out(f"payloads: {stats['bundles']} bundles read in {stats['rounds']} round(s) ({stats['unreadable']} unreadable); "
        f"{stats['notices']} notices read, {stats['no_identifier']} without one usable SIRET")
    numbers = {i for c in idents.values() for i in c} | {o.reg_no for o in orgs.values() if o.reg_no}
    holders = registered_holders(conn, numbers, orgs)
    p = plan(orgs, idents, holders, stated_names(conn, sorted(orgs)))
    pairs, left, attach = p["pairs"], p["left"], p["attach"]
    by_method = collections.Counter(x.method for x in pairs)
    moved = sum(x.absorbed.notices for x in pairs)
    joined = {x.absorbed.id for x in pairs if x.absorbed.side == "new"}
    result: dict[str, Any] = {
        "organisations": len(orgs), "new_only": sides["new"], "pairs": dict(by_method),
        "notices_moved": moved, "aliases_moved": sum(x.absorbed.aliases for x in pairs),
        "attach": len(attach), "left_out": dict(collections.Counter((m, r) for m, r, _ in left)),
        "conflicting_numbers": p["conflicting"], "merged": 0, "attached": 0, "skipped": 0}
    out(f"pairs by SIRET ({METHOD_ID}, {CONF_ID}): {by_method[METHOD_ID]}; "
        f"by exact name ({METHOD_NAME}, {CONF_NAME}): {by_method[METHOD_NAME]}")
    out(f"rows that would move: {moved} notices and {result['aliases_moved']} aliases onto the older row; "
        f"{len(joined)} of the {sides['new']} from-2024-only organisations rejoin their history")
    out(f"SIRET attached to an organisation that alone states it: {len(attach)}")
    out(f"organisations whose registered number differs from the SIRET their notices state: {p['conflicting']}")
    out("left out (method, reason: groups):")
    for (m, r), n in sorted(result["left_out"].items(), key=lambda x: -x[1]):
        out(f"  {m}, {r}: {n}")
    out(f"examples ({min(examples, len(pairs))} of {len(pairs)} pairs; keep <- absorbed):")
    for x in pairs[:examples]:
        out(f"  {x.method}: {x.keep.id} {x.keep.name[:45]!r} <- {x.absorbed.id} {x.absorbed.name[:45]!r} "
            f"({x.absorbed.notices} notices; {x.evidence})")
    if left:
        out("examples left out:")
        for m, r, members in left[:examples]:
            names = "; ".join(f"{o.id} {o.name[:30]!r} [{o.side}]" for o in members[:4])
            out(f"  {m} ({r}): {names}{' ...' if len(members) > 4 else ''}")
    if not apply:
        conn.rollback()
        out("report only: nothing written (add --yes)")
        return result

    started = conn.execute("SELECT now() AS t").fetchone()["t"]
    conn.commit()
    for x in pairs:
        try:
            with conn.transaction():
                ok = _merge(conn, x, x.number)
            conn.commit()
        except Exception as exc:  # noqa: BLE001 - logged; the other pairs go on
            log.error("pair %s <- %s not merged: %s", x.keep.id, x.absorbed.id, exc)
            conn.rollback()
            ok = False
        result["merged" if ok else "skipped"] += 1
    for org, key in attach:
        result["attached"] += _attach(conn, org.id, key)
    conn.commit()
    ended = conn.execute("SELECT now() AS t").fetchone()["t"]
    conn.commit()
    result["window"] = (started.isoformat(), ended.isoformat())
    result["families_written"] = buyer_families.run(conn, write=True)
    result["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
    out(f"merged {result['merged']} pairs ({result['skipped']} left: merged or numbered since), "
        f"attached {result['attached']} numbers")
    out(f"to undo this run: python -m dgate.ops.boamp_buyer_ids --undo '{started.isoformat()}' "
        f"'{ended.isoformat()}' [--yes]")
    return result


def apply_groups(conn, groups: list[dict[str, Any]], *, apply: bool = False, out=print) -> dict[str, Any]:
    """Groups a person reviewed: [{"group": "G5", "head": id, "members": [id, ...]}], each member merged into its head.

    A member is left when either row is gone or merged since, or `db.merge_organisations` refuses it (another country,
    two different registered numbers). Report by default; undone with `--undo` over the printed window."""
    ids = sorted({g["head"] for g in groups} | {m for g in groups for m in g["members"]})
    live = {r["id"]: r for r in conn.execute(
        "SELECT id, merged_into, country FROM organisation WHERE id = ANY(%s)", (ids,)).fetchall()}
    todo = [(g["group"], g["head"], m) for g in groups for m in g["members"]
            if all(live.get(i) and live[i]["merged_into"] is None for i in (g["head"], m))]
    res: dict[str, Any] = {"groups": len(groups), "members": sum(len(g["members"]) for g in groups),
                           "to_merge": len(todo), "merged": 0, "skipped": 0}
    out(f"reviewed groups: {res['groups']}, members {res['members']}, still separate and to merge {len(todo)}")
    if not apply:
        conn.rollback()
        out("report only: nothing written (add --yes)")
        return res
    started = conn.execute("SELECT now() AS t").fetchone()["t"]
    conn.commit()
    for group, head, member in todo:
        try:
            with conn.transaction():
                db.merge_organisations(conn, head, member, method=METHOD_REVIEW, confidence=CONF_REVIEW,
                                       evidence=f"BOAMP buyer group {group}, reviewed by the owner",
                                       detected_by=DETECTED_BY)
            conn.commit()
            res["merged"] += 1
        except Exception as exc:  # noqa: BLE001 - logged; the other members go on
            log.error("%s: %s <- %s not merged: %s", group, head, member, exc)
            conn.rollback()
            res["skipped"] += 1
    ended = conn.execute("SELECT now() AS t").fetchone()["t"]
    conn.commit()
    res["window"] = (started.isoformat(), ended.isoformat())
    res["families_written"] = buyer_families.run(conn, write=True)
    res["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
    out(f"merged {res['merged']}, left {res['skipped']}")
    out(f"to undo this run: python -m dgate.ops.boamp_buyer_ids --undo '{started.isoformat()}' "
        f"'{ended.isoformat()}' [--yes]")
    return res


def undo(conn, start: str, end: str, *, apply: bool = False, out=print) -> dict[str, Any]:
    """Undo one run: its merges (`ops.undo_merges` over METHODS in the window) and the numbers it attached."""
    attached = conn.execute(
        """SELECT r.organisation_id, r.new_value FROM organisation_repair r
             JOIN organisation g ON g.id = r.organisation_id AND g.national_reg_no = r.new_value
            WHERE r.action = %s AND r.detected_by = %s AND r.created_at >= %s AND r.created_at < %s""",
        (ATTACHED, DETECTED_BY, start, end)).fetchall()
    res = undo_merges.run(conn, apply=apply, start=start, end=end, methods=METHODS, expected=None,
                          detected_by=DETECTED_BY, out=out)
    res["numbers_detached"] = len(attached)
    out(f"numbers this run attached, to clear: {len(attached)}")
    if apply and attached:
        for r in attached:
            conn.execute(
                """UPDATE organisation SET national_reg_no = NULL, identifier_method = NULL, identifier_confidence = NULL
                    WHERE id = %s AND national_reg_no = %s""", (r["organisation_id"], r["new_value"]))
        conn.commit()
    elif not apply:
        conn.rollback()
    return res


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="write (default: report only)")
    p.add_argument("--undo", nargs=2, metavar=("FROM", "TO"), help="undo the run of [FROM, TO) (timestamps with zone)")
    p.add_argument("--max-bundles", type=int, default=None, help="stop after this many bundles (a sample)")
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--groups", metavar="FILE", help="merge the groups a person reviewed (JSON list of "
                   '{"group", "head", "members"}); "-" reads standard input')
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        if a.undo:
            undo(conn, *a.undo, apply=a.yes)
        elif a.groups:
            with (open(a.groups, encoding="utf-8") if a.groups != "-" else sys.stdin) as f:
                apply_groups(conn, json.load(f), apply=a.yes)
        else:
            run(conn, build_store(), apply=a.yes, max_bundles=a.max_bundles, rounds=a.rounds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
