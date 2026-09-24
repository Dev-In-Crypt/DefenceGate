"""Reading a topic page: the budget, and the rules stated in words.

The calendar says a call exists. These are the three facts that decide whether a
twenty-person supplier writes a proposal: how much money is on the topic, how
many partners it needs, and from how many countries. Two of them are only
sometimes stated, which is the whole difficulty -- the test is as much about what
must stay null as about what must be read.

Shapes are the ones the portal returned on 24 September 2026 for
`EDF-2026-RA-SENS-MSDT` and `HORIZON-CL3-2026-01-DRS-01`.
"""

from __future__ import annotations

import pytest

from dgate.sources import eu_portal as portal

# The 2026 EDF research call holds eleven topics under one budget key, each with
# its own money. Two of them here, and the one asked for is the second.
EDF_DETAILS = {
    "identifier": "EDF-2026-RA-SENS-MSDT",
    "topicMGAs": [{"abbreviation": "EDF-AG"}],
    "tags": ["STEP-Digital/deep tech", "STEP-Defence"],
    "sme": False,
    "links": [{"url": "https://ec.europa.eu/research/participants/submission/"
                      "manage/screen/submission/create-draft/43473?topic=EDF-2026-RA-SENS-MSDT"}],
    "conditions": '<div class="x"> Conditions <p>1. Admissibility Conditions: '
                  'described in section 5 of the <a href="#">call document</a>.</p>'
                  "<p>2. Eligible Countries described in section 6 of the call document.</p>"
                  "<p>Proposal page limit: at least 3 pages of annexes.</p></div>",
    "budgetOverviewJSONItem": {"budgetTopicActionMap": {"113481": [
        {"action": "EDF-2026-RA-CYBER-QSTN - EDF-RA EDF Research Actions",
         "budgetYearMap": {"2026": "110000000"}, "expectedGrants": 0,
         "minContribution": 0, "maxContribution": 0, "deadlineModel": "single-stage"},
        {"action": "EDF-2026-RA-SENS-MSDT - EDF-RA EDF Research Actions",
         "budgetYearMap": {"2026": "30000000"}, "expectedGrants": 0,
         "minContribution": 0, "maxContribution": 0, "deadlineModel": "single-stage"},
    ]}},
}

CL3_DETAILS = {
    "identifier": "HORIZON-CL3-2026-01-DRS-01",
    "topicMGAs": [{"abbreviation": "HORIZON-AG"}],
    "tags": [],
    "sme": True,
    "links": [],
    "conditions": "<p>3. Other Eligible Conditions: This topic requires the active "
                  "involvement, as beneficiaries, of at least 3 organisations from at "
                  "least 3 different EU Member States or Associated Countries.</p>",
    "budgetOverviewJSONItem": {"budgetTopicActionMap": {"113345": [
        {"action": "HORIZON-CL3-2026-01-DRS-01 - HORIZON-RIA",
         "budgetYearMap": {"2026": "6000000"}, "expectedGrants": 2,
         "minContribution": 3000000, "maxContribution": 3000000,
         "deadlineModel": "single-stage"},
    ]}},
}


# ------------------------------------------------------------- the budget

def test_the_budget_is_this_topic_not_the_first_one_in_the_call():
    """Several topics share one budget key. Taking the first line would hand a
    supplier a sibling topic's money -- here EUR 110m instead of EUR 30m."""
    amount, line, sharing = portal.topic_budget(EDF_DETAILS, "EDF-2026-RA-SENS-MSDT")
    assert amount == 30_000_000.0
    assert line["action"].startswith("EDF-2026-RA-SENS-MSDT")
    assert sharing == 1
    assert portal.detail_fields(
        EDF_DETAILS, "EDF-2026-RA-SENS-MSDT")["budget_scope"] == "topic"


# All eleven topics of the 2026 EDF development call carry the same figure: it is
# the pot they compete for, not one topic's money.
SHARED_BUDGET = {
    "identifier": "EDF-2026-DA-AIR-SPS",
    "conditions": "<p>described in section 6 of the call document.</p>",
    "budgetOverviewJSONItem": {"budgetTopicActionMap": {"113484": [
        {"action": f"EDF-2026-DA-{name} - EDF-DA", "budgetYearMap": {"2026": "422000000"},
         "expectedGrants": 0, "minContribution": 0, "maxContribution": 0}
        for name in ("AIR-SPS", "GROUND-MRL", "NAVAL-EMSAS")
    ]}},
}


def test_a_figure_repeated_across_sibling_topics_is_the_call_s_pot():
    """Served as the topic's budget, this would tell a twenty-person supplier
    there is EUR 422 million behind the one topic it was reading. The amount is
    kept because it is the only figure published; the scope is what makes it
    honest."""
    amount, _, sharing = portal.topic_budget(SHARED_BUDGET, "EDF-2026-DA-AIR-SPS")
    assert (amount, sharing) == (422_000_000.0, 3)
    fields = portal.detail_fields(SHARED_BUDGET, "EDF-2026-DA-AIR-SPS")
    assert fields["budget_scope"] == "call"
    assert fields["conditions_raw"]["topics_sharing_budget"] == 3


def test_a_budget_spread_over_years_is_summed():
    details = {"budgetOverviewJSONItem": {"budgetTopicActionMap": {"1": [
        {"action": "X-01 - RIA", "budgetYearMap": {"2026": "1000000", "2027": "500000"}},
    ]}}}
    assert portal.topic_budget(details, "X-01")[0] == 1_500_000.0


def test_a_topic_with_no_budget_line_gets_none_not_zero():
    assert portal.topic_budget(EDF_DETAILS, "EDF-2026-RA-NOT-HERE") == (None, {}, 0)
    assert portal.topic_budget({}, "X-01") == (None, {}, 0)
    assert portal.detail_fields({}, "X-01")["budget_scope"] is None


# -------------------------------------------------------- the conditions

def test_the_conditions_come_back_as_readable_text():
    text = portal.conditions_text(EDF_DETAILS)
    assert "<p>" not in text and "Eligible Countries" in text
    assert "  " not in text


def test_a_topic_without_conditions_has_none():
    assert portal.conditions_text({}) is None
    assert portal.conditions_text({"conditions": "   "}) is None


def test_the_consortium_rule_is_read_when_the_call_states_it():
    text = portal.conditions_text(CL3_DETAILS)
    assert portal.consortium_rule(text) == (3, 3)


def test_the_rule_stays_null_when_the_call_points_at_a_pdf():
    """Every EDF topic says "described in section 6 of the call document". The
    EDF regulation does require three entities from three states in general, and
    writing that number here would present a reading of the regulation as a fact
    about this call."""
    assert portal.consortium_rule(portal.conditions_text(EDF_DETAILS)) == (None, None)


@pytest.mark.parametrize("text,expected", [
    ("at least three eligible entities established in at least three different "
     "Member States", (3, 3)),
    ("consortium of at least 4 independent legal entities from 3 different EU "
     "Member States", (4, None)),      # the second number is not "at least"
    ("beneficiaries established in at least 2 different Member States", (None, 2)),
    ("at least 3 pages of annexes", (None, None)),
    ("letters of support from at least 5 stakeholders", (None, None)),
    ("", (None, None)),
])
def test_only_a_consortium_sentence_is_read_as_one(text, expected):
    """The same sentence shape counts pages, letters and stakeholders. A closed
    list of what can be a consortium member is what keeps those out."""
    assert portal.consortium_rule(text) == expected


# ---------------------------------------------------- everything together

def test_the_detail_fields_are_what_the_call_columns_need():
    fields = portal.detail_fields(CL3_DETAILS, "HORIZON-CL3-2026-01-DRS-01")
    assert fields["budget"] == 6_000_000.0
    assert (fields["min_consortium_size"], fields["min_member_states"]) == (3, 3)
    assert "at least 3 organisations" in fields["eligibility_text"]
    conditions = fields["conditions_raw"]
    assert conditions["expected_grants"] == 2
    assert conditions["max_contribution"] == 3_000_000
    assert conditions["for_smes"] is True
    assert conditions["mga"] == ["HORIZON-AG"]


def test_a_total_without_a_grant_count_says_so_rather_than_implying_one():
    """EUR 30 million across an unknown number of grants and two grants of
    EUR 3 million are different propositions. A zero in the portal's line means
    "not stated", so it is carried as null and not as a count of zero."""
    conditions = portal.detail_fields(EDF_DETAILS, "EDF-2026-RA-SENS-MSDT")["conditions_raw"]
    assert conditions["expected_grants"] is None
    assert conditions["min_contribution"] is None
    assert conditions["tags"] == ["STEP-Digital/deep tech", "STEP-Defence"]
    assert conditions["submission_urls"][0].endswith("topic=EDF-2026-RA-SENS-MSDT")


def test_a_document_that_is_not_a_topic_page_is_refused(monkeypatch):
    class _Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"error": "not found"}

    class _Client:
        def get(self, url, timeout=None):
            return _Response()

    with pytest.raises(ValueError, match="shape changed"):
        portal.fetch_topic_details("edf-2026-ra-sens-msdt", client=_Client())


def test_the_identifier_is_lower_cased_for_a_portal_that_insists(monkeypatch):
    """The portal publishes `EDF-2026-RA-SENS-MSDT` everywhere and answers 404
    to it in the path. Lower case is the only spelling that works."""
    asked: list[str] = []

    class _Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"TopicDetails": {"identifier": "x"}}

    class _Client:
        def get(self, url, timeout=None):
            asked.append(url)
            return _Response()

    portal.fetch_topic_details("EDF-2026-RA-SENS-MSDT", client=_Client())
    assert asked[0].endswith("/edf-2026-ra-sens-msdt.json")
