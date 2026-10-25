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
  WP-119 (verification of 25 October 2026), the rules narrowed and the rows written that day repaired:
  winners-check  an award excluded as its buyer's that today's rules no longer exclude is counted again (TED
              109763-2024 SPIE FACILITIES, 841870-2025 DEF OUEST)
  namesakes   the rejoin groups under a name two public bodies bear (`ambiguous_name`: 'powiat tomaszowski', a unit's
              name without a place) are undone, exactly those rows (WP-129: not a row whose cleared value states its
              head's number)
  pics        what a rejoined row holds that its head lacks goes to the head (`db.carry_to_head`: PIC and VAT number;
              Universitat de Girona, URV, NCBR, IRB Barcelona); participations are read through the merge (WP-41)
  restore-ids the numbers cleared on 25 October that today's rules keep, from the log: Polish NIP+REGON pairs, a REGON
              without its leading zeros, a foreign VAT number on a company row
  held-ids    (WP-126) those numbers that another live row of the country holds: a merge candidate of the two rows
              (method `cleared_register_number`, 0.90, pending for a person); nothing merged, nothing logged here
              (the candidate row is the record). Run after restore-ids.
  twice      a live winner named twice on one notice: two companies a supplier merge joined are taken apart (Sign
              Polska / Sign 4 Security), spellings of one company counted once (`same_winner_twice`)
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
from datetime import timedelta
from typing import Any

from .. import db, networks
from ..awards import is_buyer_body, same_name_as_buyer
from ..buyer_family import is_public_body
from ..config import settings
from ..normalise import (
    normalise_identifier,
    normalise_org_name,
    pl_number_pair,
    pl_unpadded_regon,
    strip_name_contacts,
)
from ..supplier_identity import foreign_vat
from . import supplier_dedupe, undo_merges

log = logging.getLogger("org_repair")

DETECTED_BY = "ops.org_repair"
REJOIN = "false_identifier_rejoin"
CONF_REJOIN = db.CONF_EXACT_NAME
COUNTRIES = ("PL", "ES")
COMMIT_EVERY = 100
UNNAMED = "unnamed organisation"
STEPS = ("false-ids", "chains", "contacts", "winners", "winners-check", "namesakes", "pics", "restore-ids", "held-ids",
         "twice", "unlinked")


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


# WP-119: names two public bodies share, never joined by name alone. The Polish powiat names that two counties carry
# ('powiat tomaszowski': Tomaszow Mazowiecki and Tomaszow Lubelski, 36 rows joined on 25 October 2026), and a unit's
# name with no place in it ('miejskie przedsiebiorstwo oczyszczania', 'zaklad remontow i konserwacji drog'): every word
# of three letters or more is one of the words such units are named with. WP-129: and the municipal service companies
# ('miejski zaklad uslug komunalnych': Walbrzych's and at least three others; two rows joined by name on 25 October).
# ponytail: a vocabulary, not a register; a generic name with a word it lacks is still joined.
_PL_TWIN_POWIATS = frozenset(f"powiat {n}" for n in (
    "bielski", "brzeski", "grodziski", "krosnienski", "nowodworski", "opolski", "ostrowski", "sredzki", "swidnicki",
    "tomaszowski"))
_UNIT_WORDS = frozenset("""
    powiat powiatu powiatowy powiatowe powiatowa powiatowego powiatowej powiatowych gmina gminy gminny gminne gminna
    gminnego gminnej miasto miasta miejski miejskie miejska miejskiego miejskiej miejskich zaklad zakladu zaklady zarzad
    zarzadu osrodek osrodka przedsiebiorstwo przedsiebiorstwa centrum zespol zespolu szkol szkola szkoly przedszkole
    publiczne publiczny publiczna publicznej publicznego samodzielny samodzielne samodzielna pomocy spolecznej kultury
    sportu rekreacji oczyszczania remontow konserwacji drog drogowy drogowe drogowych dokumentacji geodezyjnej
    kartograficznej zdrowia restrukturyzacji opieki zdrowotnej gospodarki komunalnej komunalne komunalny komunalnego
    mieszkaniowej mieszkaniowa wodociagow kanalizacji wodociagi energetyki cieplnej transportu komunikacji inwestycji
    nieruchomosci nieruchomosciami gospodarowania urzad urzedu starostwo biblioteka przychodnia straz pozarna
    komenda policji administracji obslugi jednostek oswiatowych oswiaty edukacji spolka spoldzielnia wydzial biuro
    zieleni utrzymania domu dom
    uslug komunalnych komunalna
    junta gobierno local alcaldia presidencia pleno ayuntamiento organo contratacion mesa servicio servicios departamento
    direccion general gerencia consejeria secretaria unidad seccion comision consejo administracion municipal
    """.split())


def ambiguous_name(country: str, name: str) -> bool:
    """WP-119: a name more than one public body bears (`_PL_TWIN_POWIATS`, or a unit's name with no place)."""
    n = (name or "").lower()
    if country == "PL" and n in _PL_TWIN_POWIATS:
        return True
    words = {w for w in re.split(r"[\s\-]+", n) if len(w) >= 3} - {"del", "los", "las"}     # Sax, Ibi and Ełk are places
    return bool(words) and words <= _UNIT_WORDS


# ----------------------------------------------------------------------------- 1. false identifiers

def register_form(number: str | None, country: str) -> str | None:
    """A number in its register's form (`normalise_identifier`), or (WP-119) a Polish REGON written without its leading
    zeros in its 9-digit form (`pl_unpadded_regon`); None when it is neither."""
    n = normalise_identifier(number, country)
    if n is None and country == "PL":
        n = pl_unpadded_regon((number or "").strip())
    return n


def vat_of(row: dict[str, Any]) -> str | None:
    """WP-119: the foreign VAT number a company row (not a public body) holds as its registration number, or None."""
    v = foreign_vat(row["national_reg_no"], row["country"])
    return (v if v and not row.get("individual_reason") and not is_public_body(row["canonical_name"], row["country"])
            else None)


def plan_false_ids(rows: list[dict[str, Any]], siblings: dict[tuple[str, str], list[dict[str, Any]]]
                   ) -> tuple[list[dict[str, Any]], list[tuple[int, str, str]]]:
    """The groups (one per country and name holding a false number) and the re-spellings (id, old, new).

    `rows` are live rows with a number; `siblings` the live rows of each (country, lower name).
    WP-119: a Polish NIP and REGON written together is re-spelt to the NIP, a REGON without its leading zeros to its
    9-digit form (`register_form`); a foreign VAT number on a company row moves to `vat_number` (the group's "vat",
    not cleared as false, not merged); and a group whose name more than one public body bears (`ambiguous_name`) is never merged."""
    respell: list[tuple[int, str, str]] = []
    false_keys: set[tuple[str, str]] = set()
    for r in rows:
        n = register_form(r["national_reg_no"], r["country"])
        if n is None:
            false_keys.add((r["country"], r["canonical_name"].lower()))
        elif n != r["national_reg_no"]:
            respell.append((r["id"], r["national_reg_no"], n))
    groups = []
    for key in sorted(false_keys):
        members = sorted(siblings.get(key, []), key=lambda m: m["id"])
        vat = [m for m in members if m["national_reg_no"] and register_form(m["national_reg_no"], m["country"]) is None
               and vat_of(m)]
        bad = [m for m in members if m["national_reg_no"] and m not in vat
               and register_form(m["national_reg_no"], m["country"]) is None]
        valid = {register_form(m["national_reg_no"], m["country"]) for m in members
                 if m["national_reg_no"]} - {None}
        g = {"country": key[0], "name": key[1], "first": members[0]["id"] if members else None,
             "rows": len(members), "clear": [m["id"] for m in bad], "vat": [(m["id"], vat_of(m)) for m in vat],
             "shapes": Counter(_shape(m["national_reg_no"]) for m in bad), "target": None, "merge": []}
        # two numbers of one register are two bodies; a NIP beside a REGON (a 340-row hospital holds both) is not
        kinds = Counter(_kind(key[0], v) for v in valid)
        if any(n > 1 for n in kinds.values()):
            g["decision"] = "held_two_numbers"
        elif ambiguous_name(key[0], key[1]):
            g["decision"] = "namesake"
        else:
            target = (next((m for m in members if m["national_reg_no"] and m["id"] not in g["clear"]
                            and m not in vat), None)
                      or next((m for m in members if not m["national_reg_no"]), None)
                      or members[0])
            g["target"] = target["id"]
            g["merge"] = [m["id"] for m in bad if m["id"] != target["id"]]
            g["decision"] = "rejoin" if g["merge"] else "clear_only" if bad else "vat_only"
        groups.append(g)
    return groups, respell


def false_ids(conn, *, apply: bool, out=print) -> dict[str, Any]:
    rows = [dict(r) for r in conn.execute(
        """SELECT id, country, canonical_name, national_reg_no, individual_reason FROM organisation
            WHERE merged_into IS NULL AND country = ANY(%s) AND national_reg_no IS NOT NULL""",
        (list(COUNTRIES),)).fetchall()]
    keys: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if register_form(r["national_reg_no"], r["country"]) is None:
            keys[r["country"]].add(r["canonical_name"].lower())
    siblings: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for country, names in keys.items():
        names_l = sorted(names)
        for i in range(0, len(names_l), 1000):
            for m in conn.execute(
                    """SELECT id, country, canonical_name, national_reg_no, individual_reason FROM organisation
                        WHERE country = %s AND lower(canonical_name) = ANY(%s) AND merged_into IS NULL""",
                    (country, names_l[i:i + 1000])).fetchall():
                siblings[(country, m["canonical_name"].lower())].append(dict(m))
    groups, respell = plan_false_ids(rows, siblings)
    by_decision = Counter(g["decision"] for g in groups)
    res = {"rows_with_number": len(rows), "groups": len(groups), "by_decision": dict(by_decision),
           "numbers_cleared": sum(len(g["clear"]) for g in groups),
           "rows_rejoined": sum(len(g["merge"]) for g in groups), "respelt": len(respell),
           "to_vat_number": sum(len(g["vat"]) for g in groups),
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
        for oid, vat in g["vat"]:
            old = by_id[oid]["national_reg_no"]
            conn.execute("""UPDATE organisation SET vat_number = COALESCE(vat_number, %s), national_reg_no = NULL,
                                   identifier_method = NULL, identifier_confidence = NULL
                             WHERE id = %s AND national_reg_no = %s""", (vat, oid, old))
            db.log_repair(conn, oid, "move_to_vat_number", old_value=old, new_value=vat,
                          method="wp119_foreign_vat", detected_by=DETECTED_BY)
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


# ----------------------------------------------------------------------------- WP-119 repairs of the 25 October writes

def winners_check(conn, *, apply: bool, out=print) -> dict[str, Any]:
    """WP-119: an award excluded as its buyer's that today's rules no longer exclude (`same_name_as_buyer` needs more
    than one shared word; a twin-notice buyer family no longer counts) is counted again; logged for the undo."""
    rows = [dict(r) for r in conn.execute(
        """SELECT a.id, a.organisation_id, a.name_as_stated, o.buyer_org_id, o.buyer_name_raw, o.native_id
             FROM award a JOIN opportunity o ON o.id = a.opportunity_id
            WHERE a.excluded_reason = 'buyer_as_winner' ORDER BY a.id""").fetchall()]
    lift = [r for r in rows if not same_name_as_buyer(r["name_as_stated"], r["buyer_name_raw"])
            and not is_buyer_body(conn, r["buyer_org_id"], r["organisation_id"])]
    res = {"excluded_as_buyer": len(rows), "counted_again": len(lift),
           "awards": [(r["id"], r["native_id"]) for r in lift]}
    out(f"awards excluded as the buyer's, checked again: {res}")
    if not apply:
        conn.rollback()
        return res
    for r in lift:
        conn.execute("UPDATE award SET excluded_reason = NULL WHERE id = %s AND excluded_reason = 'buyer_as_winner'",
                     (r["id"],))
        db.log_repair(conn, r["organisation_id"], "award_buyer_as_winner_lifted", old_value=str(r["id"]),
                      new_value=None, method="wp119_winners", detected_by=DETECTED_BY)
    conn.commit()
    return res


def agrees(cleared: str | None, country: str, numbers: tuple[str | None, ...]) -> bool:
    """WP-129: the cleared value, or a part of it (`register_form`, either half of a Polish NIP+REGON pair), is one of
    `numbers` (in their register's form)."""
    if not cleared:
        return False
    held = {register_form(n, country) or n for n in numbers if n}
    parts = {cleared, register_form(cleared, country)}
    if country == "PL":
        parts |= set(pl_number_pair(cleared) or ())
    return bool(parts & held)


def namesakes(conn, *, apply: bool, out=print) -> dict[str, Any]:
    """WP-119: the rejoin groups whose name more than one public body bears (`ambiguous_name`) are undone, exactly
    those rows (`ops.undo_merges` with `only`); the false numbers stay cleared. Every group is listed.
    WP-129: a row whose cleared value states a number its head holds (the NIP of a NIP+REGON pair: 'miejski zarzad
    uslug komunalnych') was joined by that number, not by the name alone, and stays (`agrees`)."""
    rows = [dict(r) for r in conn.execute(
        """SELECT m.id, m.merged_into AS head, m.merged_at, t.country, t.canonical_name, t.national_reg_no, t.vat_number,
                  (SELECT r.old_value FROM organisation_repair r WHERE r.organisation_id = m.id
                      AND r.action = 'clear_false_identifier' ORDER BY r.id DESC LIMIT 1) AS cleared
             FROM organisation m JOIN organisation t ON t.id = m.merged_into
            WHERE m.merge_method = %s ORDER BY m.id""", (REJOIN,)).fetchall()]
    named = [r for r in rows if ambiguous_name(r["country"], r["canonical_name"])]
    hit = [r for r in named if not agrees(r["cleared"], r["country"], (r["national_reg_no"], r["vat_number"]))]
    groups = Counter((r["head"], r["country"], r["canonical_name"]) for r in hit)
    res: dict[str, Any] = {"rejoined_rows": len(rows), "groups": len(groups), "rows": len(hit),
                           "kept_number_agrees": len(named) - len(hit)}
    out(f"rejoin groups under a name two public bodies bear: {res['groups']} groups, {res['rows']} rows "
        f"({res['kept_number_agrees']} rows stay: their cleared value states their head's number)")
    for (head, country, name), n in groups.most_common():
        out(f"  {country} head {head} {name[:70]!r}: {n} rows")
    if not hit:
        conn.rollback()
        return res
    times = [r["merged_at"] for r in hit]
    res["undo"] = undo_merges.run(conn, apply=apply, start=min(times).isoformat(),
                                  end=(max(times) + timedelta(seconds=1)).isoformat(), methods=(REJOIN,),
                                  expected=None, detected_by=DETECTED_BY, out=out, only=[r["id"] for r in hit],
                                  refresh=False)
    return res


def pics(conn, *, apply: bool, out=print) -> dict[str, Any]:
    """WP-119: what a rejoined row held that its head lacks goes to the head (`db.carry_to_head`: the EU PIC, the VAT
    number; an award twice on one notice counted once), as every merge does from now on. The participations stay on
    the rejoined row and are read through the merge (WP-41); the report counts them."""
    rows = [dict(r) for r in conn.execute(
        """SELECT m.id, m.merged_into AS head FROM organisation m
            WHERE m.merge_method = %s AND (m.eu_pic IS NOT NULL OR m.vat_number IS NOT NULL
                  OR EXISTS (SELECT 1 FROM participation p WHERE p.organisation_id = m.id)
                  OR EXISTS (SELECT 1 FROM award a WHERE a.organisation_id = m.id))
            ORDER BY m.id""", (REJOIN,)).fetchall()]
    moved: Counter = Counter()
    heads: set[int] = set()
    for r in rows:
        k, a = (conn.execute("SELECT id, eu_pic, pic_method, pic_confidence, vat_number FROM organisation "
                             "WHERE id = %s", (x,)).fetchone() for x in (r["head"], r["id"]))
        got = db.carry_to_head(conn, k, a, False, REJOIN)
        moved.update(got)
        if any(got.values()):
            heads.add(r["head"])
    parts = conn.execute("""SELECT count(*) AS n FROM participation p JOIN organisation m ON m.id = p.organisation_id
                                 WHERE m.merge_method = %s""", (REJOIN,)).fetchone()["n"]
    res = {"rejoined_rows_holding_something": len(rows), "heads": len(heads), **moved,
           "participations_read_through_the_merge": parts}
    out(f"rejoined rows: what their heads lacked: {res}")
    if apply:
        conn.commit()
    else:
        conn.rollback()
    return res


_CLEARED = """SELECT r.organisation_id AS id, r.old_value, g.country, g.canonical_name, g.merged_into, g.individual_reason
                FROM organisation_repair r JOIN organisation g ON g.id = r.organisation_id
               WHERE r.action = 'clear_false_identifier' AND r.old_value IS NOT NULL
               ORDER BY r.id"""


def _kept_number(r: dict[str, Any]) -> tuple[str | None, str, str | None]:
    """(kind, column, number) today's rules keep of a cleared value `r['old_value']` (WP-119), or (None, _, None)."""
    old, country = r["old_value"], r["country"]
    pair = pl_number_pair(old) if country == "PL" else None
    number = pair[0] if pair else (pl_unpadded_regon(old) if country == "PL" else None)
    if number:
        return ("nip_regon_pair" if pair else "unpadded_regon"), "national_reg_no", number
    vat = vat_of({**r, "national_reg_no": old})
    return ("foreign_vat", "vat_number", vat) if vat else (None, "national_reg_no", None)


# WP-126: a cleared number today's rules keep that another live row of the country holds says the two rows may be one
# body under two spellings ("gmina kolbiel" twice, "amw sinevia" / "amw sinevia spolka z ograniczona odpowiedzialnoscia")
# or units of one (a forest district and Lasy Panstwowe, a faculty and its university: a public body files its units
# under one number, which `ops.accept_merge_candidates` never merges). Below the 0.97 of `identifier`, so no tool accepts
# it by itself: a person decides.
HELD_ID = "cleared_register_number"
CONF_HELD_ID = 0.90


def held_ids(conn, *, apply: bool, out=print) -> dict[str, Any]:
    """WP-126: the cleared register numbers `restore_ids` cannot restore because another live row of the country holds
    them (WP-119: 64 NIP+REGON pairs, 8 short REGONs) become merge candidates of the two live rows (method HELD_ID,
    CONF_HELD_ID, the evidence names the kind, both rows and their names, never the number); nothing is merged. A pair
    already a candidate of this method is left as it is; one of another method gets this row too."""
    rows = [dict(r) for r in conn.execute(_CLEARED).fetchall()]
    c: Counter = Counter()
    pairs: dict[tuple[int, int], tuple[str, int, int]] = {}      # (a, b) -> (kind, cleared row, holder live row)
    for r in rows:
        kind, column, number = _kept_number(r)
        if number is None or column != "national_reg_no":
            continue
        if r["individual_reason"]:
            c[f"{kind}_skipped_person"] += 1
            continue
        live = r["merged_into"] or r["id"]
        holders = {h["live"] for h in conn.execute(
            """SELECT DISTINCT COALESCE(merged_into, id) AS live FROM organisation
                WHERE country = %s AND national_reg_no = %s""", (r["country"], number)).fetchall()}
        if not holders - {live}:
            c[f"{kind}_{'on_the_live_row' if holders else 'held_by_none'}"] += 1
            continue
        c[f"{kind}_held_by_another_row"] += 1
        for h in sorted(holders - {live}):
            pairs.setdefault((min(live, h), max(live, h)), (kind, r["id"], h))
    names = {x["id"]: x["canonical_name"] for x in conn.execute(
        "SELECT id, canonical_name FROM organisation WHERE id = ANY(%s)",
        ([i for p in pairs for i in p],)).fetchall()}
    held = {(x["organisation_id"], x["candidate_org_id"]) for x in conn.execute(
        """SELECT organisation_id, candidate_org_id FROM organisation_merge_candidate
            WHERE match_method = %s""", (HELD_ID,)).fetchall()}
    new = [p for p in pairs if p not in held]
    res = {"logged_values": len(rows), **c, "candidate_pairs": len(pairs), "candidate_pairs_new": len(new)}
    out(f"cleared numbers another live row holds: {res}")
    for a, b in list(pairs)[:20]:
        out(f"  {pairs[(a, b)][0]}: {a} {names.get(a, '')[:50]!r} ~ {b} {names.get(b, '')[:50]!r}")
    if not apply:
        conn.rollback()
        return res
    for a, b in new:
        kind, cleared, holder = pairs[(a, b)]
        db.add_merge_candidate(
            conn, a, b, method=HELD_ID, confidence=CONF_HELD_ID, detected_by=DETECTED_BY,
            evidence=(f"{kind}: the number cleared from row {cleared} on 25 Oct 2026 (organisation_repair) is held by "
                      f"row {holder}; names {names.get(a, a)!r} and {names.get(b, b)!r}"))
    conn.commit()
    return res


def restore_ids(conn, *, apply: bool, out=print) -> dict[str, Any]:
    """WP-119: the numbers the false-ids step of 25 October cleared that today's rules keep, from its log
    (`old_value`): a Polish NIP and REGON written together (the NIP), a REGON written without its leading zeros (its
    9-digit form) and a foreign VAT number on a company row (as `vat_number`). Each goes to the live row when it holds
    none, else back to its own row when that holds none; never when another row of the country holds it."""
    rows = [dict(r) for r in conn.execute(_CLEARED).fetchall()]
    c: Counter = Counter()
    plan: list[tuple[int, str, str, str]] = []       # (target, column, value, kind)
    planned: set[str] = set()
    for r in rows:
        kind, column, number = _kept_number(r)
        country = r["country"]
        if number is None:
            continue
        c[kind] += 1
        live = r["merged_into"] or r["id"]
        own = {x["id"]: x[column] for x in conn.execute(
            f"SELECT id, {column} FROM organisation WHERE id = ANY(%s)", ([live, r["id"]],)).fetchall()}
        if number in own.values():
            c[f"{kind}_already_there"] += 1
            continue
        if column == "national_reg_no" and (number in planned or conn.execute(
                "SELECT 1 FROM organisation WHERE country = %s AND national_reg_no = %s", (country, number)).fetchone()):
            c[f"{kind}_held_by_another_row"] += 1         # the register number is unique per country
            continue
        target = next((x for x in dict.fromkeys((live, r["id"])) if own.get(x) is None), None)
        if target is None:
            c[f"{kind}_rows_hold_another"] += 1
            continue
        planned.add(number)
        c[f"{kind}_restored"] += 1
        c[f"{kind}_restored_on_{'live' if target == live else 'own'}_row"] += 1
        plan.append((target, column, number, kind))
    res = {"logged_values": len(rows), **c}
    out(f"cleared numbers today's rules keep: {res}")
    if not apply:
        conn.rollback()
        return res
    for target, column, number, kind in plan:
        extra = ", identifier_method = 'identifier'" if column == "national_reg_no" else ""
        if conn.execute(f"UPDATE organisation SET {column} = %s{extra} WHERE id = %s AND {column} IS NULL",
                        (number, target)).rowcount:
            db.log_repair(conn, target, "restore_identifier" if column == "national_reg_no" else "restore_vat_number",
                          old_value=None, new_value=number, method=f"wp119_{kind}", detected_by=DETECTED_BY)
    conn.commit()
    return res


def twice(conn, *, apply: bool, out=print) -> dict[str, Any]:
    """WP-119: one notice whose current awards name one live company twice. Two rows the supplier merge joined although
    the notice names them side by side under two names (`supplier_dedupe.spelling_variants`, a person's review aside:
    Sign Polska / Sign 4 Security) are taken apart (`ops.undo_merges` for that row); spellings of one company (Works 11,
    Vogtmann-Herold, Norrenbrock, Magtel) are one award: the row on the live row itself stays (else the lowest id), the
    others get `excluded_reason = 'same_winner_twice'`, logged for the undo."""
    rows = [dict(r) for r in conn.execute(
        """WITH d AS (SELECT a.opportunity_id, COALESCE(g.merged_into, g.id) AS live
                        FROM award a JOIN organisation g ON g.id = a.organisation_id
                       WHERE a.superseded_at IS NULL AND a.excluded_reason IS NULL
                       GROUP BY 1, 2 HAVING count(*) > 1)
           SELECT a.id, a.opportunity_id, a.organisation_id, a.name_as_stated, g.merge_method, g.merged_at, d.live
             FROM d JOIN award a ON a.opportunity_id = d.opportunity_id
             JOIN organisation g ON g.id = a.organisation_id AND COALESCE(g.merged_into, g.id) = d.live
            WHERE a.superseded_at IS NULL AND a.excluded_reason IS NULL
            ORDER BY a.opportunity_id, a.id""").fetchall()]
    by: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[(r["opportunity_id"], r["live"])].append(r)
    apart: dict[int, dict[str, Any]] = {}
    exclude: list[dict[str, Any]] = []
    for (_, live), rs in by.items():
        head = next((r for r in rs if r["organisation_id"] == live), rs[0])
        others = [r for r in rs if r is not head]
        wrong = [r for r in others if r["organisation_id"] != head["organisation_id"]
                 and r["merge_method"] in supplier_dedupe.METHODS and r["merge_method"] != supplier_dedupe.CURATED_REVIEW
                 and not supplier_dedupe.spelling_variants(r["name_as_stated"], head["name_as_stated"])]
        for r in wrong:
            apart[r["organisation_id"]] = r
        exclude += [r for r in others if r not in wrong and r["organisation_id"] not in apart]
    res: dict[str, Any] = {"notices": len(by), "rows_taken_apart": sorted(apart),
                           "awards_counted_once": [r["id"] for r in exclude]}
    out(f"notices naming one live winner twice: {res}")
    if apart:
        times = [r["merged_at"] for r in apart.values()]
        res["undo"] = undo_merges.run(conn, apply=apply, start=min(times).isoformat(),
                                      end=(max(times) + timedelta(seconds=1)).isoformat(),
                                      methods=tuple(supplier_dedupe.METHODS), expected=None,
                                      detected_by=supplier_dedupe.DETECTED_BY, out=out, only=sorted(apart),
                                      refresh=False)
    if not apply:
        conn.rollback()
        return res
    for r in exclude:
        if conn.execute("UPDATE award SET excluded_reason = %s WHERE id = %s AND excluded_reason IS NULL",
                        (db.SAME_WINNER_TWICE, r["id"])).rowcount:
            db.log_repair(conn, r["organisation_id"], "award_same_winner_twice", old_value=str(r["id"]),
                          new_value=None, method="wp119_twice", detected_by=DETECTED_BY)
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
    """Reverse steps 1, 2 and 5 of [start, end): the rejoin merges (`ops.undo_merges`), then the logged values.
    WP-119: and the WP-119 steps' writes: the numbers restored or moved to `vat_number`, the awards counted again or
    counted once, and what `pics` moved to a head whose row stays merged. The rows `namesakes` and `twice` took apart
    stay apart (their merges were wrong)."""
    res: dict[str, Any] = {"merges": undo_merges.run(conn, apply=apply, start=start, end=end, methods=(REJOIN,),
                                                       expected=None, detected_by=DETECTED_BY, out=out)}
    logged = [dict(r) for r in conn.execute(
        """SELECT id, organisation_id, action, old_value, new_value FROM organisation_repair
            WHERE detected_by = %s AND created_at >= %s AND created_at < %s
              AND action IN ('clear_false_identifier', 'respell_identifier', 'repoint_merged_into',
                             'award_buyer_as_winner', 'move_to_vat_number', 'restore_identifier',
                             'restore_vat_number', 'award_buyer_as_winner_lifted', 'award_same_winner_twice')
            ORDER BY id DESC""", (DETECTED_BY, start, end)).fetchall()]
    moves = [dict(r) for r in conn.execute(
        """SELECT DISTINCT ON (r.organisation_id, r.action) r.organisation_id AS member, r.action, r.old_value,
                  r.new_value::bigint AS head
             FROM organisation_repair r JOIN organisation g ON g.id = r.organisation_id
            WHERE r.detected_by = 'db.merge_organisations' AND r.method = %s AND r.action = ANY(%s)
              AND r.created_at >= %s AND r.created_at < %s AND g.merged_into::text = r.new_value
            ORDER BY r.organisation_id, r.action, r.id DESC""",
        (REJOIN, list(db.MERGE_MOVES), start, end)).fetchall()]
    res["logged"] = dict(Counter(r["action"] for r in logged))
    res["moved_back"] = len(moves)
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
        elif r["action"] == "move_to_vat_number":
            conn.execute("""UPDATE organisation SET national_reg_no = %s, identifier_method = 'identifier',
                                   vat_number = NULLIF(vat_number, %s)
                             WHERE id = %s AND national_reg_no IS NULL""",
                         (r["old_value"], r["new_value"], r["organisation_id"]))
        elif r["action"] == "restore_identifier":
            conn.execute("UPDATE organisation SET national_reg_no = NULL WHERE id = %s AND national_reg_no = %s",
                         (r["organisation_id"], r["new_value"]))
        elif r["action"] == "restore_vat_number":
            conn.execute("UPDATE organisation SET vat_number = NULL WHERE id = %s AND vat_number = %s",
                         (r["organisation_id"], r["new_value"]))
        elif r["action"] == "award_buyer_as_winner_lifted":
            conn.execute("UPDATE award SET excluded_reason = 'buyer_as_winner' WHERE id = %s AND excluded_reason IS NULL",
                         (int(r["old_value"]),))
        elif r["action"] == "award_same_winner_twice":
            conn.execute("UPDATE award SET excluded_reason = NULL WHERE id = %s AND excluded_reason = %s",
                         (int(r["old_value"]), db.SAME_WINNER_TWICE))
    undo_merges.move_back(conn, moves)
    conn.commit()
    return res


def run(conn, steps: tuple[str, ...] = STEPS, *, apply: bool = False, out=print) -> dict[str, Any]:
    conn.execute("SET statement_timeout = '30s'")
    started = conn.execute("SELECT now() AS t").fetchone()["t"]
    conn.commit()
    res: dict[str, Any] = {}
    for name, fn in (("false-ids", false_ids), ("chains", chains), ("contacts", contacts), ("winners", winners),
                     ("winners-check", winners_check), ("namesakes", namesakes), ("pics", pics),
                     ("restore-ids", restore_ids), ("held-ids", held_ids), ("twice", twice)):
        if name in steps:
            res[name] = fn(conn, apply=apply, out=out)
    if "unlinked" in steps:
        res["unlinked"] = unlinked(conn, out=out)
    if apply and {"false-ids", "chains", "namesakes", "pics", "twice"} & set(steps):
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
