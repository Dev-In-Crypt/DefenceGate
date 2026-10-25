"""WP-139 (verification round 8, system): a sitemap page of tenders stays under the 2 MB the site's fetch cache keeps, and
the TED award reader and the EU portal's topic-page run have floors measured from their history."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from dgate import config
from dgate.tenders import SITEMAP_ID_SPAN, SitemapPage

# Next.js keeps no fetch answer over 2 MB ("items over 2MB can not be cached", web log of 25 Oct 2026)
FETCH_CACHE_MAX = 2 * 1024 * 1024
MONDAY = date(2026, 9, 7)


@pytest.fixture(autouse=True)
def clean_settings():
    config.reset_cache()
    yield
    config.reset_cache()


def test_a_full_sitemap_page_fits_the_sites_fetch_cache():
    """Every id of a range a core notice, each with a nine-digit id and the longest slug (60 characters of words): still
    under 2 MB. At 50,000 ids a page, pages of 23,000 notices were 3.0 MB and were rebuilt on every request."""
    words = "x" * 60
    page = SitemapPage(page=0, pages=1, items=[
        {"slug": f"{100_000_000 + i}-{words}", "updatedAt": datetime(2026, 10, 25, tzinfo=timezone.utc)}
        for i in range(SITEMAP_ID_SPAN)])
    assert len(page.model_dump_json().encode()) < FETCH_CACHE_MAX
    assert SITEMAP_ID_SPAN <= 50_000            # and within the sitemap protocol's 50,000 URLs a file


def test_the_award_reader_expects_result_notices_on_the_days_ted_brought_some():
    """Core result notices per TED publication day, 7 Sep - 23 Oct 2026: 5 to 27, Monday to Friday. The 14:10 run of
    Tuesday to Saturday reads one such day; Sunday's and Monday's none."""
    s = config.settings()
    floors = [s.floor("ted_awards", date(2026, 9, 7 + i)) for i in range(7)]
    assert floors == [0, 2, 2, 2, 2, 2, 0]
    assert max(floors) < 5                      # below the smallest day measured


def test_the_award_floor_can_be_set_from_the_environment(monkeypatch):
    monkeypatch.setenv("DGATE_FLOOR_TED_AWARDS", "7")
    config.reset_cache()
    assert config.settings().floor("ted_awards", MONDAY) == 7
