"""WP-41, N5 / N6 / N9 / N11 against a real Postgres: the deterministic merge, the name families in the
directory and on the profile, the legal-form guard, the EDF recovery, and the gaps route's topic form."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from dgate import api, db, networks, stats
from dgate.ops import edf_recover, org_dedupe, org_families, split_legal_forms
from dgate.rawstore import FileRawStore
from dgate.resolution import resolve
from dgate.sources import edf_factsheets as edf
from tests.integration.test_network_api import join, org, project
from tests.integration.test_supplier_map import put_notice
from tests.unit.test_wp41_edf import ARCHER_LAYOUT, ARCHER_PLAIN

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _projects(conn, n, prefix="p", programme="H2020"):
    return [project(conn, f"{prefix}{i}", programme, f"Project {prefix}{i}", year=2020) for i in range(n)]


def _directory(conn):
    return {r["organisation_id"]: r for r in conn.execute("SELECT * FROM organisation_network").fetchall()}


def _review(conn, a, b, method="trigram", conf=0.9):
    lo, hi = sorted((a, b))
    conn.execute("INSERT INTO resolution_review (org_a, org_b, proposed_relation, method, confidence) VALUES (%s, %s, 'same', %s, %s)",
                 (lo, hi, method, conf))


# ----------------------------------------------------------------- N5: the merge

def test_rows_with_one_key_are_merged_into_the_row_with_the_pic_and_the_directory_counts_them_once(conn):
    ps = _projects(conn, 3)
    head = org(conn, "fraunhofer gesellschaft zur forderung der angewandten forschung", "DE", "999000001",
               "FRAUNHOFER GESELLSCHAFT ZUR FORDERUNG DER ANGEWANDTEN FORSCHUNG EV")
    twin = org(conn, "fraunhofer-gesellschaft zur forderung der angewandten forschung e v", "DE", None, "fraunhofer-gesellschaft zur forderung der angewandten forschung e v")
    join(conn, ps[0], head, "coordinator", 100)
    join(conn, ps[1], head, "participant", 50)
    join(conn, ps[1], twin, "participant", 7)           # a second row of the same body in the same project
    join(conn, ps[2], twin, "participant", 30)
    conn.execute("INSERT INTO organisation_alias (organisation_id, raw_name, normalised_name, country_hint, match_method, confidence) "
                 "VALUES (%s, 'Fraunhofer-Gesellschaft e.V.', 'fraunhofer-gesellschaft e v', 'DE', 'exact_name', 0.95)", (twin,))
    _review(conn, head, twin)
    conn.commit()
    networks.refresh_organisation_network(conn)
    assert len(_directory(conn)) == 2

    dry = org_dedupe.run(conn, apply=False, out=lambda *_: None)
    assert dry["groups"] == 1 and dry["merged"] == 0
    assert conn.execute("SELECT merged_into FROM organisation WHERE id = %s", (twin,)).fetchone()["merged_into"] is None

    done = org_dedupe.run(conn, apply=True, out=lambda *_: None)
    assert done["merged"] == 1
    row = conn.execute("SELECT merged_into, merge_method, merge_confidence FROM organisation WHERE id = %s", (twin,)).fetchone()
    assert row["merged_into"] == head and row["merge_method"] == "name_key" and float(row["merge_confidence"]) == 0.95
    assert conn.execute("SELECT organisation_id, prev_organisation_id FROM organisation_alias WHERE raw_name LIKE 'Fraunhofer-G%'"
                        ).fetchone() == {"organisation_id": head, "prev_organisation_id": twin}     # reversible: the alias remembers
    assert conn.execute("SELECT status FROM resolution_review").fetchone()["status"] == "merged"
    d = _directory(conn)
    assert list(d) == [head] and d[head]["projects"] == 3 and float(d[head]["eu_contribution"]) == 187.0
    assert conn.execute("SELECT count(*) AS n FROM participation WHERE organisation_id = %s", (twin,)).fetchone()["n"] == 2   # nothing re-pointed or deleted

    again = org_dedupe.run(conn, apply=True, out=lambda *_: None)
    assert again["groups"] == 0 and again["merged"] == 0                                       # idempotent


def test_a_spacing_only_difference_is_merged_with_the_lower_confidence(conn):
    ps = _projects(conn, 2)
    a = org(conn, "universite du luxembourg", "LU", "999000002", "UNIVERSITE DU LUXEMBOURG")
    b = org(conn, "universiteduluxembourg", "LU", None, "UNIVERSITEDULUXEMBOURG")
    join(conn, ps[0], a)
    join(conn, ps[1], b, method="exact_name", conf=0.9)
    conn.commit()
    org_dedupe.run(conn, apply=True, out=lambda *_: None)
    row = conn.execute("SELECT merged_into, merge_method, merge_confidence FROM organisation WHERE id = %s", (b,)).fetchone()
    assert row["merged_into"] == a and row["merge_method"] == "name_key_spaces" and float(row["merge_confidence"]) == 0.90


def test_two_pics_two_numbers_two_legal_forms_and_buyer_only_groups_are_left_alone(conn):
    ps = _projects(conn, 4)
    a1 = org(conn, "aalborg universitet", "DK", "999000003", "AALBORG UNIVERSITET")
    a2 = org(conn, "aalborg universitet", "DK", "999000004", "Aalborg Universitet")
    r1 = org(conn, "mairie de lyon", "FR", None, "MAIRIE DE LYON")
    r2 = org(conn, "mairie de lyon", "FR", None, "Mairie de Lyon")
    conn.execute("UPDATE organisation SET national_reg_no = '21690123100011' WHERE id = %s", (r1,))
    conn.execute("UPDATE organisation SET national_reg_no = '21690123100029' WHERE id = %s", (r2,))
    k1 = org(conn, "renk", "DE", None, "Renk Aktiengesellschaft")
    k2 = org(conn, "renk", "DE", None, "RENK GmbH")
    org(conn, "stadt xyz", "DE", None, "STADT XYZ")          # two buyer rows, no project
    org(conn, "stadt xyz", "DE", None, "Stadt Xyz")
    for i, o in enumerate((a1, a2, r1, r2, k1, k2)):
        join(conn, ps[i % 4], o)
    conn.commit()
    done = org_dedupe.run(conn, apply=True, out=lambda *_: None)
    assert done["groups"] == 0 and done["merged"] == 0
    assert done["left_different_pics"] == 1 and done["left_different_registration_numbers"] == 1 and done["left_different_legal_forms"] == 1
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE merged_into IS NOT NULL").fetchone()["n"] == 0


# ----------------------------------------------------------------- N5: the name families

def _fraunhofer(conn):
    ps = _projects(conn, 5)
    head = org(conn, "fraunhofer gesellschaft", "DE", "999000010", "FRAUNHOFER GESELLSCHAFT")
    v1 = org(conn, "fraunhofer gesellschaft e v muenchen", "DE", None, "Fraunhofer-Gesellschaft e.V. Muenchen")
    v2 = org(conn, "fraunhofer gesellschaft zentrale", "DE", None, "Fraunhofer Gesellschaft Zentrale")
    other = org(conn, "fraunhofer gesellschaft austria", "AT", "999000011", "Fraunhofer Gesellschaft Austria")
    for p in ps[:3]:
        join(conn, p, head, "participant", 10)
    join(conn, ps[2], v1, "participant", 5)            # the same project as the head: counted once
    join(conn, ps[3], v1, "coordinator", 20)
    join(conn, ps[4], v2, "participant", 1)
    join(conn, ps[0], other, "participant", 2)
    _review(conn, head, v1, conf=0.91)
    _review(conn, head, v2, conf=0.87)
    _review(conn, head, other, conf=0.95)              # another country: never
    conn.commit()
    return head, v1, v2, other


def test_name_variants_become_one_card_and_the_profile_counts_their_projects(conn, client):
    head, v1, v2, other = _fraunhofer(conn)
    networks.refresh_organisation_network(conn)
    assert len(_directory(conn)) == 4

    dry = org_families.run(conn, apply=False, out=lambda *_: None)
    assert dry["families"] == 1 and dry["members"] == 2 and dry["pairs_vetoed_country"] == 1
    assert conn.execute("SELECT count(*) AS n FROM organisation_family_member").fetchone()["n"] == 0     # a dry run writes nothing

    done = org_families.run(conn, apply=True, out=lambda *_: None)
    assert done["written"] == 2
    fm = {r["org_id"]: r for r in conn.execute("SELECT * FROM organisation_family_member").fetchall()}
    assert set(fm) == {v1, v2} and all(r["head_org_id"] == head for r in fm.values())
    assert (fm[v1]["method"], float(fm[v1]["confidence"])) == ("name_variant", 0.91)
    # nothing was merged or changed on the rows themselves
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE merged_into IS NOT NULL").fetchone()["n"] == 0

    d = _directory(conn)
    assert set(d) == {head, other}                     # the variants have no card of their own
    assert d[head]["projects"] == 5 and d[head]["family_variants"] == 2 and d[head]["coordinated"] == 1
    assert float(d[head]["eu_contribution"]) == 10 * 3 + 5 + 20 + 1
    assert d[other]["family_variants"] == 0

    listing = client.get("/v1/organisations?pageSize=10").json()["items"]
    card = next(i for i in listing if i["id"] == str(head))
    assert card["nameVariants"] == 2 and card["projects"] == 5

    prof = client.get(f"/v1/organisations/{card['slug']}").json()
    assert prof["counts"]["projects"] == 5 == card["projects"]                   # the profile equals the card
    assert prof["nameVariants"]["total"] == 2 and prof["variantOf"] is None
    names = [i["organisation"]["name"] for i in prof["nameVariants"]["items"]]
    assert names == ["Fraunhofer-Gesellschaft e.V. Muenchen", "Fraunhofer Gesellschaft Zentrale"]
    assert prof["mergedFrom"] == 0

    member = client.get(f"/v1/organisations/{v1}-x").json()
    assert member["variantOf"]["organisation"]["id"] == str(head) and member["counts"]["projects"] == 2
    assert member["nameVariants"] is None

    again = org_families.run(conn, apply=True, out=lambda *_: None)
    assert again["written"] == 0 and again["removed"] == 0                       # idempotent


def test_a_family_goes_when_its_pair_goes_and_an_organisation_removed_on_request_leaves_every_family(conn):
    head, v1, v2, _ = _fraunhofer(conn)
    org_families.run(conn, apply=True, out=lambda *_: None)
    conn.execute("UPDATE resolution_review SET status = 'rejected' WHERE org_b = %s OR org_a = %s", (v2, v2))
    conn.commit()
    done = org_families.run(conn, apply=True, out=lambda *_: None)
    assert done["removed"] == 1 and done["members"] == 1
    conn.execute("UPDATE organisation SET suppressed = TRUE WHERE id = %s", (v1,))
    conn.commit()
    assert conn.execute("SELECT count(*) AS n FROM organisation_family_member").fetchone()["n"] == 0     # by the trigger
    networks.refresh_organisation_network(conn)
    assert head in _directory(conn) and v1 not in _directory(conn)


def test_different_pics_legal_forms_and_countries_are_not_a_family(conn):
    ps = _projects(conn, 2)
    a = org(conn, "universite de nantes", "FR", "999000020", "UNIVERSITE DE NANTES")
    b = org(conn, "nantes universite", "FR", "999000021", "NANTES UNIVERSITE")
    c = org(conn, "rheinmetall aktiengesellschaft", "DE", None, "Rheinmetall Aktiengesellschaft")
    d = org(conn, "rheinmetall", "DE", None, "RHEINMETALL GmbH")
    for o in (a, b, c, d):
        join(conn, ps[0], o)
    _review(conn, a, b)
    _review(conn, c, d, conf=0.95)
    conn.commit()
    done = org_families.run(conn, apply=True, out=lambda *_: None)
    assert done["members"] == 0 and done["pairs_vetoed_pic"] == 1 and done["pairs_vetoed_legal_form"] == 1


def test_one_name_under_several_pics_is_a_family_of_its_own_kind(conn):
    ps = _projects(conn, 3)
    a = org(conn, "assistance publique hopitaux de paris", "FR", "999000030", "ASSISTANCE PUBLIQUE HOPITAUX DE PARIS")
    b = org(conn, "assistance publique hopitaux de paris", "FR", "999000031", "Assistance Publique - Hopitaux de Paris")
    join(conn, ps[0], a)
    join(conn, ps[1], a)
    join(conn, ps[2], b)
    _review(conn, a, b, method="exact_name_ambiguous", conf=0.8)
    conn.commit()
    done = org_families.run(conn, apply=True, out=lambda *_: None)
    assert done["members"] == 1
    r = conn.execute("SELECT * FROM organisation_family_member").fetchone()
    assert (r["org_id"], r["head_org_id"], r["method"], float(r["confidence"])) == (b, a, "same_name", 0.8)


# ----------------------------------------------------------------- N11: legal forms

def test_a_name_with_another_legal_form_is_not_the_organisation_that_has_the_first(conn):
    first = resolve(conn, "Renk Aktiengesellschaft", "DE", None, {"candidates": False})
    again = resolve(conn, "RENK AG", "DE", None, {"candidates": False})
    gmbh = resolve(conn, "RENK GmbH", "DE", None, {"candidates": False})
    assert again.org_id == first.org_id and again.method in ("alias", "exact_name")
    assert gmbh.created and gmbh.org_id != first.org_id
    review = conn.execute("SELECT method, org_a, org_b, status FROM resolution_review").fetchone()
    assert review["method"] == "legal_form_conflict" and {review["org_a"], review["org_b"]} == {first.org_id, gmbh.org_id}
    # and the GmbH is found again as the GmbH, not the AG
    assert resolve(conn, "Renk GMBH", "DE", None, {"candidates": False}).org_id == gmbh.org_id
    # a name without any form is still matched by its key, as before
    bare = resolve(conn, "Renk Test Systems", "DE", None, {"candidates": False})
    assert resolve(conn, "RENK TEST SYSTEMS GmbH", "DE", None, {"candidates": False}).org_id == bare.org_id


def _award(conn, org_id, name, ident, n):
    opp = put_notice(conn, f"n{n}")
    conn.execute(
        """INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated, identifier_as_stated,
                              winners_in_notice, resolution_method, resolution_confidence)
           VALUES (%s, %s, 'DE', %s, %s, 1, 'exact_name', 0.95)""", (opp, org_id, name, ident))


def test_a_supplier_that_holds_awards_under_two_legal_forms_is_split_unless_the_register_says_one_body(conn):
    renk = org(conn, "renk", "DE", None, "Renk Aktiengesellschaft")
    _award(conn, renk, "Renk Aktiengesellschaft", "DE811234567", 1)
    _award(conn, renk, "Renk Aktiengesellschaft", None, 2)
    _award(conn, renk, "RENK GmbH", "DE829876543", 3)
    same = org(conn, "mueller", "DE", None, "Mueller AG")
    _award(conn, same, "Mueller AG", "DE835551234", 4)
    _award(conn, same, "Mueller Aktiengesellschaft", "DE835551234", 5)           # one class
    one = org(conn, "otto", "DE", None, "Otto AG")
    _award(conn, one, "Otto AG", "DE846781234", 6)
    _award(conn, one, "Otto GmbH", "DE846781234", 7)                               # the register says: one body
    conn.commit()
    dry = split_legal_forms.run(conn, apply=False, out=lambda *_: None)
    assert dry["organisations"] == 1 and dry["awards"] == 1
    done = split_legal_forms.run(conn, apply=True, out=lambda *_: None)
    assert done["organisations_new"] == 1
    moved = conn.execute("SELECT organisation_id FROM award WHERE name_as_stated = 'RENK GmbH'").fetchone()["organisation_id"]
    assert moved != renk
    assert conn.execute("SELECT count(*) AS n FROM award WHERE organisation_id = %s", (renk,)).fetchone()["n"] == 2
    assert conn.execute("SELECT display_name FROM organisation WHERE id = %s", (moved,)).fetchone()["display_name"] == "RENK GmbH"
    assert conn.execute("SELECT method FROM resolution_review").fetchone()["method"] == "legal_form_conflict"
    assert conn.execute("SELECT count(*) AS n FROM award").fetchone()["n"] == 7                       # nothing deleted
    again = split_legal_forms.run(conn, apply=True, out=lambda *_: None)
    assert again["organisations"] == 0


# ----------------------------------------------------------------- N9: the topic form of the gaps route

def test_the_gaps_route_takes_the_call_code_as_the_programme_prints_it(conn, client):
    a, b = org(conn, "alpha", "DE", "999000040", "ALPHA"), org(conn, "beta", "FR", "999000041", "BETA")
    for i in range(2):
        pid = project(conn, f"hz{i}", "HORIZON", f"Drs {i}", topic="HORIZON_HORIZON-CL3-2023-DRS-01-01", year=2023)
        conn.execute("UPDATE project SET call_code = 'HORIZON-CL3-2023-DRS-01' WHERE id = %s", (pid,))
        join(conn, pid, a)
        join(conn, pid, b)
    conn.commit()
    for topic in ("HORIZON-CL3-2023-DRS", "HORIZON_HORIZON-CL3-2023-DRS", "horizon-cl3-2023-drs-01"):
        body = client.get("/v1/analytics/consortium-gaps", params={"programme": "HORIZON", "topic": topic, "lacking": "UA"}).json()
        assert body["projectsInArea"] == 2, topic
        assert not any("EDF factsheets" in x for x in body["limits"])               # not said about a Horizon query
    miss = client.get("/v1/analytics/consortium-gaps", params={"programme": "HORIZON", "topic": "HORIZON-CL9-1999-X"}).json()
    assert miss["projectsInArea"] == 0 and "No project of the programme matches" in miss["limits"][0]


# ----------------------------------------------------------------- N6: recovering what the quote check dropped

def test_dropped_members_come_back_from_the_stored_text_without_a_model_and_only_once(conn, tmp_path):
    src = conn.execute("SELECT id FROM source WHERE code = 'edf_factsheets'").fetchone()["id"]
    url = "https://defence-industry-space.ec.europa.eu/document/download/ac9b_en?filename=EDF-2023-LS-RA-CHALLENGE-DIGIT-HLTO_ARCHER.pdf"
    info = edf.parse_filename("EDF-2023-LS-RA-CHALLENGE-DIGIT-HLTO_ARCHER.pdf", 2023)
    text = edf.FactsheetText("a" * 64, 2, ARCHER_LAYOUT, ARCHER_PLAIN)
    facts = {"acronym": "ARCHER", "title": "ARCHER", "coordinator": None, "eu_contribution": None, "total_cost": None,
             "duration_months": None, "participants": [
                 {"name": "AIRBUS DEFENCE AND SPACE SAS", "country": "France", "country_iso": "FR", "role": "coordinator", "is_sme": None},
                 {"name": "VYSOKEUCENITECHNICKEVBRNE", "country": "Czechia", "country_iso": "CZ", "role": "participant", "is_sme": None}]}
    from collections import Counter
    pid = networks.load_edf_factsheet(conn, src, info, url, text, facts, Counter())
    conn.execute(
        """INSERT INTO project_factsheet (url, project_id, sha256, pages, facts, dropped, model, prompt_version)
           VALUES (%s, %s, %s, 2, %s, '{"not_in_text": 3, "missing_from_answer": 3}', 'm', 1)""",
        (url, pid, text.sha256, Jsonb(facts)))
    store = FileRawStore(tmp_path / "raw")
    key = store.put("edf_factsheets/2026/10/17/x.json", {"url": url, "filename": "EDF-2023-LS-RA-CHALLENGE-DIGIT-HLTO_ARCHER.pdf",
                                                         "sha256": text.sha256, "pages": 2, "layout": ARCHER_LAYOUT, "plain": ARCHER_PLAIN})
    db.record_raw(conn, src, "2023:x", "h" * 64, key)
    conn.commit()
    assert conn.execute("SELECT count(*) AS n FROM participation WHERE project_id = %s", (pid,)).fetchone()["n"] == 2

    dry = edf_recover.run(conn, store, apply=False, out=lambda *_: None)
    assert dry["participants_recovered"] == 3 and conn.execute("SELECT count(*) AS n FROM participation").fetchone()["n"] == 2
    assert dry["names_respaced"] == 1 and conn.execute(
        "SELECT count(*) AS n FROM organisation WHERE display_name = 'VYSOKEUCENITECHNICKEVBRNE'").fetchone()["n"] == 1

    done = edf_recover.run(conn, store, apply=True, out=lambda *_: None)
    assert done["participants_recovered"] == 3 and done["participations_new"] == 3
    assert done["names_respaced"] == 1
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE display_name = 'VYSOKE UCENI TECHNICKE V BRNE'").fetchone()["n"] == 1
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE display_name = 'VYSOKEUCENITECHNICKEVBRNE'").fetchone()["n"] == 0
    rows = conn.execute("""SELECT o.display_name, o.country, pa.role FROM participation pa JOIN organisation o ON o.id = pa.organisation_id
                            WHERE pa.project_id = %s AND pa.active""", (pid,)).fetchall()
    assert len(rows) == 5
    assert any(r["display_name"].startswith("ATHINA - EREVNITIKO") and r["country"] == "GR" for r in rows)
    pf = conn.execute("SELECT facts, dropped FROM project_factsheet WHERE url = %s", (url,)).fetchone()
    assert pf["dropped"]["recovered"] == 3 and sum(1 for p in pf["facts"]["participants"] if p.get("recovered")) == 3
    assert done["sheets_to_reread_with_the_model"] == 0                      # all 3 lost names came back
    again = edf_recover.run(conn, store, apply=True, out=lambda *_: None)
    assert again["participants_recovered"] == 0 and again["names_respaced"] == 0
    assert conn.execute("SELECT count(*) AS n FROM participation").fetchone()["n"] == 5


def test_edf_projects_are_filed_under_the_last_category_their_code_names(conn):
    src = conn.execute("SELECT id FROM source WHERE code = 'edf_factsheets'").fetchone()["id"]
    pid = conn.execute(
        """INSERT INTO project (source_id, native_id, title, topic_code, category)
           VALUES (%s, '2023:eatmi', 'EATMI', 'EDF-2023-DA-DS-AIRDEF-EATMI', 'DS') RETURNING id""", (src,)).fetchone()["id"]
    conn.commit()
    assert edf_recover.recategorise(conn, apply=False) == 1
    assert conn.execute("SELECT category FROM project WHERE id = %s", (pid,)).fetchone()["category"] == "DS"
    assert edf_recover.recategorise(conn, apply=True) == 1
    assert conn.execute("SELECT category FROM project WHERE id = %s", (pid,)).fetchone()["category"] == "AIRDEF"
    assert edf_recover.recategorise(conn, apply=True) == 0
