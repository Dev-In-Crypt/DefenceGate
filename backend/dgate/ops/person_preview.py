"""Owner-run, read-only: which award rows `clean_suppliers --yes` would mark as a natural person (WP-94).

    python -m dgate.ops.person_preview              # counts and 60 random distinct names
    python -m dgate.ops.person_preview --sample 200 --country ES

The same verdict as `clean_suppliers` (`verdict(name, country, identifier_as_stated)`), in a read-only transaction:
nothing is written. Check the sample before running `clean_suppliers --yes`.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from collections import Counter

from .. import awards, db
from ..config import settings
from .clean_suppliers import verdict


def id_class(ident: str | None) -> str:
    """none, masked, dni, nie, cif or other: the kind of number a row states (the number itself is not printed)."""
    raw = (ident or "").strip().upper()
    if not raw:
        return "none"
    if awards._MASKED_ID.fullmatch(raw):
        return "masked"
    s = re.sub(r"[\s.\-/]", "", raw)
    s = s[2:] if s.startswith("ES") and len(s) == 11 else s
    if re.fullmatch(r"\d{8}[A-Z]", s):
        return "dni"
    if re.fullmatch(r"[XYZ]\d{7}[A-Z]", s):
        return "nie"
    return "cif" if awards._ES_ENTITY_ID.fullmatch(s) else "other"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dgate.ops.person_preview", description=__doc__.split("\n\n")[0])
    p.add_argument("--sample", type=int, default=60)
    p.add_argument("--country", help="only this supplier country (e.g. ES)")
    a = p.parse_args(argv)
    with db.connect(settings().dsn) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        rows = conn.execute("SELECT supplier_country AS country, name_as_stated AS name, identifier_as_stated AS ident, "
                            "excluded_reason AS reason FROM award").fetchall()
    rows = [r for r in rows if not a.country or r["country"] == a.country]
    reasons: Counter[str] = Counter()
    classes: Counter[tuple[str, str]] = Counter()
    names: dict[tuple[str, str | None], tuple[str, str]] = {}
    new = 0
    for r in rows:
        why = verdict(r["name"], r["country"], r["ident"])
        if not why or not why.startswith("person"):
            continue
        reasons[why] += 1
        classes[(why, id_class(r["ident"]))] += 1
        new += r["reason"] != why
        names[(r["name"].strip(), r["country"])] = (why, id_class(r["ident"]))
    print(len(rows), "award rows read;", sum(reasons.values()), "would be a natural person", dict(reasons),
          "| not marked so today:", new)
    print("by reason and identifier class:", {f"{w}/{c}": n for (w, c), n in sorted(classes.items())})
    print(len(names), "distinct (name, country) flagged; by country:", dict(Counter(c for _, c in names)))
    for (name, country), (why, cls) in random.sample(sorted(names.items()), min(a.sample, len(names))):
        print(f"  {country or '--'}  {why:18} {cls:6} {name[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
