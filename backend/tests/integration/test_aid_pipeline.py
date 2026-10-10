"""The French agency run against a real Postgres.

The unit tests cover the date phrasings; this is the path through the database: every page
landed once per distinct content, the ones in scope becoming calls, a call that moves from
one list to the other staying one row, and the attribution the source row states reaching
the API.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, pipeline
from dgate.sources import aid

pytestmark = pytest.mark.integration


def _page(slug, title, text, *, listed="cours", published="2026-03-17"):
    return {
        "url": f"https://www.defense.gouv.fr/aid/appels-projets/{listed}/{slug}",
        "slug": slug, "list": listed, "title": title,
        "summary": "Resume. Contact : agent@defense.gouv.fr",
        "published": published, "modified": published, "text": text,
    }


ASTRID = _page("astrid-2026", "ASTRID 2026 : Accompagnement Specifique",
               "Ouverture : 16/12/2025 a 09:00 CET Limite de depot des projets : 02/03/2030 a 15:00 CET")
DEFI = _page("defi-cyber", "Participez au Defi Cyber", "Vous avez jusqu'au vendredi 29 mai pour candidater.",
             published="2026-03-17")
OLD = _page("ami-2023", "Appel a Manifestation d'Interet", "Fermeture : 15/09/2023 a 15h00",
            listed="clotures", published="2023-07-21")
RAPID = _page("rapid", "RAPID (Regime d'APpui a l'Innovation Duale)",
              "Appel a projets permanent", listed="standing", published="2024-02-01")


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


def _pages(monkeypatch, records):
    monkeypatch.setattr(aid, "fetch_all", lambda client=None: copy.deepcopy(records))


def test_only_the_pages_in_scope_become_calls(conn, fs_store, monkeypatch):
    _pages(monkeypatch, [ASTRID, OLD, RAPID])
    pipeline.run_aid()

    rows = conn.execute(
        """SELECT c.native_id, c.country, c.issuer, c.regime, c.status, c.type_of_action,
                  c.deadline_at, p.code AS programme
             FROM call c JOIN programme p ON p.id = c.programme_id
            WHERE c.country = 'FR' ORDER BY c.native_id""").fetchall()
    assert [r["native_id"] for r in rows] == ["astrid-2026", "rapid"]
    astrid, rapid = rows
    assert (astrid["programme"], astrid["regime"], astrid["status"], astrid["type_of_action"]) == \
        ("FR-AID", "defence", "open", "research grant")
    assert astrid["deadline_at"].year == 2030
    assert (rapid["status"], rapid["deadline_at"]) == ("open", None)   # a standing call


def test_every_page_is_landed_even_the_ones_not_kept(conn, fs_store, monkeypatch):
    _pages(monkeypatch, [ASTRID, OLD, RAPID])
    pipeline.run_aid()
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 3


def test_a_second_night_lands_nothing_new_and_changes_nothing(conn, fs_store, monkeypatch):
    _pages(monkeypatch, [ASTRID, OLD, RAPID])
    pipeline.run_aid()
    pipeline.run_aid()
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 3
    runs = conn.execute(
        """SELECT records_fetched, records_new, records_changed FROM ingest_run r
             JOIN source s ON s.id = r.source_id WHERE s.code = 'fr_aid' ORDER BY r.id""").fetchall()
    assert [(r["records_new"], r["records_changed"]) for r in runs] == [(2, 0), (0, 0)]


def test_a_call_that_moves_between_the_lists_stays_one_row(conn, fs_store, monkeypatch):
    """Its path changes from /cours/ to /clotures/; its slug does not."""
    _pages(monkeypatch, [DEFI])
    pipeline.run_aid()
    moved = _page("defi-cyber", "Participez au Defi Cyber",
                  "Vous avez jusqu'au vendredi 29 mai pour candidater.", listed="clotures")
    _pages(monkeypatch, [moved])
    pipeline.run_aid()
    rows = conn.execute("SELECT status, source_url FROM call WHERE country = 'FR'").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "closed" and "/clotures/" in rows[0]["source_url"]


def test_the_attribution_and_the_url_reach_the_api(conn, fs_store, monkeypatch):
    _pages(monkeypatch, [ASTRID])
    pipeline.run_aid()
    conn.commit()
    with TestClient(api.app) as client:
        french = client.get("/v1/calls?country=FR").json()
        assert [c["native_id"] for c in french] == ["astrid-2026"]
        call = french[0]
        assert call["attribution"].startswith("Source : Agence de l'innovation de defense")
        assert call["issuer"].startswith("Agence de l'innovation de defense")
        assert call["source_url"].endswith("/aid/appels-projets/cours/astrid-2026")
        one = client.get(f"/v1/calls/{call['id']}").json()
        assert "agent@defense.gouv.fr" not in json.dumps(one)


def test_the_landed_page_carries_no_address(conn, fs_store, monkeypatch):
    from dgate.rawstore import build_store

    _pages(monkeypatch, [ASTRID])
    pipeline.run_aid()
    key = conn.execute("SELECT storage_key FROM raw_ingest").fetchone()["storage_key"]
    assert "agent@defense.gouv.fr" not in json.dumps(build_store().get(key), ensure_ascii=False)
