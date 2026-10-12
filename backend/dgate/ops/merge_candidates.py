"""Find organisations that may be one body, and write them down as merge candidates.

Nothing here merges anything. A pair is written to `organisation_merge_candidate`
with the method that found it and a confidence, `status = 'pending'`, and waits for
a person (or for the identifier backfill, which has a stronger fact).

Two methods, both within one country:

  folded_name  the names are equal once state prefixes and suffixes are folded and
               word order and dashes are ignored ("Ceska republika - Ministerstvo
               obrany", "Ministerstvo obrany - Ceska republika", "Ministerstvo
               obrany CR"; a Romanian unit by its number). Confidence 0.90.
  trigram      the stored names are 0.90 or more similar. Confidence is the
               similarity itself.

The stored names are not changed and the fold is not used as a lookup key
(`normalise_org_name(fold_state=True)` is opt-in for exactly this reason).

    python -m dgate.ops.merge_candidates                      # dry run, organisations holding notices
    python -m dgate.ops.merge_candidates --country CZ --yes
    python -m dgate.ops.merge_candidates --all-organisations  # also those without notices
"""

from __future__ import annotations

import argparse
import collections
import logging
import sys

from .. import db
from ..config import settings
from ..normalise import candidate_key

log = logging.getLogger("merge_candidates")

DETECTED_BY = "ops.merge_candidates"
FOLDED_CONFIDENCE = 0.90
TRIGRAM_MIN = 0.90


def folded_pairs(orgs: list[dict], focus: set[int] | None) -> list[tuple[int, int, str]]:
    """(a, b, key) for organisations sharing a folded key; a star around the
    lowest id of each group, and only groups touching `focus` when it is given."""
    groups: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for o in orgs:
        key = candidate_key(o["canonical_name"])
        if key:
            groups[(o["country"], key)].append(o)
    out = []
    for (_, key), members in groups.items():
        if len(members) < 2:
            continue
        if focus is not None and not any(m["id"] in focus for m in members):
            continue
        members.sort(key=lambda m: m["id"])
        head = members[0]
        for m in members[1:]:
            out.append((head["id"], m["id"], key))
    return out


def run(conn, *, country: str | None = None, all_organisations: bool = False,
        apply: bool = False, out=print, sample: int = 12) -> dict[str, int]:
    where, params = ["g.merged_into IS NULL"], []
    if country:
        where.append("g.country = %s")
        params.append(country.upper())
    orgs = conn.execute(
        f"SELECT g.id, g.country, g.canonical_name FROM organisation g WHERE {' AND '.join(where)}",
        params).fetchall()
    held = {r["buyer_org_id"] for r in conn.execute(
        "SELECT DISTINCT buyer_org_id FROM opportunity WHERE buyer_org_id IS NOT NULL")}
    focus = None if all_organisations else held
    out(f"organisations considered: {len(orgs)}; holding notices: {len(held)}")

    names = {o["id"]: o["canonical_name"] for o in orgs}
    pairs: dict[tuple[int, int, str], float] = {}
    for a, b, _key in folded_pairs(orgs, focus):
        pairs[(a, b, "folded_name")] = FOLDED_CONFIDENCE
    n_folded = len(pairs)

    conn.execute("SELECT set_config('pg_trgm.similarity_threshold', %s, false)",
                 (str(TRIGRAM_MIN),))
    left = [o for o in orgs if focus is None or o["id"] in focus]
    for i, o in enumerate(left, 1):
        for r in conn.execute(
                """SELECT b.id, b.canonical_name, similarity(b.canonical_name, %s) AS sim
                     FROM organisation b
                    WHERE b.country = %s AND b.id <> %s AND b.merged_into IS NULL
                      AND b.canonical_name %% %s""",
                (o["canonical_name"], o["country"], o["id"], o["canonical_name"])).fetchall():
            a, b = sorted((o["id"], r["id"]))
            names.setdefault(r["id"], r["canonical_name"])
            pairs.setdefault((a, b, "trigram"), float(r["sim"]))
        if i % 1000 == 0:
            log.info("trigram: %s of %s", i, len(left))
    n_trigram = len(pairs) - n_folded

    out(f"candidate pairs: folded_name {n_folded}, trigram {n_trigram}")
    for (a, b, method), conf in list(pairs.items())[:sample]:
        out(f"  {method:11s} {conf:.2f}  {names.get(a, a)[:50]!r}  ~  {names.get(b, b)[:50]!r}")
    if not apply:
        out("dry run: nothing written (add --yes)")
        return {"folded_name": n_folded, "trigram": n_trigram, "written": 0}

    written = 0
    for (a, b, method), conf in pairs.items():
        db.add_merge_candidate(
            conn, a, b, method=method, confidence=conf,
            evidence=f"{names.get(a, a)!r} and {names.get(b, b)!r}", detected_by=DETECTED_BY)
        written += 1
    conn.commit()
    out(f"written (existing pairs are left as they are): {written}")
    return {"folded_name": n_folded, "trigram": n_trigram, "written": written}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--country")
    p.add_argument("--all-organisations", action="store_true")
    p.add_argument("--yes", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        run(conn, country=args.country, all_organisations=args.all_organisations, apply=args.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
