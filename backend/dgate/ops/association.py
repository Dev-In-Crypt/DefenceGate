"""Operator-run: an association's licence and members (WP-158, docs/verification/features/wp158-selfcheck.md).

    python -m dgate.ops.association                                   report: every association
    python -m dgate.ops.association --create NAME --display-name "Cluster X" --until 2027-10-31 --reason "agreement ref" [--yes]
                                                                      create it, licensed from now to that day
    python -m dgate.ops.association --association NAME                report: licence, seats, digest opt-ins
    python -m dgate.ops.association --association NAME --add-member EMAIL [--admin] [--yes]
                                                                      add an existing account (--admin: as its admin)
    python -m dgate.ops.association --association NAME --revoke EMAIL [--yes]   remove that member
    python -m dgate.ops.association --association NAME --revoke [--yes]         withdraw the licence
    python -m dgate.ops.association --association NAME --license --until DATE --reason TEXT [--yes]
                                                                      grant it again, or move its end date
    python -m dgate.ops.association --association NAME --reports N [--yes]   WP-162: the yearly pool of supplier reports
                                                                      for all its members (0-1000; "none": no pool)

NAME is the operator's key (lower case, digits, hyphens); the display name is what members see in the mail's sender and
heading. A member's account gets the Pro features and the admin's the Team features while the licence holds
(dgate/associations.py); at most `seat_cap` (50) members, the admin counted. Report by default; every change is written to
the accounts security log (account ids, never an address). Only accounts that exist can be added: the module never stores
an address of its own.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from .. import db
from ..accounts import _audit, canonical_email, clean_report_name
from ..config import settings

_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,59}$")
DISPLAY_MAX = 80


def get(conn, name: str) -> dict[str, Any] | None:
    return conn.execute(
        "SELECT a.*, (SELECT count(*) FROM association_member m WHERE m.association_id = a.id) AS members, "
        "(SELECT count(*) FROM association_member m WHERE m.association_id = a.id AND m.digest) AS digest "
        "FROM association a WHERE a.name = %s", (name,)).fetchone()


def account(conn, email: str) -> dict[str, Any] | None:
    canonical, _ = canonical_email(email)
    return conn.execute(
        "SELECT u.id, m.association_id FROM app_user u LEFT JOIN association_member m ON m.account_id = u.id "
        "WHERE u.email_canonical = %s", (canonical,)).fetchone()


def create(conn, name: str, display_name: str, until: date, reason: str) -> dict[str, Any]:
    row = conn.execute("INSERT INTO association (name, display_name, licensed_at, licensed_until, licence_reason) "
                       "VALUES (%s, %s, now(), %s, %s) ON CONFLICT (name) DO NOTHING RETURNING id",
                       (name, display_name, _end(until), reason)).fetchone()
    if not row:
        raise ValueError("an association with that name exists")
    _audit("association_created", None, association=row["id"])
    return row


def add_member(conn, assoc: dict[str, Any], account_id: Any, admin: bool = False) -> str:
    """Add the account (or make it the admin). Returns what happened; raises ValueError when it may not."""
    held = conn.execute("SELECT association_id FROM association_member WHERE account_id = %s", (account_id,)).fetchone()
    if held and held["association_id"] != assoc["id"]:
        raise ValueError("the account is a member of another association")
    if not held:
        # The cap is checked under a lock on the association row: two operators adding at once cannot pass it.
        conn.execute("SELECT 1 FROM association WHERE id = %s FOR UPDATE", (assoc["id"],))
        used = conn.execute("SELECT count(*) AS n FROM association_member WHERE association_id = %s",
                            (assoc["id"],)).fetchone()["n"]
        if used >= assoc["seat_cap"]:
            raise ValueError(f"every seat is taken ({used} of {assoc['seat_cap']})")
        conn.execute("INSERT INTO association_member (account_id, association_id) VALUES (%s, %s)",
                     (account_id, assoc["id"]))
        _audit("association_member_added", account_id, association=assoc["id"])
    if admin and assoc["admin_id"] != account_id:
        conn.execute("UPDATE association SET admin_id = %s WHERE id = %s", (account_id, assoc["id"]))
        _audit("association_admin_set", account_id, association=assoc["id"])
        return "added as admin" if not held else "made admin"
    return "added" if not held else "already a member"


def remove_member(conn, assoc: dict[str, Any], account_id: Any) -> bool:
    row = conn.execute("DELETE FROM association_member WHERE account_id = %s AND association_id = %s RETURNING account_id",
                       (account_id, assoc["id"])).fetchone()
    if row:
        conn.execute("UPDATE association SET admin_id = NULL WHERE id = %s AND admin_id = %s", (assoc["id"], account_id))
        _audit("association_member_removed", account_id, association=assoc["id"])
    return row is not None


def _end(day: date) -> datetime:
    """The licence runs to the end of its last day (UTC)."""
    return datetime.combine(day + timedelta(days=1), time(0), tzinfo=timezone.utc)


def set_licence(conn, assoc: dict[str, Any], on: bool, until: date | None = None, reason: str | None = None) -> bool:
    """Withdraw the licence, or grant it (again) to `until` with a reason. False when nothing changed."""
    if on:
        row = conn.execute(
            "UPDATE association SET licensed_at = COALESCE(licensed_at, now()), licensed_until = %s, licence_reason = %s "
            "WHERE id = %s AND (licensed_at IS NULL OR licensed_until IS DISTINCT FROM %s OR licence_reason IS DISTINCT FROM %s) "
            "RETURNING id", (_end(until), reason, assoc["id"], _end(until), reason)).fetchone()
    else:
        row = conn.execute("UPDATE association SET licensed_at = NULL, licensed_until = NULL, licence_reason = NULL "
                           "WHERE id = %s AND licensed_at IS NOT NULL RETURNING id", (assoc["id"],)).fetchone()
    if row:
        _audit("association_licence_granted" if on else "association_licence_withdrawn", None, association=assoc["id"])
    return row is not None


def _report(a: dict[str, Any]) -> str:
    licence = (f"since {a['licensed_at']:%Y-%m-%d} until {a['licensed_until']:%Y-%m-%d}"
               + (" (ended)" if a["licensed_until"] <= datetime.now(timezone.utc) else "") if a["licensed_at"] else "none")
    return (f"{a['name']} ({a['display_name']}): licence {licence}, "
            f"{a['members']} of {a['seat_cap']} seats, admin {'set' if a['admin_id'] else 'none'}, {a['digest']} digest opt-in(s), "
            f"supplier reports a year: {'no pool' if a.get('sell_reports_per_year') is None else a['sell_reports_per_year']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m dgate.ops.association", description=__doc__.split("\n")[0])
    p.add_argument("--create", metavar="NAME", help="create an association, licensed from now (with --display-name)")
    p.add_argument("--display-name", help="the name members see in the mail")
    p.add_argument("--association", metavar="NAME", help="the association to report on or change")
    p.add_argument("--add-member", metavar="EMAIL", help="add an existing account")
    p.add_argument("--admin", action="store_true", help="with --add-member: as the association's admin (Team features)")
    p.add_argument("--revoke", metavar="EMAIL", nargs="?", const="", help="remove that member; without one, withdraw the licence")
    p.add_argument("--license", action="store_true", help="grant the licence again, or move its end date (with --until, --reason)")
    p.add_argument("--until", type=date.fromisoformat, metavar="YYYY-MM-DD", help="the licence's last day (with --create, --license)")
    p.add_argument("--reason", help="the reference of the agreement (with --create, --license), at most 200 characters")
    p.add_argument("--reports", metavar="N", help="WP-162: supplier reports a calendar year for all members; 'none': no pool")
    p.add_argument("--yes", action="store_true", help="make the change (default: report only)")
    a = p.parse_args(argv)
    email = a.add_member or a.revoke or None
    if email:
        try:
            canonical_email(email)
        except ValueError:
            print("not an e-mail address", file=sys.stderr)
            return 2
    reason = " ".join((a.reason or "").split())
    if (a.create or a.license) and (not a.until or a.until < date.today() or not reason or len(reason) > 200):
        print("--create and --license need --until (a day from today) and --reason (1-200 characters)", file=sys.stderr)
        return 2
    with db.connect(settings().dsn) as conn:
        if a.create:
            display = clean_report_name(a.display_name or "")
            if not _NAME.match(a.create) or not display or len(display) > DISPLAY_MAX:
                print("NAME is 2-60 of a-z, 0-9 and hyphens; --display-name is 1-80 characters", file=sys.stderr)
                return 2
            if get(conn, a.create):
                print("an association with that name exists")
                return 1
            if not a.yes:
                print(f"dry run: would create {a.create} ({display}), licensed from now until {a.until} (add --yes)")
                return 0
            create(conn, a.create, display, a.until, reason)
            conn.commit()
            print(_report(get(conn, a.create)))
            return 0
        if not a.association:
            for row in conn.execute("SELECT name FROM association ORDER BY name").fetchall():
                print(_report(get(conn, row["name"])))
            return 0
        assoc = get(conn, a.association)
        if not assoc:
            print("no association with that name")
            return 1
        print(_report(assoc))
        if a.reports is not None:
            pool = None if a.reports == "none" else int(a.reports) if a.reports.isdigit() and int(a.reports) <= 1000 else -1
            if pool == -1:
                print("--reports is a number from 0 to 1000, or none", file=sys.stderr)
                return 2
            if not a.yes:
                print(f"dry run: would set the yearly pool of supplier reports to {a.reports} (add --yes)")
                return 0
            conn.execute("UPDATE association SET sell_reports_per_year = %s WHERE id = %s", (pool, assoc["id"]))
            _audit("association_report_pool_set", None, association=assoc["id"], pool=a.reports)
            conn.commit()
            print(_report(get(conn, a.association)))
            return 0
        if not (email or a.revoke == "" or a.license):
            return 0
        user = account(conn, email) if email else None
        if email and not user:
            print("no account with that address")
            return 1
        action = ("add the account" + (" as admin" if a.admin else "") if a.add_member else
                  f"remove account {user['id']}" if a.revoke else
                  "withdraw the licence" if a.revoke == "" else "grant the licence")
        if not a.yes:
            print(f"dry run: would {action} (add --yes)")
            return 0
        try:
            if a.add_member:
                print(f"account {user['id']}: {add_member(conn, assoc, user['id'], a.admin)}")
            elif a.revoke:
                print("removed" if remove_member(conn, assoc, user["id"]) else "nothing to remove: not a member")
            else:
                on = a.license and a.revoke is None
                print(("licence " + ("granted" if on else "withdrawn")) if set_licence(conn, assoc, on, a.until, reason)
                      else "nothing to change: already so")
        except ValueError as exc:
            conn.rollback()
            print(str(exc))
            return 1
        conn.commit()
        print(_report(get(conn, a.association)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
