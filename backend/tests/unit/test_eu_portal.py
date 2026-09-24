"""The EU grant calendar: which calls are in scope, and what a call maps to.

Fixtures are the shapes the reference-data document returned on 24 September
2026, trimmed to the fields the connector reads. Four of them are what the
agreed scope says yes to and two are what it says no to, because a selection
rule is only testable against what it must reject.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from dgate.normalise import from_eu_call
from dgate.sources import eu_portal as portal


def _topic(**over):
    record = {
        "type": 1,
        "ccm2Id": 45095551,
        "identifier": "EDF-2026-RA-SENS-MSDT",
        "callIdentifier": "EDF-2026-RA",
        "title": "Multidomain sensors demonstrator and test",
        "frameworkProgramme": [{"abbreviation": "EDF",
                                "description": "European Defence Fund (EDF)"}],
        "programmeDivision": [],
        "status": {"id": 31094502, "abbreviation": "Open", "description": "Open"},
        "tags": [],
        "actions": [{
            "types": [{"typeOfAction": "EDF-RA EDF Research Actions"}],
            "plannedOpeningDate": "1770768000000",          # 2026-02-11
            "deadlineDates": ["1790640000000"],             # 2026-09-29
        }],
    }
    record.update(over)
    return record


CL3 = _topic(ccm2Id=99001, identifier="HORIZON-CL3-2026-01-DRS-01",
             callIdentifier="HORIZON-CL3-2026-01",
             title="Disaster resilient society",
             frameworkProgramme=[{"abbreviation": "HORIZON"}],
             programmeDivision=[{"abbreviation": "HORIZON.2.3",
                                 "description": "Civil Security for Society"}])

EIC = _topic(ccm2Id=99002, identifier="HORIZON-EIC-2026-ACCELERATOR",
             title="EIC Accelerator Open",
             frameworkProgramme=[{"abbreviation": "HORIZON"}],
             programmeDivision=[{"abbreviation": "HORIZON.3.1.2",
                                 "description": "The Accelerator"}])

DIGITAL = _topic(ccm2Id=99003, identifier="DIGITAL-2026-AI-09-DS-HEALTH-TOOL",
                 title="AI data space",
                 frameworkProgramme=[{"abbreviation": "DIGITAL"}],
                 programmeDivision=[])

FARMING = _topic(ccm2Id=99004, identifier="AGRIP-MULTI-2026-IM",
                 title="Support for multi programmes",
                 frameworkProgramme=[{"abbreviation": "AGRIP2027"}],
                 programmeDivision=[])

COMMISSION_TENDER = _topic(type=0, ccm2Id=99005, identifier="DIGIT-2026-OP-0001",
                           title="Framework contract for cloud services",
                           frameworkProgramme=[{"abbreviation": "DIGITAL"}])


# ------------------------------------------------------------- the scope

def test_a_defence_programme_is_the_reason_on_its_own():
    """`frameworkProgramme` is the regulation the money comes from. EDF is
    Directive-level evidence of defence, stated by the publisher, and it does not
    matter that the topic is about sensors rather than about weapons."""
    assert portal.regime(_topic()) == "defence"
    assert portal.regime(_topic(frameworkProgramme=[{"abbreviation": "EDIP"}])) == "defence"


def test_the_step_defence_seal_makes_a_civil_topic_defence():
    """The Commission tags civil-programme topics that carry the STEP defence
    seal. Read as a defence signal rather than as a programme name, which is the
    only way a Digital Europe topic under the seal is not filed as dual-use."""
    assert portal.regime({**DIGITAL, "tags": ["STEP-Defence"]}) == "defence"


@pytest.mark.parametrize("record", [CL3, EIC, DIGITAL])
def test_the_civil_programmes_in_scope_are_dual_use_not_defence(record):
    assert portal.regime(record) == "dual_use"


def test_a_programme_outside_the_agreed_scope_is_not_collected():
    """Agricultural promotion is somebody else's product. The filter has to say
    no to 10,000 of the portal's topics for the 150 to be worth anything."""
    assert portal.regime(FARMING) is None
    assert portal.in_scope(FARMING) is False


def test_commission_procurement_is_not_a_grant():
    """`type` 0 is the Commission buying for itself, which reaches us through
    TED. Only type 1 is a call for proposals."""
    assert portal.in_scope(COMMISSION_TENDER) is False


def test_open_and_forthcoming_are_in_scope_whatever_their_dates():
    assert portal.in_scope(_topic(), today=date(2026, 9, 24)) is True
    forthcoming = _topic(status={"abbreviation": "Forthcoming"}, actions=[])
    assert portal.in_scope(forthcoming, today=date(2026, 9, 24)) is True


def test_a_closed_call_is_kept_for_the_current_year_and_no_further():
    """A call that closed in March tells a supplier when the next one opens. One
    that closed in 2021 belongs to the participant-network work, and collecting
    it here would quietly turn a current database into a decade of history."""
    closed_now = _topic(status={"abbreviation": "Closed"},
                        actions=[{"deadlineDates": ["1772409600000"]}])     # 2026-03-02
    closed_old = _topic(status={"abbreviation": "Closed"},
                        actions=[{"deadlineDates": ["1614643200000"]}])     # 2021-03-02
    assert portal.in_scope(closed_now, today=date(2026, 9, 24)) is True
    assert portal.in_scope(closed_old, today=date(2026, 9, 24)) is False


def test_a_topic_without_an_identifier_is_not_collected():
    assert portal.in_scope(_topic(identifier=None)) is False


# ------------------------------------------------------------ the shapes

def test_the_deadline_is_the_next_stage_not_the_last():
    """A two-stage call has one deadline per stage. What decides whether to start
    writing is the next one; the rest stay in the payload."""
    two_stage = _topic(actions=[{"deadlineDates": ["1790640000000", "1806451200000"]}])
    assert portal.deadline(two_stage) == datetime(2026, 9, 29, tzinfo=timezone.utc)


def test_a_topic_with_no_deadline_yet_has_none_rather_than_a_guess():
    assert portal.deadline(_topic(actions=[])) is None


def test_a_call_maps_completely():
    call = from_eu_call(_topic())
    assert call.programme_code == "EDF"
    assert call.native_id == "45095551"                 # ccm2Id, not the code
    assert call.topic_code == "EDF-2026-RA-SENS-MSDT"
    assert call.call_identifier == "EDF-2026-RA"
    assert call.status == "open"
    assert call.regime == "defence"
    assert call.type_of_action == "EDF-RA EDF Research Actions"
    assert call.opens_at == date(2026, 2, 11)
    assert call.deadline_at == datetime(2026, 9, 29, tzinfo=timezone.utc)
    assert call.source_url.endswith("edf-2026-ra-sens-msdt")
    assert call.budget is None                          # the feed carries none


def test_the_budget_stays_null_because_the_feed_has_none():
    """Checked across all 10,164 grant topics on 24 September 2026: no budget
    field, no conditions of participation, and no CPV on a single grant. A null
    is the honest value; the topic page is where those three come from."""
    call = from_eu_call(_topic())
    assert (call.budget, call.eligibility_text, call.cpv_codes) == (None, None, [])


def test_a_call_without_the_portal_identity_is_refused():
    with pytest.raises(ValueError):
        from_eu_call(_topic(ccm2Id=None))


def test_a_call_naming_no_programme_is_refused():
    """The programme is a foreign key, and inventing one would file a call under
    a regulation that does not fund it."""
    with pytest.raises(ValueError):
        from_eu_call(_topic(frameworkProgramme=[]))


# --------------------------------------------------------- the document

def test_the_document_is_filtered_to_the_scope():
    document = {"fundingData": {"GrantTenderObj": [
        _topic(), CL3, DIGITAL, FARMING, COMMISSION_TENDER]}}
    kept = portal.parse_snapshot(document, today=date(2026, 9, 24))
    assert [r["identifier"] for r in kept] == [
        "EDF-2026-RA-SENS-MSDT", "HORIZON-CL3-2026-01-DRS-01",
        "DIGITAL-2026-AI-09-DS-HEALTH-TOOL"]


@pytest.mark.parametrize("document", [
    {},                                                     # not the document
    {"fundingData": {}},                                    # shape changed
    {"fundingData": {"GrantTenderObj": []}},                # served, but empty
])
def test_a_document_that_is_not_the_calendar_is_an_error_not_an_empty_day(document):
    """A source that publishes 11,163 calls and answers with none is having an
    outage. Returning nothing would record the outage as a successful run that
    found no calls, and the floor would be the only thing left to catch it."""
    with pytest.raises(ValueError):
        portal.parse_snapshot(document)
