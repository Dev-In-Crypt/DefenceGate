"""One file number, two buyers: two notices, never one history.

Found by the spot check of 11 October 2026: in the Catalan feed `2582/2026` is a
police-vest supply of one municipality and park works of another. The key is
(source, native_id), so two *defence* notices sharing a number would have been one
row whose versions alternate between two buyers.
"""

from __future__ import annotations

from datetime import date

import pytest

from dgate import db
from dgate.normalise import Opportunity

pytestmark = pytest.mark.integration


def _put(conn, source: str, buyer: str, *, title: str = "Vests", native_id: str = "2582/2026",
         published: date = date(2026, 9, 21), digest: str | None = None) -> tuple[int, str]:
    opp = Opportunity(source_code=source, native_id=native_id, buyer_name_raw=buyer,
                      title_original=title, country="ES", published_at=published,
                      cpv_codes=["35815000"], is_defence=True, sig_cpv=True)
    out = db.upsert_opportunity(conn, opp, digest or f"{source}-{buyer}-{title}-{published}",
                                db.source_id(conn, source))
    conn.commit()
    return out


def test_two_buyers_with_the_same_number_are_two_notices(conn):
    first, _ = _put(conn, "es_placsp_agg", "Ajuntament del Prat de Llobregat")
    second, action = _put(conn, "es_placsp_agg", "Ajuntament de la Garriga", title="Park works")
    assert action == "new" and first != second

    rows = {r["id"]: r for r in conn.execute(
        "SELECT id, native_id, buyer_name_raw FROM opportunity ORDER BY id")}
    assert rows[first]["native_id"] == "2582/2026"          # the first holder is not moved
    assert rows[second]["native_id"].startswith("2582/2026#")
    assert rows[second]["buyer_name_raw"] == "Ajuntament de la Garriga"


def test_each_buyers_own_amendment_versions_its_own_row_only(conn):
    prat, _ = _put(conn, "es_placsp_agg", "Ajuntament del Prat de Llobregat")
    garriga, _ = _put(conn, "es_placsp_agg", "Ajuntament de la Garriga", title="Park works")

    same, action = _put(conn, "es_placsp_agg", "Ajuntament de la Garriga",
                        title="Park works, extended", published=date(2026, 9, 25))
    assert (same, action) == (garriga, "changed")
    versions = {r["opportunity_id"]: r["n"] for r in conn.execute(
        "SELECT opportunity_id, count(*) n FROM opportunity_version GROUP BY 1")}
    assert versions == {prat: 1, garriga: 2}

    again, action = _put(conn, "es_placsp_agg", "Ajuntament del Prat de Llobregat")
    assert (again, action) == (prat, "unchanged")


def test_a_difference_in_spelling_of_the_same_buyer_is_not_a_second_buyer(conn):
    first, _ = _put(conn, "es_placsp_agg", "Ajuntament del Prat de Llobregat")
    again, _ = _put(conn, "es_placsp_agg", "AJUNTAMENT DEL PRAT DE LLOBREGAT ",
                    title="Vests, corrected", published=date(2026, 9, 26))
    assert again == first
    assert conn.execute("SELECT count(*) n FROM opportunity").fetchone()["n"] == 1


def test_a_source_with_globally_unique_numbers_is_left_alone(conn):
    """TED's publication number identifies one notice. A different buyer name under
    it is the same notice, said differently, and must stay one history."""
    first, _ = _put(conn, "ted", "Ministry of Defence", native_id="696956-2026")
    again, action = _put(conn, "ted", "MoD", native_id="696956-2026", title="Vests, corrected",
                         published=date(2026, 9, 26))
    assert again == first and action == "changed"
