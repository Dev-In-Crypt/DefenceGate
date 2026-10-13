"""Verification round of 13 October 2026, package WP-2: classification precision.

Every buyer name and notice title here was read in the verifier's report
(docs/verification/classification.md, coverage.md, correctness.md); the id in the
comment is the serving-row id it was found under. Titles only: nothing describes a
system's technical specification.

Left alone on purpose, because they are the owner's to decide (pinned below so that
nobody changes them by accident): D1 (the 2009/81/EC legal basis alone qualifies a
notice for `core`), D3 (a military CPV from police, prison or tax bodies stays core)
and D10 (defence-specific titles in `supply`).
"""

from __future__ import annotations

import pytest

from dgate import buyer_vocab as bv
from dgate.classify import CPV_MILITARY_ADJACENT, classify
from dgate.db import names_compatible
from dgate.normalise import normalise_org_name
from dgate.ops import derive_buyers as d


def verdict(name, country, cpv, *, legal=None, listed=False):
    cls = bv.effective_buyer_class(name, country, listed)
    return classify(legal_basis=legal, cpv_codes=cpv, buyer_is_defence=listed, buyer_class=cls)


def in_core(sig) -> bool:
    return bool(sig.legal_basis or (sig.military_cpv and not sig.dual_use))


# ------------------------------------------------------------ D2, D4: CPV groups

@pytest.mark.parametrize("name, country, cpv", [
    # 71643 / 63262 / 42541: road works carrying 35710000 (the road authority is also D6)
    ("Skarb Państwa, Generalny Dyrektor Dróg Krajowych i Autostrad", "PL", ["35710000"]),
    # 120390: IT software for a parking company
    ("Umeå Parkerings AB", "SE", ["35710000"]),
    # 48271: "Command, control, communication and computer systems", an airport
    ("Swedavia AB", "SE", ["35710000"]),
    # 69551 / 81422: "Radar sets", the Swedish maritime administration
    ("Sjöfartsverket", "SE", ["35722000"]),
    # D4, 98882: "Protective gear", a Maltese procurement directorate the vocabulary
    # cannot place (class other)
    ("Sectoral Procurement Directorate", "MT", ["35113400", "35113430", "35814000"]),
    # an unknown commercial buyer with a UAV code (group 356) and nothing else
    ("Some Engineering Works Ltd", "GB", ["35613000"]),
])
def test_civil_bodies_with_only_ambiguous_military_groups_leave_core(name, country, cpv):
    sig = verdict(name, country, cpv)
    assert sig.military_cpv and sig.is_defence       # kept in the table, labelled
    assert sig.dual_use and not in_core(sig)


def test_ambiguous_groups_demote_a_buyer_the_vocabulary_cannot_name_only_when_alone():
    unknown = "Some Engineering Works Ltd"
    assert bv.buyer_class_of(unknown, "GB") == "other"
    # one unambiguous military group beside the ambiguous one: stays core
    assert in_core(verdict(unknown, "GB", ["35710000", "35330000"]))
    # a military CPV outside division 35 is never ambiguous
    assert in_core(verdict(unknown, "GB", ["35710000", "50630000"]))
    # the directive, or a listed buyer, keeps the notice where it was
    assert in_core(verdict(unknown, "GB", ["35710000"], legal="32009L0081"))
    assert in_core(verdict(unknown, "GB", ["35710000"], listed=True))
    # ammunition from a body that is not listed stays core: group 353 is not ambiguous
    assert in_core(verdict(unknown, "GB", ["35330000"]))


def test_the_demotion_reason_says_which_rule_fired():
    sig = verdict("Some Engineering Works Ltd", "GB", ["35613000"])
    assert any("356-358" in r for r in sig.reasons)


# --------------------------------------------------------------- D5: elision

@pytest.mark.parametrize("name", [
    "Ville d'Orléans",                  # 170189, event equipment
    "Ville d'Antibes Juan-les-Pins",    # 173625, flags and events
    "Ville d'Aulnay-sous-Bois",         # 175559
    "Commune d'Agde",
    "Ville de Paris",
    "Département d'Ille-et-Vilaine",
])
def test_french_towns_with_an_elided_article_are_municipal(name):
    assert bv.buyer_class_of(name, "FR") == "municipal"
    assert verdict(name, "FR", ["35821000", "35321100"]).dual_use


# ----------------------------------------------- D6: utilities and infrastructure

@pytest.mark.parametrize("name, country", [
    ("Swedavia AB", "SE"),
    ("Sjöfartsverket", "SE"),
    ("Umeå Parkerings AB", "SE"),
    ("Skarb Państwa-Generalny Dyrektor Dróg Krajowych i Autostrad", "PL"),
    ("Port Lotniczy Wrocław", "PL"),
    ("Zarząd Dróg Wojewódzkich w Lublinie", "PL"),
    ("Deutscher Wetterdienst", "DE"),
    ("Polskie Linie Kolejowe", "PL"),
    ("Wodociągi Miejskie", "PL"),
])
def test_infrastructure_operators_are_their_own_demoting_class(name, country):
    assert bv.buyer_class_of(name, country) == "infrastructure"
    assert "infrastructure" in bv.DEMOTING_CLASSES


@pytest.mark.parametrize("name, country", [
    ("Wojskowe Zakłady Lotnicze nr 1", "PL"),
    ("Ministerstvo obrany", "CZ"),
    ("Bundesamt für Ausrüstung, Informationstechnik und Nutzung der Bundeswehr", "DE"),
])
def test_defence_bodies_are_never_infrastructure(name, country):
    assert bv.buyer_class_of(name, country) == "defence"


# --------------------------------------------------------------- D7: DGA

@pytest.mark.parametrize("name", [
    "DGA Council of Europe Directorate General of Administration",
    "Council of Europe — Directorate General of Administration",   # 206009
    "DGA Tech de France Travail",
])
def test_the_dga_rule_no_longer_matches_other_bodies(name):
    assert bv.defence_body(name, "FR").label is None
    assert bv.buyer_class_of(name, "FR") != "defence"


def test_the_french_armament_agency_is_still_a_defence_body():
    for name in ("DGA/DO/S2A", "DGA Maîtrise de l'information", "Direction générale de l'armement"):
        assert bv.defence_body(name, "FR").confidence >= 0.80, name


# ------------------------------------------- D11: the armed forces' own bodies

def test_the_armed_forces_university_is_not_labelled_education():
    for name in ("Universität der Bundeswehr München", "Universität der Bundeswehr München (UniBw M)"):
        assert bv.buyer_class_of(name, "DE") == "defence"                      # 76598, 91345
    # a simulator bought by the Bundeswehr's university is a military CPV in core
    assert in_core(verdict("Universität der Bundeswehr München (UniBw M)", "DE", ["35740000"]))
    # a civil university is as it was
    assert verdict("Technische Universität Dresden", "DE", ["35810000"]).dual_use
    # and the buyer list still keeps the university out (property of the earlier decision)
    assert bv.defence_body("Universität der Bundeswehr München", "DE").label is None


@pytest.mark.parametrize("name", [
    "Junta de Contratación del Ejército de Tierra",       # 190165, 220351
    "Junta de Contratación del Ejército del Aire",
    "Junta de Contratación de la Armada",
])
def test_the_spanish_army_contracting_board_is_not_municipal(name):
    assert bv.buyer_class_of(name, "ES") == "defence"
    assert in_core(verdict(name, "ES", ["45216200"]))      # construction for military buildings


def test_a_municipal_junta_is_still_municipal():
    assert bv.buyer_class_of("Junta de Andalucía", "ES") == "municipal"


# ----------------------------------------- D13: embassies, hospitals, institutes

@pytest.mark.parametrize("name, country", [
    ("Ambasada Rzeczypospolitej Polskiej w Republice Białorusi", "BY"),   # 42598, 67824
    ("Embassy of the Netherlands", "NL"),
    ("Delegation of the European Union to Ukraine", "UA"),
    ("Council of Europe — Directorate General of Administration", "FR"),
])
def test_embassies_and_international_bodies_are_demoted(name, country):
    assert bv.buyer_class_of(name, country) == "international"
    assert verdict(name, country, ["35810000"]).dual_use


def test_a_military_hospital_or_institute_is_demoted_like_a_civil_one():
    assert bv.buyer_class_of("Chu de Pointe à Pitre", "FR") == "health"        # 47472
    assert bv.buyer_class_of("Sieć Badawcza Łukasiewicz – Instytut Lotnictwa", "PL") == "education"
    assert verdict("Sieć Badawcza Łukasiewicz – Instytut Lotnictwa", "PL", ["35722000"]).dual_use


# ------------------------------------------------- D9: military CPVs outside 35

@pytest.mark.parametrize("code, why", [
    ("50620000", "of firearms and ammunition"),
    ("50630000", "of military vehicles"),                      # 213656
    ("50650000", "of military aircrafts, missiles and spacecrafts"),
    ("50660000", "of military electronic systems"),            # 127459
    ("50840000", "of weapons and weapon systems"),             # 233846
    ("50841000", "of weapons"),
    ("50842000", "of weapon systems"),                         # 41490
    ("80630000", "training and simulation in military vehicles"),
    ("80640000", "training and simulation in warships"),
    ("80650000", "training and simulation in aircrafts, missiles and spacecrafts"),
])
def test_military_repair_and_training_codes_are_military_cpvs(code, why):
    assert code in CPV_MILITARY_ADJACENT, why
    sig = classify(legal_basis=None, cpv_codes=[code], buyer_is_defence=False)
    assert sig.cpv_adjacent and sig.military_cpv and sig.is_defence
    assert not sig.cpv_ambiguous_only


@pytest.mark.parametrize("code", [
    "50600000",     # parent: "security and defence materials", alarms and cameras too
    "50610000",     # security equipment (alarms, cameras): a civil market
    "50000000", "50100000", "50800000",
    "80600000",     # parent: training in defence and security materials
    "80610000", "80620000", "80000000", "80660000",
])
def test_neighbouring_codes_stay_out(code):
    assert not classify(legal_basis=None, cpv_codes=[code], buyer_is_defence=False).military_cpv


def test_a_municipal_repair_of_weapon_systems_is_still_demoted():
    assert verdict("Stadt Nürnberg", "DE", ["50840000"]).dual_use


# ----------------------------------------------- D8: class on listed buyers

def test_a_listed_buyer_is_a_defence_body_whatever_its_name_says():
    name = "HM Védelemgazdasági Hivatal"                                   # 203812
    assert bv.buyer_class_of("Some Unnamed Depot", "HU") == "other"
    assert bv.effective_buyer_class("Some Unnamed Depot", "HU", listed=True) == "defence"
    assert bv.effective_buyer_class("Some Unnamed Depot", "HU", listed=False) == "other"
    assert bv.buyer_class_of(name, "HU") == "defence"
    assert bv.defence_body(name, "HU").confidence >= 0.80


def test_a_listed_buyer_keeps_a_warning_label_when_its_name_says_hospital():
    assert bv.effective_buyer_class("Szpital Wojewódzki w Zamościu", "PL", listed=True) == "health"


def test_the_navy_with_a_country_in_the_name():
    assert bv.buyer_class_of("Royal Netherlands Navy", "NL") == "defence"          # 216394


# ---------------------------------------- D12 / C2: bodies missing from the lists

@pytest.mark.parametrize("name", [
    "Bundeswehr-Dienstleistungszentrum Leer",                       # 655852-2026
    "Bundeswehr-Dienstleistungszentrum Koblenz",
    "Bundeswehr Dienstleistungszentrum Ulm",
    "Verpflegungsamt der Bundeswehr",
    "Bundesamt für Ausrüstung, Informationstechnik und Nutzung der Bundeswehr",
    "Bundesamt fur Aussrustung Informationstechnik und Nutzung der Bundeswehr",
])
def test_bundeswehr_service_bodies_reach_the_loading_floor(name):
    body = bv.defence_body(name, "DE")
    assert body.label and body.confidence >= 0.80, (name, body)


def test_other_bundeswehr_offices_still_wait_for_a_person():
    # recruiting, personnel and training centres buy for themselves: left at 0.70
    for name in ("Karrierecenter der Bundeswehr Kiel", "Bundesamt für das Personalmanagement "
                 "der Bundeswehr", "Zentrum Brandschutz der Bundeswehr"):
        assert 0 < bv.defence_body(name, "DE").confidence < 0.80, name


@pytest.mark.parametrize("name", [
    "1 Baza Lotnictwa Transportowego",                              # 110775-2026
    "42 Baza Lotnictwa Szkolnego w Radomiu",
    "Rejonowy Zarząd Infrastruktury w Lublinie",
    "Rejonowy Zarząd Infrastruktury we Wrocławiu",
])
def test_polish_air_bases_and_regional_infrastructure_boards_are_listed(name):
    assert d.decide(name, d.PL_INCLUDE, d.PL_EXCLUDE).category is not None
    assert bv.defence_body(name, "PL").confidence >= 0.80


@pytest.mark.parametrize("name", [
    "Intendente de Rota", "Intendente de San Fernando", "Organo de contratacion Intendente de Rota",
    "Intendencia de Madrid", "Jefatura de Intendencia y Asuntos Económicos Sur",
])
def test_spanish_intendances_are_listed(name):
    assert d.decide(name, d.ES_INCLUDE, d.ES_EXCLUDE).category is not None


def test_a_property_agency_is_still_not_a_defence_buyer():
    """Owner's standing decision (docs/RUNBOOK.md, buyer_vocab.PROPERTY): military property
    and estate agencies stay off the list. Forsvarsbygg is one of them; whether it moves is
    a policy change and not part of this package."""
    for name, country in (("Forsvarsbygg", "NO"), ("Agencja Mienia Wojskowego", "PL"),
                          ("Defence Infrastructure Organisation", "GB")):
        assert bv.defence_body(name, country).label is None, name


# ------------------------------------------------------ D8: the shared number

def test_a_ministrys_number_does_not_vouch_for_a_service_that_shares_only_its_prefix():
    holder = normalise_org_name("MINARM/AIR/SIAé")                  # organisation 196441
    for stated in ("MINARM/SCA/PFC-RBT", "MINARM/SGA/DCSID/ESID Lyon", "MINARM/SGA/SDPAMG",
                   "MINARM/EMA/SCA/PFC-SE/DAP/BHA", "SID Sud-Est", "PFC SO"):
        assert not names_compatible(normalise_org_name(stated), holder), stated


def test_two_services_that_differ_in_one_word_are_not_one_body():
    assert not names_compatible("minarm sga dcsid esid lyon", "minarm sga dcsid esid toulon")


@pytest.mark.parametrize("a, b", [
    ("ministerstvo obrany", "ceska republika - ministerstvo obrany"),
    ("bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr",
     "bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr baainbw"),
    ("gemeinde neustadt", "neustadt gemeinde"),
    ("ministerstvo obrany", "ministerstvo obrany"),
])
def test_spelling_variants_of_one_body_stay_compatible(a, b):
    assert names_compatible(a, b)


# ---------------------------------------- the owner's decisions, pinned unchanged

def test_owner_d1_the_directive_alone_still_qualifies_a_notice_for_core():
    sig = verdict("Landesbetrieb Bau und Liegenschaften", "DE", ["45000000"], legal="32009L0081")
    assert sig.is_defence and in_core(sig)


def test_owner_d3_a_police_body_keeps_its_military_cpv_in_core():
    for name, cpv in (("Komenda Główna Policji", ["35321200"]),                  # 1037
                      ("Izba Administracji Skarbowej w Gdańsku", ["35321100", "35330000"])):  # 618
        sig = verdict(name, "PL", cpv)
        assert bv.buyer_class_of(name, "PL") == "security" and in_core(sig), name


# ------------------------------------------------- the derived file, one row a name

def test_one_body_under_several_numbers_is_one_proposal():
    """14 organisations named 'Bundeswehr-Dienstleistungszentrum Aachen' (one per Leitweg-ID
    the notices stated) made 14 identical rows of the derived file."""
    rows = [("DE", "bundeswehr-dienstleistungszentrum aachen", "", 2),
            ("DE", "bundeswehr-dienstleistungszentrum aachen", "T0228885504", 3),
            ("DE", "bundeswehr-dienstleistungszentrum aachen", "9911394720", 1),
            ("DE", "bundeswehr-dienstleistungszentrum bonn", "", 1)]
    got = d.vocabulary_proposals(rows)
    assert [(p.name, p.identifier, p.notices) for p in got] == [
        ("bundeswehr-dienstleistungszentrum aachen", "T0228885504", 6),
        ("bundeswehr-dienstleistungszentrum bonn", "", 1)]
