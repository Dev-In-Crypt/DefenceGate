"""The winners of PLACSP (Spain) award results (WP-60), on the supplier map's tables.

The pipeline rule, as everywhere: land the raw payload, normalise, archive.

    land       the award results of each kept awarded folder (`placsp.award_payload`, read next to the
               notice and never inside it), with natural persons blanked first (`redact`), in the raw
               store under `placsp_awards/` (source `es_placsp_awards`)
    normalise  `read`: one `awards.Winner` per winning organisation, persons and unusable names left out
               and counted, with the TED loader's own rules (`awards.person_reason`, `clean_supplier_name`)
    archive    `awards.store_notice`: one `award` row per (notice, organisation), the organisation found by
               the resolution cascade, one `award_notice` row per notice with the payload's hash

Natural persons. A winner is a person when its tax number is a DNI or an NIE, when the publisher masked the
number ("***1234**"), or when it has no CIF and its name reads as a person's (`awards.person_reason`, which
knows Spanish capitals-only names). Of a person the landed payload keeps `{"natural_person": true}` and
nothing else: no name, no number, no address; the folder counts its distinct persons. A UTE (unión temporal
de empresas) is a joint venture, kept as a contracting party of its own under its name, with any member that
reads as a person blanked (`awards.joint_venture_name`). No address is landed for anyone, only the country.

Re-reading. A folder states its result again on every entry. The landed payload's hash is kept on
`award_notice`: the same hash is a no-op, a different one from an entry no older than the last read is read
again (`store_notice` marks winners no longer named `superseded_at`), an older one is left alone.

Not served: the supplier map leaves these winners out unless DGATE_PLACSP_AWARDS_PUBLIC is true.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import psycopg

from . import awards, db
from .award_value import framework_refs, placsp_kind
from .normalise import PLACEHOLDER_AMOUNT_MAX, looks_like_contact
from .rawstore import BundleWriter, build_store, storage_key
from .sources import ted

log = logging.getLogger(__name__)

SOURCE_CODE = "es_placsp_awards"
KEY_PREFIX = "placsp_awards"
# Result codes with no winner: 3 deserted, 4 withdrawn (sources/placsp._NO_AWARD_RESULT_CODES).
NO_WINNER_CODES = frozenset({"3", "4"})


def _country(w: dict[str, Any]) -> str | None:
    cc = (w.get("country") or "").strip().upper()
    if len(cc) == 2 and cc.isalpha():
        return cc
    # A Spanish tax number names a Spanish taxpayer even where the address block is missing.
    return "ES" if awards.es_tax_kind(w.get("identifier"), None) else None


def redact(payload: dict[str, Any]) -> dict[str, Any]:
    """The award payload as it may be landed: persons reduced to a marker, no address, no contact."""
    persons: set[tuple[str, str]] = set()
    results = []
    for r in payload.get("results") or []:
        winners = []
        for w in r.get("winners") or []:
            name = (w.get("name") or "").strip()
            ident = (w.get("identifier") or "").strip() or None
            country = _country(w)
            if awards.person_reason(name, ident, country):
                persons.add((name.upper(), (ident or "").upper()))
                winners.append({"natural_person": True})
                continue
            problem, _ = awards.clean_supplier_name(name)
            if problem == "contact_in_name":
                winners.append({"contact_in_name": True, "country": country})
                continue
            out = {"name": awards.joint_venture_name(name) if awards.is_joint_venture(name) else name,
                   "identifier": None if looks_like_contact(ident) else ident,
                   "scheme": w.get("scheme"), "country": country}
            if awards.is_joint_venture(name):
                out["joint_venture"] = True
            winners.append(out)
        results.append({**{k: v for k, v in r.items() if k != "winners"}, "winners": winners})
    return {"source": payload.get("source"), "folder_id": payload.get("folder_id"),
            "status_native": payload.get("status_native"), "updated": payload.get("updated"),
            **({"contracting_system": payload["contracting_system"]} if payload.get("contracting_system") else {}),
            "natural_persons": len(persons),
            # how many of them stated a number at all (counted, the number itself is not kept)
            "natural_persons_identified": sum(1 for _, i in persons if i), "results": results}


def _values(landed: dict[str, Any]) -> dict[tuple[str, str | None], tuple[float, str] | None]:
    """WP-81: per winner (its name key and country), the awarded amount without VAT (`value`, TaxExclusiveAmount) of the
    results that name it alone, summed; None when its lots state two currencies. A result naming several winners (a
    blanked person counts as one) is attributed to none; a placeholder amount is no amount."""
    sums: dict[tuple[str, str | None], dict[str, float]] = {}
    for r in landed.get("results") or []:
        ws = r.get("winners") or []
        amount, currency = r.get("value"), r.get("currency")
        if len(ws) != 1 or not ws[0].get("name") or amount is None or amount <= PLACEHOLDER_AMOUNT_MAX or not currency:
            continue
        key = (awards.key_of(ws[0]["name"].strip())[0], ws[0].get("country"))
        by = sums.setdefault(key, {})
        by[currency] = by.get(currency, 0.0) + float(amount)
    return {k: (round(next(iter(v.values())), 2), next(iter(v))) if len(v) == 1 else None for k, v in sums.items()}


def read(landed: dict[str, Any], kind: str | None = None) -> awards.Read:
    """The winners of one landed (redacted) payload. `kind` (WP-95): what the awarded amounts are, contract or
    framework ceiling (`award_value.placsp_kind`); None leaves the kind unset."""
    out = awards.Read()
    seen: set[tuple[str, str | None]] = set()
    values = _values(landed)
    persons = int(landed.get("natural_persons") or 0)
    for r in landed.get("results") or []:
        for w in r.get("winners") or []:
            if w.get("natural_person"):
                continue
            if w.get("contact_in_name"):
                out.counts["skipped_contact_in_name"] += 1
                continue
            name, country, ident = (w.get("name") or "").strip(), w.get("country"), w.get("identifier")
            key = (awards.key_of(name)[0] if name else "", country)
            if key in seen:
                continue                     # one winner of several lots is one supplier of the notice
            seen.add(key)
            out.winners_seen += 1
            if w.get("joint_venture"):
                # a UTE is a party of its own; its members are checked again (a rule fixed later applies on replay)
                name, reason = awards.joint_venture_name(name, country), None
            else:
                reason = awards.person_reason(name, ident, country)   # again, for the same reason
            problem, cleaned = (None, name) if reason else awards.clean_supplier_name(name)
            if reason:
                out.counts["skipped_" + reason] += 1
                persons += 1
            elif problem:
                out.counts["skipped_" + problem] += 1
            elif not country:
                out.counts["skipped_no_country"] += 1
            else:
                value = values.get(key)
                out.winners.append(awards.Winner(cleaned, country, None if looks_like_contact(ident) else ident,
                                                 *(value or (None, None)), kind if value else None))
                out.counts["joint_ventures"] += bool(w.get("joint_venture"))
    out.winners_seen += int(landed.get("natural_persons") or 0)
    out.counts["skipped_person"] = persons
    if not out.winners_seen:
        codes = {r.get("result_code") for r in landed.get("results") or []}
        out.counts["no_winner_result" if codes <= NO_WINNER_CODES else "no_winner_named"] += 1
    return out


def framework_of(conn: psycopg.Connection, opp_id: int, title: str | None) -> int | None:
    """WP-95: the PLACSP notice of the framework agreement a call-off's title names by its file number
    ("1º CB AM (2025/AR43U/00001894)" -> folder 2025/AR43U/00001894E), or None."""
    refs = framework_refs(title)
    if not refs:
        return None
    row = conn.execute(
        """SELECT o.id FROM opportunity o
            WHERE o.native_id = ANY(%s) AND o.id <> %s
              AND o.source_id IN (SELECT id FROM source WHERE code IN ('es_placsp', 'es_placsp_agg'))
            ORDER BY array_position(%s, o.native_id), o.id LIMIT 1""", (refs, opp_id, refs)).fetchone()
    return row["id"] if row else None


def _instant(stamp: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else None
    except ValueError:
        return None


class Loader:
    """Lands and loads the award payloads of one run. Called by the PLACSP ingest for every kept record
    that carries one (`pipeline._ingest_placsp(..., awards=Loader)`), inside its transaction: `writer` is
    drained before every commit, so no committed row points at a payload that was never written.

    `land_only`: land the payload and index it in `raw_ingest`, write no award row. The winners are loaded
    later from the store (`replay_from_store`), without asking PLACSP again."""

    def __init__(self, conn: psycopg.Connection, store=None, writer: BundleWriter | None = None,
                 *, land_only: bool = False):
        self.src_id = db.source_id(conn, SOURCE_CODE)
        self.writer = writer or BundleWriter(store or build_store(), KEY_PREFIX)
        self.land_only = land_only
        self.counts: Counter = Counter()

    def __call__(self, conn: psycopg.Connection, opp_id: int, opp: Any, payload: dict[str, Any],
                 *, raw_key: str | None = None, force: bool = False) -> str:
        """`raw_key`: the payload was read back from the store at that key; it is not landed again."""
        c = self.counts
        # A payload read back from the store is landed already (it carries its count of persons).
        landed = payload if "natural_persons" in payload else redact(payload)
        h = ted.content_hash(landed)
        updated = _instant(landed.get("updated"))
        native = landed.get("folder_id") or getattr(opp, "native_id", None) or str(opp_id)
        if self.land_only:
            if not db.raw_held(conn, self.src_id, native, h):
                db.record_raw(conn, self.src_id, native, h,
                              self.writer.put(storage_key(KEY_PREFIX, native, content_hash=h), landed))
                c["payloads_landed"] += 1
            return "landed"
        held = conn.execute("SELECT payload_hash, payload_updated_at FROM award_notice WHERE opportunity_id = %s",
                            (opp_id,)).fetchone()
        if held and not force:
            if held["payload_hash"] == h:
                c["payloads_unchanged"] += 1
                return "unchanged"
            if held["payload_updated_at"] and updated and updated < held["payload_updated_at"]:
                c["payloads_older"] += 1
                return "older"
        key = raw_key
        if key is None:
            key = self.writer.put(storage_key(KEY_PREFIX, native, content_hash=h), landed)
            if not db.raw_held(conn, self.src_id, native, h):
                db.record_raw(conn, self.src_id, native, h, key)
        cpv, title = getattr(opp, "cpv_codes", None), getattr(opp, "title_original", None)
        if cpv is None or title is None:
            row = conn.execute("SELECT cpv_codes, title_original FROM opportunity WHERE id = %s", (opp_id,)).fetchone()
            cpv, title = row["cpv_codes"], row["title_original"]
        result = read(landed, placsp_kind(landed.get("contracting_system"), title))
        result.framework_id = framework_of(conn, opp_id, title)
        awards.store_notice(conn, self.src_id, {"id": opp_id, "cpv_codes": cpv}, result, key, c,
                            payload_hash=h, payload_updated_at=updated)
        c["payloads_read"] += 1
        c["reread"] += held is not None
        return "read"


def replay_from_store(conn: psycopg.Connection, *, store=None, limit: int | None = None,
                      commit: bool = True) -> Counter:
    """Load the winners from the payloads in the raw store, without asking PLACSP.

    Every PLACSP notice is read from its newest landed payload (by the entry's own update stamp): the
    payloads a land-only walk left, and after a corrected reading rule (a person test, a name cleaning)
    all of them again. A winner blanked when it landed stays blanked; one the corrected rule now finds to
    be a person is skipped and its award marked superseded. `commit=False` runs it all and rolls back:
    what a load would write, measured, with nothing kept."""
    store = store or build_store()
    src = db.source_id(conn, SOURCE_CODE)
    rows = conn.execute(
        """SELECT r.native_id, r.storage_key FROM raw_ingest r
            WHERE r.source_id = %s ORDER BY r.id LIMIT %s""",   # landing order: each bundle is read once
        (src, limit or 100_000_000)).fetchall()
    # nothing is written yet: end the read before the store is read (30+ minutes on production), or
    # the worker role's idle-in-transaction timeout closes the connection (22 Oct 2026)
    conn.rollback()
    newest: dict[str, tuple[datetime, str, dict]] = {}
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    for r in rows:
        landed = store.get(r["storage_key"])
        stamp = _instant(landed.get("updated")) or oldest
        if r["native_id"] not in newest or stamp >= newest[r["native_id"]][0]:
            newest[r["native_id"]] = (stamp, r["storage_key"], landed)
    loader = Loader(conn, store, writer=BundleWriter(store, KEY_PREFIX))
    c = loader.counts
    for i, (native, (_, key, landed)) in enumerate(sorted(newest.items()), 1):
        opp = conn.execute(
            """SELECT o.id FROM opportunity o JOIN source s ON s.id = o.source_id
                WHERE s.code = %s AND o.native_id = %s""", (landed.get("source") or "es_placsp", native)).fetchone()
        if opp is None:
            c["no_notice_held"] += 1
            continue
        loader(conn, opp["id"], None, landed, raw_key=key, force=True)
        if commit and i % 500 == 0:
            conn.commit()
    c["notices"] = len(newest)
    c["payloads_in_store"] = len(rows)
    awards.refresh_award_twins(conn)
    if commit:
        conn.commit()
    else:
        conn.rollback()
    return c


