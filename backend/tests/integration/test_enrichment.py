"""The enrichment framework against a real Postgres, with a fake Anthropic client.

The plan's done-when for M1-04: a re-run over an unchanged notice performs zero
API calls, asserted by a mocked client. The other tests pin what that rests on:
a changed notice does cost a call, an identical text on another notice does not,
a batch is matched by custom_id in any order, and an unusable answer is never
stored.
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from dgate import db
from dgate.enrichment import base, queue, runner
from dgate.normalise import Opportunity
from dgate.sources.ted import content_hash

pytestmark = pytest.mark.integration


class EchoOut(BaseModel):
    title_upper: str


def _input(payload: dict) -> dict | None:
    if not payload.get("title_original"):
        return None
    return {"title": payload["title_original"], "description": payload.get("description") or ""}


TASK = base.register(base.Task(
    name="test_echo", model="claude-sonnet-5", output=EchoOut,
    system_prompt="Upper-case the title.",
    build_input=_input,
    build_user_message=lambda task_input: json.dumps(task_input, sort_keys=True),
))


def _answer(params: dict, stop: str = "end_turn"):
    title = json.loads(params["messages"][0]["content"])["title"]
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(
        type="text", text=json.dumps({"title_upper": title.upper()}))])


class FakeMessages:
    def __init__(self, stop: str = "end_turn"):
        self.calls: list[dict] = []
        self.stop = stop
        self.batches = FakeBatches()

    def create(self, **params):
        self.calls.append(params)
        return _answer(params, self.stop)


class FakeBatches:
    def __init__(self):
        self.created: list[list[dict]] = []
        self.errored: set[str] = set()

    def create(self, requests):
        self.created.append(requests)
        return SimpleNamespace(id=f"batch-{len(self.created)}", processing_status="in_progress")

    def retrieve(self, batch_id):
        return SimpleNamespace(id=batch_id, processing_status="ended")

    def results(self, batch_id):
        requests = self.created[int(batch_id.split("-")[1]) - 1]
        out = []
        for req in reversed(requests):  # any order, never by position
            if req["custom_id"] in self.errored:
                out.append(SimpleNamespace(custom_id=req["custom_id"], result=SimpleNamespace(
                    type="errored", error=SimpleNamespace(type="api_error"))))
            else:
                out.append(SimpleNamespace(custom_id=req["custom_id"], result=SimpleNamespace(
                    type="succeeded", message=_answer(req["params"]))))
        return out


class FakeClient:
    def __init__(self, stop: str = "end_turn"):
        self.messages = FakeMessages(stop)


def _notice(conn, native_id: str, *, title: str, description: str = "",
            is_defence: bool = True, status: str = "open", published: str = "2026-09-01") -> int:
    opp = Opportunity(source_code="ted", native_id=native_id, buyer_name_raw="MoD",
                      title_original=title, country="PL", description=description,
                      published_at=date.fromisoformat(published), status=status,
                      is_defence=is_defence, sig_cpv=is_defence)
    oid, _ = db.upsert_opportunity(conn, opp, content_hash(db.opportunity_payload(opp)),
                                   db.source_id(conn, "ted"))
    conn.commit()
    return oid


def _run(conn, client):
    queue.enqueue(conn, TASK)
    return runner.run_sync(conn, TASK, client=client)


# --------------------------------------------------------------- done-when

def test_a_rerun_over_an_unchanged_notice_makes_zero_api_calls(conn):
    """Plan M1-04, done-when."""
    _notice(conn, "N-1", title="rations")
    first = FakeClient()
    assert _run(conn, first).stored == 1
    assert len(first.messages.calls) == 1

    second = FakeClient()
    result = _run(conn, second)
    assert second.messages.calls == []
    assert result.calls == 0 and result.stored == 0


def test_seeing_the_same_notice_again_queues_nothing(conn):
    oid = _notice(conn, "N-1", title="rations")
    _run(conn, FakeClient())
    _notice(conn, "N-1", title="rations")          # re-ingested, unchanged
    assert queue.enqueue(conn, TASK).queued == 0
    stored = conn.execute("SELECT count(*) n FROM enrichment WHERE entity_id = %s",
                          (oid,)).fetchone()["n"]
    assert stored == 1


# -------------------------------------------------------- what costs a call

def test_an_amended_notice_whose_input_changed_costs_one_call(conn):
    _notice(conn, "N-1", title="rations", description="1000 packs")
    _run(conn, FakeClient())
    _notice(conn, "N-1", title="rations", description="2000 packs", published="2026-09-02")
    client = FakeClient()
    assert _run(conn, client).stored == 1
    assert len(client.messages.calls) == 1


def test_an_amendment_the_task_does_not_read_costs_nothing(conn):
    """The hash covers only what is sent. A status change is not."""
    _notice(conn, "N-1", title="rations")
    _run(conn, FakeClient())
    _notice(conn, "N-1", title="rations", status="awarded", published="2026-09-02")
    client = FakeClient()
    _run(conn, client)
    assert client.messages.calls == []


def test_identical_input_on_two_notices_is_paid_for_once(conn):
    _notice(conn, "N-1", title="rations")
    _notice(conn, "N-2", title="rations")
    client = FakeClient()
    result = _run(conn, client)
    assert len(client.messages.calls) == 1
    assert (result.stored, result.reused) == (1, 1)
    assert conn.execute("SELECT count(*) n FROM enrichment").fetchone()["n"] == 2


def test_non_defence_notices_are_never_queued(conn):
    _notice(conn, "N-1", title="office chairs", is_defence=False)
    assert queue.enqueue(conn, TASK).queued == 0


def test_a_job_whose_notice_changed_before_it_ran_is_not_paid_for(conn):
    _notice(conn, "N-1", title="rations", description="old")
    queue.enqueue(conn, TASK)
    _notice(conn, "N-1", title="rations", description="new", published="2026-09-02")
    client = FakeClient()
    result = runner.run_sync(conn, TASK, client=client)
    assert client.messages.calls == [] and result.superseded == 1


# ------------------------------------------------------------ bad answers

def test_a_refusal_is_retried_then_failed_and_never_stored(conn):
    _notice(conn, "N-1", title="rations")
    queue.enqueue(conn, TASK)
    for _ in range(runner.MAX_ATTEMPTS):
        runner.run_sync(conn, TASK, client=FakeClient(stop="refusal"))
    job = conn.execute("SELECT status, attempts, last_error FROM enrichment_job").fetchone()
    assert job["status"] == "failed" and job["attempts"] == runner.MAX_ATTEMPTS
    assert "refusal" in job["last_error"]
    assert conn.execute("SELECT count(*) n FROM enrichment").fetchone()["n"] == 0


# ----------------------------------------------------------------- batches

def test_a_batch_is_matched_by_custom_id_and_errors_go_back_to_pending(conn):
    ids = [_notice(conn, f"N-{i}", title=f"item {i}") for i in range(3)]
    queue.enqueue(conn, TASK)
    client = FakeClient()
    batch_id, submitted = runner.submit_batch(conn, TASK, client=client)
    assert batch_id == "batch-1" and submitted.calls == 1
    requests = client.messages.batches.created[0]
    assert len(requests) == 3
    client.messages.batches.errored = {requests[1]["custom_id"]}

    collected = runner.collect_batches(conn, client=client)
    assert collected.stored == 2
    rows = conn.execute(
        """SELECT e.entity_id, e.output->>'title_upper' AS t FROM enrichment e
            ORDER BY e.entity_id""").fetchall()
    assert {r["entity_id"]: r["t"] for r in rows} == {ids[0]: "ITEM 0", ids[2]: "ITEM 2"}
    retry = conn.execute("SELECT status, attempts FROM enrichment_job WHERE entity_id = %s",
                         (ids[1],)).fetchone()
    assert (retry["status"], retry["attempts"]) == ("pending", 1)


def test_a_rerun_submits_no_batch_for_unchanged_notices(conn):
    _notice(conn, "N-1", title="rations")
    queue.enqueue(conn, TASK)
    client = FakeClient()
    runner.submit_batch(conn, TASK, client=client)
    runner.collect_batches(conn, client=client)

    again = FakeClient()
    queue.enqueue(conn, TASK)
    batch_id, _ = runner.submit_batch(conn, TASK, client=again)
    assert batch_id is None and again.messages.batches.created == []
