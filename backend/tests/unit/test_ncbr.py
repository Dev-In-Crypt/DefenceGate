"""The Polish research agency's competitions: which count, and what they map to.

Fixtures are the shapes the API returned on 6 October 2026: the horizontal SMART call
that is open to large enterprises and carries the defence tag, the old PERUN defence
programme, a fellowship for researchers that carries the same tag, and a call with no tag.
What matters most is what must *not* be kept: of 364 competitions, a handful are a
supplier's.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from dgate.normalise import from_ncbr, strip_personal_data
from dgate.sources import ncbr

TODAY = date(2026, 10, 6)


def _record(**over):
    record = {
        "name": "FENG.01.01-IP.01-003/26 - Ścieżka SMART - Projekty realizowane w konsorcjach",
        "path": "/web/ncbr/feng010101-ip01-00326",
        "publishDate": "2026-07-01T10:00:00",
        "type": "NCBR",
        "description": "<p>Konkurs. Kontakt: jan.kowalski@ncbr.gov.pl</p>",
        "budget": "350 000 000 zł",
        "status": "APPLICATIONS_IN_PROGRESS",
        "typesOfApplicant": json.dumps(["large_enterprise", "consortium", "sme"]),
        "sourcesOfFunding": json.dumps(["eu_funds"]),
        "thematicAreas": json.dumps(["innovative_technologies", "defence_and_security"]),
        "programmeTypes": json.dumps(["eu"]),
        "dates": json.dumps([{"name": "Ogłoszenie konkursu", "value": "2026-07-01T00:00:00"}]),
        "announcementDate": "2026-07-01T00:00:00",
        "applicationsStartDate": "2026-07-01T09:00:00",
        "applicationsEndDate": "2026-10-16T16:00:00",
        "resultsDate": None,
    }
    record.update(over)
    return record


SMART = _record()
PERUN = _record(
    name="Konkurs nr 1/PERUN/2023", path="/web/ncbr/konkurs-nr-1perun2023",
    budget="nie ma określonej alokacji", status="APPLICATIONS_IN_EVALUATION",
    thematicAreas=json.dumps(["defence_and_security"]),
    programmeTypes=json.dumps(["defence_security"]),
    sourcesOfFunding=json.dumps(["national_funds"]),
    announcementDate="2023-11-15T00:00:00", applicationsStartDate="2023-12-01T09:00:00",
    applicationsEndDate="2024-01-31T16:00:00")
FELLOWSHIP = _record(
    name="Polskie Powroty NAWA 2026", path="/web/ncbr/polskie-powroty-nawa-2026",
    budget="2 000 000 PLN", typesOfApplicant=json.dumps(["scientist", "individual"]))
UNTAGGED = _record(
    name="EUREKA nabór w roku 2026", path="/web/ncbr/eureka-2026",
    thematicAreas=json.dumps(["innovative_technologies"]), programmeTypes=json.dumps(["international"]))


# ----------------------------------------------------------- the signal

def test_the_publishers_own_defence_programme_tag_makes_the_regime_defence():
    assert ncbr.regime(PERUN) == "defence"


def test_a_horizontal_programme_that_names_defence_among_its_fields_is_dual_use():
    """SMART is not a defence programme. It is PLN 350 million that a defence
    manufacturer may apply for, and the publisher says so with the thematic tag."""
    assert ncbr.regime(SMART) == "dual_use"


def test_a_competition_without_either_tag_is_not_collected():
    assert ncbr.regime(UNTAGGED) is None
    assert not ncbr.in_scope(UNTAGGED, today=TODAY)


# ---------------------------------------------------------------- scope

def test_a_tagged_call_open_to_enterprises_and_open_now_is_in_scope():
    assert ncbr.in_scope(SMART, today=TODAY)


def test_a_fellowship_for_researchers_carrying_the_same_tag_is_not():
    """NAWA and LIDER UP wear the defence tag and are for natural persons and
    researchers. A supplier does not answer them."""
    assert not ncbr.in_scope(FELLOWSHIP, today=TODAY)


def test_a_call_that_closed_in_an_earlier_year_is_not_in_scope_even_if_it_is_defence():
    """PERUN 1/2023 closed in January 2024 and has sat in evaluation since. The agreed
    window is the current year, and the documentation says where the last one went."""
    assert not ncbr.in_scope(PERUN, today=TODAY)


def test_a_call_that_closed_this_year_is_kept_so_the_next_cycle_can_be_predicted():
    closed = _record(status="APPLICATIONS_IN_EVALUATION", applicationsEndDate="2026-05-22T16:00:00")
    assert ncbr.in_scope(closed, today=TODAY)


def test_a_record_without_a_path_or_a_name_is_refused():
    assert not ncbr.in_scope(_record(path=None), today=TODAY)
    with pytest.raises(ValueError):
        from_ncbr(_record(path=None))


# ------------------------------------------------------------ the fields

def test_the_arrays_come_back_from_json_text_inside_strings():
    assert ncbr.applicant_types(SMART) == ["large_enterprise", "consortium", "sme"]
    assert ncbr.applicant_types(_record(typesOfApplicant=None)) == []
    assert ncbr.applicant_types(_record(typesOfApplicant="not json")) == []


@pytest.mark.parametrize("text,expected", [
    ("350 000 000 zł", (350_000_000.0, "PLN")),
    ("1 950 000 euro", (1_950_000.0, "EUR")),
    ("1 950 000 EUR", (1_950_000.0, "EUR")),
    ("120 000 000,00 zł", (120_000_000.0, "PLN")),
    ("66 203 985,86 zł", (66_203_985.86, "PLN")),
    ("296 982 000 PLN (70% dofinansowania)", (296_982_000.0, "PLN")),
    ("10 000 000  zł", (10_000_000.0, "PLN")),
    ("2 000 000 PLN", (2_000_000.0, "PLN")),
    ("1.000.000 zł", (1_000_000.0, "PLN")),
    ("nie ma określonej alokacji", (None, None)),
    ("100% kosztów kwalifikowanych", (None, None)),
    ("", (None, None)),
    (None, (None, None)),
])
def test_a_sum_is_read_only_when_a_currency_follows_it(text, expected):
    """The field is prose. A percentage must never be mistaken for money, and a figure
    with no currency is no figure."""
    assert ncbr.parse_budget(text) == expected


def test_the_deadline_is_warsaw_time_not_utc():
    """The API states 16:00 with no zone. Read as UTC it would be two hours late in
    summer, and a call would show open for two hours it is closed."""
    assert ncbr.deadline(SMART) == datetime(2026, 10, 16, 14, 0, tzinfo=UTC)      # CEST
    assert ncbr.deadline(_record(applicationsEndDate="2026-12-22T12:00:00")) \
        == datetime(2026, 12, 22, 11, 0, tzinfo=UTC)                              # CET
    assert ncbr.deadline(_record(applicationsEndDate=None)) is None


def test_status_follows_the_portal_and_falls_back_to_the_dates():
    now = datetime(2026, 10, 6, tzinfo=UTC)
    assert ncbr.status(SMART, now=now) == "open"
    assert ncbr.status(PERUN, now=now) == "closed"                # in evaluation: applications over
    assert ncbr.status(_record(status="FINISHED"), now=now) == "closed"
    assert ncbr.status(_record(status="ANNOUNCED", applicationsStartDate="2027-01-10T09:00:00"),
                       now=now) == "forthcoming"


# ----------------------------------------------------------- the mapping

def test_a_competition_maps_completely():
    call = from_ncbr(SMART, today=TODAY)
    assert call.programme_code == "PL-NCBR"
    assert call.native_id == "/web/ncbr/feng010101-ip01-00326"
    assert call.country == "PL" and "NCBR" in call.issuer
    assert (call.budget, call.currency, call.budget_scope) == (350_000_000.0, "PLN", "call")
    assert call.status == "open" and call.regime == "dual_use"
    assert call.opens_at == date(2026, 7, 1)
    assert call.source_url == "https://www.gov.pl/web/ncbr/feng010101-ip01-00326"
    assert call.type_of_action == "eu"


def test_who_may_apply_is_stated_from_the_structured_fields():
    text = from_ncbr(SMART, today=TODAY).eligibility_text
    assert "large enterprise" in text and "consortium" in text
    assert "defence and security" in text and "eu funds" in text


def test_the_competitions_own_text_is_never_carried_into_what_the_product_serves():
    """The description is CC BY-SA 4.0. Served, the share-alike clause would reach the
    product, so it stays in the raw archive and out of the call."""
    call = from_ncbr(SMART, today=TODAY)
    assert "jan.kowalski" not in json.dumps(call.conditions_raw, ensure_ascii=False)
    assert "Konkurs. Kontakt" not in (call.eligibility_text or "")
    assert "description" not in call.conditions_raw


def test_a_call_with_no_stated_sum_has_none_and_no_currency():
    call = from_ncbr(PERUN, today=date(2024, 1, 10))
    assert (call.budget, call.currency, call.budget_scope) == (None, None, None)
    assert call.regime == "defence"


def test_the_budget_text_survives_for_the_reader_when_it_is_not_a_sum():
    assert from_ncbr(PERUN).conditions_raw["budget_text"] == "nie ma określonej alokacji"


def test_a_contact_address_in_the_landed_description_is_redacted():
    assert "jan.kowalski@ncbr.gov.pl" not in str(strip_personal_data(SMART))


# -------------------------------------------------------------- fetching

class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _Client:
    """Serves pages from a list of competitions the way the real API misbehaves: each page
    repeats `overlap` rows of the one before, and `hide` drops competitions from the walk
    at a given page size."""

    def __init__(self, records, *, overlap=0, hide=None):
        self.records, self.overlap, self.hide, self.asked = records, overlap, hide or {}, []

    def get(self, url, params=None, timeout=None):
        self.asked.append(dict(params))
        size, page = params["size"], params["page"]
        hidden = self.hide.get(size, set())
        visible = [r for r in self.records if r["path"] not in hidden]
        start = max(0, page * size - (self.overlap if page else 0))
        return _Response({"content": visible[start:start + size],
                          "totalElements": len(self.records),
                          "last": start + size >= len(visible), "number": page})


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(ncbr, "REQUEST_PAUSE", 0.0)


def _records(n):
    return [{"path": f"/web/ncbr/c{i}", "name": f"C{i}"} for i in range(n)]


def test_rows_repeated_across_pages_are_counted_once():
    """414 rows for 364 competitions, measured. Deduplicated by path."""
    client = _Client(_records(120), overlap=10)
    got = ncbr.fetch_all(client=client)
    assert len(got) == 120 and len({r["path"] for r in got}) == 120


def test_a_walk_that_misses_competitions_is_retried_at_another_page_size_and_pooled():
    records = _records(120)
    client = _Client(records, hide={50: {"/web/ncbr/c7", "/web/ncbr/c99"}})
    got = ncbr.fetch_all(client=client)
    assert len(got) == 120
    assert {c["size"] for c in client.asked} == {50, 100}


def test_a_list_that_never_adds_up_is_an_error_not_a_smaller_list():
    """Recording 118 of 120 as complete is a silent hole. Every page size misses the
    same two here, so the pull must fail."""
    hidden = {50: {"/web/ncbr/c1", "/web/ncbr/c2"}, 100: {"/web/ncbr/c1", "/web/ncbr/c2"},
              25: {"/web/ncbr/c1", "/web/ncbr/c2"}}
    with pytest.raises(RuntimeError, match="cut short"):
        ncbr.fetch_all(client=_Client(_records(120), hide=hidden))


def test_a_reply_that_is_not_a_page_of_competitions_is_refused():
    class Bad(_Client):
        def get(self, url, params=None, timeout=None):
            return _Response({"error": "nope"})

    with pytest.raises(ValueError, match="shape changed"):
        ncbr.fetch_all(client=Bad([]))
