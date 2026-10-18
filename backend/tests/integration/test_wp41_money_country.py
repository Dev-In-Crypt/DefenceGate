"""WP-41, N1 to N4 and N12 against a real Postgres: what the loader writes for an amount, the repair path
that re-derives it for rows already stored, and the country and name of an organisation CORDIS records
contradictorily."""

from __future__ import annotations

import pytest

from dgate import config, networks
from dgate.ops import repair_contributions
from dgate.sources import cordis
from tests.fakecordis import FakeCordis

pytestmark = pytest.mark.integration


@pytest.fixture
def env(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("DGATE_FLOOR_CORDIS", "1")
    config.reset_cache()
    for kind in cordis.PAGE_SIZE:
        monkeypatch.setitem(cordis.PAGE_SIZE, kind, 3)
    conn.execute("UPDATE source SET active = FALSE WHERE code = 'cordis'")
    conn.commit()
    yield tmp_path
    conn.execute("UPDATE source SET active = FALSE WHERE code = 'cordis'")
    conn.commit()
    config.reset_cache()


def _org(key, pic, name, country, **kw):
    return {"key": key, "pic": pic, "rcn": key, "name": name, "vat": kw.pop("vat", ""), "country": country, **kw}


def _project(key, rcn, fund, **kw):
    return {"key": key, "rcn": rcn, "ga": kw.get("ga", "101000" + rcn[-3:]), "title": "Project " + rcn, "acronym": "P" + rcn,
            "start": "2022-01-01", "end": "2024-12-31", "duration": "36", "status": "SIGNED", "cost": str(fund),
            "fund": str(fund), "call": "HORIZON-CL4-2021-X", "topic": "HORIZON_HORIZON-CL4-2021-X-01"}


def _role(key, project, org, role, amount=None):
    row = {"key": key, "project": project, "org": org, "role": role}
    if amount is not None:
        row["amount"] = str(amount)
    return row


def dataset():
    orgs = [_org("o1", "111111111", "ALPHA UNIVERSITE", "FR"), _org("o2", "222222222", "BETA INSTITUT", "FR"),
            _org("o3", "333333333", "GAMMA SPA", "IT"), _org("o4", "444444444", "DELTA GMBH", "DE")]
    projects = [_project("p1", "2001", 2810229),      # host with a linked third party, as ERC 695618
                _project("p2", "2002", 1498800),      # two hosts each paid the whole grant, as FP7 109646
                _project("p3", "2003", 500000),       # an ordinary project, one participant without a payment
                ]
    roles = [
        _role("r1", "2001", "o1", "coordinator", 2810229), _role("r2", "2001", "o2", "thirdParty", 0),
        _role("r3", "2002", "o1", "coordinator", 1498800), _role("r4", "2002", "o3", "coordinator", 1498800),
        _role("r5", "2003", "o3", "coordinator", 300000), _role("r6", "2003", "o4", "participant", 200000),
        _role("r7", "2003", "o1", "participant"),        # no payment in the service
        _role("r8", "2003", "o2", "associatedPartner", 0),
    ]
    return orgs, projects, roles


def _run(fake, **kw):
    return networks.run_cordis(sparql=fake.sparql(), **kw)


def _rows(conn):
    return {(r["cordis_id"], r["pic"]): (None if r["contribution"] is None else float(r["contribution"]),
                                         r["contribution_note"],
                                         None if r["contribution_stated"] is None else float(r["contribution_stated"]))
            for r in conn.execute(
                """SELECT p.cordis_id, o.eu_pic AS pic, pa.contribution, pa.contribution_note, pa.contribution_stated
                     FROM participation pa JOIN project p ON p.id = pa.project_id
                     JOIN organisation o ON o.id = pa.organisation_id""").fetchall()}


def test_the_loader_writes_unknown_as_null_with_a_note_and_withholds_an_excess(conn, env):
    orgs, projects, roles = dataset()
    c = _run(FakeCordis(orgs, projects, roles))
    got = _rows(conn)
    # the host is paid the whole grant, gross of the third party it is linked to
    assert got[("2001", "111111111")] == (2810229.0, "gross_of_third_parties", None)
    assert got[("2001", "222222222")] == (None, "linked_third_party", None)        # was 0 before WP-41
    # two coordinators each carrying the full grant: neither is believed, the stated figure is kept
    assert got[("2002", "111111111")] == (None, "exceeds_project_total", 1498800.0)
    assert got[("2002", "333333333")] == (None, "exceeds_project_total", 1498800.0)
    # an ordinary project is untouched; a missing payment says so; a stated 0 stays 0
    assert got[("2003", "333333333")] == (300000.0, None, None)
    assert got[("2003", "444444444")] == (200000.0, None, None)
    assert got[("2003", "111111111")] == (None, "no_payment_stated", None)
    assert got[("2003", "222222222")] == (0.0, None, None)
    assert c["projects_amounts_withheld"] == 1


def test_a_second_run_changes_nothing(conn, env):
    orgs, projects, roles = dataset()
    _run(FakeCordis(orgs, projects, roles))
    before = _rows(conn)
    c = _run(FakeCordis(orgs, projects, roles))
    assert c["new"] == 0 and c["changed"] == 0 and _rows(conn) == before


def test_the_repair_gives_rows_of_the_first_version_exactly_what_the_loader_writes(conn, env):
    orgs, projects, roles = dataset()
    _run(FakeCordis(orgs, projects, roles))
    expected = _rows(conn)
    # put the rows back as the first version stored them: third parties at 0, no notes, amounts kept
    conn.execute("UPDATE participation SET contribution = COALESCE(contribution_stated, contribution), "
                 "contribution_note = NULL, contribution_stated = NULL")
    conn.execute("UPDATE participation SET contribution = 0 WHERE role = 'third_party'")
    conn.commit()
    assert _rows(conn) != expected

    dry = repair_contributions.run(conn, apply=False, out=lambda *_: None)
    assert dry["changed"] > 0
    conn.rollback()
    assert _rows(conn) != expected                         # a dry run writes nothing

    done = repair_contributions.run(conn, apply=True, out=lambda *_: None)
    assert done["projects_withheld"] == 1 and done["to_linked_third_party"] == 1
    assert _rows(conn) == expected
    again = repair_contributions.run(conn, apply=True, out=lambda *_: None)
    assert again["changed"] == 0                           # idempotent


def test_the_repair_gives_the_amounts_back_when_the_project_total_is_corrected(conn, env):
    orgs, projects, roles = dataset()
    _run(FakeCordis(orgs, projects, roles))
    conn.execute("UPDATE project SET eu_contribution = 3000000 WHERE cordis_id = '2002'")
    conn.commit()
    repair_contributions.run(conn, apply=True, out=lambda *_: None)
    got = _rows(conn)
    assert got[("2002", "111111111")] == (1498800.0, None, None)
    assert got[("2002", "333333333")] == (1498800.0, None, None)


def test_the_repair_marks_edf_rows_without_an_amount_and_deletes_nothing(conn, env):
    orgs, projects, roles = dataset()
    _run(FakeCordis(orgs, projects, roles))
    edf_src = conn.execute("SELECT id FROM source WHERE code = 'edf_factsheets'").fetchone()["id"]
    pid = conn.execute("INSERT INTO project (source_id, native_id, title) VALUES (%s, '2024:x', 'X') RETURNING id", (edf_src,)).fetchone()["id"]
    org = conn.execute("SELECT id FROM organisation LIMIT 1").fetchone()["id"]
    conn.execute("INSERT INTO participation (project_id, organisation_id, role, resolution_method, resolution_confidence) "
                 "VALUES (%s, %s, 'participant', 'exact_name', 0.9)", (pid, org))
    conn.commit()
    n = conn.execute("SELECT count(*) AS n FROM participation").fetchone()["n"]
    done = repair_contributions.run(conn, apply=True, out=lambda *_: None)
    assert done["to_source_states_none"] == 1
    assert conn.execute("SELECT count(*) AS n FROM participation").fetchone()["n"] == n
    assert conn.execute("SELECT contribution_note FROM participation WHERE project_id = %s", (pid,)).fetchone()["contribution_note"] == "source_states_none"
    assert repair_contributions.run(conn, apply=True, out=lambda *_: None)["to_source_states_none"] == 0


def test_the_note_is_a_closed_list(conn, env):
    orgs, projects, roles = dataset()
    _run(FakeCordis(orgs, projects, roles))
    with pytest.raises(Exception, match="contribution_note_check"):
        conn.execute("UPDATE participation SET contribution_note = 'because' WHERE id = (SELECT min(id) FROM participation)")
    conn.rollback()


# ----------------------------------------------------------------- N4, the country

def csic_orgs():
    return [_org("o1", "999991722", "AGENCIA ESTATAL CONSEJO SUPERIOR DE INVESTIGACIONES CIENTIFICAS", "IT",
                 vat="ESQ2818002D", countries="IT", site_names="AGENCIA ESTATAL CONSEJO SUPERIOR DE INVESTIGACIONES CIENTIFICAS Madrid ES",
                 vats="ESQ2818002D")]


def test_a_new_organisation_gets_the_country_its_records_agree_on(conn, env):
    projects = [_project("p1", "2001", 100)]
    roles = [_role("r1", "2001", "o1", "coordinator", 100)]
    _run(FakeCordis(csic_orgs(), projects, roles))
    row = conn.execute("SELECT country, country_basis, country_sites FROM organisation WHERE eu_pic = '999991722'").fetchone()
    assert row["country"] == "ES" and row["country_basis"] == "vote" and sorted(row["country_sites"]) == ["ES", "IT"]


def test_an_organisation_stored_with_the_address_country_is_moved_with_its_aliases(conn, env):
    # as production stood on 17 October: CSIC under Italy, its alias hinted IT, a Spanish twin without a PIC
    key = "agencia estatal consejo superior de investigaciones cientificas"
    org = conn.execute("INSERT INTO organisation (canonical_name, display_name, country, eu_pic, pic_method) "
                       "VALUES (%s, 'CSIC', 'IT', '999991722', 'source') RETURNING id", (key,)).fetchone()["id"]
    conn.execute("INSERT INTO organisation_alias (organisation_id, raw_name, normalised_name, country_hint, match_method, confidence) "
                 "VALUES (%s, 'CSIC', %s, 'IT', 'pic', 1.0)", (org, key))
    conn.commit()
    projects = [_project("p1", "2001", 100)]
    roles = [_role("r1", "2001", "o1", "coordinator", 100)]
    c = _run(FakeCordis(csic_orgs(), projects, roles))
    assert c["countries_changed"] == 1
    row = conn.execute("SELECT country, country_basis FROM organisation WHERE id = %s", (org,)).fetchone()
    assert row["country"] == "ES" and row["country_basis"] == "vote"
    assert conn.execute("SELECT country_hint FROM organisation_alias WHERE organisation_id = %s AND normalised_name = %s",
                        (org, key)).fetchone()["country_hint"] == "ES"
    again = _run(FakeCordis(csic_orgs(), projects, roles))
    assert again["countries_changed"] == 0 and again["new"] == 0         # idempotent


def test_a_plain_record_never_changes_the_country_of_an_organisation_held_by_the_buyer_side(conn, env):
    org = conn.execute("INSERT INTO organisation (canonical_name, country) VALUES ('alpha universite', 'BE') "
                       "RETURNING id").fetchone()["id"]
    conn.commit()
    projects = [_project("p1", "2001", 100)]
    roles = [_role("r1", "2001", "o1", "coordinator", 100)]
    # the record agrees with the stored country: it stays, and the basis says what it rests on (WP-43)
    _run(FakeCordis([_org("o1", "111111111", "ALPHA UNIVERSITE", "BE")], projects, roles))
    assert conn.execute("SELECT country, country_basis FROM organisation WHERE id = %s", (org,)).fetchone() == {
        "country": "BE", "country_basis": "address"}


def test_an_undisputed_address_that_differs_from_a_country_without_a_basis_changes_nothing(conn, env):
    org = conn.execute("INSERT INTO organisation (canonical_name, country, eu_pic, pic_method) "
                       "VALUES ('alpha universite', 'BE', '111111111', 'source') "
                       "RETURNING id").fetchone()["id"]
    conn.commit()
    projects = [_project("p1", "2001", 100)]
    roles = [_role("r1", "2001", "o1", "coordinator", 100)]
    c = _run(FakeCordis([_org("o1", "111111111", "ALPHA UNIVERSITE", "FR")], projects, roles))
    assert c["address_differs_kept"] == 1 and c["countries_changed"] == 0
    assert conn.execute("SELECT country, country_basis FROM organisation WHERE id = %s", (org,)).fetchone() == {
        "country": "BE", "country_basis": None}


def test_sites_in_several_countries_are_recorded_and_counted(conn, env):
    orgs = [_org("o1", "998669806", "FUNDACAO EUROCEAN", "NL", countries="PT|NL",
                 site_names="FUNDACAO EUROCEAN Lisboa PT|STICHTING EUROCEAN HAGUE NL", vats="PT980405599|NL818784337B01")]
    projects = [_project("p1", "2001", 100)]
    roles = [_role("r1", "2001", "o1", "coordinator", 100)]
    _run(FakeCordis(orgs, projects, roles))
    row = conn.execute("SELECT country, country_basis, country_sites FROM organisation WHERE eu_pic = '998669806'").fetchone()
    assert row["country_basis"] == "several" and sorted(row["country_sites"]) == ["NL", "PT"] and row["country"] == "NL"


def test_the_targeted_repair_reads_only_the_organisations_and_a_dry_run_writes_nothing(conn, env):
    key = "agencia estatal consejo superior de investigaciones cientificas"
    org = conn.execute("INSERT INTO organisation (canonical_name, display_name, country, eu_pic) "
                       "VALUES (%s, 'CSIC', 'IT', '999991722') RETURNING id", (key,)).fetchone()["id"]
    conn.commit()
    fake = FakeCordis(csic_orgs(), [], [])
    dry = networks.run_cordis_countries(apply=False, sparql=fake.sparql())
    assert dry["organisations_country_by_vote"] == 1 and dry["countries_changed"] == 1
    assert conn.execute("SELECT country FROM organisation WHERE id = %s", (org,)).fetchone()["country"] == "IT"
    assert all("OrganisationRole" not in q and "e:Project ." not in q for q in fake.requests)
    assert conn.execute("SELECT count(*) AS n FROM raw_ingest").fetchone()["n"] == 0        # nothing landed either
    done = networks.run_cordis_countries(apply=True, sparql=FakeCordis(csic_orgs(), [], []).sparql())
    assert done["countries_changed"] == 1
    assert conn.execute("SELECT country FROM organisation WHERE id = %s", (org,)).fetchone()["country"] == "ES"
    assert conn.execute("SELECT count(*) AS n FROM raw_ingest").fetchone()["n"] >= 1          # landed first
    again = networks.run_cordis_countries(apply=True, sparql=FakeCordis(csic_orgs(), [], []).sparql())
    assert again["countries_changed"] == 0


# ----------------------------------------------------------------- N12, the current name

def test_the_display_name_follows_the_name_cordis_prints_now_and_the_old_one_stays_an_alias(conn, env):
    projects = [_project("p1", "2001", 100)]
    roles = [_role("r1", "2001", "o1", "coordinator", 100)]
    _run(FakeCordis([_org("o1", "422890000", "SANSIRRO GMBH", "DE")], projects, roles))
    org = conn.execute("SELECT id, display_name FROM organisation WHERE eu_pic = '422890000'").fetchone()
    assert org["display_name"] == "SANSIRRO GMBH"
    c = _run(FakeCordis([_org("o1", "422890000", "QUS TECH GMBH", "DE")], projects, roles))
    assert c["names_refreshed"] == 1 and c["organisations_new"] == 0
    assert conn.execute("SELECT display_name FROM organisation WHERE id = %s", (org["id"],)).fetchone()["display_name"] == "QUS TECH GMBH"
    aliases = {r["normalised_name"] for r in conn.execute(
        "SELECT normalised_name FROM organisation_alias WHERE organisation_id = %s", (org["id"],)).fetchall()}
    assert {"sansirro", "qus tech"} <= aliases
    again = _run(FakeCordis([_org("o1", "422890000", "QUS TECH GMBH", "DE")], projects, roles))
    assert again["names_refreshed"] == 0


def test_a_respelling_is_not_a_new_name(conn, env):
    projects = [_project("p1", "2001", 100)]
    roles = [_role("r1", "2001", "o1", "coordinator", 100)]
    _run(FakeCordis([_org("o1", "422891000", "Fundación Robotiker S.A.", "ES")], projects, roles))
    c = _run(FakeCordis([_org("o1", "422891000", "FUNDACION ROBOTIKER SA", "ES")], projects, roles))
    assert c["names_refreshed"] == 0
    assert conn.execute("SELECT display_name FROM organisation WHERE eu_pic = '422891000'").fetchone()["display_name"] == "Fundación Robotiker S.A."
