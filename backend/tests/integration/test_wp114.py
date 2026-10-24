"""WP-114 (coverage audit of 24 October 2026) against a real Postgres:

  - /changes reads the amendment candidates from the worker's snapshot and scans only what came after it; the answer is
    the live scan's, and an amendment observed after the snapshot is still listed
  - the tender page's "winner has a supplier page" query (award_set.OF_ORGS) answers as before, merged rows included
  - /v1/tenders refuses an unknown parameter, a country that is no code and a CPV that is no number
  - the sitemap pages of tenders (by id range) and the suppliers with a page, with the slugs their pages answer under
  - versionCount + correctionCount = the entries of /versions
  - a source that refuses access, and a check in alert, are said by /v1/sources and /v1/health; a run cut off by a restart
    is `interrupted`; a daily source whose runs of the day fetched nothing is stale at once
  - job_run: a job's run is recorded, a restart closes the running ones as interrupted, and the catch-up runs a job whose
    slot passed since it last started
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from psycopg.types.json import Jsonb

from dgate import award_set, changes, config, db, worker
from dgate.funding import make_slug
from tests.integration.test_changes import FUTURE, LATER, amend, client, feed, opp, store  # noqa: F401 - fixtures
from tests.integration.test_wp95 import award, env, notice, org  # noqa: F401 - fixtures

pytestmark = pytest.mark.integration


# ------------------------------------------------------------------ 1. the change candidates snapshot

def test_the_change_window_reads_the_snapshot_and_what_came_after_it(client, conn):  # noqa: F811
    first = opp("C-1")
    store(conn, first)
    amend(conn, first, "b", deadline_at=LATER)
    live = feed(client)
    assert live["counts"]["amended"] == 0          # first seen today: the same-day version is no amendment (rule)
    # an amendment read on another day than the first sighting is: move the first version back two days
    conn.execute("SET LOCAL session_replication_role = replica")
    conn.execute("UPDATE opportunity_version SET observed_at = observed_at - interval '2 days', "
                 "valid_from = valid_from - interval '2 days' WHERE version = 1")
    conn.execute("SET LOCAL session_replication_role = DEFAULT")
    conn.commit()
    live = feed(client)
    assert live["counts"]["amended"] == 1
    body = changes.compute_candidates(conn)
    assert [i for i, _ in body["ids"]] == [int(live["items"][0]["tender"]["id"])]
    conn.execute("INSERT INTO list_snapshot (key, body) VALUES (%s, %s)", (changes.CANDIDATES_KEY, Jsonb(body)))
    conn.commit()
    again = feed(client)                              # read through the snapshot: the same answer
    assert (again["items"], again["counts"], again["total"]) == (live["items"], live["counts"], live["total"])
    # a second notice amended after the snapshot (the snapshot made an hour and a half ago): the scan after it finds it
    conn.execute("UPDATE list_snapshot SET body = jsonb_set(body, '{upto}', to_jsonb((now() - interval '90 minutes')::text))")
    second = opp("C-2", title="Ammunition")
    oid = store(conn, second)
    conn.execute("SET LOCAL session_replication_role = replica")
    conn.execute("UPDATE opportunity_version SET observed_at = observed_at - interval '3 days' WHERE opportunity_id = %s", (oid,))
    conn.execute("SET LOCAL session_replication_role = DEFAULT")
    conn.commit()
    amend(conn, second, "b", value_amount=5e6, value_currency="EUR")
    got = changes._snapshot_candidates(conn, datetime.now(timezone.utc) - timedelta(days=14))
    assert got == set(changes.amended_candidates(conn, datetime.now(timezone.utc) - timedelta(days=14)))
    assert oid in got and len(got) == 2
    # a snapshot that does not reach back to the window's start is not used
    conn.execute("UPDATE list_snapshot SET body = jsonb_set(body, '{from}', to_jsonb(now()::text))")
    conn.commit()
    assert changes._snapshot_candidates(conn, datetime.now(timezone.utc) - timedelta(days=14)) is None


def test_the_worker_writes_the_candidates_first(conn):
    from dgate.ops import warm_lists

    todo = warm_lists.views([])
    assert todo[0][1] == changes.CANDIDATES_KEY
    assert "changes-candidates" in warm_lists.FIRST_VIEWS
    assert warm_lists.run_first(conn)["failed"] == 0
    assert conn.execute("SELECT 1 FROM list_snapshot WHERE key = %s", (changes.CANDIDATES_KEY,)).fetchone()


# ------------------------------------------------------------------ 3. winners with a supplier page

def test_the_winners_query_starts_from_the_organisations_and_answers_as_before(conn, env):  # noqa: F811
    jae = org(conn, "jae", "ES", is_defence_buyer=True)
    live = org(conn, "indra sistemas", "ES")
    merged = org(conn, "indra sistemas sa", "ES", merged_into=live)
    other = org(conn, "other", "ES")
    award(conn, notice(conn, "ted", "1-2026", buyer=jae), merged, "INDRA SISTEMAS SA")
    award(conn, notice(conn, "ted", "2-2026", buyer=jae), other, "Other SL")
    conn.commit()
    args = {"since": award_set.since(), "orgs": [live, other, 999999]}
    old = {r["id"] for r in conn.execute(
        f"SELECT DISTINCT org.id {award_set.FROM} WHERE {award_set.scope()} AND org.id = ANY(%(orgs)s)", args).fetchall()}
    new = {r["id"] for r in conn.execute(
        f"SELECT DISTINCT org.id {award_set.FROM} WHERE {award_set.scope()} AND {award_set.OF_ORGS}", args).fetchall()}
    assert old == new == {live, other}


# ------------------------------------------------------------------ 8. validation, sitemap, version counts

def test_the_tender_list_refuses_what_it_cannot_read(client):  # noqa: F811
    assert client.get("/v1/tenders", params={"foo": "bar"}).status_code == 422
    assert client.get("/v1/tenders", params={"country": "1!"}).status_code == 422
    assert client.get("/v1/tenders", params={"cpv": "abc"}).status_code == 422
    assert client.get("/v1/tenders/scope-counts", params={"foo": "bar"}).status_code == 422
    assert client.get("/v1/tenders/export", params={"foo": "bar"}).status_code == 422
    assert client.get("/v1/tenders", params={"country": "fr,de", "cpv": "35120000-1"}).status_code == 200


def test_the_sitemap_pages_hold_every_core_tender_by_id_range(client, conn):  # noqa: F811
    core = store(conn, opp("S-1", title="Night vision goggles"))
    supply = store(conn, opp("S-2", kind="supply"))
    first = client.get("/v1/tenders/sitemap", params={"page": 0}).json()
    assert first["pages"] == max(core, supply) // 50_000 + 1
    slugs = [i["slug"] for i in first["items"]]
    assert slugs == [make_slug(core, "Night vision goggles")]              # the supply notice's page is noindex
    assert client.get(f"/v1/tenders/{slugs[0]}").json()["slug"] == slugs[0]
    assert client.get("/v1/tenders/sitemap", params={"page": first["pages"]}).json()["items"] == []


def test_the_supplier_slugs_are_the_ones_their_pages_answer_under(client, conn, env):  # noqa: F811
    jae = org(conn, "jae", "ES", is_defence_buyer=True)
    w = org(conn, "leonardo spa", "IT")
    for i, name in enumerate(("LEONARDO - SOCIETA PER AZIONI", "Leonardo S.p.A.", "Leonardo S.p.A.")):
        award(conn, notice(conn, "ted", f"5{i}-2026", buyer=jae), w, name)
    person = org(conn, "juan perez", "ES", individual_reason="name")
    award(conn, notice(conn, "ted", "60-2026", buyer=jae), person, "Juan Perez")
    conn.commit()
    got = client.get("/v1/suppliers/slugs").json()
    assert [g["slug"] for g in got] == [make_slug(w, "Leonardo S.p.A.")]   # a natural person has no page
    assert client.get(f"/v1/suppliers/{got[0]['slug']}").json()["slug"] == got[0]["slug"]


def test_the_version_count_and_the_corrections_add_up_to_the_history(client, conn):  # noqa: F811
    o = opp("V-1")
    oid = store(conn, o)
    amend(conn, o, "b", deadline_at=LATER)
    conn.execute("INSERT INTO opportunity_version_note (opportunity_version_id, kind, note) "
                 "SELECT id, 'correction', 'test' FROM opportunity_version WHERE opportunity_id = %s AND version = 2", (oid,))
    conn.commit()
    slug = client.get("/v1/tenders/sitemap").json()["items"][0]["slug"]
    t = client.get(f"/v1/tenders/{slug}").json()
    history = client.get(f"/v1/tenders/{slug}/versions").json()
    assert t["versionCount"] + t["correctionCount"] == len(history)


# ------------------------------------------------------------------ 6. health says what is wrong

def _run(conn, code: str, *, status: str, fetched: int, error: str | None = None, hours_ago: float = 0,
         floor: int | None = 10) -> None:
    run_id = db.start_run(conn, code, expected_min=floor)
    db.finish_run(conn, run_id, fetched=fetched, new=0, changed=0, status=status, error=error)
    conn.execute("UPDATE ingest_run SET started_at = now() - make_interval(secs => %s), "
                 "finished_at = now() - make_interval(secs => %s) WHERE id = %s",
                 (hours_ago * 3600 + 60, hours_ago * 3600, run_id))
    conn.commit()


def test_a_source_that_refuses_access_is_said_so_with_since_when(client, conn):  # noqa: F811
    conn.execute("UPDATE source SET update_freq = 'daily' WHERE code = 'pl_ezam'")
    _run(conn, "pl_ezam", status="success", fetched=500, hours_ago=30)
    refused = "re-read stopped after 3 failures in a row; " + db.refused_access(403)
    _run(conn, "pl_ezam", status="partial", fetched=0, error=refused, hours_ago=10)
    _run(conn, "pl_ezam", status="partial", fetched=0, error=refused, hours_ago=2)
    src = next(s for s in client.get("/v1/sources").json()["sources"] if s["id"] == "pl_ezam")
    assert src["statusReasonKind"] == "refused"
    assert "refuses access (HTTP 403)" in src["statusReason"] and "Refused since" in src["statusReason"]
    assert src["statusReasonSince"] is not None
    assert src["stale"] is True                       # every run of the last day fetched nothing: stale now, not in 72 h
    health = client.get("/v1/health").json()
    item = next(s for s in health["sources"] if s["code"] == "pl_ezam")
    assert item["health"] == "unhealthy" and "refused_since" in item
    assert "pl_ezam" in health["unhealthy_sources"] and health["status"] == "degraded"


def test_a_check_in_alert_degrades_health_and_is_on_the_sources_list(client, conn):  # noqa: F811
    from dgate.ops import controls

    now = datetime.now(timezone.utc)
    controls._save(conn, "placsp_links", "alert", {}, {"placsp_null_date_rate": 0.39}, now - timedelta(days=1))
    controls._save(conn, "placsp_links", "alert", {}, {"placsp_null_date_rate": 0.39}, now)
    alerts = client.get("/v1/sources").json()["alerts"]
    assert [a["control"] for a in alerts] == ["placsp_links"]
    assert datetime.fromisoformat(alerts[0]["since"]) == now - timedelta(days=1)   # the first check of the alert
    health = client.get("/v1/health").json()
    assert health["alerting_controls"] == ["placsp_links"] and health["status"] == "degraded"
    controls._save(conn, "placsp_links", "ok", {}, {"placsp_null_date_rate": 0.1}, now)
    assert client.get("/v1/sources").json()["alerts"] == []


def test_a_run_cut_off_by_a_restart_is_interrupted(client, conn):  # noqa: F811
    run_id = db.start_run(conn, "fr_aid")
    conn.execute("UPDATE ingest_run SET owner = 'worker:old' WHERE id = %s", (run_id,))
    conn.commit()
    kind = db.RUN_KIND
    db.RUN_KIND = "worker"
    try:
        assert db.close_interrupted_runs(conn) == [run_id]
    finally:
        db.RUN_KIND = kind
    src = next(s for s in client.get("/v1/sources").json()["sources"] if s["id"] == "fr_aid")
    assert src["statusReasonKind"] == "interrupted"


# ------------------------------------------------------------------ 5. job runs and the catch-up

@pytest.fixture
def job_runs(conn, monkeypatch):
    monkeypatch.setenv("DGATE_JOB_RUNS", "1")        # the `conn` fixture has pointed DGATE_DSN at the test database
    config.reset_cache()
    monkeypatch.setattr(worker, "notify", lambda *a, **k: True)
    monkeypatch.setattr(worker, "ping", lambda *a, **k: None)
    yield
    config.reset_cache()


def test_a_job_run_is_recorded_and_a_restart_closes_it_as_interrupted(conn, job_runs, client):  # noqa: F811
    assert worker.run_job("digest", lambda: None).ok

    def boom():
        raise RuntimeError("no")
    assert worker.run_job("warm_lists", boom).status == "failed"
    rows = {r["job"]: r for r in conn.execute("SELECT job, status, finished_at, owner FROM job_run").fetchall()}
    assert rows["digest"]["status"] == "success" and rows["digest"]["finished_at"] is not None
    assert rows["warm_lists"]["status"] == "failed"
    conn.execute("INSERT INTO job_run (job, owner) VALUES ('ted_awards_daily', %s)", (db.RUN_KIND,))
    conn.commit()
    worker.close_interrupted_runs()
    assert conn.execute("SELECT status FROM job_run WHERE job = 'ted_awards_daily'").fetchone()["status"] == "interrupted"
    jobs = client.get("/v1/health").json()["jobs"]
    assert jobs["digest"]["status"] == "success" and jobs["ted_awards_daily"]["status"] == "interrupted"
    assert "detail" not in jobs["warm_lists"]            # an exception text is not served


def test_the_catch_up_runs_every_job_whose_slot_passed_since_it_last_started(conn, job_runs):
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    ran: list[str] = []

    def job(name):
        return lambda: ran.append(name) or worker.JobResult(name, "success", 0.0)

    sched = BlockingScheduler(timezone="UTC")
    now = datetime(2026, 10, 24, 15, 53, tzinfo=timezone.utc)          # the worker recreated after the 14:10 slot
    sched.add_job(job("ted_awards_daily"), CronTrigger(hour=14, minute=10), id="ted_awards_daily")
    sched.add_job(job("digest"), CronTrigger(hour=11, minute=0), id="digest_daily")
    sched.add_job(job("link_twins"), CronTrigger(hour=9, minute=15), id="link_twins_daily")
    sched.add_job(job("cordis_monthly"), CronTrigger(day=5, hour=2, minute=30), id="cordis_monthly")
    sched.add_job(job("ted_daily"), CronTrigger(hour=7, minute=0), id="ted_daily")      # the ingest catch-up's
    for name, at in (("ted_awards_daily", "2026-10-23 14:10"), ("digest", "2026-10-24 11:00"),
                     ("link_twins", "2026-10-23 09:15")):
        conn.execute("INSERT INTO job_run (job, started_at, status) VALUES (%s, %s, 'success')", (name, f"{at}+00"))
    conn.commit()
    worker.catch_up_jobs(sched, now)
    # missed today: the twins (09:15) before ted_awards (14:10); the digest ran; cordis was never recorded (monthly: kept
    # for its slot); the ingest job is the ingest catch-up's
    assert ran == ["link_twins", "ted_awards_daily"]
