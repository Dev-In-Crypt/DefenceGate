"""The regulatory tracker: entries about the rules that matter to a supplier, each with its primary source.

    GET /v1/regulation        the active entries, newest event first

Content lives in `seeds/regulation_tracker.json`. Every entry has the primary source link, a verbatim
sentence of that source, who is affected and the day we last checked. A claim we could not confirm
against a primary text is not an entry; an entry whose point stays open says so in its status
(`unconfirmed`). The worker applies the seed when it starts (`ensure_regulation`); a row the seed
stops listing is switched off, never deleted.

    python -m dgate.regulation --check     parse and validate the seed only (no database)
    python -m dgate.regulation             apply it to the database in DGATE_DSN
    python -m dgate.regulation --export <repository root>   write web/lib/mock/regulation.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from fastapi import APIRouter, Depends

from . import db
from .config import settings

router = APIRouter()

SEED_PATH = Path(__file__).resolve().parents[1] / "seeds" / "regulation_tracker.json"
STATUSES = ("proposed", "announced", "agreed", "adopted", "in_force", "unconfirmed")
LINK_KINDS = ("requirement", "programme", "page")
MIN_QUOTE_CHARS = 25
NOTICE = ("Each entry gives the primary source and one sentence of it, copied word for word, and the day we last "
          "read it. It is a reading aid for suppliers, not legal advice. Where a point is not settled by a text we "
          "could read, the status says unconfirmed.")


class SeedError(ValueError):
    """The seed file is not valid. The message names the entry."""


def _need(cond: bool, message: str) -> None:
    if not cond:
        raise SeedError(message)


def parse(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate the seed and return its entries in file order. Raises SeedError naming the entry."""
    entries = raw.get("entries")
    _need(isinstance(entries, list) and bool(entries), "no entries")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for position, e in enumerate(entries):
        code = str(e.get("code") or "")
        where = f"entry {code or position}"
        _need(bool(code) and code not in seen, f"{where}: a unique code is required")
        seen.add(code)
        for key in ("instrument", "title", "what_changed", "affected", "source_ref"):
            _need(bool(str(e.get(key) or "").strip()), f"{where}: {key} is required")
        _need(e.get("status") in STATUSES, f"{where}: status must be one of {', '.join(STATUSES)}")
        _need(str(e.get("source_url") or "").startswith("https://") or str(e.get("source_url") or "").startswith("http://data.europa.eu/"),
              f"{where}: source_url must be an https address")
        _need(len(str(e.get("source_quote") or "").strip()) >= MIN_QUOTE_CHARS, f"{where}: a verbatim sentence of the source is required")
        for key in ("event_date", "checked_on"):
            try:
                date.fromisoformat(e[key])
            except (KeyError, ValueError, TypeError):
                raise SeedError(f"{where}: {key} must be a date") from None
        links = e.get("links") or []
        for ln in links:
            _need(ln.get("kind") in LINK_KINDS and bool(ln.get("code")) and bool(ln.get("label")), f"{where}: a link needs kind, code and label")
        out.append({**e, "links": links, "position": position})
    return out


def load_file(path: Path = SEED_PATH) -> list[dict[str, Any]]:
    return parse(json.loads(path.read_text(encoding="utf-8")))


def apply(conn: psycopg.Connection, entries: list[dict[str, Any]]) -> dict[str, int]:
    """Write the entries. Returns how many rows were inserted and how many switched off."""
    counts = {"inserted": 0, "deactivated": 0}
    for e in entries:
        row = conn.execute(
            """INSERT INTO regulation_entry
                 (code, instrument, title, what_changed, event_date, status, affected, source_url, source_ref,
                  source_quote, checked_on, links, position, active)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,TRUE)
               ON CONFLICT (code) DO UPDATE SET instrument=EXCLUDED.instrument, title=EXCLUDED.title,
                 what_changed=EXCLUDED.what_changed, event_date=EXCLUDED.event_date, status=EXCLUDED.status,
                 affected=EXCLUDED.affected, source_url=EXCLUDED.source_url, source_ref=EXCLUDED.source_ref,
                 source_quote=EXCLUDED.source_quote, checked_on=EXCLUDED.checked_on, links=EXCLUDED.links,
                 position=EXCLUDED.position, active=TRUE
               RETURNING (xmax = 0) AS inserted""",
            (e["code"], e["instrument"], e["title"], e["what_changed"], e["event_date"], e["status"], e["affected"],
             e["source_url"], e["source_ref"], e["source_quote"], e["checked_on"], json.dumps(e["links"]), e["position"])).fetchone()
        counts["inserted"] += 1 if row["inserted"] else 0
    gone = conn.execute("UPDATE regulation_entry SET active = FALSE WHERE active AND NOT (code = ANY(%s))",
                        ([e["code"] for e in entries],))
    counts["deactivated"] = gone.rowcount
    conn.commit()
    return counts


def _served(e: dict[str, Any]) -> dict[str, Any]:
    """One entry as the API serves it (the seed's field names in, the API's out)."""
    return {"code": e["code"], "instrument": e["instrument"], "title": e["title"], "whatChanged": e["what_changed"],
            "eventDate": str(e["event_date"]), "status": e["status"], "affected": e["affected"],
            "source": {"url": e["source_url"], "ref": e["source_ref"], "quote": e["source_quote"]},
            "checkedOn": str(e["checked_on"]), "links": e["links"]}


def payload(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """The whole answer for entries in the order they are served: newest event first."""
    ordered = sorted(entries, key=lambda e: (-date.fromisoformat(str(e["event_date"])).toordinal(), e.get("position", 0), e["code"]))
    served = [_served(e) for e in ordered]
    return {"entries": served, "lastChecked": max((e["checkedOn"] for e in served), default=None), "notice": NOTICE}


def read(conn) -> dict[str, Any]:
    rows = conn.execute(
        """SELECT code, instrument, title, what_changed, event_date, status, affected, source_url, source_ref,
                  source_quote, checked_on, links, position
             FROM regulation_entry WHERE active""").fetchall()
    return payload([dict(r) for r in rows])


MOCK_PATH = "web/lib/mock/regulation.json"


def mock_text() -> str:
    """The file the site builds from when it has no API (CI): the seed, as the API would serve it."""
    return json.dumps(payload(load_file()), indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def get_conn():
    cfg = settings()
    with db.connect(cfg.api_dsn or cfg.dsn) as conn:
        yield conn


@router.get("/v1/regulation")
def list_regulation(conn=Depends(get_conn)):
    return read(conn)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="regulation", description=__doc__.split("\n\n")[0])
    p.add_argument("--check", action="store_true", help="validate the seed file only")
    p.add_argument("--export", type=Path, metavar="ROOT", help="write web/lib/mock/regulation.json under the repository root")
    a = p.parse_args(argv)
    entries = load_file()
    if a.check:
        print(f"{len(entries)} entries valid")
        return 0
    if a.export:
        (a.export / MOCK_PATH).write_text(mock_text(), encoding="utf-8", newline="\n")
        print(f"wrote {MOCK_PATH}")
        return 0
    with db.connect(settings().dsn) as conn:
        print(apply(conn, entries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
