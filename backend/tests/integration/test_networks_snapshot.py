"""Consortium snapshots and the consortium.changed rows, the report, and the grants of the tables."""

from __future__ import annotations

from datetime import date
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from dgate import db, migrate, networks
from dgate.ops import networks_report

pytestmark = pytest.mark.integration


def _project(conn, native: str, programme: str = "EDF", **cols) -> int:
    src = conn.execute("SELECT id FROM source WHERE code = 'cordis'").fetchone()["id"]
    prog = conn.execute("SELECT id FROM programme WHERE code = %s", (programme,)).fetchone()["id"]
    return conn.execute(
        """INSERT INTO project (source_id, programme_id, native_id, title, call_year, start_date)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (src, prog, native, f"Project {native}", cols.get("year", 2024),
         cols.get("start"))).fetchone()["id"]


def _org(conn, name: str, country: str, pic: str | None = None) -> int:
    return conn.execute(
        "INSERT INTO organisation (canonical_name, display_name, country, eu_pic) "
        "VALUES (%s, %s, %s, %s) RETURNING id", (name, name.upper(), country, pic)).fetchone()["id"]


def _join(conn, project: int, org: int, role: str = "participant", active: bool = True,
          contribution=None) -> int:
    return conn.execute(
        """INSERT INTO participation (project_id, organisation_id, role, contribution,
                                      resolution_method, resolution_confidence, active)
           VALUES (%s, %s, %s, %s, 'pic', 1, %s) RETURNING id""",
        (project, org, role, contribution, active)).fetchone()["id"]


def test_two_snapshots_with_a_synthetic_change_give_exactly_one_event(conn):
    p = _project(conn, "a")
    o1, o2, o3 = _org(conn, "one", "FR"), _org(conn, "two", "DE"), _org(conn, "three", "PL")
    _join(conn, p, o1, "coordinator")
    _join(conn, p, o2)
    conn.commit()

    first = networks.snapshot_consortia(conn, date(2026, 9, 1))
    assert first == {"snapshots": 1, "changes": 0, "projects": 1}     # nothing to compare yet
    snap = conn.execute("SELECT * FROM consortium_snapshot").fetchone()
    assert snap["member_org_ids"] == sorted([o1, o2]) and snap["coordinator_org_id"] == o1
    assert (snap["member_count"], snap["country_count"]) == (2, 2)

    _join(conn, p, o3)                                      # a partner joins
    conn.commit()
    second = networks.snapshot_consortia(conn, date(2026, 10, 1))
    assert second == {"snapshots": 1, "changes": 1, "projects": 1}
    ev = conn.execute("SELECT * FROM consortium_change").fetchall()
    assert len(ev) == 1
    assert ev[0]["added_org_ids"] == [o3] and ev[0]["removed_org_ids"] == []
    assert ev[0]["coordinator_before"] == o1 and ev[0]["coordinator_after"] == o1
    assert ev[0]["observed_at"] == date(2026, 10, 1)
    assert conn.execute("SELECT count(*) AS n FROM consortium_snapshot").fetchone()["n"] == 2


def test_an_unchanged_consortium_gets_no_new_snapshot_and_no_event(conn):
    p = _project(conn, "a")
    _join(conn, p, _org(conn, "one", "FR"), "coordinator")
    conn.commit()
    networks.snapshot_consortia(conn, date(2026, 9, 1))
    again = networks.snapshot_consortia(conn, date(2026, 10, 1))
    assert again["snapshots"] == 0 and again["changes"] == 0
    assert conn.execute("SELECT count(*) AS n FROM consortium_snapshot").fetchone()["n"] == 1
    # the same day twice is harmless as well
    networks.snapshot_consortia(conn, date(2026, 10, 1))
    assert conn.execute("SELECT count(*) AS n FROM consortium_snapshot").fetchone()["n"] == 1


def test_a_participant_who_left_and_a_new_coordinator_are_one_event(conn):
    p = _project(conn, "a")
    o1, o2 = _org(conn, "one", "FR"), _org(conn, "two", "DE")
    j1, j2 = _join(conn, p, o1, "coordinator"), _join(conn, p, o2)
    conn.commit()
    networks.snapshot_consortia(conn, date(2026, 9, 1))
    conn.execute("UPDATE participation SET active = FALSE WHERE id = %s", (j1,))
    conn.execute("UPDATE participation SET role = 'coordinator' WHERE id = %s", (j2,))
    conn.commit()
    out = networks.snapshot_consortia(conn, date(2026, 10, 1))
    assert out["changes"] == 1
    ev = conn.execute("SELECT * FROM consortium_change").fetchone()
    assert ev["removed_org_ids"] == [o1] and ev["added_org_ids"] == []
    assert (ev["coordinator_before"], ev["coordinator_after"]) == (o1, o2)


def test_projects_are_snapshotted_independently(conn):
    a, b = _project(conn, "a"), _project(conn, "b")
    o1, o2 = _org(conn, "one", "FR"), _org(conn, "two", "DE")
    _join(conn, a, o1)
    _join(conn, b, o1)
    conn.commit()
    networks.snapshot_consortia(conn, date(2026, 9, 1))
    _join(conn, b, o2)
    conn.commit()
    out = networks.snapshot_consortia(conn, date(2026, 10, 1))
    assert out == {"snapshots": 1, "changes": 1, "projects": 2}
    assert conn.execute("SELECT project_id FROM consortium_change").fetchone()["project_id"] == b


def test_a_merged_organisation_is_counted_as_the_one_it_was_merged_into(conn):
    p = _project(conn, "a")
    keep, gone = _org(conn, "keep", "FR"), _org(conn, "gone", "FR")
    _join(conn, p, gone)
    conn.commit()
    networks.snapshot_consortia(conn, date(2026, 9, 1))
    conn.execute("UPDATE organisation SET merged_into = %s WHERE id = %s", (keep, gone))
    conn.commit()
    out = networks.snapshot_consortia(conn, date(2026, 10, 1))
    assert out["changes"] == 1
    ev = conn.execute("SELECT added_org_ids, removed_org_ids FROM consortium_change").fetchone()
    assert ev["added_org_ids"] == [keep] and ev["removed_org_ids"] == [gone]


# ------------------------------------------------------------------ the report

def test_the_report_counts_programmes_coordinators_missing_pics_and_the_review_queue(conn):
    p1 = _project(conn, "a", "EDF", year=2024)
    p2 = _project(conn, "b", "HORIZON", start=date(2022, 3, 1))
    big, small = _org(conn, "bigco", "FR", "111111111"), _org(conn, "smallco", "DE")
    _join(conn, p1, big, "coordinator", contribution=10)
    _join(conn, p1, small)
    _join(conn, p2, big, "coordinator")
    conn.execute("INSERT INTO resolution_review (org_a, org_b, proposed_relation, method) "
                 "VALUES (%s, %s, 'same', 'trigram')", (big, small))
    conn.commit()
    rep = networks_report.build(conn)
    by = {(r["programme"], r["year"]): r for r in rep["per_programme_year"]}
    assert by[("EDF", 2024)]["projects"] == 1 and by[("EDF", 2024)]["participations"] == 2
    assert by[("HORIZON", 2022)]["participations"] == 1
    assert rep["top_coordinators"][0]["name"] == "BIGCO" and rep["top_coordinators"][0]["projects_coordinated"] == 2
    assert rep["participants_without_pic"] == [{"source": "cordis", "organisations": 1, "participations": 1}]
    assert rep["review_queue"] == [{"method": "trigram", "status": "open", "pairs": 1}]
    assert [r["name"] for r in rep["edf_top_organisations"]] == ["BIGCO", "SMALLCO"]
    text = networks_report.format_text(rep)
    assert "BIGCO" in text and "Resolution review queue" in text
    only = networks_report.build(conn, "EDF")
    assert [r["programme"] for r in only["per_programme_year"]] == ["EDF"]
    plan = networks_report.explain(conn)
    assert "-- top_coordinators" in plan and "Execution Time" in plan


# ------------------------------------------------------------------ the roles

def _as(dsn: str, role: str, password: str) -> str:
    parts = urlsplit(dsn)
    return urlunsplit(parts._replace(netloc=f"{role}:{password}@{parts.hostname}:{parts.port}"))


@pytest.fixture()
def service_roles(conn, schema, monkeypatch):
    monkeypatch.setenv("DGATE_API_PASSWORD", "api-test-password-1")
    monkeypatch.setenv("DGATE_WORKER_PASSWORD", "worker-test-password-1")
    with db.connect(schema) as admin:
        assert migrate.set_role_passwords(admin) == ["dgate_api", "dgate_worker"]
    return {"api": _as(schema, "dgate_api", "api-test-password-1"),
            "worker": _as(schema, "dgate_worker", "worker-test-password-1")}


NETWORK_TABLES = ("project", "participation", "consortium_snapshot", "consortium_change",
                  "project_factsheet", "resolution_review", "resolution_gold")


def test_the_api_reads_the_network_tables_and_cannot_write_them(conn, service_roles):
    with psycopg.connect(service_roles["api"], autocommit=True) as c:
        for table in NETWORK_TABLES:
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone()[0] >= 0
        with pytest.raises(psycopg.Error):
            c.execute("UPDATE project SET title = 'x'")


def test_the_worker_writes_the_network_tables_and_can_delete_none_of_them(conn, service_roles):
    p = _project(conn, "a")
    conn.commit()
    with psycopg.connect(service_roles["worker"], autocommit=True) as c:
        c.execute("UPDATE project SET title = title WHERE id = %s", (p,))
        for table in NETWORK_TABLES:
            if table != "resolution_gold":
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    c.execute(f"DELETE FROM {table}")
        with pytest.raises(psycopg.Error):
            c.execute("TRUNCATE project CASCADE")
