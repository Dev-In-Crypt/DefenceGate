"""A TED list that ends before the count TED itself states is an error, not a short day."""

from __future__ import annotations

import pytest

from dgate.sources import ted


def _pages(monkeypatch, *pages):
    it = iter(pages)
    monkeypatch.setattr(ted, "_post", lambda client, payload: next(it))


def _notices(n: int) -> list[dict]:
    return [{"publication-number": str(i)} for i in range(n)]


def test_a_list_that_ends_short_of_the_stated_total_raises(monkeypatch):
    _pages(monkeypatch, {"notices": _notices(ted.PAGE_SIZE), "totalNoticeCount": 3 * ted.PAGE_SIZE},
           {"notices": [], "totalNoticeCount": 3 * ted.PAGE_SIZE})
    with pytest.raises(RuntimeError, match="cut short"):
        list(ted.search("q", client=object()))


def test_a_short_last_page_below_the_total_raises(monkeypatch):
    _pages(monkeypatch, {"notices": _notices(10), "totalNoticeCount": 500})
    with pytest.raises(RuntimeError, match="10 of 500"):
        list(ted.search("q", client=object()))


def test_a_complete_list_and_one_without_a_total_are_unchanged(monkeypatch):
    _pages(monkeypatch, {"notices": _notices(7), "totalNoticeCount": 7})
    assert len(list(ted.search("q", client=object()))) == 7
    _pages(monkeypatch, {"notices": _notices(7)})
    assert len(list(ted.search("q", client=object()))) == 7


def test_the_page_cap_is_an_error_when_more_is_stated(monkeypatch):
    full = {"notices": _notices(ted.PAGE_SIZE), "totalNoticeCount": 10 * ted.PAGE_SIZE}
    _pages(monkeypatch, full, full)
    with pytest.raises(RuntimeError, match="cut short"):
        list(ted.search("q", client=object(), max_pages=2))
