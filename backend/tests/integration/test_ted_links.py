"""One notice published in two places: the link, the API and the backfill.

A Dutch notice above the EU thresholds is on TenderNed and again on TED, and
TenderNed says so in the record. The serving layer must show it once, never lose
it when a filter keeps only one of the two, and say where else it was published.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, pipeline
from dgate.normalise import Opportunity
from dgate.ops import link_ted
from dgate.rawstore import build_store
from dgate.sources import tenderned

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


def _put(conn, source: str, native_id: str, *, ted_ref: str | None = None,
         cpv: tuple[str, ...] = ("35700000",), status: str = "open") -> int:
    opp = Opportunity(
        source_code=source, native_id=native_id, buyer_name_raw="Ministerie van Defensie",
        title_original=f"Notice {native_id}", country="NL", published_at=date(2026, 10, 1),
        deadline_at=FUTURE, cpv_codes=list(cpv), status=status, is_defence=True,
        sig_cpv=True, ted_ref=ted_ref)
    opp_id, _ = db.upsert_opportunity(conn, opp, f"hash-{source}-{native_id}",
                                      db.source_id(conn, source))
    conn.commit()
    return opp_id


def _list(client, **params) -> list[dict]:
    return client.get("/v1/opportunities", params={"scope": "all", **params}).json()


def test_a_notice_forwarded_to_ted_is_listed_once_and_says_where_else_it_is(conn):
    ted_id = _put(conn, "ted", "696956-2026")
    nl_id = _put(conn, "nl_tenderned", "443966", ted_ref="696956-2026")
    _put(conn, "nl_tenderned", "999")           # national only: nothing to collapse
    with TestClient(api.app) as client:
        served = _list(client)
        assert sorted(o["native_id"] for o in served) == ["696956-2026", "999"]
        ted = next(o for o in served if o["native_id"] == "696956-2026")
        assert [(t["id"], t["source"], t["native_id"]) for t in ted["same_notice"]] == \
            [(nl_id, "nl_tenderned", "443966")]

        everything = _list(client, collapse="false")
        assert len(everything) == 3
        national = client.get(f"/v1/opportunities/{nl_id}").json()
        assert [(t["id"], t["source"]) for t in national["same_notice"]] == [(ted_id, "ted")]


def test_a_filter_that_keeps_only_the_national_row_never_loses_the_notice(conn):
    """The Dutch notice carries a CPV code its TED twin does not. Hiding it
    because a twin exists, when the twin is not in the result, would make the
    notice vanish from exactly the search that should find it."""
    _put(conn, "ted", "696956-2026", cpv=("35700000",))
    _put(conn, "nl_tenderned", "443966", ted_ref="696956-2026", cpv=("90500000",))
    with TestClient(api.app) as client:
        assert [o["native_id"] for o in _list(client, cpv="9050")] == ["443966"]


def test_a_reference_to_a_ted_notice_we_do_not_hold_hides_nothing(conn):
    _put(conn, "nl_tenderned", "443966", ted_ref="123-2026")
    with TestClient(api.app) as client:
        served = _list(client)
    assert [o["native_id"] for o in served] == ["443966"]
    assert served[0]["same_notice"] == []


def test_the_backfill_links_records_ingested_before_the_column_existed(
        conn, fs_store, monkeypatch):
    record = {
        "publicatieId": "443966", "publicatieDatum": "2026-10-09",
        "typePublicatie": {"code": "AAO", "omschrijving": "Aankondiging opdracht"},
        "aanbestedingNaam": "Opdracht", "opdrachtgeverNaam": "Gemeente Voorbeeld",
        "sluitingsDatum": "2026-11-19T17:00:00",
        "publicatiecode": {"code": "EF18", "omschrijving": "defensierichtlijn"},
        "detail": {"publicatieId": 443966, "pbNummerTed": "00696956-2026",
                   "cpvCodes": [{"isHoofdOpdracht": True, "code": "35700000-1"}]},
    }
    monkeypatch.setattr(tenderned, "fetch_window", lambda days_back=2: iter([record]))
    pipeline.run_tenderned(days=2)
    conn.execute("UPDATE opportunity SET ted_ref = NULL")      # as before the migration
    conn.commit()

    read, linked = link_ted.backfill(conn, build_store(), "nl_tenderned", dry_run=True)
    assert (read, linked) == (1, 1)
    assert conn.execute("SELECT ted_ref FROM opportunity").fetchone()["ted_ref"] is None

    assert link_ted.backfill(conn, build_store(), "nl_tenderned") == (1, 1)
    assert conn.execute("SELECT ted_ref FROM opportunity").fetchone()["ted_ref"] == "696956-2026"
    # nothing left to do, and no version was written for a derived link
    assert link_ted.backfill(conn, build_store(), "nl_tenderned") == (0, 0)
    assert conn.execute("SELECT count(*) n FROM opportunity_version").fetchone()["n"] == 1
