"""The TED publication number a national notice states about itself.

It is the only thing two portals' records are matched on: an identifier the
publisher wrote, not a name or a title that merely looks alike.
"""

from __future__ import annotations

from dgate.db import opportunity_payload
from dgate.normalise import (
    Opportunity,
    canonical_ted_ref,
    from_atlas_pl,
    from_ezamowienia,
    from_tenderned,
    ted_ref_from_url,
)


def test_padding_does_not_make_two_numbers_different():
    assert canonical_ted_ref("00696956-2026") == "696956-2026"
    assert canonical_ted_ref(" 696956-2026 ") == "696956-2026"


def test_only_a_number_and_a_year_is_a_reference():
    for value in ("3381", "696956", "abc-2026", "696956-2026/S", "x 696956-2026", None, 696956):
        assert canonical_ted_ref(value) is None, value


def test_the_number_is_read_from_a_ted_link_in_either_shape():
    assert ted_ref_from_url("https://ted.europa.eu/pl/notice/618851-2026/pdf") == "618851-2026"
    assert ted_ref_from_url("https://ted.europa.eu/en/notice/-/detail/00618851-2026") == "618851-2026"
    assert ted_ref_from_url("https://ezamowienia.gov.pl/notice/618851-2026") is None
    assert ted_ref_from_url(None) is None


def test_tenderned_states_it_in_the_detail():
    opp = from_tenderned({"publicatieId": "443966", "aanbestedingNaam": "x",
                          "opdrachtgeverNaam": "Defensie",
                          "detail": {"pbNummerTed": "696956-2026", "referentieNummer": "3381"}})
    assert opp.ted_ref == "696956-2026"


def test_a_tenderned_notice_not_sent_to_ted_has_none():
    opp = from_tenderned({"publicatieId": "1", "aanbestedingNaam": "x",
                          "opdrachtgeverNaam": "Defensie", "detail": {"referentieNummer": "3381"}})
    assert opp.ted_ref is None


def test_the_polish_bulletin_states_it_as_a_link():
    opp = from_ezamowienia({"bzpNumber": "2026/BZP 00480881", "orderObject": "x",
                            "organizationName": "JW",
                            "pdfUrl": "https://ted.europa.eu/pl/notice/618851-2026/pdf"})
    assert opp.ted_ref == "618851-2026"


def test_atlas_states_it_as_a_column():
    opp = from_atlas_pl({"id": "9", "title": "x", "buyer": "JW", "ted_number": "871147-2025"})
    assert opp.ted_ref == "871147-2025"


def test_an_empty_link_leaves_the_payload_as_it_was_so_hashes_do_not_move():
    bare = Opportunity(source_code="es_placsp", native_id="1", buyer_name_raw="b", title_original="t")
    assert "ted_ref" not in opportunity_payload(bare)
    bare.ted_ref = "1-2026"
    assert opportunity_payload(bare)["ted_ref"] == "1-2026"
