"""Correct the country of contract winners filed under another country (WP-96, persona round of 23 October 2026, A2.4).

    python -m dgate.ops.supplier_countries                 # report: every correction, nothing written
    python -m dgate.ops.supplier_countries --yes           # write, then rebuild the directory table
    python -m dgate.ops.supplier_countries --undo FROM TO [--yes]   # put back the corrections of [FROM, TO)

The cause. A TED result notice states its tenderers as parallel lists (names, countries, numbers), and `awards.read_award`
took a country from its list when the list had one entry per name or one value for all. Where a list is short or out of
order, a winner took another tenderer's country: LEONARDO Germany GmbH, Saab Finland Oy and Rheinmetall Canada Inc. as
Sweden, Indra Avitech GmbH as Spain, Rheinmetall Expal Munition S.A. as Latvia, KNDS Ammo France as Luxembourg. The
loader now checks each winner's country against its own VAT prefix, name and legal form
(`supplier_identity.stated_country_check`); this command applies the same check to the winners held:

  * the organisation's country is corrected when its name or its number (own, or stated in its award rows) contradicts
    it; the notices' other tenderer countries (the countries of the other award rows of its notices) decide between the
    countries a legal form allows
  * "UK" is GB (basis `uk_is_gb`), on organisations and award rows
  * its award rows' `supplier_country` follow

Every correction is recorded in `organisation_country_fix` (old and new country, basis, award rows), so `--undo` puts
it back. A corrected row whose name now has a twin in the new country is left to `ops.supplier_dedupe` (run it after
this). Idempotent: a second run finds nothing.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from typing import Any

from .. import db, networks
from ..config import settings
from ..supplier_identity import stated_country_check

log = logging.getLogger("supplier_countries")


def candidates(conn) -> list[dict[str, Any]]:
    """The live contract winners with their country, numbers and the countries of the other winners of their notices."""
    return [dict(r) for r in conn.execute(
        """SELECT g.id, COALESCE(g.display_name, g.canonical_name) AS name, btrim(g.country) AS country,
                  COALESCE(g.vat_number, g.national_reg_no) AS own_number,
                  array_agg(DISTINCT a.identifier_as_stated) FILTER (WHERE a.identifier_as_stated IS NOT NULL) AS stated,
                  ARRAY(SELECT DISTINCT b.supplier_country FROM award b
                         WHERE b.opportunity_id = ANY(array_agg(a.opportunity_id))
                           AND b.organisation_id <> g.id) AS others
             FROM award a JOIN organisation raw ON raw.id = a.organisation_id
             JOIN organisation g ON g.id = COALESCE(raw.merged_into, raw.id)
            WHERE a.superseded_at IS NULL AND NOT g.suppressed
            GROUP BY g.id""").fetchall()]


def correction(row: dict[str, Any]) -> tuple[str, str] | None:
    """(new country, basis) for a winner, or None."""
    if row["country"] == "UK":
        return "GB", "uk_is_gb"
    for number in (row["own_number"], *(row["stated"] or ())):
        new, basis = stated_country_check(row["name"], number, row["country"], tuple(row["others"] or ()))
        if basis:
            return new or row["country"], basis
    return None


def run(conn, *, apply: bool = False, out=print, sample: int = 40) -> dict[str, Any]:
    rows = candidates(conn)
    fixes = [(r, *c) for r in rows if (c := correction(r)) and c[0] != r["country"]]
    by: Counter = Counter(f"{r['country']}>{new} ({basis})" for r, new, basis in fixes)
    stray_awards = conn.execute("SELECT count(*) AS n FROM award WHERE supplier_country = 'UK'").fetchone()["n"]
    out(f"contract winners read: {len(rows)}; countries to correct: {len(fixes)}; award rows stating UK: {stray_awards}")
    out(f"by change: {dict(by.most_common(30))}")
    for r, new, basis in fixes[:sample]:
        out(f"  {r['id']:>8} {r['name'][:50]!r}: {r['country']} -> {new} ({basis})")
    result = {"winners": len(rows), "to_correct": len(fixes), "by_change": dict(by), "written": 0,
              "award_rows": 0}
    if not apply:
        conn.rollback()
        out("dry run: nothing written (add --yes)")
        return result
    started = conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"]
    result["skipped_number_held_there"] = 0
    for r, new, basis in fixes:
        if conn.execute(
                """SELECT 1 FROM organisation x JOIN organisation m ON m.national_reg_no = x.national_reg_no
                    WHERE (m.id = %s OR m.merged_into = %s) AND x.country = %s AND x.id <> m.id LIMIT 1""",
                (r["id"], r["id"], new)).fetchone():
            # another body of the new country holds its registration number: a person decides
            result["skipped_number_held_there"] += 1
            continue
        n = conn.execute(
            """UPDATE award SET supplier_country = %s
                WHERE organisation_id IN (SELECT id FROM organisation WHERE id = %s OR merged_into = %s)
                  AND supplier_country = %s""", (new, r["id"], r["id"], r["country"])).rowcount
        conn.execute("UPDATE organisation SET country = %s WHERE id = %s OR merged_into = %s",
                     (new, r["id"], r["id"]))
        conn.execute("""INSERT INTO organisation_country_fix (org_id, old_country, new_country, basis, award_rows)
                        VALUES (%s, %s, %s, %s, %s)""", (r["id"], r["country"], new, basis, n))
        result["written"] += 1
        result["award_rows"] += n
    result["award_rows"] += conn.execute(
        "UPDATE award SET supplier_country = 'GB' WHERE supplier_country = 'UK'").rowcount
    conn.commit()
    ended = conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"]
    conn.commit()
    result["batch_window"] = (started.isoformat(), ended.isoformat())
    result["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
    out(f"corrected {result['written']} winners and {result['award_rows']} award rows; then run "
        "python -m dgate.ops.supplier_dedupe; to undo: python -m dgate.ops.supplier_countries --undo "
        f"'{started.isoformat()}' '{ended.isoformat()}' [--yes]")
    return result


def undo(conn, start: str, end: str, *, apply: bool = False, out=print) -> int:
    """Put back the corrections recorded in [start, end) that are not undone yet. An organisation merged since is put
    back too (its award rows with it); `ops.supplier_dedupe --undo-batch` undoes the merge."""
    fixes = conn.execute(
        """SELECT id, org_id, old_country, new_country FROM organisation_country_fix
            WHERE fixed_at >= %s AND fixed_at < %s AND undone_at IS NULL ORDER BY id DESC""", (start, end)).fetchall()
    out(f"corrections to put back: {len(fixes)}")
    if not apply:
        conn.rollback()
        out("dry run: nothing written (add --yes)")
        return len(fixes)
    for f in fixes:
        conn.execute("""UPDATE award SET supplier_country = %s
                         WHERE organisation_id IN (SELECT id FROM organisation WHERE id = %s OR merged_into = %s)
                           AND supplier_country = %s""", (f["old_country"], f["org_id"], f["org_id"], f["new_country"]))
        conn.execute("UPDATE organisation SET country = %s WHERE (id = %s OR merged_into = %s) AND country = %s",
                     (f["old_country"], f["org_id"], f["org_id"], f["new_country"]))
        conn.execute("UPDATE organisation_country_fix SET undone_at = clock_timestamp() WHERE id = %s", (f["id"],))
    conn.commit()
    networks.refresh_organisation_network(conn)
    out(f"put back: {len(fixes)}")
    return len(fixes)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="write; without it nothing changes")
    p.add_argument("--undo", nargs=2, metavar=("FROM", "TO"), help="put back the corrections of [FROM, TO)")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        if a.undo:
            undo(conn, *a.undo, apply=a.yes)
        else:
            run(conn, apply=a.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
