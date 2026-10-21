"""WP-70 against a real Postgres: the bulk packages fill what the SPARQL load left empty or doubled, and nothing
else."""

from __future__ import annotations

import pytest

from dgate import networks
from dgate.ops import cordis_bulk
from tests.fakecordis import FakeCordis
from tests.integration import test_wp41_money_country as wp41
from tests.integration.test_wp41_money_country import _org, _project, _role, _rows
from tests.unit.test_cordis_bulk import make_package, org_line

pytestmark = pytest.mark.integration

env = wp41.env


def _dataset():
    orgs = [_org("o1", "111111111", "ALPHA UNIVERSITE", "FR"), _org("o2", "222222222", "BETA INSTITUT", "FR"),
            _org("o3", "333333333", "GAMMA SPA", "IT"), _org("o4", "444444444", "DELTA GMBH", "DE")]
    projects = [_project("p1", "2001", 3000000, ga="101000001"), _project("p2", "2002", 100000, ga="101000002"),
                _project("p3", "2003", 500000, ga="101000003")]
    roles = [
        _role("r1", "2001", "o1", "coordinator", 92035),     # doubled: the bulk says 46,017.50
        _role("r2", "2001", "o2", "participant"),            # no payment in the service: the bulk says 250,000
        _role("r3", "2001", "o3", "participant", 1652264.59),  # amended later: the bulk says 1,823,370.98, kept
        _role("r4", "2002", "o3", "coordinator", 120000),    # doubled, and project 2002 then fits its total again
        _role("r5", "2002", "o2", "participant", 30000),
        _role("r6", "2003", "o4", "coordinator", 200000),    # a project the bulk does not describe
        _role("r7", "2003", "o1", "participant"),
    ]
    return orgs, projects, roles


def _package(tmp_path):
    return make_package(tmp_path / "cordis-HORIZONprojects-csv.zip",
                        [("101000001", "2001"), ("101000002", "9002")], [   # 2002 only by its grant number
        org_line("101000001", "111111111", "coordinator", "46017.5"),
        org_line("101000001", "222222222", "participant", "250000"),
        org_line("101000001", "333333333", "participant", "1823370.98", "IT"),
        org_line("101000001", "555555555", "participant", "10"),            # a participant we never stored
        org_line("101000002", "333333333", "coordinator", "60000", "IT"),
        org_line("101000002", "222222222", "participant", "30000"),
        org_line("101000002", "444444444", "participant", "1", "DE"),        # DELTA is not in 2002 in our copy
    ])


def _dry(conn, paths):
    return cordis_bulk.run(conn, paths, apply=False, out=lambda *_: None)


def test_the_bulk_fills_and_undoubles_and_keeps_what_differs(conn, env, tmp_path):
    networks.run_cordis(sparql=FakeCordis(*_dataset()).sparql())
    before = _rows(conn)
    assert before[("2001", "222222222")] == (None, "no_payment_stated", None)
    assert before[("2002", "333333333")] == (None, "exceeds_project_total", 120000.0)
    paths = [_package(tmp_path)]

    lines: list[str] = []
    dry = cordis_bulk.run(conn, paths, apply=False, out=lines.append)
    assert _rows(conn) == before                                   # a dry run writes nothing
    assert dry["filled"] == 1 and dry["multiple"] == 2 and dry["differs_kept"] == 1
    assert dry["resettled"] == 1                                    # project 2002's participant gets its amount back
    assert dry["changed"] == 4 and dry["country_differs_kept"] == 0 and dry["country_empty"] == 0
    assert dry["bulk_participants_not_stored"] == 2 and dry["project_by_grant_number"] == 3
    assert any("HORIZON" in line and "filled" in line for line in lines)

    done = cordis_bulk.run(conn, paths, apply=True, out=lambda *_: None)
    assert done["changed"] == 4 and done["directory_rows"] > 0
    got = _rows(conn)
    assert got[("2001", "111111111")] == (46017.5, None, None)
    assert got[("2001", "222222222")] == (250000.0, None, None)
    assert got[("2001", "333333333")] == before[("2001", "333333333")]       # a stated amount is not overwritten
    assert got[("2002", "333333333")] == (60000.0, None, None)
    assert got[("2002", "222222222")] == (30000.0, None, None)
    assert got[("2003", "111111111")] == before[("2003", "111111111")]       # not in the bulk: untouched
    assert conn.execute("SELECT eu_contribution FROM organisation_network o JOIN organisation x "
                        "ON x.id = o.organisation_id WHERE x.eu_pic = '222222222'").fetchone()["eu_contribution"] == 280000

    again = cordis_bulk.run(conn, paths, apply=True, out=lambda *_: None)
    assert again["changed"] == 0 and _rows(conn) == got


def test_an_organisation_met_twice_is_one_row_and_a_country_is_only_compared(conn, env, tmp_path):
    networks.run_cordis(sparql=FakeCordis(*_dataset()).sparql())
    p = make_package(tmp_path / "cordis-h2020projects-csv.zip", [("101000003", "2003")], [
        org_line("101000003", "444444444", "coordinator", "200000", "AT"),
        org_line("101000003", "444444444", "participant", "1", "AT")])
    c = cordis_bulk.run(conn, [p], apply=True, out=lambda *_: None)
    # coordinator first, amounts added: 200,001 is not the 200,000 stored, so it is kept
    assert c["differs_kept"] == 1 and c["changed"] == 0
    assert c["country_differs_kept"] == 1
    assert conn.execute("SELECT country FROM organisation WHERE eu_pic = '444444444'").fetchone()["country"] == "DE"


def test_a_fill_that_would_withhold_the_amounts_of_its_project_is_dropped(conn, env, tmp_path):
    orgs, projects, roles = _dataset()
    networks.run_cordis(sparql=FakeCordis(orgs, [_project("p4", "2004", 100000, ga="101000004")], [
        _role("r8", "2004", "o1", "coordinator", 100000),     # the open data gives the host the whole grant
        _role("r9", "2004", "o2", "participant")]).sparql())
    before = _rows(conn)
    p = make_package(tmp_path / "cordis-HORIZONprojects-csv.zip", [("101000004", "2004")], [
        org_line("101000004", "111111111", "coordinator", "60000"),
        org_line("101000004", "222222222", "participant", "50000")])
    c = cordis_bulk.run(conn, [p], apply=True, out=lambda *_: None)
    assert c["fill_over_total"] == 1 and c["differs_kept"] == 1 and c["changed"] == 0
    assert _rows(conn) == before


def test_two_of_our_rows_on_one_pic_are_not_guessed_between(conn, env, tmp_path):
    networks.run_cordis(sparql=FakeCordis(*_dataset()).sparql())
    # a second organisation row carrying the same PIC, merged into the first, both in project 2001
    o1 = conn.execute("SELECT id FROM organisation WHERE eu_pic = '222222222'").fetchone()["id"]
    twin = conn.execute("""INSERT INTO organisation (canonical_name, country, merged_into)
                           VALUES ('beta institut twin', 'FR', %s) RETURNING id""", (o1,)).fetchone()["id"]
    pid = conn.execute("SELECT id FROM project WHERE cordis_id = '2001'").fetchone()["id"]
    conn.execute("""INSERT INTO participation (project_id, organisation_id, role, resolution_method,
                    resolution_confidence) VALUES (%s, %s, 'participant', 'pic', 1)""", (pid, twin))
    conn.commit()
    c = _dry(conn, [_package(tmp_path)])
    assert c["ambiguous"] == 2 and c["filled"] == 0
