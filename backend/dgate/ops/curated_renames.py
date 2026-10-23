"""Apply the curated list of renamed bodies (WP-87, owner decision of 22 October 2026).

    python -m dgate.ops.curated_renames          # report: what each entry covers, nothing written
    python -m dgate.ops.curated_renames --yes    # write

A body that was renamed publishes under two names, and no name rule can tell they are one: only a person who knows
the rename can. The list is curated by hand, each entry with its evidence and a confidence, and every row it joins is
stored with the method `curated_rename` and that confidence. Two kinds:

  buyers         `buyer_family.RENAMES` (Inspektorat Uzbrojenia, renamed Agencja Uzbrojenia on 1 January 2022). Public
                 bodies are never merged: the predecessor joins the successor's buyer family (display layer only,
                 `buyer_family_member`, the successor's row heads it). Written by `ops.buyer_families`, which the
                 worker also runs daily, so the family stays.
  organisations  `ORG_RENAMES` below: the live rows of one country whose name, folded (`resolution.names.key_of`, spaces
                 removed), is one of an entry's names are merged into the row with the successor's name
                 (`db.merge_organisations`: method, confidence and evidence stored; nothing deleted; undone like any
                 merge). An entry is refused, and reported, when its rows hold two different PICs, registration
                 numbers or VAT numbers (the owner's standing rule), or one of them was removed on request.

Idempotent: a second run finds nothing to write. No network, no language model.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from typing import Any

from .. import db, networks
from ..buyer_family import CURATED_RENAME
from ..config import settings
from ..resolution.cascade import clean_vat
from ..resolution.names import fold_key, key_of
from . import buyer_families

log = logging.getLogger("curated_renames")

DETECTED_BY = "ops.curated_renames"


@dataclass(frozen=True)
class OrgRename:
    country: str
    old: tuple[str, ...]       # the predecessor's names (and spellings), as written
    new: str                   # the successor's name, as written
    confidence: float
    evidence: str


ORG_RENAMES: tuple[OrgRename, ...] = (
    # Instytut Lotnictwa joined the Lukasiewicz Research Network on 1 April 2019 and has been "Sieć Badawcza
    # Łukasiewicz - Instytut Lotnictwa" since; CORDIS and the EDF factsheets hold both, and the second spelling joins
    # two words ("...INSTYTUTLOTNICTWA").
    OrgRename("PL", ("Instytut Lotnictwa", "Siec Badawcza Lukasiewicz - Instytutlotnictwa"),
              "Siec Badawcza Lukasiewicz - Instytut Lotnictwa", 0.95,
              "Instytut Lotnictwa became Siec Badawcza Lukasiewicz - Instytut Lotnictwa on 1 April 2019 "
              "(Lukasiewicz Research Network act); one institute, one KRS entry"),
)


def folded(name: str) -> str:
    return fold_key(key_of(name)[0])


def org_rows(conn, entry: OrgRename) -> list[dict[str, Any]]:
    """The live rows of the entry's country whose folded name is one of its names, the successor's first."""
    wanted = {folded(n) for n in (*entry.old, entry.new)}
    # a cheap SQL filter on the stored name, then the exact test in Python
    like = [re.sub(r"[^a-z0-9]", "", w)[-12:] for w in wanted]
    rows = conn.execute(
        """SELECT id, canonical_name, display_name, eu_pic, national_reg_no, vat_number, suppressed, country
             FROM organisation
            WHERE merged_into IS NULL AND country = %s
              AND regexp_replace(canonical_name, '[^a-z0-9]', '', 'g') LIKE ANY(%s)""",
        (entry.country, [f"%{w}" for w in like])).fetchall()
    out = [dict(r) for r in rows if folded(r["display_name"] or r["canonical_name"]) in wanted]
    new = folded(entry.new)
    out.sort(key=lambda r: (folded(r["display_name"] or r["canonical_name"]) != new, r["eu_pic"] is None, r["id"]))
    return out


def refusal(rows: list[dict[str, Any]]) -> str | None:
    if any(r["suppressed"] for r in rows):
        return "a row was removed on request"
    for label, values in (("PICs", {r["eu_pic"] for r in rows if r["eu_pic"]}),
                          ("registration numbers", {r["national_reg_no"] for r in rows if r["national_reg_no"]}),
                          ("VAT numbers", {v for v in (clean_vat(r["vat_number"], r["country"]) for r in rows) if v})):
        if len(values) > 1:
            return f"two different {label}: a person decides (bodies with different numbers are never merged)"
    return None


def run(conn, *, apply: bool = False, out=print) -> dict[str, int]:
    counts = {"buyer_rows": 0, "org_entries": 0, "org_rows_to_merge": 0, "org_refused": 0, "merged": 0}
    # buyers: the families the curated rule makes
    for g in buyer_families.all_groups(conn):
        renamed = [m for m in g.members if m.method == CURATED_RENAME]
        if g.head.method == CURATED_RENAME:
            renamed.append(g.head)
        if renamed:
            out(f"buyer family {g.key}: head {g.head.org_id} {g.head.name!r}")
            for m in renamed:
                out(f"    {m.org_id:>8} {m.notices:>6} notices  {m.name!r}  ({m.method}, {m.confidence})")
            counts["buyer_rows"] += len(renamed)
    # organisations: merges
    for entry in ORG_RENAMES:
        rows = org_rows(conn, entry)
        counts["org_entries"] += 1
        names = " | ".join(f"{r['id']} {(r['display_name'] or r['canonical_name'])!r}" for r in rows) or "no row"
        if len(rows) < 2:
            out(f"organisations {entry.new!r}: nothing to merge ({names})")
            continue
        why = refusal(rows)
        if why:
            counts["org_refused"] += 1
            out(f"organisations {entry.new!r}: refused, {why} ({names})")
            continue
        counts["org_rows_to_merge"] += len(rows) - 1
        out(f"organisations {entry.new!r}: head {names.split(' | ')[0]} <- " + " | ".join(names.split(" | ")[1:]))
        if apply:
            for r in rows[1:]:
                db.merge_organisations(conn, rows[0]["id"], r["id"], method=CURATED_RENAME,
                                       confidence=entry.confidence, evidence=entry.evidence, detected_by=DETECTED_BY)
                counts["merged"] += 1
            conn.commit()
    if apply:
        counts.update({f"families_{k}": v for k, v in buyer_families.run(conn, write=True).items()})
        if counts["merged"]:
            counts["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
    else:
        out("dry run: nothing written (add --yes)")
    return counts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="write; without it nothing changes")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        counts = run(conn, apply=a.yes)
    log.info("%s", ", ".join(f"{k} {v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
