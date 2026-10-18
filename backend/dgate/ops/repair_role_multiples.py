"""Correct the stored EU contributions that were counted twice (WP-43, N1 of the third verification).

    python -m dgate.ops.repair_role_multiples          # report what would change, write nothing
    python -m dgate.ops.repair_role_multiples --yes    # write, then rebuild the directory table

The CORDIS roles query summed a role's payment once per organisation node and per project the role points to.
About 207 of the 398,584 roles point to two organisation nodes (usually one bare reference with no description
besides the real organisation), so their payment was stored twice over (ENEN2plus, CEA: 92,035 for 46,017.50;
NATURE-ETN, Warsaw: 454,957.20 for 227,478.60). The loader now divides (`cordis.role_record`); this module repairs
the rows already stored without re-reading the other 398,000 roles.

It reads those roles from the public SPARQL service in one request (robots.txt first, honest User-Agent), finds the
stored participation by project record number and PIC (through the organisation's live row; for an organisation
without a PIC, the one participation of that project and role that holds exactly the doubled figure), and takes the
surplus out of the stored amount. Afterwards the project is settled again with the same rules the loader uses
(`repair_contributions.derive`), because a corrected amount can end an `exceeds_project_total` withholding or
change a `gross_of_third_parties` note. No row is deleted; an amount that does not contain the doubled figure is
left alone and counted. Idempotent: a second run finds the amounts already right.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from typing import Any

from .. import db, networks
from ..config import settings
from ..sources import cordis
from . import repair_contributions

log = logging.getLogger("repair_role_multiples")

EPS = 0.011           # EUR: amounts are stored to the cent


def _stored(conn, rcn: str, pic: str) -> list[dict[str, Any]]:
    return conn.execute(
        """SELECT pa.id, pa.project_id FROM project p
             JOIN source s ON s.id = p.source_id AND s.code = 'cordis'
             JOIN participation pa ON pa.project_id = p.id AND pa.active
            WHERE p.native_id = %s
              AND dgate_live_org(pa.organisation_id) IN (SELECT dgate_live_org(id) FROM organisation WHERE eu_pic = %s)
            ORDER BY pa.id""", (rcn, pic)).fetchall()


def _stored_by_amount(conn, rcn: str, role: str | None, raw: float) -> list[dict[str, Any]]:
    """For a role whose organisation has no PIC: the participations of that project that hold exactly the doubled figure
    (as the amount, or as the withheld one) in that role. The figure is specific enough to name one."""
    return conn.execute(
        """SELECT pa.id, pa.project_id FROM project p
             JOIN source s ON s.id = p.source_id AND s.code = 'cordis'
             JOIN participation pa ON pa.project_id = p.id AND pa.active
            WHERE p.native_id = %s AND pa.role = %s
              AND (abs(pa.contribution - %s) < 0.006 OR abs(pa.contribution_stated - %s) < 0.006)
            ORDER BY pa.id""", (rcn, role, raw, raw)).fetchall()


def _group(conn, project_id: int) -> list[dict[str, Any]]:
    return conn.execute(
        """SELECT pa.id, pa.project_id, pa.role, pa.contribution, pa.contribution_note, pa.contribution_stated,
                  p.eu_contribution AS fund, p.native_id
             FROM participation pa JOIN project p ON p.id = pa.project_id
            WHERE pa.project_id = %s AND pa.active ORDER BY pa.id""", (project_id,)).fetchall()


def plan(conn, rows: list[dict[str, str]]) -> tuple[list[tuple[Any, ...]], list[str], Counter]:
    """(updates, sample lines, counters) for the roles the query returned. Each update is
    (contribution, note, stated, participation id)."""
    c: Counter = Counter()
    cut: dict[int, float] = {}                         # participation id -> amount to take out
    doubled: dict[int, float] = {}                     # participation id -> the figure that was stored for these roles
    for row in rows:
        c["roles"] += 1
        pic, rcn = (row.get("pic") or "").strip(), (row.get("project") or "").strip()
        raw = cordis._num(row.get("amount"))
        copies = max(cordis._whole(row.get("orgs")), 1) * max(cordis._whole(row.get("projects")), 1)
        if raw is None or copies < 2:
            c["nothing_to_correct"] += 1
            continue
        if pic:
            found = _stored(conn, rcn, pic)
        else:
            # an organisation without a PIC was found by its name when it was loaded: here by the doubled amount
            found = _stored_by_amount(conn, rcn, cordis._ROLE.get(row.get("role") or ""), raw)
            c["by_amount" if len(found) == 1 else "no_pic_unmatched"] += 1
        if not found:
            c["not_stored"] += 1
            continue
        if len(found) > 1:
            c["ambiguous"] += 1
            continue
        pa_id = found[0]["id"]
        cut[pa_id] = cut.get(pa_id, 0.0) + raw - round(raw / copies, 2)
        doubled[pa_id] = doubled.get(pa_id, 0.0) + raw
        c["matched"] += 1
    updates: list[tuple[Any, ...]] = []
    sample: list[str] = []
    seen_projects: set[int] = set()
    for pid in cut:
        project_id = conn.execute("SELECT project_id FROM participation WHERE id = %s", (pid,)).fetchone()["project_id"]
        if project_id in seen_projects:
            continue
        seen_projects.add(project_id)
        group = _group(conn, project_id)
        before = {g["id"]: (g["contribution"], g["contribution_note"], g["contribution_stated"]) for g in group}
        for g in group:
            if g["id"] not in cut:
                continue
            field = "contribution_stated" if g["contribution_note"] == "exceeds_project_total" else "contribution"
            have = None if g[field] is None else float(g[field])
            if have is None:
                c["no_amount_stored"] += 1
            elif have < doubled[g["id"]] - EPS:
                c["already_right_or_other"] += 1       # does not contain the doubled figure: not ours to touch
            else:
                g[field] = round(have - cut[g["id"]], 2)
                c["corrected"] += 1
        for pid2, amount, note, stated in repair_contributions.derive(group):
            old = before[pid2]
            old_n = (None if old[0] is None else float(old[0]), old[1], None if old[2] is None else float(old[2]))
            if old_n != (amount, note, stated):
                updates.append((amount, note, stated, pid2))
                if len(sample) < 12:
                    g = next(x for x in group if x["id"] == pid2)
                    sample.append(f"project {g['native_id']} participation {pid2}: {old_n[0]} [{old_n[1]}] -> {amount} [{note}]")
    c["participations_changed"] = len(updates)
    c["projects"] = len(seen_projects)
    return updates, sample, c


def run(conn, rows: list[dict[str, str]], *, apply: bool = False, out=print) -> Counter:
    updates, sample, c = plan(conn, rows)
    for line in sample:
        out("  " + line)
    if apply and updates:
        with conn.cursor() as cur:
            cur.executemany(
                """UPDATE participation SET contribution = %s, contribution_note = %s,
                          contribution_stated = %s WHERE id = %s""", updates)
        conn.commit()
        c["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
    else:
        conn.rollback()
    out(f"{'written' if apply else 'would change'}: {dict(c)}" + ("" if apply else "  (dry run; add --yes)"))
    return c


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="write; without it nothing changes")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sp = cordis.Sparql()
    try:
        sp.check_robots()
        rows = sp.select(cordis.multiple_roles_query())
    finally:
        sp.close()
    log.info("%d roles point to more than one organisation node or project", len(rows))
    with db.connect(settings().dsn) as conn:
        run(conn, rows, apply=a.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
