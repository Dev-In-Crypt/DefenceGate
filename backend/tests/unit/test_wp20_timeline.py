"""WP-20: the version lines a reader sees (UX walk-throughs of 16 October 2026)."""

from __future__ import annotations

from datetime import datetime, timezone

from dgate.tenders import link_host, search_words, timeline

AT = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _row(version, changed, kinds=(), **payload):
    return {"version": version, "observed_at": AT, "changed_fields": changed,
            "payload": payload, "kinds": list(kinds)}


def test_a_source_link_that_only_moved_inside_the_same_site_is_no_line():
    rows = [
        _row(1, [], source_url="https://ezamowienia.gov.pl/mp-client/notice/4b1f-aaaa"),
        _row(2, ["source_url"], source_url="https://ezamowienia.gov.pl/mp-client/notice/9c2e-bbbb"),
    ]
    assert len(timeline(rows)) == 1                  # not an amendment: no raw URL swap listed


def test_a_source_link_that_moved_to_another_site_names_the_sites_not_the_addresses():
    rows = [
        _row(1, [], source_url="https://ezamowienia.gov.pl/mp-client/notice/4b1f-aaaa"),
        _row(2, ["source_url"], source_url="https://www.ted.europa.eu/en/notice/-/detail/1-2026"),
    ]
    entry = timeline(rows)[1]
    assert entry["changes"] == [{"field": "source_url", "label": "Source link",
                                 "before": "ezamowienia.gov.pl", "after": "ted.europa.eu"}]


def test_link_host():
    assert link_host("HTTP://www.Example.org/a?b=c") == "example.org"
    assert link_host(None) is None and link_host("") is None


def test_a_history_version_stays_in_the_timeline_marked_historic():
    rows = [
        _row(1, [], deadline_at="2022-03-16T12:00:00+00:00"),
        _row(2, ["deadline_at"], ["history"], deadline_at="2022-03-31T12:00:00+00:00"),
        _row(3, ["deadline_at"], [], deadline_at="2022-04-05T12:00:00+00:00"),
    ]
    got = timeline(rows)
    assert [e["historic"] for e in got] == [False, True, False]
    # the change after it is measured from the historic state, not from the first
    assert got[2]["changes"][0]["before"].startswith("31 Mar 2022")


def test_search_words_split_on_punctuation_and_keep_letters():
    assert search_words("Off-Road, Fahrzeuge (Ausrüstung)") == ["Off", "Road", "Fahrzeuge", "Ausrüstung"]
    assert search_words(" - / ") == []
    assert len(search_words("a b c d e f g h")) == 6
