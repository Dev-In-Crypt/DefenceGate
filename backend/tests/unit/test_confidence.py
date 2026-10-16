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
    NOT_LISTED,
    confidence,
    confidence_of_row,
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


def test_the_directive_and_a_listed_buyer_is_medium_and_names_the_directive():
    lv, basis = confidence(legal_basis=True, military_cpv=False, buyer=True)
    assert lv == MEDIUM and basis[0] == DIRECTIVE and DEFENCE_BUYER in basis


@pytest.mark.parametrize("cls", [None, "defence", "other"])
def test_the_directive_and_a_military_code_from_an_unlisted_defence_or_unknown_body_is_medium(cls):
    lv, basis = confidence(legal_basis=True, military_cpv=True, buyer=False, buyer_class=cls)
    assert lv == MEDIUM
    assert basis == [DIRECTIVE, MILITARY_CODE, NOT_LISTED]


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
        # the rule in one line each
        if cpv and buy:
            assert lv == HIGH
        elif buy:
            assert lv == MEDIUM
        elif lb and cpv and cls in (None, "defence", "other"):
            assert lv == MEDIUM
        else:
            assert lv == LOW


def test_the_row_helper_reads_the_stored_columns():
    got = confidence_of_row({"sig_legal_basis": True, "sig_cpv_military": True, "sig_buyer": True,
                             "sig_linked_defence": None, "dual_use": False, "buyer_class": "defence"})
    assert got == {"level": HIGH, "basis": [DIRECTIVE, MILITARY_CODE, DEFENCE_BUYER]}
    assert confidence_of_row({})["level"] == LOW


def test_the_three_sql_levels_are_distinct_and_cover_the_levels():
    assert set(CONFIDENCE_SQL) == set(LEVELS)
    assert len(set(CONFIDENCE_SQL.values())) == 3
