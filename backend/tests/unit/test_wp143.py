"""WP-143: verification round 9 (system, site, data), the parts without a database."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from dgate import config, tenders, worker
from dgate.normalise import VALUE_UNIT_PRICE

# ------------------------------------------------------------------ 10. a unit price in the version history


def _version(n: int, amount, *, kind=None, changed=("value_amount",)):
    return {"opportunity_id": 1, "version": n, "observed_at": datetime(2026, 10, n, tzinfo=timezone.utc),
            "changed_fields": list(changed), "payload": {"value_amount": amount, "value_currency": "EUR", "status": "open"},
            "kinds": [], "remapped_fields": None, "row_value_kind": kind}


def test_a_unit_price_is_not_called_the_estimated_value_in_the_history():
    rows = [_version(1, None, kind=VALUE_UNIT_PRICE, changed=()), _version(13, 94.27, kind=VALUE_UNIT_PRICE)]
    lines = [c for e in tenders.timeline(rows, corrections=True) for c in e["changes"]]
    assert lines == [{"field": "value_amount", "label": tenders.UNIT_PRICE_LABEL, "before": None, "after": "EUR 94.27"}]
    assert "Estimated value" not in tenders.UNIT_PRICE_LABEL
    # a notice whose value is a value keeps the label it had
    rows = [_version(1, None, changed=()), _version(13, 94000.0)]
    assert [c["label"] for e in tenders.timeline(rows) for c in e["changes"]] == ["Estimated value"]


# ------------------------------------------------------------------ 12. a twin gmina name

def test_stezyca_is_a_twin_gmina_name_and_its_rows_join_only_by_a_number():
    from dgate.ops import accept_merge_candidates as amc
    from dgate.ops.org_repair import ambiguous_name, twin_name

    assert twin_name("PL", "gmina stezyca") and ambiguous_name("PL", "gmina stezyca")
    assert not twin_name("PL", "gmina iwaniska")
    org = lambda i, **kw: {"id": i, "country": "PL", "name": "gmina stezyca", "display_name": None, "suppressed": False,  # noqa: E731
                           "person": False, "reg": None, "vat": None, "pic": None, "notices": 0, "raw_names": [],
                           "legal_form": None, "org_role": "buyer", "is_defence_buyer": False, "buys": True, **kw}
    # merge review 2: 7240 (NIP 589..., kartuski) and 294460 (rycki), candidate 437768: by the name alone, refused
    orgs = {7240: org(7240, reg="5891595806"), 294460: org(294460)}
    pairs = [{"id": 437768, "a": 7240, "b": 294460, "confidence": 0.9, "match_method": "same_name_different_identifier",
              "evidence": "", "status": "pending"}]
    groups, refused, _ = amc.plan_reviewed(pairs, orgs, {437768: {"decision": "ACCEPT", "head": None, "confidence": None,
                                                                  "reason": "r"}})
    assert groups == [] and refused == {"twin_name": 1}


# ------------------------------------------------------------------ 2. the catch-up waits after a start

def _due_sched(ran: list[str]):
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(lambda: ran.append("requalify_weekly"), CronTrigger(day_of_week="sun", hour=12, minute=0), id="requalify_weekly")
    return sched


def test_a_missed_job_waits_a_few_minutes_after_the_worker_started(monkeypatch):
    monkeypatch.setenv("DGATE_JOB_RUNS", "1")
    config.reset_cache()
    slept: list[float] = []
    monkeypatch.setattr(worker.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(worker, "last_job_start", lambda names: (None, datetime(2026, 10, 25, 12, tzinfo=timezone.utc)))
    monkeypatch.setattr(worker, "STARTED_AT", time.monotonic())
    ran: list[str] = []
    try:
        worker.catch_up_jobs(_due_sched(ran), datetime(2026, 10, 26, 12, 32, tzinfo=timezone.utc))
        assert ran == ["requalify_weekly"] and len(slept) == 1 and 290 < slept[0] <= 300
        # long after the start: no wait
        slept.clear()
        ran.clear()
        monkeypatch.setattr(worker, "STARTED_AT", time.monotonic() - 3600)
        worker.catch_up_jobs(_due_sched(ran), datetime(2026, 10, 26, 12, 32, tzinfo=timezone.utc))
        assert ran == ["requalify_weekly"] and slept == []
    finally:
        config.reset_cache()


def test_a_slot_that_ran_the_job_during_the_wait_is_not_run_again(monkeypatch):
    monkeypatch.setenv("DGATE_JOB_RUNS", "1")
    config.reset_cache()
    calls: list[int] = []

    def started(names):
        calls.append(1)        # first read: not run since its slot; after the wait: the slot ran it
        return (None, None) if len(calls) == 1 else (datetime(2026, 11, 1, 12, tzinfo=timezone.utc), None)

    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    monkeypatch.setattr(worker, "last_job_start", started)
    monkeypatch.setattr(worker, "STARTED_AT", time.monotonic())
    monkeypatch.setattr(worker, "UNRECORDED_MAX_PERIOD", worker.timedelta(days=8))
    ran: list[str] = []
    try:
        worker.catch_up_jobs(_due_sched(ran), datetime(2026, 11, 1, 12, 1, tzinfo=timezone.utc))
        assert ran == [] and len(calls) == 2
    finally:
        config.reset_cache()


def test_an_api_connection_is_named_by_its_route_family(monkeypatch):
    import asyncio

    from dgate import api, db

    assert db.route_family("/v1/tenders/123-notice/versions") == "dgate-api /v1/tenders/{id}/versions"
    assert db.route_family("/v1/digest") == "dgate-api /v1/digest"
    assert len(db.route_family("/v1/" + "x" * 200)) == 63
    seen: list[dict] = []

    class _Conn:
        def commit(self): ...
        def rollback(self): ...
        def close(self): ...

    monkeypatch.setattr(db.psycopg, "connect", lambda dsn, **kw: seen.append(kw) or _Conn())

    async def route(scope, receive, send):
        with db.connect("postgresql://x"):
            pass

    asyncio.run(api._NameConnections(route)({"type": "http", "path": "/v1/suppliers/7-x"}, None, None))
    assert seen[-1]["application_name"] == "dgate-api /v1/suppliers/{id}"
    with db.connect("postgresql://x"):            # outside a request (the worker): no name of ours
        pass
    assert "application_name" not in seen[-1]


def test_the_digest_gaps_are_scheduled_hourly():
    jobs = {j.id: j for j in worker.build_scheduler().get_jobs()}
    fields = {f.name: str(f) for f in jobs["digest_gaps"].trigger.fields}
    assert (fields["minute"], fields["hour"]) == ("5", "*")
    assert any(line.startswith("digest_gaps") for line in worker.describe_schedule())
