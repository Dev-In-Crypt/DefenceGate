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
    assert any("eu_portal" in line for line in lines)
    assert any("eu_topics" in line for line in lines)
    assert any("bdns_daily" in line for line in lines)
    assert any("ncbr_daily" in line for line in lines)
    assert any("health_report" in line for line in lines)
    assert any("backup_nightly" in line for line in lines)
    assert any("backup_verify" in line for line in lines)


def test_the_networks_jobs_are_monthly_and_in_order_cordis_edf_snapshot():
    jobs = {job.id: job for job in worker.build_scheduler().get_jobs()}
    days = {}
    for name in ("cordis_monthly", "edf_monthly", "consortium_snapshot"):
        trigger = jobs[name].trigger
        fields = {f.name: str(f) for f in trigger.fields}
        days[name] = int(fields["day"])
        assert fields["month"] == "*"           # every month
    assert days["cordis_monthly"] < days["edf_monthly"] < days["consortium_snapshot"]
    lines = worker.describe_schedule()
    for word in ("cordis_monthly", "edf_monthly", "consortium_snapshot"):
        assert any(line.startswith(word) for line in lines)


def test_every_job_is_reachable_from_the_cli():
    assert set(worker.JOBS) == {"ted", "ezamowienia", "placsp", "seed-buyers",
                                "health", "backup", "backup-verify", "catch-up",
                                "atlas-backfill", "ted-history", "boamp", "calls",
                                "topics", "bdns", "ncbr", "tenderned", "de-bkms", "vinnova", "aid", "matine",
                                "alerts", "backup-freshness", "link-twins", "requalify", "controls",
                                "buyer-families", "warm-lists", "cascade-flags", "digest",
                                "cordis", "edf", "consortium-snapshot", "placsp-awards-catchup",
                                "ted-awards",   # WP-103
                                "association-digest"}   # WP-158


def test_the_ted_award_load_is_daily_bounded_and_away_from_the_heavy_jobs(monkeypatch):
    """WP-103 (owner, 24 October 2026): the TED award load runs daily in the worker, at most a bounded batch, at an hour
    no ingest, twin, digest, backup or networks job holds, and records its run under `ted_awards`."""
    jobs = {job.id: job for job in worker.build_scheduler().get_jobs()}
    fields = {f.name: str(f) for f in jobs["ted_awards_daily"].trigger.fields}
    assert (fields["hour"], fields["minute"], fields["day_of_week"]) == ("14", "10", "*")
    taken = set()
    for jid, job in jobs.items():
        f = {x.name: str(x) for x in job.trigger.fields}
        if jid != "ted_awards_daily" and f["hour"] not in ("*",) and "," not in f["hour"]:
            taken.add(int(f["hour"]))
    assert 14 not in taken
    assert any(line.startswith("ted_awards") and "1500" in line for line in worker.describe_schedule())
    seen = {}
    monkeypatch.setattr(worker, "run_awards", lambda **kw: seen.update(kw))
    monkeypatch.setattr(worker, "source_run_status", lambda sources: [(s, "success", 1, None) for s in sources])
    assert worker.JOBS["ted-awards"]().status == "success"
    assert seen == {"limit": 1500}


# ------------------------------------------------- PLACSP award catch-up (WP-61)

def test_the_placsp_award_catchup_is_off_unless_switched_on(monkeypatch):
    from dgate import config

    monkeypatch.delenv("DGATE_PLACSP_AWARDS_CATCHUP", raising=False)
    config.reset_cache()
    try:
        assert "placsp_awards_monthly" not in {j.id for j in worker.build_scheduler().get_jobs()}
        assert any(line.startswith("placsp_awards_monthly off") for line in worker.describe_schedule())
        monkeypatch.setenv("DGATE_PLACSP_AWARDS_CATCHUP", "true")
        config.reset_cache()
        job = {j.id: j for j in worker.build_scheduler().get_jobs()}["placsp_awards_monthly"]
        fields = {f.name: str(f) for f in job.trigger.fields}
        assert (fields["day"], fields["hour"], fields["month"]) == ("3", "12", "*")
    finally:
        config.reset_cache()


def test_the_catchup_reads_last_months_archive_and_is_not_green_when_stopped(monkeypatch):
    from datetime import date

    from dgate.ops import placsp_archives

    asked = []

    def fake_run(todo, ds, **kw):
        asked.append([(u.name, u.url.rsplit("_", 1)[-1], u.day, u.since.date()) for u in todo])
        return {"done": [u.name for u in todo], "skipped": [], "failed": [], "stopped": []}

    monkeypatch.setattr(placsp_archives, "run", fake_run)
    worker.placsp_awards_catchup(today=date(2026, 11, 3))
    assert asked[-1] == [("es_placsp-202610", "202610.zip", date(2026, 10, 1), date(2026, 10, 1))]
    # December of the year before: the annual archive, walked from 1 December and marked as December
    worker.placsp_awards_catchup(today=date(2026, 1, 3))
    assert asked[-1] == [("es_placsp-202512", "2025.zip", date(2025, 12, 1), date(2025, 12, 1))]
    monkeypatch.setattr(placsp_archives, "run", lambda todo, ds, **kw: {
        "done": [], "skipped": [], "failed": [], "stopped": ["es_placsp-202610"]})
    with pytest.raises(RuntimeError, match="did not finish"):
        worker.placsp_awards_catchup(today=date(2026, 11, 3))
