"""WP-111 (round-4 re-check of 24 October 2026, p02, p03, p04, p06, p07, p08, p10): buyer families, supplier evidence."""

from __future__ import annotations

from dgate.buyer_family import family_key, family_of
from dgate.ops.supplier_dedupe import Row, core_key, plan
from dgate.resolution.names import legal_form_of
from dgate.supplier_identity import own_number


def test_the_dutch_national_police_is_one_buyer_and_a_regional_force_is_not():
    assert family_key("NL", "politie") == family_key("NL", "politie nederland")
    assert family_of("NL", "politie nederland").method == "rule:nl_politie"
    assert family_key("NL", "politieregio zaanstreek waterland") != family_key("NL", "politie")
    assert family_key("NL", "politieacademie") != family_key("NL", "politie")
    assert family_key("BE", "politie") != family_key("NL", "politie")          # a Belgian police zone is not it


def test_agenzia_industrie_difesa_with_and_without_the_ministry_is_one_buyer():
    names = ("agenzia industrie difesa", "agenzia industrie difesa aid", "aid agenzia industrie difesa",
             "ministero della difesa agenzia industrie difesa", "ministero della difesa - agenzia industrie difesa",
             "ministero della difesa - agenzia industrie difesa - direzione generale")
    assert len({family_key("IT", n) for n in names}) == 1
    assert family_key("IT", "ministero della difesa direzione degli armamenti navali") != family_key("IT", names[0])


def test_the_european_space_agency_is_one_buyer_across_its_seats_but_not_euspa_or_a_prime():
    seats = [("NL", "european space agency"), ("NL", "european space agency esa"), ("NL", "european space agency estec"),
             ("FR", "european space agency"), ("FR", "agence spatiale europeenne"), ("DE", "european space agency esoc"),
             ("IT", "european space agency - esrin")]
    assert len({family_key(c, n) for c, n in seats}) == 1
    assert family_of("DE", "european space agency esoc").method == "rule:esa"
    assert family_key("CZ", "european space agency for the space programme") != family_key("NL", "european space agency")
    prime = "european space agency contract to be awarded by ohb prime contractor and not directly by esa contracting authority"
    assert family_key("NL", prime) != family_key("NL", "european space agency")
    # no other body crosses a border
    assert family_key("BE", "ministere de la defense") != family_key("FR", "ministere de la defense")


def test_a_buyers_code_or_a_number_of_no_shape_is_not_a_company_number():
    assert own_number("DE0000CGC00430", "DE") is None             # a Spanish defence buyer's code for Heckler & Koch
    assert own_number("IL0000CGC62412", "ES") is None
    assert own_number("0006001333", "IT") is None                  # passes the check digit padded, office 133 does not exist
    assert own_number("401990585", "IT") == "00401990585"         # Leonardo without its leading zeros
    assert own_number("00881841001", "IT") == "00881841001"
    assert own_number("0898937602", "GB") is None                  # neither a Companies House nor a VAT number
    assert own_number("02426132", "GB") == "02426132" and own_number("2426132", "GB") == "02426132"
    assert own_number("849774658", "GB") == "849774658"
    assert own_number("DE811127845", "DE") == "811127845"          # other countries as before


def test_the_name_key_reads_and_as_the_ampersand_and_drops_the_etenders_reference():
    assert core_key("HECKLER  AND  KOCH GMBH.") == core_key("Heckler & Koch GmbH") == "heckler koch"
    assert core_key("Wescom signal and rescue Germany GMBH") == core_key("WesCom Signal & Rescue Germany GmbH")


def test_a_name_with_the_etenders_reference_and_no_number_of_its_own_is_the_company():
    leo = row(1, "LEONARDO - SOCIETA PER AZIONI", "IT", {"00401990585", "00881841001"}, 25)
    bare = row(2, "Leonardo Spa_149684", "IT", {own_number("0006001333", "IT")} - {None})
    groups, _, _ = plan([leo, bare])
    assert [(g["head"], g["members"]) for g in groups] == [(1, [(2, "name_key_portal_suffix", 0.90)])]
    # holding a number of its own it stays apart (WP-104)
    assert plan([leo, row(2, "Leonardo Spa_149684", "IT", {"0006001333"})])[0] == []


def row(i, name, country="DE", numbers=(), awards=1):
    return Row(i, country, name, set(numbers), {legal_form_of(name)} - {None}, awards, False, {}, set(numbers))


def test_heckler_and_koch_joins_and_rheinmetall_electronics_stays_three_companies_with_the_reason_listed():
    rows = [row(1, "Heckler Koch GmbH", numbers={"481250"}, awards=28), row(2, "HECKLER  AND  KOCH GMBH.", awards=5),
            row(3, "RHEINMETALL ELECTRONICS GMBH", numbers={"811127845"}, awards=32),
            row(4, "Rheinmetall Electronics GmbH", numbers={"119356818"}, awards=4),
            row(5, "Rheinmetall Electronics GmbH", numbers={"251121155"})]
    apart: list[str] = []
    groups, left, _ = plan(rows, apart)
    assert [(g["head"], [m[:2] for m in g["members"]]) for g in groups] == [(1, [(2, "name_key")])]
    assert left == {"different_company_numbers": 1}
    assert len(apart) == 1 and "different_company_numbers" in apart[0]
    assert all(n in apart[0] for n in ("811127845", "119356818", "251121155"))


def test_leonardo_uk_rows_join_when_one_holds_no_company_number():
    rows = [row(1, "LEONARDO UK LTD", "GB", numbers={"02426132", "849774658"}, awards=4),
            row(2, "LEONARDO UK LTD", "GB", numbers={own_number("0898937602", "GB")} - {None})]
    groups, _, _ = plan(rows)
    assert [(g["head"], [m[0] for m in g["members"]]) for g in groups] == [(1, [2])]
    # with a real second number, two companies, as the owner's rule says
    rows[1] = row(2, "LEONARDO UK LTD", "GB", numbers={"04536271"})
    assert plan(rows)[0] == []
