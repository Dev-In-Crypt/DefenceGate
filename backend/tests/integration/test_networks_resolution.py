"""The resolution cascade against a real Postgres: what each stage decides, and what it refuses."""

from __future__ import annotations

import pytest

from dgate.resolution import resolve
from dgate.resolution.trigram import similarity

pytestmark = pytest.mark.integration


def _org(conn, name: str, country: str, **cols) -> int:
    cols = {"canonical_name": name, "country": country, **cols}
    row = conn.execute(
        f"INSERT INTO organisation ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
        "RETURNING id", tuple(cols.values())).fetchone()
    conn.commit()
    return row["id"]


def _count(conn, table: str = "organisation") -> int:
    return conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]


def test_a_pic_beats_any_name(conn):
    first = resolve(conn, "Alpha Systems SA", "FR", {"pic": "123456789"})
    assert first.created and first.method == "pic" and first.confidence == 1.0
    again = resolve(conn, "Completely Other Name", "FR", {"pic": "123456789"})
    assert again.org_id == first.org_id and again.method == "pic" and not again.created
    assert _count(conn) == 1


def test_an_alias_decided_before_is_found_again_and_costs_no_row(conn):
    a = resolve(conn, "Indra Sistemas, S.A.", "ES")
    b = resolve(conn, "INDRA SISTEMAS SA", "ES")
    assert a.org_id == b.org_id and b.method in ("alias", "exact_name")
    assert _count(conn) == 1
    n = _count(conn, "organisation_alias")
    resolve(conn, "INDRA SISTEMAS SA", "ES")
    assert _count(conn, "organisation_alias") == n


def test_the_exact_name_within_a_country_attaches_the_pic_to_the_organisation_we_know(conn):
    oid = _org(conn, "ministerio de defensa", "ES")
    r = resolve(conn, "MINISTERIO DE DEFENSA", "ES", {"pic": "987654321"})
    assert r.org_id == oid and r.method == "exact_name" and r.confidence == 0.95
    row = conn.execute("SELECT eu_pic, pic_method, pic_confidence FROM organisation WHERE id = %s",
                       (oid,)).fetchone()
    assert row["eu_pic"] == "987654321" and row["pic_method"] == "exact_name"
    assert float(row["pic_confidence"]) == 0.95


def test_an_alias_without_a_country_never_carries_a_name_across_countries(conn):
    oid = _org(conn, "acme", "FR")
    conn.execute(
        "INSERT INTO organisation_alias (organisation_id, raw_name, normalised_name, country_hint, "
        "match_method, confidence) VALUES (%s, 'Acme', 'acme', NULL, 'exact_name', 0.95)", (oid,))
    conn.commit()
    r = resolve(conn, "Acme", "DE")
    assert r.org_id != oid and r.created


def test_the_same_name_in_two_countries_is_two_organisations(conn):
    a = resolve(conn, "Rheinmetall Defence", "DE")
    b = resolve(conn, "Rheinmetall Defence", "AT")
    assert a.org_id != b.org_id and _count(conn) == 2


def test_a_namesake_with_another_pic_is_a_new_organisation_and_waits_for_a_person(conn):
    a = resolve(conn, "University of Somewhere", "GB", {"pic": "111111111"})
    b = resolve(conn, "UNIVERSITY OF SOMEWHERE", "GB", {"pic": "222222222"})
    assert a.org_id != b.org_id and b.created
    review = conn.execute("SELECT org_a, org_b, method, status, evidence FROM resolution_review"
                          ).fetchall()
    assert len(review) == 1 and review[0]["method"] == "pic_conflict" and review[0]["status"] == "open"
    assert {review[0]["org_a"], review[0]["org_b"]} == {a.org_id, b.org_id}
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE merged_into IS NOT NULL"
                        ).fetchone()["n"] == 0


def test_two_organisations_with_one_name_resolve_to_the_better_known_and_are_queued(conn):
    plain = _org(conn, "kongsberg defence", "NO")
    known = _org(conn, "kongsberg defence", "NO", eu_pic="555555555")
    r = resolve(conn, "Kongsberg Defence AS", "NO")
    assert r.org_id == known and r.method == "exact_name_ambiguous" and r.confidence == 0.80
    review = conn.execute("SELECT org_a, org_b, method FROM resolution_review").fetchall()
    assert len(review) == 1 and review[0]["method"] == "exact_name_ambiguous"
    assert {review[0]["org_a"], review[0]["org_b"]} == {plain, known}


def test_a_cyrillic_and_a_latin_spelling_are_one_ukrainian_organisation(conn):
    a = resolve(conn, 'ТОВ "Укроборонпром"', "UA")
    b = resolve(conn, "Ukroboronprom LLC", "UA")
    assert a.org_id == b.org_id and _count(conn) == 1
    assert conn.execute("SELECT canonical_name FROM organisation").fetchone()["canonical_name"] \
        == "ukroboronprom"
    # both forms of the key are kept as aliases: the Latin one and the Cyrillic one the old lookups use
    aliases = {r["normalised_name"] for r in conn.execute("SELECT normalised_name FROM organisation_alias")}
    assert aliases == {"ukroboronprom", "тов укроборонпром"}


def test_an_organisation_stored_under_the_old_key_is_still_reached(conn):
    oid = _org(conn, "indra sistemas", "ES")
    assert resolve(conn, "INDRA SISTEMAS, S.A.", "ES").org_id == oid
    cyr = _org(conn, "укроборонпром", "UA")                 # a Cyrillic key stored before this layer
    assert resolve(conn, "Укроборонпром", "UA").org_id == cyr


def test_a_vat_number_is_trusted_only_against_a_name_that_shares_its_words(conn):
    oid = _org(conn, "siemens energy", "DE", vat_number="123456789")
    ok = resolve(conn, "Siemens Energy Global", "DE", {"vat": "DE 123 456 789"})
    assert ok.org_id == oid and ok.method == "vat"
    other = resolve(conn, "Quite Another Company", "DE", {"vat": "DE123456789"})
    assert other.org_id != oid and other.created


def test_a_registration_number_resolves_like_a_vat_number(conn):
    oid = _org(conn, "polska grupa zbrojeniowa", "PL", national_reg_no="5252500006")
    r = resolve(conn, "Polska Grupa Zbrojeniowa S.A.", "PL", {"reg": "PL5252500006"})
    assert r.org_id == oid and r.method == "national_id"


# ------------------------------------------------------------------ stage 3 never merges

def test_a_spelling_variant_becomes_a_candidate_pair_and_is_never_merged(conn):
    a = resolve(conn, "FRAUNHOFER GESELLSCHAFT ZUR FOERDERUNG DER ANGEWANDTEN FORSCHUNG EV", "DE",
                {"pic": "999980001"})
    b = resolve(conn, "FRAUNHOFER GESELLSCHAFT ZUR FORDERUNG DER ANGEWANDTEN FORSCHUNG EV", "DE",
                {"pic": "999980002"})
    assert a.org_id != b.org_id and b.created
    assert [c["org_id"] for c in b.candidates] == [a.org_id]
    row = conn.execute("SELECT method, proposed_relation, status, confidence FROM resolution_review"
                       ).fetchone()
    assert row["method"] == "trigram" and row["status"] == "open" and float(row["confidence"]) >= 0.85
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE merged_into IS NOT NULL"
                        ).fetchone()["n"] == 0


def test_parent_and_subsidiary_are_neither_merged_nor_queued(conn):
    parent = resolve(conn, "Thales SA", "FR")
    child = resolve(conn, "Thales Nederland B.V.", "NL")
    sibling = resolve(conn, "Thales Alenia Space France", "FR")
    assert len({parent.org_id, child.org_id, sibling.org_id}) == 3
    assert _count(conn, "resolution_review") == 0


def test_a_country_mismatch_is_a_hard_veto_even_for_a_near_identical_name(conn):
    resolve(conn, "Leonardo Helicopters Division", "IT")
    b = resolve(conn, "Leonardo Helicopters Divisions", "PL")
    assert b.created and b.candidates == [] and _count(conn, "resolution_review") == 0


def test_a_numbered_sibling_is_not_a_candidate(conn):
    resolve(conn, "Szkola Podstawowa nr 1 w Gdansku", "PL")
    b = resolve(conn, "Szkola Podstawowa nr 2 w Gdansku", "PL")
    assert b.created and b.candidates == [] and _count(conn, "resolution_review") == 0


def test_candidates_can_be_switched_off_for_a_bulk_load(conn):
    resolve(conn, "Fraunhofer Gesellschaft zur Foerderung der Angewandten Forschung", "DE")
    b = resolve(conn, "Fraunhofer Gesellschaft zur Forderung der Angewandten Forschung", "DE", None,
                {"candidates": False})
    assert b.created and _count(conn, "resolution_review") == 0


def test_the_review_pair_is_queued_once(conn):
    resolve(conn, "Fraunhofer Gesellschaft zur Foerderung der Angewandten Forschung", "DE")
    resolve(conn, "Fraunhofer Gesellschaft zur Forderung der Angewandten Forschung", "DE")
    resolve(conn, "FRAUNHOFER GESELLSCHAFT ZUR FORDERUNG DER ANGEWANDTEN FORSCHUNG", "DE")
    assert _count(conn, "resolution_review") == 1


def test_nothing_is_created_when_the_caller_only_wants_to_look(conn):
    r = resolve(conn, "Unknown Company", "FR", None, {"create": False})
    assert r.org_id is None and r.method == "none" and _count(conn) == 0


def test_a_name_without_a_country_or_with_nothing_but_a_legal_form_resolves_to_nothing(conn):
    assert resolve(conn, "Acme SA", None).org_id is None
    assert resolve(conn, "", "FR").org_id is None
    assert _count(conn) == 0


# ------------------------------------------------------------------ the database and Python agree

@pytest.mark.parametrize("a,b", [
    ("thales", "thales nederland"),
    ("fraunhofer gesellschaft zur forderung", "fraunhofer gesellschaft zur foerderung"),
    ("universidad politecnica de madrid", "universidad politecnica de valencia"),
    ("ukroboronprom", "ukroboronpro"),
    ("a b c", "abc"),
])
def test_the_python_similarity_is_the_one_postgres_computes(conn, a, b):
    db_value = float(conn.execute("SELECT similarity(%s, %s) AS s", (a, b)).fetchone()["s"])
    assert similarity(a, b) == pytest.approx(db_value, abs=1e-5)


def test_the_candidate_pass_over_organisations_already_held_is_resumable_and_merges_nothing(conn):
    from dgate import networks

    for name, pic in (("Fraunhofer Gesellschaft zur Foerderung der Angewandten Forschung", "999980001"),
                      ("Fraunhofer Gesellschaft zur Forderung der Angewandten Forschung", "999980002"),
                      ("Thales Nederland", "999980003")):
        resolve(conn, name, "DE" if "Fraun" in name else "NL", {"pic": pic}, {"candidates": False})
    assert _count(conn, "resolution_review") == 0
    first = networks.queue_candidates(conn, limit=2)
    assert first["processed"] == 2 and first["pairs"] == 1 and _count(conn, "resolution_review") == 1
    rest = networks.queue_candidates(conn, after_id=first["last_id"], limit=10)
    assert rest["processed"] == 1 and rest["pairs"] == 0
    again = networks.queue_candidates(conn, limit=10)                  # a second full pass adds nothing
    assert _count(conn, "resolution_review") == 1 and again["processed"] == 3
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE merged_into IS NOT NULL"
                        ).fetchone()["n"] == 0


def test_the_gold_set_loads_into_its_table_once_and_evaluates_the_same_from_there(conn):
    from dgate.resolution import evaluate

    pairs = evaluate.load_seed()
    assert evaluate.store_seed(conn, pairs) == len(pairs)
    assert evaluate.store_seed(conn, pairs) == len(pairs)                 # a second load adds nothing
    assert _count(conn, "resolution_gold") == len(pairs)
    held = evaluate.load_table(conn)
    assert evaluate.evaluate(held)["stages"]["exact_name"] == evaluate.evaluate(pairs)["stages"]["exact_name"]
    assert evaluate.evaluate(held)["ok"]

