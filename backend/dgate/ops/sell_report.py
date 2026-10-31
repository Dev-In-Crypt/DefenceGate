"""The admin's one-off "Who to sell to" report (WP-162): any company, never counted against a quota.

Read-only: the session is READ ONLY with a statement timeout, nothing is written, and the form (a JSON file of the request,
`sell_report.ReportIn`) is read from disk and never logged. The report is written as JSON to `--out` (or stdout); the page
renders it (web: `node scripts/sell-report-pdf.mjs <json> <pdf>` prints the same page to PDF).

    python -m dgate.ops.sell_report --org 406963-indra-sistemas-sa --out report.json
    python -m dgate.ops.sell_report --org 123-acme --cpv 35720000,35722000 --held ISO9001 --out report.json
    python -m dgate.ops.sell_report --form form.json --out report.json
    python -m dgate.ops.sell_report --sample --out sample.json          # the public sample as the site serves it

`--anonymous` gives the view of a visitor who is not signed in (no company named in section 3).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .. import db
from ..config import settings
from ..sell_report import DEMO, ReportIn, build


def run(inp: ReportIn, *, names: bool, sample: bool = False, dsn: str | None = None) -> dict:
    with db.connect(dsn or settings().dsn) as conn:
        conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        conn.execute("SET statement_timeout = '30s'")
        try:
            return build(conn, inp, names=names, sample=sample)
        finally:
            conn.rollback()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m dgate.ops.sell_report", description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--org", help="slug of a supplier or organisation (mode A)")
    src.add_argument("--form", type=Path, help="a JSON file of the form (mode B)")
    src.add_argument("--sample", action="store_true", help="the demo company of the public sample")
    ap.add_argument("--cpv", default="", help="comma-separated 8-digit CPV codes (mode A: instead of the codes it won)")
    ap.add_argument("--held", default="", help="comma-separated certificates and registrations held (ISO9001,RID,...)")
    ap.add_argument("--country", default=None)
    ap.add_argument("--anonymous", action="store_true", help="the view of a visitor who is not signed in")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)

    def split(s: str) -> list[str]:
        return [x.strip() for x in s.split(",") if x.strip()]

    if a.sample:
        inp = ReportIn(**DEMO)
    elif a.form:
        inp = ReportIn(**json.loads(a.form.read_text(encoding="utf-8")))
    else:
        inp = ReportIn(org=a.org, cpv=split(a.cpv), held=split(a.held), country=a.country)
    out = json.dumps(run(inp, names=not a.anonymous, sample=a.sample), default=str, ensure_ascii=False, indent=1)
    if a.out:
        a.out.write_text(out, encoding="utf-8")
        print(f"written {a.out} ({len(out)} characters)")
    else:
        sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
