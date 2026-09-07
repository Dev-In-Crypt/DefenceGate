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
from pathlib import Path

import pytest

from dgate.classify import classify
from dgate.normalise import from_ted, strip_personal_data

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
