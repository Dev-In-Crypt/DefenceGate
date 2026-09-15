"""Which notices need a task run, recorded as rows in enrichment_job.

A job is queued for the current version of every defence opportunity whose
input, hashed, has no result yet. The hash is the whole decision:

  - a notice seen again unchanged hashes the same and queues nothing
  - an amended notice whose relevant fields changed hashes differently and
    queues one job
  - an amendment that touched nothing the task reads queues nothing either,
    because the hash covers only what the task sends

Input comes from the archived version payload, not the serving row: it is the
record of what the source said, and it carries fields -- the description --
that the serving row does not keep.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .base import Task

log = logging.getLogger(__name__)

ENTITY = "opportunity"


@dataclass
class EnqueueResult:
    examined: int = 0
    queued: int = 0
    already_done: int = 0
    already_queued: int = 0
    no_input: int = 0


def current_versions(conn, *, only_ids: list[int] | None = None):
    """Current archived version of every defence opportunity."""
    where = "o.is_defence"
    params: list[Any] = []
    if only_ids is not None:
        where += " AND o.id = ANY(%s)"
        params.append(only_ids)
    return conn.execute(
        f"""SELECT o.id AS opportunity_id, v.payload
              FROM opportunity o
              JOIN opportunity_version v
                ON v.opportunity_id = o.id AND v.version = o.current_version
             WHERE {where}
             ORDER BY o.id""",
        params,
    )


def enqueue(conn, task: Task, *, only_ids: list[int] | None = None) -> EnqueueResult:
    result = EnqueueResult()
    for row in current_versions(conn, only_ids=only_ids):
        result.examined += 1
        task_input = task.build_input(row["payload"])
        if task_input is None:
            result.no_input += 1
            continue
        digest = task.input_hash(task_input)

        if conn.execute(
            """SELECT 1 FROM enrichment
                WHERE entity_type = %s AND entity_id = %s AND task = %s AND input_hash = %s""",
            (ENTITY, row["opportunity_id"], task.name, digest),
        ).fetchone():
            result.already_done += 1
            continue

        inserted = conn.execute(
            """INSERT INTO enrichment_job (entity_type, entity_id, task, input_hash)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (entity_type, entity_id, task, input_hash) DO NOTHING
               RETURNING id""",
            (ENTITY, row["opportunity_id"], task.name, digest),
        ).fetchone()
        if inserted:
            result.queued += 1
        else:
            result.already_queued += 1
    conn.commit()
    log.info("enqueue %s: %s", task.name, result)
    return result
