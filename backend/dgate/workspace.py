"""Team workspace (Team, Consultant) and client profiles (Consultant): WP-157, migration 0149.

A workspace has one owner and up to `billing.seat_limit` users, the owner included. Its members have the owner's plan
(`billing.plan_of`, through the membership `accounts.current` joins) and see one another's saved searches, shortlist (status
and note) and follows: a member's rows carry the workspace while it is a member (`accounts.shared_scope`). Saved searches are
changed by their author only (the alerts are the author's); the shortlist and the follows by any member. Leaving, a removal or
the end of the workspace takes the member's rows back to it alone.

Client profiles (Consultant, `billing.client_limit`): a company name, its country, the CPV codes it sells under and a note,
in the workspace; a saved search or a shortlist entry can belong to one (`client_id`), and a company report can carry the
client's name (competition.open_report).

Invitations, built to docs/SECURITY_REQUIREMENTS.md like the account links (A2): the owner types an address, the mail carries
a 256-bit random token of which the database holds only the SHA-256; it works once, for 7 days, and only for a signed-in
account whose address is the one invited (a forwarded link is no use to anyone else). The answer is the same whether or not
the address has an account. At most INVITES_PER_DAY invitations a day per workspace and one mail an hour to one address.
O1: every query is scoped in SQL by the workspace of the authenticated account; another workspace's member, invitation or
client is a 404. O2: ids are UUIDs. Accounts and their mails stay closed while `accounts.accounts_problem` says so.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import Response
from pydantic import Field

from . import billing
from .accounts import (
    _CONTROL,
    NOTE_MAX,
    OK,
    AccountError,
    _address,
    _audit,
    _Body,
    _hash,
    _open,
    _secret,
    current,
    get_conn,
    internal_only,
    no_store,
)
from .config import settings
from .ops import mailer

INVITE_TTL = timedelta(days=7)
INVITES_PER_DAY = 20              # per workspace
RESEND_AFTER = timedelta(hours=1)  # one invitation mail an hour to one address
CLIENT_NAME_MAX = 120
MAX_CPV = 20

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_CPV = re.compile(r"^[0-9]{2,8}$")
_COUNTRY = re.compile(r"^[A-Z]{2}$")

router = APIRouter(prefix="/v1/account", dependencies=[Depends(internal_only), Depends(no_store)])

INVITE_MAIL = ("You are invited to a DefenceGate team",
               "A DefenceGate account invited this address to its team workspace. Members share that account's plan, "
               "saved searches, shortlist and follows.\n\n"
               "To join, sign in to DefenceGate with this address (or create an account with it), then open this link. "
               "It works once and expires in 7 days:\n\n{link}\n\n"
               "If you do not want to join, ignore this message. Nothing happens without you.")


# ------------------------------------------------------------------ helpers
def _text(raw: str, limit: int) -> str:
    """Plain text: control and direction characters out, spaces collapsed, cut to `limit`."""
    return " ".join(_CONTROL.sub(" ", raw).split())[:limit]


def _owner(user: dict[str, Any]) -> Any:
    """The account's workspace when it owns it, or 403."""
    if not user.get("ws_id") or user.get("ws_role") != "owner":
        raise AccountError(403, "owner_only", "only the owner of the workspace can do this")
    return user["ws_id"]


def _create(conn, user: dict[str, Any]) -> Any:
    """A workspace owned by this account; its rows join it."""
    ws = conn.execute("INSERT INTO workspace (owner_id) VALUES (%s) RETURNING id", (user["id"],)).fetchone()["id"]
    conn.execute("INSERT INTO workspace_member (workspace_id, user_id, role) VALUES (%s, %s, 'owner')", (ws, user["id"]))
    _share(conn, ws, user["id"])
    _audit("workspace_created", user["id"], workspace=ws)
    return ws


def _share(conn, ws: Any, uid: Any) -> None:
    for table in ("app_saved_search", "app_shortlist", "app_follow"):
        conn.execute(f"UPDATE {table} SET workspace_id = %s WHERE owner_id = %s", (ws, uid))


def _detach(conn, ws: Any, uid: Any) -> bool:
    """A member out of the workspace, with its rows (and off the workspace's clients)."""
    gone = conn.execute("DELETE FROM workspace_member WHERE workspace_id = %s AND user_id = %s AND role = 'member' "
                        "RETURNING 1", (ws, uid)).fetchone()
    if gone:
        for table in ("app_saved_search", "app_shortlist"):
            conn.execute(f"UPDATE {table} SET workspace_id = NULL, client_id = NULL "
                         "WHERE owner_id = %s AND workspace_id = %s", (uid, ws))
        conn.execute("UPDATE app_follow SET workspace_id = NULL WHERE owner_id = %s AND workspace_id = %s", (uid, ws))
    return gone is not None


def client_id(conn, user: dict[str, Any], raw: str) -> str:
    """The id of a client profile of the account's workspace, for a plan that has client profiles; 404 for anything else."""
    billing.require(user, "client_profiles")
    if not user.get("ws_id") or not _UUID.match(raw or "") or not conn.execute(
            "SELECT 1 FROM app_client WHERE id = %s AND workspace_id = %s", (raw, user["ws_id"])).fetchone():
        raise AccountError(404, "not_found", "no such client")
    return raw


def _prune(conn) -> None:
    conn.execute("DELETE FROM workspace_invite WHERE expires_at < now() - interval '1 day' "
                 "OR used_at < now() - interval '1 day'")


def export_rows(conn, user: dict[str, Any]) -> dict[str, Any] | None:
    """For the account export (Art. 15/20): the membership; for the owner the open invitations and the client profiles."""
    if not user.get("ws_id"):
        return None
    m = conn.execute("SELECT role, joined_at FROM workspace_member WHERE user_id = %s", (user["id"],)).fetchone()
    out: dict[str, Any] = {"role": m["role"], "joinedAt": m["joined_at"]}
    if m["role"] == "owner":
        out["invitations"] = [{"email": r["email_display"], "createdAt": r["created_at"], "expiresAt": r["expires_at"],
                               "usedAt": r["used_at"]} for r in conn.execute(
            "SELECT * FROM workspace_invite WHERE workspace_id = %s ORDER BY created_at LIMIT 100", (user["ws_id"],))]
        out["clients"] = [_client_out(r) for r in conn.execute(
            "SELECT * FROM app_client WHERE workspace_id = %s ORDER BY created_at LIMIT 100", (user["ws_id"],))]
    return out


# ------------------------------------------------------------------ the workspace
@router.get("/workspace")
def get_workspace(conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    ws = user.get("ws_id")
    if not ws:
        return {"workspace": None, "canCreate": billing.may(user, "team_workspace"), "seats": billing.seat_limit(user)}
    owner = user.get("ws_role") == "owner"
    _prune(conn)
    members = conn.execute(
        "SELECT u.id, u.email_display, m.role, m.joined_at FROM workspace_member m JOIN app_user u ON u.id = m.user_id "
        "WHERE m.workspace_id = %s ORDER BY m.role = 'owner' DESC, m.joined_at", (ws,)).fetchall()
    invites = conn.execute(
        "SELECT id, email_display, created_at, expires_at FROM workspace_invite WHERE workspace_id = %s "
        "AND used_at IS NULL AND expires_at > now() ORDER BY created_at", (ws,)).fetchall() if owner else []
    return {"workspace": {
        "id": str(ws), "role": user["ws_role"],
        # the sharing works while the plan in force has the workspace (the owner's, for a member)
        "active": billing.may(user, "team_workspace"),
        "seats": billing.seat_limit(user),
        "members": [{"id": str(r["id"]), "email": r["email_display"], "role": r["role"], "joinedAt": r["joined_at"],
                     "me": r["id"] == user["id"]} for r in members],
        "invites": [{"id": str(r["id"]), "email": r["email_display"], "createdAt": r["created_at"],
                     "expiresAt": r["expires_at"]} for r in invites],
    }, "canCreate": False, "seats": billing.seat_limit(user)}


@router.post("/workspace", status_code=201)
def create_workspace(conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    billing.require(user, "team_workspace")
    if user.get("ws_id"):
        raise AccountError(409, "in_workspace", "this account is in a workspace already")
    return {"id": str(_create(conn, user))}


@router.delete("/workspace", status_code=204)
def dissolve_workspace(conn=Depends(get_conn), user=Depends(current)) -> Response:
    """The owner ends the workspace: members, invitations and client profiles go; every member keeps its own rows (the
    foreign keys set their workspace and client to NULL)."""
    ws = _owner(user)
    conn.execute("DELETE FROM workspace WHERE id = %s AND owner_id = %s", (ws, user["id"]))
    _audit("workspace_dissolved", user["id"], workspace=ws)
    return Response(status_code=204)


class InviteIn(_Body):
    email: str = Field(max_length=320)


@router.post("/workspace/invites", status_code=201)
def invite(body: InviteIn, background: BackgroundTasks, conn=Depends(get_conn),
           user=Depends(current)) -> dict[str, Any]:
    ws = _owner(user)
    billing.require(user, "team_workspace")
    _open()                                     # no mail relay, no notice for accounts: no invitation either
    canonical, display = _address(body.email)
    if canonical == user["email_canonical"]:
        raise AccountError(422, "invalid_email", "that is your own address")
    _prune(conn)
    conn.execute("SELECT 1 FROM workspace WHERE id = %s FOR UPDATE", (ws,))      # one invitation at a time per workspace
    if conn.execute("SELECT 1 FROM workspace_member m JOIN app_user u ON u.id = m.user_id "
                    "WHERE m.workspace_id = %s AND u.email_canonical = %s", (ws, canonical)).fetchone():
        raise AccountError(409, "already_member", "that address is a member already")
    counts = conn.execute(
        """SELECT (SELECT count(*) FROM workspace_member WHERE workspace_id = %(ws)s) AS members,
                  (SELECT count(*) FROM workspace_invite WHERE workspace_id = %(ws)s AND used_at IS NULL
                      AND expires_at > now() AND email_canonical <> %(c)s) AS pending,
                  (SELECT count(*) FROM workspace_invite WHERE workspace_id = %(ws)s
                      AND created_at > now() - interval '1 day') AS today,
                  (SELECT created_at > now() - %(resend)s::interval FROM workspace_invite
                    WHERE workspace_id = %(ws)s AND email_canonical = %(c)s) AS recent""",
        {"ws": ws, "c": canonical, "resend": RESEND_AFTER}).fetchone()
    seats = billing.seat_limit(user)
    if counts["members"] + counts["pending"] >= seats:
        raise AccountError(409, "seats_full", f"the workspace has {seats} places, members and open invitations together")
    if counts["today"] >= INVITES_PER_DAY or counts["recent"]:
        raise AccountError(429, "rate_limited", "too many invitations: try again later", {"Retry-After": "3600"})
    token = _secret()
    row = conn.execute(
        """INSERT INTO workspace_invite (workspace_id, email_canonical, email_display, token_hash, expires_at)
           VALUES (%s, %s, %s, %s, now() + %s::interval)
           ON CONFLICT (workspace_id, email_canonical) DO UPDATE SET email_display = EXCLUDED.email_display,
               token_hash = EXCLUDED.token_hash, created_at = now(), expires_at = EXCLUDED.expires_at, used_at = NULL
           RETURNING id, email_display, created_at, expires_at""",
        (ws, canonical, display, _hash(token), INVITE_TTL)).fetchone()
    subject, text = INVITE_MAIL
    link = f"{settings().site_url.rstrip('/')}/app/team/join?token={token}"
    background.add_task(lambda: mailer.send_mail(display, subject, text.format(link=link) + "\n"))
    _audit("workspace_invite", user["id"], workspace=ws, invite=row["id"])
    return {"id": str(row["id"]), "email": row["email_display"], "createdAt": row["created_at"],
            "expiresAt": row["expires_at"]}


@router.delete("/workspace/invites/{invite_id}", status_code=204)
def cancel_invite(invite_id: str, conn=Depends(get_conn), user=Depends(current)) -> Response:
    ws = _owner(user)
    if not _UUID.match(invite_id) or not conn.execute(
            "DELETE FROM workspace_invite WHERE id = %s AND workspace_id = %s RETURNING 1", (invite_id, ws)).fetchone():
        raise AccountError(404, "not_found", "no such invitation")
    return Response(status_code=204)


class JoinIn(_Body):
    token: str = Field(max_length=64)


@router.post("/workspace/join")
def join(body: JoinIn, conn=Depends(get_conn), user=Depends(current)) -> dict[str, bool]:
    """The invited account accepts. The token is spent only when the account joins."""
    bad = AccountError(400, "invalid_or_expired", "this invitation is not valid any more: ask for a new one")
    if not _TOKEN.match(body.token or ""):
        raise bad
    inv = conn.execute(
        "SELECT i.id, i.workspace_id, i.email_canonical, w.owner_id FROM workspace_invite i "
        "JOIN workspace w ON w.id = i.workspace_id WHERE i.token_hash = %s AND i.used_at IS NULL "
        "AND i.expires_at > now() FOR UPDATE OF i, w", (_hash(body.token),)).fetchone()
    if not inv:
        raise bad
    if inv["email_canonical"] != user["email_canonical"]:
        raise AccountError(403, "wrong_account", "this invitation is for another address: sign in with the address it was sent to")
    if user.get("ws_id"):
        raise AccountError(409, "in_workspace", "this account is in a workspace already: leave it first")
    sub = conn.execute("SELECT plan AS sub_plan, status AS sub_status, current_period_end AS sub_period_end "
                       "FROM billing_subscription WHERE account_id = %s", (inv["owner_id"],)).fetchone()
    owner = dict(sub or {})
    if not billing.may(owner, "team_workspace"):
        raise AccountError(402, "plan_required", "the team's plan has no workspace at the moment: ask its owner")
    members = conn.execute("SELECT count(*) AS n FROM workspace_member WHERE workspace_id = %s",
                           (inv["workspace_id"],)).fetchone()["n"]
    if members >= billing.seat_limit(owner):
        raise AccountError(409, "seats_full", "the workspace has no place left: ask its owner")
    conn.execute("UPDATE workspace_invite SET used_at = now() WHERE id = %s", (inv["id"],))
    conn.execute("INSERT INTO workspace_member (workspace_id, user_id, role) VALUES (%s, %s, 'member')",
                 (inv["workspace_id"], user["id"]))
    _share(conn, inv["workspace_id"], user["id"])
    _audit("workspace_joined", user["id"], workspace=inv["workspace_id"])
    return OK


@router.post("/workspace/leave", status_code=204)
def leave(conn=Depends(get_conn), user=Depends(current)) -> Response:
    if not user.get("ws_id"):
        raise AccountError(404, "not_found", "this account is in no workspace")
    if user.get("ws_role") == "owner":
        raise AccountError(409, "owner_cannot_leave", "the owner ends the workspace instead")
    _detach(conn, user["ws_id"], user["id"])
    _audit("workspace_left", user["id"], workspace=user["ws_id"])
    return Response(status_code=204)


@router.delete("/workspace/members/{member_id}", status_code=204)
def remove_member(member_id: str, conn=Depends(get_conn), user=Depends(current)) -> Response:
    ws = _owner(user)
    if not _UUID.match(member_id) or not _detach(conn, ws, member_id):
        raise AccountError(404, "not_found", "no such member")
    _audit("workspace_removed", user["id"], workspace=ws, member=member_id)
    return Response(status_code=204)


# ------------------------------------------------------------------ client profiles
class ClientIn(_Body):
    name: str = Field(min_length=1, max_length=CLIENT_NAME_MAX * 2)
    country: str | None = Field(None, max_length=2)
    cpvCodes: list[str] = Field(default_factory=list, max_length=MAX_CPV)
    note: str = Field("", max_length=NOTE_MAX)


class ClientPatch(_Body):
    name: str | None = Field(None, min_length=1, max_length=CLIENT_NAME_MAX * 2)
    country: str | None = Field(None, max_length=2)
    cpvCodes: list[str] | None = Field(None, max_length=MAX_CPV)
    note: str | None = Field(None, max_length=NOTE_MAX)


def _client_out(r: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(r["id"]), "name": r["name"], "country": r["country"], "cpvCodes": list(r["cpv_codes"]),
            "note": r["note"], "createdAt": r["created_at"], "updatedAt": r["updated_at"]}


def _client_values(fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if fields.get("name") is not None:
        out["name"] = _text(fields["name"], CLIENT_NAME_MAX)
        if not out["name"]:
            raise AccountError(422, "invalid_name", "give the client a name")
    if "country" in fields:
        country = (fields["country"] or "").strip().upper() or None
        if country and not _COUNTRY.match(country):
            raise AccountError(422, "invalid_country", "countries are two-letter codes")
        out["country"] = country
    if fields.get("cpvCodes") is not None:
        codes = list(dict.fromkeys(c.strip() for c in fields["cpvCodes"]))
        if not all(_CPV.match(c) for c in codes):
            raise AccountError(422, "invalid_cpv", "CPV codes are 2 to 8 digits")
        out["cpv_codes"] = codes
    if fields.get("note") is not None:
        out["note"] = fields["note"].replace("\x00", "").strip()
    return out


def _owned_client(conn, user: dict[str, Any], cid: str) -> None:
    if not user.get("ws_id") or not _UUID.match(cid) or not conn.execute(
            "SELECT 1 FROM app_client WHERE id = %s AND workspace_id = %s", (cid, user["ws_id"])).fetchone():
        raise AccountError(404, "not_found", "no such client")


@router.get("/clients")
def list_clients(conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    rows = conn.execute("SELECT * FROM app_client WHERE workspace_id = %s ORDER BY lower(name), id LIMIT 100",
                        (user.get("ws_id"),)).fetchall() if user.get("ws_id") else []
    return {"items": [_client_out(r) for r in rows], "limit": billing.client_limit(user),
            "allowed": billing.may(user, "client_profiles")}


@router.post("/clients", status_code=201)
def create_client(body: ClientIn, conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    """A client profile; the first one makes the account's workspace when it has none."""
    billing.require(user, "client_profiles")
    values = _client_values(body.model_dump())
    ws = user.get("ws_id") or _create(conn, user)
    conn.execute("SELECT 1 FROM workspace WHERE id = %s FOR UPDATE", (ws,))
    n = conn.execute("SELECT count(*) AS n FROM app_client WHERE workspace_id = %s", (ws,)).fetchone()["n"]
    limit = billing.client_limit(user)
    if n >= limit:
        raise AccountError(409, "limit_reached", f"at most {limit} client profiles on your plan")
    row = conn.execute(
        "INSERT INTO app_client (workspace_id, name, country, cpv_codes, note) VALUES (%s, %s, %s, %s, %s) RETURNING *",
        (ws, values["name"], values.get("country"), values.get("cpv_codes", []), values.get("note", ""))).fetchone()
    return _client_out(row)


@router.patch("/clients/{cid}")
def patch_client(cid: str, body: ClientPatch, conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    _owned_client(conn, user, cid)
    billing.require(user, "client_profiles")
    values = _client_values(body.model_dump(exclude_unset=True))
    sets = ", ".join(f"{k} = %s" for k in values)
    row = conn.execute(f"UPDATE app_client SET {sets + ', ' if sets else ''}updated_at = now() "
                       "WHERE id = %s AND workspace_id = %s RETURNING *",
                       (*values.values(), cid, user["ws_id"])).fetchone()
    return _client_out(row)


@router.delete("/clients/{cid}", status_code=204)
def delete_client(cid: str, conn=Depends(get_conn), user=Depends(current)) -> Response:
    """Removed with nothing else: its searches and shortlist entries stay, without a client."""
    _owned_client(conn, user, cid)
    conn.execute("DELETE FROM app_client WHERE id = %s AND workspace_id = %s", (cid, user["ws_id"]))
    return Response(status_code=204)
