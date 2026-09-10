"""Job outcome logic (plan task M0-10).

The point of these tests is one rule: a job is a success only if it finished
*and* every source it touched reported success. A run that finished below its
coverage floor must be `partial` and must alert, because silent
under-collection is the failure mode that quietly destroys a coverage promise.
"""

import pytest

from dgate import worker


@pytest.fixture()
def captured(monkeypatch):
    """Capture alerts and healthcheck pings instead of sending them."""
    alerts: list[str] = []
    pings: list[tuple[str, str]] = []
    monkeypatch.setattr(worker, "notify", lambda text, **kw: alerts.append(text) or True)
    monkeypatch.setattr(worker, "ping", lambda slug, event="success", **kw:
                        pings.append((slug, event)) or True)
    return alerts, pings


def test_clean_run_is_success_and_pings_success(captured, monkeypatch):
    alerts, pings = captured
    monkeypatch.setattr(worker, "source_run_status",
                        lambda codes: [(c, "success", 100, "") for c in codes])
    result = worker.run_job("ted_daily", lambda: None, sources=["ted"])
    assert result.status == "success" and result.ok
    assert alerts == [], "a healthy run must not page anybody"
    assert pings == [("ted-daily", "start"), ("ted-daily", "success")]


def test_raised_exception_is_failed_and_alerts(captured):
    alerts, pings = captured

    def boom() -> None:
        raise RuntimeError("getaddrinfo failed")

    result = worker.run_job("ted_daily", boom, sources=["ted"])
    assert result.status == "failed"
    assert not result.ok
    assert "FAILED" in alerts[0] and "getaddrinfo" in alerts[0]
    assert ("ted-daily", "fail") in pings


def test_under_floor_run_is_partial_not_success(captured, monkeypatch):
    """The run finished. It still is not a green tick."""
    alerts, pings = captured
    monkeypatch.setattr(worker, "source_run_status",
                        lambda codes: [("ted", "partial", 1, "fetched 1 below floor 5")])
    result = worker.run_job("ted_daily", lambda: None, sources=["ted"])
    assert result.status == "partial"
    assert not result.ok, "partial must never be reported as success"
    assert "degraded" in alerts[0] and "below floor" in alerts[0]
    assert ("ted-daily", "fail") in pings


def test_missing_run_record_is_also_degraded(captured, monkeypatch):
    """A connector that never even started a run must not look healthy."""
    alerts, _ = captured
    monkeypatch.setattr(worker, "source_run_status",
                        lambda codes: [("es_placsp_agg", "missing", 0, "no run recorded")])
    result = worker.run_job("placsp_daily", lambda: None, sources=["es_placsp_agg"])
    assert result.status == "partial"
    assert "es_placsp_agg" in alerts[0]


def test_one_bad_source_among_several_still_degrades_the_job(captured, monkeypatch):
    alerts, _ = captured
    monkeypatch.setattr(worker, "source_run_status", lambda codes: [
        ("es_placsp", "success", 500, ""),
        ("es_placsp_agg", "partial", 2, "fetched 2 below floor 10"),
    ])
    result = worker.run_job("placsp_daily", lambda: None,
                            sources=["es_placsp", "es_placsp_agg"])
    assert result.status == "partial"
    assert "es_placsp_agg" in alerts[0]
    assert "es_placsp:" not in alerts[0], "only the degraded source belongs in the alert"


def test_unreadable_ingest_run_table_degrades_rather_than_hides(captured, monkeypatch):
    alerts, _ = captured

    def explode(codes):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(worker, "source_run_status", explode)
    result = worker.run_job("ted_daily", lambda: None, sources=["ted"])
    assert result.status == "partial"
    assert "could not read ingest_run" in alerts[0]


def test_schedule_is_described_for_operators():
    lines = worker.describe_schedule()
    assert any("ezamowienia" in line for line in lines)
    assert any("ted_daily" in line for line in lines)
    assert any("placsp_daily" in line for line in lines)
    assert any("health_report" in line for line in lines)
    assert any("backup_nightly" in line for line in lines)
    assert any("backup_verify" in line for line in lines)


def test_every_job_is_reachable_from_the_cli():
    assert set(worker.JOBS) == {"ted", "ezamowienia", "placsp", "seed-buyers",
                                "health", "backup", "backup-verify", "catch-up"}
