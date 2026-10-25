"""WP-123 checks that need no database: the account key reaches the API only, the plan lists match the web's, and
the settings never print the key."""

from __future__ import annotations

import re
from pathlib import Path

from dgate import accounts, config
from tests.unit.test_compose_env import COMPOSE, _service

WEB_PLANS = Path(__file__).resolve().parents[3] / "web" / "lib" / "plans.ts"


def test_the_account_key_is_given_to_the_api_and_not_to_the_site():
    text = COMPOSE.read_text(encoding="utf-8")
    assert re.search(r"^\s+DGATE_ACCOUNT_KEY: ", _service(text, "api"), re.M)
    for other in ("web", "worker", "caddy"):
        assert "ACCOUNT_KEY" not in _service(text, other), other


def test_the_plan_ids_are_the_same_on_both_sides():
    text = WEB_PLANS.read_text(encoding="utf-8")
    labels = re.search(r"PLAN_LABELS = \{(.*?)\}", text).group(1)
    assert tuple(re.findall(r"(\w+): '", labels)) == accounts.PLANS
    assert set(re.findall(r"'(monthly|yearly)'", text)) == set(accounts.BILLINGS)


def test_the_account_key_is_not_in_the_settings_repr(monkeypatch):
    monkeypatch.setenv("DGATE_ACCOUNT_KEY", "KEYSECRET")
    config.reset_cache()
    try:
        assert "KEYSECRET" not in repr(config.settings())
    finally:
        config.reset_cache()
