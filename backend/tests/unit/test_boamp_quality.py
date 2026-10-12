"""BOAMP: CPV in every notice shape, the value a notice states, the rectificatif link.

Closes finding F10 of the data-quality audit of 12 October 2026. The fixtures in
`tests/fixtures/boamp_notices.json` are real records of the production raw store
reduced to what the mappers read (the CPV, value, reference and administrative
columns; no free text beyond a title, no contacts, no parties):

    legacy Boamp_v230.xsd   2015-2020, the shape 4,175 of the 4,185 stored rows have
    FNSimple                the simplified national form, 2023 onwards
    EFORMS                  the European standard forms, 2023 onwards

Until then `_fr_cpv` read only the last two, so every notice of 2015-2020 had no
CPV although it carried one, and `_fr_value` read only `EstimatedOverallContractAmount`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dgate.db import opportunity_payload
from dgate.normalise import _fr_amount, from_boamp

NOTICES = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "boamp_notices.json")
    .read_text(encoding="utf-8"))


def _map(name: str):
    return from_boamp(NOTICES[name])


def _synthetic(body: dict, **columns) -> dict:
    return {"idweb": "26-1", "objet": "x", "nomacheteur": "Y", "dateparution": "2026-10-01",
            "perimetre": "DIRECTIVE-81", "nature": "APPEL_OFFRE", "donnees": json.dumps(body),
            **columns}


# ----------------------------------------------------------------- CPV

@pytest.mark.parametrize("name,expected", [
    # legacy: one block, a list of blocks, a block with alphanumeric supplementary
    # codes, lots repeating the notice's own code, an award, a rectificatif
    ("single_cpv_fnf", ["35111100"]),
    ("cpv_list", ["34730000", "35640000", "35600000"]),
    ("cpv_supplementary", ["37412240"]),
    ("cpv_lots", ["63712600", "31610000", "45233293", "50100000"]),
    ("cpv_fns_list_award", ["35520000", "44541000"]),
    ("rectificatif_cpv_list", ["35520000", "34522300", "35500000", "35521100"]),
])
def test_the_legacy_schema_carries_its_cpv_and_none_is_lost(name, expected):
    """`OBJET.CPV.PRINCIPAL` is the notice's main code: 150 of 150 sampled
    2015-2020 notices have it, and none of them was read."""
    assert _map(name).cpv_codes == expected


def test_supplementary_vocabulary_is_not_a_cpv_code():
    """`SUPPLEMENTAIRE` mixes CPV codes with the four-character supplementary
    list (`AB25`). Only eight digits are a CPV code."""
    body = {"OBJET": {"CPV": {"PRINCIPAL": "37412240",
                              "SUPPLEMENTAIRE": ["AB25", "BA08", "45233293"]}}}
    assert from_boamp(_synthetic(body)).cpv_codes == ["37412240", "45233293"]


def test_a_rectificatifs_cpv_is_what_it_now_reads_not_what_it_corrects():
    """Boamp_v240.xsd: `RECTIF.MODIFICATION.CPV` says INIT (the code being
    corrected) and LIRE (the code it should read)."""
    body = {"OBJET": {"CPV": {"PRINCIPAL": "35111100"}},
            "RECTIF": {"MODIFICATION": {"CPV": {"INIT": {"PRINCIPAL": "35111100"},
                                                  "LIRE": {"PRINCIPAL": "35121000"}}}}}
    assert from_boamp(_synthetic(body)).cpv_codes == ["35111100", "35121000"]


@pytest.mark.parametrize("name", [n for n, rec in NOTICES.items()
                                  if "FNSimple" in rec["donnees"] or "EFORMS" in rec["donnees"]])
def test_the_two_modern_shapes_still_read(name):
    """The shapes read before the change give the same answer after it."""
    codes = _map(name).cpv_codes
    assert codes and len(codes) == len(set(codes))
    assert all(len(c) == 8 and c.isdigit() for c in codes)


def test_every_sampled_notice_of_every_shape_has_a_cpv():
    """24 real notices, 2015 to 2026, three schemas: none is left without."""
    assert [n for n in NOTICES if not _map(n).cpv_codes] == []


def test_a_notice_with_no_cpv_block_gets_no_invented_code():
    assert from_boamp(_synthetic({"OBJET": {"TITRE_MARCHE": "Travaux"}})).cpv_codes == []


# --------------------------------------------------------------- values

@pytest.mark.parametrize("name,expected", [
    # awarded: the total, then the single decision
    ("award_total_and_decision", (1150000.0, "EUR")),
    ("award_decision_only", (514419.96, "EUR")),
    # estimated: CARACTERISTIQUES.VALEUR, ACCORD_CADRE.VALEUR (not the first lot's)
    ("features_value", (1120000.0, "EUR")),
    ("framework_value_and_features", (440000.0, "EUR")),
    ("lots_with_values", (280000.0, "EUR")),
    # the estimate an award was made against, when it is all the notice says
    ("award_estimate_only", (120000.0, "EUR")),
    # a framework with only a range: the ceiling, never the bottom
    ("framework_min_max", (16400000.0, "EUR")),
    # nothing stated
    ("award_without_value", (None, None)),
])
def test_the_legacy_value_is_read_by_what_it_means(name, expected):
    opp = _map(name)
    assert (opp.value_amount, opp.value_currency) == expected


def test_an_award_value_comes_before_the_estimate_the_notice_repeats():
    """eForms award notices repeat the procedure's estimate. The award is the fact."""
    opp = _map("eforms_award_total")
    assert (opp.value_amount, opp.value_currency) == (57500000.0, "EUR")
    body = NOTICES["eforms_award_total"]["donnees"]
    estimated = body["EFORMS"]["ContractAwardNotice"]["cac:ProcurementProject"][
        "cac:RequestedTenderTotal"]["cbc:EstimatedOverallContractAmount"]["#text"]
    assert float(estimated) != opp.value_amount


def test_an_eforms_notice_value_is_the_procedures_not_a_lots():
    opp = _map("eforms_cn_procedure_and_lot")
    assert (opp.value_amount, opp.value_currency) == (255000.0, "EUR")


def test_an_eforms_award_that_states_only_a_framework_ceiling_gets_the_ceiling():
    opp = _map("eforms_award_framework_only")
    assert (opp.value_amount, opp.value_currency) == (1000000.0, "EUR")


def test_the_simplified_form_estimate_and_range():
    point = _map("fnsimple_point_estimate")
    assert point.value_amount and point.value_currency == "EUR"
    assert _map("fnsimple_range").value_amount == 140000.0     # valeurHaute, not valeurBasse (1)


def test_a_zero_estimate_is_not_stated():
    """The simplified form writes 0 and 0.00 for a lot the buyer left blank."""
    assert _map("fnsimple_lot_zero").value_amount is None


def test_two_lots_with_their_own_values_are_not_a_notice_value():
    """No notice total and several lots: the first lot is not the notice."""
    def lot(amount: str) -> dict:
        return {"cac:ProcurementProject": {"cac:RequestedTenderTotal": {
            "cbc:EstimatedOverallContractAmount": {"@currencyID": "EUR", "#text": amount}}}}

    body = {"EFORMS": {"ContractNotice": {"cac:ProcurementProjectLot": [lot("100"), lot("200")]}}}
    assert from_boamp(_synthetic(body)).value_amount is None
    one = {"EFORMS": {"ContractNotice": {"cac:ProcurementProjectLot": lot("100")}}}
    assert from_boamp(_synthetic(one)).value_amount == 100.0


def test_two_award_decisions_without_a_total_are_not_a_notice_value():
    def decision(amount: str) -> dict:
        return {"RENSEIGNEMENT": {"MONTANT": {"@DEVISE": "EUR", "#text": amount}}}

    body = {"ATTRIBUTION": {"DECISION": [decision("10"), decision("20")]}}
    assert from_boamp(_synthetic(body)).value_amount is None
    with_total = {"ATTRIBUTION": {"VALEUR_TOTALE": {"@DEVISE": "EUR", "#text": "30"},
                                  "DECISION": [decision("10"), decision("20")]}}
    assert from_boamp(_synthetic(with_total)).value_amount == 30.0


def test_the_currency_is_the_one_the_notice_states_and_is_never_converted():
    body = {"OBJET": {"CARACTERISTIQUES": {"VALEUR": {"@DEVISE": "GBP", "#text": "250000"}}}}
    opp = from_boamp(_synthetic(body))
    assert (opp.value_amount, opp.value_currency) == (250000.0, "GBP")


def test_a_notice_that_states_no_currency_is_taken_as_euro():
    """The only place EUR is assumed: a French notice that gives an amount and no
    currency. The legacy schema makes DEVISE mandatory, so this is malformed input."""
    body = {"OBJET": {"CARACTERISTIQUES": {"VALEUR": {"#text": "250000"}}}}
    assert from_boamp(_synthetic(body)).value_currency == "EUR"


def test_a_currency_that_is_not_a_code_drops_the_value_rather_than_guessing():
    body = {"OBJET": {"CARACTERISTIQUES": {"VALEUR": {"@DEVISE": "EUROS", "#text": "250000"}}}}
    opp = from_boamp(_synthetic(body))
    assert (opp.value_amount, opp.value_currency) == (None, None)


@pytest.mark.parametrize("raw,expected", [
    ("12500", 12500.0), ("12500.00", 12500.0), ("12 500,50", 12500.5), (12500, 12500.0),
    ("0", None), ("0.00", None), ("-5", None), ("", None), (None, None), ("abc", None),
    ("1,234.50", None),                    # ambiguous grouping: not guessed
    ("1" + "0" * 14, None),                # does not fit NUMERIC(16,2)
    (True, None),
])
def test_amounts_are_parsed_strictly(raw, expected):
    assert _fr_amount(raw) == expected


# --------------------------------------------------- rectificatif link

def test_a_rectificatif_names_the_notice_it_corrects():
    opp = _map("rectificatif_one_link")
    assert opp.related_native_id == "16-45339"


def test_a_legacy_rectificatif_is_linked_by_its_own_reference_not_by_list_position():
    """`annonce_lie` lists the corrected notice and its earlier rectificatifs. In
    3 of 198 stored notices the corrected one is second; the notice's own
    `RECTIF.ANNONCE_ANTERIEUR` is the authority."""
    body = {"RECTIF": {"ANNONCE_ANTERIEUR": {"REFERENCE": {"IDWEB": "14-180286"}}}}
    record = _synthetic(body, etat="RECTIFICATIF",
                        annonce_lie=["13-59899", "14-180286", "15-29360"])
    assert from_boamp(record).related_native_id == "14-180286"


def test_a_modern_rectificatif_with_one_link_is_linked():
    opp = _map("eforms_rectificatif")
    assert opp.related_native_id == NOTICES["eforms_rectificatif"]["annonce_lie"][0]
    fn = _map("fnsimple_rectificatif")
    assert fn.related_native_id == NOTICES["fnsimple_rectificatif"]["annonce_lie"][0]


def test_a_rectificatif_with_several_links_and_no_reference_is_left_unlinked():
    """The immediate parent is not stated; a guess could hide an award correction
    behind the tender it belongs to."""
    assert _map("eforms_rectificatif_two_links").related_native_id is None


def test_a_notice_that_is_not_a_rectificatif_is_not_linked_by_its_annonce_lie():
    """An award links to its tender through `annonce_lie` too. That is another
    relation and is not what this column means."""
    assert NOTICES["award_total_and_decision"]["annonce_lie"]
    assert _map("award_total_and_decision").related_native_id is None


def test_a_rectificatif_that_points_at_itself_is_not_linked():
    body = {"RECTIF": {"ANNONCE_ANTERIEUR": {"REFERENCE": {"IDWEB": "26-1"}}}}
    assert from_boamp(_synthetic(body, etat="RECTIFICATIF")).related_native_id is None


def test_the_link_is_in_the_archived_payload_only_when_there_is_one():
    """So no existing content hash moves: an empty link is simply absent."""
    assert "related_native_id" not in opportunity_payload(_map("award_total_and_decision"))
    assert opportunity_payload(_map("rectificatif_one_link"))["related_native_id"] == "16-45339"


# --------------------------------------------------------------- TED link

def test_a_boamp_record_states_no_ted_publication_number_of_its_own():
    """Recorded finding. The only JOUE/TED numbers in a record are those of
    *previous* notices (`PUBLICATION_JOUE` under ANNONCE_ANTERIEUR), which are
    not this notice's, so `ted_ref` stays empty rather than naming the parent."""
    assert all(from_boamp(rec).ted_ref is None for rec in NOTICES.values())
