"""Work package E (12 October 2026): classification, buyer classes, the derived
buyer list and identifier handling. Every case here is a body or a notice that
was read in the audit, not an invented one.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

from dgate import buyer_vocab as bv
from dgate.classify import (
    CPV_ADJACENT_2026_10_12,
    CPV_CIVIL_EXCEPTIONS,
    CPV_MILITARY_ADJACENT,
    MILITARY_CPV_SQL_REGEX,
    classify,
)
from dgate.normalise import (
    candidate_key,
    normalise_identifier,
    normalise_org_name,
    token_sort_key,
)

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / \
    "0029_classification_and_buyer_entities.sql"


# ------------------------------------------------------------- the vocabulary

@pytest.mark.parametrize("name, country", [
    ("Ministerul Apărării Naționale - Unitatea Militară 02550 București", "RO"),
    ("Ministerul Apărării - U.M. 02192", "RO"),
    ("Česká republika - Ministerstvo obrany", "CZ"),
    ("Ministerstvo obrany - Česká republika, sekce vyzbrojování a akvizic", "CZ"),
    ("Ministerie van Defensie", "BE"),
    ("Direction générale Material Resources - Division Marchés publics", "BE"),
    ("Danish Ministry of Defence Acquisition and Logistics Organisation (DALO)", "DK"),
    ("Department of Defence", "IE"),
    ("Irish Defence Forces", "IE"),
    ("European Defence Agency", "BE"),
    ("OCCAR-EA", "DE"),
    ("NATO Support and Procurement Agency (NSPA)", "LU"),
    ("Bundesamt für Ausrüstung, Informationstechnik und Nutzung der Bundeswehr", "DE"),
    ("BAAINBw Koblenz", "DE"),
    ("Economat des armées", "FR"),
    ("Ministère des Armées - Direction générale de l'armement", "FR"),
    ("Försvarets materielverk", "SE"),
    ("Forsvarsministeriet", "DK"),
    ("Puolustusvoimat", "FI"),
    ("Kaitseministeerium", "EE"),
    ("Υπουργείο Εθνικής Άμυνας", "GR"),
    ("Министерство на отбраната", "BG"),
])
def test_defence_bodies_are_recognised_with_confidence_to_load(name, country):
    body = bv.defence_body(name, country)
    assert body.label, name
    assert body.confidence >= 0.80, (name, body)


@pytest.mark.parametrize("name, country, why", [
    # the exclusions the owner asked for, by name
    ("Hôpital d'instruction des armées Percy", "FR", "military_healthcare"),
    ("Wojskowy Szpital Kliniczny", "DE", "military_healthcare"),
    ("Ministerul Apărării - Spitalul Militar de Urgență Regina Maria", "RO", "military_healthcare"),
    ("Universität der Bundeswehr München", "DE", "education"),
    ("Bundeswehr Sprachenschule", "DE", "education"),
    ("Defence Infrastructure Organisation (MOD DIO)", "GB", "property_agency"),
    ("Bundesanstalt für Immobilienaufgaben - Bundeswehr", "DE", "property_agency"),
    ("Forsvarsbygg - the Norwegian Defence Estates Agency", "NO", "property_agency"),
    ("Établissement public d'aménagement de la Défense (Paris La Défense)", "FR", "property_agency"),
    ("Myndigheten för civilt försvar", "SE", "civil_protection"),
    ("Civil Defence Directorate", "IE", "civil_protection"),
    ("Bundesamt für Bevölkerungsschutz und Katastrophenhilfe", "DE", "civil_protection"),
])
def test_bodies_that_carry_a_defence_word_are_kept_out(name, country, why):
    body = bv.defence_body(name, country)
    assert body.label is None, (name, body)


@pytest.mark.parametrize("name", [
    "University Hospital Department of Human and Material Resources",
    "Gemeente Material Resources Management",
    "Material Resources Trading Ltd",
])
def test_the_phrase_material_resources_alone_does_not_make_a_defence_body(name):
    """Review finding of 13 October 2026: the bare phrase matched any name that held it,
    at 0.95. Only Belgian Defence's directorate (and a defence body that names it) does."""
    assert bv.defence_body(name, "BE").label is None, name


@pytest.mark.parametrize("name", [
    "Direction générale Material Resources - Division Marchés publics",
    "Defence - Material Resources Directorate",
])
def test_belgian_defences_material_resources_directorate_still_matches(name):
    assert bv.defence_body(name, "BE").confidence >= 0.80, name


def test_a_name_with_no_word_of_four_letters_is_compatible_with_nothing():
    """A stated number is trusted against a name only when the two share a word; a name
    with none to share used to pass because the test had nothing to compare."""
    from dgate.db import names_compatible

    assert names_compatible("ministerstvo obrany", "ceska republika ministerstvo obrany")
    assert not names_compatible("mon", "ministerstvo obrany")
    assert not names_compatible("ministerstvo obrany", "dga")
    assert not names_compatible("mon", "dga")
    assert not names_compatible("ministerstvo obrany", "krajska nemocnice liberec")


@pytest.mark.parametrize("name", [
    "Eda bostäder", "Dga Servicios Generales", "Ministerio de Fomento",
    "Gemeinde Westendorf", "Stadt Nürnberg Hochbauamt", "Freiwillige Feuerwehr Jelonki",
    "Politiets fellestjenester", "Rigspolitiet", "Ministerstvo vnitra",
])
def test_ordinary_and_security_bodies_are_not_defence_bodies(name):
    for country in ("SE", "DE", "PL", "DK", "CZ", "ES"):
        assert bv.defence_body(name, country).label is None


@pytest.mark.parametrize("name, country, expected", [
    ("Stadt Nürnberg", "DE", "municipal"),
    ("Gemeinde Westendorf", "DE", "municipal"),
    ("Ayuntamiento de Madrid", "ES", "municipal"),
    ("Gmina Miejska Kraków", "PL", "municipal"),
    ("Hlavní město Praha", "CZ", "municipal"),
    ("Universitätsklinikum Heidelberg", "DE", "health"),
    ("Szpital Wojewódzki w Zamościu", "PL", "health"),
    ("Technische Universität Dresden", "DE", "education"),
    ("Freiwillige Feuerwehr Westendorf", "DE", "fire_rescue"),
    ("Komenda Wojewódzka Państwowej Straży Pożarnej w Krakowie", "PL", "fire_rescue"),
    ("Inspectoratul General pentru Situații de Urgență", "RO", "fire_rescue"),
    ("Polizeiverwaltungsamt Logistikzentrum", "DE", "security"),
    ("Centralny Zarząd Służby Więziennej", "PL", "security"),
    ("Generalzolldirektion Zentrale Beschaffungsstelle", "DE", "security"),
    ("Ministerstvo vnitra", "CZ", "security"),
    ("Ministère des Armées", "FR", "defence"),
    ("Some Engineering Works Ltd", "GB", "other"),
])
def test_buyer_class(name, country, expected):
    assert bv.buyer_class_of(name, country) == expected


# --------------------------------------------------------------- the verdicts

def _verdict(name, country, cpv, *, legal=None, listed=False, clearance=False):
    return classify(
        legal_basis=legal, cpv_codes=cpv, buyer_is_defence=listed,
        security_clearance_text="present" if clearance else None,
        buyer_class=bv.buyer_class_of(name, country))


def test_a_municipality_buying_a_military_cpv_item_is_demoted_to_dual_use():
    sig = _verdict("Stadt Nürnberg", "DE", ["35810000"])
    assert sig.cpv_military and not sig.legal_basis
    assert sig.dual_use and sig.is_defence       # labelled, kept, out of `core`
    assert sig.confidence < 0.5


def test_a_fire_brigade_buying_a_military_cpv_item_is_demoted():
    sig = _verdict("Freiwillige Feuerwehr Westendorf", "DE", ["35811300"])
    assert sig.dual_use


def test_a_hospital_and_a_university_are_demoted_too():
    assert _verdict("Szpital Wojewódzki w Zamościu", "PL", ["35820000"]).dual_use
    assert _verdict("Technische Universität Dresden", "DE", ["35810000"]).dual_use


def test_the_legal_basis_or_a_listed_buyer_keeps_a_military_cpv_in_core():
    by_law = _verdict("Stadt Nürnberg", "DE", ["35810000"], legal="32009L0081")
    assert by_law.is_defence and not by_law.dual_use
    listed = _verdict("Stadt Nürnberg", "DE", ["35810000"], listed=True)
    assert listed.is_defence and not listed.dual_use


def test_a_police_body_keeps_its_military_cpv_and_is_labelled_security():
    sig = _verdict("Polizeiverwaltungsamt Logistikzentrum", "DE", ["35810000"])
    assert sig.is_defence and not sig.dual_use
    assert bv.buyer_class_of("Polizeiverwaltungsamt Logistikzentrum", "DE") == "security"


def test_a_guard_service_notice_with_clearance_only_is_not_defence():
    sig = _verdict("Landratsamt Musterkreis", "DE", ["79713000"], clearance=True)
    assert sig.clearance and not sig.is_defence


def test_clearance_plus_a_civil_security_cpv_no_longer_qualifies():
    """Finding F8: 316 such rows were read, none was relevant."""
    sig = _verdict("Landratsamt Musterkreis", "DE", ["35120000"], clearance=True)
    assert sig.cpv_civil_security and sig.clearance
    assert not sig.is_defence
    assert sig.confidence < 0.5


def test_a_civil_cpv_with_a_listed_buyer_is_defence_but_not_core():
    sig = _verdict("Ministerul Apărării Naționale", "RO", ["35110000"], listed=True)
    assert sig.is_defence and sig.buyer and not sig.military_cpv


def test_the_municipal_fire_extinguisher_stays_out():
    sig = _verdict("Stadt Nürnberg", "DE", ["35110000"], legal="32014L0024")
    assert not sig.is_defence


@pytest.mark.parametrize("code, military", [
    ("45216200", True), ("50640000", True), ("75220000", True), ("75221000", True),
    ("75222000", False),      # civil defence services
    ("45216000", False), ("50600000", False), ("75200000", False),
    ("35330000", True), ("35811300", True), ("35811100", False), ("35821000", False),
    ("35110000", False), ("35120000", False), ("90911100", False),
])
def test_military_cpvs_outside_division_35(code, military):
    sig = classify(legal_basis=None, cpv_codes=[code], buyer_is_defence=False)
    assert sig.military_cpv is military
    assert sig.is_defence is military
    assert sig.cpv_adjacent is (code in CPV_MILITARY_ADJACENT)


def test_a_linked_defence_notice_makes_its_twin_defence():
    sig = classify(legal_basis=None, cpv_codes=["90911100"], buyer_is_defence=False,
                   linked_defence=True)
    assert sig.is_defence and not sig.military_cpv


def test_the_sql_and_python_military_cpv_rules_agree():
    """Migration 0029 backfills the column in SQL; the classifier decides in Python."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert MILITARY_CPV_SQL_REGEX in sql
    # The codes added on 13 October 2026 are not in this migration: stored rows get them
    # from `reprocess --reclassify-serving`, which reads cpv_codes (tests/integration).
    for code in CPV_ADJACENT_2026_10_12 | CPV_CIVIL_EXCEPTIONS:
        assert f"'{code}'" in sql
    for n in range(35000000, 36000000, 4999):
        code = str(n)
        in_sql = bool(re.search(MILITARY_CPV_SQL_REGEX, code)) and code not in CPV_CIVIL_EXCEPTIONS
        assert in_sql == classify(legal_basis=None, cpv_codes=[code],
                                  buyer_is_defence=False).cpv_military, code


# ------------------------------------------------------------ name folding

@pytest.mark.parametrize("raw, folded", [
    ("Česká republika - Ministerstvo obrany", "ministerstvo obrany"),
    ("Ministerstvo obrany - Česká republika", "ministerstvo obrany"),
    ("Ministerstvo obrany ČR", "ministerstvo obrany"),
    ("Skarb Państwa - Jednostka Wojskowa Nr 2305", "jednostka wojskowa nr 2305"),
    ("Bundesrepublik Deutschland, vertreten durch das Bundesministerium der Verteidigung",
     "bundesministerium der verteidigung"),
    ("Republik Österreich (Bund) vertreten durch die Bundesministerin für Landesverteidigung",
     "bundesministerin fur landesverteidigung"),
    ("Republic of Benin represented by the Ministry of Economy and Finance",
     "ministry of economy and finance"),
])
def test_state_prefixes_fold_only_when_asked(raw, folded):
    assert normalise_org_name(raw, fold_state=True) == folded
    # The stored form must not move: names already stored were normalised without it.
    assert normalise_org_name(raw) == normalise_org_name(raw, fold_state=False)
    assert normalise_org_name(raw) != folded


def test_the_stored_normal_form_is_unchanged_for_the_old_inputs():
    assert normalise_org_name("Ministerstwo Obrony Narodowej") == "ministerstwo obrony narodowej"
    assert normalise_org_name("Białystok Sp. z o.o.") == "bialystok"
    assert normalise_org_name("Česká republika - Ministerstvo obrany") == \
        "ceska republika - ministerstvo obrany"


def test_candidate_keys_meet_spelling_and_word_order_variants():
    assert candidate_key("Česká republika - Ministerstvo obrany") == \
        candidate_key("Ministerstvo obrany ČR")
    assert token_sort_key("defence ministry") == token_sort_key("ministry of defence")
    assert candidate_key("Ministerul Apărării - U.M. 02192") == \
        candidate_key("Unitatea Militară 02192 București") == "unitatea militara 02192"
    # different unit numbers are different bodies
    assert candidate_key("Unitatea Militară 02192") != candidate_key("Unitatea Militară 02193")


# -------------------------------------------------------------- identifiers

@pytest.mark.parametrize("raw, country, expected", [
    ("REGON 170939001", "PL", "170939001"),
    ("5250007313", "PL", "5250007313"),
    ("NIP: 525-000-73-13", "PL", "5250007313"),
    ("DE 139 601 469", "DE", "139601469"),
    ("DE139601469", "DE", "139601469"),
    ("SIRET 217 901 917 00013", "FR", "21790191700013"),
    ("00179906", "CZ", "00179906"),
    ("992-80002-47", "DE", "9928000247"),
    # not identifiers
    ("COM", "BE", None), ("n/a", "MT", None), ("TBD", "MT", None), ("N.A.", "ME", None),
    ("ORG-29942897", "DK", None),
    ("9fc9d88c-a65f-4bb1-8dee-78656efdd490", "CH", None),
    ("https://1486", "CY", None), ("B4513", "LU", None), ("1", "AT", None),
    ("Central government authority", "MZ", None),
    ("Reg.No.07008104; PIC:951929386", "RS", None),
    ("", "PL", None), (None, "PL", None), ("000000000", "PL", None),
])
def test_normalise_identifier(raw, country, expected):
    assert normalise_identifier(raw, country) == expected


# --------------------------------------------------------- the derived list

def test_vocabulary_proposals_skip_poland_and_spain_and_exclusions():
    from dgate.ops.derive_buyers import vocabulary_proposals

    rows = [
        ("CZ", "Česká republika - Ministerstvo obrany", "60162694", 14),
        ("PL", "Ministerstwo Obrony Narodowej", "", 3),            # has its own rules
        ("ES", "Ministerio de Defensa", "", 3),
        ("DE", "Universität der Bundeswehr München", "", 2),     # excluded
        ("DE", "Karrierecenter der Bundeswehr Kiel", "", 0),
        ("SE", "Eda bostäder", "", 0),
    ]
    got = vocabulary_proposals(rows)
    assert {(p.country, p.name) for p in got} == {
        ("CZ", "Česká republika - Ministerstvo obrany"),
        ("DE", "Karrierecenter der Bundeswehr Kiel")}
    low = next(p for p in got if p.country == "DE")
    assert low.confidence < 0.80       # reviewed by a person before it counts


def test_derived_files_are_one_per_country_and_keep_human_decisions(tmp_path):
    from dgate.ops.derive_buyers import Proposal, write_derived

    first = [Proposal("CZ", "ministerstvo obrany", "", "ministry", 0.95),
             Proposal("CZ", "vojenska sprava x", "", "military_unit", 0.85),
             Proposal("DE", "karrierecenter der bundeswehr kiel", "", "defence_word", 0.70)]
    assert write_derived(first, tmp_path) == {"CZ": 2, "DE": 1}
    path = tmp_path / "defence_buyers_derived_CZ.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert [r["reviewed"] for r in rows] == ["false", "false"]
    assert list(rows[0]) == ["country", "name", "identifier", "reason", "confidence", "reviewed"]
    # a person rejects one; a re-derivation must not bring it back as undecided
    text = path.read_text(encoding="utf-8").replace(
        "vojenska sprava x,,military_unit,0.85,false", "vojenska sprava x,,military_unit,0.85,rejected")
    path.write_text(text, encoding="utf-8")
    write_derived(first, tmp_path)
    rows = {r["name"]: r["reviewed"] for r in csv.DictReader(path.open(encoding="utf-8"))}
    assert rows["vojenska sprava x"] == "rejected"


def test_the_loader_takes_confident_and_reviewed_rows_and_never_rejected_ones(tmp_path):
    from dgate.pipeline import DERIVED_MIN_CONFIDENCE, load_derived_rows

    (tmp_path / "defence_buyers_derived_XX.csv").write_text(
        "country,name,identifier,reason,confidence,reviewed\n"
        "XX,confident ministry,,ministry,0.95,false\n"
        "XX,borderline unit,,military_unit,0.85,false\n"
        "XX,weak word,,defence_word,0.70,false\n"
        "XX,weak but reviewed,,defence_word,0.70,true\n"
        "XX,confident but rejected,,ministry,0.95,rejected\n",
        encoding="utf-8")
    names = {r["name"] for r in load_derived_rows(tmp_path)}
    assert DERIVED_MIN_CONFIDENCE == 0.80
    assert names == {"confident ministry", "borderline unit", "weak but reviewed"}


def test_the_committed_derived_files_hold_no_excluded_body():
    from dgate.pipeline import DERIVED_GLOB, SEEDS_FILE

    files = sorted(SEEDS_FILE.parent.glob(DERIVED_GLOB))
    if not files:
        pytest.skip("no derived buyer files committed")
    seen = 0
    for path in files:
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                seen += 1
                assert row["country"] not in {"PL", "ES"}
                assert bv.defence_body(row["name"], row["country"]).label, row
                assert 0 < float(row["confidence"]) <= 1
    assert seen > 0
