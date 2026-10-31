"""The query of `ted-defence-history`: what it asks the API, and the shape of the answer."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from dgate import classify, pipeline
from dgate.sources import ted

PAGE = json.loads((Path(__file__).parent.parent / "fixtures"
                   / "ted_defence_history_page.json").read_text(encoding="utf-8"))


def test_query_asks_every_signal_the_classifier_can_decide_from_the_notice():
    q = ted.defence_history_query(date(2021, 3, 1), date(2021, 3, 31))
    assert q.startswith("(publication-date>=20210301 AND publication-date<=20210331) AND (")
    assert 'legal-basis IN ("32009L0081")' in q
    for group in classify.CPV_MILITARY_GROUPS:
        assert f"classification-cpv={group}*" in q
    for code in classify.CPV_MILITARY_ADJACENT:
        assert code in q
    assert "buyer-name~Bundeswehr" in q and 'buyer-name~"Marine nationale"' in q
    # Division 35 as a whole is not asked: the civil groups never qualify.
    assert "classification-cpv=35*" not in q and "classification-cpv=351*" not in q


def test_no_stem_starts_with_a_wildcard_and_phrases_are_quoted():
    """TED refuses a leading wildcard (pattern ^[^*?].*) and a bare two-word value is a
    syntax error; both were met on the live API on 16 October 2026."""
    for stem in ted.DEFENCE_BUYER_STEMS:
        assert not stem.startswith(("*", "?"))
        assert " " not in stem or (stem.startswith('"') and stem.endswith('"'))


def test_count_reads_the_stated_total_from_a_one_notice_page(monkeypatch):
    sent = []

    def post(client, payload):
        sent.append(payload)
        return PAGE

    monkeypatch.setattr(ted, "_post", post)
    assert ted.count("q") == 3
    assert sent[0]["limit"] == 1 and sent[0]["fields"] == ["publication-number"]


def test_search_pages_at_the_requested_size(monkeypatch):
    sent = []

    def post(client, payload):
        sent.append(payload)
        return {"notices": PAGE["notices"][:2] if payload["page"] == 1 else PAGE["notices"][2:],
                "totalNoticeCount": 3}

    monkeypatch.setattr(ted, "_post", post)
    got = list(ted.search("q", page_size=2))
    assert [n["publication-number"] for n in got] == ["103679-2021", "105063-2021", "102262-2021"]
    assert [p["limit"] for p in sent] == [2, 2]


def test_search_keeps_fields_times_page_size_within_teds_limit(monkeypatch):
    sent = []
    monkeypatch.setattr(ted, "_post", lambda client, payload: sent.append(payload) or {"notices": [], "totalNoticeCount": 0})
    list(ted.search("q"))
    assert len(sent[0]["fields"]) * sent[0]["limit"] <= ted.MAX_FIELDS_PER_PAGE
    assert sent[0]["limit"] == ted.MAX_FIELDS_PER_PAGE // len(ted.TED_FIELDS)
    sent.clear()
    list(ted.search("q", fields=["publication-number"], page_size=250))
    assert sent[0]["limit"] == 250                                   # a short field list keeps the full page


def test_month_windows_clip_to_the_range_and_split_into_weeks_then_days():
    assert pipeline._month_windows(date(2024, 2, 10), date(2024, 4, 16)) == [
        (date(2024, 2, 10), date(2024, 2, 29)), (date(2024, 3, 1), date(2024, 3, 31)),
        (date(2024, 4, 1), date(2024, 4, 16))]
    weeks = pipeline._split_window(date(2024, 2, 1), date(2024, 2, 29), "M")
    assert weeks[0] == (date(2024, 2, 1), date(2024, 2, 7))
    assert weeks[-1] == (date(2024, 2, 29), date(2024, 2, 29))
    assert pipeline._split_window(date(2024, 2, 1), date(2024, 2, 3), "W") == [
        (date(2024, 2, d),) * 2 for d in (1, 2, 3)]
