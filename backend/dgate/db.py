"""Database layer.

The one non-obvious piece here is upsert_opportunity. It is the mechanism that
turns a daily feed into an archive, and it has to satisfy three properties:

  - re-ingesting an unchanged notice must produce no new version
  - a changed notice must produce a new version listing what changed
  - the previous version must be closed off with valid_to, not overwritten

Everything else in this file is plumbing.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import asdict, fields
from datetime import date, datetime
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .normalise import Opportunity, normalise_org_name

log = logging.getLogger(__name__)

# Fields compared to decide whether a notice materially changed. Deliberately
# excludes enrichment output: a re-translation is not a change to the notice.
VERSIONED_FIELDS = [
    "title_original", "buyer_name_raw", "country", "procedure_type",
    "legal_basis", "value_amount", "value_currency", "published_at",
    "deadline_at", "cpv_codes", "source_url", "status",
]


def _jsonable(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def opportunity_payload(opp: Opportunity) -> dict[str, Any]:
    return {k: _jsonable(v) for k, v in asdict(opp).items()}


# Fields that come back out of a payload as strings and have to become dates
# and datetimes again. Everything else round-trips as itself.
_DATE_FIELDS = {"published_at"}
_DATETIME_FIELDS = {"deadline_at"}


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
        """UPDATE ingest_run
              SET finished_at = now(), status = %s, records_fetched = %s,
                  records_new = %s, records_changed = %s, error_message = %s
            WHERE id = %s""",
        (status, fetched, new, changed, error, run_id),
    )
    conn.commit()


# ------------------------------------------------------ organisations

def resolve_organisation(
    conn: psycopg.Connection, raw_name: str, country: str | None,
    *, src_id: int | None = None,
) -> int | None:
    """Cascade stage 0 and 2: alias lookup, then exact normalised match.

    Fuzzy, embedding and LLM stages are deliberately absent from Phase 1. They
    belong here later, behind the same interface, once there is enough data to
    measure precision against a labelled set. Guessing early would poison the
    alias table, and a poisoned alias table is worse than none.
    """
    if not raw_name or not country:
        return None
    norm = normalise_org_name(raw_name)
    if not norm:
        return None

    row = conn.execute(
        """SELECT organisation_id FROM organisation_alias
            WHERE normalised_name = %s AND (country_hint = %s OR country_hint IS NULL)
            ORDER BY confidence DESC LIMIT 1""",
        (norm, country),
    ).fetchone()
    if row:
        return row["organisation_id"]

    row = conn.execute(
        """SELECT id FROM organisation
            WHERE country = %s AND lower(canonical_name) = %s LIMIT 1""",
        (country, norm),
    ).fetchone()
    if row:
        org_id = row["id"]
    else:
        org_id = conn.execute(
            """INSERT INTO organisation (canonical_name, country, confidence, review_status)
               VALUES (%s, %s, 0.95, 'auto') RETURNING id""",
            (norm, country),
        ).fetchone()["id"]

    conn.execute(
        """INSERT INTO organisation_alias
             (organisation_id, raw_name, normalised_name, source_id,
              country_hint, match_method, confidence)
           VALUES (%s, %s, %s, %s, %s, 'exact_name', 0.95)
           ON CONFLICT (normalised_name, country_hint, source_id) DO NOTHING""",
        (org_id, raw_name, norm, src_id, country),
    )
    return org_id


def is_defence_buyer(conn: psycopg.Connection, org_id: int | None) -> bool:
    if org_id is None:
        return False
    row = conn.execute(
        "SELECT is_defence_buyer FROM organisation WHERE id = %s", (org_id,)
    ).fetchone()
    return bool(row and row["is_defence_buyer"])


# ------------------------------------------------------- the archive

def upsert_opportunity(
    conn: psycopg.Connection, opp: Opportunity, raw_hash: str, src_id: int,
) -> tuple[int, str]:
    """Insert or version an opportunity. Returns (id, "new"|"changed"|"unchanged")."""
    payload = opportunity_payload(opp)

    existing = conn.execute(
        """SELECT id, current_version FROM opportunity
            WHERE source_id = %s AND native_id = %s""",
        (src_id, opp.native_id),
    ).fetchone()

    cols = dict(
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
    )

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

    prev = last["payload"] if last else {}
    changed = [f for f in VERSIONED_FIELDS if prev.get(f) != payload.get(f)]
    if not changed:
        # Hash moved but nothing we track did: a cosmetic upstream edit.
        return opp_id, "unchanged"

    version = (last["version"] if last else 0) + 1
    conn.execute(
        """UPDATE opportunity_version SET valid_to = now()
            WHERE opportunity_id = %s AND valid_to IS NULL""",
        (opp_id,),
    )
    conn.execute(
        """INSERT INTO opportunity_version
             (opportunity_id, version, payload, raw_hash, changed_fields)
           VALUES (%s, %s, %s, %s, %s)""",
        (opp_id, version, Jsonb(payload), raw_hash, changed),
    )
    sets = ", ".join(f"{k} = %s" for k in cols)
    conn.execute(
        f"UPDATE opportunity SET {sets}, current_version = %s WHERE id = %s",
        list(cols.values()) + [version, opp_id],
    )
    log.info("opportunity %s -> v%s, changed: %s", opp.native_id, version, changed)
    return opp_id, "changed"


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
