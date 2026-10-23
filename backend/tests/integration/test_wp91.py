"""WP-91: the funding path of the UX audit of 22 October 2026, section 6 (Piotr, a Polish drone-software start-up).

Against a real Postgres. No network and no model: calls, projects and participations are rows written here.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from dgate import accounts, api, networks, stats
from dgate.readiness import api as readiness_api
from dgate.readiness.seed import apply as apply_rules
from dgate.readiness.seed import load_file as load_rules
from tests.integration import test_network_api as net
from tests.integration import test_wp32 as wp32
from tests.integration.test_wp31 import put

pytestmark = pytest.mark.integration

USI = "EDF-EDIP-USI-2027-LS-IRA-CUXS"
CPA = "EDF-EDIP-P-2027-FNLC-CPA-AMDS"
EDF = "EDF-2026-DA-SPACE-SSA"


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    readiness_api.reset_cache()
    yield
    stats.reset_cache()
    readiness_api.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def titled(conn, cid: int, title: str) -> None:
    conn.execute("UPDATE call SET title = %s WHERE id = %s", (title, cid))
    conn.commit()


def listing(client, **params) -> dict:
    r = client.get("/v1/funding", params={"status": "all", "pageSize": 50, **params})
    assert r.status_code == 200, r.text
    return r.json()


def ids(body: dict) -> set[str]:
    return {c["id"] for c in body["items"]}


@pytest.fixture()
def calls(conn):
    """A Ukraine Support Instrument topic, an EDIP common-procurement topic, an EDF topic (all filed under EDF by the portal),
    a Horizon topic the portal flags for SMEs with its tags, and a Horizon topic that says nothing of who may apply."""
    out = {
        "usi": put(conn, "usi", programme="EDF", topic=USI),
        "cpa": put(conn, "cpa", programme="EDF", topic=CPA),
        "edf": put(conn, "edf", programme="EDF", topic=EDF),
        "sme": put(conn, "sme", topic="HORIZON-CL3-2026-01-DRS-01",
                   conditions={"for_smes": True, "tags": ["Software", "Autonomous systems"]}),
        "plain": put(conn, "plain", topic="HORIZON-CL4-2026-01-MAT-01"),
    }
    titled(conn, out["usi"], "Unmanned systems and counter-unmanned systems")
    return {k: str(v) for k, v in out.items()}


# ------------------------------------------------------------------------------------- 3. programme labels

def test_an_edip_topic_filed_under_the_edf_is_labelled_by_its_instrument(client, calls):
    by_id = {c["id"]: c["programme"] for c in listing(client)["items"]}
    assert by_id[calls["usi"]] == "EDIP-USI" and by_id[calls["cpa"]] == "EDIP" and by_id[calls["edf"]] == "EDF"
    detail = client.get(f"/v1/funding/{calls['usi']}").json()
    assert detail["programme"] == "EDIP-USI" and detail["rulesApply"]["regime"]["code"] == "EDIP-USI"


def test_the_programme_filter_reads_the_same_labels(client, calls):
    assert ids(listing(client, programme="EDIP-USI")) == {calls["usi"]}
    assert ids(listing(client, programme="EDIP")) == {calls["usi"], calls["cpa"]}, "the instrument is part of EDIP"
    assert ids(listing(client, programme="EDF")) == {calls["usi"], calls["cpa"], calls["edf"]}, "EDF and EDIP: every call filed under it"
    assert client.get("/v1/funding", params={"programme": "EDIPUSI"}).status_code == 422


def test_a_programme_follow_names_the_instrument(conn, calls):
    chips = accounts._programmes(conn)
    assert {"EDF", "EDIP", "EDIP-USI"} <= set(chips)
    assert chips["EDIP-USI"]["name"] == "EDIP Ukraine Support Instrument" and chips["EDIP-USI"]["openCount"] == 1


# ------------------------------------------------------------------------------------- 5. who may apply

def test_who_may_apply_is_read_from_the_rules_and_the_stored_call_data(client, calls):
    by_id = {c["id"]: c["whoMayApply"] for c in listing(client)["items"]}
    assert by_id[calls["cpa"]] == "public", "common procurement: contracting authorities, SEAPs, the EDA"
    assert by_id[calls["usi"]] == by_id[calls["edf"]] == "companies"
    assert by_id[calls["sme"]] == "companies", "the portal's SME flag"
    assert by_id[calls["plain"]] is None, "nothing we hold says: no badge, never a guess"
    assert ids(listing(client, who="public")) == {calls["cpa"]}
    assert ids(listing(client, who="companies")) == {calls["usi"], calls["edf"], calls["sme"]}
    assert client.get("/v1/funding", params={"who": "everybody"}).status_code == 422


def test_a_saved_search_keeps_the_who_filter(conn, calls):
    assert accounts.clean_filters("call", {"who": "companies"}) == {"who": "companies"}
    with pytest.raises(accounts.AccountError):
        accounts.clean_filters("call", {"who": "x"})
    page = accounts.run_search(conn, "call", {"who": "public", "status": "all"}, full=True)
    assert [i["id"] for i in page["items"]] == [calls["cpa"]]


# ------------------------------------------------------------------------------------- 4. search

def test_search_reads_the_topic_tags_the_sme_flag_and_the_new_synonyms(client, calls):
    assert ids(listing(client, q="software")) == {calls["sme"]}, "the portal's tag 'Software'"
    assert ids(listing(client, q="autonomy")) == {calls["sme"]}, "autonomy also finds autonomous"
    assert calls["sme"] in ids(listing(client, q="SME")), "the portal's SME flag"
    body = listing(client, q="drone")
    assert calls["usi"] in ids(body) and "unmanned" in body["search"]["alsoSearched"]
    assert ids(listing(client, q="EUDIS")) == set()


# ------------------------------------------------------------------------------------- 2. can I apply?

def test_the_rules_block_says_per_country_group_what_the_establishment_rules_give(conn, client, calls):
    apply_rules(conn, load_rules())
    conn.commit()
    block = client.get(f"/v1/funding/{calls['usi']}").json()["rulesApply"]
    eu = {r["rule"]: r for r in block["byCountry"]["EU"]}
    assert eu["USI-ESTABLISH"]["outcome"] == "met"
    assert eu["USI-INVOLVES-UA"]["outcome"] == "unknown" and eu["USI-INVOLVES-UA"]["asks"] == ["ua_partner"], \
        "from Poland: only together with a Ukrainian partner, never a plain yes"
    assert "USI-TERRITORY" not in eu, "the non-government-controlled areas concern a Ukrainian company only"
    ua = {r["rule"]: r for r in block["byCountry"]["UA"]}
    assert ua["USI-INVOLVES-UA"]["outcome"] == "met" and ua["USI-TERRITORY"]["asks"] == ["ua_non_government_controlled_area"]
    assert {r["rule"]: r["outcome"] for r in block["byCountry"]["OTHER"]}["USI-ESTABLISH"] == "not_met"
    assert block["forCompany"] == []
    cpa = client.get(f"/v1/funding/{calls['cpa']}").json()["rulesApply"]
    assert [(r["rule"], r["outcome"]) for r in cpa["forCompany"]] == [("EDIP-CPA-APPLICANT", "not_met")]


# ------------------------------------------------------------------------------------- 6. partners and organisations

def test_partners_of_an_edip_topic_rank_by_its_title_words_and_offer_ukraine(conn, client, calls):
    big = wp32.org(conn, "Leonardo SpA", "IT")
    drone = wp32.org(conn, "Dron Sp. z o.o.", "PL")
    for i in range(3):
        wp32.join(conn, wp32.project(conn, f"big{i}", category="NAVAL", year=2022, topic="EDF-2022-DA-NAVAL-X",
                                     title=f"Naval platform {i}"), big)
    wp32.join(conn, wp32.project(conn, "uas1", category="AIR", year=2023, topic="EDF-2023-DA-AIR-X",
                                 title="Counter-UAS sensor network"), drone)
    conn.commit()
    body = wp32.partners(client, f"{calls['usi']}-x")
    assert body["area"]["generic"] is True
    assert [p["name"] for p in body["partners"]][:2] == ["Dron Sp. z o.o.", "Leonardo SpA"], "the topic first, then the largest"
    assert body["partners"][0]["topical"] == 1 and body["partners"][1]["topical"] == 0
    assert "unmanned" in body["area"]["topicWords"] and "uas" in body["area"]["topicAlso"]
    assert body["area"]["topicalProjects"] == 1 and "share a word of its title" in body["note"]
    assert {"country": "UA", "organisations": 0} in body["countries"], "Ukraine is a choice for the instrument"
    edf_body = wp32.partners(client, f"{calls['cpa']}-x")
    assert all(c["country"] != "UA" for c in edf_body["countries"]), "not for another call"


@pytest.fixture()
def projects(conn):
    a = net.org(conn, "dron works", "PL", None, "DRON WORKS SP Z O O")
    b = net.org(conn, "air frame", "FR", None, "AIR FRAME SAS")
    c = net.org(conn, "kyiv lab", "UA", None, "KYIV LAB")
    civil = net.org(conn, "civil uni", "PT", None, "CIVIL UNIVERSITY")
    mro = net.org(conn, "aero mro", "NL", None, "AERO MRO BV")
    p1 = net.project(conn, "t1", "EDF", "Swarm of drones for perimeter security", source="edf_factsheets", year=2024, category="AIR")
    p2 = net.project(conn, "t2", "HORIZON", "Aircraft maintenance", year=2023, start=date(2023, 1, 1))
    p3 = net.project(conn, "t3", "HORIZON", "AI for crisis maps", year=2023, start=date(2023, 1, 1))
    for p, o in ((p1, a), (p2, mro), (p3, b)):
        net.join(conn, p, o)
    # Ukraine partners: a coordinator with one defence-relevant project, one with two civil ones
    q1 = net.project(conn, "u1", "HORIZON", "Border sensing", year=2023, start=date(2023, 1, 1))
    conn.execute("UPDATE project SET call_code = 'HORIZON-CL3-2022-BM-01' WHERE id = %s", (q1,))
    q2 = net.project(conn, "u2", "HORIZON", "Folk songs", year=2023, start=date(2023, 2, 1))
    q3 = net.project(conn, "u3", "HORIZON", "Old maps", year=2024, start=date(2024, 2, 1))
    for p in (q2, q3):
        net.join(conn, p, civil, "coordinator")
        net.join(conn, p, c)
    net.join(conn, q1, b, "coordinator")
    net.join(conn, q1, c)
    conn.commit()
    networks.refresh_organisation_network(conn)
    return {"a": a, "b": b, "c": c, "civil": civil}


def names(client, **params) -> list[str]:
    r = client.get("/v1/organisations", params={"pageSize": 50, **params})
    assert r.status_code == 200, r.text
    return sorted(i["name"] for i in r.json()["items"])


def test_organisations_by_the_topic_of_their_projects(client, projects):
    assert names(client, topic="drone") == ["DRON WORKS SP Z O O"], "drones, at the start of a word"
    assert names(client, topic="unmanned") == ["DRON WORKS SP Z O O"], "a synonym of drone"
    assert names(client, topic="AI") == ["AIR FRAME SAS"], "AI is a whole word: not 'aircraft', and the AI project is AIR FRAME's"
    assert names(client, topic="swarm security") == ["DRON WORKS SP Z O O"], "every word, in one project"
    assert names(client, topic="swarm maintenance") == []
    assert names(client, topic="air") == ["DRON WORKS SP Z O O"], "the EDF category AIR; 'aircraft' is another word"
    assert names(client, topic="aircraft") == ["AERO MRO BV"]


def test_the_topic_index_exists(conn):
    row = conn.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'project_topic_fold'").fetchone()
    assert row and "gin_trgm_ops" in row["indexdef"]


def test_ukraine_partners_put_defence_relevant_projects_first(client, projects):
    body = client.get("/v1/analytics/ukraine-partners?since=2021").json()
    coords = [c["organisation"]["name"] for c in body["coordinators"]]
    assert coords == ["AIR FRAME SAS", "CIVIL UNIVERSITY"], "one dual-use project ranks above two civil ones"
    assert body["coordinators"][0]["dualUseProjects"] == 1 and body["coordinators"][1]["dualUseProjects"] == 0
    assert "defence programmes come first" in body["order"]
