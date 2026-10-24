"""Tie a national notice to the TED notice it is the same procurement as.

The serving layer already shows a national row under its TED twin and not beside
it, but only where the national source states the TED number (`opportunity.ted_ref`:
TenderNed, the Polish bulletin, Atlas). BOAMP and PLACSP state none, so a frigate
engine tender was listed once from PLACSP and once from TED. This sets `ted_ref`
for those rows, so the collapse works unchanged, and records how it knew in
`twin_method` and `twin_confidence` (migration 0035):

    stated_ted_ref  `ted_ref` already stated by the source and the TED row is held
    procedure_id    the eForms procedure identifier is the same on both rows
                    (PLACSP `<cbc:UUID schemeName="TED">`, BOAMP `contractfolderid`)
    heuristic       no identifier on the national row: same buyer, deadline instant,
                    value and currency, publication within 14 days, a shared 5-digit
                    CPV class, and exactly one candidate on each side

Nothing is fetched except under `--fill-placsp`, nothing is deleted, no version is
written (a link is not a version-worthy fact), a stated `ted_ref` is never replaced,
and a second run finds nothing left to do.

    python -m dgate.ops.link_twins                          # dry run: counts per method
    python -m dgate.ops.link_twins --yes                    # write
    python -m dgate.ops.link_twins --source fr_boamp --limit 500 --yes
    python -m dgate.ops.link_twins --fill-raw --yes         # BOAMP procedure ids from the store
    python -m dgate.ops.link_twins --fill-placsp 2026-08 2026-10 --yes   # PLACSP ids from monthly archives
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import defaultdict
from typing import Any

from .. import db
from ..config import settings

log = logging.getLogger("link_twins")

METHODS = ("stated_ted_ref", "procedure_id", "heuristic")

# How sure each method is, as the share of links expected to be the same procurement.
# The two identifier methods compare a value both sides state; the heuristic's figure is
# the lower bound of the sample read by hand (see docs/sources/boamp.md, "TED reference").
CONFIDENCE = {"stated_ted_ref": 1.0, "procedure_id": 0.98, "heuristic": 0.9,
              # no value on either side, deadline within a day (zones differ): weaker
              "heuristic_novalue": 0.8,
              # WP-111: two planned notices with no deadline and no value: the codes, the buyer and the days only
              "heuristic_planned": 0.8}

# Sources whose stored raw payload is the record as the source sent it, so the mapper can
# read the procedure identifier again. PLACSP's raw payload is the mapped record, which
# has no CODICE left in it: its identifier comes from the archives (`--fill-placsp`).
# TenderNed states a TED number and its own UUID is not a procedure identifier.
RAW_FILL_SOURCES = ("fr_boamp",)

# The same identifier spelled with braces or capitals compares equal.
_NORM = "lower(btrim({col}, '{{}} '))"


def _ted_id(conn) -> int:
    return db.source_id(conn, "ted")


def _only(source: str | None, conn) -> int | None:
    return db.source_id(conn, source) if source else None


def link_stated(conn, *, write: bool = False, source: str | None = None,
                limit: int | None = None) -> int:
    """Rows whose own `ted_ref` points at a TED row we hold: record that it was stated."""
    ted, only = _ted_id(conn), _only(source, conn)
    where = """o.source_id <> %(ted)s AND o.ted_ref IS NOT NULL AND o.twin_method IS NULL
               AND (%(only)s::int IS NULL OR o.source_id = %(only)s)
               AND EXISTS (SELECT 1 FROM opportunity t
                            WHERE t.source_id = %(ted)s AND t.native_id = o.ted_ref)"""
    params = {"ted": ted, "only": only, "limit": limit, "conf": CONFIDENCE["stated_ted_ref"]}
    if not write:
        return conn.execute(
            f"SELECT count(*) AS n FROM (SELECT 1 FROM opportunity o WHERE {where} "
            "LIMIT %(limit)s) c", params).fetchone()["n"]
    return conn.execute(
        f"""WITH todo AS (SELECT o.id FROM opportunity o WHERE {where} ORDER BY o.id LIMIT %(limit)s)
            UPDATE opportunity o SET twin_method = 'stated_ted_ref', twin_confidence = %(conf)s
              FROM todo WHERE o.id = todo.id""", params).rowcount


def link_procedure(conn, *, write: bool = False, source: str | None = None,
                   limit: int | None = None) -> int:
    """Rows that share an eForms procedure identifier with a TED row.

    A procedure has several TED notices (the call, a corrigendum, the award); the one
    chosen is the newest with the row's own status, which is the one the list shows.
    """
    ted, only = _ted_id(conn), _only(source, conn)
    params = {"ted": ted, "only": only, "limit": limit, "conf": CONFIDENCE["procedure_id"]}
    pid_n = _NORM.format(col="c.procedure_identifier")
    pid_t = _NORM.format(col="t.procedure_identifier")
    best = f"""
        WITH cand AS (
            SELECT o.id, o.status, o.procedure_identifier FROM opportunity o
             WHERE o.source_id <> %(ted)s AND o.ted_ref IS NULL
               AND o.procedure_identifier IS NOT NULL
               AND (%(only)s::int IS NULL OR o.source_id = %(only)s)
             ORDER BY o.id LIMIT %(limit)s),
        best AS (
            SELECT DISTINCT ON (c.id) c.id, t.native_id
              FROM cand c JOIN opportunity t
                ON t.source_id = %(ted)s AND t.procedure_identifier IS NOT NULL
               AND {pid_t} = {pid_n}
             ORDER BY c.id, (t.status IS NOT DISTINCT FROM c.status) DESC,
                      t.published_at DESC NULLS LAST, t.id DESC)"""
    if not write:
        return conn.execute(best + " SELECT count(*) AS n FROM best", params).fetchone()["n"]
    return conn.execute(
        best + """ UPDATE opportunity o
                      SET ted_ref = best.native_id, twin_method = 'procedure_id',
                          twin_confidence = %(conf)s
                     FROM best WHERE o.id = best.id AND o.ted_ref IS NULL""", params).rowcount


# Every pair of a national row and a TED row that agree on what the heuristic requires.
# `free` marks the rows that may be written: no stated link and no identifier that a TED row
# shares (BOAMP 26-77210 states one that TED's payload for the same notice lacks, and was
# never offered to the heuristic for that reason). The others
# still count as candidates, because a second notice that looks the same makes the match
# ambiguous whether or not it already has a twin.
_PAIRS = """
SELECT n.id AS nid, n.source_id AS nsrc, coalesce(n.related_native_id, n.native_id) AS ngroup,
       (n.ted_ref IS NULL AND (n.procedure_identifier IS NULL OR NOT EXISTS (
            SELECT 1 FROM opportunity x WHERE x.source_id = %(ted)s
               AND x.procedure_identifier = n.procedure_identifier))) AS free,
       n.status AS nstatus,
       t.native_id AS tnative, t.id AS tid, coalesce(t.procedure_identifier, t.native_id) AS tgroup,
       t.status AS tstatus, t.published_at AS tpub
  FROM opportunity n
  JOIN opportunity t
    ON t.source_id = %(ted)s AND t.country = n.country
   AND {match}
   AND (n.procedure_identifier IS NULL OR t.procedure_identifier IS NULL)
   AND abs(t.published_at - n.published_at) <= 14
 WHERE n.source_id <> %(ted)s AND n.published_at IS NOT NULL
   AND {have}
   AND EXISTS (SELECT 1 FROM unnest(n.cpv_codes) a, unnest(t.cpv_codes) b
                WHERE left(a, 5) = left(b, 5) AND length(a) >= 5 AND length(b) >= 5)
   AND (n.buyer_org_id = t.buyer_org_id
        OR regexp_replace(lower(btrim(n.buyer_name_raw)), '\\s+', ' ', 'g')
         = regexp_replace(lower(btrim(t.buyer_name_raw)), '\\s+', ' ', 'g'))
"""


# The strict match needs the same deadline instant and the same value. A notice with no
# value on either side (SID Sud-Est, BOAMP 26-77210 / TED 537243-2026: the buyer's local
# 16:00 against TED's 23:59 Paris, no amount, no procedure identifier in TED's payload) never
# matched, so the loose match takes a deadline within a day and both values empty. The
# one-candidate-per-side rule is unchanged and the confidence is lower.
_STRICT = ("t.deadline_at = n.deadline_at AND t.value_amount = n.value_amount "
           "AND t.value_currency = n.value_currency",
           "n.deadline_at IS NOT NULL AND n.value_amount IS NOT NULL AND n.value_currency IS NOT NULL")
_LOOSE = ("t.deadline_at IS NOT NULL AND abs(extract(epoch FROM t.deadline_at - n.deadline_at)) <= 86400 "
          "AND t.value_amount IS NULL AND t.value_currency IS NULL",
          "n.deadline_at IS NOT NULL AND n.value_amount IS NULL AND n.value_currency IS NULL")
# WP-111 (p03): a planned notice (prior information) states no deadline, so neither match above could tie BAAINBw's
# Bekanntmachungsservice copy of a market survey (26 June 2026) to its TED notice 448143-2026 (30 June), and the buyer page
# showed one procurement twice. Both planned, neither with a deadline, the same CPV codes exactly, the same buyer, published
# within 14 days, and (as for every heuristic) each the other's only candidate.
_PLANNED = ("t.status = 'forthcoming' AND t.deadline_at IS NULL AND t.cpv_codes = n.cpv_codes",
            "n.status = 'forthcoming' AND n.deadline_at IS NULL")


def heuristic_pairs(conn, *, loose: bool = False, planned: bool = False) -> list[tuple[int, str]]:
    """(national row id, TED native id) for every row the heuristic would link."""
    match, have = _PLANNED if planned else _LOOSE if loose else _STRICT
    sql = _PAIRS.replace("{match}", match).replace("{have}", have)
    return unambiguous(conn.execute(sql, {"ted": _ted_id(conn)}).fetchall())


def unambiguous(rows: list[dict[str, Any]]) -> list[tuple[int, str]]:
    """Keep the pairs where each side has no other candidate.

    A national notice and a TED notice are one procurement only when each is the other's
    single candidate. A BOAMP rectificatif counts with the notice it corrects, and the
    TED notices of one procedure (call and corrigendum) count as one, so a notice that
    was amended is not turned away for being repeated.
    """
    tgroups: dict[tuple, set] = defaultdict(set)
    ngroups: dict[str, set] = defaultdict(set)
    for r in rows:
        tgroups[(r["nsrc"], r["ngroup"])].add(r["tgroup"])
        ngroups[r["tgroup"]].add((r["nsrc"], r["ngroup"]))
    chosen: dict[int, tuple] = {}
    for r in rows:
        if not r["free"]:
            continue
        if len(tgroups[(r["nsrc"], r["ngroup"])]) != 1 or len(ngroups[r["tgroup"]]) != 1:
            continue
        # the TED notice with the row's own status, then the newest: the one the list shows
        rank = (r["tstatus"] == r["nstatus"], r["tpub"].toordinal() if r["tpub"] else 0, r["tid"])
        if r["nid"] not in chosen or rank > chosen[r["nid"]][0]:
            chosen[r["nid"]] = (rank, r["tnative"])
    return sorted((nid, tnative) for nid, (_, tnative) in chosen.items())


def link_heuristic(conn, *, write: bool = False, source: str | None = None,
                   limit: int | None = None) -> int:
    only = _only(source, conn)
    pairs = [(p, "heuristic") for p in heuristic_pairs(conn)]
    pairs += [(p, "heuristic_novalue") for p in heuristic_pairs(conn, loose=True)]
    pairs += [(p, "heuristic_planned") for p in heuristic_pairs(conn, planned=True)]
    if only is not None:
        keep = {r["id"] for r in conn.execute(
            "SELECT id FROM opportunity WHERE id = ANY(%s) AND source_id = %s",
            ([p[0] for p, _ in pairs], only))}
        pairs = [(p, m) for p, m in pairs if p[0] in keep]
    if limit is not None:
        pairs = pairs[:limit]
    if not write:
        return len(pairs)
    done = 0
    for (nid, tnative), conf in pairs:
        done += conn.execute(
            """UPDATE opportunity SET ted_ref = %s, twin_method = 'heuristic', twin_confidence = %s
                WHERE id = %s AND ted_ref IS NULL""",
            (tnative, CONFIDENCE[conf], nid)).rowcount
    return done


LINKERS = {"stated_ted_ref": link_stated, "procedure_id": link_procedure,
           "heuristic": link_heuristic}


def run(conn, *, write: bool = False, methods: tuple[str, ...] = METHODS,
        source: str | None = None, limit: int | None = None) -> dict[str, int]:
    """Links per method, in the order that makes a stronger method win."""
    out = {}
    for method in METHODS:
        if method in methods:
            out[method] = LINKERS[method](conn, write=write, source=source, limit=limit)
            if write:
                conn.commit()
    return out


# ----------------------------------------------------- procedure identifiers

def fill_from_raw(conn, store, *, write: bool = False, source: str | None = None) -> dict[str, int]:
    """Read BOAMP's procedure identifier from the landed payloads.

    Same replay as `link_ted`: nothing is fetched, no version is written.
    """
    from . import link_ted

    out = {}
    for code in RAW_FILL_SOURCES:
        if source and source != code:
            continue
        read, found = link_ted.backfill(conn, store, code, dry_run=not write,
                                        column="procedure_identifier")
        out[code] = found
        log.info("%s: read %s payloads, %s carry a procedure identifier", code, read, found)
        if write:
            conn.commit()
    return out


def fill_from_archives(conn, months: list[tuple[int, int]], *, write: bool = False,
                       sleep: float = 1.0) -> int:
    """Set `procedure_identifier` on PLACSP rows from the publisher's monthly archives.

    The landed PLACSP payload is the mapped record, so the identifier that
    `placsp.parse_entry` now reads is not in it. One request per dataset and month,
    spaced a second apart, the documented public archive host only. Notices we do not
    hold are not inserted; a row that has an identifier is left as it is.
    """
    from ..sources import placsp

    found: dict[tuple[str, str], str] = {}
    for ds in (placsp.MAIN, placsp.AGGREGATED):
        for year, month in months:
            url = ds.monthly_archive_url(year, month)
            try:
                for opp in placsp.fetch_archive(url, ds):
                    if opp.procedure_identifier:
                        found[(ds.source_code, opp.native_id)] = opp.procedure_identifier
            except Exception as exc:  # noqa: BLE001 - a month the publisher lacks is not fatal
                log.warning("%s %04d-%02d skipped: %s", ds.source_code, year, month, exc)
            log.info("%s %04d-%02d: %s identifiers so far", ds.source_code, year, month, len(found))
            time.sleep(sleep)
    done = 0
    for (code, native_id), value in found.items():
        sql = ("UPDATE opportunity SET procedure_identifier = %s WHERE source_id = %s "
               "AND native_id = %s AND procedure_identifier IS NULL")
        if write:
            done += conn.execute(sql, (value, db.source_id(conn, code), native_id)).rowcount
        else:
            done += conn.execute(
                "SELECT count(*) AS n FROM opportunity WHERE source_id = %s AND native_id = %s "
                "AND procedure_identifier IS NULL", (db.source_id(conn, code), native_id)
            ).fetchone()["n"]
    if write:
        conn.commit()
    return done


def _month(text: str) -> tuple[int, int]:
    year, month = text.split("-")
    if not (2012 <= int(year) <= 2100 and 1 <= int(month) <= 12):
        raise argparse.ArgumentTypeError(f"not a month: {text}")
    return int(year), int(month)


def _months(first: tuple[int, int], last: tuple[int, int]) -> list[tuple[int, int]]:
    out, (y, m) = [], first
    while (y, m) <= last:
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="write; without it nothing changes")
    parser.add_argument("--source", help="only national rows of this source code")
    parser.add_argument("--limit", type=int, help="at most this many links per method")
    parser.add_argument("--method", action="append", choices=METHODS,
                        help="only this method (repeatable); default all, strongest first")
    parser.add_argument("--fill-raw", action="store_true",
                        help="first read BOAMP procedure identifiers from the raw store")
    parser.add_argument("--fill-placsp", nargs=2, type=_month, metavar=("FROM", "TO"),
                        help="first read PLACSP procedure identifiers from monthly archives")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    mode = "write" if args.yes else "dry run, nothing is written"
    with db.connect(settings().dsn) as conn:
        if args.fill_raw:
            from ..rawstore import build_store

            fill_from_raw(conn, build_store(), write=args.yes, source=args.source)
        if args.fill_placsp:
            n = fill_from_archives(conn, _months(*args.fill_placsp), write=args.yes)
            log.info("placsp procedure identifiers %s: %s", "set" if args.yes else "to set", n)
        counts = run(conn, write=args.yes, methods=tuple(args.method or METHODS),
                     source=args.source, limit=args.limit)
    for method, n in counts.items():
        log.info("%-15s %6d %s", method, n, "linked" if args.yes else "would be linked")
    log.info("(%s)", mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
