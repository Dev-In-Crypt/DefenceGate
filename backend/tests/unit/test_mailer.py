"""WP-123: the mailer. Plain text with an HTML alternative made from it (no tracking), sender
name DefenceGate, TLS required for any relay not on this host, a health check that sends
nothing, and the development catcher that writes .eml files (never in production). Every
relay here is the local catcher on 127.0.0.1: no network."""

from __future__ import annotations

import socket
from email import message_from_bytes, policy

import pytest

from dgate import config
from dgate.ops import mailer
from tests.mailcatcher import MailCatcher

TEXT = ("Open this link. It works once:\n\nhttps://site.test/auth/verify?token=abc_DEF-123&x=1\n\n"
        "Ignore <b>this</b> if it was not you & nothing changes.")


@pytest.fixture()
def env(monkeypatch):
    for name in ("DGATE_SMTP_HOST", "DGATE_SMTP_PORT", "DGATE_SMTP_USER", "DGATE_SMTP_PASSWORD", "DGATE_SMTP_FROM",
                 "DGATE_SMTP_SECURITY", "DGATE_MAIL_CATCHER_DIR", "DGATE_ENV"):
        monkeypatch.delenv(name, raising=False)

    def setenv(**values: str) -> None:
        for k, v in values.items():
            monkeypatch.setenv(k, v)
        config.reset_cache()
        mailer.reset_check()
    setenv()
    yield setenv
    config.reset_cache()
    mailer.reset_check()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_the_html_part_is_the_text_escaped_with_its_links_unchanged():
    out = mailer.to_html(TEXT)
    assert "<b>this</b>" not in out and "&lt;b&gt;this&lt;/b&gt;" in out and "&amp; nothing" in out
    link = "https://site.test/auth/verify?token=abc_DEF-123&amp;x=1"
    assert f'<a href="{link}">{link}</a>' in out            # the same address, not a redirect
    assert "<img" not in out and "src=" not in out and "<link" not in out and "<script" not in out


def test_a_message_is_text_and_html_from_defencegate(env):
    env(DGATE_SMTP_FROM="no-reply@example.test")
    msg = mailer.build_message("ann@example.com", "Confirm", TEXT)
    assert msg["From"] == "DefenceGate <no-reply@example.test>"
    assert msg.get_content_type() == "multipart/alternative"
    kinds = [p.get_content_type() for p in msg.iter_parts()]
    assert kinds == ["text/plain", "text/html"]
    plain = msg.get_body(("plain",)).get_content()
    assert "https://site.test/auth/verify?token=abc_DEF-123&x=1" in plain


def test_plain_smtp_is_refused_for_a_relay_that_is_not_on_this_host(env):
    env(DGATE_SMTP_HOST="smtp.example.test", DGATE_SMTP_FROM="no-reply@example.test", DGATE_SMTP_SECURITY="none")
    assert mailer.problem() and not mailer.can_send() and not mailer.ready()
    assert mailer.send_mail("ann@example.com", "s", "b") is False
    env(DGATE_SMTP_SECURITY="starttls")
    assert mailer.problem() is None
    env(DGATE_SMTP_HOST="127.0.0.1", DGATE_SMTP_SECURITY="none")
    assert mailer.problem() is None


def test_not_configured_means_not_ready_and_nothing_sent(env):
    assert mailer.problem() == "not configured" and not mailer.ready()
    assert mailer.send_mail("ann@example.com", "s", "b") is False


def test_the_health_check_passes_against_a_working_relay_and_sends_nothing(env):
    with MailCatcher() as relay:
        env(DGATE_SMTP_HOST="127.0.0.1", DGATE_SMTP_PORT=str(relay.port), DGATE_SMTP_SECURITY="none",
            DGATE_SMTP_FROM="no-reply@example.test")
        assert mailer.ready() is True
        assert relay.box == []                                  # a check is not a message


def test_a_relay_that_does_not_answer_keeps_mail_closed_and_the_answer_is_kept(env, monkeypatch):
    env(DGATE_SMTP_HOST="127.0.0.1", DGATE_SMTP_PORT=str(_free_port()), DGATE_SMTP_SECURITY="none",
        DGATE_SMTP_FROM="no-reply@example.test")
    assert mailer.ready() is False
    calls = []
    monkeypatch.setattr(mailer, "check_relay", lambda: calls.append(1) or True)
    assert mailer.ready() is False and calls == []             # within CHECK_FAILED_SECONDS: not asked again
    monkeypatch.setenv("DGATE_SMTP_PORT", str(_free_port()))     # other settings: checked at once
    config.reset_cache()
    assert mailer.ready() is True and calls == [1]
    assert mailer.ready() is True and calls == [1]              # a pass is kept (CHECK_OK_SECONDS)


def test_send_mail_delivers_both_parts_through_the_relay(env):
    with MailCatcher() as relay:
        env(DGATE_SMTP_HOST="127.0.0.1", DGATE_SMTP_PORT=str(relay.port), DGATE_SMTP_SECURITY="none",
            DGATE_SMTP_FROM="no-reply@example.test")
        assert mailer.send_mail("ann@example.com", "Confirm your DefenceGate account", TEXT) is True
    (got,) = relay.box
    assert got["rcpt"] == ["ann@example.com"]
    msg = got["message"]
    assert msg["From"] == "DefenceGate <no-reply@example.test>"
    assert [p.get_content_type() for p in msg.iter_parts()] == ["text/plain", "text/html"]


def test_header_injection_is_refused(env, tmp_path):
    env(DGATE_MAIL_CATCHER_DIR=str(tmp_path))
    assert mailer.send_mail("ann@example.com\r\nBcc: x@example.test", "s", "b") is False
    assert mailer.send_mail("ann@example.com", "s\nBcc: x@example.test", "b") is False
    assert list(tmp_path.iterdir()) == []


def test_the_catcher_writes_eml_files_and_is_never_used_in_production(env, tmp_path):
    env(DGATE_MAIL_CATCHER_DIR=str(tmp_path / "mail"))
    assert mailer.ready() is True
    assert mailer.send_mail("ann@example.com", "Confirm", TEXT) is True
    (eml,) = (tmp_path / "mail").glob("*.eml")
    msg = message_from_bytes(eml.read_bytes(), policy=policy.default)
    assert msg["To"] == "ann@example.com" and "token=abc_DEF-123" in msg.get_body(("plain",)).get_content()
    env(DGATE_ENV="production")
    assert mailer.problem() == "not configured" and mailer.ready() is False
    assert mailer.send_mail("ann@example.com", "Confirm", TEXT) is False
    assert len(list((tmp_path / "mail").glob("*.eml"))) == 1
