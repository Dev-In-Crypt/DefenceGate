"""WP-119 (verification of 25 October 2026): the rules behind the rows written that day. Evidence: D:/DEFENCEGATE
TESTS/verify-oct25/data (problems.csv, av_out.txt, bw_out.txt, fid7_out.txt, rc*_out.txt)."""

from __future__ import annotations

from dgate import award_value as av
from dgate.api import main_code_first
from dgate.awards import same_name_as_buyer
from dgate.normalise import normalise_identifier, pl_number_pair, pl_unpadded_regon
from dgate.ops import org_repair, supplier_dedupe
from dgate.supplier_identity import foreign_vat


def opp(value=None, kind="total", currency="EUR", procedure=None, title="Dostawa") -> dict:
    return {"value_amount": value, "value_currency": currency if value else None, "value_kind": kind if value else None,
            "notice_subtype": "29", "title_original": title, "title_en": None, "procedure_value": procedure}


# ------------------------------------------------------------------------------------------- 1. award values

def test_a_lot_sum_of_a_few_units_never_replaces_the_notice_total():
    """Marine Alutech 676175-2026 (EUR 2 served, 76,000,000 set aside) and Surcom 436610-2026 (SEK 13 for 13,107,317)."""
    held = opp(76000000.0)
    for rec in ({"BT-161-NoticeResult": "76000000", "tender-value": ["2"]},     # a notice value and its tender
                {"tender-value": ["2"], "total-value-cur": ["EUR"]}):          # TED answers the tender only
        assert av.ted_value(rec, held) == (76000000.0, "EUR", "contract")
        assert av.ted_value_set_aside(rec, held) is None
    surcom = opp(13107317.0, currency="SEK")
    assert av.ted_value({"tender-value": ["13"], "total-value-cur": ["SEK"]}, surcom) == (13107317.0, "SEK", "contract")
    # a framework maximum whose lots' maxima are placeholders stands too
    assert av.ted_value({"BT-118-NoticeResult": "35000000", "BT-709-LotResult": ["1", "1"]}, opp(35000000.0))[0] == 35e6


def test_a_lot_sum_replaces_the_total_only_when_the_total_is_a_clean_unit_error_of_it():
    assert av.unit_error_of(7247040000, 7247040)                 # FASER 394720-2025: typed in thousands
    assert av.unit_error_of(741576016.16, 7415760.16)             # 313429-2026: the cents read as units
    assert av.unit_error_of(120969785, 1209697)                   # 142545-2026: 1,209,697.85 without its separator
    assert not av.unit_error_of(5_000_000, 50_000)                # a round hundredfold is no slip
    assert not av.unit_error_of(783464568, 7290755)               # 175814-2025: x107, the total stands
    assert not av.unit_error_of(1949370000, 229586)               # 494823-2026: x8491, the total stands
    rec = {"BT-161-NoticeResult": "741576016.16", "tender-value": ["7415760.16"]}
    assert av.ted_value(rec, opp(741576016.16, currency="PLN"))[0] == 7415760.16
    assert av.ted_value_set_aside_reason(rec, opp(741576016.16, currency="PLN")) == "lots"


def test_the_procedure_check_needs_a_billion_or_a_unit_error():
    """451107-2025: a framework of EUR 22,922,861; the 2023 contract notice of its procedure estimated EUR 23,918.70
    (x958). INCM 499753-2026 (EUR 1.159 bn against 1.45 m) stays set aside."""
    nl = opp(22922861.0, procedure=23918.70, title="Raamovereenkomst Veldkleding")
    assert av.ted_value(None, nl) == (22922861.0, "EUR", "framework")
    assert av.ted_value_set_aside(None, nl) is None
    incm = opp(1159000000.0, procedure=1450000.0)
    assert av.ted_value_set_aside_reason(None, incm) == "procedure"
    assert av.implausible_against(690_000_000, 690_000)          # 107790-2025: still a clean thousandfold


# ------------------------------------------------------------------------------------------- 2. buyer as winner

def test_a_name_match_with_the_buyer_needs_more_than_one_shared_word():
    assert not same_name_as_buyer("DEF OUEST", "PFC Ouest")      # TED 841870-2025: only "ouest"
    assert same_name_as_buyer("Het Ministerie van Defensie", "Ministerie van Defensie")
    assert same_name_as_buyer("FORSVARET", "Forsvaret")          # one word, the whole name
    assert not same_name_as_buyer("SPIE FACILITIES", "ESID RENNES")


# ------------------------------------------------------------------------------------------- 3. identifiers

NIP, REGON = "5250007282", "000177916"


def test_a_nip_and_a_regon_written_together_are_split_and_the_nip_kept():
    assert pl_number_pair(NIP + REGON) == (NIP, REGON)
    assert pl_number_pair(REGON + NIP) == (NIP, REGON)
    assert normalise_identifier(NIP + REGON, "PL") == NIP
    assert pl_number_pair("1234567890123456789") is None        # no valid split
    assert normalise_identifier("1234567890123456789", "PL") is None


def test_a_regon_without_its_leading_zeros_is_restored_and_a_teryt_code_or_case_number_is_not():
    assert pl_unpadded_regon("177916") == REGON                  # a ministry's REGON stored as a number
    assert pl_unpadded_regon("3024022") is None                  # TERYT of Gmina Duszniki
    assert pl_unpadded_regon("172020") is None                   # case 17/2020
    assert pl_unpadded_regon("12345") is None and pl_unpadded_regon("123456789") is None


def test_a_foreign_vat_number_is_recognised_as_one():
    assert foreign_vat("CZ 25288040", "ES") == "CZ25288040"
    assert foreign_vat("GB123456789", "ES") == "GB123456789"
    assert foreign_vat("DE1234567", "ES") is None                # seven digits: no German VAT number
    assert foreign_vat("ESA28015865", "ES") is None              # the country's own
    assert foreign_vat("SECRETARIADELEGADA1234567A", "ES") is None


def _row(i, name, reg, country="PL"):
    return {"id": i, "country": country, "canonical_name": name, "national_reg_no": reg}


def test_the_false_ids_plan_splits_pairs_keeps_vat_numbers_and_leaves_namesakes_apart():
    rows = [_row(1, "szpital x", NIP + REGON), _row(2, "powiat tomaszowski", "ZP272372019"),
            _row(3, "powiat tomaszowski", "IZP27252020"), _row(4, "powiat tomaszowski", "590648451"),
            _row(5, "ceska zbrojovka", "CZ25288040", "ES")]
    siblings = {(r["country"], r["canonical_name"]): [x for x in rows if (x["country"], x["canonical_name"])
                                                      == (r["country"], r["canonical_name"])] for r in rows}
    groups, respell = org_repair.plan_false_ids(rows, siblings)
    assert respell == [(1, NIP + REGON, NIP)]
    by = {g["name"]: g for g in groups}
    assert by["powiat tomaszowski"]["decision"] == "namesake" and by["powiat tomaszowski"]["merge"] == []
    assert sorted(by["powiat tomaszowski"]["clear"]) == [2, 3]
    assert by["ceska zbrojovka"]["vat"] == [(5, "CZ25288040")] and by["ceska zbrojovka"]["clear"] == []


# ------------------------------------------------------------------------------------------- 4. namesakes

def test_names_two_public_bodies_bear():
    assert org_repair.ambiguous_name("PL", "powiat tomaszowski")
    assert org_repair.ambiguous_name("PL", "miejskie przedsiebiorstwo oczyszczania")
    assert org_repair.ambiguous_name("PL", "powiatowy osrodek dokumentacji geodezyjnej i kartograficznej")
    assert not org_repair.ambiguous_name("PL", "powiat pinczowski")
    assert not org_repair.ambiguous_name("ES", "pleno del ayuntamiento de sax")      # Sax is a place
    assert not org_repair.ambiguous_name("ES", "universitat de girona")


# ------------------------------------------------------------------------------------------- 6. winners of one notice

def _w(i, name, numbers, notices):
    return supplier_dedupe.Row(i, "PL", name, set(numbers), set(), 2, False, {}, set(numbers), set(notices))


def test_two_winners_of_one_notice_are_merged_only_as_spellings_of_one_name():
    # the names as stated carry the one address, which made them 0.88 alike and let a shared number join them
    sign = _w(1, "Sign Polska Sp. z o.o., ul. Wladyslawa Szafera 3/5/7, 71-245 Szczecin", {"1132958143"},
              {106381, 119300})
    sign4 = _w(2, "Sign 4 Security Sp. z o.o., ul. Wladyslawa Szafera 3/5/7, 71-245 Szczecin", {"1132958143"},
               {106381, 119300})
    groups, left, _ = supplier_dedupe.plan([sign, sign4])
    assert groups == [] and left.get("winners_of_one_notice") == 1
    sign4.notices = {999}                                   # not side by side: the shared number joins them, as before
    assert len(supplier_dedupe.plan([sign, sign4])[0]) == 1
    magtel = _w(3, "Magtel Operaciones, S.L.U.", {"B91238469"}, {311307})
    typo = _w(4, "Magtel Opertaciones, S.L.U.", {"B91238469"}, {311307})
    assert supplier_dedupe.spelling_variants(magtel.name, typo.name)
    groups, _, _ = supplier_dedupe.plan([magtel, typo])
    assert len(groups) == 1


# ------------------------------------------------------------------------------------------- 7. the main CPV code

def test_the_archive_snapshot_lists_the_serving_rows_main_code_first():
    snap = {"cpv_codes": ["35700000", "48100000", "72000000"]}
    assert main_code_first(snap, "72000000") and snap["cpv_codes"] == ["72000000", "35700000", "48100000"]
    assert not main_code_first(snap, "72000000")                      # already first
    assert not main_code_first({"cpv_codes": ["1"]}, "2") and not main_code_first({}, "2")
