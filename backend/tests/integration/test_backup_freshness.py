"""A backup that is old is a finding, not only a backup job that failed (internal audit H1).

On 14 October 2026 the newest recoverable dump was 47 hours old and nothing had said so:
the alerts were per failed job, and a job that never ran, or ran into the wrong place,
sends none.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, worker

pytestmark = pytest.mark.integration


def _ago(hours: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


@pytest.fixture()
def alerts(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(worker, "notify", lambda text, **kw: sent.append(text) or True)
    return sent


def _probes(monkeypatch, local, offsite):
    def _offsite():
        if isinstance(offsite, Exception):
            raise offsite
        return offsite

    monkeypatch.setattr(worker, "last_backup_taken", lambda: local)
    monkeypatch.setattr(worker, "last_offsite_backup", _offsite)


def test_fresh_dumps_are_ok_and_silent(conn, client, alerts, monkeypatch):
    _probes(monkeypatch, _ago(5), _ago(5))
    assert worker.job_backup_freshness().ok
    assert alerts == []
    backup = client.get("/v1/health").json()["backup"]
    assert backup["status"] == "ok"
    assert 4.9 <= backup["local_age_hours"] <= 5.2


def test_a_stale_local_dump_alerts_once_and_degrades_health(conn, client, alerts, monkeypatch):
    _probes(monkeypatch, _ago(47), _ago(5))
    result = worker.job_backup_freshness()
    assert result.status == "failed"
    assert len(alerts) == 1 and "BACKUP STALE" in alerts[0] and "47h" in alerts[0]
    worker.job_backup_freshness()           # the next hour: still stale, not a second message
    assert len(alerts) == 1
    body = client.get("/v1/health").json()
    assert body["backup"]["status"] == "stale"
    assert body["status"] == "degraded"


def test_a_stale_offsite_copy_alerts_even_when_the_local_one_is_fresh(
        conn, client, alerts, monkeypatch):
    _probes(monkeypatch, _ago(3), _ago(60))
    worker.job_backup_freshness()
    assert len(alerts) == 1 and "offsite 60h" in alerts[0]


def test_an_unreadable_store_is_stale_not_silent(conn, client, alerts, monkeypatch):
    _probes(monkeypatch, _ago(3), RuntimeError("503 from the store"))
    worker.job_backup_freshness()
    assert len(alerts) == 1 and "offsite none found" in alerts[0]
    assert "503" not in alerts[0], "no error text in the message"
    assert client.get("/v1/health").json()["backup"]["status"] == "stale"


def test_the_alert_repeats_after_six_hours(conn, alerts, monkeypatch):
    _probes(monkeypatch, _ago(47), _ago(47))
    worker.job_backup_freshness()
    conn.execute("UPDATE backup_status SET alerted_at = now() - interval '7 hours'")
    conn.commit()
    worker.job_backup_freshness()
    assert len(alerts) == 2


def test_health_reports_ages_and_nothing_else_about_the_backups(conn, client, alerts, monkeypatch):
    _probes(monkeypatch, _ago(2), _ago(2))
    worker.job_backup_freshness()
    backup = client.get("/v1/health").json()["backup"]
    assert set(backup) == {"status", "stale_after_hours", "local_age_hours", "offsite_age_hours"}


def test_nothing_recorded_yet_is_unknown_and_not_degraded(conn, client):
    body = client.get("/v1/health").json()
    assert body["backup"]["status"] == "unknown"
    assert body["backup"]["local_age_hours"] is None
