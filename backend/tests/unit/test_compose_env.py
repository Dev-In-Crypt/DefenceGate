"""The worker stores snapshots the API serves only when a switch in them matches its own (25 Oct 2026: the worker lacked
DGATE_PLACSP_AWARDS_PUBLIC, so the market money and the supplier value order were computed and never served)."""

from __future__ import annotations

import re
from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[3] / "infra" / "docker-compose.yml"
# Settings a stored snapshot carries and the API compares (money.stored, suppliers value order)
SNAPSHOT_SWITCHES = ("DGATE_PLACSP_AWARDS_PUBLIC",)


def _service(text: str, name: str) -> str:
    m = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)", text, re.M | re.S)
    assert m, name
    return m.group(1)


def test_the_api_and_the_worker_read_the_same_snapshot_switches():
    text = COMPOSE.read_text(encoding="utf-8")
    api, worker = _service(text, "api"), _service(text, "worker")
    for key in SNAPSHOT_SWITCHES:
        line = re.compile(rf"^\s+{key}: (.+)$", re.M)
        a, w = line.search(api), line.search(worker)
        assert a and w, key
        assert a.group(1) == w.group(1), key
