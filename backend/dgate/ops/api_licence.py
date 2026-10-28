"""Operator-run: grant or withdraw an account's data API licence (WP-155, owner, 28 October 2026).

    python -m dgate.ops.api_licence --email X            report: the account, its licence, its keys
    python -m dgate.ops.api_licence --email X --yes      grant the licence
    python -m dgate.ops.api_licence --email X --revoke --yes   withdraw it

The licence is a contract outside the plans: no plan grants it, and only this module sets it
(`app_user.api_licensed_at`). With it, and with DGATE_API_KEYS_OPEN=1, the account may make keys; withdrawn, its keys
are refused at once (apikeys.authenticate) and listed as before, and granting it again lets them work again until they
expire or are revoked. Report by default; every change is written to the accounts security log (account id, never the
address).
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from .. import db
from ..accounts import _audit, canonical_email
from ..config import settings


def find(conn, email: str) -> dict[str, Any] | None:
    canonical, _ = canonical_email(email)
    return conn.execute(
        "SELECT u.id, u.api_licensed_at, (SELECT count(*) FROM api_key k WHERE k.owner_id = u.id AND k.revoked_at IS NULL "
        "AND k.expires_at > now()) AS keys FROM app_user u WHERE u.email_canonical = %s", (canonical,)).fetchone()


def apply(conn, account_id: Any, revoke: bool) -> bool:
    """Grant (or withdraw) the licence; False when it already was so."""
    row = conn.execute(
        "UPDATE app_user SET api_licensed_at = " + ("NULL" if revoke else "now()") + " WHERE id = %s AND "
        "api_licensed_at IS " + ("NOT NULL" if revoke else "NULL") + " RETURNING id", (account_id,)).fetchone()
    if row:
        _audit("api_licence_revoked" if revoke else "api_licence_granted", account_id)
    return row is not None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m dgate.ops.api_licence", description=__doc__.split("\n")[0])
    p.add_argument("--email", required=True, help="the account's e-mail address")
    p.add_argument("--revoke", action="store_true", help="withdraw the licence instead of granting it")
    p.add_argument("--yes", action="store_true", help="make the change (default: report only)")
    args = p.parse_args(argv)
    try:
        canonical_email(args.email)
    except ValueError:
        print("not an e-mail address", file=sys.stderr)
        return 2
    with db.connect(settings().dsn) as conn:
        user = find(conn, args.email)
        if not user:
            print("no account with that address")
            return 1
        print(f"account {user['id']}: licence {'since ' + user['api_licensed_at'].isoformat() if user['api_licensed_at'] else 'none'}, "
              f"{user['keys']} active key(s); keys open: {'yes' if settings().api_keys_open else 'no (DGATE_API_KEYS_OPEN)'}")
        action = "withdraw" if args.revoke else "grant"
        if not args.yes:
            print(f"dry run: would {action} the licence (add --yes)")
            return 0
        changed = apply(conn, user["id"], args.revoke)
        conn.commit()
        print(f"licence {'withdrawn' if args.revoke else 'granted'}" if changed else f"nothing to {action}: already so")
    return 0


if __name__ == "__main__":
    sys.exit(main())
