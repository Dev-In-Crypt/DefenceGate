"""WP-168: the pilot report command against a real Postgres, through the served functions on a read-only session: it writes one
valid HTML file, finds the call by its topic code, and names organisations only."""

from __future__ import annotations

import pytest

from dgate.ops import pilot_report
from tests.integration import test_wp32 as wp32
from tests.unit.test_wp168_pilot_report import valid_html

pytestmark = pytest.mark.integration

_fresh_cache = wp32._fresh_cache
space = wp32.space


def test_the_command_writes_a_valid_html_report_from_the_database(conn, space, tmp_path):
    person = wp32.org(conn, "John Smith", "FR")
    conn.execute("UPDATE organisation SET individual_reason = 'test' WHERE id = %s", (person,))
    wp32.join(conn, space["p"][0], person)
    conn.commit()
    cid, slug = wp32.call(conn, "edf1", "EDF-2026-DA-SPACE-PRS-STEP")
    out = tmp_path / "report.html"
    assert pilot_report.main(["--call", "EDF-2026-DA-SPACE-PRS-STEP", "--country", "es", "--ukraine",
                              "--consortium", wp32.make_slug(space["b"], "Bravo GmbH"), "--out", str(out)]) == 0
    doc = out.read_text(encoding="utf-8")
    valid_html(doc)
    assert f"/funding/{slug}" in doc
    assert doc.count('class="report-section"') == 5
    # the partner list of the call page, Spain first, past roles included
    assert doc.index("Charlie SL") < doc.index("Alpha SA") and "coordinator 1, participant 2" in doc
    assert "3 comparable projects read" in doc, "the evidence projects of the area"
    assert "Bravo GmbH" in doc and "Gaps" in doc
    assert "John Smith" not in doc, "a natural person is counted, never named"
    # nothing was written by the run
    assert conn.execute("SELECT count(*) AS n FROM call").fetchone()["n"] == 1
