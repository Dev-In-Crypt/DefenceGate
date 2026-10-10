"""The Dutch connector (TenderNed).

Fixtures are the shapes the live API returned on 10 October 2026: a defence
directive contract notice from Defensie, a general-directive notice from a
university, and an award. All of them are in one list, and the list carries no
CPV codes -- those come from the detail page.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from dgate.classify import classify
from dgate.normalise import from_tenderned, strip_personal_data
from dgate.sources import tenderned as nl

DEFENCE_LIST = {
    "publicatieId": "407238",
    "publicatieDatum": "2026-01-06",
    "typePublicatie": {"code": "AAO", "omschrijving": "Aankondiging opdracht"},
    "aanbestedingNaam": "Vooraankondiging Challenge Battle Damage Repair",
    "opdrachtgeverNaam": "Ministerie van Defensie",
    "sluitingsDatum": "2026-01-20T00:05:00",
    "aantalDagenTotSluitingsDatum": 14,
    "procedure": {"code": "APM", "omschrijving": "Andere procedure in meerdere fasen"},
    "typeOpdracht": {"code": "L", "omschrijving": "Leveringen"},
    "europees": False,
    "publicatiecode": {"code": "EF18", "omschrijving":
                       "Aankondiging van een opdracht - defensierichtlijn, standaardregeling"},
    "opdrachtBeschrijving": "Defensie bereidt zich voor. Mail: inkoop@mindef.nl",
    "score": None,
    "link": {"href": "https://www.tenderned.nl/aankondigingen/overzicht/407238",
             "title": "self"},
}
DEFENCE_DETAIL = {
    "publicatieId": 407238,
    "numberOfDaysBeforeAanmeldenInschrijven": 14,
    "juridischKaderCode": {"code": "DEF"},
    "cpvCodes": [
        {"isHoofdOpdracht": True, "code": "34000000-7", "omschrijving": "Vervoersmaterieel"},
        {"isHoofdOpdracht": False, "code": "50600000-1", "omschrijving": "Reparatie defensie"},
    ],
}
UNIVERSITY_LIST = {
    "publicatieId": "443728",
    "publicatieDatum": "2026-10-10",
    "typePublicatie": {"code": "AAO", "omschrijving": "Aankondiging opdracht"},
    "aanbestedingNaam": "Bedrijfsmaatschappelijk werk",
    "opdrachtgeverNaam": "Technische Universiteit Delft",
    "sluitingsDatum": "2026-11-19T17:00:00",
    "publicatiecode": {"code": "EF20", "omschrijving":
                       "Aankondiging van een opdracht - algemene richtlijn, lichte regeling"},
}
AWARD_LIST = {**UNIVERSITY_LIST, "publicatieId": "443725", "typePublicatie":
              {"code": "AGO", "omschrijving": "Aankondiging gegunde opdracht"}}


# ------------------------------------------------------------- fetching

class _Response:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


class _Client:
    """Pages of a day, and detail pages by id."""

    def __init__(self, rows, details=None, total=None, fail=()):
        self.rows, self.details = rows, details or {}
        self.total = len(rows) if total is None else total
        self.fail, self.calls = set(fail), []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        if url == nl.LIST_URL:
            page, size = params["page"], params["size"]
            chunk = self.rows[page * size:(page + 1) * size]
            pages = max(1, -(-len(self.rows) // size))
            return _Response({"content": chunk, "totalElements": self.total,
                              "totalPages": pages})
        pid = url.rsplit("/", 1)[1]
        if pid in self.fail:
            raise ValueError("withdrawn")
        return _Response(self.details.get(pid, {"publicatieId": int(pid)}))


def test_a_day_is_asked_for_by_its_own_date_on_both_ends():
    client = _Client([UNIVERSITY_LIST])
    nl.fetch_day_list(date(2026, 10, 10), client=client)
    params = client.calls[0][1]
    assert params["publicatieDatumVanaf"] == params["publicatieDatumTot"] == "2026-10-10"
    assert params["size"] == 100          # 500 is rejected


def test_a_day_larger_than_a_page_is_followed_to_the_end():
    rows = [{"publicatieId": str(i)} for i in range(250)]
    got = nl.fetch_day_list(date(2026, 10, 10), client=_Client(rows))
    assert len(got) == 250


def test_a_day_that_comes_back_short_is_an_error_not_a_smaller_day():
    """The API said 3 and handed over 2: the day would be recorded complete and
    hold a hole."""
    client = _Client([{"publicatieId": "1"}, {"publicatieId": "2"}], total=3)
    with pytest.raises(RuntimeError, match="not complete"):
        nl.fetch_day_list(date(2026, 10, 10), client=client)


def test_a_publication_repeated_across_pages_is_counted_once():
    client = _Client([{"publicatieId": "1"}, {"publicatieId": "1"}, {"publicatieId": "2"}],
                     total=2)
    assert len(nl.fetch_day_list(date(2026, 10, 10), client=client)) == 2


def test_the_day_counters_are_dropped_so_a_reread_is_not_a_change():
    """`aantalDagenTotSluitingsDatum` falls by one every day. Hashed, it would
    land every notice again each night and record a change that is not one."""
    client = _Client([DEFENCE_LIST], {"407238": DEFENCE_DETAIL})
    merged = next(nl.fetch_day(date(2026, 1, 6), client=client, pause=0))
    assert "aantalDagenTotSluitingsDatum" not in merged
    assert "numberOfDaysBeforeAanmeldenInschrijven" not in merged["detail"]
    assert merged["detail"]["cpvCodes"]


def test_an_unreadable_detail_page_keeps_the_notice_and_says_why():
    client = _Client([DEFENCE_LIST, UNIVERSITY_LIST], fail={"407238"})
    got = list(nl.fetch_day(date(2026, 1, 6), client=client, pause=0))
    assert len(got) == 2
    assert "withdrawn" in got[0]["detailError"] and "detail" not in got[0]
    assert "detailError" not in got[1] and got[1]["detail"]


# ------------------------------------------------------------- mapping

def test_the_defence_directive_is_read_from_the_form_not_inferred():
    opp = from_tenderned(nl.merge_detail(DEFENCE_LIST, None))
    assert opp.legal_basis == "32009L0081"           # the form alone, no detail
    assert opp.status_native == "AAO/EF18"
    assert from_tenderned(nl.merge_detail(UNIVERSITY_LIST, None)).legal_basis is None


def test_the_legal_framework_on_the_detail_page_counts_too():
    opp = from_tenderned(nl.merge_detail(
        UNIVERSITY_LIST, {"publicatieId": 1, "juridischKaderCode": {"code": "DEF"}}))
    assert opp.legal_basis == "32009L0081"


def test_a_notice_maps_completely():
    opp = from_tenderned(nl.merge_detail(DEFENCE_LIST, DEFENCE_DETAIL))
    assert (opp.source_code, opp.native_id, opp.country) == ("nl_tenderned", "407238", "NL")
    assert opp.buyer_name_raw == "Ministerie van Defensie"
    assert opp.published_at == date(2026, 1, 6)
    assert opp.cpv_codes == ["34000000", "50600000"]
    assert opp.status == "open"
    assert opp.source_url == "https://www.tenderned.nl/aankondigingen/overzicht/407238"
    assert opp.procedure_type == "Andere procedure in meerdere fasen"
    assert opp.value_amount is None                  # neither level states one


def test_the_deadline_is_amsterdam_time_not_utc():
    """A deadline of 00:05 with no zone is winter time in Amsterdam, UTC+1."""
    opp = from_tenderned(nl.merge_detail(DEFENCE_LIST, None))
    assert opp.deadline_at == datetime(2026, 1, 19, 23, 5, tzinfo=timezone.utc)


@pytest.mark.parametrize("record,status", [
    (UNIVERSITY_LIST, "open"),
    (AWARD_LIST, "awarded"),
    ({**UNIVERSITY_LIST, "typePublicatie": {"code": "VBE"}}, "cancelled"),
    ({**UNIVERSITY_LIST, "typePublicatie": {"code": "XYZ"}}, "unknown"),
])
def test_the_publication_type_decides_the_lifecycle(record, status):
    assert from_tenderned(record).status == status


def test_a_publication_without_an_identifier_is_refused():
    with pytest.raises(ValueError, match="identifier"):
        from_tenderned({"aanbestedingNaam": "x"})


def test_an_address_typed_into_the_description_is_removed_before_landing():
    clean = strip_personal_data(nl.merge_detail(DEFENCE_LIST, None))
    assert "inkoop@mindef.nl" not in clean["opdrachtBeschrijving"]


def test_a_directive_notice_is_defence_with_the_legal_basis_alone():
    opp = from_tenderned(nl.merge_detail(DEFENCE_LIST, None))
    assert classify(legal_basis=opp.legal_basis, cpv_codes=opp.cpv_codes,
                    buyer_is_defence=False, security_clearance_text=None,
                    nda_required=False).is_defence


def test_a_day_that_is_still_growing_today_is_left_for_tomorrow():
    """Today is still being published: the count moves between two pages. A short
    list for today is not a hole, and aborting the whole run for it would flap nightly."""
    client = _Client([{"publicatieId": "1"}], total=2)
    got = list(nl.fetch_window(days_back=0, client=client, today=date(2026, 10, 10)))
    assert got == []


def test_a_short_day_that_is_not_today_is_still_an_error():
    client = _Client([{"publicatieId": "1"}], total=2)
    with pytest.raises(RuntimeError, match="not complete"):
        list(nl.fetch_window(days_back=1, client=client, today=date(2026, 10, 10)))


def test_a_field_that_arrives_as_a_string_is_not_a_crash():
    record = {**UNIVERSITY_LIST, "procedure": "Openbaar", "typePublicatie": "AAO",
              "publicatiecode": "EF16", "detail": {"juridischKaderCode": "DEF",
                                                   "cpvCodes": "34000000-7"}}
    opp = from_tenderned(record)
    assert (opp.legal_basis, opp.cpv_codes, opp.status) == (None, [], "unknown")
