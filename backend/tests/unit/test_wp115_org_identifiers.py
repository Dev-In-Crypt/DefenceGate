"""WP-115: register checks for PL and ES identifiers, contact blocks in names, the buyer as its own winner, and the
plan of `ops.org_repair` for rows split by a false identifier."""

import pytest

from dgate.awards import same_name_as_buyer
from dgate.normalise import normalise_identifier, normalise_org_name, strip_name_contacts
from dgate.ops.org_repair import _shape, plan_false_ids


@pytest.mark.parametrize("raw,expected", [
    ("5732299604", "5732299604"),              # NIP, check digit right
    ("NIP 573-229-96-04", "5732299604"),
    ("PL5732299604", "5732299604"),
    ("5732299605", None),                      # NIP, check digit wrong
    ("123456785", "123456785"),                # REGON 9
    ("12345678512347", "12345678512347"),      # REGON 14
    ("KRS 0000012345", "0000012345"),
    ("44051401359", None),                     # 11 digits: a PESEL, a person's number
    ("DEZ/26/019/2020", None),                 # a case reference (znak sprawy)
    ("WSZS/DEZ/26/035/2021", None),
    ("ZP.271.2.2021", None),
])
def test_polish_register_numbers(raw, expected):
    assert normalise_identifier(raw, "PL") == expected


@pytest.mark.parametrize("raw,expected", [
    ("A28015865", "A28015865"),                # CIF, check digit
    ("Q2817017C", "Q2817017C"),                # CIF, check letter
    ("ESA28015865", "A28015865"),              # VAT form
    ("NIF: A-28015865", "A28015865"),
    ("12345678Z", "12345678Z"),                # DNI
    ("X1234567L", "X1234567L"),                # NIE
    ("B12345678", None),                       # CIF shape, wrong check
    ("12345678A", None),                       # DNI shape, wrong letter
    ("10000140000201", None),                  # a platform code, no NIF
    ("2023S212669311", None),
])
def test_spanish_register_numbers(raw, expected):
    assert normalise_identifier(raw, "ES") == expected


def test_other_countries_unchanged():
    assert normalise_identifier("DE 139 601 469", "DE") == "139601469"
    assert normalise_identifier("DEZ/26/019/2020", "DE") == "DEZ260192020"


def test_contact_block_cut_from_names():
    name = "Stadt X, Musterstr. 1, 12345 X, Tel. 0221 123456, Fax 0221 1, E-Mail: a@b.de"
    assert strip_name_contacts(name) == "Stadt X, Musterstr. 1, 12345 X"
    assert strip_name_contacts("Tel Aviv University") == "Tel Aviv University"
    assert strip_name_contacts("Hotel Polonia 2") == "Hotel Polonia 2"
    assert strip_name_contacts("someone@example.org") == ""
    assert strip_name_contacts("Amt X +49 30 1234567") == "Amt X"
    assert normalise_org_name("Amt X Tel: +49 30 1234567") == "amt x"
    # the stored, folded form is cut the same way
    assert normalise_org_name("amt x musterstr 1 12345 x tel 0221 123456 fax 0221 1") == "amt x musterstr 1 12345 x"


def test_winner_named_as_the_buyer():
    assert same_name_as_buyer("Het Ministerie van Defensie", "Ministerie van Defensie")
    assert not same_name_as_buyer("Defensie Materieel Organisatie BV", "Ministerie van Defensie")
    assert not same_name_as_buyer("", "Ministerie van Defensie")


def _org(i, reg, name="szpital x", country="PL"):
    return {"id": i, "country": country, "canonical_name": name, "national_reg_no": reg}


def test_plan_rejoins_rows_split_by_case_numbers():
    rows = [_org(1, "5732299604"), _org(2, "DEZ260192020"), _org(3, "WSZSDEZ260352021")]
    groups, respell = plan_false_ids(rows, {("PL", "szpital x"): rows + [_org(4, None)]})
    assert respell == []
    (g,) = groups
    assert (g["decision"], g["target"], g["merge"], g["clear"]) == ("rejoin", 1, [2, 3], [2, 3])
    assert set(g["shapes"]) == {"AAA999999999", "AAAAAAA999999999"}       # a shape, never the number


def test_plan_without_a_valid_number_joins_the_row_without_one():
    rows = [_org(5, "DEZ260192020"), _org(6, "DAZ260672018")]
    (g,), _ = plan_false_ids(rows, {("PL", "szpital x"): rows + [_org(9, None)]})
    assert (g["target"], g["merge"]) == (9, [5, 6])


def test_plan_holds_a_group_with_two_numbers_of_one_register():
    rows = [_org(1, "5732299604"), _org(2, "1234563218"), _org(3, "DEZ260192020")]
    (g,), _ = plan_false_ids(rows, {("PL", "szpital x"): rows})
    assert (g["decision"], g["merge"], g["clear"]) == ("held_two_numbers", [], [3])


def test_plan_a_nip_beside_a_regon_is_not_two_bodies():
    rows = [_org(1, "5732299604"), _org(2, "123456785"), _org(3, "DEZ260192020")]
    (g,), _ = plan_false_ids(rows, {("PL", "szpital x"): rows})
    assert (g["decision"], g["target"], g["merge"]) == ("rejoin", 1, [3])


def test_plan_respells_a_vat_form():
    rows = [_org(1, "ESA28015865", "empresa", "ES")]
    groups, respell = plan_false_ids(rows, {})
    assert groups == [] and respell == [(1, "ESA28015865", "A28015865")]


def test_shape_hides_digits():
    assert _shape("DEZ260192020") == "AAA999999999"
