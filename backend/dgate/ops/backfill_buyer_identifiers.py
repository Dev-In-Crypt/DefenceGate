"""Attach TED's buyer identifiers to the organisations that hold notices, and merge
the organisations that share one.

Until 12 October 2026 a buyer was resolved by its name alone, and the identifier
TED states for it (`buyer-identifier`: a registry number, a VAT number, a SIRET,
an IČO) was requested, landed, and never read. The Czech Ministry of Defence sat
on 14 organisation rows, BAAINBw on 39, the French armed-forces ministry on 204.
Every one of those spellings carries the same number in the notices.

This reads the raw payload of notices the organisations hold, groups the
organisations that state one identifier, and applies the groups through
`db.merge_organisations`: method `identifier`, the confidence stored, the absorbed
row kept and marked `merged_into`, its aliases and notices re-pointed. Nothing is
deleted and no archived version is touched.

    python -m dgate.ops.backfill_buyer_identifiers            # dry run, reads the store
    python -m dgate.ops.backfill_buyer_identifiers --yes      # merge and attach
    python -m dgate.ops.backfill_buyer_identifiers --max-bundles 20   # a sample

Which notices are read: one notice of each organisation, from the fewest bundles
that cover them (greedy cover; about 1,100 of the 1,600 TED bundles on 12 October
2026), then a second and third pass over the organisations whose notice stated no
usable identifier. Which identifiers
count: only a notice with exactly one buyer name and one identifier, and only an
identifier `normalise_identifier` accepts. Which groups are merged: those whose
names share a word with the survivor; the others are written as merge candidates
and left for a person.
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Iterable

from .. import db
from ..config import settings
from ..normalise import normalise_identifier
from ..rawstore import RawStore, build_store, split_record_key

log = logging.getLogger("backfill_buyer_identifiers")

METHOD = "identifier"
CONFIDENCE = 0.95            # one registry number stated on notices of both rows
DEFAULT_MAX_GROUP = 500


def notice_identifier(notice: dict[str, Any], country: str | None) -> str | None:
    """The normalised buyer identifier of a single-buyer notice, else None."""
    ids = notice.get("buyer-identifier")
    if ids is None:
        return None
    ids = [str(i).strip() for i in (ids if isinstance(ids, list) else [ids]) if str(i).strip()]
    if len(set(ids)) != 1:
        return None
    names = notice.get("buyer-name")
    if isinstance(names, dict):
        first = next(iter(names.values()), [])
        names = first if isinstance(first, list) else [first]
    elif not isinstance(names, list):
        names = [names]
    if len({str(n).strip() for n in names if n}) != 1:
        return None
    return normalise_identifier(ids[0], country)


@dataclass
class Org:
    id: int
    country: str
    name: str
    notices: int
    national_reg_no: str | None = None
    defence_buyer: bool = False


@dataclass
class Group:
    country: str
    identifier: str
    survivor: Org
    absorbed: list[Org] = field(default_factory=list)    # merged into the survivor
    held_for_review: list[Org] = field(default_factory=list)   # candidates, not merged
    held_by_survivor: bool = False      # the survivor already carries the identifier
    review: str | None = None           # why the whole group is held

    @property
    def notices_moved(self) -> int:
        return sum(o.notices for o in self.absorbed)


def build_groups(orgs: dict[int, Org], idents: dict[int, collections.Counter],
                 holders: dict[tuple[str, str], int], max_group: int = DEFAULT_MAX_GROUP,
                 ) -> tuple[list[Group], list[tuple[Org, str]], dict[str, int]]:
    """Merge groups, single attachments, and counts.

    `idents` is org id -> Counter of the normalised identifiers its notices state;
    `holders` is (country, identifier) -> the organisation that already carries it.
    """
    by_ident: dict[tuple[str, str], set[int]] = collections.defaultdict(set)
    stats = {"orgs_with_identifier": 0, "orgs_conflicting": 0}
    chosen: dict[int, str] = {}
    for org_id, counter in idents.items():
        if org_id not in orgs or not counter:
            continue
        stats["orgs_with_identifier"] += 1
        ranked = counter.most_common()
        if len(ranked) > 1:
            stats["orgs_conflicting"] += 1
        chosen[org_id] = ranked[0][0]       # the identifier its notices state most often
        by_ident[(orgs[org_id].country, ranked[0][0])].add(org_id)

    groups: list[Group] = []
    singles: list[tuple[Org, str]] = []
    for (country, ident), members in by_ident.items():
        holder = holders.get((country, ident))
        ids = set(members)
        if holder is not None and holder in orgs:
            ids.add(holder)
        if len(ids) == 1:
            org = orgs[next(iter(ids))]
            if org.national_reg_no is None:
                singles.append((org, ident))
            continue
        ranked_orgs = sorted((orgs[i] for i in ids),
                             key=lambda o: (o.id != holder, -o.notices, o.id))
        survivor, rest = ranked_orgs[0], ranked_orgs[1:]
        compatible = [o for o in rest if db.names_compatible(survivor.name, o.name)]
        g = Group(country, ident, survivor, compatible,
                  held_for_review=[o for o in rest if o not in compatible],
                  held_by_survivor=survivor.national_reg_no == ident)
        if len(ids) > max_group:
            g.review = f"{len(ids)} organisations share it, over the limit of {max_group}"
            g.held_for_review, g.absorbed = rest, []
        elif g.held_for_review:
            g.review = (f"{len(g.held_for_review)} name(s) share no word with "
                        f"{survivor.name!r}")
        groups.append(g)
    groups.sort(key=lambda g: -(len(g.absorbed) + len(g.held_for_review) + 1))
    return groups, singles, stats


def cover(pairs: Iterable[tuple[int, str]], per_org: int = 1,
          max_bundles: int | None = None) -> list[str]:
    """The fewest bundles that contain a notice of every organisation (`per_org`
    times over where it has that many): greedy set cover, most uncovered first."""
    need: dict[int, int] = collections.defaultdict(int)
    by_bundle: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for org_id, bundle in pairs:
        by_bundle[bundle][org_id] += 1
    for counter in by_bundle.values():
        for org_id in counter:
            need[org_id] = per_org
    chosen: list[str] = []
    remaining = dict(need)
    while remaining and by_bundle and (max_bundles is None or len(chosen) < max_bundles):
        best = max(by_bundle, key=lambda b: sum(
            min(by_bundle[b][o], remaining[o]) for o in by_bundle[b] if o in remaining))
        gain = sum(min(by_bundle[best][o], remaining[o])
                   for o in by_bundle[best] if o in remaining)
        if gain == 0:
            break
        chosen.append(best)
        for o in by_bundle[best]:
            if o in remaining:
                remaining[o] -= min(by_bundle[best][o], remaining[o])
                if remaining[o] <= 0:
                    del remaining[o]
        del by_bundle[best]
    return chosen


def load_plan(conn):
    """Organisations holding TED notices and where their raw payloads are."""
    src = db.source_id(conn, "ted")
    # One hash join and a sort; a lookup per notice would scan raw_ingest (which has
    # no index on the notice number) a hundred thousand times.
    rows = conn.execute(
        """SELECT DISTINCT ON (o.id) o.buyer_org_id AS org_id, o.native_id, o.country,
                  r.storage_key
             FROM opportunity o
             JOIN raw_ingest r ON r.source_id = o.source_id AND r.native_id = o.native_id
            WHERE o.source_id = %s AND o.buyer_org_id IS NOT NULL
            ORDER BY o.id, r.id DESC""",
        (src,),
    ).fetchall()
    orgs: dict[int, Org] = {}
    info = conn.execute(
        """SELECT g.id, g.country, g.canonical_name, g.national_reg_no, g.is_defence_buyer,
                  count(o.id) AS n
             FROM organisation g JOIN opportunity o ON o.buyer_org_id = g.id
            WHERE g.merged_into IS NULL AND o.source_id = %s
            GROUP BY g.id""", (src,)).fetchall()
    for r in info:
        orgs[r["id"]] = Org(r["id"], r["country"], r["canonical_name"], r["n"],
                            r["national_reg_no"], bool(r["is_defence_buyer"]))
    per: dict[int, list[tuple[str, str]]] = collections.defaultdict(list)
    for r in rows:
        if r["org_id"] in orgs and r["storage_key"]:
            per[r["org_id"]].append((r["storage_key"], r["country"]))
    return orgs, per


def collect_identifiers(per: dict[int, list[tuple[str, int, str]]], read_lines, *,
                        rounds: int = 3, max_bundles: int | None = None, log_every: int = 50,
                        ) -> tuple[dict[int, collections.Counter], dict[str, int]]:
    """One usable identifier for each organisation, from as few bundles as it takes.

    `per` maps an organisation to all its notices as (bundle, line, country);
    `read_lines(bundle)` returns the bundle's JSON lines. Round one reads the fewest
    bundles that contain a notice of every organisation and takes one notice from
    each. An organisation whose notice stated no usable identifier goes into the next
    round with its other notices, up to `rounds`.
    """
    idents: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    unread = {o: sorted(ns, reverse=True) for o, ns in per.items()}     # newest first
    stats = {"bundles": 0, "notices": 0, "no_identifier": 0, "unreadable": 0, "rounds": 0}
    need = set(unread)
    for rnd in range(1, rounds + 1):
        if not need:
            break
        stats["rounds"] = rnd
        pairs = [(o, bundle) for o in need for bundle, _, _ in unread[o]]
        left = None if max_bundles is None else max_bundles - stats["bundles"]
        if left is not None and left <= 0:
            break
        chosen = cover(pairs, 1, left)
        if not chosen:
            break
        wanted: dict[str, set[int]] = collections.defaultdict(set)
        for o in need:
            for bundle, _, _ in unread[o]:
                wanted[bundle].add(o)
        for n, bundle in enumerate(chosen, 1):
            try:
                lines = read_lines(bundle)
            except Exception as exc:  # noqa: BLE001 - one unreadable bundle must not stop the rest
                log.warning("cannot read %s: %s", bundle, exc)
                stats["unreadable"] += 1
                continue
            stats["bundles"] += 1
            for o in wanted[bundle]:
                if o not in need or idents.get(o):
                    continue
                mine = [t for t in unread[o] if t[0] == bundle]
                if not mine:
                    continue
                _, line, country = mine[0]
                unread[o].remove(mine[0])
                if not 0 <= line < len(lines):
                    continue
                stats["notices"] += 1
                ident = notice_identifier(json.loads(lines[line]), country)
                if ident:
                    idents[o][ident] += 1
                else:
                    stats["no_identifier"] += 1
            if log_every and n % log_every == 0:
                log.info("round %s: read %s of %s bundles", rnd, n, len(chosen))
        need = {o for o in need if not idents.get(o) and unread[o]}
    return idents, stats


def _merge_group(conn, g: Group, result: dict[str, int]) -> int:
    """Merge the absorbed organisations of one group into its survivor; returns how many.

    The plan was made from a read at the start of the run, so each organisation is read
    again here: one that is merged by now, or that carries another registered number
    than the group's, is left out and counted in `result["skipped"]`, because
    `db.merge_organisations` refuses both and one refusal must not end the run.
    """
    live = {r["id"]: r for r in conn.execute(
        "SELECT id, national_reg_no, merged_into FROM organisation WHERE id = ANY(%s)",
        ([g.survivor.id, *(o.id for o in g.absorbed)],)).fetchall()}
    survivor = live.get(g.survivor.id)
    if survivor is None or survivor["merged_into"] is not None:
        log.warning("group %s in %s: survivor %s is already merged; left", g.identifier,
                    g.country, g.survivor.id)
        result["skipped"] += len(g.absorbed)
        return 0
    todo: list[Org] = []
    for o in g.absorbed:
        row = live.get(o.id)
        if row is None or row["merged_into"] is not None:
            log.info("organisation %s is already merged; left", o.id)
        elif row["national_reg_no"] not in (None, g.identifier):
            log.warning("organisation %s carries %s, not %s: not the same body; left",
                        o.id, row["national_reg_no"], g.identifier)
        else:
            todo.append(o)
            continue
        result["skipped"] += 1
    if todo and not g.held_by_survivor and survivor["national_reg_no"] is None:
        conn.execute(
            """UPDATE organisation SET national_reg_no = %s, identifier_method = %s,
                      identifier_confidence = %s
                WHERE id = %s AND national_reg_no IS NULL""",
            (g.identifier, METHOD, CONFIDENCE, g.survivor.id))
    for o in todo:
        db.merge_organisations(
            conn, g.survivor.id, o.id, method=METHOD, confidence=CONFIDENCE,
            evidence=f"identifier {g.identifier} in {g.country}",
            detected_by="backfill_buyer_identifiers")
    return len(todo)


def run(conn, store: RawStore, *, max_bundles: int | None = None, rounds: int = 3,
        max_group: int = DEFAULT_MAX_GROUP, apply: bool = False, top: int = 15,
        out=print) -> dict[str, int]:
    orgs, per_key = load_plan(conn)
    per: dict[int, list[tuple[str, int, str]]] = {}
    for org_id, keys in per_key.items():
        for key, country in keys:
            bundle, line = split_record_key(key)
            if line is not None:        # a plain object: none exists for TED any more
                per.setdefault(org_id, []).append((bundle, line, country or orgs[org_id].country))
    out(f"organisations holding TED notices: {len(orgs)}")
    idents, stats = collect_identifiers(per, store._bundle_lines, rounds=rounds,
                                        max_bundles=max_bundles)
    sampled, no_identifier = stats["notices"], stats["no_identifier"]
    out(f"bundles read: {stats['bundles']} in {stats['rounds']} round(s)"
        f" ({stats['unreadable']} unreadable)")

    holders: dict[tuple[str, str], int] = {}
    for (country, ident) in {(orgs[o].country, i) for o, c in idents.items() for i in c}:
        row = conn.execute(
            "SELECT id FROM organisation WHERE country = %s AND national_reg_no = %s",
            (country, ident)).fetchone()
        if row:
            holders[(country, ident)] = row["id"]
            if row["id"] not in orgs:
                info = conn.execute(
                    """SELECT g.id, g.country, g.canonical_name, g.national_reg_no,
                              g.is_defence_buyer,
                              (SELECT count(*) FROM opportunity o WHERE o.buyer_org_id = g.id) n
                         FROM organisation g WHERE g.id = %s AND g.merged_into IS NULL""",
                    (row["id"],)).fetchone()
                if info:
                    orgs[info["id"]] = Org(info["id"], info["country"], info["canonical_name"],
                                           info["n"], info["national_reg_no"],
                                           bool(info["is_defence_buyer"]))
    groups, singles, stats = build_groups(orgs, idents, holders, max_group)

    merge = [g for g in groups if g.absorbed]
    review = [g for g in groups if g.held_for_review]
    out("")
    out(f"notices read: {sampled}, without a usable identifier: {no_identifier}")
    out(f"organisations with an identifier: {stats['orgs_with_identifier']} "
        f"(conflicting identifiers on {stats['orgs_conflicting']})")
    out(f"identifiers shared by two or more organisations: {len(groups)}")
    out(f"  merge: {len(merge)} groups, {sum(len(g.absorbed) for g in merge)} organisation rows "
        f"become aliases, {sum(g.notices_moved for g in merge)} notices re-pointed")
    out(f"  held for review (written as merge candidates, not merged): "
        f"{sum(len(g.held_for_review) for g in review)} rows in {len(review)} groups")
    out(f"identifiers attached to a single organisation: {len(singles)}")
    out("")
    out(f"top {min(top, len(groups))} groups by size:")
    for g in groups[:top]:
        tail = f"  [{len(g.held_for_review)} held: {g.review}]" if g.review else ""
        absorbed = ", ".join(o.name[:38] for o in g.absorbed[:3])
        out(f"  {len(g.absorbed) + len(g.held_for_review) + 1:>4} orgs  {g.country} "
            f"{g.identifier:<18} {g.notices_moved:>5} notices  keep {g.survivor.name[:44]!r}; "
            f"absorbs {absorbed}{' ...' if len(g.absorbed) > 3 else ''}{tail}")

    result = {"merged_groups": 0, "merged_orgs": 0, "attached": 0, "candidates": 0}
    if not apply:
        out("\ndry run: nothing written (add --yes)")
        return result

    result["skipped"] = result["failed_groups"] = 0
    for g in merge:
        # One group at a time, each its own transaction and its own commit: a run of an
        # hour must not be lost to the one group that cannot be merged, and what was
        # merged stays merged if the process is stopped.
        try:
            with conn.transaction():
                merged = _merge_group(conn, g, result)
            conn.commit()
        except Exception as exc:  # noqa: BLE001 - logged; the other groups go on
            log.error("group %s in %s not merged: %s", g.identifier, g.country, exc)
            conn.rollback()
            result["failed_groups"] += 1
            continue
        result["merged_orgs"] += merged
        result["merged_groups"] += 1 if merged else 0
    for g in review:
        for o in g.held_for_review:
            db.add_merge_candidate(
                conn, g.survivor.id, o.id, method=METHOD, confidence=CONFIDENCE,
                evidence=f"identifier {g.identifier} in {g.country}; not merged: {g.review}",
                detected_by="backfill_buyer_identifiers")
            result["candidates"] += 1
    for org, ident in singles:
        conn.execute(
            """UPDATE organisation SET national_reg_no = %s, identifier_method = %s,
                      identifier_confidence = %s
                WHERE id = %s AND national_reg_no IS NULL
                  AND NOT EXISTS (SELECT 1 FROM organisation x
                                   WHERE x.country = %s AND x.national_reg_no = %s)""",
            (ident, METHOD, 0.90, org.id, org.country, ident))
        result["attached"] += 1
    conn.commit()
    out(f"\napplied: {result}")
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="merge and attach (default: report only)")
    p.add_argument("--rounds", type=int, default=3,
                   help="passes over the organisations still without an identifier (default 3)")
    p.add_argument("--max-bundles", type=int, default=None,
                   help="stop after this many bundles (a sample)")
    p.add_argument("--max-group", type=int, default=DEFAULT_MAX_GROUP,
                   help="a group larger than this is left for review")
    p.add_argument("--top", type=int, default=15)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        run(conn, build_store(), rounds=args.rounds, max_bundles=args.max_bundles,
            max_group=args.max_group, apply=args.yes, top=args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
