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


def test_caddy_mounts_the_directory_of_its_caddyfile_not_the_file():
    """WP-136: a single-file bind mount stays on the file the container started with, and git checkout replaces a file
    instead of writing into it. Production ran the Caddyfile of 21 Oct until 25 Oct ("config is unchanged" at every
    reload), so WP-127's hold never ran: 10 x 502 at the r10 deploy. Measured in a lab (caddy 2.11.4; api and web
    recreated, then absent for 6 s; docs/verification/round6/wp136-selfcheck.md): file mount 31 + 31 x 502, directory 0."""
    text = COMPOSE.read_text(encoding="utf-8")
    assert "      - ./caddy:/etc/caddy:ro\n" in _service(text, "caddy")
    assert (COMPOSE.parent / "caddy" / "Caddyfile").is_file()
    # No file of the checkout is bind-mounted on its own (the secrets are not in the repository, and git never replaces them).
    for source in re.findall(r"^\s+- (\.{1,2}/[^:]+):", text, re.M):
        assert source.startswith("./secrets/") or not (COMPOSE.parent / source).is_file(), source
    # The deploy loads the Caddyfile before api and web are replaced ...
    order = [text.index(s) for s in ("sh infra/caddy-reload.sh", "up -d --no-build --wait api", "--wait web")]
    assert order == sorted(order)
    # ... with a script that validates first, loads, and fails unless the container reads the checked-out file.
    script = (COMPOSE.parent / "caddy-reload.sh").read_text(encoding="utf-8")
    assert script.startswith("#!/bin/sh\n") and "\nset -eu\n" in script
    steps = [script.index(s) for s in ("caddy validate --config", "caddy reload --config", "sha256sum /etc/caddy/Caddyfile")]
    assert steps == sorted(steps)
    assert '-v "$PWD/infra/caddy:/etc/caddy:ro"' in script                 # validates the checkout, not the running copy
    assert re.search(r'if \[ "\$host" != "\$seen" \]; then\n.*\n\s+exit 1\n', script)
