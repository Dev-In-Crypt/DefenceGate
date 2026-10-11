"""The Finnish run against a real Postgres: the one yearly page landed once per distinct
content, becoming a call with its deadline, sum and currency, and reaching the API."""

from __future__ import annotations

import copy
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, pipeline
from dgate.sources import matine

pytestmark = pytest.mark.integration

_URL = "https://defmin.fi/matine-maanpuolustuksen-tieteellinen-neuvottelukunta/maararahahaku-2027"


def _record(deadline: date, *, sum_text="yhteisarvoltaan enintään 1 850 000 euroa"):
    return {
        "url": _URL, "slug": "maararahahaku-2027", "year": 2027,
        "title": "Määrärahahaku 2027 - Puolustusministeriö",
        "text": (f"MATINE varautuu käynnistämään 10-20 tutkimushanketta, {sum_text}. "
                 f"Hakemusten määräaika on torstai {deadline.day}.{deadline.month}.{deadline.year} "
                 f"klo 16:00. MATINE päättää kokouksessaan 3.12.{deadline.year} hankkeet."),
    }


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


def _pages(monkeypatch, records):
    monkeypatch.setattr(matine, "fetch_all", lambda client=None: copy.deepcopy(records))


def test_the_yearly_page_becomes_one_call(conn, fs_store, monkeypatch):
    _pages(monkeypatch, [_record(date.today() + timedelta(days=30))])
    pipeline.run_matine()
    row = conn.execute(
        """SELECT c.native_id, c.country, c.regime, c.status, c.budget, c.currency, c.budget_scope,
                  c.issuer, p.code AS programme FROM call c JOIN programme p ON p.id = c.programme_id
            WHERE c.country = 'FI'""").fetchone()
    assert (row["programme"], row["native_id"], row["regime"], row["status"]) == \
        ("FI-MATINE", "maararahahaku-2027", "defence", "open")
    assert (float(row["budget"]), row["currency"], row["budget_scope"]) == (1_850_000.0, "EUR", "call")


def test_a_second_night_changes_nothing_and_lands_nothing(conn, fs_store, monkeypatch):
    _pages(monkeypatch, [_record(date.today() + timedelta(days=30))])
    pipeline.run_matine()
    pipeline.run_matine()
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 1
    runs = conn.execute(
        """SELECT records_new, records_changed FROM ingest_run r JOIN source s ON s.id = r.source_id
            WHERE s.code = 'fi_matine' ORDER BY r.id""").fetchall()
    assert [(r["records_new"], r["records_changed"]) for r in runs] == [(1, 0), (0, 0)]


def test_a_moved_deadline_is_applied_and_the_budget_kept_when_the_sum_goes_unstated(
        conn, fs_store, monkeypatch):
    first = date.today() + timedelta(days=30)
    _pages(monkeypatch, [_record(first)])
    pipeline.run_matine()
    later = first + timedelta(days=14)
    _pages(monkeypatch, [_record(later, sum_text="yhteisarvoltaan tarkemmin myöhemmin")])
    pipeline.run_matine()
    row = conn.execute("SELECT deadline_at, budget FROM call WHERE country = 'FI'").fetchone()
    assert row["deadline_at"].date() >= later - timedelta(days=1)
    assert float(row["budget"]) == 1_850_000.0


def test_the_country_the_sum_and_the_attribution_reach_the_api(conn, fs_store, monkeypatch):
    _pages(monkeypatch, [_record(date.today() + timedelta(days=30))])
    pipeline.run_matine()
    conn.commit()
    with TestClient(api.app) as client:
        finnish = client.get("/v1/calls?country=FI").json()
        assert [c["native_id"] for c in finnish] == ["maararahahaku-2027"]
        call = finnish[0]
        assert (call["country"], call["currency"], call["budget"]) == ("FI", "EUR", 1_850_000.0)
        assert call["attribution"].startswith("Lähde: Puolustusministeriö")
        assert call["source_url"] == _URL
        assert "Meikäläinen" not in json.dumps(client.get(f"/v1/calls/{call['id']}").json())
