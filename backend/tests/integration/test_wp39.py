"""WP-39, data protection fixes (verify2-abuse N1-N10) against a real Postgres."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dgate import changes, config, individuals, networks, stats, suppliers
from dgate.ops import clean_suppliers, mark_individuals, suppress

# The worlds of the two features these fixes touch: their fixtures, used as they are.
from . import test_network_api as net
from . import test_supplier_map as sup
from .test_network_api import join, org
from .test_supplier_map import FakeTed, put_notice, rec, run

_fresh_cache, client, world, env = net._fresh_cache, net.client, net.world, sup.env

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)


def names(client, path="/v1/organisations?pageSize=100"):
    return [i["name"] for i in client.get(path).json()["items"]]


# ============================================================== N1: contact data in a supplier's identifiers

def seed_suppliers(conn, env):
    """Three German suppliers (one with a telephone number as identifier), one Estonian (an address)."""
    for n, cpv in enumerate(["35400000", "35400000", "35100000", "35100000"], 1):
        put_notice(conn, f"{n}-2026", cpv=(cpv,))
    fake = FakeTed([
        rec("1-2026", [("Krauss Maffei Wegmann GmbH", "DEU", "+49 89-81404707")]),
        rec("2-2026", [("Rheinmetall Waffe Munition GmbH", "DEU", "DE190270455")]),
        rec("3-2026", [("Hensoldt Sensors GmbH", "DEU", "DE333444555")]),
        rec("4-2026", [("Eqqus Ltd OU", "EST", "andrei@eqqus.ee")]),
    ])
    return run(fake)


def slug_of(client, name: str) -> str:
    return next(i["slug"] for i in client.get("/v1/suppliers?pageSize=100").json()["items"] if i["name"] == name)


def test_the_loader_stores_no_telephone_number_or_address_as_an_identifier(conn, env, client):
    seed_suppliers(conn, env)
    stored = {r["name_as_stated"]: r["identifier_as_stated"]
              for r in conn.execute("SELECT name_as_stated, identifier_as_stated FROM award").fetchall()}
    assert stored["Krauss Maffei Wegmann GmbH"] is None and stored["Eqqus Ltd OU"] is None
    assert stored["Rheinmetall Waffe Munition GmbH"] == "DE190270455"
    # and the telephone digits did not become the organisation's registration number
    reg = {r["canonical_name"]: r["national_reg_no"] for r in conn.execute(
        "SELECT canonical_name, national_reg_no FROM organisation WHERE canonical_name LIKE '%maffei%'").fetchall()}
    assert list(reg.values()) == [None]
    for name in ("Krauss Maffei Wegmann GmbH", "Eqqus Ltd OU"):
        body = client.get(f"/v1/suppliers/{slug_of(client, name)}").json()
        assert body["identifiers"] == [] and "@" not in str(body) and "81404707" not in str(body)


def test_a_profile_never_shows_what_an_older_load_stored(conn, env, client):
    """Rows stored before the fix: the profile filters on output, whatever the table holds."""
    seed_suppliers(conn, env)
    conn.execute("""UPDATE award SET identifier_as_stated = '+49 89-81404707'
                     WHERE name_as_stated LIKE 'Krauss%'""")
    conn.execute("UPDATE award SET identifier_as_stated = 'andrei@eqqus.ee' WHERE name_as_stated LIKE 'Eqqus%'")
    conn.execute("UPDATE award SET identifier_as_stated = 'Unknown' WHERE name_as_stated LIKE 'Hensoldt%'")
    conn.commit()
    for name in ("Krauss Maffei Wegmann GmbH", "Eqqus Ltd OU", "Hensoldt Sensors GmbH"):
        body = client.get(f"/v1/suppliers/{slug_of(client, name)}").json()
        assert body["identifiers"] == [], name
        assert "81404707" not in str(body) and "eqqus.ee" not in str(body)
    ok = client.get(f"/v1/suppliers/{slug_of(client, 'Rheinmetall Waffe Munition GmbH')}").json()
    assert ok["identifiers"] == ["DE190270455"]


def test_the_cleaner_removes_the_stored_contact_data_and_the_number_made_from_it(conn, env):
    seed_suppliers(conn, env)
    kmw = conn.execute("SELECT id FROM organisation WHERE canonical_name LIKE 'krauss%'").fetchone()["id"]
    conn.execute("UPDATE award SET identifier_as_stated = '+49 89-81404707' WHERE organisation_id = %s", (kmw,))
    conn.execute("""UPDATE organisation SET national_reg_no = '498981404707', identifier_method = 'identifier',
                                            identifier_confidence = 0.9 WHERE id = %s""", (kmw,))
    conn.execute("UPDATE award SET identifier_as_stated = 'Unknown' WHERE name_as_stated LIKE 'Hensoldt%'")
    conn.commit()

    dry = clean_suppliers.run(conn)
    assert dry["identifier_contact"] == 1 and dry["identifier_not_a_number"] == 1 and dry["organisations_reg_cleared"] == 1
    assert conn.execute("SELECT count(*) AS n FROM award WHERE identifier_as_stated IS NULL").fetchone()["n"] == 1   # a dry run writes nothing

    done = clean_suppliers.run(conn, write=True)
    assert done["organisations_reg_cleared"] == 1
    assert conn.execute("SELECT identifier_as_stated FROM award WHERE organisation_id = %s", (kmw,)).fetchone() == {
        "identifier_as_stated": None}
    org_row = conn.execute("SELECT national_reg_no, identifier_method FROM organisation WHERE id = %s", (kmw,)).fetchone()
    assert org_row == {"national_reg_no": None, "identifier_method": None}
    # a number that is a real one is left alone
    assert conn.execute("SELECT national_reg_no FROM organisation WHERE canonical_name LIKE 'rheinmetall%'"
                        ).fetchone()["national_reg_no"] == "190270455"
    # idempotent: a second run finds nothing
    again = clean_suppliers.run(conn, write=True)
    assert (again["identifier_contact"], again["identifier_not_a_number"], again["organisations_reg_cleared"],
            again["excluded_new"]) == (0, 0, 0, 0)


# ============================================================== N8: names that are no supplier

def test_the_loader_does_not_make_suppliers_of_placeholders_consortium_strings_and_garbled_names(conn, env, client):
    for n in range(1, 6):
        put_notice(conn, f"{n}-2026")
    fake = FakeTed([
        rec("1-2026", [("keine Angabe", "DEU", "DE0000000")]),
        rec("2-2026", [("Lider konsorcjum: A Sp. z o.o., Partner konsorcjum: B Sp. z o.o.", "POL", None)]),
        rec("3-2026", [("Wojskowe Zak¿ady Uzbrojenia S.A.", "POL", None)]),
        rec("4-2026", [("Stekop Spółka Akcyjna - Lider", "POL", "PL1234567890")]),
        rec("5-2026", [("Nammo Raufoss AS", "NOR", "NO923456789")]),
    ])
    c = run(fake)
    assert c["skipped_placeholder"] == 1 and c["skipped_consortium_string"] == 1 and c["skipped_garbled"] == 1
    got = [r["name_as_stated"] for r in conn.execute("SELECT name_as_stated FROM award ORDER BY 1").fetchall()]
    assert got == ["Nammo Raufoss AS", "Stekop Spółka Akcyjna"]
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE canonical_name LIKE '%angabe%'").fetchone()["n"] == 0
    assert sorted(i["name"] for i in client.get("/v1/suppliers?pageSize=100").json()["items"]) == [
        "Nammo Raufoss AS", "Stekop Spółka Akcyjna"]


def test_the_cleaner_excludes_stored_rows_and_every_supplier_query_skips_them(conn, env, client):
    seed_suppliers(conn, env)
    # rows an older loader made
    other = conn.execute("INSERT INTO organisation (canonical_name, country) VALUES ('keine angabe', 'DE') RETURNING id"
                         ).fetchone()["id"]
    opp = put_notice(conn, "9-2026")
    conn.execute("""INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated, winners_in_notice,
                                       cpv_main, resolution_method, resolution_confidence)
                    VALUES (%s, %s, 'DE', 'keine Angabe', 1, '35400000', 'exact_name', 1.0)""", (opp, other))
    conn.commit()
    assert "keine angabe" in [i["name"].lower() for i in client.get("/v1/suppliers?pageSize=100").json()["items"]]

    dry = clean_suppliers.run(conn)
    assert dry["excluded"]["placeholder"] == 1 and dry["excluded_new"] == 1
    assert conn.execute("SELECT count(*) AS n FROM award WHERE excluded_reason IS NOT NULL").fetchone()["n"] == 0   # a dry run

    clean_suppliers.run(conn, write=True)
    assert conn.execute("SELECT excluded_reason FROM award WHERE organisation_id = %s", (other,)).fetchone() == {
        "excluded_reason": "placeholder"}
    assert conn.execute("SELECT count(*) AS n FROM award").fetchone()["n"] == 5          # nothing was deleted
    assert "keine angabe" not in [i["name"].lower() for i in client.get("/v1/suppliers?pageSize=100").json()["items"]]
    assert client.get(f"/v1/suppliers/{other}-keine-angabe").status_code == 404
    summary = client.get("/v1/suppliers/summary").json()
    assert summary["suppliers"] == 4 and summary["awards"] == 4
    assert clean_suppliers.run(conn, write=True)["excluded_new"] == 0                    # idempotent


# ============================================================== N5/N7: the k rule on the list, and the cap

def test_a_country_or_product_group_of_fewer_than_three_suppliers_is_not_listed(conn, env, client):
    seed_suppliers(conn, env)
    big = client.get("/v1/suppliers?country=DE").json()
    assert big["total"] == 3 and big["withheld"] is False
    small = client.get("/v1/suppliers?country=EE").json()
    assert small["items"] == [] and small["total"] == 0 and small["withheld"] is True
    nothing = client.get("/v1/suppliers?country=ZZ").json()          # a group that does not exist is just empty
    assert nothing["items"] == [] and nothing["withheld"] is False
    # the product group alone, and the two together, the same
    assert client.get("/v1/suppliers?cpv=3510&country=DE").json()["withheld"] is True      # two German suppliers
    assert client.get("/v1/suppliers?cpv=3510").json()["withheld"] is True
    assert client.get("/v1/suppliers?cpv=35&country=DE&sort=name").json()["total"] == 3
    # the sort does not get round it
    assert client.get("/v1/suppliers?country=EE&sort=awards").json()["items"] == []
    # a name search inside a large group still works; the group is judged without the name
    one = client.get("/v1/suppliers?country=DE&q=hensoldt").json()
    assert one["total"] == 1 and one["withheld"] is False
    # no filter, no group
    assert client.get("/v1/suppliers").json()["total"] == 4


def test_the_list_serves_a_bounded_number_of_positions(conn, env, client, monkeypatch):
    seed_suppliers(conn, env)
    monkeypatch.setattr(suppliers, "MAX_OFFSET", 3)
    first = client.get("/v1/suppliers?pageSize=2&page=1&sort=name").json()
    assert len(first["items"]) == 2 and first["maxOffset"] == 3 and first["total"] == 4
    second = client.get("/v1/suppliers?pageSize=2&page=2&sort=name").json()
    assert len(second["items"]) == 1                      # positions 3 only: the cap cuts the page, not just the offset
    r = client.get("/v1/suppliers?pageSize=2&page=3&sort=name")
    assert r.status_code == 422 and "first 3" in r.json()["detail"][0]["msg"]
    assert client.get("/v1/suppliers?pageSize=1&page=4").status_code == 422
    assert suppliers.MAX_OFFSET == 3
    monkeypatch.undo()
    assert suppliers.MAX_OFFSET == 500
    assert client.get("/v1/suppliers?pageSize=100&page=6").status_code == 422         # offset 500
    assert client.get("/v1/suppliers?pageSize=100&page=5").status_code == 200         # offset 400


def test_a_directory_page_past_the_cap_is_refused_not_failed(client, world):
    assert client.get("/v1/organisations?page=102&pageSize=100").status_code == 422


# ============================================================== N2: organisations that are natural persons

@pytest.fixture()
def persons(conn, world):
    """A person who took part in a project with other organisations, with an amount; a real institution."""
    world.P = org(conn, "mirabile antonio", "FR", "999000777", "MIRABILE ANTONIO")
    world.Q = org(conn, "tennant david robin", "GB", None, "TENNANT DAVID ROBIN")
    join(conn, world.p1, world.P, "participant", 679250)
    join(conn, world.p2, world.P, "participant", 1000)
    join(conn, world.p3, world.Q, "participant", method="exact_name", conf=0.9)
    conn.commit()
    return world


def test_a_natural_person_is_marked_and_leaves_the_directory_the_sitemap_and_the_partner_lists(conn, client, persons):
    networks.refresh_organisation_network(conn)
    flagged = {r["canonical_name"]: r["individual_reason"] for r in conn.execute(
        "SELECT canonical_name, individual_reason FROM organisation WHERE individual_reason IS NOT NULL").fetchall()}
    assert flagged == {"mirabile antonio": "person_name", "tennant david robin": "person_name"}
    # not listed, not counted, not in the sitemap slugs, not found by a search
    listed = names(client)
    assert "MIRABILE ANTONIO" not in listed and "TENNANT DAVID ROBIN" not in listed and "ALPHA SYSTEMS GMBH" in listed
    assert client.get("/v1/organisations?q=mirabile").json()["total"] == 0
    assert all("mirabile" not in s["slug"] for s in client.get("/v1/organisations/slugs").json())
    # the profile of a person is gone (410), in every tab
    for suffix in ("", "/funding", "/partners", "/projects"):
        r = client.get(f"/v1/organisations/{persons.P}-mirabile-antonio{suffix}")
        assert r.status_code == 410 and r.json()["detail"] == "not published", suffix
    # inside someone else's partner list and project page the name is not shown
    partners = client.get(f"/v1/organisations/{persons.A}-alpha/partners?pageSize=50").json()
    assert "MIRABILE ANTONIO" not in str(partners)
    members = client.get(f"/v1/projects/{persons.p1}-alpha").json()["members"]
    named = [m["organisation"]["name"] for m in members]
    assert "MIRABILE ANTONIO" not in named and "Name not shown" in named
    assert next(m for m in members if m["organisation"]["name"] == "Name not shown")["organisation"]["slug"] is None
    assert "679250" not in str([m for m in members if m["organisation"]["name"] == "Name not shown"])
    # the totals of the person's neighbours do not change: A's own projects are still its own
    assert client.get(f"/v1/organisations/{persons.A}-alpha").json()["counts"]["projects"] == 4
    # nothing was deleted
    assert conn.execute("SELECT count(*) AS n FROM participation WHERE organisation_id = %s", (persons.P,)).fetchone()["n"] == 2
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE id = %s", (persons.P,)).fetchone()["n"] == 1


def test_a_natural_person_is_not_suggested_as_a_partner_for_a_call(conn, client):
    """The call page's partner suggestions (partners.py) read the participations, not the directory table."""
    from .test_wp32 import call, partners
    from .test_wp32 import join as join32
    from .test_wp32 import org as org32
    from .test_wp32 import project as project32

    p = project32(conn, "p1", category="SPACE", year=2024, topic="EDF-2024-DA-SPACE-X")
    ids = {n: org32(conn, n, c) for n, c in (("Alpha SA", "FR"), ("Bravo GmbH", "DE"), ("Charlie SL", "ES"),
                                              ("Delta SA", "ES"), ("Echo AB", "SE"), ("MIRABILE ANTONIO", "FR"))}
    for oid in ids.values():
        join32(conn, p, oid)
    conn.commit()
    _, slug = call(conn, "edf1", "EDF-2026-DA-SPACE-PRS-STEP")
    assert "MIRABILE ANTONIO" in [x["name"] for x in partners(client, slug)["partners"]]       # before the mark
    individuals.mark_individuals(conn)
    conn.commit()
    stats.reset_cache()
    got = [x["name"] for x in partners(client, slug)["partners"]]
    assert "MIRABILE ANTONIO" not in got and "Alpha SA" in got


def test_the_resolve_lookup_does_not_confirm_a_person(conn, client, persons):
    conn.execute("""INSERT INTO organisation_alias (organisation_id, raw_name, normalised_name, country_hint, match_method, confidence)
                    VALUES (%s, 'MIRABILE ANTONIO', 'mirabile antonio', 'FR', 'pic', 1.0)""", (persons.P,))
    conn.execute("""INSERT INTO organisation_alias (organisation_id, raw_name, normalised_name, country_hint, match_method, confidence)
                    VALUES (%s, 'ALPHA SYSTEMS GMBH', 'alpha systems', 'DE', 'pic', 1.0)""", (persons.A,))
    conn.commit()
    networks.refresh_organisation_network(conn)
    assert client.get("/v1/organisations/resolve", params={"name": "Mirabile Antonio", "country": "FR"}).json()["match"] is None
    assert client.get("/v1/organisations/resolve", params={"name": "Alpha Systems GmbH", "country": "DE"}).json()["match"]


def test_the_analytics_do_not_name_a_person_either(conn, client, persons):
    conn.execute("UPDATE organisation SET canonical_name = 'ivan petrov', display_name = 'IVAN PETROV', country = 'UA' WHERE id = %s",
                 (persons.Q,))
    conn.commit()
    networks.refresh_organisation_network(conn)
    stats.reset_cache()
    body = client.get("/v1/analytics/ukraine-partners?since=2000").json()
    assert "IVAN PETROV" not in str(body) and "Name not shown" not in str(body["ukrainianOrganisations"])


def test_marking_is_idempotent_symmetric_and_a_dry_run_writes_nothing(conn, persons, monkeypatch):
    assert individuals.mark_individuals(conn, write=False)["individuals"] == 2
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE individual_reason IS NOT NULL").fetchone()["n"] == 0
    first = individuals.mark_individuals(conn)
    conn.commit()
    again = individuals.mark_individuals(conn)
    assert first["individuals"] == again["individuals"] == 2 and first["changed"] == 2 and again["changed"] == 0
    # a corrected rule takes the mark back
    monkeypatch.setattr(individuals, "individual_reason", lambda name, country=None: None)
    cleared = individuals.mark_individuals(conn)
    assert cleared["changed"] == 2 and cleared["individuals"] == 0
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE individual_reason IS NOT NULL").fetchone()["n"] == 0


def test_the_command_marks_and_rebuilds(conn, client, persons, capsys):
    networks.refresh_organisation_network(conn)
    conn.execute("UPDATE organisation SET individual_reason = NULL")
    conn.commit()
    assert mark_individuals.main([]) == 0
    assert "dry run" in capsys.readouterr().out
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE individual_reason IS NOT NULL").fetchone()["n"] == 0
    assert "MIRABILE ANTONIO" not in names(client)       # the refresh above had already left the rows out of the table
    assert mark_individuals.main(["--yes"]) == 0
    out = capsys.readouterr().out
    assert "marked and rebuilt" in out and "natural persons: 2" in out


def test_a_supplier_that_is_also_a_person_in_the_directory_is_not_listed_as_a_supplier(conn, env, client):
    seed_suppliers(conn, env)
    conn.execute("UPDATE organisation SET individual_reason = 'person_name' WHERE canonical_name LIKE 'hensoldt%'")
    conn.commit()
    assert "Hensoldt Sensors GmbH" not in [i["name"] for i in client.get("/v1/suppliers?pageSize=100").json()["items"]]
    hens = conn.execute("SELECT id FROM organisation WHERE canonical_name LIKE 'hensoldt%'").fetchone()["id"]
    assert client.get(f"/v1/suppliers/{hens}-hensoldt").status_code == 410


# ============================================================== N3: a suppression reaches what was derived

def _suppress_org(conn, oid: int) -> int:
    entry = suppress.add(conn, kind="organisation", source=None, native_id=None, organisation=oid,
                         reason="personal_data", requested_at=NOW, decided_by="Owner", note="")
    conn.commit()
    return entry


def test_a_suppressed_organisation_leaves_the_directory_table_at_once(conn, client, world):
    assert "ALPHA SYSTEMS GMBH" in names(client) and "DELTA SP. Z O.O." in names(client)
    n_before = client.get("/v1/organisations").json()["total"]
    _suppress_org(conn, world.D)
    # no refresh has run: the entry itself cleared the derived table
    assert conn.execute("SELECT count(*) AS n FROM organisation_network WHERE organisation_id = %s", (world.D,)).fetchone()["n"] == 0
    listed = names(client)
    assert "DELTA SP. Z O.O." not in listed and client.get("/v1/organisations").json()["total"] == n_before - 1
    assert client.get("/v1/organisations?q=delta").json()["total"] == 0
    assert all(f"{world.D}-" not in s["slug"] for s in client.get("/v1/organisations/slugs").json())
    assert client.get(f"/v1/organisations/{world.D}-delta").status_code == 410
    # partner lists, which now read the same table, do not show it either
    assert "DELTA SP. Z O.O." not in str(client.get(f"/v1/organisations/{world.A}-alpha/partners?pageSize=50").json())


def test_the_whole_merge_family_leaves_and_a_lift_brings_the_organisation_back(conn, client, world, capsys):
    # B2 was merged into B; a takedown aimed at the duplicate must reach the live row's figures too
    entry = _suppress_org(conn, world.B2)
    assert conn.execute("SELECT count(*) AS n FROM organisation_network WHERE organisation_id = %s", (world.B,)).fetchone()["n"] == 0
    assert "BRAVO INGÉNIERIE SAS" not in names(client)
    assert suppress.lift(conn, entry, by="Owner")
    conn.commit()
    assert "directory rebuilt" in suppress.rebuild_directory(conn)
    assert "BRAVO INGÉNIERIE SAS" in names(client)


def test_a_flag_set_by_hand_clears_the_directory_too(conn, client, world):
    conn.execute("UPDATE organisation SET suppressed = true WHERE id = %s", (world.E,))
    conn.commit()
    assert "ECHO IBERICA SL" not in names(client)


def test_nothing_else_derived_survives_an_organisation_entry(conn, client, world):
    conn.execute("INSERT INTO list_snapshot (key, body) VALUES ('x', '{}'), ('y', '{}')")
    conn.commit()
    dropped = suppress.drop_derived(conn)
    assert dropped == {"digest_issue": 0, "list_snapshot": 2}


# ============================================================== N4: the cold paths

def test_the_partner_tab_reads_the_narrow_directory_table_and_the_active_indexes_exist(conn, client, world):
    rows = conn.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'participation'").fetchall()
    have = {r["indexname"] for r in rows}
    assert {"participation_active_project", "participation_active_org"} <= have
    items = client.get(f"/v1/organisations/{world.A}-alpha/partners?pageSize=50").json()["items"]
    got = {i["organisation"]["name"] for i in items}
    assert {"BRAVO INGÉNIERIE SAS", "KYIV INSTITUTE", "ECHO IBERICA SL"} <= got
    # an organisation that left the directory table is not a partner (the table is the list of who is shown)
    conn.execute("DELETE FROM organisation_network WHERE organisation_id = %s", (world.C,))
    conn.commit()
    assert "KYIV INSTITUTE" not in str(client.get(f"/v1/organisations/{world.A}-alpha/partners?pageSize=50").json())


def test_the_change_window_is_computed_once_for_every_page_and_page_size(conn, client, monkeypatch):
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "60")
    config.reset_cache()
    stats.reset_cache()
    calls = []
    real = changes.build_events

    def counted(*a, **kw):
        calls.append(kw.get("countries"))
        return real(*a, **kw)

    monkeypatch.setattr(changes, "build_events", counted)
    assert client.get("/v1/changes?pageSize=100").status_code == 200       # the Atom feed
    assert client.get("/v1/changes?pageSize=50").status_code == 200        # the page
    assert client.get("/v1/changes?pageSize=50&page=2").status_code == 200
    assert len(calls) == 1
    assert client.get("/v1/changes?pageSize=50&country=PL").status_code == 200
    assert len(calls) == 2                                                  # another window is its own entry
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "0")
    config.reset_cache()
    stats.reset_cache()
