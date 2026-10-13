"""Database layer.

The one non-obvious piece here is upsert_opportunity. It is the mechanism that
turns a daily feed into an archive, and it has to satisfy three properties:

  - re-ingesting an unchanged notice must produce no new version
  - a changed notice must produce a new version listing what changed
  - the previous version must be closed off with valid_to, not overwritten

Everything else in this file is plumbing.
"""

from __future__ import annotations

import hashlib
import logging
from contextlib import contextmanager
from dataclasses import asdict, fields, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .normalise import Opportunity, normalise_identifier, normalise_org_name

log = logging.getLogger(__name__)

# Fields compared to decide whether a notice materially changed. Deliberately
# excludes enrichment output: a re-translation is not a change to the notice.
VERSIONED_FIELDS = [
    "title_original", "buyer_name_raw", "country", "procedure_type",
    "legal_basis", "value_amount", "value_currency", "published_at",
    "deadline_at", "cpv_codes", "source_url", "status",
]

# Version note kinds that say "this version is not something the source did":
# re-read content, history arriving late, and our own bulk re-mapping. A client
# that counts amendments or reports "changes since your last visit" skips them.
NOT_AMENDMENT_NOTES = ("reread", "out_of_order", "remapped")


# Sources whose identifier is a file number the buyer itself assigns, so it is
# unique only within that buyer. In the Catalan feed, `2582/2026` is both a
# police-vest supply of the Ajuntament del Prat and the park works of the
# Ajuntament de la Garriga; under (source, native_id) alone, two defence notices
# like that would be one row with one history. Found by the spot check of
# 11 October 2026.
LOCAL_KEY_SOURCES = {"es_placsp", "es_placsp_agg"}


def _buyer_key(name: str | None) -> str:
    return normalise_org_name(name or "")


def _disambiguated_id(opp: Opportunity) -> str:
    """The number, made unique by who filed it: `2582/2026#3f9a1c07`."""
    token = hashlib.sha1(_buyer_key(opp.buyer_name_raw).encode("utf-8")).hexdigest()[:8]
    return f"{opp.native_id}#{token}"


def _instant(value: Any) -> datetime | None:
    """A stored ISO deadline as an instant, so +02:00 and Z spellings of one moment match."""
    if not isinstance(value, str) or len(value) <= 10:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def same_value(field: str, before: Any, after: Any) -> bool:
    """Whether two stored values of a field say the same thing.

    Not byte equality: a CPV list is a set (the sources re-order it between
    publications, and all 19 CPV "changes" in the archive on 12 October 2026 were
    re-orderings), a deadline is an instant (the same moment written with another
    UTC offset is not a change), and None, "" and [] are all "not stated". A change
    whose two sides would render identically is not a change.
    """
    if before == after:
        return True
    empty = (None, "", [])
    if before in empty and after in empty:
        return True
    if isinstance(before, list) and isinstance(after, list):
        return {str(v) for v in before} == {str(v) for v in after}
    if field == "deadline_at":
        a, b = _instant(before), _instant(after)
        return a is not None and a == b
    return False


def changed_fields(previous: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    """The versioned fields whose value differs by `same_value`."""
    return [f for f in VERSIONED_FIELDS if not same_value(f, previous.get(f), payload.get(f))]


def _jsonable(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    # A money column comes back from Postgres as Decimal and goes in as float.
    # Comparing the two as they are makes an unchanged amount look changed.
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


# Migration 0029's derived fields are absent from a payload while empty, so the hash
# taken before classification (PLACSP hashes the payload) does not move for a record
# that has none. `buyer_identifier` is handled where the TED mapper's own fields are.
_EMPTY_WHILE_UNSET = ("sig_linked_defence", "dual_use", "buyer_class")
# Pure functions of `cpv_codes`, re-derived whenever an Opportunity is built
# (Opportunity.__post_init__): never in a payload, so no hash moves for them.
_NEVER_IN_PAYLOAD = ("sig_cpv_military", "sig_cpv_adjacent")


def _drop_classification_keys(payload: dict[str, Any]) -> None:
    for key in _EMPTY_WHILE_UNSET:
        if not payload.get(key):
            payload.pop(key, None)
    for key in _NEVER_IN_PAYLOAD:
        payload.pop(key, None)


def opportunity_payload(opp: Opportunity) -> dict[str, Any]:
    payload = {k: _jsonable(v) for k, v in asdict(opp).items()}
    _drop_classification_keys(payload)
    # PLACSP hashes this payload, so a field added later must not move the hash
    # of every record that does not have it: an empty link is simply absent.
    if payload.get("ted_ref") is None:
        payload.pop("ted_ref", None)
    if payload.get("related_native_id") is None:
        payload.pop("related_native_id", None)
    if payload.get("source_updated_at") is None:
        payload.pop("source_updated_at", None)
    # Same rule for the attributes only some sources set (TED's, migration 0030,
    # and the buyer's registration number): absent while empty, so no hash moves.
    for name in ("buyer_identifier", "notice_subtype", "procedure_identifier",
                 "lot_count", "value_kind"):
        if payload.get(name) is None:
            payload.pop(name, None)
    return payload


# Fields that come back out of a payload as strings and have to become dates
# and datetimes again. Everything else round-trips as itself.
_DATE_FIELDS = {"published_at"}
_DATETIME_FIELDS = {"deadline_at", "source_updated_at"}


def opportunity_from_payload(payload: dict[str, Any]) -> Opportunity:
    """The inverse of ``opportunity_payload``.

    Sources whose connectors parse during fetching, PLACSP among them, land the
    normalised record rather than the source document. Rebuilding the database
    from raw storage therefore has to read that shape back, and it has to
    tolerate an old payload written before a field existed: an archive is only
    replayable if yesterday's payload still loads into today's code.
    """
    known = {f.name for f in fields(Opportunity)}
    values: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in known:
            continue        # a field this version no longer has
        if value is None:
            values[key] = None
        elif key in _DATE_FIELDS and isinstance(value, str):
            values[key] = date.fromisoformat(value[:10])
        elif key in _DATETIME_FIELDS and isinstance(value, str):
            values[key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            values[key] = value
    missing = {"source_code", "native_id", "buyer_name_raw", "title_original"} - values.keys()
    if missing:
        raise ValueError(f"payload is missing required fields: {sorted(missing)}")
    return Opportunity(**values)


@contextmanager
def connect(dsn: str) -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(dsn, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def source_id(conn: psycopg.Connection, code: str) -> int:
    row = conn.execute("SELECT id FROM source WHERE code = %s", (code,)).fetchone()
    if not row:
        raise KeyError(f"unknown source: {code}")
    return row["id"]


# --------------------------------------------------------- ingest runs

def start_run(conn: psycopg.Connection, code: str, expected_min: int | None = None) -> int:
    row = conn.execute(
        "INSERT INTO ingest_run (source_id, expected_min) VALUES (%s, %s) RETURNING id",
        (source_id(conn, code), expected_min),
    ).fetchone()
    conn.commit()
    return row["id"]


def finish_run(
    conn: psycopg.Connection, run_id: int, *,
    fetched: int, new: int, changed: int,
    status: str = "success", error: str | None = None,
) -> None:
    """Close a run and decide whether it should have been loud.

    A run that completes with fewer records than its floor is marked partial,
    not success. Silent under-collection is the failure mode that quietly
    destroys a coverage promise, so it must not look like a green tick.
    """
    row = conn.execute(
        "SELECT expected_min FROM ingest_run WHERE id = %s", (run_id,)
    ).fetchone()
    floor = row["expected_min"] if row else None
    if status == "success" and floor is not None and fetched < floor:
        status = "partial"
        error = error or f"fetched {fetched} below floor {floor}"
        log.warning("ingest run %s under floor: %s < %s", run_id, fetched, floor)

    conn.execute(
        # clock_timestamp(), not now(): now() is the transaction's start time,
        # and an ingest runs inside a long transaction by design. Recorded with
        # now(), a PLACSP run that took forty minutes closed with a finished_at
        # three seconds after it started, which made every duration in the
        # operational history a fiction and would have hidden a source slowing
        # down until it stopped finishing at all.
        """UPDATE ingest_run
              SET finished_at = clock_timestamp(), status = %s, records_fetched = %s,
                  records_new = %s, records_changed = %s, error_message = %s
            WHERE id = %s""",
        (status, fetched, new, changed, error, run_id),
    )
    conn.commit()


def record_progress(conn: psycopg.Connection, run_id: int, *,
                    fetched: int, new: int, changed: int) -> None:
    """Write a run's counters mid-flight, so a long run is not opaque.

    Called from the ingest checkpoint. Without it a run in progress reports
    zero records however far along it is, which is indistinguishable from a run
    that is stuck -- a distinction that cost an hour of diagnosis.
    """
    conn.execute(
        """UPDATE ingest_run
              SET records_fetched = %s, records_new = %s, records_changed = %s
            WHERE id = %s""",
        (fetched, new, changed, run_id),
    )


def close_interrupted_runs(conn: psycopg.Connection) -> list[int]:
    """Fail any run still marked `running`, and say which.

    A run is only ever closed by the process that opened it, so a process that
    is killed -- a container recreated, a machine switched off -- leaves its row
    `running` for ever. Nothing reaps it, and `source_run_status` reads the
    latest run per source, so one interrupted run makes that source look
    degraded permanently and every subsequent alert becomes noise.

    Called at worker start, where "still running" can only mean "was killed",
    because this process has not started anything yet.
    """
    rows = conn.execute(
        """UPDATE ingest_run
              SET status = 'failed', finished_at = clock_timestamp(),
                  error_message = coalesce(error_message,
                      'interrupted: the process that opened this run did not close it')
            WHERE status = 'running'
        RETURNING id""",
    ).fetchall()
    conn.commit()
    ids = [r["id"] for r in rows]
    if ids:
        log.warning("closed %s interrupted ingest run(s): %s", len(ids), ids)
    return ids


# ------------------------------------------------------ organisations

#: how sure each way of reaching an organisation is. Stored on the alias, so a
#: later look at one can say how it was decided.
CONF_EXACT_NAME = 0.95
CONF_IDENTIFIER = 0.97          # the buyer's own registration number, as the notice states it
CONF_IDENTIFIER_ATTACHED = 0.90  # a number attached to a body we already knew by name
TRIGRAM_CANDIDATE_MIN = 0.90


def _live(conn: psycopg.Connection, org_id: int) -> int:
    """The organisation a row stands for now: follows `merged_into` to its end."""
    for _ in range(8):
        row = conn.execute("SELECT merged_into FROM organisation WHERE id = %s",
                           (org_id,)).fetchone()
        if not row or row["merged_into"] is None:
            return org_id
        org_id = row["merged_into"]
    return org_id


def _tokens(norm: str) -> set[str]:
    return {t for t in norm.replace("-", " ").split() if len(t) >= 4}


def names_compatible(a: str, b: str) -> bool:
    """Whether two normalised names could be the same body: they share a word of four
    letters or more (a name with no such word is compatible with nothing).

    The guard on trusting an identifier. A notice that carries the number of a
    central purchasing body under the name of one of its members would otherwise
    be filed under the purchasing body. A pair with nothing in common is left to
    the name stages; the same body under two languages is merely not merged here.
    """
    # Both names must have a word to share: a name with none of four letters or more
    # ("MON", "DGA") says nothing a stated number should be trusted against.
    return bool(_tokens(a) & _tokens(b))


def add_merge_candidate(conn: psycopg.Connection, a: int, b: int, *, method: str,
                        confidence: float, evidence: str, detected_by: str) -> None:
    """Record that two organisations may be one. Never merges anything."""
    if a == b:
        return
    conn.execute(
        """INSERT INTO organisation_merge_candidate
             (organisation_id, candidate_org_id, match_method, confidence, evidence, detected_by)
           VALUES (LEAST(%s::bigint, %s::bigint), GREATEST(%s::bigint, %s::bigint), %s, %s, %s, %s)
           ON CONFLICT (organisation_id, candidate_org_id, match_method) DO NOTHING""",
        (a, b, a, b, method, round(confidence, 2), evidence[:500], detected_by),
    )


def _note_similar_names(conn: psycopg.Connection, org_id: int, norm: str, country: str) -> None:
    """A new organisation whose name is nearly one already held: a candidate pair.

    Trigram similarity of 0.90 or more within one country, found through the
    index on `canonical_name`. It only proposes: two municipalities named
    "Szkola Podstawowa nr 1" and "Szkola Podstawowa nr 2" are 0.9 apart and not
    one body, which is why a person decides.
    """
    conn.execute("SELECT set_config('pg_trgm.similarity_threshold', %s, false)",
                 (str(TRIGRAM_CANDIDATE_MIN),))
    rows = conn.execute(
        """SELECT id, canonical_name, similarity(canonical_name, %s) AS sim
             FROM organisation
            WHERE country = %s AND id <> %s AND merged_into IS NULL AND canonical_name %% %s
            ORDER BY sim DESC LIMIT 5""",
        (norm, country, org_id, norm),
    ).fetchall()
    for r in rows:
        add_merge_candidate(
            conn, org_id, r["id"], method="trigram", confidence=float(r["sim"]),
            evidence=f"{norm!r} and {r['canonical_name']!r} in {country}",
            detected_by="resolve_organisation")


def _record_alias(conn: psycopg.Connection, org_id: int, raw_name: str, norm: str,
                  src_id: int | None, country: str, method: str, confidence: float) -> bool:
    row = conn.execute(
        """INSERT INTO organisation_alias
             (organisation_id, raw_name, normalised_name, source_id,
              country_hint, match_method, confidence)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (normalised_name, country_hint, source_id) DO NOTHING
           RETURNING id""",
        (org_id, raw_name, norm, src_id, country, method, confidence),
    ).fetchone()
    return row is not None


def resolve_organisation(
    conn: psycopg.Connection, raw_name: str, country: str | None,
    *, src_id: int | None = None, identifier: str | None = None,
) -> int | None:
    """The resolution cascade: identifier, alias, exact normalised name.

    Stage 0, identifier first: when the notice states the buyer's registration
    or tax number and an organisation already carries it, that organisation is
    the buyer, whatever the name says -- provided the name shares a word with
    what we hold (`names_compatible`). A number met for the first time is
    attached to the organisation the name resolves to, if that has none, with
    method `identifier` and its confidence stored; if that organisation already
    carries a different number it is a different body with the same name, and
    gets an organisation of its own.

    Fuzzy, embedding and LLM stages are deliberately absent. Names that are
    nearly equal are written to `organisation_merge_candidate` and wait for a
    person: a poisoned alias table is worse than none.
    """
    if not raw_name or not country:
        return None
    norm = normalise_org_name(raw_name)
    if not norm:
        return None
    ident = normalise_identifier(identifier, country)

    if ident:
        row = conn.execute(
            """SELECT id, canonical_name FROM organisation
                WHERE country = %s AND national_reg_no = %s""",
            (country, ident),
        ).fetchone()
        if row and names_compatible(norm, row["canonical_name"]):
            org_id = _live(conn, row["id"])
            if not _record_alias(conn, org_id, raw_name, norm, src_id, country,
                                 "identifier", CONF_IDENTIFIER):
                other = conn.execute(
                    """SELECT organisation_id FROM organisation_alias
                        WHERE normalised_name = %s AND country_hint = %s
                          AND source_id IS NOT DISTINCT FROM %s""",
                    (norm, country, src_id),
                ).fetchone()
                if other and other["organisation_id"] != org_id:
                    add_merge_candidate(
                        conn, org_id, other["organisation_id"], method="identifier",
                        confidence=CONF_IDENTIFIER,
                        evidence=f"{norm!r} is filed under another organisation but "
                                 f"carries identifier {ident} in {country}",
                        detected_by="resolve_organisation")
            return org_id
        if row:
            # The number belongs to a body whose name shares nothing with this one:
            # not trusted here. The name stages decide, without the number, and the
            # pair is noted for a person.
            org_id = resolve_organisation(conn, raw_name, country, src_id=src_id)
            if org_id is not None:
                add_merge_candidate(
                    conn, org_id, row["id"], method="identifier_name_mismatch", confidence=0.50,
                    evidence=f"{norm!r} states identifier {ident} in {country}, held by "
                             f"{row['canonical_name']!r}",
                    detected_by="resolve_organisation")
            return org_id

    row = conn.execute(
        """SELECT organisation_id FROM organisation_alias
            WHERE normalised_name = %s AND (country_hint = %s OR country_hint IS NULL)
            ORDER BY confidence DESC LIMIT 1""",
        (norm, country),
    ).fetchone()
    if row:
        org_id = _live(conn, row["organisation_id"])
        return _attach_identifier(conn, org_id, raw_name, norm, src_id, country, ident)

    row = conn.execute(
        """SELECT id FROM organisation
            WHERE country = %s AND lower(canonical_name) = %s AND merged_into IS NULL
            ORDER BY id LIMIT 1""",
        (country, norm),
    ).fetchone()
    created = False
    if row:
        org_id = row["id"]
    else:
        org_id = _new_organisation(conn, norm, country, ident)
        created = True

    _record_alias(conn, org_id, raw_name, norm, src_id, country, "exact_name", CONF_EXACT_NAME)
    if created:
        _note_similar_names(conn, org_id, norm, country)
        return org_id
    return _attach_identifier(conn, org_id, raw_name, norm, src_id, country, ident)


def _new_organisation(conn: psycopg.Connection, norm: str, country: str,
                      ident: str | None) -> int:
    return conn.execute(
        """INSERT INTO organisation
             (canonical_name, country, confidence, review_status, national_reg_no,
              identifier_method, identifier_confidence)
           VALUES (%s, %s, 0.95, 'auto', %s, %s, %s) RETURNING id""",
        (norm, country, ident, "identifier" if ident else None,
         CONF_IDENTIFIER_ATTACHED if ident else None),
    ).fetchone()["id"]


def _attach_identifier(conn: psycopg.Connection, org_id: int, raw_name: str, norm: str,
                       src_id: int | None, country: str, ident: str | None) -> int:
    """Give the organisation the notice's identifier, or split off a namesake."""
    if not ident:
        return org_id
    cur = conn.execute(
        "SELECT national_reg_no FROM organisation WHERE id = %s", (org_id,)
    ).fetchone()
    if cur is None or cur["national_reg_no"] == ident:
        return org_id
    if cur["national_reg_no"] is None:
        conn.execute(
            """UPDATE organisation
                  SET national_reg_no = %s, identifier_method = 'identifier',
                      identifier_confidence = %s
                WHERE id = %s AND national_reg_no IS NULL""",
            (ident, CONF_IDENTIFIER_ATTACHED, org_id),
        )
        return org_id
    # Same name, a different registered number: another body. It is reachable by
    # its number; the name keeps pointing at the first one.
    other = _new_organisation(conn, norm, country, ident)
    add_merge_candidate(
        conn, org_id, other, method="same_name_different_identifier", confidence=0.50,
        evidence=f"{norm!r} in {country} carries {cur['national_reg_no']} and {ident}",
        detected_by="resolve_organisation")
    return other


def merge_organisations(
    conn: psycopg.Connection, keep: int, absorbed: int, *,
    method: str, confidence: float, evidence: str, detected_by: str,
) -> dict[str, int]:
    """Make `absorbed` an alias of `keep`. Nothing is deleted.

    The absorbed row stays, marked `merged_into` with the method and confidence;
    its aliases and the serving rows that point at it are re-pointed at `keep`
    (the alias remembers where it came from in `prev_organisation_id`). Version
    payloads are history and are not touched: they keep the id they were
    archived with, which is how a merge is undone.

    Returns what moved.
    """
    if keep == absorbed:
        raise ValueError("an organisation cannot be merged into itself")
    rows = {r["id"]: r for r in conn.execute(
        """SELECT id, country, national_reg_no, is_defence_buyer, merged_into
             FROM organisation WHERE id = ANY(%s) FOR UPDATE""",
        ([keep, absorbed],)).fetchall()}
    k, a = rows.get(keep), rows.get(absorbed)
    if k is None or a is None:
        raise ValueError("unknown organisation")
    if k["merged_into"] is not None or a["merged_into"] is not None:
        raise ValueError("an organisation that is already merged cannot be merged again")
    if k["country"] != a["country"]:
        raise ValueError("organisations of different countries are never merged")
    if (k["national_reg_no"] and a["national_reg_no"]
            and k["national_reg_no"] != a["national_reg_no"]):
        raise ValueError("two different registered numbers: not the same body")

    aliases = conn.execute(
        """UPDATE organisation_alias
              SET prev_organisation_id = COALESCE(prev_organisation_id, organisation_id),
                  organisation_id = %s
            WHERE organisation_id = %s RETURNING 1""",
        (keep, absorbed)).fetchall()
    notices = conn.execute(
        "UPDATE opportunity SET buyer_org_id = %s WHERE buyer_org_id = %s RETURNING 1",
        (keep, absorbed)).fetchall()
    if a["national_reg_no"] and not k["national_reg_no"]:
        conn.execute("UPDATE organisation SET national_reg_no = NULL WHERE id = %s", (absorbed,))
        conn.execute(
            """UPDATE organisation SET national_reg_no = %s, identifier_method = %s,
                      identifier_confidence = %s WHERE id = %s""",
            (a["national_reg_no"], method, confidence, keep))
    if a["is_defence_buyer"] and not k["is_defence_buyer"]:
        conn.execute("UPDATE organisation SET is_defence_buyer = TRUE WHERE id = %s", (keep,))
    conn.execute(
        """UPDATE organisation
              SET merged_into = %s, merge_method = %s, merge_confidence = %s, merged_at = now()
            WHERE id = %s""",
        (keep, method, round(confidence, 2), absorbed))
    conn.execute(
        """INSERT INTO organisation_merge_candidate
             (organisation_id, candidate_org_id, match_method, confidence, evidence,
              status, detected_by, decided_at)
           VALUES (LEAST(%s::bigint, %s::bigint), GREATEST(%s::bigint, %s::bigint),
                   %s, %s, %s, 'merged', %s, now())
           ON CONFLICT (organisation_id, candidate_org_id, match_method)
           DO UPDATE SET status = 'merged', decided_at = now()""",
        (keep, absorbed, keep, absorbed, method, round(confidence, 2), evidence[:500],
         detected_by))
    return {"aliases": len(aliases), "notices": len(notices)}


def is_defence_buyer(conn: psycopg.Connection, org_id: int | None) -> bool:
    if org_id is None:
        return False
    row = conn.execute(
        "SELECT is_defence_buyer FROM organisation WHERE id = %s", (org_id,)
    ).fetchone()
    return bool(row and row["is_defence_buyer"])


# ------------------------------------------------------- the archive

def _serving_columns(opp: Opportunity) -> dict[str, Any]:
    """The `opportunity` row's columns for a record: the serving layer's view."""
    return dict(
        buyer_name_raw=opp.buyer_name_raw, country=opp.country,
        title_original=opp.title_original, title_en=opp.title_en,
        summary_en=opp.summary_en, original_language=opp.original_language,
        procedure_type=opp.procedure_type, legal_basis=opp.legal_basis,
        value_amount=opp.value_amount, value_currency=opp.value_currency,
        published_at=opp.published_at, deadline_at=opp.deadline_at,
        cpv_codes=opp.cpv_codes, is_defence=opp.is_defence,
        sig_legal_basis=opp.sig_legal_basis, sig_cpv=opp.sig_cpv,
        sig_buyer=opp.sig_buyer, sig_clearance=opp.sig_clearance,
        subcontracting_signal=opp.subcontracting_signal,
        security_clearance_required=opp.security_clearance_required,
        source_url=opp.source_url, buyer_org_id=opp.buyer_org_id,
        status=opp.status, status_native=opp.status_native,
        ted_ref=opp.ted_ref, related_native_id=opp.related_native_id,
        notice_subtype=opp.notice_subtype, procedure_identifier=opp.procedure_identifier,
        lot_count=opp.lot_count, value_kind=opp.value_kind,
        buyer_identifier=opp.buyer_identifier,
    )


def _classification_columns(opp: Opportunity) -> dict[str, Any]:
    """The serving columns migration 0029 added for the classification, kept apart
    from `_serving_columns` and merged where that is used."""
    return dict(
        sig_cpv_military=opp.sig_cpv_military, sig_cpv_adjacent=opp.sig_cpv_adjacent,
        sig_linked_defence=opp.sig_linked_defence, dual_use=opp.dual_use,
        buyer_class=opp.buyer_class,
    )


def refresh_classification(conn: psycopg.Connection, opp_id: int, opp: Opportunity) -> None:
    """Update the derived signals on the serving row, without a version.

    A version records a change in what the source said. The classification is
    our conclusion from it, and it moves when the classifier or the buyer list
    does: on 13 September 2026 the list went from empty to 111 buyers, and every
    archived notice from those buyers still carried sig_buyer = false.
    """
    conn.execute(
        """UPDATE opportunity
              SET is_defence = %s, sig_legal_basis = %s, sig_cpv = %s, sig_buyer = %s,
                  sig_clearance = %s, buyer_org_id = %s,
                  sig_cpv_military = %s, sig_cpv_adjacent = %s,
                  sig_linked_defence = sig_linked_defence OR %s,
                  dual_use = %s, buyer_class = %s
            WHERE id = %s""",
        (opp.is_defence, opp.sig_legal_basis, opp.sig_cpv, opp.sig_buyer,
         opp.sig_clearance, opp.buyer_org_id, opp.sig_cpv_military, opp.sig_cpv_adjacent,
         opp.sig_linked_defence, opp.dual_use, opp.buyer_class, opp_id),
    )


# Columns of the serving row that are links and attributes rather than the notice's own
# versioned facts (`opportunity_payload` leaves them out while empty).
KEPT_WHEN_ABSENT = frozenset({
    "ted_ref", "procedure_identifier", "related_native_id", "buyer_identifier",
    "lot_count", "notice_subtype", "value_kind",
})

# What a PLACSP re-reading can move without the publisher having said anything: the
# fields the mapper of 12 October 2026 owns. A version that changed only these, with the
# entry's own update stamp unchanged, is the mapper's correction and not an amendment.
MAPPER_OWNED = frozenset({
    "value_amount", "value_currency", "procedure_type", "legal_basis", "published_at",
})


def append_version(conn: psycopg.Connection, opp_id: int, opp: Opportunity,
                   raw_hash: str, changed: list[str], *, after: int) -> int:
    """Close the open version, append the next one, and move the serving row.

    The only code that writes a version after the first. Ingestion reaches it
    through upsert_opportunity once a change is established; a repair reaches
    it directly, having established the change another way. One path means the
    two cannot disagree about how a version is written.
    """
    payload = opportunity_payload(opp)
    cols = {**_serving_columns(opp), **_classification_columns(opp)}
    version = after + 1
    # One instant closes the old version and opens the new one, so the two
    # intervals meet exactly. Taken from the database's own clock rather than
    # this process's, because every other timestamp in the archive is, and two
    # clocks in one column is a drift nobody would think to look for.
    #
    # clock_timestamp(), not now(): now() would return the transaction's start,
    # which during an ingest is minutes or hours before the change was seen.
    closed = conn.execute(
        """UPDATE opportunity_version SET valid_to = clock_timestamp()
            WHERE opportunity_id = %s AND valid_to IS NULL
        RETURNING valid_to""",
        (opp_id,),
    ).fetchone()
    # No previous version means nothing was closed; the column defaults apply.
    at = closed["valid_to"] if closed else None
    conn.execute(
        """INSERT INTO opportunity_version
             (opportunity_id, version, payload, raw_hash, changed_fields,
              observed_at, valid_from)
           VALUES (%s, %s, %s, %s, %s,
                   coalesce(%s, clock_timestamp()), coalesce(%s, clock_timestamp()))""",
        (opp_id, version, Jsonb(payload), raw_hash, changed, at, at),
    )
    # A link or an attribute is not erased by a version that does not state it: a record
    # built from a payload without `ted_ref` (a PLACSP notice, whose link `link_twins`
    # set outside any version) would put NULL over it while `twin_method` stayed.
    sets = ", ".join(f"{k} = COALESCE(%s, {k})" if k in KEPT_WHEN_ABSENT else f"{k} = %s"
                     for k in cols)
    conn.execute(
        f"UPDATE opportunity SET {sets}, current_version = %s WHERE id = %s",
        list(cols.values()) + [version, opp_id],
    )
    return version


def annotate_versions(conn: psycopg.Connection, version_ids: list[int],
                      kind: str, note: str) -> int:
    """Attach one note of one kind to each of the given versions; returns how many
    were annotated now.

    The archive cannot be edited, so a version it should not have counted is
    annotated and the readers skip it (migration 0006, 0028). `remapped` is for a
    bulk correction that re-derives status, value or dates from the payload a
    notice already had: the publisher amended nothing, so the corrected version
    must not read as an amendment. Idempotent: one note per version and kind.
    """
    if not version_ids:
        return 0
    return conn.execute(
        """INSERT INTO opportunity_version_note (opportunity_version_id, kind, note)
           SELECT v, %s, %s FROM unnest(%s::bigint[]) AS v
           ON CONFLICT (opportunity_version_id, kind) DO NOTHING""",
        (kind, note, list(version_ids)),
    ).rowcount


def _same_entry_state(prev: dict[str, Any], payload: dict[str, Any]) -> bool:
    """Whether the source's own update stamp of the incoming record is the held one.

    Only a record that carries a stamp can say (PLACSP's Atom `updated`). A version
    archived before the stamp was kept has none, and its publication date was the feed's
    update date then: that stands in for it, by the day.
    """
    new = _instant(payload.get("source_updated_at"))
    if new is None:
        return False
    old = _instant(prev.get("source_updated_at"))
    if old is not None:
        return old == new
    try:
        held = date.fromisoformat(str(prev.get("published_at"))[:10])
    except ValueError:
        return False
    # The legacy date is the date part of the stamp's own text, and `new` keeps the
    # stamp's offset, so its `.date()` is that same local day.
    return held == new.date()


def upsert_opportunity(
    conn: psycopg.Connection, opp: Opportunity, raw_hash: str, src_id: int,
) -> tuple[int, str]:
    """Insert or version an opportunity.

    Returns (id, action), action being "new", "changed", "unchanged" -- also for
    content already archived at an earlier version -- or "stale" for content
    older than the current version by the source's own date.
    """
    # A date of publication in the future is a typo or a hostile value, and the
    # "stale" rule below would then treat every genuine later version as history
    # arriving late and drop it. It is not a fact about the notice, so it is not kept.
    if opp.published_at and opp.published_at > date.today() + timedelta(days=1):
        log.warning("%s %s: publication date %s is in the future; ignored",
                    opp.source_code, opp.native_id, opp.published_at)
        opp = replace(opp, published_at=None)

    existing = conn.execute(
        """SELECT id, current_version, buyer_name_raw FROM opportunity
            WHERE source_id = %s AND native_id = %s""",
        (src_id, opp.native_id),
    ).fetchone()

    # A different body filing a notice under a number that is already held is a
    # different notice. The first holder keeps the plain number, so nothing already
    # stored moves, and arrival order decides, which a replay reproduces. Buyer
    # names do not change between versions of one notice: across every source, no
    # archived notice has ever had its buyer differ between versions.
    if (existing and opp.source_code in LOCAL_KEY_SOURCES
            and _buyer_key(existing["buyer_name_raw"]) != _buyer_key(opp.buyer_name_raw)):
        opp = replace(opp, native_id=_disambiguated_id(opp))
        existing = conn.execute(
            """SELECT id, current_version, buyer_name_raw FROM opportunity
                WHERE source_id = %s AND native_id = %s""",
            (src_id, opp.native_id),
        ).fetchone()

    payload = opportunity_payload(opp)
    cols = {**_serving_columns(opp), **_classification_columns(opp)}

    if not existing:
        fields = ["source_id", "native_id"] + list(cols)
        values = [src_id, opp.native_id] + list(cols.values())
        placeholders = ", ".join(["%s"] * len(fields))
        opp_id = conn.execute(
            f"INSERT INTO opportunity ({', '.join(fields)}) "
            f"VALUES ({placeholders}) RETURNING id",
            values,
        ).fetchone()["id"]
        conn.execute(
            """INSERT INTO opportunity_version
                 (opportunity_id, version, payload, raw_hash, changed_fields)
               VALUES (%s, 1, %s, %s, %s)""",
            (opp_id, Jsonb(payload), raw_hash, []),
        )
        return opp_id, "new"

    opp_id = existing["id"]
    last = conn.execute(
        """SELECT version, payload, raw_hash FROM opportunity_version
            WHERE opportunity_id = %s ORDER BY version DESC LIMIT 1""",
        (opp_id,),
    ).fetchone()

    if last and last["raw_hash"] == raw_hash:
        return opp_id, "unchanged"

    # Content already archived at ANY earlier version is not a change. Comparing
    # against the latest version alone let a re-read of old content look new:
    # PLACSP serves its feed newest first, so every run saw a notice's award and
    # then its older call for tenders, and wrote the call back as a "change".
    # On 13 September 2026 one notice with a single real change -- open on the
    # 7th, awarded on the 8th -- had twelve versions flipping between the same
    # two payloads, and its current state read "open". 75 notices were affected.
    # A publisher genuinely restoring earlier content byte for byte is not
    # distinguishable from re-reading it, and is far rarer; this errs that way.
    if conn.execute(
        """SELECT 1 FROM opportunity_version
            WHERE opportunity_id = %s AND raw_hash = %s LIMIT 1""",
        (opp_id, raw_hash),
    ).fetchone():
        return opp_id, "unchanged"

    prev = last["payload"] if last else {}

    # Content older than the current version, by the source's own date, is
    # history arriving late. It must not become the current state: that is how
    # an awarded tender came to be served as open. The sequential version model
    # cannot insert it in the past either, so it is recorded as stale and not
    # archived. Day granularity is all every source provides here; two versions
    # published the same day fall through to arrival order.
    #
    # PLACSP states when an entry last changed as an instant, and that is what orders
    # its versions: its `published_at` is the notice's publication, the same on every
    # amendment. A version archived before `source_updated_at` existed has none and
    # carried the same stamp as `published_at`, so that stands in for it.
    incoming_date = payload.get("source_updated_at") or payload.get("published_at")
    current_date = prev.get("source_updated_at") or prev.get("published_at")
    if incoming_date and current_date and str(incoming_date)[:10] < str(current_date)[:10]:
        return opp_id, "stale"
    changed = changed_fields(prev, payload)
    if not changed:
        # Hash moved but nothing we track did: a cosmetic upstream edit, or a list
        # re-ordered, or a deadline written with another UTC offset.
        return opp_id, "unchanged"

    version = append_version(conn, opp_id, opp, raw_hash, changed,
                             after=last["version"] if last else 0)
    log.info("opportunity %s -> v%s, changed: %s", opp.native_id, version, changed)
    if set(changed) <= MAPPER_OWNED and _same_entry_state(prev, payload):
        # The entry says it was last changed when it already was, and only what the mapper
        # reads differently moved: our correction, not the publisher's amendment. The
        # replay, the historical backfill and a live walk reaching a held entry all come
        # through here, so none of them has to know.
        version_id = conn.execute(
            "SELECT id FROM opportunity_version WHERE opportunity_id = %s AND version = %s",
            (opp_id, version)).fetchone()["id"]
        annotate_versions(conn, [version_id], "remapped",
                          f"{opp.source_code} entry read again under a corrected mapping: "
                          + ", ".join(changed))
    return opp_id, "changed"


def mark_backfill_day(conn: psycopg.Connection, source_code: str, day: date,
                      notices: int) -> None:
    """Record that one publication day was loaded in full.

    Written after the day's last record is committed, never before: a marker
    that runs ahead of the data turns an interrupted day into a permanent hole,
    and the whole point of the marker is that resuming is safe.
    """
    conn.execute(
        """INSERT INTO backfill_day (source_code, day, notices)
           VALUES (%s, %s, %s)
           ON CONFLICT (source_code, day)
           DO UPDATE SET notices = EXCLUDED.notices,
                         finished_at = clock_timestamp()""",
        (source_code, day, notices),
    )
    conn.commit()


def backfill_days_done(conn: psycopg.Connection, source_code: str) -> set[date]:
    rows = conn.execute(
        "SELECT day FROM backfill_day WHERE source_code = %s", (source_code,)
    ).fetchall()
    return {row["day"] for row in rows}


# How long a historical load stays away after the source refused it for rate
# without saying for how long. The edge's window is minutes, and asking again
# at once is what turned one 429 into a stopped history.
BACKFILL_COOLDOWN_SECONDS = 15 * 60


def record_backfill_stop(conn: psycopg.Connection, source_code: str, day: date | None,
                         reason: str, retry_after: float | None = None) -> datetime:
    """Remember that a source stopped a historical load, and until when.

    Which days finished is `backfill_day`'s; this is why the run ended and when
    the next may begin, so a rerun does not walk straight back into the limit.
    The later of the cooldown and the source's own Retry-After. One row per
    source, overwritten by the latest stop. Returns the time it may resume.
    """
    wait = max(BACKFILL_COOLDOWN_SECONDS, retry_after or 0.0)
    row = conn.execute(
        """INSERT INTO backfill_stop (source_code, day, reason, stopped_at, resume_after)
           VALUES (%s, %s, %s, clock_timestamp(),
                   clock_timestamp() + make_interval(secs => %s))
           ON CONFLICT (source_code) DO UPDATE
              SET day = EXCLUDED.day, reason = EXCLUDED.reason,
                  stopped_at = EXCLUDED.stopped_at, resume_after = EXCLUDED.resume_after
        RETURNING resume_after""",
        (source_code, day, reason[:500], wait),
    ).fetchone()
    conn.commit()
    return row["resume_after"]


def backfill_resume_after(conn: psycopg.Connection, source_code: str) -> datetime | None:
    """When a stopped historical load may start again, if that is still ahead."""
    row = conn.execute(
        "SELECT resume_after FROM backfill_stop "
        "WHERE source_code = %s AND resume_after > clock_timestamp()", (source_code,)
    ).fetchone()
    return row["resume_after"] if row else None


def note_backfill_finished(conn: psycopg.Connection, source_code: str) -> None:
    """A load that ran to its end lifts an earlier stop's hold. The row stays."""
    conn.execute(
        """UPDATE backfill_stop
              SET reason = 'resumed and finished: ' || reason, resume_after = clock_timestamp()
            WHERE source_code = %s AND reason NOT LIKE 'resumed and finished%%'""",
        (source_code,),
    )
    conn.commit()


def record_raw(
    conn: psycopg.Connection, src_id: int, native_id: str | None,
    content_hash: str, storage_key: str, content_type: str = "application/json",
) -> None:
    conn.execute(
        """INSERT INTO raw_ingest
             (source_id, native_id, content_hash, storage_key, content_type)
           VALUES (%s, %s, %s, %s, %s)""",
        (src_id, native_id, content_hash, storage_key, content_type),
    )


# ------------------------------------------------------------------ grants

# Columns of `call` that carry the facts. Compared to decide whether a call
# materially changed, and `deadline_at` is the one the product exists to notice:
# an extension of four days is the difference between a consortium that applies
# and one that does not.
CALL_FIELDS = [
    "topic_code", "call_identifier", "title", "budget", "opens_at", "published_at", "deadline_at",
    "min_consortium_size", "min_member_states", "eligibility_text", "status",
    "type_of_action", "regime", "source_url", "country", "issuer", "budget_scope",
    "currency", "deadline_precision",
]

# Fields a source may simply not supply. The EU calendar knows no budget, no
# conditions and no consortium rule -- the topic page does -- and a national
# source may not know a country or an issuer. A Call carrying None for one of
# these means "this document does not say", not "there is none", so an update
# never writes it over what is already there. Writing it did exactly that: when a
# deadline moved, the calendar's None overwrote the budget the topic page had
# supplied, and the page was not read again until it changed itself.
OPTIONAL_CALL_FIELDS = {"published_at", "budget", "min_consortium_size", "min_member_states",
                        "eligibility_text", "country", "issuer", "budget_scope", "currency",
                        "conditions_raw", "eligibility_parsed"}


def programme_id(conn: psycopg.Connection, code: str, name: str | None = None) -> int:
    """The id of a funding programme, inserting it if the portal names a new one.

    Inserted rather than refused: a programme that appears mid-year -- EDIP's
    first calls will -- must not stop the night's run, and a row named after its
    own code is visible to whoever reads the table. The seeded programmes carry
    their regulation; one created here does not, and that is the signal that it
    needs a look.
    """
    row = conn.execute("SELECT id FROM programme WHERE code = %s", (code,)).fetchone()
    if row:
        return int(row["id"])
    log.warning("programme %s is not seeded; inserting it unverified", code)
    return int(conn.execute(
        "INSERT INTO programme (code, name) VALUES (%s, %s) RETURNING id",
        (code, name or code),
    ).fetchone()["id"])


def upsert_call(conn: psycopg.Connection, call: Any, content_hash: str,
                src_id: int) -> tuple[int, str, list[str]]:
    """Insert, update or touch one call. Returns (id, action, changed fields).

    A call is a living row, not an archive: the payload behind every state it was
    ever seen in is already in the raw store, indexed by content hash, so the
    serving row holds the current truth and `last_seen_at` says when it was last
    confirmed. A call that vanishes from the portal keeps its row and stops being
    touched, which is how a withdrawn call stays visible instead of silently
    disappearing.
    """
    prog_id = programme_id(conn, call.programme_code)
    existing = conn.execute(
        """SELECT id, content_hash, status, deadline_at, deadline_precision FROM call
            WHERE programme_id = %s AND native_id = %s""",
        (prog_id, call.native_id),
    ).fetchone()

    values: dict[str, Any] = {f: getattr(call, f) for f in CALL_FIELDS}
    values["eligibility_parsed"] = (Jsonb(call.eligibility_parsed)
                                   if call.eligibility_parsed is not None else None)
    values["conditions_raw"] = (Jsonb(call.conditions_raw)
                                if call.conditions_raw is not None else None)

    if not existing:
        fields_ = ["programme_id", "native_id", "source_id", "content_hash", *values]
        row_values = [prog_id, call.native_id, src_id, content_hash, *values.values()]
        placeholders = ", ".join(["%s"] * len(fields_))
        call_id = conn.execute(
            f"INSERT INTO call ({', '.join(fields_)}) VALUES ({placeholders}) RETURNING id",
            row_values,
        ).fetchone()["id"]
        return int(call_id), "new", []

    call_id = int(existing["id"])
    if existing["content_hash"] == content_hash:
        # The status is not always in the payload. Spain's and Sweden's registers state
        # dates, and the status is worked out from them against today; an unchanged
        # payload on the night after a deadline is therefore a call that has closed.
        # Left alone here, a call stayed `open` for good, because nothing in the payload
        # ever moved to make the hash differ.
        moved = call.status is not None and call.status != existing["status"]
        # A column added after the call was first read is filled from the same
        # payload the next time it is seen, rather than waiting for the call to change.
        conn.execute("UPDATE call SET last_seen_at = now(), status = COALESCE(%s, status), "
                     "published_at = COALESCE(published_at, %s) WHERE id = %s",
                     (call.status, call.published_at, call_id))
        # The deadline is derived from the payload alone, so with the payload unchanged a
        # different one is a correction of our reading (a date-only deadline now stored
        # as the end of its day), never a move by the source. Refreshed here for the
        # same reason as the column above: waiting for the payload to change would
        # leave a corrected mapping unapplied until the source happened to edit the call.
        derived = ["deadline_at"] if (
            call.deadline_at is not None and call.deadline_at != existing["deadline_at"]) else []
        if call.deadline_at is not None and (
                derived or call.deadline_precision != existing["deadline_precision"]):
            conn.execute(
                "UPDATE call SET deadline_at = %s, deadline_precision = %s WHERE id = %s",
                (call.deadline_at, call.deadline_precision, call_id))
        if moved:
            derived.insert(0, "status")
        return (call_id, "changed", derived) if derived else (call_id, "unchanged", [])

    before = conn.execute(
        f"SELECT {', '.join(CALL_FIELDS)} FROM call WHERE id = %s", (call_id,)
    ).fetchone()
    supplied = {name: value for name, value in values.items()
                if not (name in OPTIONAL_CALL_FIELDS and value is None)}
    changed = [f for f in CALL_FIELDS
               if f in supplied and _jsonable(before.get(f)) != _jsonable(getattr(call, f))]
    assignments = ", ".join(f"{f} = %s" for f in supplied)
    conn.execute(
        f"UPDATE call SET {assignments}, content_hash = %s, source_id = %s, "
        f"last_seen_at = now() WHERE id = %s",
        [*supplied.values(), content_hash, src_id, call_id],
    )
    if "deadline_at" in changed:
        log.warning("call %s deadline moved: %s -> %s", call.topic_code or call.native_id,
                    before.get("deadline_at"), call.deadline_at)
    return call_id, ("changed" if changed else "unchanged"), changed


# Columns the topic detail document fills. Separate from CALL_FIELDS because
# they arrive from a different document, at a different time, under their own
# hash: a calendar entry that has not changed can still have its budget
# corrected the next morning.
CALL_DETAIL_FIELDS = ["budget", "budget_scope", "currency", "eligibility_text", "conditions_raw",
                      "min_consortium_size", "min_member_states"]


def calls_needing_details(conn: psycopg.Connection, src_id: int, *,
                          refresh_after_days: int = 7,
                          limit: int | None = None) -> list[dict[str, Any]]:
    """Calls whose detail document should be read now.

    Never read: always. Read before, and still open or forthcoming: after the
    refresh window, because budgets are corrected and deadlines are extended
    while a call is live. Closed and already read: never again -- it cannot
    change any more, and re-reading it every night would be 150 requests a day
    for nothing.
    """
    rows = conn.execute(
        """SELECT c.id, c.topic_code, c.status, c.details_hash
             FROM call c
            WHERE c.source_id = %s AND c.topic_code IS NOT NULL
              AND (c.details_seen_at IS NULL
                   OR (c.status IN ('open', 'forthcoming')
                       AND c.details_seen_at < now() - make_interval(days => %s)))
         ORDER BY c.details_seen_at NULLS FIRST, c.deadline_at NULLS LAST
            LIMIT %s""",
        (src_id, refresh_after_days, limit),
    ).fetchall()
    return list(rows)


def update_call_details(conn: psycopg.Connection, call_id: int,
                        fields: dict[str, Any], details_hash: str) -> str:
    """Apply a topic's detail document to its call. Returns the action taken."""
    if conn.execute("SELECT details_hash FROM call WHERE id = %s",
                    (call_id,)).fetchone()["details_hash"] == details_hash:
        conn.execute("UPDATE call SET details_seen_at = now() WHERE id = %s", (call_id,))
        return "unchanged"

    values: dict[str, Any] = {name: fields.get(name) for name in CALL_DETAIL_FIELDS}
    if values.get("conditions_raw") is not None:
        values["conditions_raw"] = Jsonb(values["conditions_raw"])
    assignments = ", ".join(f"{name} = %s" for name in values)
    conn.execute(
        f"UPDATE call SET {assignments}, details_hash = %s, details_seen_at = now() "
        f"WHERE id = %s",
        [*values.values(), details_hash, call_id],
    )
    return "changed"
