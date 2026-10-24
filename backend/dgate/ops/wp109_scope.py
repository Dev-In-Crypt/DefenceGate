"""WP-109: apply the corrected scope and labels to the calls already stored. No request.

  * Calls of the EU portal that the scope rule no longer takes (`sources/eu_portal.civil_subject`: healthy ageing, soil sealing, the
    RAISE doctoral networks, wildlife trafficking, the EuroHPC pilots) get `out_of_scope` (migration 0121): left out of the lists and
    counts, never deleted. A call the rule takes again is put back.
  * AID calls: RAPID is dual-use in the agency's own words (`sources/aid.regime_of`), and the agency's name keeps its accent
    (`aid.ISSUER`). The connector writes both for a page that changes; an unchanged page is not rewritten, hence this.
  * Who may apply: `who_apply.run`, which now also fills `research_may_apply_doc` (the filter "Universities and research organisations").

Only rows whose value would change are written, so a second run writes nothing. The report names every row.

    python -m dgate.ops.wp109_scope            # report only
    python -m dgate.ops.wp109_scope --yes
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from .. import db, who_apply
from ..config import settings
from ..sources import aid, eu_portal


def plan(conn) -> list[tuple[int, str, dict[str, Any]]]:
    """(call id, why, the columns to set) for every stored call whose scope or label the rules now say otherwise."""
    out: list[tuple[int, str, dict[str, Any]]] = []
    rows = conn.execute(
        """SELECT c.id, c.topic_code, c.native_id, c.title, c.regime, c.issuer, c.out_of_scope, s.code AS source
             FROM call c LEFT JOIN source s ON s.id = c.source_id
            WHERE s.code IN (%s, %s) ORDER BY c.id""", (eu_portal.SOURCE_CODE, aid.SOURCE_CODE)).fetchall()
    for r in rows:
        if r["source"] == eu_portal.SOURCE_CODE:
            why = eu_portal.civil_subject(r["topic_code"] or r["native_id"] or "", r["title"] or "") if r["regime"] == "dual_use" else None
            if bool(why) != r["out_of_scope"]:
                out.append((r["id"], f"{r['topic_code']}: {why or 'in scope again'}", {"out_of_scope": bool(why)}))
            continue
        want = {"regime": aid.regime_of(r["native_id"] or "", r["title"] or ""), "issuer": aid.ISSUER}
        diff = {k: v for k, v in want.items() if r[k] != v}
        if diff:
            out.append((r["id"], f"{r['native_id']}: {', '.join(f'{k} -> {v}' for k, v in diff.items())}", diff))
    return out


def run(*, write: bool) -> str:
    with db.connect(settings().dsn) as conn:
        changes = plan(conn)
        if write:
            for cid, _, cols in changes:
                conn.execute(f"UPDATE call SET {', '.join(f'{k} = %s' for k in cols)} WHERE id = %s", [*cols.values(), cid])
        who = who_apply.run(conn, write=write)
        if write:
            conn.commit()
    lines = [f"calls to change: {len(changes)}{' (written)' if write else ''}", *(f"  {cid} {why}" for cid, why, _ in changes),
             f"who may apply: {who}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="wp109-scope", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write (default: report)")
    a = p.parse_args(argv)
    print(run(write=a.yes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
