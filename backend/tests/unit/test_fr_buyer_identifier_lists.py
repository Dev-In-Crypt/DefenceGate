"""BOAMP eForms: a buyer's `cac:PartyLegalEntity` (or `cac:PartyIdentification`) can be a list. On 9-14 Nov 2026 such
notices (26-109446 and five others) were quarantined every day with "'list' object has no attribute 'get'"."""

from __future__ import annotations

from dgate.normalise import _fr_buyer_identifier


def _body(legal) -> dict:
    org = {"efac:Company": {"cac:PartyIdentification": [{"cbc:ID": "ORG-0001"}], "cac:PartyLegalEntity": legal}}
    return {"EFORMS": {"ContractNotice": {
        "cac:ContractingParty": {"cac:Party": {"cac:PartyIdentification": {"cbc:ID": "ORG-0001"}}},
        "ext:UBLExtensions": {"ext:UBLExtension": {"ext:ExtensionContent": {"efext:EformsExtension": {
            "efac:Organizations": {"efac:Organization": [org, {"efac:Company": {
                "cac:PartyIdentification": {"cbc:ID": "ORG-0002"},
                "cac:PartyLegalEntity": {"cbc:CompanyID": "11111111111111"}}}]}}}}}}}}


def test_a_list_of_legal_entities_with_one_number_gives_that_number():
    one = _fr_buyer_identifier(_body([{"cbc:CompanyID": "22940028800010"}, {"cbc:RegistrationName": "x"}]))
    assert one == _fr_buyer_identifier(_body({"cbc:CompanyID": "22940028800010"})) is not None


def test_two_different_numbers_leave_the_buyer_unknown():
    assert _fr_buyer_identifier(_body([{"cbc:CompanyID": "22940028800010"}, {"cbc:CompanyID": "21930029000018"}])) is None
