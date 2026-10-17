"""Names, trigrams and the gold evaluation of the networks layer (WP-26). No database."""

from __future__ import annotations

import json

import pytest

from dgate.normalise import normalise_org_name
from dgate.resolution import evaluate, key_of
from dgate.resolution.names import transliterate
from dgate.resolution.trigram import is_candidate, similarity, trigrams


def test_a_ukrainian_name_and_its_english_spelling_collapse_to_one_key():
    # the example of plan M2-07
    assert key_of('ТОВ "Укроборонпром"')[0] == key_of("Ukroboronprom LLC")[0] == "ukroboronprom"


@pytest.mark.parametrize("raw,expected", [
    ("ПрАТ «Мотор Січ»", "motor sich"),
    ("Фермер ФОП", "fermer"),
    ("Aerotech S.R.L.", "aerotech"),
    ("Aerotech SRL", "aerotech"),
    ("Optomech spol. s r.o.", "optomech"),
    ("Optomech s.r.o.", "optomech"),
    ("Optomech, a.s.", "optomech"),
    ("SIA Frankenburg Technologies", "frankenburg technologies"),
    ("FRANKENBURG TECHNOLOGIES OÜ", "frankenburg technologies"),
    ("Krattworks OU", "krattworks"),
    ("AKTYVUS PHOTONICS UAB", "aktyvus photonics"),
    ("Tallinna Kaubamaja AS", "tallinna kaubamaja"),
])
def test_the_legal_forms_of_ukraine_romania_czechia_and_the_baltics_are_dropped(raw, expected):
    assert key_of(raw)[0] == expected


@pytest.mark.parametrize("a,b", [
    ("ROBERT KOCH- INSTITUT", "ROBERT KOCH-INSTITUT"),
    ("STICHTING KONINKLIJK NEDERLANDS LUCHT- EN RUIMTEVAARTCENTRUM",
     "STICHTING KONINKLIJK NEDERLANDS LUCHT - EN RUIMTEVAARTCENTRUM"),
    ("MANAGING&INNOVATION BUSINESS PARTNERS", "MANAGING & INNOVATION BUSINESS PARTNERS SL"),
    ("GRAPHENE XT", "GRAPHENE-XT SRL"),
    ("THALES NEDERLAND B.V", "THALES NEDERLAND BV"),
    ("Osrodek Badawczo- Rozwojowy Centrum Techniki Morskiej S.A.",
     "OSRODEK BADAWCZO-ROZWOJOWY CENTRUM TECHNIKI MORSKIEJ SPOLKA AKCYJNA"),
    ("GMV AEROSPACE AND DEFENCE S.A.U.", "GMV AEROSPACE AND DEFENCE S.A."),
])
def test_spacing_around_hyphens_and_ampersands_and_dotless_legal_forms_do_not_make_two_names(a, b):
    # each pair is one real pair of spellings from the EDF factsheets and CORDIS (17 October 2026)
    assert key_of(a)[0] == key_of(b)[0]


def test_a_legal_form_inside_a_name_is_a_word_and_stays():
    assert key_of("Bank Mb Holdings Group")[0] == normalise_org_name("Bank Mb Holdings Group")
    assert key_of("Mb Bank")[0] == "bank"        # at the start it is the form


def test_a_latin_name_keeps_the_key_the_buyer_side_already_stored():
    # changing the key of a stored name would orphan its aliases: for plain Latin names the two agree
    for raw in ("Indra Sistemas, S.A.", "Thales Nederland B.V.", "Leonardo S.p.A.",
                "Hensoldt Sensors GmbH"):
        assert key_of(raw) == (normalise_org_name(raw),) * 2


def test_the_legacy_key_of_a_cyrillic_name_is_still_cyrillic():
    new, legacy = key_of("Укроборонпром")
    assert new == "ukroboronprom" and legacy == "укроборонпром"


def test_transliteration_leaves_latin_letters_alone():
    assert transliterate("Щука & Co") == "Shchuka & Co"


def test_parent_and_subsidiary_do_not_share_a_key_and_are_not_candidates():
    a, b = key_of("Thales SA")[0], key_of("Thales Nederland B.V.")[0]
    assert a != b
    assert is_candidate(a, "FR", b, "NL") is None          # a country mismatch is a hard veto
    assert is_candidate(a, "NL", b, "NL") is None          # and in one country they are not alike enough
    assert similarity(a, b) < 0.85


def test_a_numbered_sibling_is_not_a_candidate():
    assert is_candidate("szkola podstawowa nr 1", "PL", "szkola podstawowa nr 2", "PL") is None


def test_a_spelling_variant_is_a_candidate_within_a_country_only():
    a = "fraunhofer gesellschaft zur forderung der angewandten forschung"
    b = "fraunhofer gesellschaft zur foerderung der angewandten forschung"
    assert is_candidate(a, "DE", b, "DE") >= 0.85
    assert is_candidate(a, "DE", b, "AT") is None


def test_trigrams_follow_pg_trgm():
    # the set pg_trgm gives for "cat": "  c", " ca", "cat", "at "
    assert trigrams("cat") == {"  c", " ca", "cat", "at "}
    assert trigrams("a b") == {"  a", " a ", "  b", " b "}
    assert similarity("cat", "cat") == 1.0


# ------------------------------------------------------------------ the gold set

def test_the_gold_set_is_big_enough_and_balanced():
    pairs = evaluate.load_seed()
    assert len(pairs) >= 150
    assert sum(p["is_match"] for p in pairs) >= 75
    assert sum(not p["is_match"] for p in pairs) >= 75
    kinds = {p["kind"] for p in pairs}
    assert {"parent_child", "other_country", "sibling"} <= kinds
    assert len({(p["name_a"], p["country_a"], p["name_b"], p["country_b"]) for p in pairs}) == len(pairs)


def test_the_stages_that_decide_alone_have_precision_97_on_the_gold_set():
    rep = evaluate.evaluate(evaluate.load_seed())
    for stage in evaluate.DECIDING:
        precision = rep["stages"][stage]["precision"]
        assert precision is None or precision >= evaluate.MIN_PRECISION, (stage, rep["stages"][stage])
    assert rep["ok"]


def test_no_parent_subsidiary_or_cross_country_pair_is_ever_decided_to_be_the_same():
    for p in evaluate.load_seed():
        if p["kind"] in ("parent_child", "other_country", "sibling", "other_entity"):
            assert not p["is_match"]
            assert evaluate.decide(p)[0] in ("none", "candidate"), p


def test_a_failing_stage_fails_the_command():
    bad = [{"name_a": "Acme", "country_a": "FR", "name_b": "Acme SA", "country_b": "FR",
            "is_match": False, "kind": "other_entity"}]
    rep = evaluate.evaluate(bad)
    assert not rep["ok"] and rep["stages"]["exact_name"]["false_positive"] == 1


def test_the_report_prints_a_row_per_stage():
    rep = evaluate.evaluate(evaluate.load_seed())
    text = evaluate.format_report(rep)
    for word in ("identifier", "exact_name", "candidate", "deciding_stages", "precision"):
        assert word in text
    json.dumps(rep, default=str)
