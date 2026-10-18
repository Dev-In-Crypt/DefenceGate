"""Split supplier organisations that hold awards under two different legal forms (WP-41, N11).

    python -m dgate.ops.split_legal_forms           # report what would be split, write nothing
    python -m dgate.ops.split_legal_forms --yes     # split

The resolution cascade used to treat the name without its legal form as the whole name, so `Renk
Aktiengesellschaft` and `RENK GmbH` became one supplier. Two different legal forms are two bodies unless
a register says otherwise (the cascade now keeps them apart: `resolution/cascade.py`, legal-form guard).
This repairs the suppliers already stored: for an organisation whose awards state names of two or more
legal-form classes, the awards of the minority classes move to an organisation of their own, unless the
notices state the same registration number for both (then the register says it is one body, and
nothing moves). The organisation keeps the class most of its awards state (ties: the class of its
earliest award). Awards with a name that states no form stay where they are.

Each new organisation gets the name its awards state, its aliases, and a `resolution_review` pair with
the old one (method `legal_form_conflict`) so that a person can undo it. No award is deleted, no
organisation is merged. Idempotent: a second run finds nothing to split. No network, no model.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter, defaultdict
from typing import Any

from .. import db
from ..config import settings
from ..normalise import normalise_identifier
from ..resolution.cascade import _new_organisation, add_review
from ..resolution.names import key_of, legal_form_of

log = logging.getLogger("split_legal_forms")


def plan(awards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The splits: {org, keep: class, move: {class: [award ids]}, names: {class: name}} for each
    organisation whose awards state two or more legal-form classes with different registration numbers.

    awards: id, organisation_id, name_as_stated, identifier_as_stated, supplier_country, opportunity_id."""
    by_org: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for a in awards:
        by_org[a["organisation_id"]].append(a)
    out = []
    for org, rows in by_org.items():
        classes: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for a in sorted(rows, key=lambda r: r["id"]):
            cls = legal_form_of(a["name_as_stated"])
            if cls:
                classes[cls].append(a)
        if len(classes) < 2:
            continue
        ids = {cls: {normalise_identifier(a["identifier_as_stated"], a["supplier_country"]) for a in rs} - {None}
               for cls, rs in classes.items()}
        stated = set().union(*ids.values())
        if len(stated) == 1 and all(ids[c] for c in classes):
            continue                                # the register says: one body
        keep = max(classes, key=lambda c: (len(classes[c]), -min(a["id"] for a in classes[c])))
        out.append({"org": org, "keep": keep,
                    "move": {c: [a["id"] for a in rs] for c, rs in classes.items() if c != keep},
                    "names": {c: classes[c][0]["name_as_stated"] for c in classes if c != keep},
                    "country": classes[keep][0]["supplier_country"],
                    "ids": {c: sorted(ids[c]) for c in classes}})
    return out


def run(conn, *, apply: bool = False, out=print) -> Counter:
    awards = conn.execute(
        """SELECT a.id, a.organisation_id, a.name_as_stated, a.identifier_as_stated, a.supplier_country
             FROM award a JOIN organisation o ON o.id = a.organisation_id
            WHERE o.merged_into IS NULL AND NOT o.suppressed""").fetchall()
    splits = plan(awards)
    c: Counter = Counter(organisations=len(splits), awards=sum(len(v) for s in splits for v in s["move"].values()))
    for s in splits:
        out(f"organisation {s['org']}: keeps {s['keep']}; moves "
            + ", ".join(f"{len(v)} awards stated as {s['names'][k]!r} ({k})" for k, v in s["move"].items())
            + f"; numbers stated {s['ids']}")
        if not apply:
            continue
        for cls, award_ids in s["move"].items():
            name = s["names"][cls]
            key, _ = key_of(name)
            new = _new_organisation(conn, name, key, s["country"], None, None)
            conn.execute("UPDATE award SET organisation_id = %s WHERE id = ANY(%s)", (new, award_ids))
            db._record_alias(conn, new, name, key, None, s["country"], "legal_form", 0.90)
            add_review(conn, s["org"], new, relation="same_name_other_legal_form", method="legal_form_conflict",
                       confidence=0.50, evidence={"key": key, "country": s["country"], "form": cls,
                                                  "split_by": "ops.split_legal_forms"})
            c["organisations_new"] += 1
        conn.commit()
    out(f"{dict(c)} ({'written' if apply else 'dry run, nothing is written'})")
    return c


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="split; without it nothing changes")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        run(conn, apply=a.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
