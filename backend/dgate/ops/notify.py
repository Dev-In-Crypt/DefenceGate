"""Alerting.

Silent ingestion failure is the primary technical risk of this product: the
value proposition is completeness, and a connector that quietly returns nothing
looks exactly like a quiet day. So a run that fails, or finishes below its
coverage floor, has to be loud.

Two independent channels, because they fail differently:

  healthchecks.io  a dead-man switch. It fires when we say *nothing*, which is
                   the case a process that crashed at boot cannot report.
  Telegram         a message to the operator, for the cases we can describe.

Both are optional. Unconfigured means log-only, never a crash: an alerting
backend being down must not take the pipeline with it.
"""

from __future__ import annotations

import logging
from typing import Literal

import httpx

from ..config import settings

log = logging.getLogger("ops.notify")

PingEvent = Literal["start", "success", "fail"]


def ping(slug: str, event: PingEvent = "success", *, timeout: float = 5.0) -> bool:
    """Tell healthchecks.io a job started, finished, or failed.

    Never raises. A monitoring call that breaks the thing it monitors is worse
    than no monitoring.
    """
    base = settings().healthchecks_base
    if not base:
        log.debug("healthchecks not configured, skipping %s/%s", slug, event)
        return False
    suffix = {"start": "/start", "success": "", "fail": "/fail"}[event]
    url = f"{base.rstrip('/')}/{slug}{suffix}"
    try:
        httpx.get(url, timeout=timeout)
        return True
    except Exception as exc:  # noqa: BLE001 - deliberately swallowed
        log.warning("healthchecks ping failed (%s/%s): %s", slug, event, exc)
        return False


def notify(text: str, *, timeout: float = 10.0) -> bool:
    """Send an operator message. Logs at warning level either way."""
    log.warning("ALERT: %s", text)
    cfg = settings()
    if not (cfg.telegram_token and cfg.telegram_chat_id):
        return False
    try:
        httpx.post(
            f"https://api.telegram.org/bot{cfg.telegram_token}/sendMessage",
            json={"chat_id": cfg.telegram_chat_id, "text": text[:4000],
                  "disable_web_page_preview": True},
            timeout=timeout,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("telegram notify failed: %s", exc)
        return False
