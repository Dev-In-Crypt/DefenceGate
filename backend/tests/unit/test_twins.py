"""The identifiers that tie a national notice to its TED twin, and the rule for the rest.

The PLACSP entry below is the shape of the frigate-engine tender that QA found listed
twice on 12 October 2026 (PLACSP 2026/AR40U/00002845E and TED 661706-2026), stripped to
the elements the parser reads; the procedure identifier is the one TED publishes for it.
"""

from __future__ import annotations

from datetime import date

from dgate.db import opportunity_payload
from dgate.normalise import from_boamp
from dgate.ops import link_twins
from dgate.sources import placsp

PROCEDURE = "546636a5-bf94-45aa-a25f-25d76f8f0b91"

ENTRY = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:cbc="urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2"
      xmlns:cac="urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2"
      xmlns:cac-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2"
      xmlns:cbc-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2">
  <entry>
    <id>https://contrataciondelsectorpublico.gob.es/e/1</id>
    <updated>2026-10-09T10:00:00+02:00</updated>
    <cac-place-ext:ContractFolderStatus>
      <cbc:ContractFolderID>2026/AR40U/00002845E</cbc:ContractFolderID>
      {uuid}
      <cbc-place-ext:ContractFolderStatusCode>PUB</cbc-place-ext:ContractFolderStatusCode>
      <cac-place-ext:ValidNoticeInfo>
        <cbc-place-ext:NoticeTypeCode>DOC_CN</cbc-place-ext:NoticeTypeCode>
        <cac-place-ext:AdditionalPublicationStatus>
          <cbc-place-ext:PublicationMediaName>DOUE</cbc-place-ext:PublicationMediaName>
          <cac-place-ext:AdditionalPublicationDocumentReference>
            <cbc:IssueDate>2026-09-25</cbc:IssueDate>
          </cac-place-ext:AdditionalPublicationDocumentReference>
        </cac-place-ext:AdditionalPublicationStatus>
      </cac-place-ext:ValidNoticeInfo>
      <cac:ProcurementProject>
        <cbc:Name>Suministro de motores</cbc:Name>
      </cac:ProcurementProject>
    </cac-place-ext:ContractFolderStatus>
  </entry>
</feed>
"""


def _parse(uuid: str):
    opps, _ = placsp.parse_feed(ENTRY.format(uuid=uuid).encode("utf-8"))
    return opps[0]


# -------------------------------------------------------------- PLACSP

def test_placsp_reads_the_eforms_procedure_identifier():
    assert _parse(f'<cbc:UUID schemeName="TED">{PROCEDURE}</cbc:UUID>'
                  ).procedure_identifier == PROCEDURE


def test_placsp_writes_it_the_way_ted_does():
    spelled = f'<cbc:UUID schemeName="TED">{{{PROCEDURE.upper()}}}</cbc:UUID>'
    assert _parse(spelled).procedure_identifier == PROCEDURE


def test_placsp_ignores_an_entry_without_one_and_anything_that_is_not_a_uuid():
    assert _parse("").procedure_identifier is None
    assert _parse('<cbc:UUID schemeName="TED">not-a-uuid</cbc:UUID>').procedure_identifier is None
    assert _parse(f'<cbc:UUID schemeName="OTHER">{PROCEDURE}</cbc:UUID>').procedure_identifier is None


def test_the_doue_publication_has_a_date_and_no_number_to_match_on():
    """The DOUE `AdditionalPublicationDocumentReference` of 2,911 live entries carries an
    issue date only, so a DOUE number is not an identifier this connector can read."""
    opp = _parse("")
    assert opp.procedure_identifier is None and opp.ted_ref is None
    assert opp.published_at == date(2026, 9, 25)


def test_an_entry_without_the_identifier_keeps_its_hash():
    """The payload is hashed; a field that is empty is absent, so nothing already
    stored looks changed."""
    assert "procedure_identifier" not in opportunity_payload(_parse(""))
    assert opportunity_payload(
        _parse(f'<cbc:UUID schemeName="TED">{PROCEDURE}</cbc:UUID>'))["procedure_identifier"] == PROCEDURE


# --------------------------------------------------------------- BOAMP

def _boamp(**record) -> dict:
    return {"idweb": "26-91603", "objet": "Marche", "nomacheteur": "Ministere des Armees",
            "dateparution": "2026-09-19", "perimetre": "DIRECTIVE-81", "nature": "APPEL_OFFRE",
            "donnees": "{}", **record}


def test_boamp_reads_contractfolderid_as_the_procedure_identifier():
    assert from_boamp(_boamp(contractfolderid=PROCEDURE)).procedure_identifier == PROCEDURE
    assert from_boamp(_boamp(contractfolderid=f"{{{PROCEDURE.upper()}}}")
                      ).procedure_identifier == PROCEDURE
    assert from_boamp(_boamp(contractfolderid=[PROCEDURE])).procedure_identifier == PROCEDURE


def test_a_legacy_boamp_notice_or_a_non_uuid_folder_id_has_none():
    assert from_boamp(_boamp()).procedure_identifier is None
    assert from_boamp(_boamp(contractfolderid=None)).procedure_identifier is None
    assert from_boamp(_boamp(contractfolderid="DCE-2026-14")).procedure_identifier is None


# ------------------------------------------------------ the heuristic

def _row(nid, tnative, *, nsrc=1, ngroup=None, tgroup=None, free=True, nstatus="open",
         tstatus="open", tpub=date(2026, 9, 25), tid=None):
    return {"nid": nid, "nsrc": nsrc, "ngroup": ngroup or f"N{nid}", "free": free,
            "nstatus": nstatus, "tnative": tnative, "tid": tid or int(tnative.split("-")[0]),
            "tgroup": tgroup or tnative, "tstatus": tstatus, "tpub": tpub}


def test_a_single_candidate_on_each_side_is_linked():
    assert link_twins.unambiguous([_row(10, "661706-2026")]) == [(10, "661706-2026")]


def test_two_national_notices_for_one_ted_notice_are_neither_linked():
    rows = [_row(10, "661706-2026"), _row(11, "661706-2026")]
    assert link_twins.unambiguous(rows) == []


def test_one_national_notice_for_two_ted_procedures_is_not_linked():
    rows = [_row(10, "661706-2026"), _row(10, "700001-2026")]
    assert link_twins.unambiguous(rows) == []


def test_the_call_and_the_corrigendum_of_one_procedure_are_one_candidate():
    """Same procedure identifier on both TED notices: the newest of the notice's status
    is the one the list shows, so that is the one linked."""
    rows = [_row(10, "600001-2026", tgroup="p1", tpub=date(2026, 9, 1)),
            _row(10, "611111-2026", tgroup="p1", tpub=date(2026, 9, 20))]
    assert link_twins.unambiguous(rows) == [(10, "611111-2026")]


def test_a_rectificatif_counts_with_the_notice_it_corrects():
    rows = [_row(10, "661706-2026", ngroup="26-100"), _row(11, "661706-2026", ngroup="26-100")]
    assert link_twins.unambiguous(rows) == [(10, "661706-2026"), (11, "661706-2026")]


def test_two_notices_of_different_sources_are_two_candidates():
    rows = [_row(10, "661706-2026", nsrc=1, ngroup="A"), _row(11, "661706-2026", nsrc=2, ngroup="A")]
    assert link_twins.unambiguous(rows) == []


def test_a_row_that_is_already_linked_is_not_written_but_still_blocks_a_second_match():
    rows = [_row(10, "661706-2026", free=False), _row(11, "661706-2026")]
    assert link_twins.unambiguous(rows) == []
    assert link_twins.unambiguous([_row(10, "661706-2026", free=False)]) == []


def test_the_ted_notice_of_the_same_status_wins_over_a_newer_award():
    rows = [_row(10, "600001-2026", tgroup="p1", tstatus="open", tpub=date(2026, 9, 1)),
            _row(10, "699999-2026", tgroup="p1", tstatus="awarded", tpub=date(2026, 10, 5))]
    assert link_twins.unambiguous(rows) == [(10, "600001-2026")]
