"""Run queued enrichment jobs.

Two ways, same results:

    run_sync         one Messages API call per job; for development and small
                     volumes, where waiting for a batch is the bigger cost
    submit_batch     all pending jobs of a task as one Message Batch, at half
    collect_batches  the price; results are matched back by custom_id, never
                     by position, because a batch returns them in any order

Before anything is sent, a job's input is rebuilt from the current archived
version and hashed again. If a result for that exact hash already exists -- for
this notice or any other -- it is copied and no call is made. That check is the
reason a re-run over unchanged notices costs nothing, and it is what the M1-04
done-when asserts.

The client is created only when a call is actually needed, and can be passed in:
tests hand in a fake that counts calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from .base import Task, canonical_json, get_task
from .queue import ENTITY

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
CUSTOM_ID_PREFIX = "job-"


@dataclass
class RunResult:
    calls: int = 0
    reused: int = 0
    stored: int = 0
    failed: int = 0
    superseded: int = 0


def make_client() -> Any:
    """The real client, from the environment's credentials."""
    import anthropic

    return anthropic.Anthropic()


# ----------------------------------------------------------------- helpers

def _pending(conn, task: Task, limit: int | None):
    sql = """SELECT id, entity_id, input_hash, attempts FROM enrichment_job
              WHERE task = %s AND status = 'pending' ORDER BY id"""
    params: list[Any] = [task.name]
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def _current_input(conn, task: Task, entity_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT v.payload FROM opportunity o
             JOIN opportunity_version v
               ON v.opportunity_id = o.id AND v.version = o.current_version
            WHERE o.id = %s""",
        (entity_id,),
    ).fetchone()
    return task.build_input(row["payload"]) if row else None


def _cached(conn, task: Task, digest: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT output FROM enrichment WHERE task = %s AND input_hash = %s LIMIT 1",
        (task.name, digest),
    ).fetchone()
    return row["output"] if row else None


def _store(conn, task: Task, job: dict, output: BaseModel | dict[str, Any]) -> None:
    validated = (output if isinstance(output, BaseModel)
                 else task.output.model_validate(output))
    conn.execute(
        """INSERT INTO enrichment (entity_type, entity_id, task, input_hash, model, output)
           VALUES (%s, %s, %s, %s, %s, %s::jsonb)
           ON CONFLICT (entity_type, entity_id, task, input_hash) DO NOTHING""",
        (ENTITY, job["entity_id"], task.name, job["input_hash"], task.model,
         canonical_json(validated.model_dump(mode="json"))),
    )
    if task.apply is not None:
        task.apply(conn, job["entity_id"], validated)
    conn.execute(
        """UPDATE enrichment_job SET status = 'done', finished_at = clock_timestamp(),
                  last_error = NULL WHERE id = %s""",
        (job["id"],),
    )


def _fail(conn, job: dict, error: str, max_attempts: int, *, final: bool = False) -> bool:
    """Record a failure. Returns True if the job is now permanently failed."""
    attempts = job["attempts"] + 1
    permanent = final or attempts >= max_attempts
    conn.execute(
        """UPDATE enrichment_job
              SET attempts = %s, last_error = %s, batch_id = NULL,
                  status = %s, finished_at = CASE WHEN %s THEN clock_timestamp() END
            WHERE id = %s""",
        (attempts, error[:2000], "failed" if permanent else "pending", permanent, job["id"]),
    )
    log.warning("enrichment job %s %s: %s", job["id"],
                "failed" if permanent else "will retry", error)
    return permanent


def _resolve_without_call(conn, task: Task, job: dict,
                          result: RunResult) -> dict[str, Any] | None:
    """Handle what needs no API call. Returns the input if a call is still needed."""
    task_input = _current_input(conn, task, job["entity_id"])
    if task_input is None or task.input_hash(task_input) != job["input_hash"]:
        # The notice changed after this job was queued. Its new input has its
        # own hash and is queued on its own; paying for the old one is waste.
        _fail(conn, job, "superseded: the notice changed after this job was queued",
              MAX_ATTEMPTS, final=True)
        result.superseded += 1
        return None
    cached = _cached(conn, task, job["input_hash"])
    if cached is not None:
        _store(conn, task, job, cached)
        result.reused += 1
        return None
    return task_input


def _api_errors() -> tuple[type[BaseException], ...]:
    try:
        import anthropic
    except ImportError:
        return (ValueError,)
    return (anthropic.APIStatusError, anthropic.APIConnectionError, ValueError)


# ------------------------------------------------------------ synchronous

def run_sync(conn, task: Task, *, client: Any = None, limit: int | None = None,
             max_attempts: int = MAX_ATTEMPTS) -> RunResult:
    result = RunResult()
    errors = _api_errors()
    for job in _pending(conn, task, limit):
        task_input = _resolve_without_call(conn, task, job, result)
        if task_input is None:
            conn.commit()
            continue
        client = client or make_client()
        try:
            message = client.messages.create(**task.request_params(task_input))
            output = task.parse(message)
        except errors as exc:
            result.calls += 1
            if _fail(conn, job, f"{type(exc).__name__}: {exc}", max_attempts):
                result.failed += 1
            conn.commit()
            continue
        result.calls += 1
        _store(conn, task, job, output)
        result.stored += 1
        conn.commit()
    log.info("enrichment %s sync: %s", task.name, result)
    return result


# ----------------------------------------------------------------- batches

def submit_batch(conn, task: Task, *, client: Any = None,
                 limit: int | None = None) -> tuple[str | None, RunResult]:
    """Send every pending job that still needs a call as one Message Batch."""
    result = RunResult()
    requests: list[dict[str, Any]] = []
    job_ids: list[int] = []
    for job in _pending(conn, task, limit):
        task_input = _resolve_without_call(conn, task, job, result)
        if task_input is None:
            continue
        requests.append({"custom_id": f"{CUSTOM_ID_PREFIX}{job['id']}",
                         "params": task.request_params(task_input)})
        job_ids.append(job["id"])
    conn.commit()
    if not requests:
        log.info("enrichment %s: nothing to batch (%s)", task.name, result)
        return None, result

    client = client or make_client()
    batch = client.messages.batches.create(requests=requests)
    conn.execute(
        "UPDATE enrichment_job SET status = 'batched', batch_id = %s WHERE id = ANY(%s)",
        (batch.id, job_ids),
    )
    conn.commit()
    result.calls = 1
    log.info("enrichment %s: submitted batch %s with %s requests",
             task.name, batch.id, len(requests))
    return batch.id, result


def collect_batches(conn, *, client: Any = None,
                    max_attempts: int = MAX_ATTEMPTS) -> RunResult:
    """Apply the results of every batch that has finished."""
    result = RunResult()
    batch_ids = [r["batch_id"] for r in conn.execute(
        "SELECT DISTINCT batch_id FROM enrichment_job WHERE status = 'batched'").fetchall()]
    if not batch_ids:
        return result
    client = client or make_client()

    for batch_id in batch_ids:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status != "ended":
            continue
        seen: set[int] = set()
        for item in client.messages.batches.results(batch_id):
            job_id = int(str(item.custom_id).removeprefix(CUSTOM_ID_PREFIX))
            seen.add(job_id)
            job = conn.execute(
                """SELECT id, entity_id, task, input_hash, attempts FROM enrichment_job
                    WHERE id = %s AND batch_id = %s AND status = 'batched'""",
                (job_id, batch_id),
            ).fetchone()
            if job is None:
                continue
            task = get_task(job["task"])
            outcome = item.result.type
            if outcome == "succeeded":
                try:
                    output = task.parse(item.result.message)
                except ValueError as exc:
                    if _fail(conn, job, f"{type(exc).__name__}: {exc}", max_attempts):
                        result.failed += 1
                    continue
                _store(conn, task, job, output)
                result.stored += 1
            else:
                # errored / canceled / expired: back to pending until attempts run out
                detail = getattr(getattr(item.result, "error", None), "type", "")
                if _fail(conn, job, f"batch result {outcome} {detail}".strip(), max_attempts):
                    result.failed += 1
        missing = conn.execute(
            """SELECT id, entity_id, input_hash, attempts FROM enrichment_job
                WHERE batch_id = %s AND status = 'batched' AND NOT (id = ANY(%s))""",
            (batch_id, list(seen)),
        ).fetchall()
        for job in missing:
            if _fail(conn, job, "missing from batch results", max_attempts):
                result.failed += 1
        conn.commit()
    log.info("enrichment collect: %s", result)
    return result
