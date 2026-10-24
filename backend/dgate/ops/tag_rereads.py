"""Annotate, as `remapped`, the PLACSP versions that are DefenceGate's own re-reading (WP-103, persona p10).

On 15 October 2026 at 06:48-06:49 the live PLACSP walk read again notices whose held version the mapper before
12 October 2026 had written: the value with VAT, no legal basis, the feed's stamp as the publication date. The new
version moved the value by exactly / 1.21 (71,000 to 58,677.69; 45,274.11 to 37,416.62; 134,000 to 110,743.80; / 1.07
for the Canary Islands' IGIC), set the legal basis and moved the publication date back months; the change list, the
feeds and the amendment counts showed them as the buyers' amendments. `db.upsert_opportunity` annotates such a
version as it is written from now on (`db.older_mapping`); this tool does the same for the versions already written.

A version is annotated when all hold (the rule of `db.upsert_opportunity`, over the archive):

  - it is a later version (version > 1) of a PLACSP notice (es_placsp, es_placsp_agg);
  - the version before it has no entry stamp (`source_updated_at`: written by the older mapper) and it has one;
  - every field it changed is one the mapper owns (`db.MAPPER_OWNED`: value, currency, procedure, legal basis,
    publication date), or the status with the source's own status code unchanged;
  - no note already says it is not the publisher's doing.

The archive is never edited: one `opportunity_version_note` per version (kind `remapped`), nothing updated or deleted,
a second run writes nothing.

    python -m dgate.ops.tag_rereads          # report: how many, by changed fields, a few examples
    python -m dgate.ops.tag_rereads --yes    # annotate

Expected on production (read-only count of 24 October 2026, docs/verification/round3/wp103-selfcheck.md): the 17
versions of 15 October 06:48-06:49 that changed the value, the legal basis or the publication date, among the
versions the report counts.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from .. import db
from ..changes import NOT_A_CHANGE
from ..config import settings

NOTE = "PLACSP entry read again under the mapping of 12 October 2026 (the held version was the older mapping's): "
OWNED = sorted(db.MAPPER_OWNED)

CANDIDATES = """
    SELECT v.id, v.opportunity_id, o.native_id, v.observed_at, v.changed_fields
      FROM opportunity_version v
      JOIN opportunity o ON o.id = v.opportunity_id
      JOIN LATERAL (SELECT p.payload FROM opportunity_version p
                     WHERE p.opportunity_id = v.opportunity_id AND p.version < v.version
                     ORDER BY p.version DESC LIMIT 1) p ON TRUE
     WHERE v.version > 1
       AND o.source_id IN (SELECT id FROM source WHERE code IN ('es_placsp', 'es_placsp_agg'))
       AND p.payload->>'source_updated_at' IS NULL
       AND v.payload->>'source_updated_at' IS NOT NULL
       AND cardinality(v.changed_fields) > 0
       AND v.changed_fields <@ (%(owned)s::text[] || CASE
             WHEN p.payload->>'status_native' IS NOT DISTINCT FROM v.payload->>'status_native'
             THEN ARRAY['status'] ELSE ARRAY[]::text[] END)
       AND NOT EXISTS (SELECT 1 FROM opportunity_version_note n
                        WHERE n.opportunity_version_id = v.id AND n.kind = ANY(%(kinds)s))
     ORDER BY v.id
"""


def run(conn, *, write: bool) -> tuple[Counter, list[str]]:
    rows = conn.execute(CANDIDATES, {"owned": OWNED, "kinds": list(NOT_A_CHANGE)}).fetchall()
    c: Counter = Counter()
    examples: list[str] = []
    for r in rows:
        c["versions"] += 1
        c["fields " + ",".join(sorted(r["changed_fields"]))] += 1
        c["observed " + r["observed_at"].strftime("%Y-%m-%d")] += 1
        if len(examples) < 20:
            examples.append(f"{r['native_id']} v{r['id']} {r['observed_at']:%Y-%m-%d %H:%M} {','.join(r['changed_fields'])}")
        if write:
            c["annotated"] += db.annotate_versions(conn, [r["id"]], "remapped",
                                                   NOTE + ", ".join(sorted(r["changed_fields"])))
    if write:
        conn.commit()
    else:
        conn.rollback()
    return c, examples


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dgate.ops.tag_rereads", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="annotate (the default is a report)")
    a = p.parse_args(argv)
    with db.connect(settings().dsn) as conn:
        conn.execute("SET statement_timeout = 0")
        c, examples = run(conn, write=a.yes)
    print("written" if a.yes else "report only (add --yes to write)")
    for k in sorted(c):
        print(f"  {k}: {c[k]}")
    for e in examples:
        print("  e.g. " + e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
