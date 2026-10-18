"""WP-41: what a contribution means (N1 to N3) and which country an organisation is in (N4)."""

from __future__ import annotations

import pytest

from dgate import networks
from dgate.sources import cordis


def _role(role, amount):
    row = {"project": "1", "org": "o", "role": role}
    if amount is not None:
        row["amount"] = amount
    return cordis.role_record(row)


# ----------------------------------------------------------------- the role reader

def test_a_third_party_shown_at_zero_is_unknown_not_zero():
    r = _role("thirdParty", "0")
    assert r.contribution is None and r.note == "linked_third_party"


def test_a_third_party_with_an_amount_keeps_it():
    r = _role("thirdParty", "8325.63")
    assert r.contribution == 8325.63 and r.note is None


def test_a_role_with_no_payment_is_unknown_and_says_why():
    r = _role("participant", None)
    assert r.contribution is None and r.note == "no_payment_stated"


@pytest.mark.parametrize("role", ["associatedPartner", "partner", "internationalPartner", "participant"])
def test_a_stated_zero_of_any_other_role_stays_zero(role):
    r = _role(role, "0")
    assert r.contribution == 0 and r.note is None


# ----------------------------------------------------------------- the project rule

def test_two_hosts_each_paid_the_whole_grant_are_withheld():
    # FP7 ERC grant 109646: both coordinators carry the full 1,498,800 of a 1,498,800 project
    out = networks.settle_amounts([("coordinator", 1498800.0, None), ("coordinator", 1498800.0, None)], 1498800.0)
    assert out == [(None, "exceeds_project_total", 1498800.0)] * 2


def test_rounding_by_the_euro_is_not_an_excess():
    # project 88301: seven participants add up to 2,060,885 against 2,060,881
    members = [("participant", 294412.0, None) for _ in range(7)]
    total = sum(a for _, a, _ in members)
    out = networks.settle_amounts(members, total - 4)
    assert all(c is not None for c, _, _ in out)


def test_an_excess_beyond_the_rounding_withholds_every_positive_amount_but_not_a_zero():
    out = networks.settle_amounts([("coordinator", 100.0, None), ("participant", 80.0, None),
                                   ("associated_partner", 0.0, None), ("participant", None, "no_payment_stated")],
                                  150.0)
    assert out == [(None, "exceeds_project_total", 100.0), (None, "exceeds_project_total", 80.0),
                   (0.0, None, None), (None, "no_payment_stated", None)]


def test_an_excess_of_a_percent_or_two_is_an_amendment_not_a_misreading_and_more_is():
    members = [("participant", 1000.0, None) for _ in range(10)]             # 10,000 against a total of ...
    assert all(c is not None for c, _, _ in networks.settle_amounts(members, 9850.0))      # 1.5 per cent over
    assert all(n == "exceeds_project_total" for _, n, _ in networks.settle_amounts(members, 9700.0))    # 3 per cent over


def test_a_project_without_a_total_withholds_nothing():
    assert networks.settle_amounts([("coordinator", 5.0, None)], None) == [(5.0, None, None)]
    assert networks.settle_amounts([("coordinator", 5.0, None)], 0.0) == [(5.0, None, None)]


def test_a_participant_of_a_project_with_third_parties_is_marked_gross():
    # Universite de Lorraine (ERC 695618): the payment of 2,810,229 includes the 562,189 of CNRS, a linked third
    # party shown at 0; the CORDIS page prints the net, 2,248,040
    out = networks.settle_amounts([("coordinator", 2810229.0, None), ("third_party", None, "linked_third_party")],
                                  2810229.0)
    assert out == [(2810229.0, "gross_of_third_parties", None), (None, "linked_third_party", None)]


def test_an_associated_partner_is_not_marked_gross():
    out = networks.settle_amounts([("coordinator", 10.0, None), ("associated_partner", 0.0, None),
                                   ("third_party", None, "linked_third_party")], 10.0)
    assert out[1] == (0.0, None, None)


@pytest.mark.parametrize("members,fund", [
    ([("coordinator", 100.0, None), ("participant", 80.0, None)], 150.0),
    ([("coordinator", 100.0, None), ("third_party", None, "linked_third_party")], 100.0),
    ([("participant", None, "no_payment_stated"), ("participant", 3.0, None)], 3.0),
    ([("third_party", None, "linked_third_party")], None),
])
def test_settling_what_was_settled_changes_nothing(members, fund):
    first = networks.settle_amounts(members, fund)
    again = networks.settle_amounts(
        [(r, *networks.source_view(r, c, n, s)) for (r, _, _), (c, n, s) in zip(members, first, strict=True)], fund)
    assert again == first


@pytest.mark.parametrize("role,contribution,note,stated,expected", [
    ("third_party", 0.0, None, None, (None, "linked_third_party")),            # written by the first version
    ("participant", None, None, None, (None, "no_payment_stated")),
    ("participant", 5.0, "gross_of_third_parties", None, (5.0, None)),
    ("participant", None, "exceeds_project_total", 7.0, (7.0, None)),
    ("associated_partner", 0.0, None, None, (0.0, None)),
])
def test_the_source_view_of_a_stored_row(role, contribution, note, stated, expected):
    assert networks.source_view(role, contribution, note, stated) == expected


# ----------------------------------------------------------------- the country of an organisation

def test_csic_takes_the_country_its_site_name_and_vat_number_agree_on():
    # PIC 999991722 on 17 October 2026: address Trento IT, site "... CIENTIFICAS Madrid ES", VAT ESQ2818002D
    country, basis, seen = cordis.seat_country(
        ["IT"], ["AGENCIA ESTATAL CONSEJO SUPERIOR DE INVESTIGACIONES CIENTIFICAS Madrid ES"], ["ESQ2818002D"])
    assert (country, basis, seen) == ("ES", "vote", ("ES", "IT"))


def test_one_voice_against_the_address_changes_nothing():
    # CrowdHelix: address IE, VAT IE, site name "... London UK": the name alone does not overrule
    assert cordis.seat_country(["IE"], ["CROWDHELIX LIMITED London UK"], ["IE3602284DH"]) == ("IE", None, ())
    # the VAT number alone does not either (EurOcean's Dutch site with a Portuguese VAT number)
    assert cordis.seat_country(["NL"], ["STICHTING EUROCEAN S-GRAVENHAGE NL"], ["PT980405599"]) == ("NL", None, ())


def test_a_vat_prefix_that_is_not_a_country_is_not_a_signal():
    # a Mexican tax number starts with letters that happen to be a country code
    assert cordis.seat_country(["MX"], ["INFOTEC Mexico MX"], ["FID741230A22"]) == ("MX", None, ())
    assert cordis.seat_country(["KE"], [], ["PO51139812V"]) == ("KE", None, ())


def test_sites_in_two_countries_are_kept_as_several_and_nothing_is_guessed():
    # EurOcean: Lisboa PT and The Hague NL, two VAT numbers
    assert cordis.seat_country(["PT", "NL"], ["FUNDACAO EUROCEAN Lisboa PT", "STICHTING EUROCEAN HAGUE NL"],
                               ["PT980405599", "NL818784337B01"]) == ("NL", "several", ("NL", "PT"))


def test_uk_and_el_are_written_the_commission_way():
    assert cordis.seat_country(["UK"], [], []) == ("GB", None, ())
    assert cordis.seat_country(["EL"], ["X Athina EL"], ["EL123456789"]) == ("GR", None, ())


def test_no_site_no_country():
    assert cordis.seat_country([], ["x"], ["ES1234567"]) == (None, None, ())


def test_org_record_reads_the_grouped_fields_and_the_old_single_ones():
    rec = cordis.org_record({"key": "k", "pic": "999991722", "name": "AGENCIA ESTATAL CSIC", "vat": "ESQ2818002D",
                             "country": "IT", "countries": "IT", "site_names": "AGENCIA ESTATAL CSIC Madrid ES",
                             "vats": "ESQ2818002D"})
    assert (rec.country, rec.country_basis, rec.country_sites) == ("ES", "vote", ("ES", "IT"))
    old = cordis.org_record({"key": "k", "pic": "111111111", "name": "ACME", "country": "UK"})
    assert (old.country, old.country_basis) == ("GB", "address")      # WP-43: an undisputed address is a basis too


def test_the_organisation_query_asks_for_the_sites_and_the_vat_numbers_and_nothing_personal():
    q = cordis._query("organisations", "", 10)
    assert "GROUP_CONCAT" in q and "e:Organisation ." in q and "e:name ?sn" in q
    for banned in ("email", "phone", "contact", "person"):
        assert banned not in q.lower()


@pytest.mark.parametrize("kind", ["organisations", "projects", "roles"])
def test_no_select_expression_reads_a_variable_an_earlier_one_has_renamed(kind):
    """The live service answered HTTP 500 to `(MIN(?vat) AS ?vat) ... (GROUP_CONCAT(?vat) AS ?vats)`: once an
    expression is projected under a name, later expressions of the same SELECT see that name, not the
    grouped variable. The stand-in service cannot tell, so the rule is checked on the text."""
    import re

    q = cordis._query(kind, "", 10)
    select = q[q.index("SELECT"):q.index("WHERE")]
    exprs = re.findall(r"\((.*?) AS \?(\w+)\)", select, flags=re.S)
    for i, (_, alias) in enumerate(exprs):
        for body, _ in exprs[i + 1:]:
            assert not re.search(rf"\?{alias}\b", body), (kind, alias, body)
