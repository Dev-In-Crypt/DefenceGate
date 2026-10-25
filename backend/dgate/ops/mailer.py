"""Outgoing mail: account mails (confirm, reset, password changed) and alert digests.

Every message is plain text with an HTML alternative made from the same text (WP-123): no
tracking pixel, no image, no remote content, no rewritten links. One function, so that the
account code never knows which relay is behind it, and so tests replace it with a list.

Mail is deliverable only when it is configured (`DGATE_SMTP_HOST` and `DGATE_SMTP_FROM`, or
the development catcher `DGATE_MAIL_CATCHER_DIR`) AND the health check of the relay passed
(`ready()`): connect, TLS, log in, `NOOP`, nothing sent. Until then the site shows "sign-in
opens soon" and nothing is sent: an unconfigured or broken relay is never a reason to crash
or to pretend.

The catcher writes each message as an `.eml` file into a directory instead of sending it, so
a local run (and the end-to-end test) can open the links without any mail provider. It is
refused when `DGATE_ENV=production`.
"""

from __future__ import annotations

import html
import ipaddress
import logging
import re
import smtplib
import ssl
import threading
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from ..config import settings

log = logging.getLogger("ops.mailer")

TIMEOUT_SECONDS = 15
CHECK_TIMEOUT_SECONDS = 5      # the health check runs on a request path: short
CHECK_OK_SECONDS = 600         # a passed check is trusted this long, a failed one is retried after
CHECK_FAILED_SECONDS = 60
SENDER_NAME = "DefenceGate"

_check_lock = threading.Lock()
_check: dict[str, object] = {"key": None, "ok": False, "at": 0.0}


def _catcher() -> Path | None:
    cfg = settings()
    if not cfg.mail_catcher_dir or cfg.env == "production":
        return None
    return Path(cfg.mail_catcher_dir)


def _loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def problem() -> str | None:
    """Why mail cannot be sent with the settings as they are, or None. Plain SMTP (no TLS) is
    accepted only to a relay on this host: a reset link must not cross a network in clear."""
    cfg = settings()
    if _catcher():
        return None
    if not (cfg.smtp_host and cfg.smtp_from):
        return "not configured"
    if cfg.smtp_security not in ("starttls", "ssl") and not _loopback(cfg.smtp_host):
        return "DGATE_SMTP_SECURITY must be starttls or ssl for a relay that is not on this host"
    return None


def can_send() -> bool:
    """Configured (the check below has not necessarily run)."""
    return problem() is None


def _client(cfg, timeout: float) -> smtplib.SMTP:
    if cfg.smtp_security == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=timeout,
                                                context=ssl.create_default_context())
    else:
        client = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=timeout)
    try:
        if cfg.smtp_security == "starttls":
            client.starttls(context=ssl.create_default_context())
        if cfg.smtp_user and cfg.smtp_password:
            client.login(cfg.smtp_user, cfg.smtp_password)
    except BaseException:
        client.close()
        raise
    return client


def check_relay() -> bool:
    """The health check itself: connect, TLS, log in, NOOP, QUIT. Sends nothing."""
    cfg = settings()
    catcher = _catcher()
    if catcher:
        try:
            catcher.mkdir(parents=True, exist_ok=True)
            return True
        except OSError:
            return False
    if problem():
        return False
    try:
        with _client(cfg, CHECK_TIMEOUT_SECONDS) as client:
            code, _ = client.noop()
        return code == 250
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("mail relay check failed: %s", type(exc).__name__)
        return False


def ready() -> bool:
    """Configured and the relay passed its health check. The result is kept per set of
    settings (CHECK_OK_SECONDS when it passed, CHECK_FAILED_SECONDS when not), and one caller
    runs the check while the others get the last answer."""
    if not can_send():
        return False
    cfg = settings()
    key = (cfg.smtp_host, cfg.smtp_port, cfg.smtp_user, cfg.smtp_password, cfg.smtp_from,
           cfg.smtp_security, str(_catcher()))
    now = time.monotonic()
    fresh = _check["key"] == key and now - float(_check["at"]) < (  # type: ignore[arg-type]
        CHECK_OK_SECONDS if _check["ok"] else CHECK_FAILED_SECONDS)
    if fresh:
        return bool(_check["ok"])
    if not _check_lock.acquire(blocking=_check["key"] != key):
        return bool(_check["ok"])            # another request is checking these settings now
    try:
        ok = check_relay()
        _check.update(key=key, ok=ok, at=time.monotonic())
        return ok
    finally:
        _check_lock.release()


def reset_check() -> None:
    """Forget the last health check (tests, and after the settings change)."""
    _check.update(key=None, ok=False, at=0.0)


_URL = re.compile(r"https?://[^\s<>\"']+")


def to_html(text: str) -> str:
    """The plain text as HTML: escaped, paragraphs at blank lines, URLs as plain links (the
    same address as in the text: nothing is rewritten or counted). No image, no style sheet."""
    def para(block: str) -> str:
        escaped = html.escape(block)
        linked = _URL.sub(lambda m: f'<a href="{m.group(0)}">{m.group(0)}</a>', escaped)
        return "<p>" + linked.replace("\n", "<br>\n") + "</p>"
    body = "\n".join(para(b) for b in re.split(r"\n\s*\n", text.strip()) if b.strip())
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"></head>\n'
            '<body style="font-family:sans-serif;line-height:1.5;max-width:40em">\n'
            f"{body}\n</body></html>\n")


def build_message(to: str, subject: str, body: str) -> EmailMessage:
    cfg = settings()
    sender = cfg.smtp_from or "no-reply@localhost"
    msg = EmailMessage()
    msg["From"] = formataddr((SENDER_NAME, sender))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1])
    msg.set_content(body)
    msg.add_alternative(to_html(body), subtype="html")
    return msg


def send_mail(to: str, subject: str, body: str) -> bool:
    """Send one message (plain text and its HTML form). Never raises; returns whether the
    relay (or the catcher) accepted it.

    The recipient and the body are never logged: a link in a log file is a credential in a
    log file.
    """
    cfg = settings()
    if not can_send():
        log.warning("mail not sent: %s", problem())
        return False
    if any(c in to for c in "\r\n") or any(c in subject for c in "\r\n"):
        log.warning("mail refused: header injection attempt")
        return False
    msg = build_message(to, subject, body)
    catcher = _catcher()
    try:
        if catcher:
            catcher.mkdir(parents=True, exist_ok=True)
            name = f"{time.time_ns()}-{msg['Message-ID'].strip('<>').split('@')[0]}.eml"
            (catcher / name).write_bytes(bytes(msg))
            return True
        with _client(cfg, TIMEOUT_SECONDS) as client:
            client.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("mail not sent: %s", type(exc).__name__)
        return False
