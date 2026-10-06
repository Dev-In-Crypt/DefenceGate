"""The Spanish run against a real Postgres.

What the unit tests cannot show is the path through the database: that everything
scanned is landed, that only the calls a supplier could answer become calls, that a
second night costs no writes, and that a call which closes is updated rather than
duplicated -- and that the new country filter and the per-source attribution reach
the API.
"""

from __future__ import annotations

import copy
from datetime import date

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, pipeline
from dgate.sources import bdns

pytestmark = pytest.mark.integration

CDTI = {
    "codigoBDNS": "912587",
    "organo": {"nivel1": "ESTADO", "nivel2": "MINISTERIO DE CIENCIA, INNOVACIÓN Y UNIVERSIDADES",
               "nivel3": "CENTRO PARA EL DESARROLLO TECNOLÓGICO Y LA INNOVACIÓN E.P.E."},
    "fechaRecepcion": "2026-09-30",
    "tipoConvocatoria": "Concurrencia competitiva - canónica",
    "presupuestoTotal": 5000000,
    "descripcion": "Resolución del CDTI por la que se convocan ayudas a proyectos de I+D",
    "tiposBeneficiarios": [{"descripcion": "GRAN EMPRESA"}],
    "sectores": [{"descripcion": "Investigación y desarrollo", "codigo": "72"}],
    "descripcionFinalidad": "Investigación, desarrollo e innovación",
    "abierto": True, "fechaInicioSolicitud": "2026-10-01", "fechaFinSolicitud": "2099-12-31",
}
INTA_SCHOLARSHIP = {
    **CDTI, "codigoBDNS": "894036",
    "organo": {"nivel1": "ESTADO", "nivel2": "MINISTERIO DE DEFENSA",
               "nivel3": "INSTITUTO NACIONAL DE TÉCNICA AEROESPACIAL (INTA)"},
    "descripcion": "Convocatoria de becas del INTA",
    "tiposBeneficiarios": [{"descripcion": "PERSONAS FÍSICAS QUE NO DESARROLLAN ACTIVIDAD ECONÓMICA"}],
}
DIRECT_GRANT = {**CDTI, "codigoBDNS": "900002",
                "tipoConvocatoria": "Concesión directa - canónica",
                "descripcion": "Concesión directa de ayudas del CDTI"}
CULTURE = {**CDTI, "codigoBDNS": "900003",
           "organo": {"nivel2": "MINISTERIO DE CULTURA", "nivel3": "DG DEL LIBRO"},
           "descripcion": "Ayudas a la edición de libros"}


def _row(detail):
    organ = detail["organo"]
    return {"id": int(detail["codigoBDNS"]), "numeroConvocatoria": detail["codigoBDNS"],
            "descripcion": detail["descripcion"], "fechaRecepcion": detail["fechaRecepcion"],
            "nivel1": "ESTADO", "nivel2": organ.get("nivel2"), "nivel3": organ.get("nivel3")}


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(bdns, "REQUEST_PAUSE", 0.0)


def _register(monkeypatch, details):
    """Serve a register holding these calls."""
    by_number = {d["codigoBDNS"]: d for d in details}
    monkeypatch.setattr(bdns, "search_central",
                        lambda since, client=None, max_pages=0: iter([_row(d) for d in by_number.values()]))
    monkeypatch.setattr(bdns, "fetch_detail",
                        lambda number, client=None: copy.deepcopy(by_number[str(number)]))
    return by_number


def test_only_the_calls_a_supplier_could_answer_become_calls(conn, fs_store, monkeypatch):
    _register(monkeypatch, [CDTI, INTA_SCHOLARSHIP, DIRECT_GRANT, CULTURE])
    pipeline.run_bdns(days=14)

    rows = conn.execute(
        """SELECT c.native_id, c.country, c.issuer, c.regime, c.status, c.budget, c.budget_scope,
                  p.code AS programme FROM call c JOIN programme p ON p.id = c.programme_id
            WHERE c.country = 'ES'""").fetchall()
    assert [r["native_id"] for r in rows] == ["912587"]
    row = rows[0]
    assert (row["programme"], row["regime"], row["status"]) == ("ES-BDNS", "dual_use", "open")
    assert float(row["budget"]) == 5_000_000.0 and row["budget_scope"] == "call"
    assert "CENTRO PARA EL DESARROLLO" in row["issuer"]


def test_everything_scanned_is_landed_even_what_is_not_kept(conn, fs_store, monkeypatch):
    """Land everything, classify afterwards: a call passed over today may be wanted
    when the classifier changes, and the search row is what says it exists."""
    _register(monkeypatch, [CDTI, INTA_SCHOLARSHIP, DIRECT_GRANT, CULTURE])
    pipeline.run_bdns(days=14)
    landed = conn.execute(
        "SELECT count(*) n FROM raw_ingest r JOIN source s ON s.id = r.source_id "
        "WHERE s.code = 'es_bdns'").fetchone()["n"]
    # four search rows, plus the detail of the three candidates (culture is not one)
    assert landed == 4 + 3


def test_a_second_night_lands_nothing_new_and_changes_nothing(conn, fs_store, monkeypatch):
    _register(monkeypatch, [CDTI])
    pipeline.run_bdns(days=14)
    first = conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"]
    pipeline.run_bdns(days=14)
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == first
    runs = conn.execute(
        """SELECT records_new, records_changed, status FROM ingest_run r
             JOIN source s ON s.id = r.source_id WHERE s.code = 'es_bdns' ORDER BY r.id""").fetchall()
    assert [(r["records_new"], r["records_changed"]) for r in runs] == [(1, 0), (0, 0)]


def test_a_call_that_closes_is_updated_not_duplicated(conn, fs_store, monkeypatch):
    register = _register(monkeypatch, [CDTI])
    pipeline.run_bdns(days=14)
    register["912587"]["abierto"] = False
    register["912587"]["fechaFinSolicitud"] = date.today().isoformat()    # still this year
    pipeline.run_bdns(days=14)

    rows = conn.execute("SELECT status, deadline_at FROM call WHERE country = 'ES'").fetchall()
    assert [r["status"] for r in rows] == ["closed"]


def test_a_call_already_held_is_re_read_even_when_the_window_no_longer_shows_it(
        conn, fs_store, monkeypatch):
    """Registered in September, closed in November: the search window of November does
    not list it, and it would stay `open` for ever if only the window were read."""
    register = _register(monkeypatch, [CDTI])
    pipeline.run_bdns(days=14)

    monkeypatch.setattr(bdns, "search_central", lambda since, client=None, max_pages=0: iter([]))
    register["912587"]["abierto"] = False
    register["912587"]["fechaFinSolicitud"] = date.today().isoformat()
    pipeline.run_bdns(days=14)
    assert conn.execute("SELECT status FROM call WHERE country = 'ES'").fetchone()["status"] \
        == "closed"


def test_one_unreadable_call_does_not_stop_the_run(conn, fs_store, monkeypatch):
    other = {**CDTI, "codigoBDNS": "912588"}
    _register(monkeypatch, [CDTI, other])
    real = bdns.fetch_detail

    def flaky(number, client=None):
        if str(number) == "912587":
            raise RuntimeError("404 withdrawn")
        return real(number, client=client)

    monkeypatch.setattr(bdns, "fetch_detail", flaky)
    pipeline.run_bdns(days=14)
    assert [r["native_id"] for r in conn.execute(
        "SELECT native_id FROM call WHERE country = 'ES'").fetchall()] == ["912588"]


def test_the_country_and_the_source_attribution_reach_the_api(conn, fs_store, monkeypatch):
    _register(monkeypatch, [CDTI])
    pipeline.run_bdns(days=14)
    conn.commit()
    with TestClient(api.app) as client:
        spanish = client.get("/v1/calls?country=ES&status=all").json()
        assert [c["native_id"] for c in spanish] == ["912587"]
        assert spanish[0]["country"] == "ES"
        assert "CENTRO PARA EL DESARROLLO" in spanish[0]["issuer"]
        assert spanish[0]["attribution"].startswith("Fuente: Base de Datos Nacional de Subvenciones")
        assert client.get("/v1/calls?country=PL&status=all").json() == []
