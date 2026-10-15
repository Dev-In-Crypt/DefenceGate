"""Owner-run request log: when a data-subject or removal request arrived and how it ended.

    python -m dgate.ops.data_request add --kind erasure --received-at 2026-10-15 [--note ...] [--yes]
    python -m dgate.ops.data_request list [--open]
    python -m dgate.ops.data_request close ID --status closed|refused [--note ...] [--yes]

Dry run unless --yes. Holds what the owner types and nothing else: do not type the
requester's name, address or message into the note. Rows are never deleted.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from .. import db
from ..config import settings

KINDS = ("access", "rectification", "erasure", "restriction", "objection", "portability",
         "removal", "other")


def _when(text: str) -> datetime:
    value = datetime.fromisoformat(text)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def add(conn, *, kind: str, received_at: datetime, note: str = "") -> int:
    return conn.execute(
        "INSERT INTO data_request (received_at, kind, handler_note) VALUES (%s, %s, %s) "
        "RETURNING id", (received_at, kind, note)).fetchone()["id"]


def close(conn, request_id: int, *, status: str, note: str | None = None) -> bool:
    got = conn.execute(
        "UPDATE data_request SET status = %s, closed_at = now(), "
        "handler_note = coalesce(%s, handler_note) WHERE id = %s AND status = 'open' RETURNING id",
        (status, note, request_id)).fetchone()
    return got is not None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dgate.ops.data_request", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--kind", choices=KINDS, required=True)
    a.add_argument("--received-at", required=True)
    a.add_argument("--note", default="")
    a.add_argument("--yes", action="store_true")
    li = sub.add_parser("list")
    li.add_argument("--open", action="store_true")
    c = sub.add_parser("close")
    c.add_argument("id", type=int)
    c.add_argument("--status", choices=("closed", "refused"), required=True)
    c.add_argument("--note")
    c.add_argument("--yes", action="store_true")
    args = p.parse_args(argv)

    with db.connect(settings().dsn) as conn:
        if args.cmd == "list":
            where = "WHERE status = 'open'" if args.open else ""
            for r in conn.execute(f"SELECT * FROM data_request {where} ORDER BY id").fetchall():
                closed = f"{r['closed_at']:%Y-%m-%d}" if r["closed_at"] else "-"
                print(f"{r['id']:>5}  {r['kind']:<14} received {r['received_at']:%Y-%m-%d}  "
                      f"{r['status']:<8} closed {closed}  {r['handler_note']}")
            return 0
        if not args.yes:
            print("dry run: nothing written (add --yes)")
            return 0
        if args.cmd == "add":
            new = add(conn, kind=args.kind, received_at=_when(args.received_at), note=args.note)
            conn.commit()
            print(f"request {new} logged")
            return 0
        ok = close(conn, args.id, status=args.status, note=args.note)
        conn.commit()
        print("closed" if ok else "no open request with that id")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
