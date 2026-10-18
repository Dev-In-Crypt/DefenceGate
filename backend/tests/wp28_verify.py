"""WP-28 verification against a production-shaped copy (not a test: run by hand, see docs/verification/product/wp28-selfcheck.md).

    DGATE_DSN=<owner dsn of the scratch copy> DGATE_API_DSN=<read-only api role dsn> \
        python backend/tests/wp28_verify.py [timings|orgs|ukraine|gaps|edf|all]

Everything is read-only. `timings` calls every endpoint twice through the real app (the first call is the cold one);
`orgs` checks the profile of 15 organisations against SQL written independently of the API; `ukraine` and `gaps` print
the answer and the SQL evidence behind its first rows; `edf` lists the ten organisations with most EDF projects and their
top partners.
"""

from __future__ import annotations

import os
import sys
import time

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

os.environ.setdefault("DGATE_RATE_LIMIT", "0")
os.environ.setdefault("DGATE_LIST_CACHE_SECONDS", "0")

from dgate import api  # noqa: E402

OWNER = os.environ["DGATE_DSN"]

# The host is shared with the production loads (load average 10 to 15 on 2 cores while this was written), so
# wall-clock times mean little. The CPU the request used is what an idle host would take: the database container's
# cgroup counter (DB_CGROUP=/sys/fs/cgroup/system.slice/docker-<id>.scope/cpu.stat, any other session on that
# container only adds to it, so the smallest of three runs is kept) plus the application's own process time.
CGROUP = os.environ.get("DB_CGROUP")


def _db_usec() -> int:
    if not CGROUP:
        return 0
    with open(CGROUP) as f:
        return int(f.readline().split()[1])


def sql(q: str, *args):
    with psycopg.connect(OWNER, row_factory=dict_row) as c:
        return c.execute(q, args).fetchall()


def timings(client: TestClient) -> None:
    top = sql("SELECT organisation_id AS id FROM organisation_network ORDER BY projects DESC LIMIT 1")[0]["id"]
    mid = sql("SELECT organisation_id AS id FROM organisation_network WHERE projects BETWEEN 8 AND 12 ORDER BY organisation_id LIMIT 1")[0]["id"]
    small = sql("SELECT organisation_id AS id FROM organisation_network WHERE projects = 1 ORDER BY organisation_id LIMIT 1")[0]["id"]
    ua = sql("SELECT organisation_id AS id FROM organisation_network WHERE country = 'UA' ORDER BY projects DESC LIMIT 1")[0]["id"]
    proj = sql("SELECT p.id FROM project p JOIN participation pa ON pa.project_id = p.id GROUP BY p.id ORDER BY count(*) DESC LIMIT 1")[0]["id"]
    urls = [
        "/v1/organisations", "/v1/organisations?sort=name&page=3", "/v1/organisations?country=DE&programme=FP7&role=coordinator",
        "/v1/organisations?programme=EDF", "/v1/organisations?q=universit", "/v1/organisations?q=thales", "/v1/organisations?q=fraunhofer&minProjects=5",
        "/v1/organisations/slugs", "/v1/projects/slugs",
        f"/v1/organisations/{top}-x", f"/v1/organisations/{top}-x/funding", f"/v1/organisations/{top}-x/partners",
        f"/v1/organisations/{top}-x/partners?country=DE&programme=H2020", f"/v1/organisations/{top}-x/projects",
        f"/v1/organisations/{mid}-x", f"/v1/organisations/{mid}-x/partners", f"/v1/organisations/{small}-x", f"/v1/organisations/{ua}-x",
        f"/v1/projects/{proj}-x", f"/v1/projects/{proj}-x/history",
        "/v1/analytics/ukraine-partners", "/v1/analytics/ukraine-partners?since=2014",
        "/v1/analytics/consortium-gaps?programme=EDF", "/v1/analytics/consortium-gaps?programme=EDF&topic=CYBER",
        "/v1/analytics/consortium-gaps?programme=HORIZON&topic=HORIZON-CL4",
    ]
    print(f"top={top} mid={mid} small={small} ua={ua} biggest_project={proj}")
    for u in urls:
        walls, cpus = [], []
        for _ in range(3):
            d0, c0, t0 = _db_usec(), time.process_time(), time.perf_counter()
            r = client.get(u)
            walls.append((time.perf_counter() - t0) * 1000)
            cpus.append((_db_usec() - d0) / 1000 + (time.process_time() - c0) * 1000)
        print(f"{r.status_code} wall first {walls[0]:6.0f} ms, best {min(walls):6.0f} ms; cpu best {min(cpus):6.0f} ms  {u}  ({len(r.content) // 1024} KiB)")


# ---- the profile against SQL written here, not in the API: raw participations of the organisation and of the
#      rows merged into it, joined to their projects
CHECK = """
SELECT count(DISTINCT pa.project_id) AS projects, count(*) AS participations,
       count(DISTINCT pa.project_id) FILTER (WHERE pa.role = 'coordinator') AS coordinated,
       sum(pa.contribution) AS eu,
       min(COALESCE(extract(year FROM p.start_date)::int, p.call_year)) AS y0,
       max(COALESCE(extract(year FROM p.start_date)::int, p.call_year)) AS y1
  FROM participation pa JOIN project p ON p.id = pa.project_id
 WHERE pa.active AND pa.organisation_id IN (
       WITH RECURSIVE m(id) AS (SELECT %s::bigint UNION SELECT o.id FROM organisation o JOIN m ON o.merged_into = m.id)
       SELECT id FROM m)
"""


def orgs(client: TestClient, n: int = 15) -> None:
    picks = sql("""(SELECT organisation_id AS id FROM organisation_network ORDER BY projects DESC LIMIT 3)
                   UNION ALL (SELECT organisation_id FROM organisation_network WHERE projects BETWEEN 20 AND 60 ORDER BY organisation_id LIMIT 3)
                   UNION ALL (SELECT organisation_id FROM organisation_network WHERE projects BETWEEN 5 AND 12 ORDER BY organisation_id DESC LIMIT 3)
                   UNION ALL (SELECT organisation_id FROM organisation_network WHERE projects = 1 ORDER BY organisation_id LIMIT 2)
                   UNION ALL (SELECT organisation_id FROM organisation_network WHERE country = 'UA' ORDER BY projects DESC LIMIT 2)
                   UNION ALL (SELECT n.organisation_id FROM organisation_network n JOIN organisation o ON o.id = n.organisation_id
                               WHERE o.is_defence_buyer ORDER BY n.projects DESC LIMIT 2)
                   UNION ALL (SELECT DISTINCT o.merged_into FROM organisation o JOIN participation pa ON pa.organisation_id = o.id
                               WHERE o.merged_into IS NOT NULL LIMIT 2)""")
    ok = 0
    for r in picks[:n]:
        oid = r["id"]
        got = client.get(f"/v1/organisations/{oid}-x").json()
        want = sql(CHECK, oid)[0]
        row = sql("SELECT projects, coordinated, eu_contribution FROM organisation_network WHERE organisation_id = %s", oid)
        c = got["counts"]
        match = (c["projects"], c["participations"], c["coordinated"]) == (want["projects"], want["participations"], want["coordinated"]) \
            and ((c["euContribution"] is None) == (want["eu"] is None)) and (want["eu"] is None or abs(c["euContribution"] - float(want["eu"])) < 0.01) \
            and (c["firstYear"], c["lastYear"]) == (want["y0"], want["y1"])
        in_dir = bool(row) and (row[0]["projects"], row[0]["coordinated"]) == (c["projects"], c["coordinated"])
        ok += match and in_dir
        print(f"{'OK ' if match and in_dir else 'BAD'} {oid:>8} {got['name'][:44]:44} {got['country']} projects={c['projects']:>5} "
              f"coord={c['coordinated']:>4} eur={c['euContribution']} years={c['firstYear']}-{c['lastYear']} merged_in={got['mergedFrom']} "
              f"directory={'same' if in_dir else 'DIFFERENT'}")
    print(f"{ok} of {min(n, len(picks))} organisations: profile = independent SQL = directory row")


def ukraine(client: TestClient) -> None:
    body = client.get("/v1/analytics/ukraine-partners?since=2021").json()
    print(body["totals"])
    for c in body["coordinators"][:8]:
        print(f"  {c['organisation']['name'][:48]:48} {c['organisation']['country']} projects={c['projects']} ua_orgs={c['ukrainianOrganisations']} "
              f"last={c['lastYear']} ua={[u['organisation']['name'][:24] for u in c['ukrainianParticipants'][:3]]}")
    top = body["coordinators"][0]["organisation"]["id"]
    print("evidence for the first coordinator (SQL): projects since 2021 it coordinated with an active Ukrainian participant")
    for r in sql("""SELECT p.id, COALESCE(p.acronym, p.title) AS label,
                           COALESCE(extract(year FROM p.start_date)::int, p.call_year) AS yr,
                           (SELECT string_agg(DISTINCT uo.canonical_name, ' | ') FROM participation u JOIN organisation uo ON uo.id = u.organisation_id
                             WHERE u.project_id = p.id AND u.active AND uo.country = 'UA') AS ua
                      FROM participation c JOIN project p ON p.id = c.project_id
                     WHERE c.organisation_id IN (SELECT id FROM organisation WHERE id = %s OR merged_into = %s)
                       AND c.role = 'coordinator' AND c.active AND COALESCE(extract(year FROM p.start_date)::int, p.call_year) >= 2021
                       AND EXISTS (SELECT 1 FROM participation u JOIN organisation uo ON uo.id = u.organisation_id
                                    WHERE u.project_id = p.id AND u.active AND uo.country = 'UA')
                     ORDER BY 3 DESC, 1 LIMIT 12""", int(top), int(top)):
        print("  ", r["id"], r["label"], r["yr"], "|", r["ua"])
    n = sql("""SELECT count(DISTINCT p.id) AS n FROM project p JOIN participation u ON u.project_id = p.id AND u.active
                JOIN organisation uo ON uo.id = u.organisation_id
               WHERE uo.country = 'UA' AND COALESCE(extract(year FROM p.start_date)::int, p.call_year) >= 2021""")[0]["n"]
    print(f"projects since 2021 with a Ukrainian participant, SQL: {n}; API totals.projects: {body['totals']['projects']}")


def gaps(client: TestClient) -> None:
    for q in ("programme=EDF&topic=CYBER&lacking=UA", "programme=EDF&lacking=UA", "programme=HORIZON&topic=HORIZON-CL4&lacking=UA"):
        r = client.get(f"/v1/analytics/consortium-gaps?{q}")
        if r.status_code != 200:
            print(q, r.status_code, r.text[:200])
            continue
        b = r.json()
        print(q, "-> projectsInArea", b["projectsInArea"], "items", len(b["items"]), "areas", [(a["code"], a["projects"]) for a in b["areas"][:6]])
        for i in b["items"][:5]:
            print(f"   {i['organisation']['name'][:46]:46} {i['organisation']['country']} projects={i['projects']} partners={i['partnerCountries']}")


def edf(client: TestClient) -> None:
    rows = sql("""SELECT g.id, g.n AS edf_projects, COALESCE(o.display_name, o.canonical_name) AS name, o.country
                    FROM (SELECT COALESCE(l.live_id, pa.organisation_id) AS id, count(DISTINCT pa.project_id) AS n
                            FROM participation pa JOIN project p ON p.id = pa.project_id JOIN programme pr ON pr.id = p.programme_id
                            LEFT JOIN organisation_merged_live l ON l.id = pa.organisation_id
                           WHERE pr.code = 'EDF' AND pa.active GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 10) g
                    JOIN organisation o ON o.id = g.id ORDER BY g.n DESC, g.id""")
    for r in rows:
        resp = client.get(f"/v1/organisations/{r['id']}-x/partners?programme=EDF&pageSize=8")
        if resp.status_code != 200:
            print(r["name"], "->", resp.status_code, resp.text[:120])
            continue
        p = resp.json()
        print(f"{r['name'][:50]} ({r['country']}), {r['edf_projects']} EDF projects, partners in EDF: {p['total']} in {p['countries']} countries")
        for x in p["items"][:6]:
            print(f"     {x['organisation']['name'][:46]:46} {x['organisation']['country']} shared={x['shared']} {x['firstYear']}-{x['lastYear']}")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    with TestClient(api.app) as client:
        for name, fn in (("timings", timings), ("orgs", orgs), ("ukraine", ukraine), ("gaps", gaps), ("edf", edf)):
            if what in (name, "all"):
                print(f"== {name}")
                fn(client)
