"""The Polish connector, against payloads taken from the live API.

`tests/fixtures/ezamowienia_live_notices.json` holds four real records fetched
on 8 September 2026 with personal-data fields stripped. Every defect these tests
cover was invisible from documentation and appeared on contact with the API.
"""

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from dgate.classify import classify
from dgate.normalise import from_ezamowienia, strip_personal_data
from dgate.sources import ezamowienia as ez

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ezamowienia_live_notices.json"
RECORDS = json.loads(FIXTURE.read_text(encoding="utf-8"))
BY_ID = {r["bzpNumber"]: r for r in RECORDS}

DEFENCE = "2026/BZP 00421396"      # 13 Wojskowy Oddzial Gospodarczy
TOWING = "2026/BZP 00426613"       # towing services, plainly civil
AWARDED = "2026/BZP 00426600"      # a result notice
TED_ORIGIN = "2026/S 173-618851"   # an EU notice republished in the bulletin


def parsed(bzp: str):
    return from_ezamowienia(strip_personal_data(BY_ID[bzp]))


# ------------------------------------------------------------- structure

@pytest.mark.parametrize("bzp", sorted(BY_ID))
def test_every_live_record_parses(bzp):
    o = parsed(bzp)
    assert o.native_id and o.country == "PL" and o.source_code == "pl_ezam"


def test_identity_is_the_procurement_not_the_notice_revision():
    """bzpNumber identifies the procurement; noticeNumber appends a revision.

    Keying on the revision would file every amendment as a separate
    opportunity instead of a new version of the same one.
    """
    o = parsed(DEFENCE)
    assert o.native_id == DEFENCE
    assert BY_ID[DEFENCE]["noticeNumber"].startswith(DEFENCE)
    assert o.notice_version == 1


def test_every_cpv_code_is_kept_not_just_the_first():
    """The field is one string holding every code with its Polish label.

    Stopping at the first match kept one code out of seven.
    """
    raw = BY_ID[DEFENCE]["cpvCode"]
    assert raw.count("-") >= 2, "the fixture really does carry several codes"
    o = parsed(DEFENCE)
    assert len(o.cpv_codes) >= 2
    assert all(len(c) == 8 and c.isdigit() for c in o.cpv_codes)
    assert len(o.cpv_codes) == len(set(o.cpv_codes))


def test_deadline_keeps_the_stated_time():
    """submittingOffersDate is a full instant, not a date plus a time.

    Passing it to the two-field parser produced 23:59 for every deadline,
    because that parser anchors its time pattern at the start of the string.
    """
    record = BY_ID[TOWING]
    if not record.get("submittingOffersDate"):
        pytest.skip("this fixture record carries no deadline")
    o = parsed(TOWING)
    assert o.deadline_at is not None and o.deadline_at.tzinfo is not None
    stated = record["submittingOffersDate"].replace("Z", "+00:00")
    assert o.deadline_at == datetime.fromisoformat(stated)
    assert o.deadline_at != o.deadline_at.replace(hour=23, minute=59)


def test_publication_date_is_read():
    assert parsed(DEFENCE).published_at is not None


def test_source_url_points_at_the_notice():
    o = parsed(DEFENCE)
    assert o.source_url and BY_ID[DEFENCE]["objectId"] in o.source_url


def test_the_publishing_person_is_never_carried_forward():
    """userId singles out the individual who filed the notice."""
    for record in RECORDS:
        clean = strip_personal_data(record)
        assert "userId" not in clean
        blob = " ".join(str(v) for v in vars(from_ezamowienia(clean)).values())
        assert str(record.get("userId", "no-such-value")) not in blob


def test_a_record_without_an_identifier_is_rejected():
    with pytest.raises(ValueError):
        from_ezamowienia({"orderObject": "no id"})


# ----------------------------------------------------------------- status

def test_status_comes_from_the_notice_type():
    assert parsed(DEFENCE).status == "open"
    assert parsed(AWARDED).status == "awarded"


def test_unknown_notice_type_is_not_disguised_as_open():
    assert ez.map_status("SomethingNewUZPInvented") == "unknown"
    assert ez.map_status(None) == "unknown"
    assert ez.map_status("TenderResultNotice") == "awarded"


def test_the_native_type_is_kept_beside_the_mapped_one():
    o = parsed(AWARDED)
    assert o.status_native == "TenderResultNotice"


# --------------------------------------------------------------- verdicts

def test_a_military_unit_buying_in_division_35_is_defence():
    o = parsed(DEFENCE)
    sig = classify(legal_basis=o.legal_basis, cpv_codes=o.cpv_codes, buyer_is_defence=False)
    assert sig.is_defence


def test_towing_services_are_not_defence():
    o = parsed(TOWING)
    sig = classify(legal_basis=o.legal_basis, cpv_codes=o.cpv_codes, buyer_is_defence=False)
    assert not sig.is_defence


def test_the_polish_defence_notice_types_carry_the_directive():
    """These three BZP types exist to publish under Directive 2009/81/EC, so
    they are the Polish equivalent of TED's legal-basis signal."""
    for notice_type in ez.DEFENCE_NOTICE_TYPES:
        o = from_ezamowienia({"bzpNumber": "X", "noticeType": notice_type})
        assert o.legal_basis == "32009L0081"
        assert classify(legal_basis=o.legal_basis, cpv_codes=[],
                        buyer_is_defence=False).is_defence


def test_an_ordinary_notice_type_claims_no_legal_basis():
    assert parsed(TOWING).legal_basis is None


# ---------------------------------------------------------------- queries

def test_the_query_set_covers_every_defence_angle():
    queries = ez.defence_queries(date(2026, 9, 1), date(2026, 9, 8))
    assert any(q.get("cpvCode") == "35" for q in queries)
    for notice_type in ez.DEFENCE_NOTICE_TYPES:
        assert any(q.get("noticeType") == notice_type for q in queries)
    for nip in ez.DEFENCE_BUYER_TAX_IDS:
        assert any(q.get("organizationNationalId") == nip for q in queries)


def test_the_window_is_expressed_the_way_the_api_wants_it():
    q = ez.defence_queries(date(2026, 9, 1), date(2026, 9, 8))[0]
    assert q["publicationDateFrom"] == "2026-09-01T00:00:00.000Z"
    assert q["publicationDateTo"] == "2026-09-08T23:59:59.000Z"


def test_the_page_size_is_the_measured_cap():
    """The API returns ten however many are asked for."""
    assert ez.PAGE_SIZE == 10
    assert all(q["PageSize"] == 10 for q in ez.defence_queries(date(2026, 9, 1)))


def test_buyer_tax_ids_are_used_because_names_do_not_filter():
    assert ez.DEFENCE_BUYER_TAX_IDS, "an empty list silently narrows coverage"
    assert all(nip.isdigit() and len(nip) == 10 for nip in ez.DEFENCE_BUYER_TAX_IDS)


def test_queries_can_run_without_any_buyer_list():
    queries = ez.defence_queries(date(2026, 9, 1), buyer_tax_ids=())
    assert queries and not any("organizationNationalId" in q for q in queries)


# -------------------------------------------------------------- fetching

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Returns one full page then a short one, and records what was asked."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        page = (params or {}).get("PageNumber", 1)
        return _FakeResponse(self.pages[page - 1] if page <= len(self.pages) else [])


def test_search_stops_on_a_short_page():
    full = [{"noticeNumber": f"n{i}"} for i in range(ez.PAGE_SIZE)]
    client = _FakeClient([full, [{"noticeNumber": "last"}]])
    got = list(ez.search({"PageSize": ez.PAGE_SIZE}, client=client))
    assert len(got) == ez.PAGE_SIZE + 1
    assert [c["PageNumber"] for c in client.calls] == [1, 2]


def test_search_rejects_an_unexpected_envelope():
    """The endpoint returns a bare list. A dict means the contract changed."""
    client = _FakeClient([{"items": []}])
    with pytest.raises(ValueError, match="expected a list"):
        list(ez.search({}, client=client))
