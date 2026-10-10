"""The Swedish run against a real Postgres.

The unit tests cover the rules; this is the path through the database: the whole
register landed, only the publisher's defence programmes becoming calls, a second night
costing no writes, and the country, currency and attribution reaching the API.
"""

from __future__ import annotations

import copy
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, pipeline
from dgate.sources import vinnova

pytestmark = pytest.mark.integration

TODAY = date.today()


def _round(dnr, title, *, programme="civil-militära synergier", publik=1, text=None,
           closes=None, opens=None):
    return {
        "Diarienummer": dnr, "DiarienummerUtlysning": "2024-01511", "Titel": title,
        "TitelEngelska": "", "Oppningsdatum": (opens or TODAY - timedelta(days=30)).isoformat() + "T00:00:00",
        "Stangningsdatum": (closes or TODAY + timedelta(days=20)).isoformat() + "T14:00:00",
        "UppskattatBeslutsdatum": None, "Publik": publik, "Webbsida": publik,
        "WebTextLista": [{"TextSv": text or "Svenska företag kan söka.", "TextEn": ""}],
        "LankLista": [{"Beskrivning": "Ansök här", "URL": f"https://ansok.vinnova.se/utlysning/{dnr}"}],
        "DokumentLista": [],
        "KontaktLista": [{"Namn": "Per Persson", "Epost": "per.persson@vinnova.se"}],
        "utlysning": {"Diarienummer": "2024-01511", "Titel": "Civil-militära synergier",
                      "TitelEngelska": "Civil-military synergies", "DiarienummerProgram": "P1"},
        "program": {"Diarienummer": "P1", "Titel": f"Innovationsprogrammet för {programme}",
                    "TitelEngelska": ""},
    }


OPEN = _round("2026-01503", "Stärkt ekosystem för civil-militär innovationssamverkan",
              text="Den totala budgeten för utlysningen är 12 miljoner kronor.")
INVITED = _round("2025-00979", "Extra omgång", publik=0)
CIVIL = _round("2026-00496", "Test och evaluering", programme="civilt försvar")
OTHER = _round("2025-04680", "Rymdsektorn", programme="sjätte generationens mobilnät")


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


def _register(monkeypatch, records):
    monkeypatch.setattr(vinnova, "fetch_all", lambda client=None: copy.deepcopy(records))


def test_only_the_defence_programmes_public_rounds_become_calls(conn, fs_store, monkeypatch):
    _register(monkeypatch, [OPEN, INVITED, CIVIL, OTHER])
    pipeline.run_vinnova()

    rows = conn.execute(
        """SELECT c.native_id, c.country, c.issuer, c.regime, c.status, c.budget, c.currency,
                  c.budget_scope, p.code AS programme
             FROM call c JOIN programme p ON p.id = c.programme_id
            WHERE c.country = 'SE' ORDER BY c.native_id""").fetchall()
    assert [r["native_id"] for r in rows] == ["2026-00496", "2026-01503"]
    civil, open_ = rows
    assert (open_["programme"], open_["regime"], open_["status"], open_["issuer"]) == \
        ("SE-VINNOVA", "defence", "open", "Vinnova")
    assert (float(open_["budget"]), open_["currency"], open_["budget_scope"]) == \
        (12_000_000.0, "SEK", "call")
    assert civil["regime"] == "dual_use"


def test_everything_in_the_register_is_landed_even_what_is_not_kept(conn, fs_store, monkeypatch):
    _register(monkeypatch, [OPEN, INVITED, CIVIL, OTHER])
    pipeline.run_vinnova()
    landed = conn.execute(
        "SELECT count(*) n FROM raw_ingest r JOIN source s ON s.id = r.source_id "
        "WHERE s.code = 'se_vinnova'").fetchone()["n"]
    assert landed == 4


def test_a_second_night_lands_nothing_new_and_changes_nothing(conn, fs_store, monkeypatch):
    _register(monkeypatch, [OPEN, INVITED, CIVIL, OTHER])
    pipeline.run_vinnova()
    pipeline.run_vinnova()
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 4
    runs = conn.execute(
        """SELECT records_fetched, records_new, records_changed FROM ingest_run r
             JOIN source s ON s.id = r.source_id WHERE s.code = 'se_vinnova' ORDER BY r.id"""
    ).fetchall()
    assert [(r["records_fetched"], r["records_new"], r["records_changed"]) for r in runs] \
        == [(4, 2, 0), (4, 0, 0)]


def test_a_round_that_closes_is_updated_not_duplicated(conn, fs_store, monkeypatch):
    _register(monkeypatch, [OPEN])
    pipeline.run_vinnova()
    closed = _round("2026-01503", "Stärkt ekosystem för civil-militär innovationssamverkan",
                    text="Den totala budgeten för utlysningen är 12 miljoner kronor.",
                    closes=TODAY - timedelta(days=1))
    _register(monkeypatch, [closed])
    pipeline.run_vinnova()
    rows = conn.execute("SELECT status FROM call WHERE country = 'SE'").fetchall()
    assert [r["status"] for r in rows] == ["closed"]


def test_a_budget_that_stops_being_stated_does_not_wipe_one_already_known(
        conn, fs_store, monkeypatch):
    _register(monkeypatch, [OPEN])
    pipeline.run_vinnova()
    reworded = _round("2026-01503", "Stärkt ekosystem för civil-militär innovationssamverkan",
                      text="Svenska företag kan söka.")
    _register(monkeypatch, [reworded])
    pipeline.run_vinnova()
    row = conn.execute("SELECT budget, currency FROM call WHERE country = 'SE'").fetchone()
    assert (float(row["budget"]), row["currency"]) == (12_000_000.0, "SEK")


def test_the_country_the_currency_and_the_attribution_reach_the_api(conn, fs_store, monkeypatch):
    _register(monkeypatch, [OPEN])
    pipeline.run_vinnova()
    conn.commit()
    with TestClient(api.app) as client:
        swedish = client.get("/v1/calls?country=SE").json()
        assert [c["native_id"] for c in swedish] == ["2026-01503"]
        call = swedish[0]
        assert (call["country"], call["currency"], call["budget"]) == ("SE", "SEK", 12_000_000.0)
        assert call["attribution"].startswith("Källa: Vinnova")
        assert call["source_url"] == "https://ansok.vinnova.se/utlysning/2026-01503"
        one = client.get(f"/v1/calls/{call['id']}").json()
        assert "per.persson@vinnova.se" not in json.dumps(one)


def test_the_landed_payload_carries_no_contact_person(conn, fs_store, monkeypatch):
    from dgate.rawstore import build_store

    _register(monkeypatch, [OPEN])
    pipeline.run_vinnova()
    key = conn.execute("SELECT storage_key FROM raw_ingest").fetchone()["storage_key"]
    landed = json.dumps(build_store().get(key), ensure_ascii=False)
    assert "per.persson@vinnova.se" not in landed and "KontaktLista" not in landed
