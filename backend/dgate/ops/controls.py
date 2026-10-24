"""Nightly completeness controls (completeness-evidence report, 15 October 2026).

Three kinds, all cheap and all read-only against the sources:

  day totals   BZP, BOAMP and TenderNed state how many notices a publication day holds.
               After a run, each complete day it walked is compared with that number
               (`check_days`); a shortfall of more than 5 rows or 2 % ends the run
               `partial` and says which day, so the existing alert fires.
  Atlas        the Zenodo record's `metadata.version` and file checksums are remembered;
               a change is an alert (a new quarter exists, or the files were replaced).
  PLACSP       no portal counter exists, so two measures of the stored rows: TED Spanish
               defence notices older than 14 days with no Spanish twin, and the share of
               PLACSP rows without a publication date (alarm above 5 %).

Nothing here writes to `opportunity`; the last answer of the weekly and daily controls is
kept in `control_check` and shown by /v1/health.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import httpx

from ..sources import USER_AGENT, new_client, request_with_retry

log = logging.getLogger("controls")

SHORT_ROWS = 5          # a day more than this many rows short is an alert ...
SHORT_SHARE = 0.02      # ... and so is one more than this share short
NULL_DATE_ALARM = 0.05
UNLINKED_AFTER_DAYS = 14
ATLAS_EVERY_DAYS = 6
ALERT_EVERY_HOURS = 72


def verdict(landed: int, official: int) -> dict[str, Any]:
    """One day: what was landed against what the portal says. Only a shortfall alerts;
    a surplus (a notice landed once per version) is recorded, not loud."""
    short = official - landed
    alert = short > 0 and (short > SHORT_ROWS or short / official > SHORT_SHARE)
    return {"landed": landed, "official": official, "short": max(short, 0), "alert": alert}


def _officials() -> dict[str, Callable[..., int]]:
    from ..sources import boamp, ezamowienia, tenderned

    return {ezamowienia.SOURCE_CODE: ezamowienia.official_total,
            boamp.SOURCE_CODE: boamp.official_total,
            tenderned.SOURCE_CODE: tenderned.official_total}


def check_days(code: str, landed: dict[date, int], *, skip: set[date] | frozenset = frozenset(),
               today: date | None = None, official: Callable[[date], int] | None = None,
               pause: float = 1.0) -> tuple[dict[str, Any], str | None]:
    """Compare each complete day a run landed with the portal's count for it.

    Today is not compared (it is still being published) and neither is a day the walk
    reported as unread. A counter that cannot be read is recorded as `error`, never as an
    alert: the control must not turn a portal outage into a second incident.
    Returns the detail to store on the run and the sentence for its error, or None.
    """
    today = today or date.today()
    client = None
    if official is None:
        func = _officials()[code]
        client = new_client(headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                            follow_redirects=True)

        def official(day: date, _f=func, _c=client) -> int:
            return _f(day, client=_c)

    days: dict[str, Any] = {}
    short: list[str] = []
    try:
        first = True
        for day in sorted(landed):
            if day >= today or day in skip:
                continue
            if not first and pause:
                time.sleep(pause)
            first = False
            try:
                row = verdict(landed[day], official(day))
            except Exception as exc:  # noqa: BLE001 - see docstring
                days[day.isoformat()] = {"landed": landed[day], "error": type(exc).__name__}
                continue
            days[day.isoformat()] = row
            if row["alert"]:
                short.append(f"{day}: landed {row['landed']} of {row['official']} "
                             f"(-{row['short']})")
    finally:
        if client is not None:
            client.close()
    detail = {"days": days, "short": bool(short)}
    return detail, (f"{code}: fewer notices landed than the portal states, " + "; ".join(short)
                    if short else None)


# ------------------------------------------------------------------ Atlas

def zenodo_state(record: dict[str, Any]) -> dict[str, Any]:
    """Version and file checksums of the Zenodo record: what a re-release would change."""
    return {"version": (record.get("metadata") or {}).get("version"),
            "files": {f.get("key"): f.get("checksum") for f in record.get("files", [])}}


def fetch_zenodo_record() -> dict[str, Any]:
    from ..sources.atlas_pl import ZENODO_API

    def send() -> httpx.Response:
        r = httpx.get(ZENODO_API, headers={"User-Agent": USER_AGENT},
                      follow_redirects=True, timeout=60.0)
        r.raise_for_status()
        return r

    return request_with_retry(send, what="Zenodo record").json()


def check_atlas(conn, *, fetch: Callable[[], dict[str, Any]] = fetch_zenodo_record,
                now: datetime | None = None, force: bool = False) -> dict[str, Any] | None:
    """Weekly. The first look stores a baseline (`ok`); a different version or checksum is
    an `alert`, and the new state replaces the old one so it alerts once."""
    now = now or datetime.now(timezone.utc)
    row = conn.execute("SELECT status, checked_at, state FROM control_check "
                       "WHERE control = 'atlas_zenodo'").fetchone()
    if row and not force and now - row["checked_at"] < timedelta(days=ATLAS_EVERY_DAYS):
        return None
    state = zenodo_state(fetch())
    changed = bool(row) and bool(row["state"]) and row["state"] != state
    detail = {"version": state["version"], "files": len(state["files"])}
    if changed:
        detail["was"] = (row["state"] or {}).get("version")
    status = "alert" if changed else "ok"
    _save(conn, "atlas_zenodo", status, state, detail, now)
    return {"control": "atlas_zenodo", "status": status, "detail": detail}


# ----------------------------------------------------------------- PLACSP

def placsp_metrics(conn) -> dict[str, Any]:
    ted = conn.execute("SELECT id FROM source WHERE code = 'ted'").fetchone()["id"]
    unlinked = conn.execute(
        """SELECT count(*) AS n, min(t.published_at) AS oldest FROM opportunity t
            WHERE t.source_id = %s AND t.country = 'ES' AND t.is_defence
              AND t.published_at >= current_date - 365
              AND t.published_at < current_date - %s
              AND NOT EXISTS (SELECT 1 FROM opportunity n WHERE n.ted_ref = t.native_id
                                 AND n.source_id <> t.source_id)
              -- WP-113: a national row holds one `ted_ref`, the procedure's first TED publication; the procedure's
              -- later ones (its award notice) are its twins through the eForms procedure identifier: 764 of the 833
              -- "unlinked" Spanish TED notices of 24 October 2026 were these
              AND NOT (t.procedure_identifier IS NOT NULL AND EXISTS (
                    SELECT 1 FROM opportunity n WHERE n.procedure_identifier = t.procedure_identifier
                       AND n.source_id <> t.source_id))""",
        (ted, UNLINKED_AFTER_DAYS)).fetchone()
    dates = conn.execute(
        # WP-113: an award or contract entry without a call notice states its own date (`notice_date`, served as the
        # notice date): 17,741 of the 17,757 rows without a publication date of 24 October 2026. Missing is neither.
        """SELECT count(*) FILTER (WHERE o.published_at IS NULL AND o.notice_date IS NULL) AS missing, count(*) AS n
             FROM opportunity o JOIN source s ON s.id = o.source_id
            WHERE s.code IN ('es_placsp', 'es_placsp_agg')""").fetchone()
    rate = dates["missing"] / dates["n"] if dates["n"] else 0.0
    return {"ted_es_unlinked_14d": unlinked["n"],
            "ted_es_unlinked_oldest": (unlinked["oldest"].isoformat()
                                       if unlinked["oldest"] else None),
            "placsp_rows": dates["n"], "placsp_null_date_rows": dates["missing"],
            "placsp_null_date_rate": round(rate, 4)}


def check_placsp(conn, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    detail = placsp_metrics(conn)
    status = "alert" if detail["placsp_null_date_rate"] > NULL_DATE_ALARM else "ok"
    _save(conn, "placsp_links", status, {}, detail, now)
    return {"control": "placsp_links", "status": status, "detail": detail}


def _save(conn, control: str, status: str, state: dict, detail: dict, now: datetime) -> None:
    conn.execute(
        """INSERT INTO control_check (control, status, checked_at, state, detail, alert_since)
           VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, CASE WHEN %s = 'alert' THEN %s::timestamptz END)
           ON CONFLICT (control) DO UPDATE
              SET status = EXCLUDED.status, checked_at = EXCLUDED.checked_at,
                  state = CASE WHEN EXCLUDED.state = '{}'::jsonb THEN control_check.state
                               ELSE EXCLUDED.state END,
                  detail = EXCLUDED.detail,
                  alert_since = CASE WHEN EXCLUDED.status = 'alert'
                                     THEN COALESCE(control_check.alert_since, EXCLUDED.checked_at) END,
                  alerted_at = CASE WHEN EXCLUDED.status = 'ok' THEN NULL
                                    ELSE control_check.alerted_at END""",
        (control, status, now, json.dumps(state), json.dumps(detail, default=str), status, now))
    conn.commit()


def due_alerts(conn, now: datetime | None = None) -> list[dict[str, Any]]:
    """Controls in `alert` not announced within ALERT_EVERY_HOURS; marks them announced."""
    now = now or datetime.now(timezone.utc)
    rows = conn.execute(
        """UPDATE control_check SET alerted_at = %s
            WHERE status = 'alert'
              AND (alerted_at IS NULL OR alerted_at < %s - %s * interval '1 hour')
        RETURNING control, detail""", (now, now, ALERT_EVERY_HOURS)).fetchall()
    conn.commit()
    return rows
