"""The proxy's access-log filter and its container limits (security review of 5 November 2026)."""

from __future__ import annotations

import re
from pathlib import Path

INFRA = Path(__file__).resolve().parents[3] / "infra"


def test_both_logs_drop_the_next_parameter_with_the_token():
    """`next` carries a whole address with its own query string; `delete token` alone does not reach inside it."""
    text = (INFRA / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    blocks = re.findall(r"(request>uri|request>headers>Referer) query \{(.*?)\}", text, re.S)
    assert len(blocks) == 4                     # uri and Referer, in the default log and in the access log
    for _, body in blocks:
        assert "delete token" in body and "delete next" in body


def test_the_proxy_runs_with_one_capability_and_a_memory_ceiling():
    text = (INFRA / "docker-compose.yml").read_text(encoding="utf-8")
    m = re.search(r"^  caddy:\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)", text, re.M | re.S)
    assert m
    caddy = m.group(1)
    assert "    cap_drop: [ALL]\n" in caddy
    assert "    cap_add: [NET_BIND_SERVICE]\n" in caddy
    assert '    security_opt: ["no-new-privileges:true"]\n' in caddy
    assert re.search(r"^    mem_limit: \d+m$", caddy, re.M)
    assert re.search(r"^    pids_limit: \d+$", caddy, re.M)
