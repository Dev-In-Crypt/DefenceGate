"""Owner-run: clean the supplier rows that were stored before the loader refused them (WP-39, N1 and N8).

    python -m dgate.ops.clean_suppliers            # dry run: what would change
    python -m dgate.ops.clean_suppliers --yes      # write

Two things, each idempotent (a second run changes nothing):

  1. `award.identifier_as_stated` that is not a registration number: a telephone number or an e-mail address typed
     into the field (4 profiles on 18 October 2026), or a word or a name ("Unknown", "BAE Systems Ltd"). Set to NULL.
     An organisation whose `national_reg_no` was attached from one of those telephone numbers (it passed the
     number check before `normalise_identifier` refused a leading "+") loses that number and its method, so the
     next notice that states the real one can attach it.
  2. `award.excluded_reason` for a winner string that is no supplier: a placeholder ("keine Angabe"), a
     consortium written as one name, text with a replacement character, contact details in the name, a natural
     person by the rule the loader applies (`awards.person_reason`), and a company written with a role note
     ("Stekop S.A. - Lider": the stored organisation was made from the annotated string, so it is not the company;
     the loader now strips the note). The row is kept and every supplier query skips it (`suppliers.SCOPE`).
     The output counts the notices that name a consortium or carry a role note: deleting their `award_notice`
     row makes the next `awards` run read them again with the stripped name (a decision for the owner):
     DELETE FROM award_notice n USING award a
      WHERE a.opportunity_id = n.opportunity_id AND a.excluded_reason IN ('role_note', 'consortium_string');

No organisation, alias or notice row is deleted. The raw store (`ted_awards/`) keeps the winner fields of each
notice as TED returned them, natural persons blanked; telephone numbers typed into an identifier field are in the
bundles landed before this change. Rewriting a bundle is the owner's decision (docs/DATA_PROTECTION.md).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from typing import Any

from .. import db
from ..awards import clean_supplier_name, person_reason
from ..config import settings
from ..normalise import looks_like_contact, normalise_identifier


def _digits(text: str) -> set[str]:
    s = re.sub(r"[^A-Z0-9]", "", text.upper())
    return {s, s.lstrip("0")} - {""}


def verdict(name: str, country: str | None, ident: str | None = None) -> str | None:
    """Why a stored winner string is no supplier, or None. The stated number decides first (a CIF is an entity's,
    a DNI, NIE or the publisher's mask a person's), as in the loader."""
    person = person_reason(name, None if looks_like_contact(ident) else ident, country)
    if person:
        return person
    problem, cleaned = clean_supplier_name(name)
    return problem or ("role_note" if cleaned != name.strip() else None)


def run(conn, *, write: bool = False) -> dict[str, Any]:
    rows = conn.execute(
        """SELECT id, organisation_id, supplier_country AS country, name_as_stated AS name,
                  identifier_as_stated AS ident, excluded_reason AS reason, opportunity_id
             FROM award""").fetchall()
    out: dict[str, Any] = {"awards": len(rows), "identifier_contact": 0, "identifier_not_a_number": 0,
                           "organisations_reg_cleared": 0, "excluded": Counter(), "excluded_new": 0,
                           "samples": defaultdict(list)}
    blank_ids: list[int] = []
    contact_by_org: dict[int, set[str]] = defaultdict(set)
    flag: dict[str, list[int]] = defaultdict(list)
    orgs: set[int] = set()
    reread: set[int] = set()
    for r in rows:
        ident = r["ident"]
        if ident and looks_like_contact(ident):
            out["identifier_contact"] += 1
            blank_ids.append(r["id"])
            contact_by_org[r["organisation_id"]] |= _digits(ident)
        elif ident and not normalise_identifier(ident, r["country"]):
            out["identifier_not_a_number"] += 1
            blank_ids.append(r["id"])
        why = verdict(r["name"], r["country"], ident)
        if not why:
            continue
        out["excluded"][why] += 1
        orgs.add(r["organisation_id"])
        if why in ("consortium_string", "role_note"):
            reread.add(r["opportunity_id"])
        if why not in ("contact_in_name",) and not why.startswith("person") and len(out["samples"][why]) < 12:
            out["samples"][why].append(r["name"][:90])
        if r["reason"] != why:
            flag[why].append(r["id"])
            out["excluded_new"] += 1
    out["excluded_orgs"], out["reread_notices"] = len(orgs), len(reread)

    reg = [(o, c) for o, cands in contact_by_org.items() for c in cands]
    if write:
        if blank_ids:
            conn.execute("UPDATE award SET identifier_as_stated = NULL WHERE id = ANY(%s)", (blank_ids,))
        for why, ids in flag.items():
            conn.execute("UPDATE award SET excluded_reason = %s WHERE id = ANY(%s)", (why, ids))
    where = "WHERE id = %s AND national_reg_no = %s AND identifier_method = 'identifier'"
    for org_id, number in reg:
        if write:
            done = conn.execute("UPDATE organisation SET national_reg_no = NULL, identifier_method = NULL, "
                                f"identifier_confidence = NULL {where} RETURNING id", (org_id, number)).fetchone()
        else:
            done = conn.execute(f"SELECT 1 FROM organisation {where}", (org_id, number)).fetchone()
        out["organisations_reg_cleared"] += done is not None
    if write:
        conn.commit()
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dgate.ops.clean_suppliers", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write (the default is a dry run)")
    a = p.parse_args(argv)
    with db.connect(settings().dsn) as conn:
        res = run(conn, write=a.yes)
    print(("written" if a.yes else "dry run (add --yes)"), "-", res["awards"], "award rows read")
    print("identifiers cleared: contact data", res["identifier_contact"], "| not a number", res["identifier_not_a_number"],
          "| organisations that lose a telephone number as registration number", res["organisations_reg_cleared"])
    print("award rows excluded as no supplier:", dict(res["excluded"]), "| marked now:", res["excluded_new"],
          "| organisations affected:", res["excluded_orgs"], "| notices to read again:", res["reread_notices"])
    for reason, names in res["samples"].items():
        print(f"  {reason}: " + " | ".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
