"""WP-133 against a real Postgres: an old link of an organisation row merged into another (`organisation.merged_into`)
answers the head under the head's slug on the buyer, buyer profile, buyer suppliers, supplier and organisation endpoints
(the web page redirects when the slug differs), through a two-step chain as well, and a row that is not merged is
unchanged; the buyer sitemap lists heads only; and two buyer rows holding the same notice in e-Zamówienia and its mirror
become a merge candidate (`ops.shared_notice_candidates`), never a merge."""

from __future__ import annotations

from itertools import pairwise

import pytest
from fastapi.testclient import TestClient

from dgate import api, db, stats
from dgate.ops import shared_notice_candidates

from .test_buyer_families import put
from .test_network_api import world  # noqa: F401 - the networks fixture
from .test_wp105 import award, notice, org

pytestmark = pytest.mark.integration

QUIET = {"out": lambda *_: None}


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _merge(conn, keep: int, absorbed: int) -> None:
    db.merge_organisations(conn, keep, absorbed, method="person_review", confidence=0.95, evidence="test",
                           detected_by="test_wp133")
    conn.commit()


def _chain(conn, *ids: int) -> None:
    """ids[0] <- ids[1] <- ids[2] ...: each merged into the one before it, as rows merged before WP-115 could be."""
    for head, row in pairwise(ids):
        conn.execute("UPDATE organisation SET merged_into = %s, merge_method = 'person_review', merge_confidence = 0.9 "
                     "WHERE id = %s", (head, row))
    conn.commit()


def _org_of(conn, oid: int) -> int:
    return conn.execute("SELECT buyer_org_id AS o FROM opportunity WHERE id = %s", (oid,)).fetchone()["o"]


@pytest.fixture()
def buyers(conn):
    head = _org_of(conn, put(conn, "H-1", "Zaklad Karny we Wronkach", country="PL"))
    put(conn, "H-2", "Zaklad Karny we Wronkach", country="PL")
    once = _org_of(conn, put(conn, "M-1", "Zaklad Karny", country="PL"))
    twice = org(conn, "zaklad karny wronki", "PL")
    alone = _org_of(conn, put(conn, "A-1", "Areszt Sledczy", country="PL"))
    _merge(conn, head, once)            # its notice moves to the head
    _chain(conn, once, twice)           # twice -> once -> head
    return {"head": head, "once": once, "twice": twice, "alone": alone}


def test_a_merged_buyer_answers_its_head_through_a_chain_and_an_unmerged_one_is_unchanged(client, buyers):
    page = client.get(f"/v1/buyers/{buyers['head']}-x").json()
    assert page["id"] == str(buyers["head"]) and page["tenderCount"] == 3
    for old in ("once", "twice"):
        r = client.get(f"/v1/buyers/{buyers[old]}-zaklad-karny")
        assert r.status_code == 200, old
        assert (r.json()["id"], r.json()["slug"], r.json()["tenderCount"]) == (page["id"], page["slug"], 3)
    alone = client.get(f"/v1/buyers/{buyers['alone']}-areszt").json()
    assert alone["id"] == str(buyers["alone"]) and alone["tenderCount"] == 1
    assert client.get("/v1/buyers/999999-nobody").status_code == 404


def test_the_profile_and_the_suppliers_of_a_merged_buyer_are_its_heads(client, buyers):
    head = client.get(f"/v1/buyers/{buyers['head']}-x/profile").json()
    assert head["tenderCount"] == 3
    assert client.get(f"/v1/buyers/{buyers['twice']}-x/profile").json() == head
    assert client.get(f"/v1/buyers/{buyers['twice']}-x/suppliers").json() == \
        client.get(f"/v1/buyers/{buyers['head']}-x/suppliers").json()


def test_the_buyer_sitemap_lists_heads_only(conn, client, buyers):
    ids = {s["slug"].split("-")[0] for s in client.get("/v1/buyers/slugs").json()}
    assert str(buyers["head"]) in ids and str(buyers["alone"]) in ids
    assert not ids & {str(buyers["once"]), str(buyers["twice"])}
    # a family head merged away later (the family table not yet rebuilt) is not listed under its old id
    conn.execute("INSERT INTO buyer_family_member (org_id, head_org_id, method, confidence) VALUES (%s, %s, 'test', 0.9)",
                 (buyers["alone"], buyers["once"]))
    conn.commit()
    stats.reset_cache()
    ids = {s["slug"].split("-")[0] for s in client.get("/v1/buyers/slugs").json()}
    assert str(buyers["once"]) not in ids


def test_a_merged_supplier_answers_its_head_through_a_chain(conn, client):
    buyer = org(conn, "ministerio de defensa", "ES")
    head = org(conn, "acme sa", "ES")
    once = org(conn, "acme", "ES")
    twice = org(conn, "acme s a", "ES")
    alone = org(conn, "other sl", "ES")
    award(conn, notice(conn, "S-1", buyer=buyer, country="ES"), head, "ACME SA")
    award(conn, notice(conn, "S-2", buyer=buyer, country="ES"), once, "ACME S.A.")   # awards sit one step away (WP-115)
    award(conn, notice(conn, "S-3", buyer=buyer, country="ES"), alone, "OTHER SL")
    conn.commit()
    _chain(conn, head, once, twice)
    page = client.get(f"/v1/suppliers/{head}-acme-sa").json()
    assert page["id"] == str(head) and page["awardCount"] == 2
    for old in (once, twice):
        r = client.get(f"/v1/suppliers/{old}-acme")
        assert r.status_code == 200 and (r.json()["id"], r.json()["slug"]) == (page["id"], page["slug"])
    assert client.get(f"/v1/suppliers/{alone}-other-sl").json()["id"] == str(alone)


def test_a_merged_organisation_answers_its_head_through_a_chain(conn, client, world):  # noqa: F811
    older = org(conn, "bravo oldest name", "FR")
    _chain(conn, world.B2, older)            # older -> B2 -> B
    live = client.get(f"/v1/organisations/{world.B}-x").json()
    got = client.get(f"/v1/organisations/{older}-bravo-oldest-name").json()
    assert (got["id"], got["slug"]) == (str(world.B), live["slug"])
    assert client.get(f"/v1/organisations/{world.A}-x").json()["id"] == str(world.A)


# ------------------------------------------------------------------ the same notice under two rows

def _pl(conn, native: str, buyer: int, name: str, source: str) -> None:
    conn.execute(
        """INSERT INTO opportunity (source_id, native_id, buyer_org_id, buyer_name_raw, country, title_original, is_defence)
           VALUES ((SELECT id FROM source WHERE code = %s), %s, %s, %s, 'PL', 'Dostawa', true)""",
        (source, native, buyer, name))


def test_two_rows_holding_the_same_notice_become_a_candidate_never_a_merge(conn):
    mirror, bulletin = org(conn, "zaklad karny we wronkach", "PL"), org(conn, "zaklad karny we wronki", "PL")
    unit, parent = org(conn, "komenda powiatowa psp", "PL"), org(conn, "komenda wojewodzka psp", "PL")
    fam_a, fam_b = org(conn, "gmina x", "PL"), org(conn, "urzad gminy x", "PL")
    for n in ("2025/BZP 00224230", "2025/BZP 00279322"):
        _pl(conn, n, mirror, "Zakład Karny we Wronkach", "pl_atlas")
        _pl(conn, n, bulletin, "Zakład Karny we WRONKACH", "pl_ezam")
    _pl(conn, "2025/BZP 1", unit, "Komenda Powiatowa PSP", "pl_atlas")       # the names differ: not written
    _pl(conn, "2025/BZP 1", parent, "Komenda Wojewódzka PSP", "pl_ezam")
    _pl(conn, "2025/BZP 2", fam_a, "Gmina X", "pl_atlas")                    # one buyer family already: left out
    _pl(conn, "2025/BZP 2", fam_b, "Gmina X", "pl_ezam")
    conn.execute("INSERT INTO buyer_family_member (org_id, head_org_id, method, confidence) VALUES (%s, %s, 'test', 0.9)",
                 (fam_b, fam_a))
    conn.commit()

    assert shared_notice_candidates.run(conn, **QUIET) == {"pairs": 1, "written": 0}
    assert conn.execute("SELECT count(*) AS n FROM organisation_merge_candidate").fetchone()["n"] == 0
    assert shared_notice_candidates.run(conn, apply=True, **QUIET) == {"pairs": 1, "written": 1}
    shared_notice_candidates.run(conn, apply=True, **QUIET)                  # again: the pair is left as it is
    c = conn.execute("SELECT * FROM organisation_merge_candidate").fetchall()
    assert len(c) == 1
    c = c[0]
    assert (c["organisation_id"], c["candidate_org_id"], c["match_method"], float(c["confidence"]), c["status"]) == \
        (mirror, bulletin, "same_notice_number", 0.95, "pending")
    assert "2025/BZP 00224230" in c["evidence"] and "Zakład Karny we Wronkach" in c["evidence"]
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE merged_into IS NOT NULL").fetchone()["n"] == 0
