"""Apply the fixed-pattern readings (dgate/rule_readings.py, WP-93) to what is already stored. No request, no model call.

  * `call_eligibility` rows read per topic (key `<document>#<topic>`): the stored text of the document (`call_document_text`) is read
    again for the topic, and a reading replaces the model's fact of the same name in `fields` (EIC Accelerator `sme_only`, EIC STEP
    `investor_precommitment`, Digital Europe `designated_applicants`; WP-102: EIC Pathfinder `single_beneficiary_excludes`, the
    COORDPREP-type designated bodies). The quote is the text's own, so it is `verified`.
  * WP-102: rows of a whole document (the general annexes): Annex H's `procurement_conflict` (served for PCP and PPI actions only).
    The rules of a topic's portal text (rule_readings.read_conditions) are read when served and need nothing here.
  * AID calls: the latest stored page of each call (raw store) is read for its rules, kept in `conditions_raw.rules_read`.

Only rows whose value would change are written, so a second run writes nothing. The report names every row and fact.

    python -m dgate.ops.rule_readings            # report only
    python -m dgate.ops.rule_readings --yes
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from typing import Any

from .. import db
from ..config import settings
from ..rule_readings import read_aid_page, read_document

log = logging.getLogger("rule_readings")

AID_SOURCE = "fr_aid"


@dataclass
class Result:
    rows: int = 0                  # call_eligibility rows read per topic
    no_text: int = 0               # no stored text for the row's document
    aid_calls: int = 0
    aid_no_raw: int = 0
    failed: int = 0
    changed: list[str] = field(default_factory=list)      # "<key>: <fact names>"

    def __str__(self) -> str:
        lines = [f"rows {self.rows}, no text {self.no_text}, AID calls {self.aid_calls} (no raw page {self.aid_no_raw}), "
                 f"failed {self.failed}, to write/written {len(self.changed)}"]
        return "\n".join([*lines, *(f"  {c}" for c in self.changed)])


def _changed(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    return sorted(k for k, v in new.items() if {x: old.get(k, {}).get(x) for x in ("value", "quote", "note")} != {x: v.get(x) for x in ("value", "quote", "note")})


def eu_rows(conn, result: Result, *, write: bool) -> None:
    from psycopg.types.json import Jsonb

    rows = conn.execute(
        """SELECT e.url, e.fields, e.document_url, t.text
             FROM call_eligibility e LEFT JOIN call_document_text t ON t.url = e.document_url
            WHERE e.scope IN ('call_document', 'general') ORDER BY e.url""").fetchall()
    for r in rows:
        result.rows += 1
        if not r["text"]:
            result.no_text += 1
            continue
        # WP-102: a row of the whole document (the general annexes) is read for what they state for every call of a kind (PCP/PPI)
        topic = r["url"].split("#", 1)[1] if "#" in r["url"] else None
        try:
            read = read_document(r["text"], topic)
        except Exception as exc:  # one unreadable row is not the run
            log.warning("%s: %s", r["url"], exc)
            result.failed += 1
            continue
        names = _changed(r["fields"], read)
        if not names:
            continue
        # the value and the matched sentence of each reading, so that a report can be checked before --yes
        result.changed.append(f"{r['url']}: " + "; ".join(f"{k} = {read[k]['value']!r} from “{read[k]['quote'][:240]}”" for k in names))
        if write:
            conn.execute("UPDATE call_eligibility SET fields = %s WHERE url = %s",
                         (Jsonb({**r["fields"], **{k: read[k] for k in names}}), r["url"]))


def aid_calls(conn, result: Result, *, write: bool) -> None:
    from psycopg.types.json import Jsonb

    from ..normalise import _aid_rules
    from ..rawstore import build_store

    store = build_store()
    src_id = db.source_id(conn, AID_SOURCE)
    calls = conn.execute("SELECT id, native_id, conditions_raw FROM call WHERE source_id = %s ORDER BY id", (src_id,)).fetchall()
    for c in calls:
        result.aid_calls += 1
        raw = conn.execute("""SELECT storage_key FROM raw_ingest WHERE source_id = %s AND native_id = %s
                               ORDER BY fetched_at DESC LIMIT 1""", (src_id, c["native_id"])).fetchone()
        if raw is None:
            result.aid_no_raw += 1
            continue
        try:
            page = store.get(raw["storage_key"])
            text = page.get("text") if isinstance(page, dict) else None
            day = (page.get("modified") or page.get("published")) if isinstance(page, dict) else None
        except Exception as exc:
            log.warning("call %s: %s", c["id"], exc)
            result.failed += 1
            continue
        cond = c["conditions_raw"] or {}
        names = _changed(cond.get("rules_read") or {}, read_aid_page(text))
        if not names:
            continue
        new = read_aid_page(text)
        result.changed.append(f"call {c['id']} ({c['native_id']}): " + "; ".join(f"{k} = {new[k]['value']!r} from “{new[k]['quote'][:240]}”" for k in names))
        if write:
            conn.execute("UPDATE call SET conditions_raw = %s WHERE id = %s", (Jsonb({**cond, **_aid_rules(text or '', day)}), c["id"]))


def run(*, write: bool = False, dsn: str | None = None) -> Result:
    result = Result()
    with db.connect(dsn or settings().dsn) as conn:
        eu_rows(conn, result, write=write)
        aid_calls(conn, result, write=write)
        if write:
            conn.commit()
        else:
            conn.rollback()
    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="rule-readings", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write the readings (default: report)")
    a = p.parse_args(argv)
    result = run(write=a.yes)
    print(result)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
