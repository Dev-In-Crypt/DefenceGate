"""Read the eligibility of the EU calls from their call documents (dgate/eligibility.py).

    python -m dgate.ops.extract_eligibility                    # list what would be read, nothing is sent
    python -m dgate.ops.extract_eligibility --yes --limit 3    # extract the first 3 (open calls first)
    python -m dgate.ops.extract_eligibility --yes --url URL --force
    python -m dgate.ops.extract_eligibility --redact-stored [--yes]   # e-mail addresses in the kept texts

What is read: the call documents, once per topic (the model is told which topic the call is, since
one document covers many); for calls without one, the work programme's general annexes
(read once, shared by many calls) and each topic's own conditions text (WP-31). `--scope` narrows it.
Stops at the monthly cap (DGATE_LLM_MONTHLY_CAP_USD). A document that cannot be fetched or
answered is reported and skipped; the others go on.
"""

from __future__ import annotations

import argparse
import logging
import sys

from .. import db, eligibility, llm
from ..config import settings

log = logging.getLogger("extract_eligibility")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="extract-eligibility", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="fetch and ask (default: list only)")
    p.add_argument("--limit", type=int, default=0, help="at most this many documents")
    p.add_argument("--url", help="only this document (or topic key)")
    p.add_argument("--scope", choices=eligibility.SCOPES, help="only call documents, general annexes or topic texts")
    p.add_argument("--force", action="store_true", help="ask again even if held")
    p.add_argument("--redact-stored", action="store_true",
                   help="count (with --yes: redact) e-mail addresses in the stored texts; no model call")
    a = p.parse_args(argv)
    failed = 0
    with db.connect(settings().dsn) as conn:
        if a.redact_stored:
            print(eligibility.redact_stored(conn, write=a.yes), "redacted" if a.yes else "found (dry run, add --yes)")
            return 0
        docs = eligibility.extraction_units(conn)
        if a.scope:
            docs = [d for d in docs if d["scope"] == a.scope]
        if a.url:
            docs = [d for d in docs if a.url in (d["url"], d["key"])] or [
                {"url": a.url, "key": a.url, "scope": "call_document", "calls": 0, "open_calls": 0, "text": None,
                 "topic": None}]
        if a.limit:
            docs = docs[:a.limit]
        print(f"{len(docs)} documents; month spent {llm.month_spent(conn):.3f} USD, "
              f"cap {settings().llm_monthly_cap_usd:.2f}")
        for d in docs:
            if not a.yes:
                print(f"  {d['open_calls']:2d} open / {d.get('forthcoming_calls', 0):2d} forthcoming / "
                      f"{d['calls']:2d} calls  {d['scope']:13s} {d['key']}")
                continue
            try:
                print(eligibility.extract_one(conn, d["url"], force=a.force, scope=d["scope"], text=d["text"],
                                               topic=d["topic"]))
            except llm.CapReached as exc:
                print("STOP:", exc)
                return 2
            except Exception as exc:  # noqa: BLE001 - one document must not stop the others
                conn.rollback()
                failed += 1
                print({"url": d["url"], "status": "failed", "error": str(exc)[:200]})
        if a.yes:
            print(f"month spent now {llm.month_spent(conn):.3f} USD")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
