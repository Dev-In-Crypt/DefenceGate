"""WP-162 section 5 wired to WP-160 (merge, 31 Oct 2026): the supplier report lists the contracts under its codes ending in
the next 12 months by WP-160's rule: stated and computed ends, soonest first, never an estimate, nothing outside the codes."""

# ruff: noqa: F811 - the fixture `client` comes from test_accounts.py
from __future__ import annotations

from datetime import timedelta

import pytest

from dgate import sell_report
from tests.integration.test_accounts import client  # noqa: F401
from tests.integration.test_wp160 import TODAY, bases

pytestmark = pytest.mark.integration


def test_section_5_lists_stated_and_computed_ends_under_the_codes(client, conn):
    b = bases(conn)
    rows = sell_report.ending_soon(conn, ["35410000"], ["DE"], TODAY)
    assert [r["href"].rsplit("/", 1)[-1].split("-", 1)[0] for r in rows] == [str(b["stated"]), str(b["computed"])]
    assert [r["endBasis"] for r in rows] == ["stated", "computed"]
    assert rows[0]["endStated"] is True and rows[1]["endStated"] is False
    assert rows[0]["end"] == TODAY + timedelta(days=60)
    assert sell_report.ending_soon(conn, ["30200000"], ["DE"], TODAY) == []
    assert sell_report.ending_soon(conn, ["35410000"], ["ES"], TODAY) == []
