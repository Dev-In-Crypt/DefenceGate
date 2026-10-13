"""Polish sources: the bulletin's procedure codes named, the TED subtypes it republishes,
and the Atlas deadline (correctness:D5, D9, fields:D7, D8 of the verification of 13 October
2026).

The code names come from the publisher's own client (`mo-client-board/main-*.js`), whose
dictionaries pair every `tenderType` code with a key such as
`BELOW_EU.BASIC_ORDER_BASED_ON_275_1` (1.1.1) or `ABOVE_EU.OPEN_TENDER_132` (2.1). The
subtype pairs were read off the TED twins of 1,899 republished records.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from dgate.normalise import from_atlas_pl, from_ezamowienia
from dgate.sources import ezamowienia as ez

# --------------------------------------------------- the TED subtypes (D9)


@pytest.mark.parametrize("form,status", [
    ("eforms-4", "forthcoming"),      # pin-only: 27 of 27 twins
    ("eforms-9", "forthcoming"),      # pin-rtl: 2 of 2
    ("eforms-E5", "awarded"),         # compl: 1 of 1
    ("eforms-E6", "awarded"),         # can-modif: 2 of 2
])
def test_a_subtype_the_twins_named_is_no_longer_unknown(form, status):
    assert ez.map_status(form) == status
    record = {"bzpNumber": "2026/S 8-22000", "noticeNumber": "2026/S 8-22000",
              "noticeType": None, "noticeTypeTed": form, "orderObject": "x",
              "organizationName": "b"}
    assert from_ezamowienia(record).status == status


def test_a_subtype_nobody_saw_is_still_unknown():
    assert ez.map_status("eforms-99") == "unknown"


# ------------------------------------------------- the procedure codes (D7/D8)

@pytest.mark.parametrize("code,name", [
    ("1.1.1", "Basic procedure (art. 275 pt 1)"),
    ("1.1.3", "Basic procedure (art. 275 pt 3)"),
    ("1.3.2", "Negotiated procedure without publication"),
    ("1.4.1.7", "Free-hand award (direct award)"),
    ("2.1", "Open procedure"),
    ("2.2", "Restricted procedure"),
    ("2.3.4", "Negotiated procedure with a call for competition"),
    ("2.6.1", "Negotiated procedure without a call for competition"),
    ("2.7.6", "Free-hand award (direct award)"),
    ("2.8.1", "Open procedure (utilities)"),
    ("2.10.3", "Free-hand award (direct award, defence and security)"),
    ("2.12.17", "Free-hand award (direct award, defence and security)"),
    ("11.1.2", "Framework agreement (below EU thresholds)"),
    ("12.3.4", "Framework agreement (above EU thresholds)"),
    ("20.1", "Dynamic purchasing system"),
])
def test_a_bulletin_code_is_named_by_the_publishers_dictionary(code, name):
    assert ez.procedure_label(code) == name


@pytest.mark.parametrize("code", ["1.2", "1.1.4", "2.9", "21.1", "3", "1.4"])
def test_a_code_the_dictionary_does_not_name_stays_a_labelled_code(code):
    expected = ez.BZP_PROCEDURE_NAMES.get(code)
    assert ez.procedure_label(code) == (expected or f"BZP {code}")


def test_a_prefix_is_matched_on_a_dot_boundary():
    """2.10 is defence, not 2.1 (open), and 21 is not 2."""
    assert ez.procedure_label("2.10.1") != ez.procedure_label("2.1")
    assert ez.procedure_label("21.5") == "BZP 21.5"


def test_the_word_codes_of_ted_are_untouched():
    assert ez.procedure_label("open") == "Open procedure"
    assert ez.procedure_label("neg-wo-call") == "Negotiated procedure without a call for competition"


def test_a_board_record_carries_the_named_procedure():
    record = {"bzpNumber": "2026/BZP 00146334", "noticeNumber": "2026/BZP 00146334/01",
              "noticeType": "ContractNotice", "tenderType": "1.1.1", "orderObject": "x",
              "organizationName": "b"}
    assert from_ezamowienia(record).procedure_type == "Basic procedure (art. 275 pt 1)"


# ------------------------------------------------------- Atlas deadlines (D5)

def atlas(**over):
    base = {"id": "2025/BZP 00297120", "source": "bzp", "notice_type": "ContractNotice",
            "title": "t", "buyer": "b", "cpv_code": "35811300", "date": date(2025, 6, 27),
            "organization_country": "PL"}
    base.update(over)
    return base


def test_a_bzp_row_deadline_is_utc():
    """2025/BZP 00297120: the bulletin shows 09:30 Warsaw (07:30 UTC) for `07:30:00`."""
    o = from_atlas_pl(atlas(submitting_offers_date="2025-07-18 07:30:00"))
    assert o.deadline_at == datetime(2025, 7, 18, 7, 30, tzinfo=timezone.utc)


def test_a_bzp_row_in_winter_is_one_hour_not_two():
    """2025/BZP 00487658: the dataset says `10:30:00`, the bulletin 10:30 UTC (11:30 Warsaw
    in November). Read as Warsaw it came out at 09:30 UTC, one hour early."""
    o = from_atlas_pl(atlas(id="2025/BZP 00487658", submitting_offers_date="2025-11-05 10:30:00"))
    assert o.deadline_at == datetime(2025, 11, 5, 10, 30, tzinfo=timezone.utc)


def test_a_row_republished_from_ted_states_warsaw_wall_time():
    """TED-330544-2024: `09:00:00` in the dataset and 07:00 UTC at TED (22 of 22 twins)."""
    o = from_atlas_pl(atlas(id="TED-330544-2024", source="ted", notice_type="cn-standard",
                            submitting_offers_date="2024-07-08 09:00:00"))
    assert o.deadline_at == datetime(2024, 7, 8, 7, 0, tzinfo=timezone.utc)
    winter = from_atlas_pl(atlas(id="TED-1-2025", source="ted", notice_type="cn-standard",
                                 submitting_offers_date="2025-01-20 09:00:00"))
    assert winter.deadline_at == datetime(2025, 1, 20, 8, 0, tzinfo=timezone.utc)


def test_a_deadline_with_an_offset_keeps_it():
    o = from_atlas_pl(atlas(submitting_offers_date="2025-07-18T09:30:00+02:00"))
    assert o.deadline_at == datetime(2025, 7, 18, 7, 30, tzinfo=timezone.utc)
