"""WP-104 (persona round of 24 October 2026): entities, the pure parts. Buyer families (the twin rule that put the Polish
Ministry of National Defence under its cyberspace centre, Italian, Dutch, German and Portuguese variants), supplier
merges under the owner's rule (other numbers, other companies; a merge needs a shared number or one name), keys."""

from __future__ import annotations

from dgate.buyer_family import family_of
from dgate.normalise import normalise_org_name
from dgate.ops.buyer_families import Member, groups_of, twin_groups
from dgate.ops.company_groups import group_of
from dgate.ops.supplier_dedupe import Row, core_key, group_country, plan
from dgate.resolution.names import key_of, legal_form_of


def fam(country, name):
    return family_of(country, normalise_org_name(name))


# ------------------------------------------------------------------ 1. the twin rule (/buyers/9770)

def test_a_buyer_whose_copies_mostly_are_its_own_ted_notices_stays_itself():
    mon, czc, other, copy = 13000, 9770, 30, 31
    buyers = {i: Member(i, f"b{i}", n, "x", 0.9) for i, n in ((mon, 990), (czc, 2000), (other, 5), (copy, 4))}
    # the ministry: 107 national copies of its own TED notices, 28 of TED notices the centre published
    pairs = [(mon, mon)] * 107 + [(mon, czc)] * 28
    # a national-language row: three copies of TED notices of `other`, one of its own
    pairs += [(copy, other)] * 3 + [(copy, copy)]
    added = twin_groups([], pairs, buyers)
    assert [(g.head.org_id, [m.org_id for m in g.members]) for g in added] == [(other, [copy])]
    # a half is not a majority
    assert twin_groups([], [(copy, other), (copy, copy)], buyers) == []


# ------------------------------------------------------------------ 2. buyer families

def test_the_three_italian_armament_directorates_are_one_buyer_each():
    terr = {fam("IT", n).key for n in (
        "Ministero della Difesa - SGD-DNA - Direzione degli Armamenti Terrestri",
        "Ministero della Difesa Segretariato Generale e Direzione Nazionale degli Armamenti Direzione degli Armamenti Terrestri",
        "Direzione Armamenti Terrestri - TERRARM", "Min. Difesa Direzione Armamenti Terrestri 9 Divisione")}
    aero = {fam("IT", n).key for n in (
        "Ministero della Difesa SGD DNA Direzione degli Armamenti Aeronautici e per l'Aeronavigabilita",
        "Ministero della Difesa - Segretariato Generale della Difesa DNA - Direzione degli Armamenti Aeronautici e per",
        "Direzione degli Armamenti Aeronautici e per l'Aeronavigabilita - ARMAEREO")}
    nav = {fam("IT", n).key for n in ("NAVARM", "Direzione degli Armamenti Navali - NAVARM",
                                      "Ministero della Difesa Direzione degli Armamenti Navali")}
    assert terr == {"IT:rule:it_terrarm"} and aero == {"IT:rule:it_armaereo"} and nav == {"IT:rule:it_navarm"}
    assert fam("IT", "Ministero della Difesa - Direzione Informatica Telematica e Tecnologie Avanzate").key.startswith(
        "IT:ministero")                                           # TELEDIFE is another directorate


def test_dutch_ministry_english_variants_join_the_ministry():
    keys = {fam("NL", n).key for n in (
        "Netherlands Ministry of Defence", "Dutch Ministry of Defence", "The Netherlands Ministry of Defence(MoDNL)",
        "The Netherlands Ministery of Defence", "Ministery van Defence", "NLD Ministry of Defence", "NL Ministry of Defence",
        "Royal Netherlands Air Force, Logistic Centre Woensdrecht", "Royal Netherlands Navy")}
    assert keys == {"NL:rule:nl_defensie"}
    assert fam("NL", "Department of Defense").key != "NL:rule:nl_defensie"     # whose? left alone


def test_german_office_variants_and_represented_offices_are_one_buyer():
    baainbw = {fam("DE", n).key for n in (
        "Bundesamt für Ausrüstung, Informationstechnik und Nutzung der Bundeswehr",
        "Bundesamt für Bundesamt für Ausrüstung, Informationstechnik und Nutzung der Bundeswehr",
        "Bundesamt für Informationstechnik, Ausrüstung und Nutzung der Bundeswehr",
        "Bundesrepublik Deutschland, vertreten durch das Bundesamt für Ausrüstung, Informationstechnik und Nutzung der "
        "Bundeswehr")}
    assert baainbw == {"DE:rule:baainbw"}
    hall = fam("DE", "Staatliches Hochbauamt Schwäbisch Hall").key
    assert fam("DE", "Bundesrepublik Deutschland, vertreten durch das BMVg, dieses vertreten durch das Staatliche "
                     "Hochbauamt Schwäbisch Hall").key == hall
    assert fam("DE", "Staatl. Hochbauamt Schwäbisch Hall").key == hall
    assert fam("DE", "Land Niedersachsen vertreten durch das Staatliche Baumanagement Niedersachsen").key == fam(
        "DE", "Bundesrepublik Deutschland vertreten durch das Staatliche Baumanagement Niedersachsen").key
    # nothing after the last "vertreten durch": the name stays whole
    cut = "Bundesanstalt für Immobilienaufgaben (BImA), diese vertreten durch die"
    assert fam("DE", cut).key == "DE:" + normalise_org_name(cut)


def test_a_family_of_spellings_is_headed_by_its_plain_name():
    rows = [(1, "DE", normalise_org_name("Bundesrepublik Deutschland, vertreten durch das BMVg, dieses vertreten durch das "
                                         "Staatliche Hochbauamt Ulm"), 121, None),
            (2, "DE", normalise_org_name("Staatliches Hochbauamt Ulm"), 87, None),
            (3, "DE", normalise_org_name("Staatl. Hochbauamt Ulm"), 54, None),
            (4, "PL", normalise_org_name("Akademia Wojsk Lądowych imienia generała Tadeusza Kościuszki"), 2, None),
            (5, "PL", normalise_org_name("Akademia Wojsk Lądowych"), 357, None)]
    got = {g.head.org_id: sorted(m.org_id for m in g.members) for g in groups_of(rows)}
    assert got == {2: [1, 3], 5: [4]}


def test_portuguese_army_and_air_force_units_are_one_buyer_each():
    army = {fam("PT", n).key for n in ("Estado-Maior do Exército", "Estado-Maior do Exército - Repartição de Concursos e "
                                       "Contratos", "MDN - Exército Português - Comando Logística",
                                       "Estado Português - Ministério da Defesa Nacional - Exército Português")}
    air = {fam("PT", n).key for n in ("Estado Maior da Força Aérea", "Ministério da Defesa Nacional, Força Aérea, DAT",
                                      "Força Aérea, Direção de Abastecimento e Transportes", "Força Aérea Portuguesa")}
    assert army == {"PT:rule:pt_exercito"} and air == {"PT:rule:pt_forca_aerea"}
    assert fam("PT", "Ministério da Defesa Nacional - Marinha").key not in army | air


# ------------------------------------------------------------------ 3. supplier merges

def row(i, name, country="DE", numbers=(), awards=1, public=False, stated=None):
    return Row(i, country, name, set(numbers), {legal_form_of(name)} - {None}, awards, public, stated or {})


def members(groups):
    return {g["head"]: sorted((m, method) for m, method, _ in g["members"]) for g in groups}


def test_a_conflicting_row_no_longer_keeps_a_shared_number_apart():
    rows = [row(1, "Heckler Koch GmbH", numbers={"481250", "N0047964B"}, awards=27),
            row(2, "Heckler und Koch", numbers={"232899163", "N0047964B"}, awards=9),
            row(3, "HECKLER & KOCH GMBH", numbers={"N0047964B"}, awards=8),
            row(4, "Heckler and Koch GmbH", numbers={"000N0047964BN0047964B", "N0047964B"}, awards=4),
            row(5, "HECKLER  AND  KOCH GMBH.", numbers={"0000CGC00430"}, awards=5)]       # another number: another
    groups, left, _ = plan(rows)
    assert members(groups) == {1: [(2, "company_number"), (3, "company_number"), (4, "company_number")]}
    assert left["different_company_numbers"] == 1


def test_a_row_without_a_number_between_two_numbers_joins_neither():
    rows = [row(9, "Rheinmetall Electronics GmbH", numbers={"811127845"}, awards=32),
            row(10, "Rheinmetall Electronics GmbH", numbers={"119356818"}, awards=4),
            row(11, "Rheinmetall Electronics GmbH", numbers={"251121155"}),
            row(12, "Rheinmetall Electronics GmbH")]
    groups, left, _ = plan(rows)
    assert groups == [] and left == {"different_company_numbers": 1}


def test_one_number_in_two_countries_is_one_company_where_a_country_is_decided():
    rows = [row(1, "pilatus aircraft ltd", "CH", {"N034121H", "15030004652"}, 16),
            row(2, "PILATUS AIRCRAFT LIMITED", "BG", {"15030004652"}, 3),
            row(3, "PILATUS Constructions Aéronautiques SA", "CH", awards=1),           # no number, another form
            row(4, "MSM EXPORT s.r.o.", "LV", {"48006122"}, 2), row(5, "MSM EXPORT, s.r.o.", "SK", {"48006122"}, 1),
            row(6, "VAPENSMIA AS", "NO", {"928003965"}), row(7, "VAPENSMIA AS", "ES", {"928003965"}),
            row(8, "Vapensmia Holding AS", "SE", {"928003965"})]                    # another name: never across
    groups, _, _ = plan(rows)
    got = {g["head"]: (g["country"], g["recountry"], [m for m, _, _ in g["members"]]) for g in groups}
    assert got == {1: ("CH", [2], [2]), 5: ("SK", [4], [4])}     # the s.r.o. is Slovak; the AS tie decides nothing
    assert group_country(rows[5:7]) is None


def test_divisions_typos_and_the_state_company_mark_are_the_company():
    leo = row(1, "LEONARDO - SOCIETA PER AZIONI", "IT", {"00401990585", "00881841001"}, 25)
    rows = [leo, row(2, "Leonardo, Societá per Azione", "IT", {"00881841001"}, 2),
            row(3, "Leonardo S.p.A. – Aircraft Division", "IT", {"00881841001"}),
            row(4, "Leonardo S.p.A. Divisione Sistemi di Difesa", "IT", {"00881841001"}),
            row(5, "SOCIETA LEONARDO S.P.A.", "IT"),
            row(6, "Leonardo Spa_149684", "IT", {"0006001333"}),                    # another number: another
            row(7, "Leonardo Electronics Ltd", "GB", {"00401990585"}),               # another country, another key
            row(10, "NAVANTIA SA, SME", "ES", {"A84076397"}, 204), row(11, "NAVANTIA S.A.", "ES", {"A84076397"}, 54),
            row(12, "NAVANTIA SISTEMAS", "ES", {"A84076397"}, 2)]                    # a name, not a division
    groups, _, _ = plan(rows)
    assert members(groups) == {1: [(2, "company_number"), (3, "company_number_division"),
                                   (4, "company_number_division"), (5, "name_key")],
                               10: [(11, "company_number")]}


def test_keys_of_the_state_company_mark_and_the_misspelt_form():
    assert key_of("NAVANTIA SA, SME")[0] == key_of("NAVANTIA S.A., S.M.E.")[0] == key_of("NAVANTIA S.A.")[0] == "navantia"
    assert key_of("Leonardo, Societá per Azione")[0] == "leonardo" and legal_form_of("Leonardo, Societa per Azione") == "spa"
    assert core_key("SOCIETA LEONARDO S.P.A.") == "leonardo" and core_key("Societa Generale") == "societa generale"


def test_the_leonardo_group_takes_pzl_swidnik_and_belgium():
    assert group_of("LEONARDO PZL-ŚWIDNIK S.A.", "PL")[0].key == "leonardo"
    assert group_of("PZL-Świdnik S.A.", "PL")[0].key == "leonardo"
    assert group_of("Leonardo Belgium S.A.", "BE")[0].key == "leonardo"
    assert group_of("Leonardo Spa_149684", "IT")[0].key == "leonardo"
