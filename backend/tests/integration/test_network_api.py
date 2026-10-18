"""Layer 2 for the user (WP-28) on a real Postgres: the directory, the profile and its tabs, the project
page and its history, the two analytics, the buyer link, merged and removed organisations, and the grants."""

from __future__ import annotations

from datetime import date
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, migrate, networks, stats
from dgate.network_api import COUNT_CAP, resolution_note
from dgate.normalise import Opportunity

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


def org(conn, name: str, country: str, pic: str | None = None, display: str | None = None) -> int:
    return conn.execute(
        """INSERT INTO organisation (canonical_name, display_name, country, eu_pic, pic_method, pic_confidence)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (name, display or name.upper(), country, pic, "source" if pic else None, 1 if pic else None)
    ).fetchone()["id"]


def project(conn, native: str, programme: str, title: str, *, source="cordis", acronym=None, year=2022,
            start=None, category=None, topic=None, ga=None, eu=None, total=None) -> int:
    return conn.execute(
        """INSERT INTO project (source_id, programme_id, native_id, cordis_id, ga_number, acronym, title,
                                topic_code, category, call_year, start_date, eu_contribution, total_cost)
           VALUES ((SELECT id FROM source WHERE code = %s), (SELECT id FROM programme WHERE code = %s),
                   %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (source, programme, native, native if source == "cordis" else None, ga, acronym or title.upper(),
         title, topic, category, year, start, eu, total)).fetchone()["id"]


def join(conn, proj: int, o: int, role="participant", eur=None, active=True, method="pic", conf=1.0) -> None:
    conn.execute(
        """INSERT INTO participation (project_id, organisation_id, role, contribution, resolution_method,
                                      resolution_confidence, active) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (proj, o, role, eur, method, conf, active))


class W:
    """The world of these tests (three CORDIS projects, three EDF projects, one merge, one removal)."""


@pytest.fixture()
def world(conn):
    w = W()
    w.A = org(conn, "alpha systems", "DE", "999000001", "ALPHA SYSTEMS GMBH")
    w.B = org(conn, "bravo ingenierie", "FR", "999000002", "BRAVO INGÉNIERIE SAS")
    w.C = org(conn, "kyiv institute", "UA", "999000003", "KYIV INSTITUTE")
    w.D = org(conn, "delta sp zoo", "PL", "999000004", "DELTA SP. Z O.O.")
    w.E = org(conn, "echo iberica", "ES", None, "ECHO IBERICA SL")
    w.F = org(conn, "foxtrot srl", "IT", None, "FOXTROT SRL")
    w.S = org(conn, "secret ab", "SE", "999000005", "SECRET AB")
    w.B2 = org(conn, "bravo old name", "FR", None, "BRAVO OLD NAME")     # merged into B below
    conn.execute("UPDATE organisation SET merged_into = %s WHERE id = %s", (w.B, w.B2))
    w.G = org(conn, "golf lonely", "NL", None, "GOLF LONELY BV")          # in no project

    w.p1 = project(conn, "1001", "H2020", "Alpha sensing", acronym="ALPHA", year=2019, start=date(2019, 5, 1),
                   ga="700001", eu=900000, total=1200000, topic="H2020-SU-SEC-2018")
    w.p2 = project(conn, "1002", "HORIZON", "Bravo networks", acronym="BRAVO", year=2023, start=date(2023, 3, 1),
                   ga="101000002", eu=500000, total=500000, topic="HORIZON-CL4-2022-SPACE")
    w.p3 = project(conn, "edf:CHARLIE", "EDF", "Charlie cyber shield", source="edf_factsheets", acronym="CHARLIE",
                   year=2024, category="CYBER", topic="EDF-2023-DA-CYBER-CSAD", total=8000000, eu=6000000)
    w.p4 = project(conn, "edf:DELTAP", "EDF", "Delta cyber range", source="edf_factsheets", acronym="DELTAP",
                   year=2023, category="CYBER", topic="EDF-2022-DA-CYBER-CSAD")
    w.p5 = project(conn, "edf:ECHOP", "EDF", "Echo ground", source="edf_factsheets", acronym="ECHOP",
                   year=2024, category="GROUND", topic="EDF-2023-RA-GROUND-X")
    w.p6 = project(conn, "edf:FOXP", "EDF", "Fox ground", source="edf_factsheets", acronym="FOXP",
                   year=2022, category="GROUND", topic="EDF-2021-RA-GROUND-X")

    join(conn, w.p1, w.A, "coordinator", 400000)
    join(conn, w.p1, w.B, "participant", 300000)
    join(conn, w.p1, w.C, "participant", 200000)
    join(conn, w.p1, w.D, "participant", None, method="exact_name", conf=0.9)
    join(conn, w.p2, w.A, "coordinator", 250000)
    join(conn, w.p2, w.B, "participant", 150000)
    join(conn, w.p2, w.S, "participant", 100000)
    join(conn, w.p2, w.D, "participant", 0, active=False)                  # left the project: history, not a member
    join(conn, w.p3, w.B, "coordinator", method="exact_name", conf=0.9)
    join(conn, w.p3, w.A, "participant", method="exact_name", conf=0.9)
    join(conn, w.p3, w.E, "participant", method="exact_name", conf=0.9)
    join(conn, w.p4, w.A, "coordinator", method="exact_name", conf=0.9)
    join(conn, w.p4, w.B, "participant", method="exact_name", conf=0.9)
    join(conn, w.p4, w.E, "participant", method="exact_name", conf=0.9)
    join(conn, w.p5, w.E, "coordinator", method="exact_name", conf=0.9)
    join(conn, w.p5, w.F, "participant", method="exact_name", conf=0.9)
    join(conn, w.p5, w.B2, "participant", method="exact_name", conf=0.8)    # a participation of the merged-away row
    join(conn, w.p6, w.F, "coordinator", method="exact_name", conf=0.9)
    join(conn, w.p6, w.E, "participant", method="exact_name", conf=0.9)
    conn.execute("""INSERT INTO project_factsheet (url, project_id, sha256, pages, facts, dropped, model,
                                                   prompt_version)
                    VALUES ('https://example.test/CHARLIE.pdf', %s, 'x', 3, '{}', '{"not_in_text": 2, "duplicate": 0}',
                            'm', 1)""", (w.p3,))
    conn.commit()
    networks.refresh_organisation_network(conn)
    return w


def slug_of(client, oid: int) -> str:
    """The slug the directory gives an organisation (the real one, as a page would link it)."""
    items = client.get("/v1/organisations?pageSize=100").json()["items"]
    return next(i["slug"] for i in items if i["id"] == str(oid))


def sql_counts(conn, ids: list[int]) -> dict[str, int]:
    r = conn.execute(
        """SELECT count(DISTINCT project_id) AS projects, count(*) AS participations,
                  count(DISTINCT project_id) FILTER (WHERE role = 'coordinator') AS coordinated
             FROM participation WHERE organisation_id = ANY(%s) AND active""", (ids,)).fetchone()
    return dict(r)


# --------------------------------------------------------------------- the directory

def test_directory_lists_live_organisations_with_the_counts_of_the_sql(conn, client, world):
    body = client.get("/v1/organisations?pageSize=100").json()
    names = {i["name"]: i for i in body["items"]}
    assert "GOLF LONELY BV" not in names                       # in no project: not in the directory
    assert "BRAVO OLD NAME" not in names                       # merged away: its live row stands for it
    a = names["ALPHA SYSTEMS GMBH"]
    assert (a["projects"], a["coordinated"]) == (4, 3)
    assert a["euContribution"] == 650000.0                     # 400000 + 250000; the EDF rows state none
    assert (a["firstYear"], a["lastYear"], a["programmes"]) == (2019, 2024, ["EDF", "H2020", "HORIZON"])
    b = names["BRAVO INGÉNIERIE SAS"]
    # the merged row's participation (P5) counts for B
    assert b["projects"] == sql_counts(conn, [world.B, world.B2])["projects"] == 5
    assert body["total"] == len(body["items"]) == 7 and body["totalExact"] is True
    order = [i["projects"] for i in body["items"]]
    assert order == sorted(order, reverse=True)                # most projects first


def test_directory_filters_country_programme_role_and_minimum(client, world):
    def names(qs: str) -> list[str]:
        return [i["name"] for i in client.get(f"/v1/organisations?{qs}").json()["items"]]

    assert names("country=UA") == ["KYIV INSTITUTE"]
    assert set(names("country=ua,pl")) == {"DELTA SP. Z O.O.", "KYIV INSTITUTE"}
    assert set(names("programme=EDF")) == {"ALPHA SYSTEMS GMBH", "BRAVO INGÉNIERIE SAS", "ECHO IBERICA SL", "FOXTROT SRL"}
    assert set(names("programme=H2020,HORIZON&country=DE")) == {"ALPHA SYSTEMS GMBH"}
    assert set(names("role=coordinator")) == {"ALPHA SYSTEMS GMBH", "BRAVO INGÉNIERIE SAS", "ECHO IBERICA SL", "FOXTROT SRL"}
    assert set(names("minProjects=4")) == {"ALPHA SYSTEMS GMBH", "BRAVO INGÉNIERIE SAS", "ECHO IBERICA SL"}
    assert names("programme=FP7") == []


def test_directory_search_folds_accents_and_matches_word_starts(client, world):
    assert [i["name"] for i in client.get("/v1/organisations?q=ingenierie").json()["items"]] == ["BRAVO INGÉNIERIE SAS"]
    assert [i["name"] for i in client.get("/v1/organisations?q=INGÉNIERIE bravo").json()["items"]] == ["BRAVO INGÉNIERIE SAS"]
    assert client.get("/v1/organisations?q=genier").json()["items"] == []     # the middle of a word is not a match
    assert client.get("/v1/organisations?q=%25").json()["items"] == []        # a LIKE character is not a wildcard


def test_directory_sorts_by_name_and_pages_with_an_exact_total(client, world):
    first = client.get("/v1/organisations?sort=name&pageSize=3").json()
    assert [i["name"] for i in first["items"]] == ["ALPHA SYSTEMS GMBH", "BRAVO INGÉNIERIE SAS", "DELTA SP. Z O.O."]
    assert (first["total"], first["totalExact"], first["page"]) == (7, True, 1)
    third = client.get("/v1/organisations?sort=name&pageSize=3&page=3").json()
    assert [i["name"] for i in third["items"]] == ["SECRET AB"] and third["total"] == 7
    assert client.get("/v1/organisations?sort=name&pageSize=3&page=9").json()["items"] == []


def test_directory_total_is_capped_and_says_so(conn, client, world, monkeypatch):
    from dgate import network_api

    monkeypatch.setattr(network_api, "COUNT_CAP", 2)
    body = client.get("/v1/organisations?pageSize=1").json()
    assert body["total"] == 2 and body["totalExact"] is False
    assert COUNT_CAP == 10_000


def test_directory_refuses_values_it_does_not_know(client, world):
    assert client.get("/v1/organisations?page=101&pageSize=100").status_code == 200     # the 10,000th result is the last served
    assert client.get("/v1/organisations?page=102&pageSize=100").status_code == 422
    for qs in ("role=boss", "programme=a%20b", "country=Germany", "sort=funding", "pageSize=101", "minProjects=0",
               "page=0", "q=" + "x" * 101):
        assert client.get(f"/v1/organisations?{qs}").status_code == 422, qs


def test_an_organisation_removed_on_request_and_one_that_left_are_not_listed(conn, client, world):
    conn.execute("UPDATE organisation SET suppressed = true WHERE id = %s", (world.S,))
    conn.commit()
    assert networks.refresh_organisation_network(conn)["removed"] == 1
    assert "SECRET AB" not in [i["name"] for i in client.get("/v1/organisations?pageSize=100").json()["items"]]
    conn.execute("UPDATE participation SET active = false WHERE organisation_id = %s", (world.C,))
    conn.commit()
    assert networks.refresh_organisation_network(conn)["removed"] == 1
    assert "KYIV INSTITUTE" not in [i["name"] for i in client.get("/v1/organisations?pageSize=100").json()["items"]]


def test_the_refresh_is_idempotent(conn, world):
    before = conn.execute("SELECT * FROM organisation_network ORDER BY organisation_id").fetchall()
    out = networks.refresh_organisation_network(conn)
    assert out == {"organisations": len(before), "removed": 0}
    after = conn.execute("SELECT * FROM organisation_network ORDER BY organisation_id").fetchall()
    assert [{k: v for k, v in r.items() if k != "refreshed_at"} for r in before] == [
        {k: v for k, v in r.items() if k != "refreshed_at"} for r in after]


# --------------------------------------------------------------------- the profile

def test_profile_counts_equal_the_sql_and_follow_the_merge(conn, client, world):
    slug = slug_of(client, world.B)
    body = client.get(f"/v1/organisations/{slug}").json()
    sql = sql_counts(conn, [world.B, world.B2])
    assert (body["counts"]["projects"], body["counts"]["participations"], body["counts"]["coordinated"]) == (
        sql["projects"], sql["participations"], sql["coordinated"])
    assert body["name"] == "BRAVO INGÉNIERIE SAS" and body["country"] == "FR"
    assert body["pic"] == {"value": "999000002", "method": "source", "confidence": 1.0}
    assert body["mergedFrom"] == 1
    # the old row's slug leads to the live organisation
    old = client.get(f"/v1/organisations/{world.B2}-bravo-old-name").json()
    assert old["id"] == str(world.B) and old["slug"] == slug
    assert {p["code"] for p in body["programmes"]} == {"EDF", "H2020", "HORIZON"}
    edf = next(p for p in body["programmes"] if p["code"] == "EDF")
    assert edf["projects"] == 3 and edf["euContribution"] is None


def test_profile_says_how_each_participation_was_recognised(client, world):
    body = client.get(f"/v1/organisations/{slug_of(client, world.A)}").json()
    assert body["resolution"]["participations"] == {"pic": 2, "exact_name": 2}
    assert "2 of 4 matched by its PIC" in body["resolution"]["note"]
    assert "2 of 4 matched by its exact normalised name" in body["resolution"]["note"]
    assert body["resolution"]["lowestConfidence"] == 0.9
    assert {s["code"] for s in body["sources"]} == {"cordis", "edf_factsheets"}
    assert all(s["licence"] for s in body["sources"])


def test_resolution_note_wording():
    assert resolution_note({}, None, None) == "No participation is held for this organisation."
    note = resolution_note({"pic": 3}, 1.0, "999000001")
    assert note.startswith("Participations: all 3 matched by its PIC") and "Lowest confidence 1.00" in note
    assert "No PIC is held" in resolution_note({"exact_name": 1}, 0.9, None)


def test_profile_of_an_organisation_with_no_project_or_unknown_is_404_and_a_removed_one_410(conn, client, world):
    assert client.get(f"/v1/organisations/{world.G}-golf-lonely").status_code == 404
    assert client.get("/v1/organisations/99999999-nothing").status_code == 404
    assert client.get("/v1/organisations/not-a-slug").status_code == 404
    assert client.get("/v1/organisations/99999999999999999999999-x").status_code == 404
    conn.execute("UPDATE organisation SET suppressed = true WHERE id = %s", (world.S,))
    conn.commit()
    for tab in ("", "/funding", "/partners", "/projects"):
        assert client.get(f"/v1/organisations/{world.S}-secret-ab{tab}").status_code == 410, tab


def test_a_merged_organisation_removed_on_request_leaves_no_trace_in_the_keeper(conn, client, world):
    conn.execute("UPDATE organisation SET suppressed = true WHERE id = %s", (world.B2,))
    conn.commit()
    networks.refresh_organisation_network(conn)
    body = client.get(f"/v1/organisations/{slug_of(client, world.B)}").json()
    assert body["counts"]["projects"] == 4                    # P5 belonged to the removed row only
    assert body["mergedFrom"] == 0


def test_a_duplicate_row_removed_on_request_does_not_resurface_through_the_row_it_was_merged_into(conn, client, world):
    conn.execute("UPDATE organisation SET suppressed = true WHERE id = %s", (world.B2,))
    conn.commit()
    networks.refresh_organisation_network(conn)
    p5 = client.get(f"/v1/projects/{world.p5}-x").json()
    assert world.B not in {int(m["organisation"]["id"]) for m in p5["members"] if m["organisation"]["id"]}
    hidden = [m for m in p5["members"] if m["organisation"]["id"] is None]
    assert len(hidden) == 1 and hidden[0]["organisation"]["name"] == "Name withheld on request"
    echo = client.get(f"/v1/organisations/{slug_of(client, world.E)}/partners").json()
    bravo = next(p for p in echo["items"] if p["organisation"]["id"] == str(world.B))
    assert bravo["shared"] == 2 and "ECHOP" not in {p["acronym"] for p in bravo["projects"]}
    directory = {i["name"]: i["projects"] for i in client.get("/v1/organisations?pageSize=100").json()["items"]}
    assert directory["BRAVO INGÉNIERIE SAS"] == 4


def test_profile_lists_aliases_with_method_and_confidence(conn, client, world):
    src = db.source_id(conn, "cordis")
    db._record_alias(conn, world.A, "Alpha Systems GmbH", "alpha systems", src, "DE", "pic", 1.0)
    db._record_alias(conn, world.A, "ALPHA SYSTEMS (contact: x@y.example)", "alpha systems x", src, "DE",
                     "exact_name", 0.9)
    conn.commit()
    al = client.get(f"/v1/organisations/{slug_of(client, world.A)}").json()["aliases"]
    assert al["total"] == 2
    got = {a["name"]: (a["method"], a["confidence"], a["source"]) for a in al["items"]}
    assert got["Alpha Systems GmbH"] == ("pic", 1.0, "cordis")
    assert not any("@" in n for n in got)                      # an address in a name is never served
    db._record_alias(conn, world.A, "Alpha Systems tel +49 30 1234 5678", "alpha systems tel", src, "DE", "exact_name", 0.9)
    conn.commit()
    al = client.get(f"/v1/organisations/{slug_of(client, world.A)}").json()["aliases"]
    assert not any("1234" in a["name"] for a in al["items"])   # nor a name that carries a telephone number


def test_the_buyer_link_goes_both_ways(conn, client, world):
    src = db.source_id(conn, "ted")
    opp = Opportunity(source_code="ted", native_id="N1", buyer_name_raw="Alpha Systems GmbH", title_original="Radios",
                      country="DE", published_at=date.today(), cpv_codes=["35400000"], status="open",
                      is_defence=True, sig_cpv=True, sig_cpv_military=True, dual_use=False, buyer_class="defence")
    opp.buyer_org_id = world.A
    db.upsert_opportunity(conn, opp, "hash-n1", src)
    conn.commit()
    profile = client.get(f"/v1/organisations/{slug_of(client, world.A)}").json()
    assert profile["buyer"]["slug"].startswith(f"{world.A}-") and profile["buyer"]["tenderCount"] == 1
    buyer = client.get(f"/v1/buyers/{profile['buyer']['slug']}").json()
    assert buyer["organisationSlug"] == profile["slug"]
    # a body that only took part in projects has no buyer page; a buyer that never took part has no profile
    assert client.get(f"/v1/organisations/{slug_of(client, world.B)}").json()["buyer"] is None
    assert db.resolve_organisation(conn, "Pure Buyer Ministry", "DE", src_id=src)
    conn.commit()
    pb = conn.execute("SELECT id FROM organisation WHERE canonical_name LIKE 'pure buyer%'").fetchone()["id"]
    opp2 = Opportunity(source_code="ted", native_id="N2", buyer_name_raw="Pure Buyer Ministry", title_original="Boots",
                       country="DE", published_at=date.today(), cpv_codes=["35400000"], status="open",
                       is_defence=True, sig_cpv=True, sig_cpv_military=True, dual_use=False, buyer_class="defence")
    opp2.buyer_org_id = pb
    db.upsert_opportunity(conn, opp2, "hash-n2", src)
    conn.commit()
    assert client.get(f"/v1/buyers/{pb}-pure-buyer-ministry").json()["organisationSlug"] is None


def test_funding_tab_is_per_programme_and_year_with_the_edf_caveat(conn, client, world):
    body = client.get(f"/v1/organisations/{slug_of(client, world.A)}/funding").json()
    rows = {(r["programme"], r["year"]): r for r in body["rows"]}
    assert rows[("H2020", 2019)]["euContribution"] == 400000.0 and rows[("H2020", 2019)]["projects"] == 1
    assert rows[("HORIZON", 2023)]["euContribution"] == 250000.0
    assert rows[("EDF", 2024)]["euContribution"] is None and rows[("EDF", 2024)]["projectsWithoutAmount"] == 1
    assert body["totals"] == {"projects": 4, "euContribution": 650000.0}
    assert "EDF" in body["amountNote"]
    assert [r["year"] for r in body["rows"]] == sorted(r["year"] for r in body["rows"])


def test_partners_are_ranked_by_shared_projects_with_the_projects_as_evidence(conn, client, world):
    body = client.get(f"/v1/organisations/{slug_of(client, world.A)}/partners").json()
    names = [(p["organisation"]["name"], p["shared"]) for p in body["items"]]
    assert names[0] == ("BRAVO INGÉNIERIE SAS", 4)             # P1, P2, P3, P4
    assert ("ECHO IBERICA SL", 2) in names and ("KYIV INSTITUTE", 1) in names
    assert "ALPHA SYSTEMS GMBH" not in [n for n, _ in names]
    assert "DELTA SP. Z O.O." in [n for n, _ in names]          # P1 only: its P2 row is inactive
    d = next(p for p in body["items"] if p["organisation"]["name"].startswith("DELTA"))
    assert d["shared"] == 1
    top = body["items"][0]
    assert [p["acronym"] for p in top["projects"]] == ["CHARLIE", "DELTAP", "BRAVO", "ALPHA"]   # newest first
    assert top["firstYear"] == 2019 and top["lastYear"] == 2024
    assert body["total"] == len(body["items"]) and body["countries"] == 5       # FR, UA, PL, ES, SE
    # the removed organisation is not a partner
    assert "SECRET AB" in [p["organisation"]["name"] for p in body["items"]]
    conn.execute("UPDATE organisation SET suppressed = true WHERE id = %s", (world.S,))
    conn.commit()
    again = client.get(f"/v1/organisations/{slug_of(client, world.A)}/partners").json()
    assert "SECRET AB" not in [p["organisation"]["name"] for p in again["items"]]


def test_partners_count_a_merged_row_under_its_live_organisation(conn, client, world):
    body = client.get(f"/v1/organisations/{slug_of(client, world.E)}/partners").json()
    bravo = next(p for p in body["items"] if p["organisation"]["id"] == str(world.B))
    assert bravo["shared"] == 3          # P3 and P4 as B itself, P5 only as the merged-away row B2
    assert {p["acronym"] for p in bravo["projects"]} == {"CHARLIE", "DELTAP", "ECHOP"}
    assert all(p["organisation"]["id"] != str(world.B2) for p in body["items"])


def test_partners_filter_by_country_and_programme(client, world):
    slug = slug_of(client, world.A)
    only_edf = client.get(f"/v1/organisations/{slug}/partners?programme=EDF").json()
    assert {p["organisation"]["name"] for p in only_edf["items"]} == {"BRAVO INGÉNIERIE SAS", "ECHO IBERICA SL"}
    assert next(p for p in only_edf["items"] if p["organisation"]["country"] == "FR")["shared"] == 2
    only_ua = client.get(f"/v1/organisations/{slug}/partners?country=UA").json()
    assert [p["organisation"]["name"] for p in only_ua["items"]] == ["KYIV INSTITUTE"]
    assert client.get(f"/v1/organisations/{slug}/partners?country=UA&programme=EDF").json()["items"] == []


def test_partners_page_through(client, world):
    slug = slug_of(client, world.A)
    one = client.get(f"/v1/organisations/{slug}/partners?pageSize=2").json()
    two = client.get(f"/v1/organisations/{slug}/partners?pageSize=2&page=2").json()
    assert len(one["items"]) == 2 and one["total"] == 5
    assert {i["organisation"]["id"] for i in one["items"]}.isdisjoint({i["organisation"]["id"] for i in two["items"]})


def test_projects_tab_gives_role_and_contribution(client, world):
    body = client.get(f"/v1/organisations/{slug_of(client, world.A)}/projects").json()
    assert body["total"] == 4
    assert [(p["acronym"], p["role"], p["contribution"]) for p in body["items"]] == [
        ("CHARLIE", "participant", None), ("DELTAP", "coordinator", None),
        ("BRAVO", "coordinator", 250000.0), ("ALPHA", "coordinator", 400000.0)]
    coord = client.get(f"/v1/organisations/{slug_of(client, world.A)}/projects?role=participant").json()
    assert [p["acronym"] for p in coord["items"]] == ["CHARLIE"]
    edf = client.get(f"/v1/organisations/{slug_of(client, world.A)}/projects?programme=EDF").json()
    assert edf["total"] == 2


# --------------------------------------------------------------------- projects

def test_project_page_lists_the_consortium_coordinator_first(conn, client, world):
    slug = f"{world.p2}-bravo"
    body = client.get(f"/v1/projects/{slug}").json()
    assert body["acronym"] == "BRAVO" and body["programme"]["code"] == "HORIZON"
    assert body["coordinator"]["name"] == "ALPHA SYSTEMS GMBH"
    roles = [(m["organisation"]["name"], m["role"], m["contribution"]) for m in body["members"]]
    assert roles[0] == ("ALPHA SYSTEMS GMBH", "coordinator", 250000.0)
    assert ("BRAVO INGÉNIERIE SAS", "participant", 150000.0) in roles
    assert body["memberCount"] == 3 and body["countryCount"] == 3    # DE, FR, SE; D left (inactive)
    assert "DELTA SP. Z O.O." not in [r[0] for r in roles]
    assert body["source"]["url"] == "https://cordis.europa.eu/project/id/101000002"
    assert body["source"]["licence"] and body["source"]["attribution"]
    assert body["factsheet"] is None
    assert body["totalCost"] == 500000.0 and body["euContribution"] == 500000.0


def test_project_page_withholds_a_removed_organisation_and_follows_a_merge(conn, client, world):
    conn.execute("UPDATE organisation SET suppressed = true WHERE id = %s", (world.S,))
    conn.commit()
    body = client.get(f"/v1/projects/{world.p2}-x").json()
    hidden = [m for m in body["members"] if m["organisation"]["id"] is None]
    assert len(hidden) == 1 and hidden[0]["organisation"]["name"] == "Name withheld on request"
    assert hidden[0]["organisation"]["country"] is None and hidden[0]["organisation"]["slug"] is None
    assert body["memberCount"] == 3 and body["countryCount"] == 2         # the removed body's country is not counted
    p5 = client.get(f"/v1/projects/{world.p5}-x").json()
    assert world.B in {int(m["organisation"]["id"]) for m in p5["members"]}
    assert world.B2 not in {int(m["organisation"]["id"]) for m in p5["members"]}


def test_an_edf_project_says_it_was_read_by_a_model_and_what_was_dropped(client, world):
    body = client.get(f"/v1/projects/{world.p3}-charlie").json()
    assert body["source"]["code"] == "edf_factsheets" and body["source"]["urlLabel"] == "EDF project factsheet"
    assert body["factsheet"]["readBy"] == "language model"
    assert body["factsheet"]["dropped"] == [{"kind": "not_in_text", "count": 2, "meaning": body["factsheet"]["dropped"][0]["meaning"]}]
    assert "not in the factsheet text" in body["factsheet"]["dropped"][0]["meaning"]
    assert body["category"] == "CYBER" and body["callYear"] == 2024
    assert {m["resolution"]["method"] for m in body["members"]} == {"exact_name"}
    assert all(m["contribution"] is None for m in body["members"])


def test_unknown_project_is_404(client, world):
    assert client.get("/v1/projects/999999-x").status_code == 404
    assert client.get("/v1/projects/abc").status_code == 404
    assert client.get("/v1/projects/999999-x/history").status_code == 404


def test_project_history_reports_the_changes_the_snapshots_saw(conn, client, world):
    first = client.get(f"/v1/projects/{world.p1}-alpha/history").json()
    assert first["firstObserved"] is None and first["changes"] == []
    networks.snapshot_consortia(conn, date(2026, 9, 1))
    join(conn, world.p1, world.F, "participant")
    conn.commit()
    networks.snapshot_consortia(conn, date(2026, 10, 1))
    h = client.get(f"/v1/projects/{world.p1}-alpha/history").json()
    assert h["firstObserved"] == {"observedAt": "2026-09-01", "memberCount": 4, "countryCount": 4}
    assert len(h["changes"]) == 1
    ch = h["changes"][0]
    assert ch["observedAt"] == "2026-10-01" and [o["name"] for o in ch["added"]] == ["FOXTROT SRL"]
    assert ch["removed"] == [] and ch["coordinatorBefore"]["name"] == ch["coordinatorAfter"]["name"] == "ALPHA SYSTEMS GMBH"


def test_project_slugs_are_the_edf_projects(client, world):
    slugs = [s["slug"] for s in client.get("/v1/projects/slugs").json()]
    assert sorted(slugs) == sorted(f"{p}-{n}" for p, n in
                                   ((world.p3, "charlie"), (world.p4, "deltap"), (world.p5, "echop"), (world.p6, "foxp")))


def test_organisation_slugs_list_the_biggest(client, world):
    got = client.get("/v1/organisations/slugs").json()
    assert [s["slug"] for s in got] == [f"{world.B}-bravo-ingenierie-sas", f"{world.A}-alpha-systems-gmbh",
                                         f"{world.E}-echo-iberica-sl"]       # three or more projects, most first


# --------------------------------------------------------------------- analytics

def test_ukraine_partners_names_the_coordinator_and_the_ukrainian_participant(client, world):
    body = client.get("/v1/analytics/ukraine-partners?since=2019").json()
    assert body["totals"] == {"projects": 1, "coordinators": 1, "ukrainianOrganisations": 1,
                              "projectsCoordinatedFromUkraine": 0}
    [c] = body["coordinators"]
    assert c["organisation"]["name"] == "ALPHA SYSTEMS GMBH" and c["projects"] == 1
    assert [u["organisation"]["name"] for u in c["ukrainianParticipants"]] == ["KYIV INSTITUTE"]
    assert [p["acronym"] for p in c["recentProjects"]] == ["ALPHA"]
    assert [u["organisation"]["name"] for u in body["ukrainianOrganisations"]] == ["KYIV INSTITUTE"]
    assert "country of establishment" in body["definition"]
    # `since` is a start year: the 2019 project is out of a later window
    later = client.get("/v1/analytics/ukraine-partners?since=2020").json()
    assert later["coordinators"] == [] and later["totals"]["projects"] == 0


def test_ukraine_partners_can_be_narrowed_to_programmes_and_says_what_the_others_hold(client, world):
    # U10: the page defaults to the defence programmes; the one Ukrainian project of the world is an H2020 one.
    every = client.get("/v1/analytics/ukraine-partners?since=2019").json()
    assert every["programme"] == [] and every["byProgramme"] == [{"code": "H2020", "projects": 1}]
    edf = client.get("/v1/analytics/ukraine-partners?since=2019&programme=edf,EDIDP").json()
    assert edf["programme"] == ["EDF", "EDIDP"] and edf["coordinators"] == [] and edf["totals"]["projects"] == 0
    assert edf["byProgramme"] == [{"code": "H2020", "projects": 1}], "what a wider choice would add"
    h = client.get("/v1/analytics/ukraine-partners?since=2019&programme=H2020").json()
    assert h["totals"]["projects"] == 1 and len(h["coordinators"]) == 1
    assert client.get("/v1/analytics/ukraine-partners?programme=EDF;DROP").status_code == 422


def test_ukraine_partners_counts_a_ukrainian_coordinator_apart(conn, client, world):
    ua2 = org(conn, "lviv works", "UA", "999000009", "LVIV WORKS")
    join(conn, world.p2, ua2, "participant")
    p7 = project(conn, "1007", "HORIZON", "Lviv led", acronym="LVIV", year=2022, start=date(2022, 1, 1))
    join(conn, p7, ua2, "coordinator")
    join(conn, p7, world.A, "participant")
    conn.commit()
    body = client.get("/v1/analytics/ukraine-partners?since=2019").json()
    assert body["totals"]["projectsCoordinatedFromUkraine"] == 1
    assert [c["organisation"]["name"] for c in body["coordinators"]] == ["ALPHA SYSTEMS GMBH"]
    assert body["coordinators"][0]["projects"] == 2           # ALPHA led P1 and P2, each with a Ukrainian participant


def test_consortium_gaps_finds_repeat_participants_who_never_partnered_with_the_country(client, world):
    body = client.get("/v1/analytics/consortium-gaps?programme=EDF&topic=CYBER&lacking=UA").json()
    assert body["projectsInArea"] == 2
    got = {i["organisation"]["name"]: i["projects"] for i in body["items"]}
    assert got == {"ALPHA SYSTEMS GMBH": 2, "BRAVO INGÉNIERIE SAS": 2, "ECHO IBERICA SL": 2}
    alpha = next(i for i in body["items"] if i["organisation"]["name"].startswith("ALPHA"))
    assert alpha["partnerCountries"] == ["ES", "FR"]
    assert {p["acronym"] for p in alpha["recentProjects"]} == {"CHARLIE", "DELTAP"}
    assert "CYBER" in {a["code"] for a in body["areas"]} and "country of establishment" in body["definition"]
    assert any("not a gap" in x for x in body["limits"])               # no Ukrainian is in any CYBER project: nobody is "missing" one
    fr = client.get("/v1/analytics/consortium-gaps?programme=EDF&topic=CYBER&lacking=FR").json()
    assert not any("not a gap" in x for x in fr["limits"])             # France does take part in them: this is a real filter


def test_consortium_gaps_drops_whoever_did_partner_with_the_country(conn, client, world):
    kyiv = world.C
    join(conn, world.p4, kyiv, "participant")                  # a Ukrainian partner appears in one CYBER project
    conn.commit()
    body = client.get("/v1/analytics/consortium-gaps?programme=EDF&topic=cyber&lacking=ua").json()
    assert body["items"] == []                                 # DELTAP now has a Ukrainian participant: nobody is left
    ground = client.get("/v1/analytics/consortium-gaps?programme=EDF&topic=GROUND&lacking=UA").json()
    assert {i["organisation"]["name"] for i in ground["items"]} == {"ECHO IBERICA SL", "FOXTROT SRL"}
    assert ground["items"][0]["projects"] == 2
    # P5 has a French participant only through the row merged into BRAVO: the merge is followed
    assert client.get("/v1/analytics/consortium-gaps?programme=EDF&topic=GROUND&lacking=FR").json()["items"] == []
    de = client.get("/v1/analytics/consortium-gaps?programme=EDF&topic=GROUND&lacking=DE").json()
    assert {i["organisation"]["name"] for i in de["items"]} == {"ECHO IBERICA SL", "FOXTROT SRL"}


def test_consortium_gaps_by_topic_code_prefix_and_its_limits(client, world):
    body = client.get("/v1/analytics/consortium-gaps?programme=EDF&topic=EDF-2023&lacking=UA&minProjects=2").json()
    assert body["projectsInArea"] == 2                                # CHARLIE (cyber) and ECHOP (ground), both of 2023 calls
    assert {i["organisation"]["name"] for i in body["items"]} == {"BRAVO INGÉNIERIE SAS", "ECHO IBERICA SL"}
    assert client.get("/v1/analytics/consortium-gaps?programme=HORIZON").status_code == 422   # no topic for Horizon
    assert client.get("/v1/analytics/consortium-gaps?programme=HORIZON&topic=HORIZON-CL4").status_code == 200
    assert client.get("/v1/analytics/consortium-gaps?topic=%25").json()["projectsInArea"] == 0   # a LIKE character is not a wildcard
    assert client.get("/v1/analytics/consortium-gaps?lacking=Ukraine").status_code == 422
    assert client.get("/v1/analytics/consortium-gaps?minProjects=1").status_code == 422


# --------------------------------------------------------------------- the API role

def _as(dsn: str, role: str, password: str) -> str:
    parts = urlsplit(dsn)
    return urlunsplit(parts._replace(netloc=f"{role}:{password}@{parts.hostname}:{parts.port}"))


def test_every_endpoint_runs_with_nothing_but_the_read_only_api_role(conn, world, monkeypatch, schema):
    monkeypatch.setenv("DGATE_API_PASSWORD", "api-test-password-1")
    monkeypatch.setenv("DGATE_WORKER_PASSWORD", "worker-test-password-1")
    with db.connect(schema) as admin:
        migrate.set_role_passwords(admin)
    monkeypatch.setenv("DGATE_API_DSN", _as(schema, "dgate_api", "api-test-password-1"))
    config.reset_cache()
    a = world.A
    urls = ["/v1/organisations", "/v1/organisations/slugs", f"/v1/organisations/{a}-x",
            f"/v1/organisations/{a}-x/funding", f"/v1/organisations/{a}-x/partners",
            f"/v1/organisations/{a}-x/projects", f"/v1/projects/{world.p1}-x", f"/v1/projects/{world.p1}-x/history",
            "/v1/projects/slugs", "/v1/analytics/ukraine-partners", "/v1/analytics/consortium-gaps"]
    with TestClient(api.app) as c:
        for u in urls:
            assert c.get(u).status_code == 200, u
    config.reset_cache()


def test_the_worker_role_rebuilds_the_directory(conn, world, monkeypatch, schema):
    monkeypatch.setenv("DGATE_API_PASSWORD", "api-test-password-1")
    monkeypatch.setenv("DGATE_WORKER_PASSWORD", "worker-test-password-1")
    with db.connect(schema) as admin:
        migrate.set_role_passwords(admin)
    with psycopg.connect(_as(schema, "dgate_worker", "worker-test-password-1"), row_factory=psycopg.rows.dict_row) as w:
        out = networks.refresh_organisation_network(w)
    assert out["organisations"] == 7


def test_a_snapshot_run_refreshes_the_directory(conn, world):
    conn.execute("DELETE FROM organisation_network")
    conn.commit()
    assert conn.execute("SELECT count(*) AS n FROM organisation_network").fetchone()["n"] == 0
    out = networks.snapshot_consortia(conn, date(2026, 10, 1))
    assert out["projects"] == 6
    networks.refresh_organisation_network(conn)
    assert conn.execute("SELECT count(*) AS n FROM organisation_network").fetchone()["n"] == 7
