"""The cluster licence and the co-branded weekly digest (WP-158, owner, 30 October 2026).

An association (a cluster, a trade body) holds a licence agreed with us outside the plans. Only the operator module
`python -m dgate.ops.association` creates one, adds and removes its members (accounts that exist, at most `seat_cap`, 50)
and withdraws or renews its licence, always with an end date and a reason (migration 0150, SECURITY_REQUIREMENTS D3: a
grant made by hand is dated, reasoned and expiring). While the licence holds, and until its end date:

  - a member's account has the Pro features and the admin's account the Team features: the plan comes through
    `billing.plan_in_force` (`accounts.ASSOC_PLAN_SQL` reads it with the session), so every gate decides as for a paid
    plan, and while no plan is on sale nobody is refused anything anyway (WP-124);
  - a member may opt in to the weekly digest by e-mail (`/v1/account/association`, the account page /app/association): the
    public issue of the last complete week (`weekly_digest.get_digest`, for the member's country and CPV codes), plain
    text with the HTML form of `mailer.to_html`, sent under the association's name ("<name> via DefenceGate", the address
    ours) with its name in the heading, and a link that stops it without signing in (`unsubscribe_token`, which can do
    nothing else). The worker sends it (`run_digests`), and only while accounts are open (DGATE_ACCOUNTS_OPEN=1) and the
    relay is ready.

What is held: which account belongs to which association, since when, its digest choice and the last week mailed. The
admin sees how many seats are used, never who holds them.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .accounts import AccountError, _audit, current, get_conn, internal_only, no_store
from .config import settings

log = logging.getLogger("associations")

router = APIRouter(prefix="/v1/account", dependencies=[Depends(internal_only), Depends(no_store)])

SEAT_CAP = 50
MAX_MAILS_PER_RUN = 500          # an hourly job: a larger association is mailed over a few runs
SECTION_MAX = 10                 # items listed per section in the mail; the count is always the full one
CPV_MAX = 20

_MINE = """SELECT a.id, a.display_name, a.seat_cap, a.licensed_until, a.admin_id = m.account_id AS admin,
                  m.added_at, m.digest, m.digest_country, m.digest_cpv, m.digest_last_week,
                  (SELECT count(*) FROM association_member x WHERE x.association_id = a.id) AS members
             FROM association_member m JOIN association a ON a.id = m.association_id AND a.licensed_at IS NOT NULL AND a.licensed_until > now()
            WHERE m.account_id = %s"""


def _mine(conn, user: dict[str, Any]) -> dict[str, Any]:
    """The account's own membership of a licensed association (O1: scoped by the account id in SQL), or 404."""
    row = conn.execute(_MINE, (user["id"],)).fetchone()
    if not row:
        raise AccountError(404, "not_found", "this account is not a member of an association")
    return row


def _out(row: dict[str, Any]) -> dict[str, Any]:
    out = {"name": row["display_name"], "role": "admin" if row["admin"] else "member",
           "plan": "team" if row["admin"] else "pro", "memberSince": row["added_at"], "licensedUntil": row["licensed_until"],
           "digest": {"on": row["digest"], "country": row["digest_country"], "cpv": list(row["digest_cpv"]),
                      "lastWeek": row["digest_last_week"]}}
    if row["admin"]:
        out["seats"] = {"used": row["members"], "cap": row["seat_cap"]}     # counted, never named
    return out


@router.get("/association")
def get_association(conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    return _out(_mine(conn, user))


class DigestIn(BaseModel):
    on: bool
    country: str | None = Field(None, pattern=r"^[A-Za-z]{2}$")
    cpv: list[str] = Field(default_factory=list, max_length=CPV_MAX)


@router.put("/association/digest")
def set_digest(body: DigestIn, conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    _mine(conn, user)
    from .tenders import cpv_prefixes

    try:
        cpv = cpv_prefixes(",".join(c.strip() for c in body.cpv if c.strip()) or None)
    except HTTPException as exc:
        raise AccountError(422, "invalid_cpv", str(exc.detail)) from None
    conn.execute("UPDATE association_member SET digest = %s, digest_country = %s, digest_cpv = %s WHERE account_id = %s",
                 (body.on, body.country.upper() if body.country else None, cpv[:CPV_MAX], user["id"]))
    _audit("association_digest_on" if body.on else "association_digest_off", user["id"])
    return _out(_mine(conn, user))


class UnsubscribeIn(BaseModel):
    token: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.post("/association/unsubscribe")
def unsubscribe(body: UnsubscribeIn, conn=Depends(get_conn)) -> dict[str, Any]:
    """The link in a digest mail, without signing in: the token switches that account's digest off and does nothing
    else. The answer is the same for a token that matches nothing (it names no account)."""
    row = conn.execute("UPDATE association_member SET digest = false WHERE unsubscribe_token = %s RETURNING account_id",
                       (body.token,)).fetchone()
    if row:
        _audit("association_digest_unsubscribed", row["account_id"])
    return {"done": True}


def export_row(conn, account_id: Any) -> dict[str, Any] | None:
    """Art. 15/20: the membership as held (the export of accounts.export); the unsubscribe token is said to exist only."""
    row = conn.execute(
        "SELECT a.display_name, a.licensed_at IS NOT NULL AND a.licensed_until > now() AS licensed, a.admin_id = m.account_id AS admin, m.added_at, m.digest, m.digest_country, "
        "m.digest_cpv, m.digest_last_week FROM association_member m JOIN association a ON a.id = m.association_id "
        "WHERE m.account_id = %s", (account_id,)).fetchone()
    if not row:
        return None
    return {"association": row["display_name"], "licensed": row["licensed"],
            "role": "admin" if row["admin"] else "member", "memberSince": row["added_at"],
            "digest": {"on": row["digest"], "country": row["digest_country"], "cpv": list(row["digest_cpv"]),
                       "lastWeek": row["digest_last_week"]}, "unsubscribeLink": "exists (in each digest mail)"}


# ------------------------------------------------------------------ the digest mail

DUE_SQL = """
    SELECT m.account_id, m.digest_country, m.digest_cpv, m.unsubscribe_token, u.email_display, a.display_name
      FROM association_member m
      JOIN association a ON a.id = m.association_id AND a.licensed_at IS NOT NULL AND a.licensed_until > now()
      JOIN app_user u ON u.id = m.account_id
     WHERE m.digest AND m.digest_last_week IS DISTINCT FROM %s
     ORDER BY a.id, m.added_at
     LIMIT %s
"""


def _day(value: Any) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.strftime("%Y-%m-%d") if isinstance(value, datetime) else "no deadline stated"


def _section(title: str, count: int, items: list[dict[str, Any]], line) -> str:
    if not count:
        return ""
    lines = [line(i) for i in items[:SECTION_MAX]]
    more = count - len(lines)
    return f"{title}: {count}\n" + "\n".join(lines) + (f"\n  ... and {more} more" if more > 0 else "")


def render(issue: dict[str, Any], association: str, site: str, unsubscribe_url: str) -> tuple[str, str]:
    """(subject, plain text) of one digest mail: the association's name in the heading, the issue's counts and its first
    items per section, the link to the whole issue on the site and the link that stops the mail."""
    week, country, cpv = issue["week"], issue.get("country") or "", issue.get("cpv") or []
    c = issue["counts"]

    def tender(t: dict[str, Any]) -> str:
        meta = ", ".join(x for x in (t.get("buyerName"), t.get("country")) if x)
        return f"- {t['title']}\n  {meta} | deadline {_day(t.get('deadline'))}\n  {site}/tenders/{t['slug']}"

    def call(k: dict[str, Any]) -> str:
        meta = ", ".join(x for x in (k.get("funder"), k.get("funderCountry")) if x)
        return f"- {k['title']}\n  {meta} | deadline {_day(k.get('deadline'))}\n  {site}/funding/{k['slug']}"

    query = urlencode({k: v for k, v in (("country", country), ("cpv", ",".join(cpv))) if v})
    scope = ", ".join(x for x in ((f"country {country}" if country else "all countries"),
                                  (f"CPV {', '.join(cpv)}" if cpv else "")) if x)
    sections = [s for s in (
        _section("New defence tenders", c["tendersNew"], issue["tendersNew"], tender),
        _section("Amended tenders", c["tendersAmended"], issue["tendersAmended"], tender),
        _section("New funding calls", c["callsNew"], issue["callsNew"], call),
        _section("Funding calls that opened", c["callsOpened"], issue["callsOpened"], call),
        _section("Funding calls closing in the next two weeks", c["callsClosing"], issue["callsClosing"], call),
    ) if s]
    body = (
        f"{association}: the weekly digest of defence tenders and funding, week {week}\n"
        f"For the members of {association}, from DefenceGate ({scope}).\n\n"
        + ("\n\n".join(sections) if sections else "Nothing new this week for this selection.")
        + f"\n\nThe whole issue: {site}/digest/{week}" + (f"?{query}" if query else "")
        + "\n\nCheck the original notice before you act on any of these. DefenceGate is an information service, not an "
        "official source.\n"
        f"You get this mail as a member of {association}. Change it: {site}/app/association\n"
        f"Stop it: {unsubscribe_url}\n")
    return f"{association}: weekly defence digest, {week}", body


def run_digests(conn, now: datetime | None = None) -> dict[str, int]:
    """Send the last complete week's issue to every opted-in member not yet mailed it. Hourly in the worker; a failed
    send is not marked, so the next run tries again. Nothing at all while accounts are closed or the relay is not
    ready, and nothing before the daily digest job has stored the week (`digest_issue`)."""
    from . import weekly_digest
    from .ops import mailer

    result = {"mails": 0, "failed": 0, "issues": 0}
    if not settings().accounts_open or not mailer.ready():
        return result
    now = now or datetime.now(timezone.utc)
    week = weekly_digest.last_complete_week(now)
    if not conn.execute("SELECT 1 FROM digest_issue WHERE week = %s AND country = ''", (week,)).fetchone():
        return {**result, "waiting": 1}
    site = settings().site_url.rstrip("/")
    issues: dict[tuple[str, tuple[str, ...]], dict[str, Any] | None] = {}
    for row in conn.execute(DUE_SQL, (week, MAX_MAILS_PER_RUN)).fetchall():
        key = (row["digest_country"] or "", tuple(row["digest_cpv"]))
        if key not in issues:
            try:
                issues[key] = weekly_digest.get_digest(week=week, country=key[0] or None, cpv=",".join(key[1]) or None,
                                                       conn=conn, with_meta=False)
                result["issues"] += 1
            except Exception as exc:  # noqa: BLE001 - one selection that fails must not stop the others
                log.warning("association digest: issue %s skipped: %s", key, type(exc).__name__)
                conn.rollback()
                issues[key] = None
        issue = issues[key]
        if issue is None:
            continue
        name = row["display_name"]
        subject, body = render(issue, name, site, f"{site}/unsubscribe?token={row['unsubscribe_token']}")
        if not mailer.send_mail(row["email_display"], subject, body, sender_name=f"{name} via DefenceGate",
                                headers={"List-Unsubscribe": f"<{site}/unsubscribe?token={row['unsubscribe_token']}>"}):
            result["failed"] += 1
            continue
        conn.execute("UPDATE association_member SET digest_last_week = %s WHERE account_id = %s", (week, row["account_id"]))
        conn.commit()
        result["mails"] += 1
    return result
