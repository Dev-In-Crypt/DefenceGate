"""WP-173: the funding findings of the QA of 24 November 2026 (D:\\DEFENCEGATE TESTS\\qa-full-nov24\\c\\REPORT-C.md)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from dgate import ukraine
from dgate.funding import cut_offs, edition_title
from dgate.sources import eu_portal as portal

NOV_12 = 1794441600000          # 2026-11-12 00:00 UTC
FEB_16 = 1802736000000          # 2027-02-16 00:00 UTC


# ---------------------------------------------------------------- C-1: the deadline model is read where the record states it

def test_the_deadline_model_is_read_from_the_topic_or_its_actions():
    assert portal.deadline_model({"deadlineModel": {"abbreviation": "Multiple cut-off"}}) == "multiple cut-off"
    assert portal.deadline_model({"actions": [{"deadlineModel": "multiple cut-off", "deadlineDates": []}]}) == "multiple cut-off"
    assert portal.deadline_model({"actions": [{"deadlineDates": [NOV_12]}]}) == ""


def test_an_action_that_says_multiple_cut_off_gets_the_next_cut_off():
    record = {"actions": [{"deadlineModel": "multiple cut-off", "deadlineDates": [NOV_12, FEB_16]}]}
    assert portal.closing(record, now=datetime(2026, 11, 24, tzinfo=UTC)).date() == date(2027, 2, 16)


# ---------------------------------------------------------------- C-1, C-9: every cut-off and stage is served

def test_the_cut_offs_of_the_budget_line_are_served_when_there_are_several():
    assert cut_offs({"budget_line": {"deadlineDates": [FEB_16, NOV_12, str(NOV_12)]}}) == ["2026-11-12", "2027-02-16"]
    assert cut_offs({"budget_line": {"deadlineDates": [NOV_12]}}) == []
    assert cut_offs({"budget_line": None}) == [] and cut_offs({}) == []


# ---------------------------------------------------------------- C-9: titles that tell editions apart

def test_eic_titles_name_the_scheme_and_the_edition():
    assert edition_title("EIC STEP Scale Up", "HORIZON-EIC-2026-STEP") == "EIC STEP Scale Up 2026"
    assert edition_title("EIC STEP Scale Up", "HORIZON-EIC-2027-STEP") == "EIC STEP Scale Up 2027"
    assert edition_title("Short proposal", "HORIZON-EIC-2027-ACCELERATOR-01") == "EIC Accelerator 2027: Short proposal"
    assert edition_title("HORIZON-EIC-2027-PATHFINDEROPEN-two-stage", "HORIZON-EIC-2027-PATHFINDEROPEN-two-stage") \
        == "EIC Pathfinder Open 2027 (two-stage)"
    assert edition_title("EIC Accelerator 2026 - Short proposal", "HORIZON-EIC-2026-ACCELERATOR-01") \
        == "EIC Accelerator 2026 - Short proposal"
    assert edition_title("Unmanned systems", "EDF-2026-LS-RA-X") == "Unmanned systems"


# ---------------------------------------------------------------- C-3, C-15: a control clause is not a country list

STEP_2027 = ("In accordance with Article 48(2) of the Horizon Europe Regulation, participation is limited to SMEs, including start-ups, "
             "and small mid-caps established in the Union, in Ukraine, or in an EEA member associated to Horizon Europe. This call has a "
             "general exclusion rule: legal entities, established in the Union, in Ukraine or in an EEA member associated to Horizon "
             "Europe, that are directly or indirectly controlled by a third country other than Ukraine or an EEA member associated to "
             "Horizon Europe, or by legal entities of such a third country cannot participate.")


def test_the_live_eic_edition_is_open_to_ukraine_despite_its_control_clause():
    flag, reason, evidence = ukraine.decide({"programme_code": "HORIZON", "topic_code": "HORIZON-EIC-2027-STEP",
                                             "eligibility_text": STEP_2027}, {})
    assert (flag, reason) == (True, "call_text")
    assert "in Ukraine, or in an EEA member" in evidence and "controlled" not in evidence


def test_a_control_clause_is_not_quoted_as_the_list_of_eligible_countries():
    control = {"scope": "call_document", "quote": "Legal entities that are established in EU Member States, EEA countries (Iceland, "
               "Liechtenstein, and Norway), but are controlled from third countries may only participate on the condition that they "
               "guarantee the protection of the essential security interests of the Union."}
    assert ukraine._closed_list(control) is None
    listed = {"scope": "call_document", "quote": "Eligible countries: the Member States and the EEA countries Norway, Iceland and "
              "Liechtenstein."}
    assert ukraine._closed_list(listed) is not None
