"""Owner-run: remove a notice, a buyer's name or a funding call from the public site.

    python -m dgate.ops.suppress add --kind notice --source ted --native-id 123456-2026 \
        --reason personal_data --requested-at 2026-10-15 --decided-by "Owner" [--note ...] [--yes]
    python -m dgate.ops.suppress add --kind organisation --organisation 4711 ...
    python -m dgate.ops.suppress add --kind document --source EDF --native-id 12345 ...
    python -m dgate.ops.suppress list [--all]
    python -m dgate.ops.suppress lift ID --by "Owner" [--note ...] [--yes]

Dry run unless --yes. What changes: one row in `suppression`; a database trigger then
flags the serving rows, and a re-ingest cannot clear the flag. The archive rows are not
touched. The site may show a cached copy for up to ten minutes (CSV export cache and the
page cache); the API's list cache is a minute. Nothing needs a restart.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Any

from .. import db
from ..config import settings

KINDS = ("notice", "organisation", "document")


def _when(text: str) -> datetime:
    value = datetime.fromisoformat(text)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def affected(conn, kind: str, source: str | None, native_id: str | None,
             organisation: int | None) -> int:
    """How many serving rows the entry flags now (0 for a notice not yet ingested)."""
    if kind == "notice":
        sql, args = ("SELECT count(*) AS n FROM opportunity o JOIN source s ON s.id = o.source_id "
                     "WHERE s.code = %s AND o.native_id = %s"), (source, native_id)
    elif kind == "organisation":
        sql, args = "SELECT count(*) AS n FROM opportunity WHERE buyer_org_id = %s", (organisation,)
    else:
        sql, args = ("SELECT count(*) AS n FROM call c JOIN programme p ON p.id = c.programme_id "
                     "WHERE p.code = %s AND c.native_id = %s"), (source, native_id)
    return conn.execute(sql, args).fetchone()["n"]


def add(conn, *, kind: str, source: str | None, native_id: str | None,
        organisation: int | None, reason: str, requested_at: datetime, decided_by: str,
        note: str = "") -> int:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    row = conn.execute(
        """INSERT INTO suppression (kind, source_code, native_id, organisation_id, reason,
                                    requested_at, decided_by, note)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (kind, source, native_id, organisation, reason, requested_at, decided_by, note),
    ).fetchone()
    return row["id"]


def lift(conn, entry_id: int, *, by: str, note: str = "") -> bool:
    got = conn.execute(
        "UPDATE suppression SET lifted_at = now(), lifted_by = %s, lifted_note = %s "
        "WHERE id = %s AND lifted_at IS NULL RETURNING id", (by, note, entry_id)).fetchone()
    return got is not None


def listing(conn, *, include_lifted: bool) -> list[dict[str, Any]]:
    where = "" if include_lifted else "WHERE lifted_at IS NULL"
    return conn.execute(f"SELECT * FROM suppression {where} ORDER BY id").fetchall()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dgate.ops.suppress", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--kind", choices=KINDS, required=True)
    a.add_argument("--source", help="source code (notice) or programme code (document)")
    a.add_argument("--native-id")
    a.add_argument("--organisation", type=int)
    a.add_argument("--reason", required=True, help="code, lower case letters and underscores")
    a.add_argument("--requested-at", required=True, help="ISO date or time the request arrived")
    a.add_argument("--decided-by", required=True)
    a.add_argument("--note", default="")
    a.add_argument("--yes", action="store_true", help="write (the default is a dry run)")
    li = sub.add_parser("list")
    li.add_argument("--all", action="store_true", help="include lifted entries")
    lf = sub.add_parser("lift")
    lf.add_argument("id", type=int)
    lf.add_argument("--by", required=True)
    lf.add_argument("--note", default="")
    lf.add_argument("--yes", action="store_true")
    args = p.parse_args(argv)

    with db.connect(settings().dsn) as conn:
        if args.cmd == "list":
            for r in listing(conn, include_lifted=args.all):
                state = "active" if r["lifted_at"] is None else f"lifted {r['lifted_at']:%Y-%m-%d}"
                subject = (f"org {r['organisation_id']}" if r["kind"] == "organisation"
                           else f"{r['source_code']}/{r['native_id']}")
                print(f"{r['id']:>5}  {r['kind']:<12} {subject:<40} {r['reason']:<20} "
                      f"requested {r['requested_at']:%Y-%m-%d} by {r['decided_by']}  [{state}]")
            return 0
        if args.cmd == "lift":
            if not args.yes:
                print(f"dry run: would lift entry {args.id} (add --yes)")
                return 0
            ok = lift(conn, args.id, by=args.by, note=args.note)
            conn.commit()
            print("lifted" if ok else "no active entry with that id")
            return 0 if ok else 1
        if args.kind == "organisation":
            if not args.organisation:
                p.error("--organisation is required for kind organisation")
        elif not (args.source and args.native_id):
            p.error("--source and --native-id are required for kind notice and document")
        n = affected(conn, args.kind, args.source, args.native_id, args.organisation)
        print(f"{'would flag' if not args.yes else 'flags'} {n} serving row(s)"
              + (" (none held yet: the entry applies when it is first ingested)" if not n else ""))
        if not args.yes:
            print("dry run: nothing written (add --yes)")
            return 0
        try:
            entry = add(conn, kind=args.kind, source=args.source, native_id=args.native_id,
                        organisation=args.organisation, reason=args.reason,
                        requested_at=_when(args.requested_at), decided_by=args.decided_by,
                        note=args.note)
        except Exception as exc:  # noqa: BLE001 - say what the database refused
            conn.rollback()
            print(f"refused: {exc}")
            return 1
        conn.commit()
        print(f"entry {entry} written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
