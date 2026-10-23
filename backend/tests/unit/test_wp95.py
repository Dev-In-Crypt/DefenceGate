"""WP-95 (persona round of 23 October 2026, section A1): value kinds, award winners in the older TED format, classification
honesty, the change list's kinds and lots. The evidence quoted is the personas' (D:/DEFENCEGATE TESTS/ux-oct23)."""

from __future__ import annotations

import pytest

from dgate import award_value as av
from dgate.awards import legacy_award_record, read_award, with_values
from dgate.buyer_vocab import buyer_class_of, defence_body
from dgate.changes import base_title, group_key
from dgate.classify import CATCH_ALL_CODES, classify
from dgate.normalise import _ted_other_buyers

# ------------------------------------------------------------------------------------------------ 1. value kinds


def opp(value=None, kind="total", subtype="29", title="Repair", currency="EUR") -> dict:
    return {"value_amount": value, "value_currency": currency if value else None, "value_kind": kind if value else None,
            "notice_subtype": subtype, "title_original": title, "title_en": None}


def test_a_framework_maximum_is_a_ceiling_not_a_contract_value():
    """Rheinmetall Landsysteme, TED 390572-2026 (p10 ted4.json): BT-118 EUR 11,930,000, the tenders EUR 318,900; the site
    showed 11,930,000 as the contract value. Safran 854350-2025: BT-118 DKK 97,000,000 (re-estimated 60,000,000)."""
    rec = {"BT-118-NoticeResult": "11930000.00", "BT-711-LotResult": ["318900.00"], "BT-709-LotResult": ["8020000.00", "3910000.00"]}
    assert av.ted_value(rec, opp(11930000.0)) == (11930000.0, "EUR", "framework")
    rec = {"BT-660-LotResult": ["60000000"], "BT-118-NoticeResult": "97000000", "BT-720-Tender": ["60000000"]}
    assert av.ted_value(rec, opp(97000000.0, currency="DKK")) == (97000000.0, "DKK", "framework")
    # no notice maximum, the lots' maxima summed
    assert av.ted_value({"BT-709-LotResult": ["100000", "250000"]}, opp(350000.0)) == (350000.0, "EUR", "framework")


def test_an_award_that_states_its_value_as_a_placeholder_has_only_the_estimate():
    """712069-2026: BT-720 and BT-709 are -1, BT-27 EUR 1,160,000 (the procedure's estimate), which TED put in total-value."""
    rec = {"BT-711-LotResult": ["-1"], "BT-710-LotResult": ["-1"], "BT-709-LotResult": ["-1"], "BT-720-Tender": ["-1"]}
    assert av.ted_value(rec, opp(1160000.0)) == (1160000.0, "EUR", "estimate")
    assert av.ted_value(rec, opp(None)) == (None, None, None)


def test_a_notice_value_or_the_winning_tenders_are_a_contract_value():
    """808800-2025 (DGA, Safran): BT-161 5,574,391; 518727-2026 (Romania radar, Indra): BT-720 80,817,296."""
    assert av.ted_value({"BT-161-NoticeResult": "5574391", "BT-720-Tender": ["5574391"]}, opp(5574391.0)) == (
        5574391.0, "EUR", "contract")
    assert av.ted_value({"BT-720-Tender": ["80817296"]}, opp(None, currency="RON"), ) == (80817296.0, None, "contract")
    assert av.ted_value({"BT-720-Tender": ["80817296"], "total-value-cur": ["RON"]}, opp(None))[1] == "RON"


def test_without_an_eforms_value_field_the_stored_value_is_read_as_the_mapper_chose_it():
    # an older-format notice: its total is the awarded total, unless the title says framework
    assert av.ted_value({}, opp(250000.0, subtype=None)) == (250000.0, "EUR", "contract")
    assert av.ted_value(None, opp(250000.0, subtype=None, title="Rahmenvertrag Ersatzteile")) == (250000.0, "EUR", "framework")
    assert av.ted_value(None, opp(40000.0, kind="lot_sum")) == (40000.0, "EUR", "estimate")
    assert av.ted_value(None, opp(40000.0, kind="first_lot")) == (None, None, None)
    assert av.ted_value(None, opp(0.01)) == (None, None, None)          # a placeholder is no value


@pytest.mark.parametrize("title, kind", [
    ("ACUERDO MARCO - Suministro abierto de repuestos para sostenimiento de vehículos IVECO", "framework"),
    ("2018AYM2059S - TEAR - 1º CB AM (2025/AR43U/00001894) - Suministro Abierto de repuestos", "contract"),
    ("CB en AM 23_2623 Suministro repuestos torre Pizarro Lote 2.-", "contract"),
    ("Contrato basado en el Acuerdo Marco de vehículos", "contract"),
    ("Dynamic Purchasing System for Trailers over 3500 kg", "framework"),
    ("Rahmenvereinbarung über Instandsetzung", "framework"),
    ("Accordo quadro per la manutenzione", "framework"),
    ("Suministro repuestos torre Pizarro Lote 2.", None),
    ("Adquisición de baterías de arranque", None),
    ("Amortiguadores para vehículos", None),             # "am" inside a word is no framework
])
def test_the_title_rule_tells_a_framework_from_a_call_off(title, kind):
    assert av.kind_of_title(title) == kind


def test_placsp_reads_the_contracting_system_code_before_the_title():
    assert av.placsp_kind("1", "Suministro de repuestos") == "framework"
    assert av.placsp_kind("2", None) == "framework"
    assert av.placsp_kind("3", "ACUERDO MARCO de repuestos") == "contract"
    assert av.placsp_kind(None, "ACUERDO MARCO de repuestos") == "framework"
    assert av.placsp_kind("0", "Suministro") == "contract" and av.placsp_kind("9", "Suministro") == "contract"


def test_a_call_off_names_its_framework_by_the_file_number_its_title_quotes():
    """MADZEAL: call-off 2026/AR43U/00002206E quotes 2025/AR43U/00001894, the IVECO framework 2025/AR43U/00001894E."""
    refs = av.framework_refs("2018AYM2059S - TEAR - 1º CB AM (2025/AR43U/00001894) - Suministro Abierto de repuestos")
    assert refs[:2] == ["2025/AR43U/00001894", "2025/AR43U/00001894E"]
    assert av.framework_refs("ACUERDO MARCO (2025/AR43U/00001894E)") == []     # a framework names no framework
    assert av.framework_refs("CB en AM 23_2623 Suministro repuestos") == []     # an internal number, no file number


def test_with_values_gives_the_value_to_the_one_winner_only():
    one = read_award({"winner-name": ["Rosomak S.A."], "organisation-name-tenderer": ["Rosomak S.A."],
                      "organisation-country-tenderer": ["POL"]})
    with_values(one, (1951591.8, "PLN", "contract"))
    assert one.notice_value == (1951591.8, "PLN", "contract")
    assert (one.winners[0].value_amount, one.winners[0].value_kind) == (1951591.8, "contract")
    two = read_award({"winner-name": ["Alpha GmbH", "Beta AG"], "organisation-name-tenderer": ["Alpha GmbH", "Beta AG"],
                      "organisation-country-tenderer": ["DEU", "DEU"]})
    with_values(two, (900000.0, "EUR", "framework"))
    assert two.notice_value == (900000.0, "EUR", "framework")
    assert all(w.value_amount is None and w.value_kind is None for w in two.winners)
    none = with_values(read_award({"winner-name": ["Alpha GmbH"], "organisation-name-tenderer": ["Alpha GmbH"],
                                   "organisation-country-tenderer": ["DEU"]}), (None, None, None))
    assert none.notice_value is None and none.winners[0].value_kind is None


# ------------------------------------------------------------------------------- 3. winners of older-format notices

R209 = b"""<?xml version="1.0" encoding="UTF-8"?>
<TED_EXPORT xmlns="http://publications.europa.eu/resource/schema/ted/R2.0.9/publication">
 <FORM_SECTION><F03_2014 LG="IT" CATEGORY="ORIGINAL" FORM="F03">
  <AWARD_CONTRACT ITEM="1"><AWARDED_CONTRACT><CONTRACTORS>
   <CONTRACTOR><ADDRESS_CONTRACTOR><OFFICIALNAME>FINCANTIERI S.P.A.</OFFICIALNAME><NATIONALID>00397130584</NATIONALID>
     <TOWN>Trieste</TOWN><COUNTRY VALUE="IT"/><E_MAIL>someone@example.it</E_MAIL></ADDRESS_CONTRACTOR></CONTRACTOR>
  </CONTRACTORS></AWARDED_CONTRACT></AWARD_CONTRACT>
  <AWARD_CONTRACT ITEM="2"><AWARDED_CONTRACT><CONTRACTORS>
   <CONTRACTOR><ADDRESS_CONTRACTOR><OFFICIALNAME>Mario Rossi</OFFICIALNAME><COUNTRY VALUE="IT"/></ADDRESS_CONTRACTOR></CONTRACTOR>
  </CONTRACTORS></AWARDED_CONTRACT></AWARD_CONTRACT>
 </F03_2014></FORM_SECTION></TED_EXPORT>"""

R208 = b"""<?xml version="1.0" encoding="UTF-8"?>
<TED_EXPORT xmlns="http://publications.europa.eu/TED_schema/Export">
 <FORM_SECTION><CONTRACT_AWARD_DEFENCE CATEGORY="ORIGINAL" FORM="18" LG="EN">
  <FD_CONTRACT_AWARD_DEFENCE><AWARD_OF_CONTRACT_DEFENCE ITEM="1">
   <ECONOMIC_OPERATOR_NAME_ADDRESS><CONTACT_DATA_WITHOUT_RESPONSIBLE_NAME_CHP>
     <ORGANISATION><OFFICIALNAME>Babcock Marine Ltd</OFFICIALNAME></ORGANISATION>
     <TOWN>Bristol</TOWN><COUNTRY VALUE="UK"/>
   </CONTACT_DATA_WITHOUT_RESPONSIBLE_NAME_CHP></ECONOMIC_OPERATOR_NAME_ADDRESS>
  </AWARD_OF_CONTRACT_DEFENCE></FD_CONTRACT_AWARD_DEFENCE>
 </CONTRACT_AWARD_DEFENCE></FORM_SECTION></TED_EXPORT>"""


def test_the_winners_of_an_older_format_notice_are_read_from_its_document_with_the_same_rules():
    """TED 40783-2024 (Italian Navy, warship repair, defence directive, older format): the search API names no winner,
    so Fincantieri had no win. Name, country and national number only; a natural person is left out."""
    rec = legacy_award_record(R209)
    assert rec["winner-name"] == ["FINCANTIERI S.P.A.", "Mario Rossi"]
    assert rec["organisation-country-tenderer"] == ["IT", "IT"]
    assert "someone@example.it" not in str(rec) and "Trieste" not in str(rec)
    read = read_award(rec)
    assert [(w.name, w.country, w.identifier) for w in read.winners] == [("FINCANTIERI S.P.A.", "IT", "00397130584")]
    assert read.counts["skipped_person"] == 1
    assert "Mario Rossi" not in str(read.redacted)


def test_the_older_defence_form_and_its_uk_country_code_are_read():
    read = read_award(legacy_award_record(R208))
    assert [(w.name, w.country) for w in read.winners] == [("Babcock Marine Ltd", "GB")]


def test_a_document_that_is_not_xml_or_names_nobody_gives_no_winner():
    assert not legacy_award_record(b"<html>not found").get("winner-name")
    assert legacy_award_record(b"<TED_EXPORT/>")["winner-name"] == []


# ----------------------------------------------------------------------------------- 4. classification honesty

MANY = [f"{4500 + i:04d}0000" for i in range(60)]          # 60 civil codes of a catch-all purchasing system


def test_a_civil_buyers_catch_all_notice_is_not_defence_for_one_military_code_that_is_not_its_main_code():
    """Ayuntamiento de Bétera, Cetursa Sierra Nevada, Molina de Segura: 74 to 314 codes, one military, counted as defence."""
    codes = MANY + ["35420000"]
    sig = classify(legal_basis=None, cpv_codes=codes, buyer_is_defence=False, buyer_class="municipal")
    assert sig.military_cpv and not sig.is_defence and sig.catch_all_civil
    assert any("catch-all" in r for r in sig.reasons)
    # the military code first (its main code): defence, as before
    assert classify(legal_basis=None, cpv_codes=["35420000"] + MANY, buyer_is_defence=False, buyer_class="municipal").is_defence
    # a defence buyer, the directive, a buyer named as a defence body or not classified: defence, as before
    assert classify(legal_basis=None, cpv_codes=codes, buyer_is_defence=True, buyer_class="defence").is_defence
    assert classify(legal_basis="32009L0081", cpv_codes=codes, buyer_is_defence=False, buyer_class="municipal").is_defence
    assert classify(legal_basis=None, cpv_codes=codes, buyer_is_defence=False, buyer_class="defence").is_defence
    assert classify(legal_basis=None, cpv_codes=codes, buyer_is_defence=False, buyer_class=None).is_defence
    assert classify(legal_basis=None, cpv_codes=codes, buyer_is_defence=False, buyer_class="other",
                    linked_defence=True).is_defence
    # up to CATCH_ALL_CODES codes: the military code counts wherever it is
    few = MANY[:CATCH_ALL_CODES - 1] + ["35420000"]
    assert classify(legal_basis=None, cpv_codes=few, buyer_is_defence=False, buyer_class="other").is_defence


def test_the_latvian_interiors_provision_agency_is_a_security_body_not_a_defence_body():
    """Nodrošinājuma valsts aģentūra buys for the State Police (TED 711894-2026, with Valsts policija)."""
    assert buyer_class_of("Nodrošinājuma valsts aģentūra", "LV") == "security"
    assert defence_body("Nodrošinājuma valsts aģentūra", "LV").label is None
    assert buyer_class_of("Nodrošinājuma pavēlniecība", "LV") == "defence"      # the armed forces' logistics command


def test_the_derived_list_rejects_it_and_the_cleanup_unflags_a_rejected_name():
    from dgate.ops.buyer_cleanup import rejected_names
    from dgate.pipeline import load_derived_rows

    assert ("LV", "nodrosinajuma valsts agentura") in rejected_names()
    assert "nodrosinajuma valsts agentura" not in {r["name"] for r in load_derived_rows()}


def test_every_buyer_of_a_joint_procurement_is_kept():
    assert _ted_other_buyers({"lav": ["Nodrošinājuma valsts aģentūra", "Valsts policija"]}) == ["Valsts policija"]
    assert _ted_other_buyers({"eng": ["A"], "fra": ["A", "B"]}) is None       # the block the first name is read from
    assert _ted_other_buyers(["A", "B", "A", "C"]) == ["B", "C"]
    assert _ted_other_buyers(None) is None


# ------------------------------------------------------------------------------------------------- 5. /changes

def test_the_lots_of_one_notice_compare_equal_once_the_lot_number_is_off():
    assert base_title("Część II: Dostawa smaru") == base_title("Część III: Dostawa smaru") == "dostawa smaru"
    assert base_title("Suministro repuestos torre Pizarro Lote 2.") == base_title("Suministro repuestos torre Pizarro, Lote 1")
    assert base_title("Nákup X - část 4") == "nákup x" and base_title("Lot n°1 - Achat de X") == "achat de x"
    assert base_title("Dostawa amunicji 9 mm") == "dostawa amunicji 9 mm"     # a number that is no lot stays


def test_two_notices_are_one_row_only_with_the_same_buyer_title_date_kind_day_and_changes():
    row = {"buyer_org_id": 7, "buyer_name_raw": "45 WOG", "title_original": "Usługi sprzątania - część 1", "published_at": "2026-10-20"}
    ev = {"kind": "new", "day": "2026-10-21", "changes": []}
    same = group_key({**row, "title_original": "Usługi sprzątania - część 2"}, ev)
    assert group_key(row, ev) == same
    assert group_key(row, {**ev, "kind": "award"}) != same
    assert group_key({**row, "buyer_org_id": 8}, ev) != same
    assert group_key({**row, "published_at": "2026-10-19"}, ev) != same
