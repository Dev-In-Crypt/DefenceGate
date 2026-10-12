"""A refusal from Telegram is not a delivered alert."""

from __future__ import annotations

import httpx
import pytest

from dgate import config
from dgate.ops import notify as notify_mod


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("DGATE_TELEGRAM_TOKEN", "123:test-token")
    monkeypatch.setenv("DGATE_TELEGRAM_CHAT_ID", "42")
    config.reset_cache()
    yield
    config.reset_cache()


def _reply(status: int):
    return lambda url, **kw: httpx.Response(status, request=httpx.Request("POST", url))


def test_an_accepted_message_is_sent(monkeypatch):
    monkeypatch.setattr(httpx, "post", _reply(200))
    assert notify_mod.notify("x") is True


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500])
def test_a_refusal_is_not_reported_as_sent(monkeypatch, status):
    monkeypatch.setattr(httpx, "post", _reply(status))
    assert notify_mod.notify("x") is False


def test_a_transport_error_is_not_sent_and_does_not_leak_the_token(monkeypatch, caplog):
    def boom(url, **kw):
        raise httpx.ConnectError(f"cannot connect to {url}")

    monkeypatch.setattr(httpx, "post", boom)
    assert notify_mod.notify("x") is False
    assert "test-token" not in caplog.text


def test_unconfigured_is_log_only(monkeypatch):
    monkeypatch.delenv("DGATE_TELEGRAM_TOKEN")
    config.reset_cache()
    assert notify_mod.notify("x") is False
