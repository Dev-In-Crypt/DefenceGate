"""WP-161: the launch-day rehearsal (docs/verification/features/wp161-selfcheck.md). One test per breakage found when
every switch was turned on together."""

from __future__ import annotations

import re

import pytest

from dgate import config
from tests.unit.test_compose_env import COMPOSE, _service

# Every launch switch the API reads, with the setting it fills.
SWITCHES = {"DGATE_ACCOUNTS_OPEN": "accounts_open", "DGATE_COMPANY_REPORT_OPEN": "company_report_open",
            "DGATE_SIGNALS_FULL_OPEN": "signals_full_open", "DGATE_API_KEYS_OPEN": "api_keys_open"}


@pytest.fixture(autouse=True)
def _fresh_settings():
    config.reset_cache()
    yield
    config.reset_cache()


@pytest.mark.parametrize("name", sorted(SWITCHES))
def test_every_launch_switch_reaches_the_api_closed_by_default(name):
    """DGATE_SIGNALS_FULL_OPEN was read by the API but not passed to its container: infra/.env could not open it."""
    assert re.search(rf"^\s+{name}: \$\{{{name}:-0\}}$", _service(COMPOSE.read_text(encoding="utf-8"), "api"), re.M), name


@pytest.mark.parametrize("name", sorted(SWITCHES))
def test_every_launch_switch_opens_with_1_and_stays_closed_otherwise(monkeypatch, name):
    """The owner sets them all to 1 on launch day; DGATE_SIGNALS_FULL_OPEN opened only with "true"."""
    for value, is_open in (("1", True), (" 1 ", True), ("0", False), ("", False)):
        monkeypatch.setenv(name, value)
        config.reset_cache()
        assert getattr(config.settings(), SWITCHES[name]) is is_open, (name, value)
    monkeypatch.delenv(name)
    config.reset_cache()
    assert getattr(config.settings(), SWITCHES[name]) is False
