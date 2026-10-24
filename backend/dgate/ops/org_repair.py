"""Organisation identifiers and buyer records (WP-115, coverage audit of 24 October 2026).

Five steps, each a report by default; `--yes` writes. Nothing is deleted; every change but the contact clean-up is
logged in `organisation_repair` with what it replaced, and `--undo FROM TO` reverses steps 1, 2 and 5 of a window.

  false-ids   A case reference stored as a registration number ("DEZ/26/019/2020": one Polish hospital on 340
              rows). Live PL and ES rows whose number `normalise_identifier` no longer accepts (NIP/REGON/KRS,
              NIF/CIF/NIE by shape and check digit) lose it (logged with its value); a row whose name and country
              equal those of a row with a valid number, or with none, is merged into that one (method
              `false_identifier_rejoin`, 0.95, the exact-name match it would have had without the false number).
              A group with two different valid numbers is not merged (two bodies: the owner's rule); only the false
              numbers go. A number written with the country prefix (ESA28015865) is re-spelt to the register's
              form (A28015865) when no other row holds it. The report lists every group.
  chains      merged_into pointing at a row that is itself merged: re-pointed to the end of the chain.
  contacts    Telephone, fax and e-mail blocks in organisation names and aliases (`strip_name_contacts`). Counts
              only, never values; not logged with the old value (personal data), so this step has no undo.
  winners     Current awards whose winner is the notice's own buyer (same name, same organisation or one family):
              `excluded_reason = 'buyer_as_winner'` (the row stays; every supplier query skips it).
  unlinked    Report: live organisations nothing references (no notice, award or participation), by source, role
              and creation path, and how many pending merge candidates involve one or two (a pair of two is
              skipped by `ops.accept_merge_candidates`). Writes nothing.

    python -m dgate.ops.org_repair                       # all reports
    python -m dgate.ops.org_repair --step false-ids --yes
    python -m dgate.ops.org_repair --undo FROM TO [--yes]

Every statement stops after 30 s; writes are committed every 100 groups.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import Counter, defaultdict
from typing import Any

from .. import db, networks
from ..awards import is_buyer_body, same_name_as_buyer
from ..config import settings
from ..normalise import normalise_identifier, normalise_org_name, strip_name_contacts
from . import undo_merges

log = logging.getLogger("org_repair")

DETECTED_BY = "ops.org_repair"
REJOIN = "false_identifier_rejoin"
CONF_REJOIN = db.CONF_EXACT_NAME
COUNTRIES = ("PL", "ES")
COMMIT_EVERY = 100
UNNAMED = "unnamed organisation"
STEPS = ("false-ids", "chains", "contacts", "winners", "unlinked")


def _shape(number: str | None) -> str:
    """A number's shape for a report (digits as 9, letters as A): never its value."""
    return re.sub(r"[A-Z]", "A", re.sub(r"\d", "9", number or ""))


def _kind(country: str, number: str) -> str:
    """Which register a valid number is of: a Polish one by its length (NIP or KRS 10, REGON 9 or 14), a Spanish
    NIF is one register."""
    return str(len(number)) if country == "PL" else "nif"


def _personal_number(country: str, number: str) -> bool:
    """A number that may be a natural person's (a Polish PESEL, a Spanish DNI or NIE): cleared, not kept in the log."""
    if country == "PL":
        return bool(re.fullmatch(r"\d{11}", number))
    return bool(re.fullmatch(r"(?:ES)?[XYZ]?\d{7,8}[A-Z]", number))       # a DNI or NIE, mistyped


# ----------------------------------------------------------------------------- 1. false identifiers

def plan_false_ids(rows: list[dict[str, Any]], siblings: dict[tuple[str, str], list[dict[str, Any]]]
                   ) -> tuple[list[dict[str, Any]], list[tuple[int, str, str]]]:
    """The groups (one per country and name holding a false number) and the re-spellings (id, old, new).

    `rows` are live rows with a number; `siblings` the live rows of each (country, lower name)."""
    respell: list[tuple[int, str, str]] = []
    false_keys: set[tuple[str, str]] = set()
    for r in rows:
        n = normalise_identifier(r["national_reg_no"], r["country"])
        if n is None:
            false_keys.add((r["country"], r["canonical_name"].lower()))
        elif n != r["national_reg_no"]:
            respell.append((r["id"], r["national_reg_no"], n))
    groups = []
    for key in sorted(false_keys):
        members = sorted(siblings.get(key, []), key=lambda m: m["id"])
        bad = [m for m in members
               if m["national_reg_no"] and normalise_identifier(m["national_reg_no"], m["country"]) is None]
        valid = {normalise_identifier(m["national_reg_no"], m["country"]) for m in members
                 if m["national_reg_no"]} - {None}
        g = {"country": key[0], "name": key[1], "first": members[0]["id"] if members else None,
             "rows": len(members), "clear": [m["id"] for m in bad],
             "shapes": Counter(_shape(m["national_reg_no"]) for m in bad), "target": None, "merge": []}
        # two numbers of one register are two bodies; a NIP beside a REGON (a 340-row hospital holds both) is not
        kinds = Counter(_kind(key[0], v) for v in valid)
        if any(n > 1 for n in kinds.values()):
            g["decision"] = "held_two_numbers"
        else:
            target = (next((m for m in members if m["national_reg_no"] and m["id"] not in g["clear"]), None)
                      or next((m for m in members if not m["national_reg_no"]), None)
                      or members[0])
            g["target"] = target["id"]
            g["merge"] = [m["id"] for m in bad if m["id"] != target["id"]]
            g["decision"] = "rejoin" if g["merge"] else "clear_only"
        groups.append(g)
    return groups, respell


def false_ids(conn, *, apply: bool, out=print) -> dict[str, Any]:
    rows = [dict(r) for r in conn.execute(
        """SELECT id, country, canonical_name, national_reg_no FROM organisation
            WHERE merged_into IS NULL AND country = ANY(%s) AND national_reg_no IS NOT NULL""",
        (list(COUNTRIES),)).fetchall()]
    keys: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if normalise_identifier(r["national_reg_no"], r["country"]) is None:
            keys[r["country"]].add(r["canonical_name"].lower())
    siblings: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for country, names in keys.items():
        names_l = sorted(names)
        for i in range(0, len(names_l), 1000):
            for m in conn.execute(
                    """SELECT id, country, canonical_name, national_reg_no FROM organisation
                        WHERE country = %s AND lower(canonical_name) = ANY(%s) AND merged_into IS NULL""",
                    (country, names_l[i:i + 1000])).fetchall():
                siblings[(country, m["canonical_name"].lower())].append(dict(m))
    groups, respell = plan_false_ids(rows, siblings)
    by_decision = Counter(g["decision"] for g in groups)
    res = {"rows_with_number": len(rows), "groups": len(groups), "by_decision": dict(by_decision),
           "numbers_cleared": sum(len(g["clear"]) for g in groups),
           "rows_rejoined": sum(len(g["merge"]) for g in groups), "respelt": len(respell),
           "by_country": dict(Counter(g["country"] for g in groups))}
    out(f"false identifiers: {res}")
    # one line per group, by ids (a Spanish supplier row may carry a sole trader's name: names are not printed)
    for g in sorted(groups, key=lambda g: (-g["rows"], g["country"], g["name"])):
        out(f"  {g['country']} {g['decision']:<16} first row {g['first']} rows {g['rows']:>4} clear "
            f"{len(g['clear']):>4} merge {len(g['merge']):>4} into {g['target']} shapes "
            f"{dict(g['shapes'].most_common(3))}")
    if not apply:
        conn.rollback()
        return res
    for n, g in enumerate(groups, 1):
        by_id = {m["id"]: m for m in siblings[(g["country"], g["name"])]}
        for oid in g["clear"]:
            old = by_id[oid]["national_reg_no"]
            conn.execute("""UPDATE organisation SET national_reg_no = NULL, identifier_method = NULL,
                                   identifier_confidence = NULL WHERE id = %s AND national_reg_no = %s""", (oid, old))
            db.log_repair(conn, oid, "clear_false_identifier",
                          old_value=None if _personal_number(g["country"], old) else old, new_value=None,
                          method="wp115_register_check", detected_by=DETECTED_BY)
        for oid in g["merge"]:
            db.merge_organisations(
                conn, g["target"], oid, method=REJOIN, confidence=CONF_REJOIN,
                evidence=f"same name and country; the only difference was a number of shape "
                         f"{_shape(by_id[oid]['national_reg_no'])} that is no {g['country']} register number",
                detected_by=DETECTED_BY)
        if n % COMMIT_EVERY == 0:
            conn.commit()
    for oid, old, new in respell:
        if conn.execute("SELECT 1 FROM organisation WHERE country = (SELECT country FROM organisation WHERE id = %s)"
                        " AND national_reg_no = %s", (oid, new)).fetchone():
            res["respell_held"] = res.get("respell_held", 0) + 1
            continue
        conn.execute("UPDATE organisation SET national_reg_no = %s WHERE id = %s", (new, oid))
        db.log_repair(conn, oid, "respell_identifier", old_value=old, new_value=new,
                      method="wp115_register_check", detected_by=DETECTED_BY)
    conn.commit()
    out(f"written: {res['numbers_cleared']} numbers cleared, {res['rows_rejoined']} rows rejoined, "
        f"{len(respell) - res.get('respell_held', 0)} re-spelt")
    return res


# ----------------------------------------------------------------------------- 2. merge chains

def chains(conn, *, apply: bool, out=print) -> dict[str, Any]:
    rows = [dict(r) for r in conn.execute(
        """SELECT o.id, o.merged_into, l.live_id,
                  (SELECT count(*) FROM award a WHERE a.organisation_id = o.id) AS awards
             FROM organisation o JOIN organisation_merged_live l ON l.id = o.id
            WHERE o.merged_into IS DISTINCT FROM l.live_id ORDER BY o.id""").fetchall()]
    res = {"rows_in_chains": len(rows), "awards_on_them": sum(r["awards"] for r in rows)}
    out(f"merge chains: {res}; " + ", ".join(f"{r['id']}>{r['merged_into']}>..>{r['live_id']}" for r in rows))
    if not apply:
        conn.rollback()
        return res
    for r in rows:
        conn.execute("UPDATE organisation SET merged_into = %s WHERE id = %s AND merged_into = %s",
                     (r["live_id"], r["id"], r["merged_into"]))
        db.log_repair(conn, r["id"], "repoint_merged_into", old_value=str(r["merged_into"]),
                      new_value=str(r["live_id"]), method="wp115_flatten", detected_by=DETECTED_BY)
    conn.commit()
    return res


# ----------------------------------------------------------------------------- 3. contact details

# what may hold one (a coarse filter in SQL; `strip_name_contacts` decides)
_CONTACT_SQL = r"(\m(tel|fax|phone|telefon|telefono|tlf|tfno|telephone)\M\s*\.?\s*:?\s*[\d(+]|@|\me-?mail\M|\+\d)"


def contacts(conn, *, apply: bool, out=print) -> dict[str, Any]:
    orgs = [dict(r) for r in conn.execute(
        """SELECT id, canonical_name, display_name FROM organisation
            WHERE canonical_name ~* %s OR display_name ~* %s""", (_CONTACT_SQL, _CONTACT_SQL)).fetchall()]
    aliases = [dict(r) for r in conn.execute(
        """SELECT id, raw_name, normalised_name, country_hint, source_id FROM organisation_alias
            WHERE raw_name ~* %s OR normalised_name ~* %s""", (_CONTACT_SQL, _CONTACT_SQL)).fetchall()]
    org_fix = []
    for o in orgs:
        cut = strip_name_contacts(o["canonical_name"])
        name = o["canonical_name"] if cut == o["canonical_name"] else (normalise_org_name(cut) or UNNAMED)
        disp = strip_name_contacts(o["display_name"]) if o["display_name"] else o["display_name"]
        if name != o["canonical_name"] or disp != o["display_name"]:
            org_fix.append((o["id"], name, disp or None))
    alias_fix = []
    for a in aliases:
        raw = strip_name_contacts(a["raw_name"]) or UNNAMED
        cut = strip_name_contacts(a["normalised_name"])
        norm = (normalise_org_name(raw) or UNNAMED) if (raw != a["raw_name"] or cut != a["normalised_name"])             else a["normalised_name"]
        if raw != a["raw_name"] or norm != a["normalised_name"]:
            alias_fix.append((a, raw, norm))
    res = {"organisation_names": len(org_fix), "aliases": len(alias_fix),
           "alias_emails": sum("@" in a["raw_name"] for a, _, _ in alias_fix)}
    out(f"contact details in names (counts only): {res}")
    if not apply:
        conn.rollback()
        return res
    for oid, name, disp in org_fix:
        conn.execute("UPDATE organisation SET canonical_name = %s, display_name = %s WHERE id = %s",
                     (name, disp, oid))
        db.log_repair(conn, oid, "strip_contact_name", old_value=None, new_value=None,
                      method="wp115_contacts", detected_by=DETECTED_BY)
    clashes = 0
    for a, raw, norm in alias_fix:
        taken = conn.execute(
            """SELECT 1 FROM organisation_alias WHERE normalised_name = %s AND country_hint IS NOT DISTINCT FROM %s
                  AND source_id IS NOT DISTINCT FROM %s AND id <> %s""",
            (norm, a["country_hint"], a["source_id"], a["id"])).fetchone()
        if taken:                       # the clean spelling is already an alias: this one keeps a key of its own
            clashes += 1
            norm = f"{norm} (alias {a['id']})"
        conn.execute("UPDATE organisation_alias SET raw_name = %s, normalised_name = %s WHERE id = %s",
                     (raw, norm, a["id"]))
    conn.commit()
    res["alias_key_clashes"] = clashes
    return res


# ----------------------------------------------------------------------------- 5. buyer as winner

def winners(conn, *, apply: bool, out=print) -> dict[str, Any]:
    rows = [dict(r) for r in conn.execute(
        """SELECT a.id, a.organisation_id, a.name_as_stated, o.buyer_org_id, o.buyer_name_raw, o.native_id
             FROM award a JOIN opportunity o ON o.id = a.opportunity_id
            WHERE a.superseded_at IS NULL AND a.excluded_reason IS NULL""").fetchall()]
    # ponytail: up to three lookups per award (about 50,000 rows): minutes, not hours; a set query if it grows
    hit = [r for r in rows if same_name_as_buyer(r["name_as_stated"], r["buyer_name_raw"])
           or is_buyer_body(conn, r["buyer_org_id"], r["organisation_id"])]
    res = {"current_awards": len(rows), "buyer_as_winner": len(hit),
           "examples": [(r["native_id"], r["organisation_id"]) for r in hit[:10]]}
    out(f"awards whose winner is the notice's buyer: {res}")
    if not apply:
        conn.rollback()
        return res
    for r in hit:
        conn.execute("UPDATE award SET excluded_reason = 'buyer_as_winner' WHERE id = %s AND excluded_reason IS NULL",
                     (r["id"],))
        db.log_repair(conn, r["organisation_id"], "award_buyer_as_winner", old_value=str(r["id"]), new_value=None,
                      method="wp115_winners", detected_by=DETECTED_BY)
    conn.commit()
    return res


# ----------------------------------------------------------------------------- 4. unlinked organisations

def unlinked(conn, *, out=print, step: int = 20000) -> dict[str, Any]:
    top = conn.execute("SELECT coalesce(max(id), 0) AS m FROM organisation").fetchone()["m"]
    by: Counter[tuple] = Counter()
    ids: set[int] = set()
    for lo in range(0, top + 1, step):
        for r in conn.execute(
                """SELECT g.id, coalesce(g.org_role, '-') AS role, coalesce(g.review_status, '-') AS status,
                          (SELECT coalesce(s.code, '-') || ':' || a.match_method FROM organisation_alias a
                             LEFT JOIN source s ON s.id = a.source_id
                            WHERE a.organisation_id = g.id ORDER BY a.id LIMIT 1) AS first_alias,
                          g.is_defence_buyer AS flagged
                     FROM organisation g
                    WHERE g.id >= %s AND g.id < %s AND g.merged_into IS NULL
                      AND NOT EXISTS (SELECT 1 FROM opportunity o WHERE o.buyer_org_id = g.id)
                      AND NOT EXISTS (SELECT 1 FROM award a WHERE a.organisation_id = g.id)
                      AND NOT EXISTS (SELECT 1 FROM participation p WHERE p.organisation_id = g.id)""",
                (lo, lo + step)).fetchall():
            ids.add(r["id"])
            by[(r["first_alias"] or "no alias", r["role"], r["status"], r["flagged"])] += 1
    pend = conn.execute("SELECT organisation_id AS a, candidate_org_id AS b, match_method FROM "
                        "organisation_merge_candidate WHERE status = 'pending'").fetchall()
    involving = Counter(p["match_method"] for p in pend if p["a"] in ids or p["b"] in ids)
    both = Counter(p["match_method"] for p in pend if p["a"] in ids and p["b"] in ids)
    res = {"unlinked": len(ids), "pending_candidates": len(pend),
           "pending_with_an_unlinked_row": sum(involving.values()), "by_method": dict(involving),
           "pending_both_unlinked": sum(both.values()), "both_by_method": dict(both),
           "by_path": [(*k, n) for k, n in by.most_common(25)]}
    out(f"unlinked organisations: {res['unlinked']}; pending candidates {len(pend)}, of which "
        f"{res['pending_with_an_unlinked_row']} involve one {dict(involving)}, {res['pending_both_unlinked']} two "
        f"(skipped by ops.accept_merge_candidates) {dict(both)}")
    for k, n in by.most_common(25):
        out(f"  first alias {k[0]:<28} role {k[1]:<10} status {k[2]:<14} flagged {k[3]!s:<5} {n}")
    conn.rollback()
    return res


# ----------------------------------------------------------------------------- undo

def undo(conn, start: str, end: str, *, apply: bool, out=print) -> dict[str, Any]:
    """Reverse steps 1, 2 and 5 of [start, end): the rejoin merges (`ops.undo_merges`), then the logged values."""
    res: dict[str, Any] = {"merges": undo_merges.run(conn, apply=apply, start=start, end=end, methods=(REJOIN,),
                                                       expected=None, detected_by=DETECTED_BY, out=out)}
    logged = [dict(r) for r in conn.execute(
        """SELECT id, organisation_id, action, old_value, new_value FROM organisation_repair
            WHERE detected_by = %s AND created_at >= %s AND created_at < %s
              AND action IN ('clear_false_identifier', 'respell_identifier', 'repoint_merged_into',
                             'award_buyer_as_winner')
            ORDER BY id DESC""", (DETECTED_BY, start, end)).fetchall()]
    res["logged"] = dict(Counter(r["action"] for r in logged))
    out(f"undo {start} .. {end}: {res['logged']}")
    if not apply:
        conn.rollback()
        return res
    for r in logged:
        if r["action"] == "clear_false_identifier" and r["old_value"]:
            conn.execute("""UPDATE organisation SET national_reg_no = %s, identifier_method = 'identifier'
                             WHERE id = %s AND national_reg_no IS NULL""", (r["old_value"], r["organisation_id"]))
        elif r["action"] == "respell_identifier":
            conn.execute("UPDATE organisation SET national_reg_no = %s WHERE id = %s AND national_reg_no = %s",
                         (r["old_value"], r["organisation_id"], r["new_value"]))
        elif r["action"] == "repoint_merged_into":
            conn.execute("UPDATE organisation SET merged_into = %s WHERE id = %s AND merged_into = %s",
                         (int(r["old_value"]), r["organisation_id"], int(r["new_value"])))
        elif r["action"] == "award_buyer_as_winner":
            conn.execute("UPDATE award SET excluded_reason = NULL WHERE id = %s AND excluded_reason = 'buyer_as_winner'",
                         (int(r["old_value"]),))
    conn.commit()
    return res


def run(conn, steps: tuple[str, ...] = STEPS, *, apply: bool = False, out=print) -> dict[str, Any]:
    conn.execute("SET statement_timeout = '30s'")
    started = conn.execute("SELECT now() AS t").fetchone()["t"]
    conn.commit()
    res: dict[str, Any] = {}
    for name, fn in (("false-ids", false_ids), ("chains", chains), ("contacts", contacts), ("winners", winners)):
        if name in steps:
            res[name] = fn(conn, apply=apply, out=out)
    if "unlinked" in steps:
        res["unlinked"] = unlinked(conn, out=out)
    if apply and {"false-ids", "chains"} & set(steps):
        conn.execute("SET statement_timeout = 0")
        res["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
        conn.execute("SET statement_timeout = '30s'")
    if apply:
        ended = conn.execute("SELECT now() AS t").fetchone()["t"]
        conn.commit()
        out(f"to undo: python -m dgate.ops.org_repair --undo '{started.isoformat()}' '{ended.isoformat()}' [--yes]")
    else:
        out("dry run: nothing written (add --yes)")
    return res


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--step", action="append", choices=STEPS, help="run only this step (repeatable)")
    p.add_argument("--yes", action="store_true", help="write; without it nothing changes")
    p.add_argument("--undo", nargs=2, metavar=("FROM", "TO"), help="reverse this module's writes in [FROM, TO)")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        if a.undo:
            undo(conn, *a.undo, apply=a.yes)
        else:
            run(conn, tuple(a.step or STEPS), apply=a.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
