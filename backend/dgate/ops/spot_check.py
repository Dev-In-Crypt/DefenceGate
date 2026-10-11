"""Spot check: re-read sampled records from their source and compare with what we serve.

For each sampled opportunity, three things are put side by side: the payload we
landed, the record the source serves now, and the database row. Both payloads go
through the normaliser and the classifier, and the result is compared with the row.

    same record   the source's record hashes as the one we landed
        match      the row says what the record says
        MISMATCH   the row says something else: a mapping or serving defect
    moved         the source's record has changed since we landed it. Not a defect
                  of ours, but the row is out of date, and the fields are listed
    not found     the source no longer returns it
    no live       the source cannot be asked by identifier (static dataset, or a
                  platform whose robots.txt disallows it); only what we stored is
                  compared with the row

Read-only: nothing is written, the transaction is rolled back, one request a second.

    python -m dgate.ops.spot_check --source ted --source nl_tenderned -n 20
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Callable

import httpx

from .. import db
from ..config import settings
from ..db import CALL_FIELDS, OPTIONAL_CALL_FIELDS
from ..normalise import (
    Call,
    Opportunity,
    from_aid,
    from_atlas_pl,
    from_bdns,
    from_boamp,
    from_eu_call,
    from_ezamowienia,
    from_matine,
    from_ncbr,
    from_ted,
    from_tenderned,
    from_vinnova,
    strip_personal_data,
)
from ..rawstore import build_store
from ..sources import (
    USER_AGENT,
    aid,
    bdns,
    boamp,
    eu_portal,
    ezamowienia,
    matine,
    ncbr,
    ted,
    tenderned,
    vinnova,
)

log = logging.getLogger("spot_check")

PAUSE = 1.0

# What a person reading the notice would check. The classification verdict is
# compared too, because a wrong "defence" is the error that costs a supplier.
COMPARED = ["title_original", "buyer_name_raw", "country", "published_at", "deadline_at",
            "cpv_codes", "legal_basis", "value_amount", "value_currency", "procedure_type",
            "status", "source_url", "is_defence"]


def _norm(field_name: str, value: Any) -> Any:
    if isinstance(value, Decimal):
        value = float(value)
    if field_name == "cpv_codes":
        return sorted(value or [])
    if isinstance(value, str):
        return value.strip() or None
    return value


def differences(row: dict[str, Any], opp: Opportunity) -> dict[str, tuple[Any, Any]]:
    """Field -> (served, from the record), for every compared field that disagrees."""
    out = {}
    for name in COMPARED:
        served, read = _norm(name, row.get(name)), _norm(name, getattr(opp, name))
        if served != read:
            out[name] = (served, read)
    return out


@dataclass
class Verdict:
    source: str
    native_id: str
    published_at: date | None
    verdict: str                       # match | MISMATCH | moved | not found | no live
    detail: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------- live readers
# Each returns the raw record exactly as the daily job would have landed it, or None.

def _live_ted(client: httpx.Client, native_id: str, stored: dict) -> dict | None:
    for notice in ted.search(f'publication-number = "{native_id}"', client=client, max_pages=1):
        return notice
    return None


def _live_boamp(client: httpx.Client, native_id: str, stored: dict) -> dict | None:
    for record in boamp.search({"where": f'idweb = "{native_id}"', "limit": 5}, client=client):
        if str(record.get("idweb")) == native_id:
            return record
    return None


def _live_ezam(client: httpx.Client, native_id: str, stored: dict) -> dict | None:
    number = stored.get("noticeNumber") or native_id
    for record in ezamowienia.search({"noticeNumber": number, "PageSize": 20}, client=client):
        if record.get("noticeNumber") == number or record.get("objectId") == stored.get("objectId"):
            return record
    return None


def _live_tenderned(client: httpx.Client, native_id: str, stored: dict) -> dict | None:
    published = stored.get("publicatieDatum")
    if not published:
        return None
    for record in tenderned.fetch_day_list(date.fromisoformat(str(published)[:10]), client=client):
        if str(record.get("publicatieId")) == native_id:
            time.sleep(PAUSE)
            try:
                detail, error = tenderned.fetch_detail(native_id, client=client), None
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                detail, error = None, f"{type(exc).__name__}: {exc}"[:200]
            return tenderned.merge_detail(record, detail, error)
    return None


@dataclass
class Adapter:
    mapper: Callable[[dict], Opportunity]
    live: Callable[[httpx.Client, str, dict], dict | None] | None
    why_no_live: str = ""


ADAPTERS: dict[str, Adapter] = {
    "ted": Adapter(from_ted, _live_ted),
    "fr_boamp": Adapter(from_boamp, _live_boamp),
    "pl_ezam": Adapter(from_ezamowienia, _live_ezam),
    "nl_tenderned": Adapter(from_tenderned, _live_tenderned),
    "pl_atlas": Adapter(from_atlas_pl, None,
                        "static dataset (Zenodo, CC BY 4.0): there is no live source to ask"),
}


def _passthrough(payload: dict) -> Opportunity:
    return db.opportunity_from_payload(payload)


for _code in ("es_placsp", "es_placsp_agg"):
    ADAPTERS[_code] = Adapter(
        _passthrough, None,
        "contrataciondelestado.es disallows all robots (robots.txt: Disallow: /) and the "
        "feed cannot be asked by identifier; the stored record is already normalised")


# ------------------------------------------------------------------- the check

def _classify(conn, opp: Opportunity, src_id: int) -> Opportunity:
    from ..pipeline import _finalise
    return _finalise(conn, opp, src_id)


def check_source(conn, store, code: str, n: int, seed: str,
                 client: httpx.Client) -> list[Verdict]:
    adapter = ADAPTERS[code]
    src_id = db.source_id(conn, code)
    # SET is undone by the rollback below, so it is asked for again per source.
    conn.execute("SET statement_timeout = '300s'")
    rows = conn.execute(
        "SELECT * FROM opportunity WHERE source_id = %s AND is_defence "
        "ORDER BY md5(native_id || %s) LIMIT %s", (src_id, seed, n)).fetchall()
    ids = [r["native_id"] for r in rows]
    raws = {r["native_id"]: r for r in conn.execute(
        "SELECT DISTINCT ON (native_id) native_id, storage_key, content_hash FROM raw_ingest "
        "WHERE source_id = %s AND native_id = ANY(%s) ORDER BY native_id, id DESC",
        (src_id, ids))}

    out: list[Verdict] = []
    for row in rows:
        nid = row["native_id"]
        verdict = Verdict(code, nid, row["published_at"], "no live")
        raw = raws.get(nid)
        if raw is None:
            verdict.verdict, verdict.detail = "MISMATCH", {"error": "no raw payload landed"}
            out.append(verdict)
            continue
        stored = store.get(raw["storage_key"])
        # What we stored, read again today with today's code.
        from_stored = differences(row, _classify(conn, adapter.mapper(stored), src_id))
        if adapter.live is None:
            verdict.detail = {"why": adapter.why_no_live, "stored_vs_row": from_stored}
            if from_stored:
                verdict.verdict = "MISMATCH"
            out.append(verdict)
            continue

        time.sleep(PAUSE)
        try:
            live = adapter.live(client, nid, stored)
        except Exception as exc:  # noqa: BLE001 - a source error is a result, not a crash
            verdict.verdict, verdict.detail = "not found", {"error": f"{type(exc).__name__}: {exc}"[:200]}
            out.append(verdict)
            continue
        if live is None:
            verdict.verdict = "not found"
            out.append(verdict)
            continue

        clean = strip_personal_data(live)
        same = ted.content_hash(clean) == raw["content_hash"]
        from_live = differences(row, _classify(conn, adapter.mapper(clean), src_id))
        if same:
            verdict.verdict = "MISMATCH" if (from_live or from_stored) else "match"
            verdict.detail = {"live_vs_row": from_live, "stored_vs_row": from_stored}
        else:
            # The record moved. A mismatch that is already in what we stored is
            # still ours; one that appears only in the live record is the source's.
            verdict.verdict = "MISMATCH" if from_stored else "moved"
            verdict.detail = {"changed_since_landed": from_live, "stored_vs_row": from_stored}
        out.append(verdict)
    conn.rollback()           # classification may resolve buyers; nothing is kept
    return out


# ------------------------------------------------------------------ the calls
# A call is a living row, refreshed every night, so there is no "moved": a
# difference is either the source having changed since last night or a defect.
# The sets are small and fetched whole, so every stored call is checked, not a sample.

CALL_SOURCES: dict[str, tuple[Callable[..., Any], Callable[[dict], Call]]] = {
    "eu_portal": (eu_portal.fetch_calls, from_eu_call),
    "pl_ncbr": (ncbr.fetch_all, from_ncbr),
    "se_vinnova": (vinnova.fetch_all, from_vinnova),
    "fr_aid": (aid.fetch_all, from_aid),
    "fi_matine": (matine.fetch_all, from_matine),
}


def call_differences(row: dict[str, Any], call: Call) -> dict[str, tuple[Any, Any]]:
    """As `differences`, but a field the document does not carry is not a claim.

    The EU calendar has no budget or conditions (the topic page does), and a call
    never overwrites what is stored with None for those; the check follows the same
    rule, or every EU call would be a false mismatch.
    """
    out = {}
    for name in CALL_FIELDS:
        read = getattr(call, name)
        if name in OPTIONAL_CALL_FIELDS and read is None:
            continue
        served, value = _norm(name, row.get(name)), _norm(name, read)
        if served != value:
            out[name] = (served, value)
    return out


def check_calls(conn, code: str, client: httpx.Client) -> list[Verdict]:
    src_id = db.source_id(conn, code)
    rows = conn.execute(
        "SELECT c.*, p.code AS programme_code FROM call c "
        "JOIN programme p ON p.id = c.programme_id WHERE c.source_id = %s "
        "ORDER BY c.native_id", (src_id,)).fetchall()
    live: dict[tuple[str, str], Call] = {}
    if code == "es_bdns":
        for row in rows:
            time.sleep(PAUSE)
            try:
                call = from_bdns(strip_personal_data(bdns.fetch_detail(row["native_id"], client=client)))
            except Exception as exc:  # noqa: BLE001
                log.warning("bdns %s: %s", row["native_id"], exc)
                continue
            live[(call.programme_code, call.native_id)] = call
    else:
        fetch, mapper = CALL_SOURCES[code]
        for record in fetch(client=client):
            try:
                call = mapper(strip_personal_data(record))
            except Exception:  # noqa: BLE001 - an out-of-scope record may not map
                continue
            live[(call.programme_code, call.native_id)] = call

    out = []
    for row in rows:
        verdict = Verdict(code, row["native_id"], row.get("opens_at"), "match")
        call = live.get((row["programme_code"], row["native_id"]))
        if call is None:
            verdict.verdict = "not found"
        else:
            diff = call_differences(row, call)
            if diff:
                verdict.verdict, verdict.detail = "MISMATCH", {"live_vs_row": diff}
        out.append(verdict)
    return out


def _show(v: Verdict) -> str:
    def cut(x: Any) -> str:
        return json.dumps(x, ensure_ascii=False, default=str)[:90]
    lines = [f"  {v.verdict:9s} {v.native_id}  ({v.published_at})"]
    for key in ("live_vs_row", "stored_vs_row", "changed_since_landed"):
        for name, pair in (v.detail.get(key) or {}).items():
            lines.append(f"      {key}: {name}: row={cut(pair[0])}  record={cut(pair[1])}")
    for key in ("why", "error"):
        if v.detail.get(key):
            lines.append(f"      {key}: {v.detail[key]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", action="append", choices=sorted(ADAPTERS))
    parser.add_argument("--calls", action="store_true",
                        help="check every stored call of the grant sources, not the notices")
    parser.add_argument("-n", type=int, default=20)
    parser.add_argument("--seed", default="2026-10-11",
                        help="the sample is md5(native_id + seed), so a rerun reads the same records")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    store = build_store()
    client = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                          follow_redirects=True, timeout=90.0)
    worst = 0
    with db.connect(settings().dsn) as conn:
        conn.execute("SET statement_timeout = '300s'")
        sources = (sorted(CALL_SOURCES) + ["es_bdns"]) if args.calls             else (args.source or sorted(ADAPTERS))
        for code in sources:
            verdicts = (check_calls(conn, code, client) if args.calls
                        else check_source(conn, store, code, args.n, args.seed, client))
            tally: dict[str, int] = {}
            for v in verdicts:
                tally[v.verdict] = tally.get(v.verdict, 0) + 1
            print(f"\n{code}: {len(verdicts)} sampled  " +
                  "  ".join(f"{k}={v}" for k, v in sorted(tally.items())))
            for v in verdicts:
                if v.verdict != "match":
                    print(_show(v))
            worst += tally.get("MISMATCH", 0)
    return 1 if worst else 0


if __name__ == "__main__":
    sys.exit(main())
