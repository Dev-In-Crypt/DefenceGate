"""WP-43, N1 against a real Postgres: the amounts the loader stores when a role points to two organisation nodes,
and the repair of the amounts stored before the loader divided them."""

from __future__ import annotations

import pytest

from dgate import networks
from dgate.ops import repair_role_multiples
from tests.fakecordis import FakeCordis
from tests.integration import test_wp41_money_country as wp41
from tests.integration.test_wp41_money_country import _org, _project, _role, _rows

pytestmark = pytest.mark.integration

env = wp41.env          # the fixture of the file this one builds on


def _dataset(copies: str = "1"):
    orgs = [_org("o1", "111111111", "ALPHA UNIVERSITE", "FR"), _org("o2", "222222222", "BETA INSTITUT", "FR"),
            _org("o3", "333333333", "GAMMA SPA", "IT")]
    projects = [_project("p1", "2001", 1000000), _project("p2", "2002", 100000)]
    roles = [
        # the doubled payment of ENEN2plus: the service holds 46,017.50 and the sum came out 92,035
        {**_role("r1", "2001", "o1", "participant", 92035), "orgs": copies, "projects": "1"},
        _role("r2", "2001", "o2", "coordinator", 300000),
        # project 2002 only fits its EU contribution once the doubled payment is halved
        {**_role("r3", "2002", "o3", "participant", 120000), "orgs": copies, "projects": "1"},
        _role("r4", "2002", "o2", "participant", 30000),
    ]
    return orgs, projects, roles


def _load(fake):
    return networks.run_cordis(sparql=fake.sparql())


def _multi_rows():
    return [{"key": "r1", "project": "2001", "org": "x", "real_org": "o1", "pic": "111111111", "role": "participant",
             "amount": "92035", "orgs": "2", "projects": "1"},
            {"key": "r3", "project": "2002", "org": "x", "real_org": "o3", "pic": "333333333", "role": "participant",
             "amount": "120000", "orgs": "2", "projects": "1"}]


def test_the_loader_stores_the_payment_once(conn, env):
    _load(FakeCordis(*_dataset(copies="2")))
    got = _rows(conn)
    assert got[("2001", "111111111")] == (46017.5, None, None)
    assert got[("2002", "333333333")] == (60000.0, None, None)


def test_a_role_without_the_counts_is_stored_as_before(conn, env):
    _load(FakeCordis(*_dataset(copies="1")))
    assert _rows(conn)[("2001", "111111111")][0] == 92035.0


def test_the_repair_halves_the_stored_amounts_and_settles_the_project_again(conn, env):
    _load(FakeCordis(*_dataset(copies="1")))              # as production stored them: doubled
    before = _rows(conn)
    # 120,000 + 30,000 is more than the 100,000 the project got: every amount of project 2002 is withheld
    assert before[("2002", "333333333")] == (None, "exceeds_project_total", 120000.0)

    dry = repair_role_multiples.run(conn, _multi_rows(), apply=False, out=lambda *_: None)
    assert dry["corrected"] == 2 and _rows(conn) == before         # a dry run writes nothing

    done = repair_role_multiples.run(conn, _multi_rows(), apply=True, out=lambda *_: None)
    assert done["corrected"] == 2 and done["participations_changed"] >= 2
    got = _rows(conn)
    assert got[("2001", "111111111")] == (46017.5, None, None)
    # 60,000 + 30,000 fits the project again: the withheld amounts come back
    assert got[("2002", "333333333")] == (60000.0, None, None)
    assert got[("2002", "222222222")] == (30000.0, None, None)
    # what the repair did not name is untouched
    assert got[("2001", "222222222")] == before[("2001", "222222222")]

    again = repair_role_multiples.run(conn, _multi_rows(), apply=True, out=lambda *_: None)
    assert again["corrected"] == 0 and again["already_right_or_other"] == 2 and again["participations_changed"] == 0


def test_the_repair_leaves_alone_what_it_cannot_match(conn, env):
    _load(FakeCordis(*_dataset(copies="1")))
    before = _rows(conn)
    rows = [{**_multi_rows()[0], "pic": "999999999"}, {**_multi_rows()[0], "project": "9999"},
            {**_multi_rows()[0], "orgs": "1"}, {**_multi_rows()[0], "pic": "", "project": "9999"}]
    c = repair_role_multiples.run(conn, rows, apply=True, out=lambda *_: None)
    assert c["not_stored"] == 3 and c["nothing_to_correct"] == 1 and c["corrected"] == 0
    assert c["no_pic_unmatched"] == 1
    assert _rows(conn) == before


def test_an_organisation_without_a_pic_is_found_by_the_doubled_figure(conn, env):
    _load(FakeCordis(*_dataset(copies="1")))
    row = {**_multi_rows()[0], "pic": ""}
    c = repair_role_multiples.run(conn, [row], apply=True, out=lambda *_: None)
    assert c["by_amount"] == 1 and c["corrected"] == 1
    assert _rows(conn)[("2001", "111111111")] == (46017.5, None, None)


def test_two_participations_with_the_doubled_figure_are_not_guessed_between(conn, env):
    _load(FakeCordis(*_dataset(copies="1")))
    conn.execute("""UPDATE participation SET contribution = 92035 WHERE project_id =
                    (SELECT id FROM project WHERE cordis_id = '2001') AND role = 'coordinator'""")
    conn.execute("""UPDATE participation SET role = 'participant' WHERE project_id =
                    (SELECT id FROM project WHERE cordis_id = '2001') AND role = 'coordinator'""")
    conn.commit()
    before = _rows(conn)
    c = repair_role_multiples.run(conn, [{**_multi_rows()[0], "pic": ""}], apply=True, out=lambda *_: None)
    assert c["no_pic_unmatched"] == 1 and c["corrected"] == 0 and _rows(conn) == before


def test_the_repair_does_not_touch_an_amount_that_does_not_contain_the_doubled_figure(conn, env):
    _load(FakeCordis(*_dataset(copies="1")))
    conn.execute("""UPDATE participation SET contribution = 50000 WHERE project_id =
                    (SELECT id FROM project WHERE cordis_id = '2001') AND role = 'participant'""")
    conn.commit()
    c = repair_role_multiples.run(conn, _multi_rows()[:1], apply=True, out=lambda *_: None)
    assert c["already_right_or_other"] == 1 and _rows(conn)[("2001", "111111111")][0] == 50000.0
