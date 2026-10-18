"""Merge organisation rows that are one body by a deterministic key (WP-41, N5).

    python -m dgate.ops.org_dedupe                 # dry run: every group, nothing written
    python -m dgate.ops.org_dedupe --yes           # merge, then rebuild the directory table
    python -m dgate.ops.org_dedupe --yes --limit 200

Two rows of one country are merged only when the cascade itself would have called them one body
(stage 2: the same normalised name) and nothing contradicts it:

  name_key         the same key (`resolution.names.key_of`: accents, case, hyphens, ampersands,
                   legal forms of Europe stripped)             confidence 0.95, as stage 2 stores it
  name_key_spaces  the same key once spaces are removed ("UNIVERSITEDULUXEMBOURG", "ANGEWA NDTEN"):
                   a PDF broke or joined words                  confidence 0.90, and only for keys of
                   12 characters or more

and none of these holds in the group (then it is left alone, for the family layer or a person):

  * two different PICs, registration numbers or VAT numbers (the owner's standing decision: bodies with
    different registration numbers are never merged)
  * two different legal forms among the names (RENK AG and RENK GmbH are two bodies)
  * a row removed on request (suppressed)

The head of a group is the row that holds a PIC, else one with a readable name, else the oldest. Each other row is merged with
`db.merge_organisations` (method, confidence and evidence stored; aliases and notices re-pointed;
nothing deleted; undone by clearing `merged_into`: the alias remembers `prev_organisation_id`).
Open `resolution_review` pairs inside a merged group are closed as `merged`.

Idempotent: a second run finds no group. No network, no language model.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .. import db, networks
from ..config import settings
from ..resolution.cascade import clean_vat
from ..resolution.names import fold_key, key_of, legal_form_of

log = logging.getLogger("org_dedupe")

DETECTED_BY = "ops.org_dedupe"
CONF_KEY = 0.95
CONF_SPACES = 0.90
MIN_FOLD = 12            # the shortest key a spacing difference may merge
MIN_KEY = 4


@dataclass
class Group:
    head: int
    members: list[tuple[int, str, float]] = field(default_factory=list)       # (id, method, confidence)
    key: str = ""
    names: list[str] = field(default_factory=list)


def key_of_row(row: dict[str, Any]) -> str:
    return key_of(row.get("display") or row["canonical"])[0]


def plan(rows: list[dict[str, Any]], forms: dict[int, set[str]] | None = None,
         focus: set[int] | None = None) -> tuple[list[Group], dict[str, int]]:
    """The groups to merge, and how many groups were left alone and why.

    rows: id, country, canonical, display, pic, reg, vat, suppressed (live rows only).
    focus: only groups with a row in this set are looked at (the organisations that took part in a
    project: the 24,000 procurement buyers that differ by a hyphen are the buyer list's display layer,
    `buyer_family_member`, and are not merged here).
    forms: the legal-form classes of the names each row has been called, beyond its display name
    (from its aliases); the display name's own class is always counted."""
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        k = r.get("key") or key_of_row(r)
        if len(k) >= MIN_KEY and not k.isdigit():
            by_key[(r["country"], fold_key(k))].append({**r, "key": k})
    groups: list[Group] = []
    left: dict[str, int] = defaultdict(int)
    for (_, folded), members in by_key.items():
        if len(members) < 2 or (focus is not None and not any(m["id"] in focus for m in members)):
            continue
        pics = {m["pic"] for m in members if m["pic"]}
        regs = {m["reg"] for m in members if m["reg"]}
        vats = {v for v in (clean_vat(m.get("vat"), m["country"]) for m in members) if v}
        classes = {c for m in members for c in ({legal_form_of(m.get("display") or "")} | (forms or {}).get(m["id"], set())) if c}
        keys = {m["key"] for m in members}
        if any(m.get("suppressed") for m in members):
            left["suppressed"] += 1
        elif len(pics) > 1:
            left["different_pics"] += 1
        elif len(regs) > 1:
            left["different_registration_numbers"] += 1
        elif len(vats) > 1:
            left["different_vat_numbers"] += 1
        elif len(classes) > 1:
            left["different_legal_forms"] += 1
        elif len(keys) > 1 and len(folded) < MIN_FOLD:
            left["spacing_on_a_short_key"] += 1
        else:
            # the head: the row with a PIC, else one with a readable (mixed or upper case) name, else the oldest
            members.sort(key=lambda m: (m["pic"] is None, not m.get("display") or m["display"].islower(), m["id"]))
            head = members[0]
            g = Group(head["id"], key=head["key"], names=[head.get("display") or head["canonical"]])
            for m in members[1:]:
                same = m["key"] == head["key"]
                g.members.append((m["id"], "name_key" if same else "name_key_spaces",
                                  CONF_KEY if same else CONF_SPACES))
                g.names.append(m.get("display") or m["canonical"])
            groups.append(g)
    groups.sort(key=lambda g: (-len(g.members), g.head))
    return groups, dict(left)


def participants(conn) -> set[int]:
    """The live organisations with an active participation in a project."""
    return {r["org"] for r in conn.execute(
        """SELECT DISTINCT COALESCE(l.live_id, pa.organisation_id) AS org
             FROM participation pa LEFT JOIN organisation_merged_live l ON l.id = pa.organisation_id
            WHERE pa.active""").fetchall()}


def load(conn) -> tuple[list[dict[str, Any]], dict[int, set[str]], set[int]]:
    """The live organisations that could be merged, as `plan` wants them, the legal-form classes of the
    aliases of those, and the focus.

    Two passes so that the 430,000 organisations are never held as rows: the first streams id, country
    and name through a named cursor and keeps only the buckets (country, key without spaces) -> ids
    (about 100 MB); the second fetches the full rows of the buckets that have two rows and touch the focus."""
    focus = participants(conn)
    buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
    with conn.cursor(name="org_dedupe_names") as cur:
        cur.itersize = 20000
        cur.execute("""SELECT id, country, canonical_name, display_name FROM organisation
                        WHERE merged_into IS NULL AND canonical_name <> ''""")
        for r in cur:
            k = key_of(r["display_name"] or r["canonical_name"])[0]
            if len(k) >= MIN_KEY and not k.isdigit():
                buckets[(r["country"].strip(), fold_key(k))].append(r["id"])
    ids = [i for members in buckets.values() if len(members) > 1 and any(m in focus for m in members) for i in members]
    del buckets
    rows: list[dict[str, Any]] = []
    forms: dict[int, set[str]] = defaultdict(set)
    for n in range(0, len(ids), 5000):
        chunk = ids[n:n + 5000]
        rows += [{"id": r["id"], "country": r["country"].strip(), "canonical": r["canonical_name"],
                  "display": r["display_name"], "pic": r["eu_pic"], "reg": r["national_reg_no"],
                  "vat": r["vat_number"], "suppressed": r["suppressed"]}
                 for r in conn.execute(
                     """SELECT id, country, canonical_name, display_name, eu_pic, national_reg_no, vat_number, suppressed
                          FROM organisation WHERE id = ANY(%s)""", (chunk,)).fetchall()]
        for a in conn.execute("SELECT organisation_id, raw_name FROM organisation_alias WHERE organisation_id = ANY(%s)",
                              (chunk,)).fetchall():
            cls = legal_form_of(a["raw_name"])
            if cls:
                forms[a["organisation_id"]].add(cls)
    return rows, forms, focus


def run(conn, *, apply: bool = False, limit: int | None = None, out=print, sample: int = 15) -> dict[str, int]:
    rows, forms, focus = load(conn)
    groups, left = plan(rows, forms, focus)
    merged = 0
    counts = {"groups": len(groups), "rows_to_merge": sum(len(g.members) for g in groups), **{f"left_{k}": v for k, v in left.items()}}
    out(f"organisations in a candidate bucket: {len(rows)}; groups to merge: {len(groups)} ({counts['rows_to_merge']} rows); left alone: {left}")
    for g in groups[:sample]:
        out(f"  head {g.head}  {len(g.members)} more  {g.names[0][:60]!r}  <- " + " | ".join(n[:40] for n in g.names[1:4]))
    if not apply:
        out("dry run: nothing written (add --yes)")
        return {**counts, "merged": 0}
    for g in groups[:limit]:
        ids = [g.head] + [m[0] for m in g.members]
        for oid, method, conf in g.members:
            db.merge_organisations(conn, g.head, oid, method=method, confidence=conf,
                                   evidence=f"same key {g.key!r}", detected_by=DETECTED_BY)
            merged += 1
        conn.execute(
            """UPDATE resolution_review SET status = 'merged', decided_by = %s, decided_at = now()
                WHERE status = 'open' AND org_a = ANY(%s) AND org_b = ANY(%s)""", (DETECTED_BY, ids, ids))
        conn.commit()
    counts["merged"] = merged
    counts["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
    out(f"merged: {merged} rows in {min(len(groups), limit or len(groups))} groups")
    return counts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="merge; without it nothing changes")
    p.add_argument("--limit", type=int, default=None, help="merge at most this many groups")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        run(conn, apply=a.yes, limit=a.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
