"""Polish bulletin and Atlas: status, procedure, title, history and re-read.

The cases in `tests/fixtures/ezamowienia_status_cases.json` are real records of
the board, taken on 12 October 2026 from the Polish defence notices we hold, with
the heavy and contact fields (`cpvCode`, `contractors`, `htmlBody`) left out.
Every expectation below is a finding of the data quality audit of that day.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from dgate import pipeline
from dgate.normalise import from_atlas_pl, from_ezamowienia, strip_personal_data
from dgate.sources import atlas_pl
from dgate.sources import ezamowienia as ez

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ezamowienia_status_cases.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))


def mapped(name: str):
    return from_ezamowienia(strip_personal_data(CASES[name]))


# ----------------------------------------------------------- status (F12)

@pytest.mark.parametrize("case, status, native", [
    # Republished from TED: noticeType is null, the form is in noticeTypeTed.
    ("ted_cn_16", "open", "eforms-16"),
    ("ted_cn_18", "open", "eforms-18"),
    ("ted_can_29", "awarded", "eforms-29"),
    ("ted_can_31_neg_wo_call", "awarded", "eforms-31"),
    ("ted_modif_38", "awarded", "eforms-38"),
    ("ted_veat_27", "awarded", "eforms-27"),
])
def test_a_notice_republished_from_ted_gets_its_status_from_the_ted_form(case, status, native):
    """543 of 1,719 notices had noticeType null and were all `unknown`; 233 of
    them had an open deadline and were served as closed."""
    assert CASES[case]["noticeType"] is None
    o = mapped(case)
    assert (o.status, o.status_native) == (status, native)


def test_the_ted_forms_follow_the_decision_cn_open_pin_forthcoming_can_awarded():
    assert ez.map_status("eforms-16") == "open"
    assert ez.map_status("cn-standard") == "open"
    assert ez.map_status("eforms-7") == "forthcoming"        # pin-rtl
    assert ez.map_status("eforms-T01") == "forthcoming"      # pin-tran
    assert ez.map_status("eforms-29") == "awarded"           # can-standard
    assert ez.map_status("can-modif") == "awarded"
    assert ez.map_status("eforms-25") == "awarded"           # veat


def test_a_ted_form_nobody_has_seen_is_unknown_not_open():
    assert ez.map_status("eforms-99") == "unknown"
    assert ez.map_status("eforms-15") == "unknown"           # qu-sy: neither call nor award
    assert ez.map_status("eforms-") == "unknown"


def test_the_bzp_type_wins_when_both_are_present():
    o = from_ezamowienia({"bzpNumber": "2026/BZP 1", "noticeType": "TenderResultNotice",
                          "noticeTypeTed": "eforms-16"})
    assert o.status == "awarded" and o.status_native == "TenderResultNotice"


def test_a_plan_notice_is_forthcoming_not_unknown():
    assert mapped("bzp_plan").status == "forthcoming"


def test_a_prior_information_notice_is_not_a_call():
    for t in ez.DEFENCE_NOTICE_TYPES:
        if t.startswith("PriorInformation"):
            assert ez.map_status(t) == "forthcoming"
    assert ez.map_status("ContractNoticeForContractsInTheFieldOfDefenceAndSecurityEU") == "open"


def test_an_intention_to_conclude_a_contract_is_not_open():
    """The equivalent of TED's veat, which the decision maps to awarded."""
    assert mapped("bzp_intention").status == "awarded"
    assert ez.map_status("NoticeOfIntentionToConcludeAContract") == "awarded"


def test_a_small_contract_notice_with_a_deadline_is_a_call():
    o = mapped("bzp_small")
    assert o.status == "open" and o.deadline_at is not None


def test_a_change_notice_is_unknown_so_it_is_never_listed_as_a_second_open_tender():
    """It restates a notice that is listed in its own right and carries no
    deadline; the status of the original is not the copy's to claim."""
    o = mapped("bzp_update")
    assert o.status == "unknown" and o.status_native == "NoticeUpdateNotice"
    assert o.deadline_at is None


def test_a_fully_annulled_result_is_cancelled_not_awarded():
    assert CASES["bzp_result_annulled"]["procedureResult"] == "uniewaznienie"
    assert mapped("bzp_result_annulled").status == "cancelled"


def test_one_concluded_part_keeps_the_notice_awarded():
    assert mapped("bzp_result_concluded").status == "awarded"
    assert mapped("bzp_result_mixed").status == "awarded"


def test_parts_that_were_annulled_or_not_decided_are_closed_not_awarded():
    assert CASES["bzp_result_undecided"]["procedureResult"] == "nieRozstrzygnieto;uniewaznienie"
    assert mapped("bzp_result_undecided").status == "closed"


def test_the_word_unijna_is_not_an_outcome():
    """On a notice republished from TED procedureResult holds the regime."""
    assert CASES["ted_can_29"]["procedureResult"] == "Unijna"
    assert ez.result_status("Unijna") is None
    assert mapped("ted_can_29").status == "awarded"


# ------------------------------------------------------------- procedure

def test_the_procedure_is_the_tender_type_not_the_notice_type():
    """31.6% of rows had none because the notice type stood in for it."""
    assert mapped("ted_cn_16").procedure_type == "Open procedure"
    assert mapped("ted_cn_16_restricted").procedure_type == "Restricted procedure"
    assert (mapped("ted_can_31_neg_wo_call").procedure_type
            == "Negotiated procedure without a call for competition")
    assert mapped("bzp_performing").procedure_type != "ContractPerformingNotice"


def test_a_bulletin_code_without_a_verified_meaning_is_kept_and_labelled_as_a_code():
    """Until 13 October 2026 every numeric code was in this case; the publisher's own client
    names most of them (tests/unit/test_wp1_polish_procedure.py). Those it does not stay
    labelled codes: 1.2 (art. 297, an unsure translation), 2.9, anything new."""
    o = mapped("bzp_contract_1_1_2")
    assert CASES["bzp_contract_1_1_2"]["tenderType"] == "1.1.2"
    assert o.procedure_type == "Basic procedure (art. 275 pt 2)"
    assert ez.procedure_label("1.2") == "BZP 1.2"
    assert ez.procedure_label("2.9") == "BZP 2.9"


def test_no_tender_type_is_no_procedure():
    assert mapped("bzp_plan").procedure_type is None
    assert mapped("ted_modif_38").procedure_type is None
    assert ez.procedure_label("") is None and ez.procedure_label(None) is None


def test_an_unlisted_word_is_kept_as_it_came():
    assert ez.procedure_label("exp-int-rail") == "exp-int-rail"


def test_the_native_type_stays_in_status_native():
    assert mapped("bzp_performing").status_native == "ContractPerformingNotice"


# ----------------------------------------------------------------- title

def test_a_plan_notice_is_not_served_with_an_empty_title():
    """35 plan notices had none: the listing names no subject and no CPV."""
    raw = CASES["bzp_plan"]
    assert not raw.get("orderObject") and not raw.get("cpvCode")
    o = mapped("bzp_plan")
    assert o.title_original.startswith("Procurement plan notice")
    assert raw["organizationName"] in o.title_original
    assert o.title_en == o.title_original


def test_a_real_title_is_never_replaced():
    o = mapped("ted_cn_16")
    assert o.title_original == CASES["ted_cn_16"]["orderObject"].strip()
    assert o.title_en is None


def test_the_plan_revision_is_the_notice_version():
    """`2025/BZP 00427260/15/P`: the tail is the letter, the revision is 15."""
    o = mapped("bzp_plan")
    assert CASES["bzp_plan"]["noticeNumber"].endswith("/15/P")
    assert o.notice_version == 15
    assert o.native_id == "2025/BZP 00427260"


# --------------------------------------------------------------- TED link

def test_the_ted_link_comes_from_the_pdf_url():
    assert mapped("ted_cn_16").ted_ref == "612773-2026"


def test_the_ted_link_survives_a_missing_pdf_url():
    """`2026/S 172-612773` is year, OJ S issue, publication number."""
    raw = {**CASES["ted_cn_16"], "pdfUrl": None}
    assert from_ezamowienia(raw).ted_ref == "612773-2026"


def test_a_bulletin_notice_has_no_ted_link():
    assert mapped("bzp_contract_1_1_2").ted_ref is None


# -------------------------------------------------------- fetching by number

class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Client:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[dict] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(dict(params))
        return self.handler(params)


def _unavailable(params):
    return httpx.Response(503, request=httpx.Request("GET", ez.SEARCH_URL))


def test_a_notice_is_asked_for_by_its_exact_number_in_one_request():
    number = CASES["ted_cn_16"]["noticeNumber"]
    client = _Client(lambda p: _Response([CASES["ted_cn_16"]]))
    got = ez.fetch_notice(number, client=client)
    assert got["noticeNumber"] == number
    assert len(client.calls) == 1
    assert client.calls[0]["noticeNumber"] == number
    assert "BzpNumber" not in client.calls[0]      # ignored by the API: measured


def test_a_number_the_board_no_longer_knows_is_none():
    assert ez.fetch_notice("2026/BZP 00000001/01", client=_Client(lambda p: _Response([]))) is None


def test_a_filter_the_api_ignored_is_an_error_not_somebody_elses_notice():
    """When the filter is ignored the API returns the first page of the board."""
    other = [{"noticeNumber": f"2021/BZP {i:08d}/01"} for i in range(ez.PAGE_SIZE)]
    with pytest.raises(RuntimeError):
        ez.fetch_notice("2026/BZP 00448576/01", client=_Client(lambda p: _Response(other)))


# ------------------------------------------------------------ history day

def test_the_history_walks_a_day_at_one_request_a_second(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(ez.time, "sleep", lambda s: sleeps.append(s))
    pages = {1: [{"noticeNumber": f"a{i}"} for i in range(10)],
             2: [{"noticeNumber": f"b{i}"} for i in range(10)],
             3: [{"noticeNumber": "c0"}]}
    client = _Client(lambda p: _Response(pages.get(p["PageNumber"], [])))
    got = list(ez.fetch_day(date(2026, 3, 4), client=client))
    assert len(got) == 21
    assert sleeps == [1.0, 1.0]
    assert {c["publicationDateFrom"] for c in client.calls} == {"2026-03-04T00:00:00.000Z"}
    assert all(c["publicationDateTo"] == c["publicationDateFrom"] for c in client.calls)


def test_a_notice_repeated_inside_a_history_day_is_yielded_once(monkeypatch):
    monkeypatch.setattr(ez.time, "sleep", lambda s: None)
    page = [{"noticeNumber": "x"}] * 3 + [{"noticeNumber": f"n{i}"} for i in range(7)]
    client = _Client(lambda p: _Response(page if p["PageNumber"] == 1 else []))
    assert len(list(ez.fetch_day(date(2026, 3, 4), client=client))) == 8


def test_a_day_that_keeps_returning_503_is_an_error_after_six_tries(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    client = _Client(_unavailable)
    with pytest.raises(httpx.HTTPStatusError):
        list(ez.fetch_day(date(2026, 3, 4), client=client))
    assert len(client.calls) == ez.HISTORY_ATTEMPTS


def test_pl_ezam_is_registered_for_the_history_load(monkeypatch):
    monkeypatch.setattr(pipeline, "HISTORY_SOURCES", {})
    fetch_day, mapper = pipeline._history_source("pl_ezam")
    assert mapper is from_ezamowienia and callable(fetch_day)


# ----------------------------------------------------------- the window

class _DayClient:
    def __init__(self, by_day, fail_day=None, fail_page=2):
        self.by_day, self.fail_day, self.fail_page = by_day, fail_day, fail_page

    def get(self, url, params=None, timeout=None):
        day = params["publicationDateFrom"][:10]
        page = params["PageNumber"]
        if day == self.fail_day and page == self.fail_page:
            return httpx.Response(503, request=httpx.Request("GET", url))
        records = self.by_day.get(day, [])
        start = (page - 1) * ez.PAGE_SIZE
        return _Response(records[start:start + ez.PAGE_SIZE])


def _three_days():
    return {"2026-10-05": [{"noticeNumber": f"a{i}"} for i in range(25)],
            "2026-10-06": [{"noticeNumber": f"b{i}"} for i in range(25)],
            "2026-10-07": [{"noticeNumber": f"c{i}"} for i in range(5)]}


def test_a_day_that_fails_mid_walk_ends_the_window_by_default(monkeypatch):
    """The 6 October 2026 failure: a 503 on a later page of the day."""
    monkeypatch.setattr("time.sleep", lambda s: None)
    client = _DayClient(_three_days(), fail_day="2026-10-06")
    with pytest.raises(httpx.HTTPStatusError):
        list(ez.fetch_window(days_back=2, client=client, today=date(2026, 10, 7)))


def test_with_a_failed_list_the_other_days_are_still_read(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    client = _DayClient(_three_days(), fail_day="2026-10-06")
    failed: list[date] = []
    got = list(ez.fetch_window(days_back=2, client=client, today=date(2026, 10, 7),
                               failed=failed))
    assert failed == [date(2026, 10, 6)]
    ids = {r["noticeNumber"] for r in got}
    assert {f"c{i}" for i in range(5)} <= ids          # the 7th was read
    assert {f"a{i}" for i in range(25)} <= ids         # and the 5th


# ----------------------------------------------------------------- Atlas

def atlas_row(**over):
    base = {
        "id": "2024/BZP 00000043", "source": "bzp", "notice_type": "ContractNotice",
        "tender_type": "1.1.1", "procedure_result": None,
        "title": "Dostawa umundurowania", "buyer": "Komenda Portu Wojennego Gdynia",
        "cpv_code": "35811300", "date": date(2024, 1, 2), "estimated_value": None,
        "currency": None, "notice_url": None, "ted_number": None,
        "organization_country": "PL",
    }
    base.update(over)
    return base


def test_atlas_reads_the_procedure_columns():
    assert "tender_type" in atlas_pl.COLUMNS and "procedure_result" in atlas_pl.COLUMNS


def test_atlas_shows_the_procedure_not_the_notice_type():
    o = from_atlas_pl(atlas_row())
    assert o.procedure_type == "Basic procedure (art. 275 pt 1)"
    assert o.status_native == "ContractNotice"


def test_an_atlas_ted_row_has_no_procedure_of_its_own():
    """tender_type is null on all 98,114 TED rows of 2024: the TED twin's
    procedure is shown through ted_ref, never copied into this row."""
    o = from_atlas_pl(atlas_row(source="ted", notice_type="cn-standard", tender_type=None,
                                id="123-2024", ted_number="123-2024"))
    assert o.procedure_type is None
    assert o.legal_basis is None and o.value_amount is None


@pytest.mark.parametrize("raw, canonical", [("123-2024", "123-2024"),
                                            ("00696956-2026", "696956-2026")])
def test_an_atlas_ted_row_links_to_its_ted_twin(raw, canonical):
    o = from_atlas_pl(atlas_row(source="ted", notice_type="can-standard", ted_number=raw))
    assert o.ted_ref == canonical


def test_the_link_also_comes_from_a_ted_url():
    o = from_atlas_pl(atlas_row(notice_url="https://ted.europa.eu/pl/notice/-/detail/618851-2026"))
    assert o.ted_ref == "618851-2026"


def test_an_annulled_atlas_result_is_cancelled():
    o = from_atlas_pl(atlas_row(notice_type="TenderResultNotice",
                                procedure_result="uniewaznienie;uniewaznienie"))
    assert o.status == "cancelled"


def test_an_atlas_result_with_a_contract_stays_awarded():
    for result in ("zawarcieUmowy", "zawarcieUmowy;uniewaznienie", None):
        assert from_atlas_pl(atlas_row(notice_type="TenderResultNotice",
                                       procedure_result=result)).status == "awarded"


def test_a_ted_row_closed_without_a_contractor_is_closed():
    o = from_atlas_pl(atlas_row(source="ted", notice_type="can-standard", tender_type=None,
                                procedure_result="Zamknięte bez wyboru wykonawcy"))
    assert o.status == "closed"


def test_the_procedure_columns_do_not_change_what_is_open():
    assert from_atlas_pl(atlas_row(notice_type="ContractNotice",
                                   procedure_result="uniewaznienie")).status == "open"


@pytest.mark.parametrize("notice_type, status", [
    ("ContractNotice", "open"), ("cn-standard", "open"), ("SmallContractNotice", "open"),
    ("TenderResultNotice", "awarded"), ("can-standard", "awarded"), ("veat", "awarded"),
    ("can-modif", "awarded"), ("AgreementUpdateNotice", "awarded"),
    ("AgreementIntentionNotice", "awarded"),
    ("pin-rtl", "forthcoming"), ("pin-only", "forthcoming"),
    ("NoticeUpdateNotice", "unknown"), ("SomethingNew", "unknown"), (None, "unknown"),
])
def test_atlas_status_is_never_open_for_what_is_not_a_call(notice_type, status):
    from dgate.normalise import _atlas_status

    assert _atlas_status(notice_type) == status


@pytest.mark.parametrize("notice_type, status", [
    # the bulletin's own table, reused: these were `unknown` in Atlas and are decided on
    # the board
    ("ContractNoticeForContractsInTheFieldOfDefenceAndSecurityEU", "open"),
    ("PriorInformationNoticeForContractsInTheFieldOfDefenceAndSecurityEU", "forthcoming"),
    ("ContractAwardNoticeForContractsInTheFieldOfDefenceAndSecurityEU", "awarded"),
    ("ContractAwardNotice", "awarded"),
])
def test_atlas_sends_the_defence_and_award_types_the_way_the_board_does(notice_type, status):
    from dgate.normalise import _atlas_status

    assert _atlas_status(notice_type) == status
    assert ez.map_status(notice_type) == status


@pytest.mark.parametrize("notice_type", ["pin-cfc-standard", "pin-cfc-social"])
def test_a_prior_information_notice_used_as_a_call_reads_the_same_everywhere(notice_type):
    """Open with a deadline, forthcoming without: TED, Atlas and the board agree."""
    from dgate.normalise import _atlas_status

    assert ez.map_status(notice_type) == "forthcoming"
    assert ez.map_status(notice_type, has_deadline=True) == "open"
    assert _atlas_status(notice_type) == "forthcoming"
    assert _atlas_status(notice_type, has_deadline=True) == "open"
    undated = from_atlas_pl(atlas_row(source="ted", notice_type=notice_type, tender_type=None))
    dated = from_atlas_pl(atlas_row(source="ted", notice_type=notice_type, tender_type=None,
                                    submitting_offers_date="2026-11-20T10:00:00"))
    assert (undated.status, dated.status) == ("forthcoming", "open")
    board = {"bzpNumber": "2026/BZP 1", "noticeType": None, "noticeTypeTed": notice_type}
    assert from_ezamowienia(board).status == "forthcoming"
    assert from_ezamowienia({**board, "submittingOffersDate": "2026-11-20T10:00:00"}
                            ).status == "open"
