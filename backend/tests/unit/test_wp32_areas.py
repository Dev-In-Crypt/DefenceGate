"""WP-32: the area a funding call is compared in for partner suggestions (dgate/partners.py `areas_of`).

Pure: no database. The topic codes are real ones from the production call list of 17 October 2026.
"""

from __future__ import annotations

import re

import pytest

from dgate.partners import area_label, areas_of
from dgate.readiness.api import programmes_of_call
from dgate.readiness.seed import load_file


def kinds(topic):
    return [a.kind for a in areas_of(topic)]


@pytest.mark.parametrize("topic,category", [
    ("EDF-2026-DA-SPACE-PRS-STEP", "SPACE"),
    ("EDF-2026-RA-CYBER-QSTN", "CYBER"),
    ("EDF-2026-DA-ACC-AIRDEF-EATMI", "AIRDEF"),       # ACC names no category; AIRDEF does
    ("EDF-2026-RA-SI-UWW-CSBI-STEP", "UWW"),
    ("EDF-2026-LS-DA-SME-NT", "SME"),
    ("EDF-2026-DA-EXP-DIGIT-MDOC-STEP", "DIGIT"),
])
def test_an_edf_call_is_compared_first_with_its_capability_category_then_with_all_edf(topic, category):
    narrow, broad = areas_of(topic)
    assert (narrow.kind, narrow.category, narrow.source) == ("edf-category", category, "edf_factsheets")
    assert (broad.kind, broad.category) == ("edf", None)
    assert category in narrow.label


@pytest.mark.parametrize("topic", ["EDF-EDIP-P-2026-2027-FNLC-SA-SEAP", "EDF-EDIP-P-2026-LS-IRA-EC"])
def test_an_edip_call_names_no_category_so_it_is_compared_with_all_edf_projects(topic):
    assert kinds(topic) == ["edf"]


# WP-109 (p08, 113): the counter-drone and the unmanned-systems topics name their categories in their titles (partners.EDIP_RELATED)
@pytest.mark.parametrize("topic", ["EDF-EDIP-P-2026-FNLC-CPA-CDS", "EDF-EDIP-USI-2027-LS-IRA-CUXS"])
def test_the_drone_edip_calls_are_compared_with_their_categories_first(topic):
    assert kinds(topic) == ["edf-related", "edf"]


def test_a_horizon_call_has_a_destination_and_its_round_is_not_the_destination():
    narrow, wide = areas_of("HORIZON-CL3-2026-01-BM-01")
    assert (narrow.kind, wide.kind) == ("horizon-destination", "horizon-family")
    assert narrow.source == "cordis" and "destination BM" in narrow.label
    # the call codes of earlier projects in CORDIS (`HORIZON-CL3-2022-BM-01`) have no round
    for earlier in ("HORIZON-CL3-2022-BM-01", "HORIZON-CL3-2021-BM-02", "HORIZON-CL3-2023-BM-01-02", "HORIZON-CL3-2026-02-BM-01-03"):
        assert re.search(narrow.regex, earlier), earlier
    for other in ("HORIZON-CL3-2023-BMX-01-02", "HORIZON-CL3-2023-FCT-01-02", "HORIZON-CL4-2023-BM-01-02",
                  "HORIZON-CL30-2023-BM-01-02", "H2020-CL3-2023-BM-01-02"):
        assert not re.search(narrow.regex, other), other
    assert re.search(wide.regex, "HORIZON-CL3-2023-FCT-01-02") and not re.search(wide.regex, "HORIZON-CL4-2023-FCT-01-02")
    assert narrow.like == wide.like == "HORIZON-CL3-%"


def test_a_destination_made_of_two_words_is_compared_by_its_first_word():
    narrow, _ = areas_of("HORIZON-CL3-2027-02-CS-ECCC-04")
    assert "destination CS" in narrow.label and re.search(narrow.regex, "HORIZON-CL3-2023-CS-01-01")


def test_a_joint_undertaking_family_keeps_its_whole_name_and_case_does_not_matter():
    narrow, wide = areas_of("HORIZON-JU-EuroHPC-2026-SPT-10-01")
    assert "JU-EUROHPC" in narrow.label and re.search(wide.regex, "HORIZON-JU-EUROHPC-2022-COE-01-01")
    assert narrow.like == "HORIZON-JU-EUROHPC-%"


def test_a_call_whose_code_has_no_destination_is_compared_with_its_family_only():
    assert kinds("HORIZON-RAISE-2026-01-03") == ["horizon-family"]
    assert kinds("HORIZON-EIC-2026-ACCELERATOR-01") == ["horizon-destination", "horizon-family"]


@pytest.mark.parametrize("topic", [
    "DIGITAL-2026-AI-09-DS-HEALTH-TOOL", "CEF-T-2026-MILMOB-WORKS", "FR-AID-12345", "[aid] 12345", "", None,
    "HORIZON", "HORIZON-CL3", "HORIZON-CL3-BM-01", "EDF-2026",
])
def test_calls_with_no_comparable_project_data_have_no_area(topic):
    assert areas_of(topic) == [] and area_label(topic) is None


def test_a_code_with_characters_that_a_pattern_would_read_is_refused():
    for bad in ("HORIZON-CL3.*-2026-BM-01", "HORIZON-(CL3)-2026-BM-01", "HORIZON-CL3-2026-BM-01'--", "EDF-2026-DA-SP ACE"):
        assert areas_of(bad) == [], bad


def test_the_label_is_the_narrowest_area():
    assert area_label("EDF-2026-DA-SPACE-PRS-STEP") == "EDF capability category SPACE"
    assert area_label("HORIZON-CL3-2026-01-FCT-02") == "Horizon Europe, CL3, destination FCT"


# --- the programme whose rules judge a call (readiness/api.py)

CONTENT = load_file()


@pytest.mark.parametrize("stored,topic,wanted", [
    ("EDF", "EDF-2026-DA-SPACE-PRS-STEP", ["EDF"]),
    ("EDF", "EDF-EDIP-P-2027-FNLC-CPA-AMDS", ["EDIP"]),             # filed under EDF by the portal, judged by EDIP
    ("EDF", "EDF-EDIP-USI-2027-LS-IRA-CUXS", ["EDIP-USI"]),
    ("EDIP", "EDIP-c2", ["EDIP", "EDIP-USI"]),                       # a stored EDIP call whose code says neither
    ("EDF", "EDF-EDIP-X-1", ["EDIP", "EDIP-USI"]),
    ("HORIZON", "HORIZON-CL3-2026-01-BM-01", []),
    ("DIGITAL", None, []),
])
def test_an_edip_call_is_judged_by_the_edip_rules_even_when_the_portal_files_it_under_the_edf(stored, topic, wanted):
    assert [p.code for p in programmes_of_call(CONTENT, stored, topic)] == wanted
