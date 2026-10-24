"""WP-114 (coverage audit of 24 October 2026), the parts that need no database: the site's forwarded visitors have a
larger budget than a direct API client; the JSON API answers a conditional request with 304; a refused or interrupted run
is said in its own words; the catch-up's slot arithmetic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from starlette.testclient import TestClient

from dgate import config, db
from dgate.funding import run_reason
from dgate.hardening import CAPACITY, ETAG_SKIPPED, FORWARDED_FACTOR, ETag, RateLimit


def _app(monkeypatch) -> FastAPI:
    monkeypatch.setenv("DGATE_RATE_LIMIT", "1")
    monkeypatch.delenv("DGATE_INTERNAL_SECRET", raising=False)
    config.reset_cache()
    app = FastAPI()
    app.add_middleware(ETag)
    app.add_middleware(RateLimit)
    state = {"n": 0}

    @app.get("/v1/tenders")
    def tenders():
        return {"ok": True, "n": state["n"]}

    @app.get("/v1/account/me")
    def me():
        return {"me": 1}

    @app.post("/v1/tenders")
    def post():
        return {"posted": True}

    app.state.counter = state
    return app


def test_a_visitor_the_site_forwards_has_a_larger_budget_than_a_direct_client(monkeypatch):
    """27 refusals in 3 h of the site's own renders (24 Oct): a page view is several API requests, an office is one address."""
    from dgate.hardening import REFILL_PER_SECOND, TokenBuckets

    limiter = RateLimit(FastAPI())
    assert (limiter.forwarded.capacity, limiter.forwarded.refill) == (CAPACITY * FORWARDED_FACTOR,
                                                                      REFILL_PER_SECOND * FORWARDED_FACTOR)
    assert (limiter.buckets.capacity, limiter.buckets.refill) == (CAPACITY, REFILL_PER_SECOND)
    # and they are the ones charged: a direct client spends the small bucket, the forwarded visitor his own
    monkeypatch.setenv("DGATE_RATE_LIMIT", "1")
    monkeypatch.delenv("DGATE_INTERNAL_SECRET", raising=False)
    config.reset_cache()
    app = FastAPI()
    app.add_middleware(RateLimit, buckets=TokenBuckets(capacity=2, refill=0.0), forwarded=TokenBuckets(capacity=8, refill=0.0))
    app.get("/v1/tenders")(lambda: {"ok": True})
    with TestClient(app, client=("93.184.217.7", 5000)) as direct:
        assert [direct.get("/v1/tenders").status_code for _ in range(3)] == [200, 200, 429]
    with TestClient(app, client=("172.18.0.9", 5000)) as site:
        visitor = {"X-DG-Client-IP": "93.184.217.7"}            # the same address, through the site: its own bucket
        assert [site.get("/v1/tenders", headers=visitor).status_code for _ in range(9)] == [200] * 8 + [429]
    config.reset_cache()


def test_the_json_api_answers_a_conditional_request_with_304(monkeypatch):
    monkeypatch.setenv("DGATE_RATE_LIMIT", "0")
    config.reset_cache()
    app = _app(monkeypatch)
    monkeypatch.setenv("DGATE_RATE_LIMIT", "0")
    config.reset_cache()
    with TestClient(app) as c:
        first = c.get("/v1/tenders")
        tag = first.headers["etag"]
        assert first.status_code == 200 and tag.startswith('"')
        again = c.get("/v1/tenders", headers={"If-None-Match": f'W/{tag}, "other"'})
        assert again.status_code == 304 and again.content == b"" and again.headers["etag"] == tag
        app.state.counter["n"] = 1                                       # the body changed: a new tag, the new body
        changed = c.get("/v1/tenders", headers={"If-None-Match": tag})
        assert changed.status_code == 200 and changed.headers["etag"] != tag and changed.json()["n"] == 1
        # the account routes and the writes are not tagged
        assert "etag" not in c.get("/v1/account/me").headers and "/v1/account" in ETAG_SKIPPED
        assert "etag" not in c.post("/v1/tenders").headers
    config.reset_cache()


def test_a_refused_source_and_an_interrupted_run_are_said_in_their_own_words():
    refused = "re-read stopped after 3 failures in a row; " + db.refused_access(403)
    assert run_reason("partial", 0, 2000, refused)[0] == "refused"       # before "fewer than the minimum"
    assert "(HTTP 403)" in run_reason("partial", 0, 2000, refused)[1]
    assert run_reason("partial", 0, 2000, "publication days not read")[0] == "below_minimum"
    assert run_reason("failed", 0, None, db.INTERRUPTED_TEXT)[0] == "interrupted"
    assert run_reason("failed", 0, None, "boom")[0] == "failed"


def test_the_last_slot_of_a_daily_four_hourly_and_monthly_trigger():
    from apscheduler.triggers.cron import CronTrigger

    from dgate.worker import last_slot

    now = datetime(2026, 10, 24, 15, 53, tzinfo=timezone.utc)
    assert last_slot(CronTrigger(hour=14, minute=10, timezone="UTC"), now) == (
        datetime(2026, 10, 24, 14, 10, tzinfo=timezone.utc), timedelta(days=1))
    assert last_slot(CronTrigger(hour="1,5,9,13,17,21", minute=50, timezone="UTC"), now) == (
        datetime(2026, 10, 24, 13, 50, tzinfo=timezone.utc), timedelta(hours=4))
    slot, period = last_slot(CronTrigger(day=6, hour=2, minute=30, timezone="UTC"), now)
    assert slot == datetime(2026, 10, 6, 2, 30, tzinfo=timezone.utc) and period is None
