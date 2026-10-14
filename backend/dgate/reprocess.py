"""Rebuild the serving layer from raw storage.

This module is the answer to one question: what is left if the database dies?

The pipeline lands every payload in object storage before it normalises
anything, so the database is a derived artefact. Losing it costs the time it
takes to replay, not the data. Nothing here talks to a source, so a replay
works when TED is down, when a national portal has removed the notice, and when
the source has changed its schema underneath us.

Two modes, and the difference matters on the worst day:

    from the index    reads `raw_ingest`, which is fast and ordered, and is the
                      right choice for replaying a parser fix
    from the store    enumerates the object store itself, which is the only
                      mode that survives losing the database, because
                      `raw_ingest` is a table inside it

    python -m dgate.reprocess --source ted --from 2026-09-01
    python -m dgate.reprocess --from-store          # after a total loss
    python -m dgate.reprocess --from-store --dry-run

A third question is answered by `--requalify`: which landed notices does the classifier
keep today that it dropped at ingest? Any source, one day at a time, resumable:

    python -m dgate.reprocess --requalify --source fr_boamp --from 2026-09-21 --to 2026-10-14
    python -m dgate.reprocess --requalify --days 30 --yes       # every source, last 30 days
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import db
from .config import settings
from .normalise import (
    from_atlas_pl,
    from_boamp,
    from_ezamowienia,
    from_ted,
    from_tenderned,
    strip_personal_data,
)
from .rawstore import BUNDLE_EXTENSION, RawStore, build_store, record_key
from .sources.ted import content_hash

log = logging.getLogger("reprocess")

# One mapper per source. A source missing from here cannot be replayed, and
# saying so loudly is better than silently skipping a third of the archive.
MAPPERS = {
    "ted": from_ted,
    "pl_ezam": from_ezamowienia,
    "pl_atlas": from_atlas_pl,
}

# Marks a payload replay_key has not been handed and must read itself.
_UNREAD = object()

# PLACSP stores the normalised record rather than the source XML, because the
# connector parses CODICE during fetching. Replaying it needs no mapper.
PASSTHROUGH_SOURCES = {"es_placsp", "es_placsp_agg"}


@dataclass
class ReplayResult:
    scanned: int = 0
    rebuilt: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0

    def __str__(self) -> str:
        return (f"scanned {self.scanned}, rebuilt {self.rebuilt}, "
                f"unchanged {self.unchanged}, skipped {self.skipped}, "
                f"failed {self.failed}")


def _source_of(key: str) -> str:
    """`ted/2026/09/07/id.json` -> `ted`."""
    return key.split("/", 1)[0]


def _day_of(key: str) -> date | None:
    parts = key.split("/")
    if len(parts) < 4:
        return None
    try:
        return date(int(parts[1]), int(parts[2]), int(parts[3]))
    except (ValueError, IndexError):
        return None


def keys_from_store(
    store: RawStore, source: str | None = None,
    since: date | None = None, until: date | None = None,
) -> Iterator[str]:
    """Enumerate the object store, filtered by source and date, oldest first.

    Ordered by when each object was written, which is when we observed it. A
    notice can have several payloads in one day -- PLACSP publishes one entry
    per modification -- and replaying them out of order would number the
    versions wrongly and attribute the wrong changed_fields to each. Key order
    cannot supply it, because what separates those payloads is a content hash.
    """
    found = []

    def wanted(key: str) -> bool:
        day = _day_of(key)
        if since and (day is None or day < since):
            return False
        if until and (day is None or day > until):
            return False
        return True

    for key, written in store.listing(source or ""):
        if wanted(key):
            found.append((written, 0, key))
    # Bundles hold a day's payloads as lines of one object, so each is opened to
    # learn how many records it carries. Without this the disaster path -- the
    # database gone, the store the only copy -- would rebuild everything written
    # one object at a time and silently nothing written as a bundle: on 22
    # September 2026 that was 2.09 million notices of the TED history.
    for key, written in store.listing(source or "", suffix=BUNDLE_EXTENSION):
        if not wanted(key):
            continue
        for line in range(len(store._bundle_lines(key))):
            found.append((written, line, record_key(key, line)))
    for _, _, key in sorted(found):
        yield key


def keys_from_index(
    conn, source: str | None = None,
    since: date | None = None, until: date | None = None,
) -> Iterator[str]:
    """Read the keys out of `raw_ingest`, oldest first."""
    where, params = ["TRUE"], []
    if source:
        where.append("s.code = %s")
        params.append(source)
    if since:
        where.append("r.fetched_at >= %s")
        params.append(since)
    if until:
        where.append("r.fetched_at < %s + INTERVAL '1 day'")
        params.append(until)
    rows = conn.execute(
        f"""SELECT r.storage_key FROM raw_ingest r
              JOIN source s ON s.id = r.source_id
             WHERE {' AND '.join(where)}
             ORDER BY r.fetched_at""",
        params,
    ).fetchall()
    for row in rows:
        yield row["storage_key"]


def replay_key(conn, store: RawStore, key: str, result: ReplayResult,
               dry_run: bool = False, payload: Any = _UNREAD) -> None:
    """Rebuild one record. Ordering is identical to a live run, minus the fetch."""
    from .pipeline import _finalise

    source_code = _source_of(key)
    result.scanned += 1

    if source_code not in MAPPERS and source_code not in PASSTHROUGH_SOURCES:
        log.warning("no mapper for source %s (key %s)", source_code, key)
        result.skipped += 1
        return

    if payload is _UNREAD:
        try:
            payload = store.get(key)
        except Exception as exc:  # noqa: BLE001 - one unreadable object must not stop a rebuild
            log.error("cannot read %s: %s", key, exc)
            result.failed += 1
            return
    if isinstance(payload, Exception):
        log.error("cannot read %s: %s", key, payload)
        result.failed += 1
        return

    try:
        clean = strip_personal_data(payload)
        digest = content_hash(clean)
        if source_code in PASSTHROUGH_SOURCES:
            opportunity = db.opportunity_from_payload(clean)
        else:
            opportunity = MAPPERS[source_code](clean)
    except Exception as exc:  # noqa: BLE001
        log.error("cannot normalise %s: %s", key, exc)
        result.failed += 1
        return

    if dry_run:
        result.rebuilt += 1
        return

    src_id = db.source_id(conn, source_code)
    opportunity = _finalise(conn, opportunity, src_id)
    if not opportunity.is_defence:
        result.skipped += 1
        return

    opp_id, action = db.upsert_opportunity(conn, opportunity, digest, src_id)
    if action in ("unchanged", "stale"):
        # The notice's content has not changed, but what we conclude from it
        # can: a buyer added to the list makes an archived notice a buyer match
        # without any new version. Signals are derived, not source content, so
        # they are refreshed in place rather than versioned.
        db.refresh_classification(conn, opp_id, opportunity)
    # A replay into a populated database re-reads content that is already
    # archived, most of it older than the current version. Both are expected.
    if action in ("unchanged", "stale"):
        result.unchanged += 1
    else:
        result.rebuilt += 1


def _read_all(store: RawStore, keys: list[str], workers: int) -> list[Any]:
    """Fetch payloads concurrently, in the order given; a failure is returned, not raised."""
    def read(key: str) -> Any:
        try:
            return store.get(key)
        except Exception as exc:  # noqa: BLE001 - reported per key by replay_key
            return exc

    if workers <= 1:
        return [read(k) for k in keys]
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="replay") as pool:
        return list(pool.map(read, keys))


class StoreUnavailable(RuntimeError):
    """The object store stopped answering, as opposed to one object being unreadable."""


def _read_batch(store: RawStore, keys: list[str], workers: int,
                attempts: int, pause: float) -> list[Any]:
    """Read a batch, waiting out an outage rather than recording one.

    One unreadable object must not stop a replay, and still does not. But a batch
    in which every single read fails is not a batch of bad objects, it is a store
    that is not there -- and the replay used to treat it as the former. On
    13 September 2026 the network dropped 7,800 keys into a reclassification,
    and the run carried on through 147,000 more, marking every one failed in
    seconds each, having read none of them.

    Now such a batch is retried with growing pauses, and if the store never comes
    back the run stops loudly, leaving everything after it unread rather than
    wrongly counted.
    """
    import time

    payloads = _read_all(store, keys, workers)
    for attempt in range(1, attempts + 1):
        if not keys or not all(isinstance(p, Exception) for p in payloads):
            return payloads
        wait = min(pause * (2 ** (attempt - 1)), 300.0)
        log.warning("every read in a batch of %s failed (%s); store looks unavailable, "
                    "attempt %s of %s, waiting %.0fs",
                    len(keys), payloads[0], attempt, attempts, wait)
        time.sleep(wait)
        payloads = _read_all(store, keys, workers)
    if keys and all(isinstance(p, Exception) for p in payloads):
        raise StoreUnavailable(f"object store unreachable after {attempts} retries: "
                               f"{payloads[0]}")
    return payloads


def reprocess(
    *, source: str | None = None, since: date | None = None, until: date | None = None,
    from_store: bool = False, dry_run: bool = False, dsn: str | None = None,
    keys: Iterable[str] | None = None, workers: int = 1, batch: int = 200,
    outage_attempts: int = 8, outage_pause: float = 15.0,
) -> ReplayResult:
    """Replay raw payloads through normalisation, classification and the archive.

    Idempotent: content already archived at any version is unchanged, and content
    older than the current version is stale, so a replay into a populated
    database writes versions only for what is genuinely new. Before
    13 September 2026 only the latest version was compared, and a replay into a
    populated database would have re-archived history as change.

    `workers` reads payloads concurrently. Each is an object-storage round trip,
    about half a second from here, so a sequential replay of PLACSP's 136,000
    payloads would take nineteen hours. Records are still archived one at a
    time, in key order, because version order depends on it.
    """
    store = build_store()
    result = ReplayResult()
    with db.connect(dsn or settings().dsn) as conn:
        if keys is None:
            keys = (keys_from_store(store, source, since, until) if from_store
                    else keys_from_index(conn, source, since, until))
        chunk: list[str] = []

        def flush() -> None:
            payloads = _read_batch(store, chunk, workers, outage_attempts, outage_pause)
            for key, payload in zip(chunk, payloads, strict=True):
                replay_key(conn, store, key, result, dry_run=dry_run, payload=payload)
            if not dry_run:
                conn.commit()
            log.info("reprocess: %s", result)
            chunk.clear()

        for key in keys:
            chunk.append(key)
            if len(chunk) >= batch:
                flush()
        if chunk:
            flush()
    log.info("reprocess done: %s", result)
    return result


def defence_buyer_names(conn, country: str) -> set[str]:
    """Normalised names that resolve to a flagged defence buyer in one country."""
    rows = conn.execute(
        """SELECT a.normalised_name AS n FROM organisation_alias a
             JOIN organisation o ON o.id = a.organisation_id
            WHERE o.is_defence_buyer AND o.country = %s
           UNION
           SELECT lower(canonical_name) FROM organisation
            WHERE is_defence_buyer AND country = %s""",
        (country, country),
    ).fetchall()
    return {r["n"] for r in rows}


def atlas_buyer_keys(conn) -> list[str]:
    """Raw keys of Atlas rows whose buyer is on the defence list.

    The Atlas backfill landed 1.4 million payloads, and replaying all of them to
    find the buyer matches would read every one from object storage. The local
    Parquet files already carry the buyer, so candidates are found there and
    only their payloads are read.
    """
    from pathlib import Path

    from .normalise import normalise_org_name
    from .sources import atlas_pl

    wanted = defence_buyer_names(conn, "PL")
    ids: list[str] = []
    for filename in atlas_pl.YEAR_FILES.values():
        path = Path(settings().atlas_dir) / filename
        if not path.exists():
            log.warning("%s not present; its buyer matches cannot be replayed", path)
            continue
        for row in atlas_pl.read_rows(path, batch_size=50_000, columns=["id", "buyer"]):
            if normalise_org_name(row.get("buyer") or "") in wanted:
                ids.append(str(row["id"]))
    log.info("atlas: %s rows from listed defence buyers", len(ids))
    rows = conn.execute(
        """SELECT r.storage_key FROM raw_ingest r JOIN source s ON s.id = r.source_id
            WHERE s.code = 'pl_atlas' AND r.native_id = ANY(%s)
            ORDER BY r.fetched_at""",
        (ids,),
    ).fetchall()
    return [r["storage_key"] for r in rows]


def reclassify_buyers(workers: int = 64, dsn: str | None = None) -> dict[str, ReplayResult]:
    """Re-run classification wherever the defence buyer list can change it.

    Every stored payload of the live sources, which are small enough to replay
    whole, and of the Atlas backfill only the rows from listed buyers.
    """
    from .pipeline import seed_buyers

    seed_buyers()
    results: dict[str, ReplayResult] = {}
    for code in ("ted", "pl_ezam", "es_placsp", "es_placsp_agg"):
        log.info("reclassify: %s", code)
        results[code] = reprocess(source=code, workers=workers, dsn=dsn)
    with db.connect(dsn or settings().dsn) as conn:
        keys = atlas_buyer_keys(conn)
    log.info("reclassify: pl_atlas, %s candidate payloads", len(keys))
    results["pl_atlas"] = reprocess(keys=keys, workers=workers, dsn=dsn)
    return results


def _core(legal_basis: bool, military: bool, dual_use: bool) -> bool:
    return bool(legal_basis or (military and not dual_use))


def reclassify_serving(conn, *, source: str | None = None, dry_run: bool = True,
                       batch: int = 5000) -> dict[str, int]:
    """Re-run the classifier over the serving rows, reading no raw payload.

    Everything the classifier needs is on the row -- legal basis, CPV codes, the
    buyer and whether it is listed, the clearance flag -- so this takes seconds
    where a replay takes hours. It is how the rules of 12 October 2026 reach the
    notices already held: the military CPV as its own column, the buyer class,
    the dual-use demotion, and the end of "clearance plus civil CPV".

    A notice that stops qualifying keeps its row and its history: only the derived
    columns move, `refresh_classification` style, and no version is written.
    `dry_run` (the default) changes nothing and returns the same counts.
    """
    from .buyer_vocab import effective_buyer_class
    from .classify import classify

    counts: dict[str, int] = {
        "scanned": 0, "changed": 0, "defence_to_not": 0, "not_to_defence": 0,
        "demoted_to_dual_use": 0, "restored_from_dual_use": 0,
        "core_before": 0, "core_after": 0, "supply_after": 0,
        # the same stored rows under the rule before 14 October (the directive, or a
        # military CPV not demoted, whoever the buyer) and the two groups that rule moves
        "core_rule_of_13_oct": 0, "group_directive_civil_buyer": 0,
        "group_security_buyer_cpv": 0,
    }
    by_class: dict[str, int] = {}
    where, params = "o.id > %s", [0]
    if source:
        where += " AND o.source_id = (SELECT id FROM source WHERE code = %s)"
        params.append(source)
    while True:
        rows = conn.execute(
            f"""SELECT o.id, o.legal_basis, o.cpv_codes, o.country, o.buyer_name_raw,
                       o.is_defence, o.sig_legal_basis, o.sig_cpv, o.sig_buyer,
                       o.sig_clearance, o.sig_cpv_military, o.sig_cpv_adjacent,
                       o.sig_linked_defence, o.dual_use, o.buyer_class,
                       COALESCE(org.is_defence_buyer, FALSE) AS listed
                  FROM opportunity o
                  LEFT JOIN organisation org ON org.id = o.buyer_org_id
                 WHERE {where} ORDER BY o.id LIMIT %s""",
            params + [batch],
        ).fetchall()
        if not rows:
            break
        params[0] = rows[-1]["id"]
        for r in rows:
            counts["scanned"] += 1
            cls = effective_buyer_class(r["buyer_name_raw"], r["country"], bool(r["listed"]))
            sig = classify(
                legal_basis=r["legal_basis"], cpv_codes=r["cpv_codes"],
                buyer_is_defence=bool(r["listed"]),
                security_clearance_text="present" if r["sig_clearance"] else None,
                buyer_class=cls, linked_defence=bool(r["sig_linked_defence"]))
            new = (sig.is_defence, sig.legal_basis, sig.cpv, sig.buyer, sig.military_cpv,
                   sig.cpv_adjacent, sig.dual_use, cls)
            old = (r["is_defence"], bool(r["sig_legal_basis"]), bool(r["sig_cpv"]),
                   bool(r["sig_buyer"]), bool(r["sig_cpv_military"]),
                   bool(r["sig_cpv_adjacent"]), bool(r["dual_use"]), r["buyer_class"])
            counts["core_before"] += r["is_defence"] and _core(
                r["sig_legal_basis"], r["sig_cpv"], False)       # the rule it replaces
            if sig.is_defence:
                counts["core_rule_of_13_oct"] += _core(
                    sig.legal_basis, sig.military_cpv, sig.dual_use)
                counts["core_after"] += sig.in_core
                counts["supply_after"] += not sig.in_core and bool(
                    sig.buyer or sig.linked_defence or sig.scope_group)
                if sig.scope_group:
                    counts[f"group_{sig.scope_group}"] += 1
                by_class[cls] = by_class.get(cls, 0) + 1
            if new == old:
                continue
            counts["changed"] += 1
            counts["defence_to_not"] += bool(old[0] and not new[0])
            counts["not_to_defence"] += bool(new[0] and not old[0])
            counts["demoted_to_dual_use"] += bool(new[6] and not old[6])
            counts["restored_from_dual_use"] += bool(old[6] and not new[6])
            if not dry_run:
                conn.execute(
                    """UPDATE opportunity
                          SET is_defence = %s, sig_legal_basis = %s, sig_cpv = %s,
                              sig_buyer = %s, sig_cpv_military = %s, sig_cpv_adjacent = %s,
                              dual_use = %s, buyer_class = %s
                        WHERE id = %s""",
                    (*new, r["id"]))
        if not dry_run:
            conn.commit()
    counts.update({f"class_{k}": v for k, v in sorted(by_class.items())})
    return counts


def _from_stored_record(payload: dict[str, Any]):
    """PLACSP lands the record its connector parsed, not the Atom entry."""
    return db.opportunity_from_payload(payload)


# One mapper per source whose landed payloads can be requalified: the source's own record
# (TED, BOAMP, TenderNed, BZP, Atlas) or, for PLACSP, the parsed record.
REQUALIFY_MAPPERS = {
    "fr_boamp": from_boamp,
    "nl_tenderned": from_tenderned,
    "pl_ezam": from_ezamowienia,
    "es_placsp": _from_stored_record,
    "es_placsp_agg": _from_stored_record,
    "pl_atlas": from_atlas_pl,
    "ted": from_ted,
}
# The weekly job takes them in this order, TED last, so its long days cannot starve the rest.
# The marker `backfill_day` keeps for a requalified day, apart from the source's own code.
REQUALIFY_MARK = "-requalify"


def _candidates(conn, source: str, src_id: int, since: date | None, until: date | None,
                linked_only: bool = False) -> list[tuple[str, str]]:
    """(storage_key, native_id) of the newest raw payload of each notice of `source` that is
    not in `opportunity`, for a window of landing days (`linked_only`: the TED notices a
    national defence notice points at, whatever their day)."""
    where, params = ["r.source_id = %s"], [src_id]
    if linked_only:
        where.append("""r.native_id IN (SELECT ted_ref FROM opportunity
                                          WHERE is_defence AND ted_ref IS NOT NULL)""")
    else:
        if since:
            where.append("r.storage_key >= %s")
            params.append(f"{source}/{since:%Y/%m/%d}/")
        if until:
            nxt = until + timedelta(days=1)
            where.append("r.storage_key < %s")
            params.append(f"{source}/{nxt:%Y/%m/%d}/")
    rows = conn.execute(
        f"""SELECT DISTINCT ON (r.native_id) r.storage_key, r.native_id
              FROM raw_ingest r
             WHERE {' AND '.join(where)}
               AND NOT EXISTS (SELECT 1 FROM opportunity o
                                WHERE o.source_id = r.source_id AND o.native_id = r.native_id)
             ORDER BY r.native_id, r.id DESC""",
        params,
    ).fetchall()
    # Key order, so a bundle is fetched once and not once per notice.
    return sorted((r["storage_key"], r["native_id"]) for r in rows)


def _ted_candidates(conn, src_id: int, since: date | None, until: date | None,
                    linked_only: bool) -> list[tuple[str, str]]:
    return _candidates(conn, "ted", src_id, since, until, linked_only)


def requalify_source(conn, store: RawStore, source: str, *, since: date | None = None,
                     until: date | None = None, linked_only: bool = False,
                     dry_run: bool = True, workers: int = 1, batch: int = 200,
                     outage_attempts: int = 8, outage_pause: float = 15.0) -> dict[str, int]:
    """Insert the raw notices of `source` that the current rules qualify and `opportunity`
    lacks.

    The daily job lands every notice and keeps only the ones that qualify at the
    time, so a rule that widens -- a longer buyer list, a military CPV outside
    division 35, a notice that a national defence notice says it was forwarded as
    -- leaves qualifying notices only in the raw store. This reads exactly those:
    the newest payload of each notice of the window that has no `opportunity` row,
    through the same normaliser and classifier as a live run.

    One day at a time is the intended grain (`since`/`until` are landing days); `since`
    and `until` of one month is what `requalify_ted` was run with. `linked_only` (TED)
    ignores the window and takes the notices a national defence notice points at.
    `dry_run` (the default) does everything except keep it: the work is rolled back after
    every batch, so the counts are what a real run would produce.
    """
    from .pipeline import _finalise

    if source not in REQUALIFY_MAPPERS:
        raise ValueError(f"no requalify mapper for {source!r}")
    mapper = REQUALIFY_MAPPERS[source]
    src_id = db.source_id(conn, source)
    candidates = _candidates(conn, source, src_id, since, until, linked_only)
    counts: dict[str, int] = {
        "candidates": len(candidates), "unreadable": 0, "qualified": 0, "inserted": 0,
        "by_legal_basis": 0, "by_military_cpv": 0, "by_buyer": 0, "by_linked": 0,
        "by_dual_use": 0, "not_qualified": 0,
    }
    linked_refs: set[str] = set()
    if linked_only:
        linked_refs = {native_id for _, native_id in candidates}

    for start in range(0, len(candidates), batch):
        chunk = candidates[start:start + batch]
        payloads = _read_batch(store, [k for k, _ in chunk], workers,
                               outage_attempts, outage_pause)
        for (key, native_id), payload in zip(chunk, payloads, strict=True):
            if isinstance(payload, Exception):
                counts["unreadable"] += 1
                continue
            try:
                clean = strip_personal_data(payload)
                opp = mapper(clean)
                digest = content_hash(clean)
            except Exception as exc:  # noqa: BLE001 - one bad payload must not stop a window
                log.error("cannot normalise %s: %s", key, exc)
                counts["unreadable"] += 1
                continue
            opp = _finalise(conn, opp, src_id, linked_defence=native_id in linked_refs)
            if not opp.is_defence:
                counts["not_qualified"] += 1
                continue
            counts["qualified"] += 1
            counts["by_legal_basis"] += opp.sig_legal_basis
            counts["by_military_cpv"] += opp.sig_cpv_military
            counts["by_buyer"] += opp.sig_buyer
            counts["by_linked"] += opp.sig_linked_defence
            counts["by_dual_use"] += opp.dual_use
            _, action = db.upsert_opportunity(conn, opp, digest, src_id)
            # A PLACSP number held under its buyer-disambiguated spelling is "unchanged".
            counts["inserted"] += action == "new"
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
        log.info("requalify %s: %s", source, counts)
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return counts


def requalify_ted(conn, store: RawStore, *, since: date | None = None,
                  until: date | None = None, linked_only: bool = False,
                  dry_run: bool = True, workers: int = 1, batch: int = 200,
                  outage_attempts: int = 8, outage_pause: float = 15.0) -> dict[str, int]:
    """`requalify_source` for TED, which is where it began."""
    return requalify_source(conn, store, "ted", since=since, until=until,
                            linked_only=linked_only, dry_run=dry_run, workers=workers,
                            batch=batch, outage_attempts=outage_attempts,
                            outage_pause=outage_pause)


def rules_fingerprint(conn) -> str:
    """What the answer to "does this notice qualify" depends on, in one short string: the
    code of the classifier, the buyer vocabulary and the mappers, and the defence buyer list.

    A day examined under one fingerprint is not examined again under it. A rule or list
    change moves the fingerprint and the window is read again.
    # ponytail: the list is summarised by count, highest id and id sum, so a flag swapped
    # between two organisations of equal id sum is missed; use a hash of the ids if it ever is.
    """
    from . import buyer_vocab, classify, normalise

    digest = hashlib.sha1()
    for module in (classify, buyer_vocab, normalise):
        digest.update(Path(module.__file__).read_bytes())
    row = conn.execute(
        """SELECT count(*) AS n, coalesce(max(id), 0) AS top, coalesce(sum(id), 0) AS total
             FROM organisation WHERE is_defence_buyer""").fetchone()
    digest.update(f"{row['n']}:{row['top']}:{row['total']}".encode())
    return digest.hexdigest()[:10]


def requalify_window(conn, store: RawStore, source: str, since: date, until: date, *,
                     dry_run: bool = True, resume: bool = True, workers: int = 1,
                     today: date | None = None, **kw: Any) -> dict[str, int]:
    """`requalify_source` over a range of days, one day at a time.

    Bounded: a day's candidates are all that is held (a PLACSP day is about ten thousand
    keys, a TED day 3,600), and each day is committed on its own. Resumable: a day that is
    done under the current `rules_fingerprint` is marked in `backfill_day` (as
    `<source>-requalify-<fingerprint>`) and skipped, so an interrupted window continues and
    a weekly run reads only the days it has not seen. A day is marked only once it is two
    days old: TED's bundle for a day is written the morning after.
    """
    today = today or date.today()
    mark = f"{source}{REQUALIFY_MARK}-{rules_fingerprint(conn)}"
    done = db.backfill_days_done(conn, mark) if resume and not dry_run else set()
    total: dict[str, int] = {"days": 0, "skipped_days": 0}
    day = since
    while day <= until:
        if day in done:
            total["skipped_days"] += 1
        else:
            part = requalify_source(conn, store, source, since=day, until=day,
                                    dry_run=dry_run, workers=workers, **kw)
            for k, v in part.items():
                total[k] = total.get(k, 0) + v
            total["days"] += 1
            if not dry_run and part["unreadable"] == 0 and day <= today - timedelta(days=2):
                db.mark_backfill_day(conn, mark, day, part["candidates"])
        day += timedelta(days=1)
    return total


def requalify_recent(*, days: int = 30, sources: Iterable[str] | None = None,
                     dsn: str | None = None, workers: int = 8,
                     today: date | None = None, store: RawStore | None = None,
                     ) -> dict[str, dict[str, int]]:
    """The weekly job: every source's last `days` landing days, written."""
    today = today or date.today()
    store = store or build_store()
    out: dict[str, dict[str, int]] = {}
    with db.connect(dsn or settings().dsn) as conn:
        for source in sources or REQUALIFY_MAPPERS:
            out[source] = requalify_window(
                conn, store, source, today - timedelta(days=days), today,
                dry_run=False, workers=workers, today=today)
            log.info("requalify %s: %s", source, out[source])
    return out


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="dgate-reprocess")
    parser.add_argument("--source", help="source code, e.g. ted")
    parser.add_argument("--from", dest="since", type=date.fromisoformat)
    parser.add_argument("--to", dest="until", type=date.fromisoformat)
    parser.add_argument("--from-store", action="store_true",
                        help="enumerate object storage instead of raw_ingest; "
                             "the mode that survives losing the database")
    parser.add_argument("--dry-run", action="store_true",
                        help="read and normalise, write nothing")
    parser.add_argument("--workers", type=int, default=1,
                        help="payloads read from storage at once")
    parser.add_argument("--reclassify-buyers", action="store_true",
                        help="re-run classification wherever the buyer list can change it")
    parser.add_argument("--reclassify-serving", action="store_true",
                        help="re-run the classifier over the serving rows (no raw reads); "
                             "dry run unless --yes")
    parser.add_argument("--requalify-ted", action="store_true",
                        help="insert raw TED notices the current rules qualify and "
                             "opportunity lacks; one window at a time; dry run unless --yes")
    parser.add_argument("--requalify", action="store_true",
                        help="insert landed notices the current rules qualify and opportunity "
                             "lacks, any source, one day at a time, resumable; dry run unless "
                             "--yes. With --source, --from/--to or --days")
    parser.add_argument("--days", type=int,
                        help="for --requalify: the last N landing days instead of --from/--to")
    parser.add_argument("--no-resume", action="store_true",
                        help="for --requalify: read days already done under the current rules")
    parser.add_argument("--month", help="landing month for --requalify-ted, YYYY-MM")
    parser.add_argument("--linked", action="store_true",
                        help="for --requalify-ted: the TED notices a national defence "
                             "notice points at, whatever their month")
    parser.add_argument("--yes", action="store_true",
                        help="write; the modes above only report without it")
    args = parser.parse_args(argv)

    if args.reclassify_serving:
        with db.connect(settings().dsn) as conn:
            counts = reclassify_serving(conn, source=args.source, dry_run=not args.yes)
        print(("applied" if args.yes else "dry run, nothing written") + ":")
        for k, v in counts.items():
            print(f"  {k}: {v}")
        return 0

    if args.requalify:
        today = date.today()
        if args.days:
            since, until = today - timedelta(days=args.days), today
        elif args.since:
            since, until = args.since, args.until or today
        else:
            parser.error("--requalify needs --days, or --from (and optionally --to)")
        sources = [args.source] if args.source else list(REQUALIFY_MAPPERS)
        bad = [x for x in sources if x not in REQUALIFY_MAPPERS]
        if bad:
            parser.error(f"cannot requalify {bad}; choose from {', '.join(REQUALIFY_MAPPERS)}")
        failed = 0
        print(("applied" if args.yes else "dry run, nothing written") + f" ({since}..{until}):")
        with db.connect(settings().dsn) as conn:
            store = build_store()
            for source in sources:
                counts = requalify_window(
                    conn, store, source, since, until, dry_run=not args.yes,
                    resume=not args.no_resume, workers=max(args.workers, 1))
                failed += counts["unreadable"]
                print(f"  {source}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        return 0 if failed == 0 else 1

    if args.requalify_ted:
        since = until = None
        if args.month:
            since = date.fromisoformat(args.month + "-01")
            until = (since.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        elif not args.linked:
            since, until = args.since, args.until
        if not args.linked and since is None and until is None:
            parser.error("--requalify-ted needs --month, --from/--to, or --linked")
        with db.connect(settings().dsn) as conn:
            counts = requalify_ted(conn, build_store(), since=since, until=until,
                                   linked_only=args.linked, dry_run=not args.yes,
                                   workers=max(args.workers, 1))
        print(("applied" if args.yes else "dry run, nothing written")
              + f" ({since or ''}..{until or ''}{' linked' if args.linked else ''}):")
        for k, v in counts.items():
            print(f"  {k}: {v}")
        return 0 if counts["unreadable"] == 0 else 1

    if args.reclassify_buyers:
        results = reclassify_buyers(workers=max(args.workers, 1))
        for code, res in results.items():
            print(f"{code}: {res}")
        return 0 if all(r.failed == 0 for r in results.values()) else 1

    result = reprocess(source=args.source, since=args.since, until=args.until,
                       from_store=args.from_store, dry_run=args.dry_run,
                       workers=args.workers)
    print(result)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
