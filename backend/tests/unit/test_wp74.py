"""WP-74: a shared tax id never merges public bodies or their units; companies still merge."""

from __future__ import annotations

import pytest

from dgate.buyer_family import is_public_body, is_sub_unit
from dgate.ops.accept_merge_candidates import plan


def _org(i, name, *, reg=None, country="ES", **kw):
    return {"id": i, "country": country, "name": name, "suppressed": False, "person": False,
            "reg": reg, "vat": None, "pic": None, "notices": 0, **kw}


def _pair(cid, a, b):
    return {"id": cid, "a": a, "b": b, "confidence": 0.97, "match_method": "identifier",
            "evidence": f"{a}~{b}"}


# names read from the batch of 21 October 2026 (stored form: lower case, accents folded)
PUBLIC = [
    ("ES", "gobierno vasco - seguridad"),
    ("ES", "gobierno vasco departamento de trabajo y justicia"),
    ("ES", "area de gobierno de vicealcaldia portavoz seguridad"),
    ("ES", "diputacion de barcelona gabinete de presidencia"),
    ("ES", "consejeria de urbanismo y sostenibilidad del ayuntamiento de zaragoza"),
    ("IT", "agenzia del demanio direzione regionale lazio"),
    ("IT", "ministero delle infrastrutture e delle mobilita sostenibili mims - direzione generale"),
    ("IT", "comune di genova stazione unica appaltante"),
    ("RO", "directia generala de asistenta sociala"),
    ("RO", "regia nationala a padurilor romsilva directia silvica arges"),
    ("AT", "land tirol"),
    ("DE", "stadt bochum referat zentraler einkauf"),
    ("FR", "ministere de la justice"),
    ("BE", "infrabel direction asset management area center"),
    ("BG", "югоизточно държавно предприятие тп държавно горско стопанство свиленград"),
    # let through by the first vocabulary in the production dry run
    ("FR", "clisson sevre et maine agglo"),
    ("FR", "beaune cote et sud communaute beaune-chagny-nolay"),
    ("FR", "centre intercommunal d action sociale du pays ajaccien"),
    ("FR", "syndicat mixte stations du mercantour"),
    ("BG", "агенция пътна инфраструктура областно пътно управление"),
    ("AT", "asfinag autobahnen- und schnellstrassen-finanzierungs-aktiengesellschaft"),
    ("DE", "nlwkn betriebsstelle aurich"),
    ("DE", "ersatzbau lra miesbach hier pv-anlage"),
    ("SE", "goteborgs stad intraservice"),
    ("DK", "region hovedstaden"),
    ("NO", "arbeids- og velferdsetaten"),
    ("BE", "associatie ku leuven"),
]
COMPANIES = [
    ("ES", "bilbao exhibition centre"),
    ("BG", "булгартрансгаз еад"),
    ("DE", "rheinmetall landsysteme"),
    ("FR", "naval group"),
    ("IT", "fincantieri"),
]


@pytest.mark.parametrize("country,name", PUBLIC)
def test_administrations_and_their_units_are_public_bodies(country, name):
    assert is_public_body(name, country)


@pytest.mark.parametrize("country,name", COMPANIES)
def test_companies_are_not(country, name):
    assert not is_public_body(name, country)


def test_flags_role_and_legal_form_make_a_public_body_whatever_the_name():
    assert is_public_body("acme", "FR", defence_buyer=True)
    assert is_public_body("acme", "FR", org_role="buyer")
    assert is_public_body("acme", "DE", legal_form="Anstalt des offentlichen Rechts")
    assert not is_public_body("acme", "FR", org_role="supplier")


def test_a_unit_name_is_told_from_its_parent():
    assert is_sub_unit("gobierno vasco - seguridad") is False   # the head's name does not say it
    assert is_sub_unit("gobierno vasco departamento de salud")
    assert is_sub_unit("ayuntamiento de madrid area de gobierno de economia")
    assert not is_sub_unit("ayuntamiento de madrid")
    assert not is_sub_unit("gobierno vasco")


def test_dutch_care_of_is_acting_for_another_body_and_the_italian_spa_is_not():
    from dgate.ops.accept_merge_candidates import ACTING_FOR
    assert ACTING_FOR.search("associatie ku leuven p a ku leuven")
    assert ACTING_FOR.search("p a csg - marnix academie utrecht")
    assert not ACTING_FOR.search("s c r - piemonte s p a")


def test_a_shared_tax_id_never_merges_a_public_body_and_still_merges_companies():
    orgs = {1: _org(1, "gobierno vasco", reg="S4833001C"), 2: _org(2, "gobierno vasco departamento de salud"),
            3: _org(3, "bilbao exhibition centre", reg="A95135984"), 4: _org(4, "bec bilbao exhibition centre s a"),
            5: _org(5, "acme", reg="X1", is_defence_buyer=True), 6: _org(6, "acme sistemas")}
    groups, refused = plan([_pair(1, 1, 2), _pair(2, 3, 4), _pair(3, 5, 6)], orgs)
    assert refused == {"public_body": 2}
    assert [(g["head"], g["members"]) for g in groups] == [(3, [4])]
