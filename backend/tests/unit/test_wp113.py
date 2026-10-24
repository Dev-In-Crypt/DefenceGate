"""WP-113 (coverage audit of 24 October 2026): source field mappings.

BOAMP national-form deadlines in the buyer's own zone (Paris with its DST edges, the overseas departments and
collectivities), BOAMP's other directives, TenderNed's rectified deadline and flagged main CPV, the German notice link,
who may apply from a call's own text, and the closing time an EU call document states.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from dgate import who_apply
from dgate.normalise import from_boamp, from_de_bkms, from_tenderned, strip_personal_data
from dgate.sources import eu_portal

UTC = timezone.utc
FIX = Path(__file__).resolve().parents[1] / "fixtures" / "de_bkms"


def _fns(stamp: str | None, *, cp: str | None = "69007", depts: list[str] | None = None,
         column: str | None = None) -> dict:
    procedure = {"dateReceptionOffres": stamp} if stamp else {}
    organisme = {"nomOfficiel": "SID", "ville": "X", **({"cp": cp} if cp else {})}
    body = {"FNSimple": {"organisme": organisme, "initial": {"procedure": procedure}}}
    return {"idweb": "26-1", "nomacheteur": "SID", "objet": "Travaux", "perimetre": "FNSimple", "nature": "APPEL_OFFRE",
            "famille": "FNS", "code_departement": depts or ["69"], "dateparution": "2026-10-13",
            "datelimitereponse": column, "donnees": json.dumps(body)}


# ------------------------------------------------------------------ BOAMP national forms, Paris

@pytest.mark.parametrize("wall,utc", [
    ("2026-10-29T16:00:00", datetime(2026, 10, 29, 15, 0, tzinfo=UTC)),    # 26-98956 (/tenders/246424), winter
    ("2026-07-10T16:00:00", datetime(2026, 7, 10, 14, 0, tzinfo=UTC)),     # summer
    ("2026-03-28T12:00:00", datetime(2026, 3, 28, 11, 0, tzinfo=UTC)),     # the day before summer time
    ("2026-03-29T12:00:00", datetime(2026, 3, 29, 10, 0, tzinfo=UTC)),     # the day summer time starts
    ("2026-10-24T12:00:00", datetime(2026, 10, 24, 10, 0, tzinfo=UTC)),    # the last day of summer time
    ("2026-10-25T12:00:00", datetime(2026, 10, 25, 11, 0, tzinfo=UTC)),    # the day it ends
])
def test_a_national_form_deadline_is_paris_wall_time(wall, utc):
    got = from_boamp(_fns(wall, column=wall + "+00:00")).deadline_at
    assert got == utc


def test_the_false_utc_column_is_read_in_paris_when_the_body_states_no_date():
    assert from_boamp(_fns(None, column="2026-10-29T16:00:00+00:00")).deadline_at == datetime(2026, 10, 29, 15, 0, tzinfo=UTC)


# ------------------------------------------------------------------ overseas buyers

@pytest.mark.parametrize("cp,wall,utc", [
    ("97400", "2026-11-12T09:00:00", datetime(2026, 11, 12, 5, 0, tzinfo=UTC)),     # Reunion UTC+4 (/tenders/329978)
    ("97300", "2026-11-12T16:00:00", datetime(2026, 11, 12, 19, 0, tzinfo=UTC)),    # Guyane UTC-3 (/tenders/397583)
    ("97200", "2026-11-12T16:00:00", datetime(2026, 11, 12, 20, 0, tzinfo=UTC)),    # Martinique UTC-4
    ("97100", "2026-11-12T16:00:00", datetime(2026, 11, 12, 20, 0, tzinfo=UTC)),    # Guadeloupe UTC-4
    ("97600", "2026-11-12T09:00:00", datetime(2026, 11, 12, 6, 0, tzinfo=UTC)),     # Mayotte UTC+3
    ("98714", "2026-11-12T09:00:00", datetime(2026, 11, 12, 19, 0, tzinfo=UTC)),    # Tahiti UTC-10
    ("98800", "2026-11-12T09:00:00", datetime(2026, 11, 11, 22, 0, tzinfo=UTC)),    # Noumea UTC+11
    ("97500", "2026-07-10T12:00:00", datetime(2026, 7, 10, 14, 0, tzinfo=UTC)),     # Saint-Pierre, summer UTC-2
    ("97500", "2026-11-12T12:00:00", datetime(2026, 11, 12, 15, 0, tzinfo=UTC)),    # Saint-Pierre, winter UTC-3
    ("20000", "2026-11-12T12:00:00", datetime(2026, 11, 12, 11, 0, tzinfo=UTC)),    # Corsica is Paris
])
def test_an_overseas_buyer_deadline_is_its_own_wall_time(cp, wall, utc):
    assert from_boamp(_fns(wall, cp=cp)).deadline_at == utc


def test_without_a_postcode_the_first_department_listed_decides():
    # 26-103716 lists 973, 972, 971 for a buyer in Cayenne
    rec = _fns("2026-11-12T16:00:00", cp=None, depts=["973", "972", "971"])
    assert from_boamp(rec).deadline_at == datetime(2026, 11, 12, 19, 0, tzinfo=UTC)


def _eforms(postal: str, end_time: str = "12:00:00.000+02:00") -> dict:
    body = {"EFORMS": {"ContractNotice": {
        "cac:ContractingParty": {"cac:Party": {"cac:PartyIdentification": {"cbc:ID": "ORG-0001"}}},
        "cbc:RegulatoryDomain": "32014L0024",
        "ext:UBLExtensions": {"ext:UBLExtension": {"ext:ExtensionContent": {"efext:EformsExtension": {
            "efac:Organizations": {"efac:Organization": [
                {"efac:Company": {"cac:PartyIdentification": {"cbc:ID": "ORG-0001"},
                                  "cac:PostalAddress": {"cbc:PostalZone": postal}}},
                {"efac:Company": {"cac:PartyIdentification": {"cbc:ID": "ORG-0002"},
                                  "cac:PostalAddress": {"cbc:PostalZone": "75702"}}}]}}}}},
        "cac:ProcurementProjectLot": {"cac:TenderingProcess": {"cac:TenderSubmissionDeadlinePeriod": {
            "cbc:EndDate": "2026-11-19+01:00", "cbc:EndTime": end_time}}}}}}
    return {"idweb": "26-98817", "nomacheteur": "DID", "objet": "x", "perimetre": "DIRECTIVE-24", "nature": "APPEL_OFFRE",
            "code_departement": ["974", "976"], "datelimitereponse": "2026-11-19T12:00:00+00:00", "dateparution": "2026-10-14",
            "donnees": json.dumps(body)}


def test_an_eforms_overseas_notice_with_a_paris_offset_is_the_buyers_wall_time():
    # 26-98817 (/tenders/269424): DID Saint-Denis de La Reunion, "12:00:00.000+02:00" for 12:00 Reunion = 08:00 UTC
    assert from_boamp(_eforms("97476")).deadline_at == datetime(2026, 11, 19, 8, 0, tzinfo=UTC)
    # a metropolitan buyer of the same notice shape keeps Paris (WP-96): 12:00 Paris on 19 November = 11:00 UTC
    assert from_boamp(_eforms("51036")).deadline_at == datetime(2026, 11, 19, 11, 0, tzinfo=UTC)
    # an offset that is not Paris's is the notice's own
    assert from_boamp(_eforms("97476", "12:00:00+04:00")).deadline_at == datetime(2026, 11, 19, 8, 0, tzinfo=UTC)


def test_boamp_states_the_other_directives():
    assert from_boamp(_eforms("51036")).legal_basis == "32014L0024"          # cbc:RegulatoryDomain (24-21716)
    assert from_boamp({**_fns(None), "perimetre": "DIRECTIVE-25"}).legal_basis == "32014L0025"
    assert from_boamp({**_fns(None), "perimetre": "DIRECTIVE-81"}).legal_basis == "32009L0081"
    assert from_boamp(_fns(None)).legal_basis is None                         # a national form names no directive


# ------------------------------------------------------------------ TenderNed

def _nl(detail: dict, deadline: str = "2026-08-19T12:00:00") -> dict:
    return {"publicatieId": 428231, "aanbestedingNaam": "Printers", "opdrachtgeverNaam": "Defensie",
            "typePublicatie": {"code": "AAO"}, "publicatieDatum": "2026-06-09", "sluitingsDatum": deadline, "detail": detail}


def test_tenderned_takes_the_rectified_deadline_of_the_detail():
    # 428231 (/tenders/146809): rectified to 16 November, served closed on 19 August
    rec = _nl({"sluitingsDatum": "2026-11-16T12:00:00", "publicatieIDLaatsteRectificatie": 442733})
    assert from_tenderned(rec).deadline_at == datetime(2026, 11, 16, 11, 0, tzinfo=UTC)
    assert from_tenderned(_nl({})).deadline_at == datetime(2026, 8, 19, 10, 0, tzinfo=UTC)      # no detail: the list row


def test_tenderned_main_cpv_is_the_flagged_one():
    # 422883 (/tenders/146747): 34900000 listed first, 42400000 flagged as the main object
    rec = _nl({"cpvCodes": [{"code": "34900000-6", "isHoofdOpdracht": False}, {"code": "42400000-0", "isHoofdOpdracht": True},
                            {"code": "42410000-3", "isHoofdOpdracht": False}]})
    assert from_tenderned(rec).cpv_codes == ["42400000", "34900000", "42410000"]


# ------------------------------------------------------------------ German notice link

def _bkms(uri: str | None) -> dict:
    xml = (FIX / "cn_standard_defence.xml").read_text(encoding="utf-8")
    if uri:
        xml = xml.replace("<cac:TenderingTerms>", "<cac:TenderingTerms><cac:CallForTendersDocumentReference><cac:Attachment>"
                          f"<cac:ExternalReference><cbc:URI>{uri}</cbc:URI></cac:ExternalReference></cac:Attachment>"
                          "</cac:CallForTendersDocumentReference>", 1)
    return strip_personal_data({"file": "x-01.xml", "notice_id": None, "version": "01", "xml": xml})


PAGE = "https://oeffentlichevergabe.de/ui/de/search/details?noticeId=129f4d26-440e-4017-91b5-df3a10cf3f30"


def test_the_german_link_is_the_notice_and_the_platform_page_the_documents():
    opp = from_de_bkms(_bkms("https://www.evergabe-online.de/tenderdetails.html?id=543128"))
    assert opp.source_url == PAGE and opp.documents_url == "https://www.evergabe-online.de/tenderdetails.html?id=543128"


def test_a_bare_platform_home_page_is_no_documents_link():
    # /tenders/284683: https://www.meinauftrag.rib.de, which does not lead to the notice
    opp = from_de_bkms(_bkms("https://www.meinauftrag.rib.de"))
    assert opp.source_url == PAGE and opp.documents_url is None
    assert from_de_bkms(_bkms("https://www.meinauftrag.rib.de/")).documents_url is None


# ------------------------------------------------------------------ who may apply

def test_a_staff_cap_for_the_group_is_a_rule_for_companies():
    # /funding/188 RAPID: "effectif consolide de moins de 2000 salaries" (conditions_raw.rules_read, AID)
    cond = {"rules_read": {"max_group_headcount": {"value": 1999, "note": "The consolidated staff count ... under 2000.",
                                                   "quote": "effectif consolidé de moins de 2000 salariés"}}}
    who, sme, evidence = who_apply.decide(who_apply.own_text_facts(cond, None))
    assert (who, sme) == ("companies", None) and "2000" in evidence


def test_a_national_call_aimed_at_smes_is_smes_only():
    # /funding/170 Vinnova, civil-military 2027 (the served English text and the Swedish web text)
    en = ("Within the call, companies are given the opportunity to develop technology. The call for proposals is aimed at "
          "Swedish small and medium-sized enterprises (SMEs) that have innovative technology solutions. Companies can apply.")
    who, sme, evidence = who_apply.decide(who_apply.own_text_facts({}, en))
    assert (who, sme) == ("companies", True) and evidence.startswith("The call for proposals is aimed at Swedish")
    sv = {"web_text_sv": ["Utlysningen riktar sig till svenska små och medelstora företag (SMF) som har innovativa lösningar."]}
    assert who_apply.decide(who_apply.own_text_facts(sv, None))[:2] == ("companies", True)
    assert who_apply.own_text_facts({}, "Universities may apply.") == {}


def test_the_verified_sentence_on_legal_entities_names_companies():
    # /funding/125 DIGITAL-2026-SKILLS-10: the entity list was not verified; the verified sme fact quotes the call's sentence
    quote = "In order to be eligible, the applicants (beneficiaries and affiliated entities) must:\n− be legal entities (public or private bodies)"
    facts = {"sme_only": {"value": False, "quote": quote, "scope": "call_document"}}
    assert who_apply.decide(facts) == ("companies", None, quote)
    public = {"sme_only": {"value": False, "quote": "be public bodies", "scope": "call_document"}}
    assert who_apply.decide(public) == (None, None, None)


# ------------------------------------------------------------------ EU call document closing time

def test_the_call_document_time_is_used_only_for_the_portals_own_day():
    text = ("3. Deadline for submission: 1 October 2026– 17:00:00 CEST (Brussels)\n"
            "Deadline for submission: 03 March 2026 – 17:00:00 CET")
    assert eu_portal.document_closing(text, date(2026, 10, 1)) == datetime(2026, 10, 1, 15, 0, tzinfo=UTC)
    assert eu_portal.document_closing(text, date(2026, 3, 3)) == datetime(2026, 3, 3, 16, 0, tzinfo=UTC)
    assert eu_portal.document_closing(text, date(2026, 10, 2)) is None       # never a time for another day
    assert eu_portal.document_closing(None, date(2026, 10, 1)) is None
