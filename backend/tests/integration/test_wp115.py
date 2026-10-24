"""WP-115 against a real Postgres: a case reference no longer becomes a registration number, the rows it split
rejoin their organisation (and the undo puts them back), merges never leave a chain, contact blocks leave names
and aliases, the buyer is not recorded as the winner of its own award, and the merge queue skips rows nothing
references."""

from __future__ import annotations

from collections import Counter
from datetime import date

import pytest

from dgate import awards, db
from dgate.normalise import Opportunity
from dgate.ops import accept_merge_candidates, org_repair

from .wp115_links import link

pytestmark = pytest.mark.integration

QUIET = {"out": lambda *_: None}


def _org(conn, name, country="PL", reg=None):
    return conn.execute(
        """INSERT INTO organisation (canonical_name, country, confidence, review_status, national_reg_no,
                                     identifier_method)
           VALUES (%s, %s, 0.95, 'auto', %s, %s) RETURNING id""",
        (name, country, reg, "identifier" if reg else None)).fetchone()["id"]


def _notice(conn, native_id, buyer_org, buyer_name="Szpital X", country="PL"):
    opp = Opportunity(source_code="ted", native_id=native_id, buyer_name_raw=buyer_name,
                      title_original=native_id, country=country, published_at=date(2026, 10, 1),
                      status="open", is_defence=True)
    opp.buyer_org_id = buyer_org
    oid, _ = db.upsert_opportunity(conn, opp, f"h-{native_id}", db.source_id(conn, "ted"))
    conn.commit()
    return oid


def _row(conn, oid):
    return conn.execute("SELECT * FROM organisation WHERE id = %s", (oid,)).fetchone()


def test_a_case_reference_does_not_split_the_buyer(conn):
    first = db.resolve_organisation(conn, "Szpital X", "PL", identifier="573-229-96-04")
    again = db.resolve_organisation(conn, "Szpital X", "PL", identifier="DEZ/26/019/2020")
    assert again == first and _row(conn, first)["national_reg_no"] == "5732299604"
    assert conn.execute("SELECT count(*) AS n FROM organisation").fetchone()["n"] == 1


def test_contact_block_is_not_stored_with_a_new_buyer(conn):
    oid = db.resolve_organisation(conn, "Stadt Y, Hauptstr. 1, 12345 Y, Tel. 0221 123456, E-Mail: a@b.de", "DE")
    assert _row(conn, oid)["canonical_name"] == "stadt y hauptstr 1 12345 y"
    raw = conn.execute("SELECT raw_name FROM organisation_alias WHERE organisation_id = %s", (oid,)).fetchone()
    assert raw["raw_name"] == "Stadt Y, Hauptstr. 1, 12345 Y"


def test_rows_split_by_false_numbers_rejoin_and_the_undo_restores_them(conn):
    real = _org(conn, "szpital x", reg="5732299604")
    split = [_org(conn, "szpital x", reg=r) for r in ("DEZ260192020", "WSZSDEZ260352021")]
    other = _org(conn, "szpital y", reg="123456785")           # untouched: a valid number
    lone = _org(conn, "szpital z", reg="ZP52018")              # no sibling: only the number goes
    es = _org(conn, "empresa", country="ES", reg="ESA28015865")
    _notice(conn, "1-2026", split[0])
    conn.commit()

    dry = org_repair.run(conn, ("false-ids",), **QUIET)["false-ids"]
    assert (dry["groups"], dry["numbers_cleared"], dry["rows_rejoined"], dry["respelt"]) == (2, 3, 2, 1)
    assert _row(conn, split[0])["merged_into"] is None          # a dry run writes nothing

    org_repair.run(conn, ("false-ids",), apply=True, **QUIET)
    for s in split:
        r = _row(conn, s)
        assert (r["merged_into"], r["merge_method"], float(r["merge_confidence"]), r["national_reg_no"]) == \
            (real, org_repair.REJOIN, 0.95, None)
    assert conn.execute("SELECT buyer_org_id FROM opportunity").fetchone()["buyer_org_id"] == real
    assert _row(conn, lone)["national_reg_no"] is None and _row(conn, lone)["merged_into"] is None
    assert _row(conn, other)["national_reg_no"] == "123456785"
    assert _row(conn, es)["national_reg_no"] == "A28015865"
    assert conn.execute("SELECT count(*) AS n FROM organisation").fetchone()["n"] == 6     # nothing deleted

    window = conn.execute("SELECT min(created_at) - interval '1 minute' AS a, now() + interval '1 minute' AS b "
                          "FROM organisation_repair").fetchone()
    org_repair.undo(conn, window["a"].isoformat(), window["b"].isoformat(), apply=True, **QUIET)
    assert [_row(conn, s)["national_reg_no"] for s in split] == ["DEZ260192020", "WSZSDEZ260352021"]
    assert all(_row(conn, s)["merged_into"] is None for s in split)
    assert _row(conn, es)["national_reg_no"] == "ESA28015865"
    assert conn.execute("SELECT buyer_org_id FROM opportunity").fetchone()["buyer_org_id"] == split[0]


def test_a_merge_never_leaves_a_chain_and_old_chains_are_flattened(conn):
    a, b, c = (_org(conn, n, "FR") for n in ("acme a", "acme b", "acme c"))
    db.merge_organisations(conn, b, a, method="test", confidence=0.99, evidence="t", detected_by="t")
    db.merge_organisations(conn, c, b, method="test", confidence=0.99, evidence="t", detected_by="t")
    assert _row(conn, a)["merged_into"] == c                    # re-pointed, and logged for the undo
    log = conn.execute("SELECT old_value, new_value FROM organisation_repair WHERE organisation_id = %s",
                       (a,)).fetchone()
    assert (log["old_value"], log["new_value"]) == (str(b), str(c))

    x, y, z = (_org(conn, n, "FR") for n in ("beta x", "beta y", "beta z"))
    conn.execute("UPDATE organisation SET merged_into = %s WHERE id = %s", (y, x))   # a chain made before
    conn.execute("UPDATE organisation SET merged_into = %s WHERE id = %s", (z, y))
    conn.commit()
    assert org_repair.chains(conn, apply=False, **QUIET)["rows_in_chains"] == 1
    org_repair.chains(conn, apply=True, **QUIET)
    assert _row(conn, x)["merged_into"] == z
    assert org_repair.chains(conn, apply=False, **QUIET)["rows_in_chains"] == 0


def test_contact_details_are_cleaned_from_stored_names_and_aliases(conn):
    oid = _org(conn, "amt w musterstr 1 12345 w tel 0221 123456 fax 0221 7", "DE")
    conn.execute("""INSERT INTO organisation_alias (organisation_id, raw_name, normalised_name, country_hint,
                                                    match_method, confidence)
                    VALUES (%s, 'Amt W, Tel: 0221 123456, E-Mail: x@y.de', 'amt w tel 0221 123456', 'DE',
                            'exact_name', 0.95)""", (oid,))
    conn.commit()
    lines: list[str] = []
    dry = org_repair.contacts(conn, apply=False, out=lines.append)
    assert (dry["organisation_names"], dry["aliases"], dry["alias_emails"]) == (1, 1, 1)
    assert not any("0221" in s or "x@y" in s for s in lines)      # counts only, never the values
    org_repair.contacts(conn, apply=True, **QUIET)
    assert _row(conn, oid)["canonical_name"] == "amt w musterstr 1 12345 w"
    al = conn.execute("SELECT raw_name, normalised_name FROM organisation_alias").fetchone()
    assert (al["raw_name"], al["normalised_name"]) == ("Amt W", "amt w")
    assert org_repair.contacts(conn, apply=False, **QUIET)["aliases"] == 0


def test_the_buyer_is_not_the_winner_of_its_own_award(conn):
    mod = db.resolve_organisation(conn, "Ministerie van Defensie", "NL")
    oid = _notice(conn, "624641-2025", mod, "Ministerie van Defensie", "NL")
    read = awards.Read(winners=[awards.Winner(name="Het Ministerie van Defensie", country="SE", identifier=None),
                                awards.Winner(name="Defensie Materieel BV", country="NL", identifier=None)], winners_seen=2)
    c: Counter = Counter()
    awards.store_notice(conn, db.source_id(conn, "ted"), {"id": oid, "cpv_codes": []}, read, None, c)
    conn.commit()
    names = [r["name_as_stated"] for r in conn.execute("SELECT name_as_stated FROM award").fetchall()]
    assert names == ["Defensie Materieel BV"] and c["skipped_buyer_as_winner"] == 1
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE country = 'SE'").fetchone()["n"] == 0

    # an award stored before the reader skipped it: marked, not deleted
    conn.execute("""INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated, winners_in_notice,
                                       resolution_method, resolution_confidence)
                    VALUES (%s, %s, 'NL', 'Ministerie van Defensie', 1, 'exact_name', 0.95)""", (oid, mod))
    conn.commit()
    assert org_repair.winners(conn, apply=False, **QUIET)["buyer_as_winner"] == 1
    org_repair.winners(conn, apply=True, **QUIET)
    assert conn.execute("SELECT excluded_reason FROM award WHERE organisation_id = %s",
                        (mod,)).fetchone()["excluded_reason"] == "buyer_as_winner"


def test_the_merge_queue_skips_rows_nothing_references(conn):
    a = _org(conn, "chantiers de l atlantique", "FR", reg="44440103600121")
    b = _org(conn, "chantiers de l atlantique s a", "FR")
    c = _org(conn, "naval works", "FR", reg="55540103600121")
    d = _org(conn, "naval works s a", "FR")
    for x, y in ((a, b), (c, d)):
        db.add_merge_candidate(conn, x, y, method="identifier", confidence=0.97, evidence="same SIRET",
                               detected_by="test")
    link(conn, a)                                  # b: only its partner is referenced; c and d: neither
    conn.commit()
    dry = accept_merge_candidates.run(conn, with_office_splits=False, **QUIET)
    assert dry["strong_candidates"] == 2 and dry["refused"] == {"unlinked": 1} and dry["rows_to_merge"] == 1
    rep = org_repair.unlinked(conn, **QUIET)
    assert (rep["unlinked"], rep["pending_with_an_unlinked_row"], rep["pending_both_unlinked"]) == (3, 2, 1)
