"""WP-137: who may apply derived again, with the call's own limits (Art. 22.5, a control restriction) as the evidence before the general
annexes' "Any legal entity, regardless of its place of establishment ... is eligible". No request, no model.

The report and the write derive from the same stored facts: nothing is changed before `who_apply.run`, so the calls the report names are
the ones `--yes` writes (the report of wp132_funding counted before its re-check of the stored facts was saved: 44 against 45). Only the
calls whose answer changes are written, so a second run writes nothing.

    python -m dgate.ops.wp137_who_apply            # report only
    python -m dgate.ops.wp137_who_apply --yes
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from .. import db, who_apply
from ..config import settings


def run(*, write: bool) -> list[str]:
    with db.connect(settings().dsn) as conn:
        changes: list[dict[str, Any]] = []
        counts = who_apply.run(conn, write=write, changes=changes)
    lines = [f"who may apply: {counts['changed']} calls change{' (written)' if write else ''}; research answer only: {counts['research_changed']}"]
    for c in changes:
        (b_who, _, b_ev), (a_who, _, a_ev) = c["before"], c["after"]
        lines.append(f"  {c['id']} {c['topic'] or ''}: {b_who} -> {a_who}; evidence {(b_ev or '-')[:70]!r} -> {(a_ev or '-')[:70]!r}")
    return lines


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="wp137-who-apply", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write (default: report)")
    a = p.parse_args(argv)
    for line in run(write=a.yes):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
