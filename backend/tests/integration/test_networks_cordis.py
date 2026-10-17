"""The CORDIS import end to end against a real Postgres, with a stand-in for the SPARQL service."""

from __future__ import annotations

import copy

import pytest

from dgate import config, networks
from dgate.sources import cordis
from tests.fakecordis import FakeCordis, dataset

pytestmark = pytest.mark.integration


@pytest.fixture
def env(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("DGATE_FLOOR_CORDIS", "1")
    config.reset_cache()
    for kind in cordis.PAGE_SIZE:                       # tiny pages: the keyset is walked
        monkeypatch.setitem(cordis.PAGE_SIZE, kind, 2)
    conn.execute("UPDATE source SET active = FALSE WHERE code = 'cordis'")      # as the migration leaves it
    conn.commit()
    yield tmp_path
    conn.execute("UPDATE source SET active = FALSE WHERE code = 'cordis'")
    conn.commit()
    config.reset_cache()


def _counts(conn) -> dict[str, int]:
    return {t: conn.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"] for t in
            ("organisation", "organisation_alias", "project", "participation", "raw_ingest",
             "resolution_review")}


def _run(fake: FakeCordis, **kw):
    return networks.run_cordis(sparql=fake.sparql(), **kw)


def test_the_first_run_loads_organisations_projects_and_participations(conn, env):
    orgs, projects, roles = dataset()
    c = _run(FakeCordis(orgs, projects, roles))
    assert c["organisations_new"] == 4 and c["projects_new"] == 2 and c["participations_new"] == 5

    org = conn.execute("SELECT * FROM organisation WHERE eu_pic = '111111111'").fetchone()
    assert org["country"] == "FR" and org["canonical_name"] == "acme defence"
    assert org["display_name"] == "ACME DEFENCE SA" and org["pic_method"] == "source"
    assert float(org["pic_confidence"]) == 1.0 and org["vat_number"] == "11111111111"
    gamma = conn.execute("SELECT country FROM organisation WHERE eu_pic = '333333333'").fetchone()
    assert gamma["country"] == "GB"                     # CORDIS writes UK

    p1 = conn.execute("""SELECT p.*, pr.code AS prog FROM project p JOIN programme pr
                          ON pr.id = p.programme_id WHERE cordis_id = '1001'""").fetchone()
    assert p1["prog"] == "HORIZON" and p1["ga_number"] == "101000001"
    assert float(p1["eu_contribution"]) == 800000 and p1["topic_code"] == "HORIZON_HORIZON-CL4-2021-X-01"
    p2 = conn.execute("""SELECT pr.code AS prog FROM project p JOIN programme pr
                          ON pr.id = p.programme_id WHERE cordis_id = '1002'""").fetchone()
    assert p2["prog"] == "H2020"

    rows = conn.execute("""SELECT pa.role, pa.contribution, pa.resolution_method, pa.active,
                                  pa.resolution_confidence, o.eu_pic
                             FROM participation pa JOIN organisation o ON o.id = pa.organisation_id
                             JOIN project p ON p.id = pa.project_id
                            WHERE p.cordis_id = '1001' ORDER BY o.eu_pic""").fetchall()
    assert [(r["role"], float(r["contribution"]), r["resolution_method"]) for r in rows] == [
        ("coordinator", 300000.0, "pic"), ("participant", 500000.0, "pic")]
    assert all(r["active"] and float(r["resolution_confidence"]) == 1.0 for r in rows)
    third = conn.execute("SELECT role, contribution FROM participation pa JOIN organisation o "
                         "ON o.id = pa.organisation_id WHERE o.eu_pic = '333333333'").fetchone()
    assert third["role"] == "third_party" and third["contribution"] is None

    run = conn.execute("SELECT status, records_fetched, detail FROM ingest_run").fetchone()
    assert run["status"] == "success" and run["records_fetched"] == 4 + 2 + 5
    assert run["detail"]["expected_roles"] == 5


def test_a_second_run_creates_nothing_and_changes_nothing(conn, env):
    orgs, projects, roles = dataset()
    _run(FakeCordis(orgs, projects, roles))
    before = _counts(conn)
    c = _run(FakeCordis(orgs, projects, roles))
    assert _counts(conn) == before
    assert c["new"] == 0 and c["changed"] == 0 and c["participations_deactivated"] == 0


def test_a_changed_amount_and_a_vanished_participant_are_recorded_not_deleted(conn, env):
    orgs, projects, roles = dataset()
    _run(FakeCordis(orgs, projects, roles))
    roles2 = [dict(r) for r in roles if r["key"] != "r2"]
    roles2[0]["amount"] = "310000"
    projects2 = copy.deepcopy(projects)
    projects2[0]["status"] = "CLOSED"
    c = _run(FakeCordis(orgs, projects2, roles2))
    assert c["participations_changed"] == 1 and c["participations_deactivated"] == 1
    assert c["projects_changed"] == 1
    gone = conn.execute("""SELECT pa.active FROM participation pa JOIN organisation o
                             ON o.id = pa.organisation_id WHERE o.eu_pic = '222222222'""").fetchone()
    assert gone["active"] is False
    assert conn.execute("SELECT count(*) AS n FROM participation").fetchone()["n"] == 5
    # and if the participant comes back it is active again, without a second row
    c = _run(FakeCordis(orgs, projects2, roles2 + [roles[1]]))
    assert c["participations_changed"] == 1
    assert conn.execute("SELECT count(*) AS n FROM participation").fetchone()["n"] == 5
    assert conn.execute("SELECT active FROM participation pa JOIN organisation o ON "
                        "o.id = pa.organisation_id WHERE o.eu_pic = '222222222'"
                        ).fetchone()["active"] is True


def test_the_same_organisation_twice_in_a_project_is_one_participation(conn, env):
    orgs, projects, roles = dataset()
    roles = roles + [{"key": "r9", "project": "1001", "org": "o2", "role": "coordinator",
                      "amount": "5"}]
    c = _run(FakeCordis(orgs, projects, roles))
    assert c["roles_duplicate"] == 1
    row = conn.execute("""SELECT role, contribution FROM participation pa JOIN organisation o
                            ON o.id = pa.organisation_id JOIN project p ON p.id = pa.project_id
                           WHERE o.eu_pic = '222222222' AND p.cordis_id = '1001'""").fetchone()
    assert row["role"] == "coordinator" and float(row["contribution"]) == 500005.0
    # and a second run writes nothing: the merged row is compared with the merged value, not with
    # the first sight of the organisation (131 spurious changes a run on the real data)
    before = _counts(conn)
    again = _run(FakeCordis(orgs, projects, roles))
    assert again["new"] == 0 and again["changed"] == 0 and _counts(conn) == before


def test_an_organisation_we_know_by_name_gets_its_pic_instead_of_a_twin(conn, env):
    existing = conn.execute(
        "INSERT INTO organisation (canonical_name, country) VALUES ('acme defence', 'FR') "
        "RETURNING id").fetchone()["id"]
    conn.commit()
    orgs, projects, roles = dataset()
    c = _run(FakeCordis(orgs, projects, roles))
    row = conn.execute("SELECT eu_pic, pic_method, pic_confidence FROM organisation WHERE id = %s",
                       (existing,)).fetchone()
    assert row["eu_pic"] == "111111111" and row["pic_method"] == "exact_name"
    assert float(row["pic_confidence"]) == 0.95
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE canonical_name = 'acme defence'"
                        ).fetchone()["n"] == 1
    assert c["organisations_new"] == 3
    method = conn.execute("""SELECT pa.resolution_method FROM participation pa
                              WHERE pa.organisation_id = %s LIMIT 1""", (existing,)).fetchone()
    assert method["resolution_method"] == "exact_name"


def test_two_registered_entities_with_one_name_stay_two_organisations_and_wait_for_a_person(conn, env):
    orgs, projects, roles = dataset()
    orgs.append({"key": "o5", "pic": "555555555", "rcn": "5", "name": "ACME DEFENCE S.A.",
                 "vat": "", "country": "FR"})
    _run(FakeCordis(orgs, projects, roles))
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE canonical_name = 'acme defence'"
                        ).fetchone()["n"] == 2
    review = conn.execute("SELECT method, status FROM resolution_review").fetchall()
    assert [(r["method"], r["status"]) for r in review] == [("pic_conflict", "open")]


def test_no_organisation_is_merged_by_the_import(conn, env):
    orgs, projects, roles = dataset()
    orgs.append({"key": "o6", "pic": "666666666", "rcn": "6", "name": "ACME DEFENSE SA",
                 "vat": "", "country": "FR"})
    _run(FakeCordis(orgs, projects, roles), candidates=True)
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE merged_into IS NOT NULL"
                        ).fetchone()["n"] == 0
    kinds = {r["method"] for r in conn.execute("SELECT method FROM resolution_review").fetchall()}
    assert kinds <= {"trigram", "pic_conflict", "exact_name_ambiguous"}


def test_a_partial_read_is_refused_and_leaves_nothing_inactive(conn, env):
    orgs, projects, roles = dataset()
    _run(FakeCordis(orgs, projects, roles))
    lying = FakeCordis(orgs, projects, roles[:2], claimed={"roles": 400})
    with pytest.raises(RuntimeError, match="not loading a partial copy"):
        _run(lying)
    assert conn.execute("SELECT count(*) AS n FROM participation WHERE NOT active"
                        ).fetchone()["n"] == 0
    runs = conn.execute("SELECT status FROM ingest_run ORDER BY id").fetchall()
    assert [r["status"] for r in runs] == ["success", "failed"]
    # a failed run keeps the counters of what it had read
    assert conn.execute("SELECT records_fetched FROM ingest_run ORDER BY id DESC LIMIT 1"
                        ).fetchone()["records_fetched"] >= 6


def test_robots_disallowing_the_sparql_path_stops_before_anything_is_asked(conn, env):
    orgs, projects, roles = dataset()
    fake = FakeCordis(orgs, projects, roles, robots="User-agent: *\nDisallow: /datalab/\n")
    with pytest.raises(cordis.RobotsDisallowed):
        _run(fake)
    assert fake.requests == []
    assert conn.execute("SELECT count(*) AS n FROM ingest_run").fetchone()["n"] == 0


def test_a_programme_filter_loads_that_framework_and_deactivates_nobody_else(conn, env):
    orgs, projects, roles = dataset()
    _run(FakeCordis(orgs, projects, roles))
    c = _run(FakeCordis(orgs, projects, roles), programmes={"HORIZON"})
    assert c["projects_out_of_scope"] == 1 and c["roles_unlinked"] == 3
    assert c["participations_deactivated"] == 0
    assert conn.execute("SELECT count(*) AS n FROM participation WHERE NOT active"
                        ).fetchone()["n"] == 0


def test_a_rehearsal_reads_a_few_pages_and_marks_nobody_inactive(conn, env):
    orgs, projects, roles = dataset()
    _run(FakeCordis(orgs, projects, roles))
    c = _run(FakeCordis(orgs, projects, roles), max_pages=1)
    assert c["organisations_seen"] == 2 and "participations_deactivated" not in c


def test_an_organisation_without_a_country_is_counted_and_skipped(conn, env):
    orgs, projects, roles = dataset()
    orgs[3]["country"] = ""
    c = _run(FakeCordis(orgs, projects, roles))
    assert c["organisations_no_country"] == 1 and c["roles_unlinked"] == 1


def test_the_raw_pages_are_landed_once_per_content(conn, env):
    orgs, projects, roles = dataset()
    _run(FakeCordis(orgs, projects, roles))
    first = conn.execute("SELECT count(*) AS n FROM raw_ingest").fetchone()["n"]
    assert first == 2 + 1 + 3          # 4 orgs, 2 projects, 5 roles at 2 a page, plus the pages
    _run(FakeCordis(orgs, projects, roles))
    assert conn.execute("SELECT count(*) AS n FROM raw_ingest").fetchone()["n"] == first


def test_the_source_is_invisible_to_health_until_its_first_run_and_never_stale_afterwards(conn, env):
    from fastapi.testclient import TestClient

    from dgate import api

    orgs, projects, roles = dataset()
    with TestClient(api.app) as client:
        before = client.get("/v1/health").json()
        assert "cordis" not in [s["code"] for s in before["sources"]]
        assert "cordis" not in before["unhealthy_sources"]

        _run(FakeCordis(orgs, projects, roles))
        conn.execute("UPDATE ingest_run SET finished_at = now() - interval '40 days', "
                     "started_at = now() - interval '40 days'")
        conn.commit()
        after = client.get("/v1/health").json()
        item = next(s for s in after["sources"] if s["code"] == "cordis")
        # a monthly source is not late for having last run forty days ago
        assert item["status"] == "success" and item["health"] == "healthy"
        assert "cordis" not in after["unhealthy_sources"]

        failing = FakeCordis(orgs, projects, roles[:2], claimed={"roles": 400})
        with pytest.raises(RuntimeError):
            _run(failing)
        broken = client.get("/v1/health").json()
        assert "cordis" in broken["unhealthy_sources"]               # a failed month does show


def test_the_source_is_a_grant_source_so_the_public_list_does_not_call_it_tenders(conn, env):
    assert conn.execute("SELECT kind FROM source WHERE code = 'cordis'").fetchone()["kind"] == "grant"
