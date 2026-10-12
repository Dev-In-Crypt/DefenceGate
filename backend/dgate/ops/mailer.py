"""Outgoing mail: sign-in links and alert digests.

Plain text only, no tracking pixel, no remote content. One function, so that the account
code never knows which relay is behind it, and so tests replace it with a list.

Mail is deliverable only when `DGATE_SMTP_HOST` and `DGATE_SMTP_FROM` are set. When they
are not, `can_send()` is False, the site shows "sign-in is not open", and nothing is sent:
an unconfigured relay is never a reason to crash or to pretend.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from ..config import settings

log = logging.getLogger("ops.mailer")

TIMEOUT_SECONDS = 15


def can_send() -> bool:
    cfg = settings()
    return bool(cfg.smtp_host and cfg.smtp_from)


def send_mail(to: str, subject: str, body: str) -> bool:
    """Send one plain-text message. Never raises; returns whether the relay accepted it.

    The recipient and the body are never logged: a sign-in link in a log file is a
    credential in a log file.
    """
    cfg = settings()
    if not can_send():
        log.warning("mail not sent: no SMTP relay configured")
        return False
    if any(c in to for c in "\r\n") or any(c in subject for c in "\r\n"):
        log.warning("mail refused: header injection attempt")
        return False
    msg = EmailMessage()
    msg["From"] = cfg.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=(cfg.smtp_from or "dgate").rsplit("@", 1)[-1])
    msg.set_content(body)
    try:
        if cfg.smtp_security == "ssl":
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                cfg.smtp_host, cfg.smtp_port, timeout=TIMEOUT_SECONDS,
                context=ssl.create_default_context())
        else:
            client = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=TIMEOUT_SECONDS)
        with client:
            if cfg.smtp_security == "starttls":
                client.starttls(context=ssl.create_default_context())
            if cfg.smtp_user and cfg.smtp_password:
                client.login(cfg.smtp_user, cfg.smtp_password)
            client.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("mail not sent: %s", type(exc).__name__)
        return False
