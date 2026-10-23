"""WP-23: the confidence level of a listed notice (dgate/confidence.py), derived from the
stored signals. One test per combination of the table in docs/design/CONFIDENCE.md."""

from __future__ import annotations

import itertools

import pytest

from dgate.confidence import (
    CONFIDENCE_SQL,
    DEFENCE_BUYER,
    DIRECTIVE,
    HIGH,
    LEVELS,
    LOW,
    MEDIUM,
    MILITARY_CODE,
    MILITARY_NOT_MAIN,
    NOT_LISTED,
    confidence,
    confidence_of_row,
    label,
    main_is_military,
)

CLASSES = (None, "defence", "other", "security", "municipal", "health", "education",
           "fire_rescue", "infrastructure", "international")


def level(**kw):
    return confidence(**{"legal_basis": False, "military_cpv": False, "buyer": False, **kw})[0]


# ------------------------------------------------------------------------------- high

@pytest.mark.parametrize("legal_basis", [True, False])
@pytest.mark.parametrize("linked", [True, False])
@pytest.mark.parametrize("cls", [None, "defence", "other", "education"])
def test_a_military_code_and_a_listed_defence_buyer_is_high(legal_basis, linked, cls):
    lv, basis = confidence(legal_basis=legal_basis, military_cpv=True, buyer=True,
                           linked_defence=linked, buyer_class=cls)
    assert lv == HIGH
    assert MILITARY_CODE in basis and DEFENCE_BUYER in basis
    assert (DIRECTIVE in basis) is legal_basis


# ----------------------------------------------------------------------------- medium

def test_a_listed_buyer_without_a_military_code_is_medium():
    lv, basis = confidence(legal_basis=False, military_cpv=False, buyer=True, buyer_class="defence")
    assert lv == MEDIUM
    assert basis == [DEFENCE_BUYER, "No military product code in the notice"]


def test_the_directive_and_a_listed_buyer_is_high_and_names_the_directive():
    # WP-95 (persona p10: a ministry's pyrotechnics under 2009/81/EC with a chemical code were "Probably defence", as refuse
    # collection was): the directive used by a listed defence buyer is high now (it was medium)
    lv, basis = confidence(legal_basis=True, military_cpv=False, buyer=True)
    assert lv == HIGH and basis[0] == DIRECTIVE and DEFENCE_BUYER in basis


@pytest.mark.parametrize("cls", [None, "defence", "other"])
def test_the_directive_and_a_main_military_code_from_an_unlisted_defence_or_unknown_body_is_high(cls):
    # WP-95: a military main code with the directive beside it is high (it was medium)
    lv, basis = confidence(legal_basis=True, military_cpv=True, buyer=False, buyer_class=cls)
    assert lv == HIGH
    assert basis == [DIRECTIVE, MILITARY_CODE, NOT_LISTED]


@pytest.mark.parametrize("cls", [None, "defence", "other"])
def test_the_directive_and_a_military_code_that_is_not_the_main_code_is_medium(cls):
    lv, basis = confidence(legal_basis=True, military_cpv=True, buyer=False, buyer_class=cls, main_military=False)
    assert lv == MEDIUM
    assert basis == [DIRECTIVE, MILITARY_NOT_MAIN, NOT_LISTED]


def test_a_listed_buyer_with_a_military_code_that_is_not_the_main_code_is_medium():
    """WP-95, /tenders/396812: a gatehouse renovation at a naval air base, a long list of repair codes with one military
    vehicle code, was "Clearly defence"."""
    lv, basis = confidence(legal_basis=False, military_cpv=True, buyer=True, buyer_class="defence", main_military=False)
    assert lv == MEDIUM
    assert basis == [MILITARY_NOT_MAIN, DEFENCE_BUYER]
    assert label(lv, buyer=True, military_cpv=True) == "Defence buyer, some military codes"


@pytest.mark.parametrize("cls", ["security", "municipal", "health", "education", "fire_rescue",
                                 "infrastructure", "international"])
def test_the_directive_and_a_military_code_from_a_civil_or_security_body_is_low(cls):
    assert level(legal_basis=True, military_cpv=True, buyer_class=cls) == LOW


# -------------------------------------------------------------------------------- low

def test_a_military_code_alone_is_low():
    lv, basis = confidence(legal_basis=False, military_cpv=True, buyer=False, buyer_class="other")
    assert lv == LOW
    assert basis == ["Military product code only", NOT_LISTED]


def test_the_directive_alone_from_a_civil_buyer_is_low_and_says_so():
    lv, basis = confidence(legal_basis=True, military_cpv=False, buyer=False, buyer_class="municipal")
    assert lv == LOW
    assert basis == ["Defence directive (2009/81/EC) only", NOT_LISTED, "Buyer is a municipal body"]


def test_a_military_code_from_a_security_body_is_low_and_says_so():
    lv, basis = confidence(legal_basis=False, military_cpv=True, buyer=False, buyer_class="security")
    assert lv == LOW
    assert basis[-1] == "Buyer is a police, prison, border, customs or tax body"


def test_a_notice_listed_only_for_its_link_to_a_defence_notice_is_low():
    lv, basis = confidence(legal_basis=False, military_cpv=False, buyer=False,
                           linked_defence=True, buyer_class="municipal")
    assert lv == LOW
    assert basis[0] == "Same procurement as a defence notice of another source"


def test_a_demoted_military_code_is_named_as_bought_by_a_civil_body():
    lv, basis = confidence(legal_basis=False, military_cpv=True, buyer=False,
                           linked_defence=True, dual_use=True, buyer_class="municipal")
    assert lv == LOW
    assert "Military product code, bought by a civil body" in basis


def test_the_directive_with_a_link_and_a_defence_class_is_low_but_says_the_body_looks_defence():
    lv, basis = confidence(legal_basis=True, military_cpv=False, buyer=False,
                           linked_defence=True, buyer_class="defence")
    assert lv == LOW
    assert "Buyer looks like a defence body but is not on the defence list" in basis


# --------------------------------------------------------------------- all combinations

@pytest.mark.parametrize("lb, cpv, buy, lnk, du", list(itertools.product([False, True], repeat=5)))
def test_every_combination_has_one_level_and_a_reason(lb, cpv, buy, lnk, du):
    for cls in CLASSES:
        lv, basis = confidence(legal_basis=lb, military_cpv=cpv, buyer=buy, linked_defence=lnk,
                               dual_use=du, buyer_class=cls)
        assert lv in LEVELS and basis and all(isinstance(b, str) and b for b in basis)
        # the rule in one line each (WP-95: high is a main military code with a listed buyer or the directive from a
        # body not of a civil or security class, or the directive used by a listed buyer; a main code here, as the
        # default of a caller that does not know)
        corroborated = buy or (lb and cls in (None, "defence", "other"))
        if not du and ((cpv and corroborated) or (lb and buy)):
            assert lv == HIGH
        elif buy:
            assert lv == MEDIUM
        elif lb and cpv and cls in (None, "defence", "other"):
            assert lv == MEDIUM
        else:
            assert lv == LOW


def test_the_row_helper_reads_the_stored_columns():
    got = confidence_of_row({"sig_legal_basis": True, "sig_cpv_military": True, "sig_buyer": True,
                             "sig_linked_defence": None, "dual_use": False, "buyer_class": "defence",
                             "cpv_codes": ["35300000", "45000000"]})
    assert got == {"level": HIGH, "basis": [DIRECTIVE, MILITARY_CODE, DEFENCE_BUYER], "label": "Clearly defence"}
    assert confidence_of_row({})["level"] == LOW
    assert confidence_of_row({})["label"] == "Weak defence signal"


def test_the_row_helper_reads_the_main_code_from_the_first_cpv_code():
    """WP-95: the gatehouse (/tenders/396812): a defence buyer, repair codes first, a military vehicle code later."""
    row = {"sig_cpv_military": True, "sig_buyer": True, "buyer_class": "defence",
           "cpv_codes": ["45453000", "50000000", "50630000"]}
    assert confidence_of_row(row)["level"] == MEDIUM
    assert confidence_of_row({**row, "cpv_codes": ["50630000", "45453000"]})["level"] == HIGH
    assert main_is_military(["35811300"]) and not main_is_military(["35811200"]) and not main_is_military([])


@pytest.mark.parametrize("lv, buy, cpv, want", [
    (HIGH, True, True, "Clearly defence"),
    (MEDIUM, True, False, "Defence buyer, ordinary purchase"),
    (MEDIUM, True, True, "Defence buyer, some military codes"),
    (MEDIUM, False, True, "Defence directive, unlisted buyer"),
    (LOW, False, True, "Weak defence signal"),
])
def test_each_level_is_named_by_what_it_rests_on_never_by_a_probability(lv, buy, cpv, want):
    """WP-95: "Probably defence" stood on refuse collection, bed linen and air conditioning (84 % of the list)."""
    got = label(lv, buyer=buy, military_cpv=cpv)
    assert got == want and "robabl" not in got and "ossibl" not in got


def test_the_three_sql_levels_are_distinct_and_cover_the_levels():
    assert set(CONFIDENCE_SQL) == set(LEVELS)
    assert len(set(CONFIDENCE_SQL.values())) == 3
