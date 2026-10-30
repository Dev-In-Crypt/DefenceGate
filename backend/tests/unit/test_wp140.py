"""WP-140: privacy 1.7 and terms 2.2 are published, and the owner's switch keeps sign-in closed in production
until DGATE_ACCOUNTS_OPEN=1 (publishing the notice removed the last gate the code had besides the relay)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dgate import accounts, config
from tests.unit.test_compose_env import COMPOSE, _service

ROOT = Path(__file__).resolve().parents[3]
PAGES = ROOT / "web" / "app" / "(public)"


@pytest.fixture(autouse=True)
def _fresh_settings():
    config.reset_cache()
    yield
    config.reset_cache()


def test_the_api_gets_the_switch_closed_by_default_and_nobody_else_does():
    text = COMPOSE.read_text(encoding="utf-8")
    assert re.search(r"^\s+DGATE_ACCOUNTS_OPEN: \$\{DGATE_ACCOUNTS_OPEN:-0\}$", _service(text, "api"), re.M)
    # WP-158: the worker reads the same switch (closed by default) to send the associations' digest only while accounts are open
    assert re.search(r"^\s+DGATE_ACCOUNTS_OPEN: \$\{DGATE_ACCOUNTS_OPEN:-0\}$", _service(text, "worker"), re.M)
    for other in ("web", "caddy"):
        assert "ACCOUNTS_OPEN" not in _service(text, other), other


@pytest.mark.parametrize(("value", "is_open"), [(None, False), ("0", False), ("", False), ("true", False),
                                                ("yes", False), ("1", True), (" 1 ", True)])
def test_only_1_opens_the_switch(monkeypatch, value, is_open):
    if value is None:
        monkeypatch.delenv("DGATE_ACCOUNTS_OPEN", raising=False)
    else:
        monkeypatch.setenv("DGATE_ACCOUNTS_OPEN", value)
    assert config.settings().accounts_open is is_open


def test_in_production_accounts_stay_closed_until_the_switch_is_set(monkeypatch):
    monkeypatch.setenv("DGATE_ENV", "production")
    monkeypatch.setenv("DGATE_INTERNAL_SECRET", "site-and-api-share-this")
    monkeypatch.setenv("DGATE_ACCOUNT_KEY", "only-the-api-holds-this")
    monkeypatch.delenv("DGATE_ACCOUNTS_OPEN", raising=False)
    monkeypatch.setattr(accounts.mailer, "ready", lambda: True)       # a relay that passed its check
    assert accounts.accounts_problem() == "DGATE_ACCOUNTS_OPEN"
    monkeypatch.setenv("DGATE_ACCOUNTS_OPEN", "1")
    config.reset_cache()
    assert accounts.accounts_problem() is None


def test_outside_production_the_switch_is_not_needed(monkeypatch):
    monkeypatch.setenv("DGATE_ENV", "development")
    monkeypatch.delenv("DGATE_ACCOUNTS_OPEN", raising=False)
    monkeypatch.setattr(accounts.mailer, "ready", lambda: True)
    assert accounts.accounts_problem() is None


def test_the_published_versions_are_the_pages_and_the_archived_copies():
    assert accounts._version(accounts.PRIVACY_VERSION) >= accounts._version(accounts.PASSWORD_PRIVACY_VERSION)
    privacy = (PAGES / "privacy" / "page.tsx").read_text(encoding="utf-8")
    terms = (PAGES / "terms" / "page.tsx").read_text(encoding="utf-8")
    assert f'lead="Version {accounts.PRIVACY_VERSION}, published 26 October 2026' in privacy
    assert f'lead="Version {accounts.TERMS_VERSION}, published 26 October 2026' in terms
    versions = ROOT / "docs" / "legal" / "versions"
    assert (versions / f"privacy-v{accounts.PRIVACY_VERSION}-2026-10-26.md").is_file()
    assert (versions / f"terms-v{accounts.TERMS_VERSION}-2026-10-26.md").is_file()


def test_no_payment_text_is_published_yet():
    """WP-124's additions wait for Creem: neither page names it or has a 'Paid plans' term."""
    for page in ("privacy", "terms"):
        text = (PAGES / page / "page.tsx").read_text(encoding="utf-8")
        assert "Creem" not in text and "Paid plans" not in text, page
