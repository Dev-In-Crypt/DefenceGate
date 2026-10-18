"""WP-43 against a real Postgres: the directory shows and sorts by the defence-relevant count when it is limited to the
defence programmes, and an organisation's country says what it rests on."""

from __future__ import annotations

import pytest

from dgate import networks
from dgate.ops import org_countries
from tests.fakecordis import FakeCordis
from tests.integration import test_network_api as net
from tests.integration import test_wp41_money_country as wp41
from tests.integration.test_network_api import org, slug_of
from tests.integration.test_wp41_money_country import _org, _project, _role, csic_orgs

pytestmark = pytest.mark.integration

# the fixtures of the two files this one builds on
_fresh_cache, client, world, env = net._fresh_cache, net.client, net.world, wp41.env


def _names(body):
    return [i["name"] for i in body["items"]]


def test_the_defence_directory_counts_and_orders_by_the_defence_projects(client, world):
    body = client.get("/v1/organisations?programme=EDF,EDIDP,PADR").json()
    got = {i["name"]: (i["defenceProjects"], i["projects"]) for i in body["items"]}
    # Echo took part in four EDF projects; Bravo in four plus a fifth through the name merged into it: three EDF
    # (p3, p4 and p5 through the merged row) and two civil
    assert got["ECHO IBERICA SL"] == (4, 4)
    assert got["BRAVO INGÉNIERIE SAS"] == (3, 5)
    assert got["ALPHA SYSTEMS GMBH"] == (2, 4)
    assert got["FOXTROT SRL"] == (2, 2)
    assert _names(body) == ["ECHO IBERICA SL", "BRAVO INGÉNIERIE SAS", "ALPHA SYSTEMS GMBH", "FOXTROT SRL"]
    assert body["meta"]["sort"] == "defence"
    assert body["meta"]["defenceProgrammes"] == ["EDF", "EDIDP", "PADR"]
    assert "every programme" in body["meta"]["countsNote"]


def test_all_programmes_stays_ordered_by_all_projects(client, world):
    body = client.get("/v1/organisations").json()
    assert body["meta"]["sort"] == "projects"
    assert _names(body)[0] == "BRAVO INGÉNIERIE SAS"          # five projects in all programmes
    # the same organisations ordered by the defence figure, when asked for outright
    asked = client.get("/v1/organisations?sort=defence").json()
    assert asked["meta"]["sort"] == "defence" and _names(asked)[0] == "ECHO IBERICA SL"


def test_a_civil_programme_filter_is_not_ordered_by_the_defence_figure(client, world):
    body = client.get("/v1/organisations?programme=H2020,HORIZON").json()
    assert body["meta"]["sort"] == "projects"
    assert all(i["defenceProjects"] >= 0 for i in body["items"])


def test_projects_of_other_programmes_do_not_count_as_defence(client, world):
    got = {i["name"]: i["defenceProjects"] for i in client.get("/v1/organisations").json()["items"]}
    assert got["DELTA SP. Z O.O."] == 0 and got["KYIV INSTITUTE"] == 0


def test_an_unknown_sort_is_refused(client, world):
    assert client.get("/v1/organisations?sort=wealth").status_code == 422


def test_the_name_order_is_still_there(client, world):
    names = _names(client.get("/v1/organisations?programme=EDF&sort=name").json())
    assert names == sorted(names)


def test_the_profile_says_what_the_country_rests_on(client, conn, world):
    conn.execute("UPDATE organisation SET country_basis = 'several', country_sites = ARRAY['NL','PT']::char(2)[] "
                 "WHERE id = %s", (world.A,))
    conn.commit()
    body = client.get(f"/v1/organisations/{slug_of(client, world.A)}").json()
    assert body["countryBasis"] == "several" and body["countrySites"] == ["NL", "PT"]
    other = client.get(f"/v1/organisations/{slug_of(client, world.B)}").json()
    assert other["countryBasis"] is None and other["countrySites"] == []


# ----------------------------------------------------------------- the country report

def test_the_country_report_counts_before_and_after_and_writes_only_with_yes(conn, env):
    orgs = csic_orgs() + [_org("o2", "222222222", "BETA INSTITUT", "FR")]
    projects = [_project("p1", "2001", 100)]
    roles = [_role("r1", "2001", "o1", "coordinator", 100), _role("r2", "2001", "o2", "participant", 0)]
    networks.run_cordis(sparql=FakeCordis(orgs, projects, roles).sparql())
    # as production stood: no basis anywhere, CSIC under Italy
    conn.execute("UPDATE organisation SET country_basis = NULL, country_sites = NULL")
    conn.execute("UPDATE organisation SET country = 'IT' WHERE eu_pic = '999991722'")
    conn.commit()
    lines: list[str] = []

    dry = org_countries.run(apply=False, sparql=FakeCordis(orgs, [], []).sparql(), out=lines.append)
    assert dry["countries_changed"] == 1 and dry["organisations_country_by_vote"] == 1
    assert "'not looked at': 2" in lines[0] and "'not looked at': 2" in lines[1]      # a dry run writes nothing
    assert conn.execute("SELECT country FROM organisation WHERE eu_pic = '999991722'").fetchone()["country"] == "IT"

    lines.clear()
    done = org_countries.run(apply=True, sparql=FakeCordis(orgs, [], []).sparql(), out=lines.append)
    assert done["countries_changed"] == 1
    rows = {r["eu_pic"]: (r["country"], r["country_basis"]) for r in conn.execute(
        "SELECT eu_pic, country, country_basis FROM organisation WHERE eu_pic IS NOT NULL").fetchall()}
    assert rows == {"999991722": ("ES", "vote"), "222222222": ("FR", "address")}
    assert "'vote': 1" in lines[1] and "'address': 1" in lines[1]

    again = org_countries.run(apply=True, sparql=FakeCordis(orgs, [], []).sparql(), out=lambda *_: None)
    assert again["countries_changed"] == 0 and again["bases_set"] == 0                # idempotent
    # nobody was merged and nobody deleted
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE merged_into IS NOT NULL").fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) AS n FROM organisation").fetchone()["n"] == 2


def test_the_basis_is_a_closed_list(conn):
    o = org(conn, "zulu", "DE", "999000009", "ZULU GMBH")
    conn.commit()
    with pytest.raises(Exception, match="country_basis_check"):
        conn.execute("UPDATE organisation SET country_basis = 'guess' WHERE id = %s", (o,))
    conn.rollback()
    conn.execute("UPDATE organisation SET country_basis = 'address' WHERE id = %s", (o,))
    conn.rollback()
