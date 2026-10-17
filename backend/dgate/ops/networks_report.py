"""Read-only report on the networks layer (WP-26, plan M2-13).

    python -m dgate.ops.networks_report [--json] [--programme EDF] [--explain]

Prints: projects and participations per programme and year, the organisations that coordinate
most, the participants held without a PIC, the size of the resolution review queue, and the twenty
organisations that appear most in the EDF. It writes nothing. `--explain` prints the plan and the
timing (EXPLAIN ANALYZE) of each query instead of its rows.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import psycopg

from .. import db
from ..config import settings

YEAR = "COALESCE(extract(year FROM p.start_date)::int, p.call_year::int)"
NAME = "COALESCE(o.display_name, o.canonical_name)"
LIVE_ORG = """JOIN organisation o ON o.id = COALESCE(
                 (SELECT merged_into FROM organisation m WHERE m.id = pa.organisation_id),
                 pa.organisation_id)"""


def queries(programme: str | None = None) -> dict[str, str]:
    prog = "AND pr.code = %(programme)s" if programme else ""
    return {
        "per_programme_year": f"""
            SELECT COALESCE(pr.code, '(none)') AS programme, {YEAR} AS year,
                   count(DISTINCT p.id) AS projects, count(pa.id) AS participations,
                   count(DISTINCT pa.organisation_id) AS organisations
              FROM project p LEFT JOIN programme pr ON pr.id = p.programme_id
              LEFT JOIN participation pa ON pa.project_id = p.id AND pa.active
             WHERE true {prog}
             GROUP BY 1, 2 ORDER BY 1, 2""",
        "top_coordinators": f"""
            SELECT o.id AS organisation_id, {NAME} AS name, o.country,
                   count(*) AS projects_coordinated, sum(p.eu_contribution) AS eu_contribution_eur
              FROM participation pa JOIN project p ON p.id = pa.project_id
              JOIN programme pr ON pr.id = p.programme_id {LIVE_ORG}
             WHERE pa.active AND pa.role = 'coordinator' {prog}
             GROUP BY o.id ORDER BY projects_coordinated DESC, o.id LIMIT 20""",
        "participants_without_pic": f"""
            SELECT s.code AS source, count(DISTINCT pa.organisation_id) AS organisations,
                   count(*) AS participations
              FROM participation pa JOIN project p ON p.id = pa.project_id
              JOIN source s ON s.id = p.source_id LEFT JOIN programme pr ON pr.id = p.programme_id
              JOIN organisation o ON o.id = pa.organisation_id
             WHERE pa.active AND o.eu_pic IS NULL {prog}
             GROUP BY 1 ORDER BY 1""",
        "review_queue": """
            SELECT method, status, count(*) AS pairs FROM resolution_review
             GROUP BY 1, 2 ORDER BY 1, 2""",
        "edf_top_organisations": f"""
            SELECT o.id AS organisation_id, {NAME} AS name, o.country,
                   count(DISTINCT pa.project_id) AS projects,
                   count(DISTINCT pa.project_id) FILTER (WHERE pa.role = 'coordinator') AS coordinated
              FROM participation pa JOIN project p ON p.id = pa.project_id
              JOIN programme pr ON pr.id = p.programme_id {LIVE_ORG}
             WHERE pa.active AND pr.code = 'EDF'
             GROUP BY o.id ORDER BY projects DESC, o.id LIMIT 20""",
    }


def build(conn: psycopg.Connection, programme: str | None = None) -> dict[str, Any]:
    args = {"programme": programme}
    return {name: [dict(r) for r in conn.execute(sql, args).fetchall()]
            for name, sql in queries(programme).items()}


def explain(conn: psycopg.Connection, programme: str | None = None) -> str:
    out = []
    for name, sql in queries(programme).items():
        plan = conn.execute("EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) " + sql,
                            {"programme": programme}).fetchall()
        out.append(f"-- {name}\n" + "\n".join(next(iter(r.values())) for r in plan))
    return "\n\n".join(out)


def format_text(rep: dict[str, Any]) -> str:
    lines = ["Projects and participations per programme and year",
             f"  {'programme':<9}{'year':>6}{'projects':>10}{'participations':>16}{'organisations':>15}"]
    for r in rep["per_programme_year"]:
        lines.append(f"  {r['programme']:<9}{r['year'] or '-':>6}{r['projects']:>10}"
                     f"{r['participations']:>16}{r['organisations']:>15}")
    lines += ["", "Most frequent coordinators"]
    for r in rep["top_coordinators"]:
        lines.append(f"  {r['projects_coordinated']:>5}  {r['name'][:60]} ({r['country']})")
    lines += ["", "Participants held without a PIC (organisations, participations)"]
    for r in rep["participants_without_pic"]:
        lines.append(f"  {r['source']:<16}{r['organisations']:>8}{r['participations']:>10}")
    lines += ["", "Resolution review queue"]
    for r in rep["review_queue"]:
        lines.append(f"  {r['method']:<24}{r['status']:<10}{r['pairs']:>8}")
    if not rep["review_queue"]:
        lines.append("  empty")
    lines += ["", "The 20 organisations most often in an EDF project"]
    for r in rep["edf_top_organisations"]:
        lines.append(f"  {r['projects']:>4} projects ({r['coordinated']} coordinated)  "
                     f"{r['name'][:56]} ({r['country']})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="networks_report")
    ap.add_argument("--programme", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--explain", action="store_true")
    a = ap.parse_args(argv)
    with db.connect(settings().dsn) as conn:
        if a.explain:
            print(explain(conn, a.programme))
            return 0
        rep = build(conn, a.programme)
    print(json.dumps(rep, indent=1, default=str) if a.json else format_text(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
