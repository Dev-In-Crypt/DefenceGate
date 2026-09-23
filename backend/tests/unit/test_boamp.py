"""The French connector (BOAMP).

Fixtures are the shapes the live API returned on 22 September 2026: an eForms
notice under the defence directive, a simplified French form, and a 2016 notice
in the old schema. All three are in one dataset, and all three have to map.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from dgate.normalise import from_boamp, strip_personal_data
from dgate.sources import boamp as fr

EFORMS_DEFENCE = {
    "idweb": "26-90291",
    "id": "26_90291",
    "objet": "Collecte et traitement de dechets",
    "nomacheteur": "Centre de soutien technique et administratif",
    "dateparution": "2026-09-19",
    "datelimitereponse": "2026-10-15T12:00:00+00:00",
    "perimetre": "DIRECTIVE-81",
    "nature": "APPEL_OFFRE",
    "nature_libelle": "Avis de marche",
    "procedure_libelle": "Procedure Ouverte",
    "etat": "INITIAL",
    "donnees": json.dumps({"EFORMS": {"ContractNotice": {
        "cac:ProcurementProject": {
            "cbc:Description": {"@languageID": "FRA", "#text": "Collecte de dechets dangereux"},
            "cac:MainCommodityClassification": {
                "cbc:ItemClassificationCode": {"@listName": "cpv", "#text": "90500000"}},
            "cac:RequestedTenderTotal": {
                "cbc:EstimatedOverallContractAmount": {"@currencyID": "EUR", "#text": "7000000"}},
        },
        "ext:UBLExtensions": {"efac:Organizations": {"efac:Organization": {"efac:Company": {
            "cbc:Name": "Ministere des Armees",
            "cac:Contact": {"cbc:Name": "Joseph COLIN", "cbc:Telephone": "0383193494",
                            "cbc:ElectronicMail": "joseph.colin@intradef.gouv.fr"}}}}},
    }}}, ensure_ascii=False),
}

FN_SIMPLE = {
    "idweb": "26-89664",
    "objet": "Rehabilitation du batiment de la Police Municipale",
    "nomacheteur": "Commune de Beaucaire",
    "dateparution": "2026-09-16",
    "datelimitereponse": None,
    "perimetre": "FNSimple",
    "nature": "APPEL_OFFRE",
    "donnees": json.dumps({"FNSimple": {"initial": {
        "natureMarche": {"codeCPV": {"objetPrincipal": {"classPrincipale": "45000000"}},
                         "description": "Travaux pour la rehabilitation du batiment"},
        "lots": {"lot": [{"codeCPV": {"objetPrincipal": {"classPrincipale": "45262500"}},
                          "description": "Maconneries"}]},
        "communication": {"nomContact": "M Le Maire", "telContact": "+33 466599003",
                          "adresseMailContact": "pierre@beaucaire.fr"},
    }}}, ensure_ascii=False),
}

OLD_SCHEMA = {
    "idweb": "16-88033",
    "objet": "Travaux de voirie",
    "nomacheteur": "Commune de Digne",
    "dateparution": "2016-06-15",
    "perimetre": "CMP-2006",
    "nature": "APPEL_OFFRE",
    "donnees": json.dumps({"IDENTITE": {"DENOMINATION": "Commune de Digne",
                                        "TEL": "04-92-74-80-13"},
                           "OBJET": {"OBJET_COMPLET": "Travaux de voirie communale"}}),
}


# ------------------------------------------------------------- the query

def test_a_day_is_the_window_and_the_order_is_stable():
    """Paging is capped at 10,000 results, and a French day is 106 to 471
    notices. Ordered by idweb, not by date: within one day the dates are equal,
    and an unstable order across pages is how Poland lost 4.5% of a day."""
    q = fr.day_query(date(2026, 9, 16))
    assert q["where"] == "dateparution = date'2026-09-16'"
    assert q["order_by"] == "idweb"
    assert q["limit"] == 100


class _FakeResponse:
    def __init__(self, records, total):
        self._records, self._total = records, total

    def raise_for_status(self):
        pass

    def json(self):
        return {"total_count": self._total, "results": self._records}


class _FakeClient:
    """Serves a day of notices in pages, recording what was asked."""

    def __init__(self, records):
        self.records = records
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(dict(params))
        offset = params.get("offset", 0)
        limit = params.get("limit", fr.PAGE_SIZE)
        return _FakeResponse(self.records[offset:offset + limit], len(self.records))


def test_paging_follows_offsets_to_the_end_of_a_day():
    client = _FakeClient([{"idweb": f"26-{i}"} for i in range(250)])
    got = list(fr.search(fr.day_query(date(2026, 9, 16)), client=client))
    assert [r["idweb"] for r in got] == [f"26-{i}" for i in range(250)]
    assert [c["offset"] for c in client.calls] == [0, 100, 200]


def test_a_query_that_hits_the_api_cap_is_an_error_not_a_smaller_day():
    """offset + limit above 10,000 is rejected by the API. A day that reached
    it was cut short, and recording it as complete would be a silent hole."""
    client = _FakeClient([{"idweb": f"26-{i}"} for i in range(500)])
    with pytest.raises(RuntimeError, match="cut short"):
        list(fr.search(fr.day_query(date(2026, 9, 16)), client=client, max_offset=200))


def test_a_notice_repeated_at_a_day_boundary_is_yielded_once():
    client = _FakeClient([{"idweb": "26-1"}])
    got = list(fr.fetch_window(days_back=2, client=client, today=date(2026, 9, 16)))
    assert [r["idweb"] for r in got] == ["26-1"]
    assert len({c["where"] for c in client.calls}) == 3


# ------------------------------------------------------------ the mapping

def test_the_defence_directive_is_read_from_the_source_not_inferred():
    """`perimetre` states the regime. DIRECTIVE-81 is Directive 2009/81/EC,
    the same legal-basis signal TED gives, said by the publisher."""
    opp = from_boamp(EFORMS_DEFENCE)
    assert opp.legal_basis == "32009L0081"
    assert opp.status_native == "DIRECTIVE-81/APPEL_OFFRE"
    assert from_boamp(FN_SIMPLE).legal_basis is None


def test_an_eforms_notice_maps_completely():
    opp = from_boamp(EFORMS_DEFENCE)
    assert opp.source_code == "fr_boamp"
    assert opp.native_id == "26-90291"
    assert opp.country == "FR"
    assert opp.buyer_name_raw == "Centre de soutien technique et administratif"
    assert opp.published_at == date(2026, 9, 19)
    assert opp.deadline_at.isoformat() == "2026-10-15T12:00:00+00:00"
    assert opp.cpv_codes == ["90500000"]
    assert (opp.value_amount, opp.value_currency) == (7000000.0, "EUR")
    assert opp.source_url.endswith("26-90291%22")


def test_the_simplified_french_form_maps_too():
    """Three notice shapes share one dataset; a connector that reads only the
    newest would silently drop most of the file."""
    opp = from_boamp(FN_SIMPLE)
    assert opp.cpv_codes == ["45000000", "45262500"]
    assert opp.buyer_name_raw == "Commune de Beaucaire"
    assert opp.deadline_at is None


def test_a_notice_from_before_cpv_was_recorded_gets_no_invented_codes():
    """2016 notices carry no CPV. An empty list is honest; a guess is not."""
    opp = from_boamp(OLD_SCHEMA)
    assert opp.cpv_codes == []
    assert opp.published_at == date(2016, 6, 15)
    assert opp.title_original == "Travaux de voirie"


def test_a_notice_without_an_identifier_is_refused():
    with pytest.raises(ValueError):
        from_boamp({"objet": "x"})


def test_an_unparsable_body_still_yields_the_notice():
    """The columns alone describe the notice. A broken body must not make it
    disappear from the archive."""
    opp = from_boamp({**FN_SIMPLE, "donnees": "{not json"})
    assert opp.native_id == "26-89664"
    assert opp.cpv_codes == []


# --------------------------------------------------------- personal data

def test_contact_details_are_removed_from_every_shape_before_landing():
    """France hides personal data one level down, inside the `donnees` string:
    a flat key filter sees none of it."""
    for record in (EFORMS_DEFENCE, FN_SIMPLE, OLD_SCHEMA):
        clean = json.dumps(strip_personal_data(record), ensure_ascii=False)
        for trace in ("joseph.colin@intradef.gouv.fr", "0383193494", "Joseph COLIN",
                      "pierre@beaucaire.fr", "+33 466599003", "M Le Maire",
                      "04-92-74-80-13"):
            assert trace not in clean, trace


def test_scrubbing_keeps_everything_that_is_not_a_contact():
    clean = strip_personal_data(EFORMS_DEFENCE)
    body = json.dumps(clean["donnees"], ensure_ascii=False)
    assert "Ministere des Armees" in body
    assert "90500000" in body
    assert from_boamp(clean).cpv_codes == ["90500000"]


def test_a_body_that_cannot_be_parsed_is_dropped_rather_than_stored_unchecked():
    """Unparsable means unscrubbable, and an unscrubbed body may carry names."""
    clean = strip_personal_data({**FN_SIMPLE, "donnees": "{not json"})
    assert clean["donnees"] is None


def test_an_address_written_into_prose_is_redacted_too():
    """Named fields can be dropped by name; an address typed into a sentence
    has to be found. 300 recent TED payloads carried six of them."""
    record = {**FN_SIMPLE, "donnees": json.dumps({"FNSimple": {"initial": {
        "informComplementaire": {
            "autres": "Renseignements: greffe.ta-nice@juradm.fr ou 04 92 00 00 00"}}}})}
    clean = json.dumps(strip_personal_data(record), ensure_ascii=False)
    assert "greffe.ta-nice@juradm.fr" not in clean
    assert "[email removed]" in clean
    assert "Renseignements" in clean


def test_redaction_reaches_every_source_not_only_france():
    from dgate.normalise import strip_personal_data as strip

    ted_notice = {"notice-identifier": ["1-2026"],
                  "notice-title": {"eng": "Write to helpdesk@logintrade.net for access"}}
    clean = json.dumps(strip(ted_notice), ensure_ascii=False)
    assert "helpdesk@logintrade.net" not in clean and "[email removed]" in clean


def test_text_without_an_address_is_left_exactly_as_it_was():
    record = {"notice-identifier": ["1"], "notice-title": {"eng": "Supply of 35 helmets @ 2 units"}}
    assert strip_personal_data(record) == record


def test_an_address_after_an_escaped_newline_does_not_break_the_body():
    """Redaction has to happen on what the body decodes to, never on the JSON
    text: matching an address together with the `n` of a preceding \n escape
    left a dangling backslash, and the archive entry no longer parsed."""
    record = {**FN_SIMPLE, "donnees": json.dumps({"FNSimple": {"initial": {
        "informComplementaire": {
            "autres": "Mairie\nRoquebrune\n04.92.10.48.81\nrestauration@mairie.fr"}}}})}
    clean = strip_personal_data(record)
    body = json.loads(clean["donnees"])            # must still be readable JSON
    text = body["FNSimple"]["initial"]["informComplementaire"]["autres"]
    assert "restauration@mairie.fr" not in text
    assert "[email removed]" in text
    assert "Roquebrune" in text and text.count("\n") == 3
    assert fr.notice_body(clean) != {}
