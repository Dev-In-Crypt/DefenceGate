"""WP-127: no 502 while a container is replaced. Caddy holds a request and dials again (both upstreams), and the api and web
healthchecks are probed often while starting, so `up --wait` returns soon after they are ready. Measured locally with
caddy:2 and an upstream removed for 6 s: 3 x 502 without the hold, none with it (docs/verification/round6/wp127-selfcheck.md)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_both_upstreams_are_held_and_retried_while_they_restart():
    text = (ROOT / "infra" / "Caddyfile").read_text(encoding="utf8")
    blocks = re.findall(r"reverse_proxy (\S+) \{(.*?)\n\t\t\}", text, re.S)
    assert {name for name, _ in blocks} == {"api-edge:8000", "web:3000"}
    for name, body in blocks:
        assert "lb_try_duration 30s" in body and "lb_try_interval 250ms" in body, name


def test_api_and_web_healthchecks_are_probed_while_starting():
    compose = (ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf8")
    for service in ("api", "web"):
        hc = re.search(rf"\n  {service}:\n.*?\n    healthcheck:\n((?:      [^\n]*\n)+)", compose, re.S).group(1)
        assert "start_interval: 2s" in hc and "start_period: 60s" in hc, service
    assert "up -d --no-build --wait api" in compose          # the deploy order is written down
