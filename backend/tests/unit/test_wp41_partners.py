"""WP-41, N8: the area a funding call is compared with. All 40 EDF-prefixed calls of 18 October 2026, by call id."""

from __future__ import annotations

import pytest

from dgate import partners
from dgate.sources import edf_factsheets as edf

# call id: (topic code, area kind, category or categories of the narrowest area)
CALLS = {
    93: ("EDF-2026-DA-ACC-AIRDEF-EATMI", "edf-category", "AIRDEF"),
    97: ("EDF-2026-DA-AIR-SPS", "edf-category", "AIR"),
    103: ("EDF-2026-DA-AIR-STFS", "edf-category", "AIR"),
    96: ("EDF-2026-DA-ENERENV-AWC-STEP", "edf-category", "ENERENV"),
    99: ("EDF-2026-DA-ENERENV-HPES-STEP", "edf-category", "ENERENV"),
    83: ("EDF-2026-DA-EXP-DIGIT-MDOC-STEP", "edf-category", "DIGIT"),
    104: ("EDF-2026-DA-GROUND-MBT", "edf-category", "GROUND"),
    98: ("EDF-2026-DA-GROUND-MRL", "edf-category", "GROUND"),
    94: ("EDF-2026-DA-MATCOMP-SMT-STEP", "edf-category", "MATCOMP"),
    102: ("EDF-2026-DA-NAVAL-EMSAS", "edf-category", "NAVAL"),
    100: ("EDF-2026-DA-PROTMOB-DMM", "edf-category", "PROTMOB"),
    101: ("EDF-2026-DA-SENS-CEW-STEP", "edf-category", "SENS"),
    95: ("EDF-2026-DA-SPACE-PRS-STEP", "edf-category", "SPACE"),
    80: ("EDF-2026-LS-DA-DIS-OTHR", "edf-category", "DIS"),
    79: ("EDF-2026-LS-DA-SME-NT", "edf-category", "SME"),
    107: ("EDF-2026-LS-DIS-NT", "edf-category", "DIS"),
    106: ("EDF-2026-LS-DIS-RA-SMERO-NT", "edf-category", "SMERO"),          # was DIS
    81: ("EDF-2026-LS-RA-CHALLENGE-DIGIT-AISAO", "edf-category", "DIGIT"),
    82: ("EDF-2026-LS-RA-CHALLENGE-DIGIT-AISAP-STEP", "edf-category", "DIGIT"),
    92: ("EDF-2026-LS-RA-SI-ENERENV-NTFE", "edf-category", "ENERENV"),
    89: ("EDF-2026-RA-AIR-A4R", "edf-category", "AIR"),
    88: ("EDF-2026-RA-CYBER-QSTN", "edf-category", "CYBER"),
    84: ("EDF-2026-RA-MCBRN-DST", "edf-category", "MCBRN"),
    85: ("EDF-2026-RA-PROTMOB-FMLA", "edf-category", "PROTMOB"),
    87: ("EDF-2026-RA-SENS-MSDT", "edf-category", "SENS"),
    86: ("EDF-2026-RA-SIMTRAIN-MSAI", "edf-category", "SIMTRAIN"),
    91: ("EDF-2026-RA-SI-UWW-CSBI-STEP", "edf-category", "UWW"),
    90: ("EDF-2026-RA-UWW-FUWN", "edf-category", "UWW"),
    # the EDIP calls: three name an EDF capability in their title, the rest are compared with every EDF project
    110: ("EDF-EDIP-P-2027-FNLC-CPA-AMDS", "edf-related", ("AIRDEF",)),
    112: ("EDF-EDIP-P-2027-FNLC-CPA-GNPS", "edf-related", ("GROUND", "NAVAL")),
    111: ("EDF-EDIP-P-2027-FNLC-CPA-C5ISRS", "edf-related", ("C4ISR", "SPACE")),
    108: ("EDF-EDIP-P-2026-FNLC-CPA-AMEW", "edf", None),
    109: ("EDF-EDIP-P-2026-FNLC-CPA-CDS", "edf", None),
    193: ("EDF-EDIP-P-2026-FNLC-CSA-PREP", "edf", None),
    115: ("EDF-EDIP-P-2026-LS-IRA-EC", "edf", None),
    114: ("EDF-EDIP-P-2026-2027-FNLC-SA-SEAP", "edf", None),
    116: ("EDF-EDIP-P-2027-LS-IRA-KEC", "edf", None),
    117: ("EDF-EDIP-P-2027-LS-IRA-PE", "edf", None),
    118: ("EDF-EDIP-USI-2026-LS-IRA-MAB", "edf", None),
    113: ("EDF-EDIP-USI-2027-LS-IRA-CUXS", "edf", None),
}


def test_the_table_holds_all_forty_calls():
    assert len(CALLS) == 40


@pytest.mark.parametrize("call", sorted(CALLS))
def test_the_area_of_each_edf_prefixed_call(call):
    topic, kind, want = CALLS[call]
    narrow = partners.areas_of(topic)[0]
    assert narrow.kind == kind
    if kind == "edf-category":
        assert narrow.category == want
    elif kind == "edf-related":
        assert narrow.categories == want and "Our reading of the title" in narrow.rule
    else:
        assert narrow.generic is True and narrow.category is None


def test_the_edip_calls_that_were_compared_with_everything_no_longer_all_get_the_same_area():
    kinds = {partners.areas_of(t)[0].kind for _, (t, k, _) in CALLS.items() if "EDIP" in t}
    assert kinds == {"edf-related", "edf"}
    related = {partners.areas_of(t)[0].label for _, (t, k, _) in CALLS.items() if k == "edf-related"}
    assert len(related) == 3


def test_a_related_edip_area_still_falls_back_to_all_edf_and_says_so():
    narrow, broad = partners.areas_of("EDF-EDIP-P-2027-FNLC-CPA-AMDS")
    assert broad.kind == "edf" and broad.generic is True      # the fallback of an EDIP topic says it is every EDF project


def test_the_category_of_a_code_is_the_last_one_it_names():
    assert edf.category_of("EDF-2026-LS-DIS-RA-SMERO-NT".split("-")) == "SMERO"
    assert edf.category_of("EDF-2023-DA-DS-AIRDEF-EATMI".split("-")) == "AIRDEF"
    assert edf.category_of("EDF-2023-LS-RA-SMERO-NT".split("-")) == "SMERO"
    assert edf.category_of("EDF-EDIP-P-2027-LS-IRA-PE".split("-")) is None
    info = edf.parse_filename("EDF-2023-DA-DS-AIRDEF-EATMI TEST.pdf", 2023)
    assert info.category == "AIRDEF"
