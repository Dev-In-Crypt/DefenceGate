"""The Polish run against a real Postgres.

The unit tests cover the rules; this is the path through the database: the whole list
landed, only the tagged competitions a company may answer becoming calls, a second night
costing no writes, and the currency and country reaching the API.
"""

from __future__ import annotations

import copy
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, pipeline
from dgate.sources import ncbr

pytestmark = pytest.mark.integration

TODAY = date.today()


def _record(path, name, **over):
    record = {
        "name": name, "path": path, "publishDate": f"{TODAY.year}-07-01T10:00:00", "type": "NCBR",
        "description": "<p>Konkurs. Kontakt: dzial@ncbr.gov.pl</p>", "budget": "350 000 000 zł",
        "status": "APPLICATIONS_IN_PROGRESS",
        "typesOfApplicant": json.dumps(["large_enterprise", "consortium", "sme"]),
        "sourcesOfFunding": json.dumps(["eu_funds"]),
        "thematicAreas": json.dumps(["innovative_technologies", "defence_and_security"]),
        "programmeTypes": json.dumps(["eu"]),
        "dates": "[]", "announcementDate": f"{TODAY.year}-07-01T00:00:00",
        "applicationsStartDate": f"{TODAY.year}-07-01T09:00:00",
        "applicationsEndDate": (TODAY + timedelta(days=30)).isoformat() + "T16:00:00",
        "resultsDate": None,
    }
    record.update(over)
    return record


SMART = _record("/web/ncbr/smart-26", "SMART - Projekty realizowane w konsorcjach")
FELLOWSHIP = _record("/web/ncbr/nawa-26", "Polskie Powroty NAWA",
                     typesOfApplicant=json.dumps(["scientist", "individual"]))
UNTAGGED = _record("/web/ncbr/eureka-26", "EUREKA",
                   thematicAreas=json.dumps(["innovative_technologies"]))
OLD_PERUN = _record("/web/ncbr/perun-23", "Konkurs nr 1/PERUN/2023",
                    status="APPLICATIONS_IN_EVALUATION",
                    programmeTypes=json.dumps(["defence_security"]),
                    applicationsEndDate="2024-01-31T16:00:00")


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


def _list(monkeypatch, records):
    monkeypatch.setattr(ncbr, "fetch_all", lambda client=None: copy.deepcopy(records))


def test_only_the_tagged_competitions_a_company_may_answer_become_calls(conn, fs_store, monkeypatch):
    _list(monkeypatch, [SMART, FELLOWSHIP, UNTAGGED, OLD_PERUN])
    pipeline.run_ncbr()

    rows = conn.execute(
        """SELECT c.native_id, c.country, c.issuer, c.regime, c.status, c.budget, c.currency,
                  c.budget_scope, p.code AS programme
             FROM call c JOIN programme p ON p.id = c.programme_id WHERE c.country = 'PL'""").fetchall()
    assert [r["native_id"] for r in rows] == ["/web/ncbr/smart-26"]
    row = rows[0]
    assert (row["programme"], row["regime"], row["status"]) == ("PL-NCBR", "dual_use", "open")
    assert (float(row["budget"]), row["currency"], row["budget_scope"]) == (350_000_000.0, "PLN", "call")
    assert "NCBR" in row["issuer"]


def test_everything_listed_is_landed_even_what_is_not_kept(conn, fs_store, monkeypatch):
    _list(monkeypatch, [SMART, FELLOWSHIP, UNTAGGED, OLD_PERUN])
    pipeline.run_ncbr()
    landed = conn.execute(
        "SELECT count(*) n FROM raw_ingest r JOIN source s ON s.id = r.source_id "
        "WHERE s.code = 'pl_ncbr'").fetchone()["n"]
    assert landed == 4


def test_a_second_night_lands_nothing_new_and_changes_nothing(conn, fs_store, monkeypatch):
    _list(monkeypatch, [SMART, FELLOWSHIP, UNTAGGED, OLD_PERUN])
    pipeline.run_ncbr()
    pipeline.run_ncbr()
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 4
    runs = conn.execute(
        """SELECT records_fetched, records_new, records_changed FROM ingest_run r
             JOIN source s ON s.id = r.source_id WHERE s.code = 'pl_ncbr' ORDER BY r.id""").fetchall()
    assert [(r["records_fetched"], r["records_new"], r["records_changed"]) for r in runs] \
        == [(4, 1, 0), (4, 0, 0)]


def test_a_competition_that_closes_is_updated_not_duplicated(conn, fs_store, monkeypatch):
    _list(monkeypatch, [SMART])
    pipeline.run_ncbr()
    closed = _record("/web/ncbr/smart-26", "SMART - Projekty realizowane w konsorcjach",
                     status="APPLICATIONS_IN_EVALUATION",
                     applicationsEndDate=TODAY.isoformat() + "T16:00:00")
    _list(monkeypatch, [closed])
    pipeline.run_ncbr()
    rows = conn.execute("SELECT status FROM call WHERE country = 'PL'").fetchall()
    assert [r["status"] for r in rows] == ["closed"]


def test_a_budget_that_is_not_a_sum_does_not_wipe_one_already_known(conn, fs_store, monkeypatch):
    """The portal rewrites a budget field as prose. A competition whose text stops being
    parseable must keep the sum that was read before: a field the source did not supply
    is never written over what is there."""
    _list(monkeypatch, [SMART])
    pipeline.run_ncbr()
    prose = _record("/web/ncbr/smart-26", "SMART - Projekty realizowane w konsorcjach",
                    budget="Alokacja zostanie określona w regulaminie")
    _list(monkeypatch, [prose])
    pipeline.run_ncbr()
    row = conn.execute("SELECT budget, currency FROM call WHERE country = 'PL'").fetchone()
    assert (float(row["budget"]), row["currency"]) == (350_000_000.0, "PLN")


def test_the_country_the_currency_and_the_attribution_reach_the_api(conn, fs_store, monkeypatch):
    _list(monkeypatch, [SMART])
    pipeline.run_ncbr()
    conn.commit()
    with TestClient(api.app) as client:
        polish = client.get("/v1/calls?country=PL").json()
        assert [c["native_id"] for c in polish] == ["/web/ncbr/smart-26"]
        call = polish[0]
        assert (call["country"], call["currency"], call["budget"]) == ("PL", "PLN", 350_000_000.0)
        assert call["attribution"].startswith("Zrodlo: Narodowe Centrum Badan i Rozwoju")
        assert call["source_url"] == "https://www.gov.pl/web/ncbr/smart-26"
        assert client.get("/v1/calls?country=ES").json() == []
        one = client.get(f"/v1/calls/{call['id']}").json()
        assert "dzial@ncbr.gov.pl" not in json.dumps(one)
        assert "Konkurs. Kontakt" not in json.dumps(one)


def test_the_descriptions_are_landed_but_never_served(conn, fs_store, monkeypatch):
    """The text is CC BY-SA 4.0. It lives in the raw archive, redacted of addresses, and
    the API serves facts and a link."""
    from dgate.rawstore import build_store

    _list(monkeypatch, [SMART])
    pipeline.run_ncbr()
    key = conn.execute("SELECT storage_key FROM raw_ingest").fetchone()["storage_key"]
    landed = build_store().get(key)
    assert "Konkurs. Kontakt" in landed["description"]
    assert "dzial@ncbr.gov.pl" not in landed["description"]
