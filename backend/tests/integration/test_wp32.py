"""WP-32: partner suggestions for a funding call, the document facts of the fit badge, and the programme a call is judged by.

Against a real Postgres, with fixtures of projects, participations and calls. No network, no model.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, stats
from dgate.funding import make_slug
from dgate.readiness import api as readiness_api
from dgate.readiness import seed
from tests.integration import test_readiness_api
from tests.integration.test_readiness_api import CONTENT, UA
from tests.integration.test_wp31 import doc, hold, put

pytestmark = pytest.mark.integration

service_roles = test_readiness_api.service_roles       # the fixture of the read-only roles, shared

PARTNER_KEYS = {"organisationId", "slug", "name", "country", "projects", "coordinated", "firstYear", "lastYear", "evidence"}


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _source(conn, code):
    return conn.execute("SELECT id FROM source WHERE code = %s", (code,)).fetchone()["id"]


def project(conn, native, *, edf=True, category=None, topic=None, year=2024, acronym=None, title=None):
    """An EDF project has a topic code made from its file name; a CORDIS one has the call code that the area is read
    from (`HORIZON-CL3-2023-BM-01`) and a topic code with the prefix CORDIS puts on it (`HORIZON_HORIZON-CL3-2023-BM-01-02`)."""
    call_code = None if edf or not topic else topic.rsplit("-", 1)[0]
    return conn.execute(
        """INSERT INTO project (source_id, native_id, acronym, title, topic_code, call_code, category, call_year, start_date)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (_source(conn, "edf_factsheets" if edf else "cordis"), native, acronym or native.upper(),
         title or f"Project {native}", f"HORIZON_{topic}" if call_code else topic, call_code, category, year,
         None if edf else f"{year}-03-01")).fetchone()["id"]


def org(conn, name, country, *, suppressed=False, merged_into=None):
    return conn.execute(
        "INSERT INTO organisation (canonical_name, display_name, country, suppressed, merged_into) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id", (name.lower(), name, country, suppressed, merged_into)).fetchone()["id"]


def join(conn, p, o, role="participant", active=True):
    conn.execute(
        """INSERT INTO participation (project_id, organisation_id, role, resolution_method, resolution_confidence, active)
           VALUES (%s, %s, %s, 'pic', 1, %s)""", (p, o, role, active))


def call(conn, native, topic, programme="EDF", **kw):
    cid = put(conn, native, programme=programme, topic=topic, **kw)
    title = conn.execute("SELECT title FROM call WHERE id = %s", (cid,)).fetchone()["title"]
    return cid, make_slug(cid, title)


def partners(client, slug, **params):
    r = client.get(f"/v1/funding/{slug}/partners", params=params)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def space(conn):
    """Six organisations in the EDF category SPACE, with ties that only the year can break, one that left
    the project and one in another category."""
    p23, p24, p25 = (project(conn, f"s{y}", category="SPACE", year=y, topic=f"EDF-{y}-DA-SPACE-X") for y in (2023, 2024, 2025))
    other = project(conn, "air", category="AIR", year=2025, topic="EDF-2025-DA-AIR-X")
    a, b, c, d, e, f = (org(conn, n, cc) for n, cc in (("Alpha SA", "FR"), ("Bravo GmbH", "DE"), ("Charlie SL", "ES"),
                                                      ("Delta SA", "ES"), ("Echo AB", "SE"), ("Foxtrot SA", "FR")))
    for project_id, who, role in ((p23, a, "coordinator"), (p24, a, "participant"), (p25, a, "participant"),   # Alpha: 3 projects
                                  (p25, b, "participant"), (p24, b, "participant"),                           # Bravo: 2, last 2025
                                  (p23, c, "participant"), (p24, c, "participant")):                          # Charlie: 2, last 2024
        join(conn, project_id, who, role)
    join(conn, p25, d, "coordinator")                                                   # Delta: 1, 2025
    join(conn, p23, e)                                                                  # Echo: 1, 2023
    join(conn, p25, f, active=False)                                                    # Foxtrot left: not counted
    join(conn, other, e)                                                                # another category: not counted
    conn.commit()
    return {"a": a, "b": b, "c": c, "d": d, "e": e, "f": f, "p": (p23, p24, p25)}


# ------------------------------------------------------------------------------ partner suggestions

def test_partners_are_ranked_by_projects_in_the_area_then_by_recency(client, conn, space):
    cid, slug = call(conn, "edf1", "EDF-2026-DA-SPACE-PRS-STEP")
    body = partners(client, slug)
    assert [p["name"] for p in body["partners"]] == ["Alpha SA", "Bravo GmbH", "Charlie SL", "Delta SA", "Echo AB"]
    assert [p["projects"] for p in body["partners"]] == [3, 2, 2, 1, 1]
    assert body["area"]["kind"] == "edf-category" and body["area"]["broaderThanCall"] is False
    assert body["area"]["projects"] == 3 and (body["area"]["firstYear"], body["area"]["lastYear"]) == (2023, 2025)
    alpha = body["partners"][0]
    assert (alpha["coordinated"], alpha["firstYear"], alpha["lastYear"], alpha["country"]) == (1, 2023, 2025, "FR")
    assert body["total"] == 5 and body["note"] is None and body["call"]["id"] == str(cid)
    assert body["source"]["licence"].startswith("Commission Decision 2011/833/EU")


def test_a_partner_carries_the_organisation_slug_and_at_most_three_projects_as_evidence_newest_first(client, conn, space):
    for i in range(3):
        join(conn, project(conn, f"x{i}", category="SPACE", year=2020 + i, topic="EDF-2024-DA-SPACE-X"), space["a"])
    conn.commit()
    _, slug = call(conn, "edf1", "EDF-2026-DA-SPACE-PRS-STEP")
    alpha = partners(client, slug)["partners"][0]
    assert alpha["slug"] == make_slug(space["a"], "Alpha SA") and alpha["slug"].startswith(f"{space['a']}-alpha-sa")
    assert alpha["projects"] == 6
    assert [e["year"] for e in alpha["evidence"]] == [2025, 2024, 2023]
    assert set(alpha["evidence"][0]) == {"projectId", "acronym", "title", "year", "role"}
    assert set(alpha) == PARTNER_KEYS, "organisation facts only: no contact, no person"


def test_an_organisation_that_left_the_project_or_was_removed_on_request_is_not_suggested(client, conn, space):
    _, slug = call(conn, "edf1", "EDF-2026-DA-SPACE-PRS-STEP")
    assert "Foxtrot SA" not in [p["name"] for p in partners(client, slug)["partners"]]
    conn.execute("UPDATE organisation SET suppressed = TRUE WHERE id = %s", (space["e"],))
    conn.commit()
    stats.reset_cache()
    body = partners(client, slug)
    assert "Echo AB" not in [p["name"] for p in body["partners"]]
    # four organisations are under the minimum, so the broader area answers (Echo is still removed there)
    assert body["area"]["broaderThanCall"] is True and "Echo AB" not in {p["name"] for p in body["partners"]}


def test_a_merged_organisation_is_read_as_the_one_it_was_merged_into_and_counted_once_per_project(client, conn, space):
    gone = org(conn, "Alpha Aerospace (old spelling)", "FR", merged_into=space["a"])
    join(conn, space["p"][2], gone)             # the same project as Alpha: still one project
    join(conn, space["p"][0], gone)
    conn.commit()
    _, slug = call(conn, "edf1", "EDF-2026-DA-SPACE-PRS-STEP")
    body = partners(client, slug)
    alpha = body["partners"][0]
    assert alpha["organisationId"] == str(space["a"]) and alpha["projects"] == 3
    assert [e["acronym"] for e in alpha["evidence"]] == ["S2025", "S2024", "S2023"], "no project twice"
    assert all(p["organisationId"] != str(gone) for p in body["partners"])
    assert body["total"] == 5


def test_the_country_filter_and_the_country_counts(client, conn, space):
    _, slug = call(conn, "edf1", "EDF-2026-DA-SPACE-PRS-STEP")
    body = partners(client, slug, country="es")
    assert [p["name"] for p in body["partners"]] == ["Charlie SL", "Delta SA"] and body["total"] == 2 and body["country"] == "ES"
    # the filter does not change what the counts say: they let the visitor choose another country
    assert {c["country"]: c["organisations"] for c in body["countries"]} == {"ES": 2, "FR": 1, "DE": 1, "SE": 1}
    assert partners(client, slug, country="PL")["partners"] == []
    assert client.get(f"/v1/funding/{slug}/partners", params={"country": "Spain"}).status_code == 422


def test_the_limit_is_honoured_and_bounded(client, conn, space):
    _, slug = call(conn, "edf1", "EDF-2026-DA-SPACE-PRS-STEP")
    assert len(partners(client, slug, limit=2)["partners"]) == 2
    assert client.get(f"/v1/funding/{slug}/partners", params={"limit": 51}).status_code == 422
    assert client.get(f"/v1/funding/{slug}/partners", params={"limit": 0}).status_code == 422


def test_a_category_with_too_few_organisations_falls_back_to_all_edf_and_says_so(client, conn, space):
    _, slug = call(conn, "edf2", "EDF-2026-DA-AIR-SPS")                  # one organisation in AIR
    body = partners(client, slug)
    assert body["area"]["kind"] == "edf" and body["area"]["broaderThanCall"] is True
    assert "all projects of the European Defence Fund" in body["area"]["label"]
    assert body["partners"][0]["name"] == "Alpha SA"


def test_an_edip_call_is_compared_with_all_edf_projects(client, conn, space):
    # counter-drone systems: no EDF category is named by the title (WP-41: AMDS, GNPS and C5ISRS now are)
    _, slug = call(conn, "edip1", "EDF-EDIP-P-2026-FNLC-CPA-CDS")
    body = partners(client, slug)
    assert body["area"]["kind"] == "edf" and body["area"]["broaderThanCall"] is False and body["partners"]
    assert body["area"]["generic"] is True and "no earlier counterpart" in body["note"]


def test_a_horizon_call_is_compared_with_its_destination_and_not_with_other_destinations(client, conn):
    orgs = [org(conn, n, "ES") for n in ("Bm1", "Bm2", "Bm3", "Bm4", "Bm5", "Fct1")]
    bm = [project(conn, f"bm{i}", edf=False, topic=f"HORIZON-CL3-{2022 + i}-BM-01-0{i + 1}", year=2022 + i) for i in range(3)]
    fct = project(conn, "fct", edf=False, topic="HORIZON-CL3-2023-FCT-01-01", year=2023)
    other_cluster = project(conn, "cl4", edf=False, topic="HORIZON-CL4-2023-BM-01-01", year=2023)
    for i, o in enumerate(orgs[:5]):
        join(conn, bm[i % 3], o)
    for project_id, who in ((fct, orgs[5]), (other_cluster, orgs[0]), (other_cluster, orgs[5])):
        join(conn, project_id, who)
    conn.commit()
    _, slug = call(conn, "hz1", "HORIZON-CL3-2026-01-BM-01", programme="HORIZON")
    body = partners(client, slug)
    assert body["area"]["kind"] == "horizon-destination" and body["area"]["projects"] == 3
    assert sorted(p["name"] for p in body["partners"]) == ["Bm1", "Bm2", "Bm3", "Bm4", "Bm5"]
    assert next(p for p in body["partners"] if p["name"] == "Bm1")["projects"] == 1, "the CL4 project is not in the area"
    # a destination nobody funded yet falls back to the cluster
    _, slug2 = call(conn, "hz2", "HORIZON-CL3-2026-01-SSRI-01", programme="HORIZON")
    wide = partners(client, slug2)
    assert wide["area"]["kind"] == "horizon-family" and wide["area"]["broaderThanCall"] is True
    assert "Fct1" in {p["name"] for p in wide["partners"]}


def test_an_area_that_is_too_broad_is_not_ranked_and_the_answer_says_so(client, conn, space, monkeypatch):
    from dgate import partners as module

    monkeypatch.setattr(module, "MAX_AREA_PROJECTS", 2)
    _, slug = call(conn, "edf1", "EDF-2026-DA-SPACE-PRS-STEP")          # 3 SPACE projects, 4 in all EDF
    body = partners(client, slug)
    assert body["partners"] == [] and "too broad" in body["note"]
    assert body["area"]["label"] == "EDF capability category SPACE" and body["area"]["projects"] == 0
    monkeypatch.setattr(module, "MAX_AREA_PROJECTS", 3)                 # exactly at the limit: ranked
    assert partners(client, slug)["partners"]


def test_projects_of_the_wrong_source_are_not_compared(client, conn):
    p = project(conn, "cordis-space", edf=False, category="SPACE", topic="HORIZON-CL4-2023-SPACE-01-01")
    for i in range(6):
        join(conn, p, org(conn, f"O{i}", "FR"))
    conn.commit()
    _, slug = call(conn, "edf1", "EDF-2026-DA-SPACE-PRS-STEP")
    body = partners(client, slug)
    assert body["partners"] == [] and body["note"]


def test_a_call_with_no_comparable_projects_gets_an_honest_empty_answer(client, conn, space):
    _, digital = call(conn, "dg1", "DIGITAL-2026-AI-09-DS-HEALTH-TOOL", programme="DIGITAL")
    body = partners(client, digital)
    assert body["area"] is None and body["partners"] == [] and "not in the project data" in body["note"]
    _, empty = call(conn, "hz3", "HORIZON-EIC-2026-ACCELERATOR-01", programme="HORIZON")
    body = partners(client, empty)
    assert body["partners"] == [] and body["area"]["projects"] == 0 and "No earlier project" in body["note"]


def test_an_unknown_call_is_404_a_removed_one_410_and_a_bad_slug_404(client, conn, space):
    assert client.get("/v1/funding/987654-x/partners").status_code == 404
    assert client.get("/v1/funding/not-a-call/partners").status_code == 404
    cid, slug = call(conn, "edf1", "EDF-2026-DA-SPACE-PRS-STEP")
    conn.execute("UPDATE call SET suppressed = TRUE WHERE id = %s", (cid,))
    conn.commit()
    assert client.get(f"/v1/funding/{slug}/partners").status_code == 410


def test_the_call_slug_resolves_by_its_leading_id_even_when_the_title_changed(client, conn, space):
    cid, _ = call(conn, "edf1", "EDF-2026-DA-SPACE-PRS-STEP")
    assert partners(client, str(cid))["partners"] and partners(client, f"{cid}-an-older-title")["partners"]


def test_the_call_detail_names_the_partner_area_from_the_topic_code_alone(client, conn):
    _, edf = call(conn, "edf1", "EDF-2026-DA-SPACE-PRS-STEP")
    _, digital = call(conn, "dg1", "DIGITAL-2026-AI-09-DS-HEALTH-TOOL", programme="DIGITAL")
    assert client.get(f"/v1/funding/{edf}").json()["partnerArea"] == "EDF capability category SPACE"
    assert client.get(f"/v1/funding/{digital}").json()["partnerArea"] is None


# ------------------------------------------------------------------------------ the facts of the fit badge

def test_fit_facts_serve_only_the_facts_the_badge_reads_and_no_quote(client, conn):
    read = put(conn, "read", documents=[doc("https://example.test/a.pdf")])
    hold(conn, "https://example.test/a.pdf", "call_document",
         eligible_countries=("EU Member States and associated countries", "Eligible: Member States.", None),
         sme_only=(False, "Open to all.", "A bonus for SMEs."),
         funding_rate=("100%", "Funding rate 100%.", None),                 # not a fit fact
         cascade_funding=(True, "FSTP allowed.", None))
    body = client.get("/v1/fit/facts", params={"ids": str(read)}).json()["items"][str(read)]
    assert body["state"] == "read" and body["basis"] == "call_document"
    assert body["programme"] == "HORIZON" and body["topic"] == "HORIZON-read"
    assert set(body["facts"]) == {"eligible_countries", "sme_only"}
    assert body["facts"]["sme_only"] == {"value": False, "note": "A bonus for SMEs.", "scope": "call_document"}
    assert all("quote" not in f for f in body["facts"].values())


def test_fit_facts_say_not_read_for_unread_calls_and_no_source_for_national_ones_and_skip_removed_ones(client, conn):
    unread = put(conn, "unread", documents=[doc("https://example.test/b.pdf")])
    national = put(conn, "nat", programme="PL-NCBR", source="pl_ncbr")
    gone = put(conn, "gone", documents=[doc("https://example.test/c.pdf")])
    conn.execute("UPDATE call SET suppressed = TRUE WHERE id = %s", (gone,))
    conn.commit()
    items = client.get("/v1/fit/facts", params={"ids": f"{unread},{national},{gone},4242"}).json()["items"]
    assert items[str(unread)]["state"] == "not_read" and items[str(unread)]["facts"] == {}
    assert items[str(national)] == {"state": "no_source", "basis": None, "facts": {}, "programme": "NATIONAL", "topic": "PL-NCBR-nat"}
    assert str(gone) not in items and "4242" not in items


def test_fit_facts_follow_the_licence_row_of_the_source(client, conn):
    cid = put(conn, "lic", documents=[doc("https://example.test/d.pdf")])
    hold(conn, "https://example.test/d.pdf", "call_document", sme_only=(True, "SMEs only.", None))
    assert client.get("/v1/fit/facts", params={"ids": str(cid)}).json()["items"][str(cid)]["state"] == "read"
    was = conn.execute("SELECT commercial_ok FROM source WHERE code = 'eu_portal'").fetchone()["commercial_ok"]
    try:
        conn.execute("UPDATE source SET commercial_ok = NULL WHERE code = 'eu_portal'")
        conn.commit()
        assert client.get("/v1/fit/facts", params={"ids": str(cid)}).json()["items"][str(cid)]["state"] == "no_source"
    finally:                                   # `source` is reference data that no test starts without
        conn.execute("UPDATE source SET commercial_ok = %s WHERE code = 'eu_portal'", (was,))
        conn.commit()


def test_fit_facts_refuse_bad_ids_and_more_than_a_hundred(client):
    for bad in ("", "a", "1,,2", "1;2", "-1", "1 ,2", "1,x", "9999999999"):
        assert client.get("/v1/fit/facts", params={"ids": bad}).status_code == 422, bad
    assert client.get("/v1/fit/facts", params={"ids": ",".join(str(i) for i in range(1, 102))}).status_code == 422
    assert client.get("/v1/fit/facts", params={"ids": ",".join(str(i) for i in range(1, 101))}).status_code == 200
    assert client.get("/v1/fit/facts").status_code == 422


# ------------------------------------------------------------------------------ the programme a call is judged by

def test_an_edip_call_filed_under_the_edf_is_judged_by_the_edip_rules(conn):
    readiness_api.reset_cache()
    seed.apply(conn, CONTENT)
    conn.commit()
    with TestClient(api.app) as client:
        edip, _ = call(conn, "e1", "EDF-EDIP-P-2027-FNLC-CPA-AMDS", days=60)
        usi, _ = call(conn, "e2", "EDF-EDIP-USI-2027-LS-IRA-CUXS", days=60)
        plain, _ = call(conn, "e3", "EDF-2026-DA-SPACE-PRS-STEP", days=60)

        def timings(cid):
            return {t["programme"]: t["realistic"] for t in
                    client.post("/v1/readiness/assess", json={"profile": UA, "call": cid}).json()["call"]["timings"]}

        assert timings(edip) == {"EDIP": "not_possible"}, "a Ukrainian company is not eligible for the EDIP programme"
        assert timings(usi) == {"EDIP-USI": "yes"}
        assert timings(plain) == {"EDF": "yes"}


# ------------------------------------------------------------------------------ the read-only role

def test_both_reads_work_with_nothing_but_the_read_only_api_role(conn, space, service_roles, monkeypatch):
    """The tests above run as the owner; the site runs as `dgate_api`, which can only SELECT. A table or a column the
    queries read and the role may not would fail here and nowhere else."""
    _, slug = call(conn, "edf1", "EDF-2026-DA-SPACE-PRS-STEP")
    read = put(conn, "read", documents=[doc("https://example.test/r.pdf")])
    hold(conn, "https://example.test/r.pdf", "call_document", sme_only=(True, "SMEs only.", None))
    monkeypatch.setenv("DGATE_API_DSN", service_roles["api"])
    config.reset_cache()
    with TestClient(api.app) as c:
        body = c.get(f"/v1/funding/{slug}/partners").json()
        assert [p["name"] for p in body["partners"]][:2] == ["Alpha SA", "Bravo GmbH"] and body["source"]["licence"]
        assert c.get("/v1/fit/facts", params={"ids": str(read)}).json()["items"][str(read)]["facts"]["sme_only"]["value"] is True
    config.reset_cache()
