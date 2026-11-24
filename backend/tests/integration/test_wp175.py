"""WP-175 (QA of 24 November 2026, organisations and market data) against a real Postgres: the largest buyers' profiles kept by
the worker and served from there (D-3), a reviewed split of a buyer family that the daily family run keeps (D-4), a supplier's
namesakes counted as its list counts them (D-8), a name search that says by which stated name it found a company (D-23), past
roles over an organisation's family rows (D-15), and the consortium gaps saying when the country is absent from the area (D-14)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from psycopg.types.json import Jsonb

from dgate import partners, stats
from dgate.ops import buyer_families, buyer_split, warm_lists
from tests.integration.test_warm_lists import cache_on  # noqa: F401 - fixture
from tests.integration.test_wp111 import buyer_of, client, notice, winner  # noqa: F401 - fixtures and helpers

pytestmark = pytest.mark.integration

QUIET = {"out": lambda *_: None}


# ----------------------------------------------------------------------------------------------- D-3: kept profiles

def test_the_worker_keeps_the_largest_buyers_profiles_and_the_api_serves_them(conn, client, cache_on):  # noqa: F811
    head = buyer_of(conn, notice(conn, "1-2026", "Ministerstvo obrany", country="CZ"))
    notice(conn, "2-2026", "Ministerstvo obrany", country="CZ")
    views = warm_lists.profile_views(conn)
    assert [v[1] for v in views] == [f"{stats.BUYER_PROFILE_KEY}{head}"]
    assert warm_lists.run(conn, write=True)["failed"] == 0
    row = conn.execute("SELECT body FROM list_snapshot WHERE key = %s", (f"{stats.BUYER_PROFILE_KEY}{head}",)).fetchone()
    assert row and row["body"]["tenderCount"] == 2
    # a marker in the kept body: the API answers from it, not from the notices
    conn.execute("UPDATE list_snapshot SET body = jsonb_set(body, '{tenderCount}', '777') WHERE key = %s",
                 (f"{stats.BUYER_PROFILE_KEY}{head}",))
    conn.commit()
    stats.reset_cache()
    assert client.get(f"/v1/buyers/{head}/profile").json()["tenderCount"] == 777
    # an old one is not read: the profile is computed
    conn.execute("UPDATE list_snapshot SET computed_at = now() - interval '9 hours' WHERE key = %s",
                 (f"{stats.BUYER_PROFILE_KEY}{head}",))
    conn.commit()
    stats.reset_cache()
    assert client.get(f"/v1/buyers/{head}/profile").json()["tenderCount"] == 2


# ----------------------------------------------------------------------------------------------- D-4: reviewed split

LONG = "Bundesamt für Ausrüstung, Informationstechnik und Nutzung der Bundeswehr"
INFRA = "Bundesamt für Infrastruktur, Umweltschutz und Dienstleistungen der Bundeswehr"


def test_a_reviewed_split_takes_a_body_out_of_a_family_and_the_family_run_keeps_it_out(conn, client):  # noqa: F811
    head = buyer_of(conn, notice(conn, "1-2026", LONG, country="DE"))
    notice(conn, "2-2026", LONG, country="DE")
    other = buyer_of(conn, notice(conn, "3-2026", "BAIUDBw Bonn", country="DE"))       # put in the family by some rule
    baiudbw = buyer_of(conn, notice(conn, "4-2026", INFRA, country="DE"))               # the office's own buyer row
    stray = notice(conn, "5-2026", LONG, country="DE")                                   # filed under the BAAINBw row ...
    conn.execute("UPDATE opportunity SET buyer_name_raw = %s WHERE id = %s", (INFRA, stray))   # ... though it states BAIUDBw
    conn.execute("INSERT INTO buyer_family_member (org_id, head_org_id, method, confidence) VALUES (%s, %s, 'twin_notice', 0.85)",
                 (other, head))
    conn.commit()
    pattern = "baiudbw|infrastruktur umweltschutz und dienstleistungen"

    dry = buyer_split.run(conn, head, pattern, to=baiudbw, why="a federal office of its own", confidence=0.95, **QUIET)
    assert dry == {"members": 1, "notices": 1}                 # the notice of the leaving row goes with the row, not moved
    assert conn.execute("SELECT count(*) AS n FROM resolution_review").fetchone()["n"] == 0         # a report writes nothing

    done = buyer_split.run(conn, head, pattern, to=baiudbw, why="a federal office of its own", confidence=0.95,
                           apply=True, **QUIET)
    assert done["moved"] == 1
    assert buyer_of(conn, stray) == baiudbw
    review = conn.execute("SELECT method, status, confidence, evidence FROM resolution_review WHERE method = %s",
                          (buyer_split.SPLIT,)).fetchone()
    assert (review["status"], float(review["confidence"]), review["evidence"]["member"]) == ("rejected", 0.95, other)
    moved = conn.execute("SELECT evidence FROM resolution_review WHERE method = %s", (buyer_split.MOVE,)).fetchone()
    assert moved["evidence"]["notices"] == [stray]
    # the daily run: the row stays out of the BAAINBw family and is shown under the BAIUDBw buyer
    buyer_families.run(conn, write=True)
    rows = {r["org_id"]: (r["head_org_id"], r["method"]) for r in conn.execute(
        "SELECT org_id, head_org_id, method FROM buyer_family_member").fetchall()}
    assert rows.get(other) == (baiudbw, buyer_split.SPLIT)
    stats.reset_cache()
    units = client.get(f"/v1/buyers/{head}").json()
    assert units["nameVariants"] == 0 and units["tenderCount"] == 2


def test_apply_splits_moves_a_member_and_drops_an_emptied_family():
    M = buyer_families.Member
    g = buyer_families.Group("DE:x", M(1, "a", 5, "rule:x", 0.9), [M(2, "b", 1, "twin_notice", 0.85)])
    buyers = {i: M(i, n, 1, "shared_tax_id", 0.9) for i, n in ((1, "a"), (2, "b"), (3, "c"))}
    out = buyer_families.apply_splits([g], [{"member": 2, "head": 1, "to": 3, "confidence": 0.95}], buyers)
    assert [(x.head.org_id, [(m.org_id, m.method, m.confidence) for m in x.members]) for x in out] == [
        (3, [(2, buyer_split.SPLIT, 0.95)])]


# ----------------------------------------------------------------------------------------------- D-8, D-23: suppliers

def test_a_namesake_is_counted_as_the_list_counts_it_and_one_without_a_win_in_the_window_is_left_out(conn, client):  # noqa: F811
    a = winner(conn, notice(conn, "10-2026", "BAAINBw", country="DE", status="awarded"), "Rheinmetall Electronics GmbH",
               "DE", "811127845")
    b_notice = notice(conn, "11-2026", "BAAINBw", country="DE", status="awarded")
    b = winner(conn, b_notice, "Rheinmetall Electronics GmbH", "DE", "119356818")
    old = notice(conn, "12-2019", "BAAINBw", country="DE", status="awarded", published=date.today() - timedelta(days=5 * 365))
    winner(conn, old, "Rheinmetall Electronics GmbH", "DE", "251121155")                # its only win is years ago
    got = client.get(f"/v1/suppliers/{a}").json()
    assert [(n["slug"].split("-")[0], n["awards"]) for n in got["namesakes"]] == [(str(b), 1)]


def test_a_name_search_says_by_which_stated_name_it_found_a_company(conn, client):  # noqa: F811
    org = winner(conn, notice(conn, "20-2026", "Inspektorat Wsparcia", country="PL", status="awarded"),
                 "Konsorcjum: MEGMAR Logistics Sp. z o.o. Leonardo Poland Sp. z o.o.", "PL", None)
    for i in (21, 22):              # its own name, the one most notices state and the list shows
        opp = notice(conn, f"{i}-2026", "Inspektorat Wsparcia", country="PL", status="awarded")
        conn.execute("""INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated, winners_in_notice,
                                           cpv_main, resolution_method, resolution_confidence)
                        VALUES (%s, %s, 'PL', 'Megmar Logistics Sp. z o.o.', 1, '35400000', 'exact_name', 1.0)""", (opp, org))
    conn.execute("UPDATE organisation SET canonical_name = 'megmar logistics' WHERE id = %s", (org,))
    conn.commit()
    items = client.get("/v1/suppliers", params={"q": "leonardo"}).json()["items"]
    assert [(i["id"], i["name"], i["matchedAs"]) for i in items] == [
        (str(org), "Megmar Logistics Sp. z o.o.", "Konsorcjum: MEGMAR Logistics Sp. z o.o. Leonardo Poland Sp. z o.o.")]
    assert client.get("/v1/suppliers", params={"q": "megmar"}).json()["items"][0]["matchedAs"] is None


# ----------------------------------------------------------------------------------------------- D-15: past roles

def test_past_roles_count_the_projects_of_the_organisations_family_rows(conn):
    head = conn.execute("INSERT INTO organisation (canonical_name, country) VALUES ('tno', 'NL') RETURNING id").fetchone()["id"]
    variant = conn.execute("INSERT INTO organisation (canonical_name, country) VALUES ('tno defence', 'NL') RETURNING id"
                           ).fetchone()["id"]
    conn.execute("INSERT INTO organisation_family_member (org_id, head_org_id, method, confidence) VALUES (%s, %s, 'x', 0.9)",
                 (variant, head))
    prog = conn.execute("SELECT id FROM programme WHERE code = 'H2020'").fetchone()
    prog_id = prog["id"] if prog else conn.execute(
        "INSERT INTO programme (code, name) VALUES ('H2020', 'Horizon 2020') RETURNING id").fetchone()["id"]
    src = conn.execute("SELECT id FROM source WHERE code = 'cordis'").fetchone()["id"]
    for i, (org, role) in enumerate(((head, "coordinator"), (head, "participant"), (variant, "participant"))):
        p = conn.execute("INSERT INTO project (source_id, programme_id, native_id, acronym, title) VALUES (%s, %s, %s, %s, %s) "
                         "RETURNING id", (src, prog_id, f"P{i}", f"P{i}", f"Project {i}")).fetchone()["id"]
        conn.execute("INSERT INTO participation (project_id, organisation_id, role, resolution_method, resolution_confidence) "
                     "VALUES (%s, %s, %s, 'exact_name', 1.0)", (p, org, role))
    conn.commit()
    assert partners.past_roles(conn, [head])[head] == {"coordinator": 1, "participant": 2, "thirdParty": 0, "other": 0}


# ----------------------------------------------------------------------------------------------- D-14: consortium gaps

def test_the_gaps_say_how_many_projects_of_the_area_have_the_country(conn):
    from dgate.network_api import consortium_gaps

    got = consortium_gaps.__wrapped__(programme="EDF", topic=None, lacking="UA", minProjects=2, conn=conn)
    assert got["projectsWithLacking"] == 0


def test_a_split_decision_needs_its_member_and_head(conn):
    conn.execute("INSERT INTO organisation (id, canonical_name, country) VALUES (900001, 'a', 'DE'), (900002, 'b', 'DE')")
    conn.execute("""INSERT INTO resolution_review (org_a, org_b, proposed_relation, method, confidence, evidence, status)
                    VALUES (900001, 900002, %s, %s, 0.9, %s, 'rejected')""",
                 (buyer_split.SPLIT_RELATION, buyer_split.SPLIT, Jsonb({"head": 900001})))
    conn.commit()
    assert buyer_split.split_decisions(conn) == []
