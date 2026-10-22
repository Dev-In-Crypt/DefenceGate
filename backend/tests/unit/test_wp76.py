"""WP-76: a shared identifier merges only when a second signal agrees and neither side is public."""

from __future__ import annotations

import pytest

from dgate.buyer_family import is_public_body, public_identifier, public_signal
from dgate.ops.accept_merge_candidates import (
    ACTING_FOR,
    agreement,
    legal_forms,
    main,
    name_similarity,
    plan,
)


def _org(i, name, *, reg=None, country="NL", raw=(), **kw):
    return {"id": i, "country": country, "name": name, "suppressed": False, "person": False,
            "reg": reg, "vat": None, "pic": None, "notices": 0, "raw_names": list(raw), **kw}


def _pair(cid, a, b):
    return {"id": cid, "a": a, "b": b, "confidence": 0.97, "match_method": "identifier",
            "evidence": f"{a}~{b}"}


# identifiers read from the pending pairs on production, 22 October 2026
PUBLIC_IDS = [
    ("FR", "21370243400019"), ("FR", "24010080000020"), ("FR", "17350001800028"),
    ("FR", "25197619042"),              # a VAT number: check key + SIREN 197619042
    ("ES", "P1503700E"), ("ES", "Q2801011D"), ("ES", "S4833001C"), ("ES", "ESQ2826000H"),
    ("IT", "84000190714"), ("IT", "93005430256"), ("IT", "80204250585"),
    ("BE", "0207501113"), ("BE", "0316381138603153"),
    ("SE", "2120001181"), ("PT", "680021892"), ("EE", "75012345"), ("LV", "90000012345"),
    ("HU", "15732468215"), ("NL", "00000001003214345000"),
    ("DE", "LEITWEG99106546F80"), ("DE", "9911951888"), ("DE", "08421000A394320"),
]
COMPANY_IDS = [
    ("FR", "52291157700016"), ("FR", "12522911577"), ("FR", "44440103600121"),
    ("ES", "A95135984"), ("ES", "B59589143"), ("IT", "03278040245"), ("IT", "01199250158"),
    ("BE", "0698838775"), ("SE", "5564816204"), ("PT", "509479600"), ("NL", "82637490"),
    ("DE", "HRB10774"), ("DE", "811205325"), ("DE", "DE258395586"), ("HU", "24819699244"),
]


@pytest.mark.parametrize("country,ident", PUBLIC_IDS)
def test_identifiers_of_public_bodies(country, ident):
    assert public_identifier(country, None, ident)


@pytest.mark.parametrize("country,ident", COMPANY_IDS)
def test_identifiers_of_companies(country, ident):
    assert not public_identifier(country, ident)


def test_an_identifier_shape_is_read_in_its_own_country_only():
    assert public_identifier("FR", "21370243400019")
    assert not public_identifier("PL", "21370243400019")


# names the vocabulary of WP-74 let through (the two wrong pairs of its sample) and one per language
PUBLIC_NAMES = [
    ("NL", "ubr his"), ("NL", "ssc iuc dji"), ("NL", "sic dji"),
    ("NL", "erie van volksgezondheid welzijn en sport dtv ubr his"),
    ("NL", "gemeente oldebroek"), ("NL", "provincie gelderland"), ("NL", "waterschap rivierenland"),
    ("NL", "dienst justitiele inrichtingen"),
    ("DE", "landesamt fur steuern"), ("DE", "stadt ravensburg"), ("DE", "landkreis oder-spree"),
    ("DE", "behorde fur inneres und sport"), ("DE", "zweckverband abfallwirtschaft"),
    ("FR", "ministere de la culture"), ("FR", "prefecture de la gironde"), ("FR", "commune d orcieres"),
    ("FR", "conseil departemental 13"), ("FR", "sivom de la vallee"),
    ("IT", "comune di cesano boscone"), ("IT", "a s p palermo"), ("IT", "camera di commercio di torino"),
    ("IT", "centrale di committenza rete delle stazioni appaltanti"),
    ("ES", "ayuntamiento de zumaia"), ("ES", "mesa del senado"), ("ES", "xunta de galicia"),
    ("PL", "urzad gminy w kazimierzu biskupim"), ("PL", "gmina wronki"), ("PL", "starostwo powiatowe w x"),
    ("PL", "komenda wojewodzka policji"), ("PL", "jednostka wojskowa 1234"),
    ("CZ", "statni pozemkovy urad"), ("CZ", "obec dolni brezany"), ("SE", "ystads kommun"),
    ("FI", "lapuan kaupunki"), ("DK", "aarhus kommune"), ("BE", "cpas de boussu"),
    ("AT", "stadtgemeinde salzburg"), ("PT", "camara municipal de lisboa"), ("RO", "primaria orasului x"),
    ("EE", "tallinna linnavalitsus"), ("LV", "rigas valstspilsetas pasvaldiba"),
    ("LT", "vilniaus miesto savivaldybe"), ("HU", "tiszavasvari varos onkormanyzata"),
    ("BG", "столична община"), ("GR", "δημος περιστεριου"), ("IE", "limerick city and county council"),
]
COMPANY_NAMES = [
    ("NL", "thales nederland"), ("NL", "bonaire brandstof terminals"), ("DE", "rheinmetall landsysteme"),
    ("DE", "hensoldt sensors"), ("FR", "naval group"), ("FR", "arquus"), ("IT", "fincantieri"),
    ("IT", "leonardo"), ("ES", "indra sistemas"), ("ES", "navantia"), ("PL", "huta stalowa wola"),
    ("SE", "saab"), ("FI", "patria land"), ("NO", "nammo raufoss"), ("DK", "terma"),
    ("CZ", "czechoslovak group"), ("BE", "fn herstal"), ("PT", "edisoft"),
]


@pytest.mark.parametrize("country,name", PUBLIC_NAMES)
def test_public_names_of_every_country(country, name):
    assert is_public_body(name, country)


@pytest.mark.parametrize("country,name", COMPANY_NAMES)
def test_company_names_are_not_public(country, name):
    assert not is_public_body(name, country)


def test_a_buyer_is_public_unless_a_name_of_it_states_a_company_form():
    assert public_signal("bilbao exhibition centre", "ES", buys=True) == "buyer_role"
    assert public_signal("bilbao exhibition centre", "ES", buys=True, company_form=True) is None
    assert public_signal("acme", "FR", identifiers=("21370243400019",)) == "identifier"


def test_legal_forms_are_read_from_the_raw_names_of_the_aliases():
    assert legal_forms(_org(1, "ebn", raw=["EBN B.V."])) == {"bv"}
    assert legal_forms(_org(1, "ebn")) == set()


def test_the_names_must_agree_or_the_pair_waits():
    assert name_similarity("secom drobeta-turnu severin", "secom - drobeta turnu severin") == 1.0
    assert name_similarity("ssc iuc dji", "sic dji") < 0.85
    a, b = _org(1, "faxe og hylleholt boligforening"), _org(2, "faxe og hylleholdt boligforening")
    assert agreement(a, b) == ("identifier+name", 0.98)
    # a name and its long form, both B.V.
    a, b = _org(1, "ebn", raw=["EBN B.V."]), _org(2, "ebn energie beheer nederland", raw=["EBN B.V."])
    assert agreement(a, b) == ("identifier+legal_form", 0.98)
    a, b = _org(1, "stedin netbeheer", raw=["Stedin Netbeheer BV"]), _org(2, "stedin netbeheer b v")
    assert agreement(a, b) == ("identifier+name+legal_form", 0.99)
    # the same form and a shared word, but neither name begins or ends the other: two companies
    a = _org(1, "verkehrsbetrieb hamm", country="DE", raw=["Verkehrsbetrieb Hamm GmbH"])
    b = _org(2, "energie- und wasserversorgung hamm", country="DE",
             raw=["Energie- und Wasserversorgung Hamm GmbH"])
    assert agreement(a, b) is None
    # a sentence naming two companies contains the short name, but does not begin or end with it
    a = _org(1, "50hertz transmission", country="DE", raw=["50Hertz Transmission GmbH"])
    b = _org(2, "50hertz offshore die 50hertz transmission wurden von der", country="DE",
             raw=["50Hertz Offshore GmbH Die 50Hertz Transmission"])
    assert agreement(a, b) is None


def test_the_plan_refuses_public_units_waits_on_a_lone_number_and_records_the_method():
    orgs = {
        # the two wrong pairs of the WP-74 sample
        1: _org(1, "ubr his", reg="00000001003214345000"), 2: _org(2, "erie van volksgezondheid welzijn en sport dtv"),
        3: _org(3, "ssc iuc dji", reg="27373207"), 4: _org(4, "sic dji"),
        # a number and nothing else: waits
        5: _org(5, "posten norge", country="NO", reg="984661185"), 6: _org(6, "posten bring", country="NO"),
        # two forms under one number: waits
        7: _org(7, "tertiaire mixte", country="FR", reg="45107941200012", raw=["SARL Tertiaire Mixte"]),
        8: _org(8, "tertiaire mixte", country="FR", raw=["SAS Tertiaire Mixte"]),
        # a company: merged, with what agreed
        9: _org(9, "stedin netbeheer", reg="24289101", raw=["Stedin Netbeheer BV"]),
        10: _org(10, "stedin netbeheer b v"),
    }
    groups, refused = plan([_pair(1, 1, 2), _pair(2, 3, 4), _pair(3, 5, 6), _pair(4, 7, 8),
                            _pair(5, 9, 10)], orgs)
    assert refused == {"public_body": 2, "no_second_signal": 1, "different_legal_form": 1}
    assert [(g["head"], g["members"], g["confidence"]) for g in groups] == [(9, [10], 0.99)]
    assert groups[0]["candidates"][0]["method"] == "identifier+name+legal_form"


@pytest.mark.parametrize("name", [
    "gse ggmbh vertreten durch die vea beratungs-gmbh",
    "billebogen entwicklungsgesellschaft & co bbeg verteten durch",
    "agb boortmeerbeek bijgestaan door belfius bank",
    "stiftelsen antidoping norge c o inventura",
    "verdo varme a s pa vegne af verdo varme a s",
    "septalia maitrise d ouvrage deleguee pour vilogia",
    "obb- holding sowie die mit ihr im sinne des",
    "hlm des chalets et sccv le clos tolosan",
    "enel grids en nombre y cuenta de e-distribuzione",
])
def test_names_that_say_one_body_acts_for_another(name):
    assert ACTING_FOR.search(name)


def test_the_nordic_care_of_is_read_in_norway_and_denmark_only():
    orgs = {1: _org(1, "abakus", country="NO", reg="983335543", raw=["Abakus AS"]),
            2: _org(2, "innkjopssamarbeidet i nord-gudbrandsdalen v abakus", country="NO", raw=["x AS"]),
            3: _org(3, "nemocnice v praze", country="CZ", reg="00064220"),
            4: _org(4, "nemocnice v praze", country="CZ")}
    assert plan([_pair(1, 1, 2)], orgs)[1] == {"acting_for_another_body": 1}
    # the Czech 'v' is 'in'; the pair is refused, but as a hospital, not as an agent
    assert plan([_pair(2, 3, 4)], orgs)[1] == {"public_body": 1}


def test_the_command_line_takes_a_batch_size_a_sample_and_an_undo_window(monkeypatch):
    calls = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import dgate.ops.accept_merge_candidates as m
    monkeypatch.setattr(m.db, "connect", lambda *_a, **_k: Conn())
    monkeypatch.setattr(m, "settings", lambda: type("S", (), {"dsn": "x"})())
    monkeypatch.setattr(m, "run", lambda conn, **kw: calls.append(("run", kw)))
    monkeypatch.setattr(m, "undo_batch", lambda conn, *w, **kw: calls.append(("undo", w, kw)))
    main(["--yes", "--limit", "200", "--sample", "20", "--no-office-splits"])
    main(["--undo-batch", "2026-10-23 08:00:00+00", "2026-10-23 08:10:00+00"])
    assert calls[0] == ("run", {"apply": True, "limit": 200, "sample": 20, "with_office_splits": False})
    assert calls[1] == ("undo", ("2026-10-23 08:00:00+00", "2026-10-23 08:10:00+00"), {"apply": False})


@pytest.mark.parametrize("short,long_", [
    ("verdo", "verdo holding"), ("femern", "femern landanlaeg"),
    ("50hertz transmission", "50hertz transmission 50hertz offshore 50hertz connectors"),
    ("nordals fjernvarme", "sonderborg forsyningsservice a s nordals fjernvarme"),
    ("gas storage denmark", "energinet gas storage denmark"),
])
def test_a_sister_company_or_a_list_of_companies_is_not_a_long_form(short, long_):
    a, b = _org(1, short, country="DK", raw=["x A/S"]), _org(2, long_, country="DK", raw=["y A/S"])
    assert agreement(a, b) is None


def test_a_group_word_on_one_side_only_keeps_the_pair_waiting():
    orgs = {1: _org(1, "provas - haderslev forsyningsservice a s", country="DK", reg="32767966"),
            2: _org(2, "provas - haderslev forsyning a s", country="DK")}
    assert plan([_pair(1, 1, 2)], orgs)[1] == {"sister_company": 1}


def test_social_insurance_funds_are_public():
    assert is_public_body("раионна здравноосигурителна каса монтана", "BG")
    assert is_public_body("msa midi pyrenees sud", "FR")
    assert is_public_body("arbeitsmarktservice wien", "AT")
