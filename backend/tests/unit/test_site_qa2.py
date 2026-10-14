"""Site QA round 2, package WP-7: the pure parts."""

from __future__ import annotations

from dgate.classify import military_cpv_codes
from dgate.stats import month_gaps
from dgate.tenders import _qualified_by, clean_buyer_name


def test_the_military_codes_of_a_notice_are_those_classify_reads_as_military():
    codes = ["39162100", "35811300", "35811100", "35821000", "75221000", "35400000", "35400000"]
    assert military_cpv_codes(codes) == ["35811300", "75221000", "35400000"]
    assert military_cpv_codes(None) == []


def test_a_legal_basis_or_a_military_code_qualifies_a_notice_and_the_codes_are_named():
    row = {"sig_legal_basis": True, "sig_cpv_military": True, "legal_basis": "32009L0081"}
    assert _qualified_by(row, ["35400000", "33100000"]) == (["legal_basis", "military_cpv"], ["35400000"])
    row = {"sig_legal_basis": False, "sig_cpv_military": True, "buyer_class": "defence"}
    assert _qualified_by(row, ["35400000"]) == (["military_cpv"], ["35400000"])


def test_a_military_code_that_only_the_buyer_keeps_in_the_scope_is_not_called_a_product_code():
    # without its buyer a municipality's military code would be demoted as dual-use
    row = {"sig_legal_basis": False, "sig_cpv_military": True, "sig_buyer": True,
           "legal_basis": "32014L0024", "buyer_class": "municipal"}
    assert _qualified_by(row, ["35811300", "39162100"]) == (["buyer"], [])
    # a buyer that is on the list and has no military code at all
    assert _qualified_by({"sig_buyer": True}, ["39162100"]) == (["buyer"], [])
    assert _qualified_by({}, ["39162100"]) == ([], [])


def test_months_well_below_the_usual_are_gaps_and_the_partial_ends_are_not():
    per_month = {"2026-01": 3, "2026-02": 100, "2026-03": 120, "2026-04": 40, "2026-05": 110,
                 "2026-07": 105, "2026-08": 9}
    median, gaps = month_gaps(per_month)
    assert median == 102
    assert gaps == ["2026-04", "2026-06"]           # June has none; January and August are the ends
    assert month_gaps({"2026-01": 5, "2026-02": 7}) == (0, [])
    assert month_gaps({}) == (0, [])


def test_the_irish_buyer_id_after_a_name_is_dropped_and_a_real_number_is_not():
    assert clean_buyer_name("Irish Defence Forces_1144") == "Irish Defence Forces"
    assert clean_buyer_name("An Garda Síochána_1192") == "An Garda Síochána"
    assert clean_buyer_name("Stalag 13") == "Stalag 13"
    assert clean_buyer_name(None) == ""
