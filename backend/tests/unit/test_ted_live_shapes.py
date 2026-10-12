"""Parsing and classification against payloads taken from the live TED API.

The fixture in `tests/fixtures/ted_live_notices.json` is four real notices
fetched on 7 September 2026, with personal-data fields stripped. They are here
because every defect these tests cover was invisible to hand-written fixtures
and appeared the moment the connector met the real API:

  550462-2026  a volunteer fire brigade buying a fire engine: CPV 35110000, in
               the defence CPV division, and not defence
  550530-2026  ammunition under Directive 2009/81/EC: genuinely defence
  550510-2026  engineering services whose "security clearance" field holds the
               Regulation (EU) 2022/576 sanctions declaration
  551365-2026  a cleaning contract whose "security clearance" field asks for
               criminal-record certificates for the cleaning staff
"""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from dgate import db
from dgate.api import effective_status
from dgate.classify import classify
from dgate.normalise import (
    _ISO3_TO_2,
    TED_STATUS_BY_TYPE,
    _country2,
    _parse_date,
    _ted_buyer_identifier,
    from_ted,
    strip_personal_data,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ted_live_notices.json"
NOTICES = {n["publication-number"]: n for n in json.loads(FIXTURE.read_text(encoding="utf-8"))}


def parsed(pub: str):
    return from_ted(strip_personal_data(NOTICES[pub]))


def verdict(pub: str):
    o = parsed(pub)
    return o, classify(
        legal_basis=o.legal_basis,
        cpv_codes=o.cpv_codes,
        buyer_is_defence=False,
        security_clearance_text="present" if o.security_clearance_required else None,
        nda_required=o.nda_required,
    )


# --------------------------------------------------------------- structure

@pytest.mark.parametrize("pub", sorted(NOTICES))
def test_every_live_notice_parses(pub):
    o = parsed(pub)
    assert o.native_id and o.country and o.title_original


def test_native_id_is_the_publication_number_not_the_uuid():
    """notice-identifier is a UUID that resolves nowhere; the publication
    number is what TED puts in its URLs and what a buyer can quote."""
    o = parsed("550530-2026")
    assert o.native_id == "550530-2026"
    assert o.native_id != NOTICES["550530-2026"]["notice-identifier"]


def test_source_url_points_at_the_readable_notice_page():
    o = parsed("550530-2026")
    assert o.source_url == "https://ted.europa.eu/en/notice/-/detail/550530-2026"
    assert not o.source_url.endswith("/xml"), "an XML link is not something a person reads"


def test_title_is_taken_in_the_notices_own_language():
    """TED returns the title in all 24 EU languages at once. Taking whichever
    key comes first put a Hungarian title on a Polish notice."""
    o = parsed("550462-2026")
    assert o.original_language == "PL"
    assert o.title_original == NOTICES["550462-2026"]["notice-title"]["pol"]


def test_english_title_comes_from_the_source_not_a_translation():
    o = parsed("550462-2026")
    assert o.title_en == NOTICES["550462-2026"]["notice-title"]["eng"]
    assert o.title_en != o.title_original


def test_cpv_duplicates_from_the_source_are_collapsed():
    raw = NOTICES["550530-2026"]["classification-cpv"]
    assert len(raw) > len(set(raw)), "the fixture really does repeat codes"
    o = parsed("550530-2026")
    assert len(o.cpv_codes) == len(set(o.cpv_codes))


def test_scalar_dispatch_date_with_z_suffix_parses():
    o = parsed("550462-2026")
    assert o.published_at is not None


# ------------------------------------------------------------ verdicts

def test_ammunition_under_the_defence_directive_is_defence():
    o, sig = verdict("550530-2026")
    assert sig.is_defence
    assert sig.legal_basis and sig.cpv_military
    assert sig.confidence == 1.00


def test_volunteer_fire_brigade_is_not_defence():
    """CPV 35110000 sits in the defence division and this is a fire engine."""
    o, sig = verdict("550462-2026")
    assert not sig.is_defence
    assert sig.cpv_civil_security


def test_sanctions_declaration_does_not_make_engineering_defence():
    o, sig = verdict("550510-2026")
    assert o.security_clearance_required, "the field is present and recorded"
    assert not sig.is_defence


def test_staff_vetting_does_not_make_cleaning_defence():
    o, sig = verdict("551365-2026")
    assert o.security_clearance_required
    assert not sig.is_defence, "CPV 90911100 is cleaning services"


def test_the_feed_would_contain_only_the_real_one():
    defence = [pub for pub in NOTICES if verdict(pub)[1].is_defence]
    assert defence == ["550530-2026"]


# ======================================================================
# The mapping corrections of 12 October 2026 (findings F1 to F6, F17).
#
# `ted_live_notices_2026_10.json` is real notices fetched that day with the
# fields the connector now requests, contact data stripped. Where TED had no
# notice of the shape wanted (two currencies in one list) the case is built by
# hand below and says so.
# ======================================================================

FIXTURE_2026_10 = Path(__file__).resolve().parents[1] / "fixtures" / "ted_live_notices_2026_10.json"
LIVE = {n["publication-number"]: n for n in json.loads(FIXTURE_2026_10.read_text(encoding="utf-8"))}
TODAY = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


def live(pub: str):
    return from_ted(strip_personal_data(LIVE[pub]))


def synthetic(**fields):
    return from_ted({"publication-number": "1-2026", "notice-title": "t",
                     "buyer-name": "b", **fields})


# ---------------------------------------------------------------- status (F1)

@pytest.mark.parametrize("notice_type,status", [
    ("cn-standard", "open"), ("cn-social", "open"), ("cn-desg", "open"),
    ("pin-cfc-standard", "open"), ("pin-cfc-social", "open"),
    ("subco", "open"), ("qu-sy", "open"),
    ("can-standard", "awarded"), ("can-social", "awarded"), ("can-desg", "awarded"),
    ("can-tran", "awarded"), ("can-modif", "awarded"), ("veat", "awarded"),
    ("compl", "awarded"),
    ("pin-only", "forthcoming"), ("pin-buyer", "forthcoming"), ("pin-rtl", "forthcoming"),
    ("pin-tran", "forthcoming"), ("pmc", "forthcoming"),
])
def test_every_notice_type_has_the_agreed_status(notice_type, status):
    o = synthetic(**{"notice-type": notice_type})
    assert o.status == status
    assert o.status_native == notice_type


@pytest.mark.parametrize("notice_type", ["something-new", "x"])
def test_an_unmapped_notice_type_is_unknown_and_never_open(notice_type):
    o = synthetic(**{"notice-type": notice_type})
    assert o.status == "unknown"
    assert notice_type not in TED_STATUS_BY_TYPE


def test_a_notice_without_a_type_is_unknown():
    assert synthetic().status == "unknown"


def test_the_type_is_read_case_insensitively():
    assert synthetic(**{"notice-type": ["CAN-Standard"]}).status == "awarded"


def test_a_corrigendum_is_open_only_when_it_states_a_deadline():
    assert live("1268-2024").status == "open"
    assert live("1268-2024").deadline_at == datetime(
        2024, 1, 30, 13, 0, tzinfo=timezone(timedelta(hours=1)))
    assert live("17143-2024").status == "unknown"


def test_an_award_notice_is_never_served_as_open():
    """The reason F1 is a finding: 4,244 award, modification and prior-information
    notices were in the default open list."""
    for pub in ("534116-2026", "535203-2026", "573801-2026", "533575-2026"):
        o = live(pub)
        assert effective_status(o.status, o.deadline_at, o.published_at, TODAY) != "open"


def test_a_contract_notice_stays_open_until_its_deadline():
    o = live("554343-2026")
    assert o.status == "open"
    before = o.deadline_at - timedelta(days=1)
    after = o.deadline_at + timedelta(days=1)
    assert effective_status(o.status, o.deadline_at, o.published_at, before) == "open"
    assert effective_status(o.status, o.deadline_at, o.published_at, after) == "expired"


def test_a_result_notice_where_every_lot_closed_without_a_winner_is_cancelled():
    """Measured: about 13% of can-standard have every lot `clos-nw`."""
    assert live("534883-2026").status == "cancelled"
    assert live("534883-2026").status_native == "can-standard"


@pytest.mark.parametrize("lots,status", [
    (["selec-w"], "awarded"),
    (["selec-w", "open-nw", "open-nw"], "awarded"),
    (["clos-nw", "selec-w"], "awarded"),
    (["clos-nw", "clos-nw"], "cancelled"),
    (["open-nw"], "awarded"),       # undecided is not "closed with no winner"
    ([], "awarded"),                # before eForms the notice cannot say per lot
])
def test_lot_results_decide_between_awarded_and_cancelled(lots, status):
    o = synthetic(**{"notice-type": "can-standard", "winner-selection-status": lots})
    assert o.status == status


# ------------------------------------------------------ publication date (F2)

def test_published_at_is_the_publication_date_not_the_dispatch_date():
    o = live("534116-2026")
    assert _parse_date(LIVE["534116-2026"]["dispatch-date"]) == date(2026, 7, 31)
    assert o.published_at == date(2026, 8, 3)


def test_without_a_publication_date_the_dispatch_date_is_used():
    o = synthetic(**{"dispatch-date": "2026-08-14+02:00"})
    assert o.published_at == date(2026, 8, 14)


# ------------------------------------------------------------------ value (F3)

def test_a_result_notice_carries_its_awarded_total():
    o = live("536788-2026")        # 24 lots; the procedure estimate is another number
    assert (o.value_amount, o.value_currency, o.value_kind) == (1982953.6, "CZK", "total")
    assert o.lot_count == 24


def test_a_result_notice_falls_back_to_the_result_value_then_to_the_estimate():
    got = synthetic(**{"notice-type": "can-standard", "result-value-notice": "500",
                       "result-value-cur-notice": "EUR", "estimated-value-proc": "900",
                       "estimated-value-cur-proc": "EUR"})
    assert (got.value_amount, got.value_kind) == (500.0, "total")
    got = synthetic(**{"notice-type": "can-standard", "estimated-value-proc": "900",
                       "estimated-value-cur-proc": "EUR"})
    assert (got.value_amount, got.value_kind) == (900.0, "estimated")


def test_the_procedure_estimate_beats_the_sum_of_the_lots():
    o = live("537885-2026")        # lots 5.05M + 18.19M, procedure 30.89M
    assert (o.value_amount, o.value_currency, o.value_kind) == (30893400.0, "EUR", "estimated")
    assert o.lot_count == 2


def test_lots_with_one_currency_and_no_procedure_value_are_summed():
    o = live("554343-2026")        # two lots, 24,623,514 + 50,654,246 PLN
    assert (o.value_amount, o.value_currency, o.value_kind) == (75277760.0, "PLN", "lot_sum")
    assert o.lot_count == 2


def test_lots_in_different_currencies_are_not_summed():
    # Built by hand: no live notice with two currencies was found on 12 October.
    o = synthetic(**{"notice-type": "cn-standard", "estimated-value-lot": ["100", "200"],
                     "estimated-value-cur-lot": ["EUR", "PLN"],
                     "description-lot": {"eng": ["a", "b"]}})
    assert (o.value_amount, o.value_currency, o.value_kind) == (100.0, "EUR", "first_lot")


def test_a_lot_without_a_value_makes_the_sum_a_first_lot_figure():
    o = synthetic(**{"notice-type": "cn-standard", "estimated-value-lot": ["100", "200"],
                     "estimated-value-cur-lot": ["EUR"],
                     "description-lot": {"eng": ["a", "b", "c"]}})
    assert o.lot_count == 3
    assert (o.value_amount, o.value_kind) == (100.0, "first_lot")


def test_equal_lot_values_are_summed_not_taken_once():
    """136450: ours said 600,000 PLN for lots of 600k, 600k, 600k and 300k."""
    o = synthetic(**{"notice-type": "cn-standard",
                     "estimated-value-lot": ["600000"] * 3 + ["300000"],
                     "estimated-value-cur-lot": ["PLN"],
                     "description-lot": {"pol": ["a", "b", "c", "d"]}})
    assert (o.value_amount, o.value_currency, o.value_kind) == (2100000.0, "PLN", "lot_sum")


def test_a_legacy_notice_with_only_a_total_uses_it():
    o = live("99379-2019")
    assert (o.value_amount, o.value_currency, o.value_kind) == (959790.0, "EUR", "total")


def test_no_value_at_all_is_no_value():
    o = live("534883-2026")
    assert (o.value_amount, o.value_currency, o.value_kind) == (None, None, None)


# ------------------------------------------------------- the procedure (F4)

def test_the_procedure_is_the_name_and_the_subtype_has_its_own_field():
    o = live("93334-2024")
    assert o.procedure_type == "restricted"
    assert o.notice_subtype == "18"
    assert live("573801-2026").procedure_type == "neg-wo-call"
    assert live("534116-2026").notice_subtype == "31"


def test_a_notice_that_names_no_procedure_has_none_and_keeps_its_subtype():
    o = live("533575-2026")
    assert o.procedure_type is None
    assert o.notice_subtype == "6"


# ---------------------------------------------------------- deadline (F5)

def test_the_request_to_participate_deadline_keeps_its_time_and_offset():
    """93334-2024: TED shows 08:00 at +01:00. The mapper used to apply 23:59 UTC."""
    o = live("93334-2024")
    assert o.deadline_at == datetime(2024, 3, 22, 8, 0, tzinfo=timezone(timedelta(hours=1)))
    assert o.deadline_at.astimezone(timezone.utc) == datetime(
        2024, 3, 22, 7, 0, tzinfo=timezone.utc)


def test_a_legacy_notice_gets_its_deadline_from_the_unified_field():
    o = live("99381-2019")
    assert o.deadline_at == datetime(2019, 3, 29, 10, 0, tzinfo=timezone(timedelta(hours=1)))
    assert o.status == "open"
    assert o.buyer_identifier == "REGON: 276854946"


def test_without_the_unified_field_the_request_time_is_still_used():
    o = synthetic(**{"deadline-receipt-request-date-lot": ["2024-03-22+01:00"],
                     "deadline-receipt-request-time-lot": ["08:00:00+01:00"]})
    assert o.deadline_at == datetime(2024, 3, 22, 8, 0, tzinfo=timezone(timedelta(hours=1)))


def test_the_additional_information_deadline_is_never_a_tender_deadline():
    o = synthetic(**{"deadline-date-lot": ["2026-01-01+01:00"], "deadline": ["2026-01-01"]})
    assert o.deadline_at is None


def test_lots_with_different_deadlines_take_the_latest():
    o = synthetic(**{"deadline-receipt-request": ["2026-10-01T10:00:00+02:00",
                                                  "2026-10-08T10:00:00+02:00"]})
    assert o.deadline_at == datetime(2026, 10, 8, 10, 0, tzinfo=timezone(timedelta(hours=2)))


def test_the_deadline_offset_is_kept_so_an_unchanged_instant_is_not_a_change():
    o = synthetic(**{"deadline-receipt-request": ["2026-10-01T10:00:00+02:00"]})
    assert db.opportunity_payload(o)["deadline_at"] == "2026-10-01T10:00:00+02:00"


# ------------------------------------------------------------ country (F6)

@pytest.mark.parametrize("iso3,iso2", [
    ("BLR", "BY"), ("SRB", "RS"), ("MNE", "ME"), ("TUR", "TR"), ("ALA", "AX"),
    ("GLP", "GP"), ("PYF", "PF"), ("CHN", "CN"), ("GRL", "GL"), ("XKX", "XK"),
    ("GBR", "GB"), ("GRC", "GR"), ("CHE", "CH"), ("ESP", "ES"), ("PRY", "PY"),
    ("ALB", "AL"), ("NCL", "NC"), ("EUR", "EU"),
])
def test_iso3_codes_map_to_their_own_alpha2(iso3, iso2):
    assert _country2([iso3]) == iso2


def test_a_two_letter_code_passes_through_upper_cased():
    assert _country2("pl") == "PL"


def test_an_unknown_code_is_none_not_a_truncation(caplog):
    with caplog.at_level("WARNING", logger="dgate.normalise"):
        assert _country2("ZZZ") is None
        assert _country2("ZZZ") is None
    assert sum("ZZZ" in r.getMessage() for r in caplog.records) == 1, "logged once per code"


def test_the_iso_table_is_complete_and_collision_free():
    assert len(_ISO3_TO_2) == 249 + 2          # ISO 3166-1, plus XKX and EUR
    assert len(set(_ISO3_TO_2.values())) == len(_ISO3_TO_2)
    assert all(len(k) == 3 and len(v) == 2 for k, v in _ISO3_TO_2.items())


# --------------------------------------------- identifiers, lots (F15, F17)

def test_the_buyer_and_procedure_identifiers_are_mapped():
    o = live("93334-2024")
    assert o.buyer_identifier == "60162694"
    assert o.procedure_identifier == "c3c8137c-d92b-4f7f-8175-36decaf1451d"


@pytest.mark.parametrize("value,kept", [
    ("60162694", True), ("REGON: 276854946", True), ("08-A8410-43", True),
    ("+49381877142133", False),       # a switchboard filed as the identifier
    ("info@example.org 12345", False), ("Jan Kowalski", False), ("1" * 65, False),
    ("", False), (None, False),
])
def test_a_buyer_identifier_is_an_organisation_number_or_nothing(value, kept):
    got = _ted_buyer_identifier([value] if value is not None else None)
    assert (got is not None) == kept


def test_lot_count_is_none_when_the_notice_lists_no_lots():
    assert synthetic().lot_count is None
    assert live("537885-2026").lot_count == 2


# ---------------------------------------------------------- versions

def test_the_new_attributes_are_not_versioned_and_not_in_a_payload_while_empty():
    for name in ("notice_subtype", "procedure_identifier", "lot_count", "value_kind"):
        assert name not in db.VERSIONED_FIELDS
    payload = db.opportunity_payload(synthetic())
    for name in ("notice_subtype", "procedure_identifier", "lot_count", "value_kind",
                 "buyer_identifier"):
        assert name not in payload


def test_a_corrected_status_is_a_versioned_change_and_an_unchanged_payload_is_not():
    raw = strip_personal_data(LIVE["534116-2026"])
    before = {k: v for k, v in raw.items() if k != "notice-type"}
    old = db.opportunity_payload(from_ted(before))
    new = db.opportunity_payload(from_ted(raw))
    assert [f for f in db.VERSIONED_FIELDS if old.get(f) != new.get(f)] == ["status"]
    again = db.opportunity_payload(from_ted(raw))
    assert [f for f in db.VERSIONED_FIELDS if new.get(f) != again.get(f)] == []
