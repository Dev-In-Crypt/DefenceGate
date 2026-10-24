"""WP-111 (round-4 re-check of 24 October 2026) on a real Postgres: a buyer family merged after the worker stored the buyer
aggregate is counted whole on the list and on its page, with its newest publication; the family run renews the aggregate;
a defence member flags the family; the page names the variants; a supplier page names its namesakes and their numbers; a
planned national notice is tied to its planned TED twin."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from dgate import api, db, stats, tenders
from dgate.listcache import stored
from dgate.normalise import Opportunity
from dgate.ops import buyer_families, link_twins

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def notice(conn, native_id: str, buyer: str, *, country: str = "IT", source: str = "ted", published: date | None = None,
           status: str = "open", cpv: tuple[str, ...] = ("35400000",)) -> int:
    planned = status == "forthcoming"
    opp = Opportunity(source_code=source, native_id=native_id, buyer_name_raw=buyer, title_original=f"Notice {native_id}",
                      title_en=f"Notice {native_id}", country=country,
                      published_at=published or date.today() - timedelta(days=10),
                      deadline_at=None if planned else FUTURE, cpv_codes=list(cpv), status=status, is_defence=True,
                      sig_cpv=True, sig_cpv_military=True, sig_buyer=False, dual_use=False, buyer_class="defence")
    src = db.source_id(conn, source)
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{source}-{native_id}", src)
    conn.commit()
    return oid


def buyer_of(conn, opp: int) -> int:
    return conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s", (opp,)).fetchone()["buyer_org_id"]


def store_base(conn) -> None:
    """What the worker stores (`ops.warm_lists`): the exact aggregate."""
    conn.execute("INSERT INTO list_snapshot (key, body, computed_at) VALUES (%s, %s, now()) "
                 "ON CONFLICT (key) DO UPDATE SET body = EXCLUDED.body, computed_at = EXCLUDED.computed_at",
                 (tenders.BUYER_BASE_KEY, Jsonb(stored(jsonable_encoder(tenders.compute_buyer_base(conn, exact=True))))))
    conn.commit()


def test_a_family_merged_after_the_stored_aggregate_is_counted_whole_with_its_newest_notice(conn, client):
    head = buyer_of(conn, notice(conn, "1-2023", "Direzione Armamenti Terrestri", published=date(2024, 1, 31)))
    member = buyer_of(conn, notice(conn, "2-2026", "Ministero della Difesa - Direzione degli Armamenti Terrestri",
                                   published=date(2026, 9, 1)))
    notice(conn, "3-2026", "Ministero della Difesa - Direzione degli Armamenti Terrestri", published=date(2026, 9, 2))
    conn.execute("UPDATE organisation SET is_defence_buyer = TRUE WHERE id = %s", (member,))   # only the member is flagged
    store_base(conn)                                     # the worker's run, before the merge
    conn.execute("INSERT INTO buyer_family_member (org_id, head_org_id, method, confidence) VALUES (%s, %s, 'rule:x', 0.9)",
                 (member, head))
    conn.commit()
    stats.reset_cache()
    listed = {b["id"]: b for b in client.get("/v1/buyers").json()["items"]}
    page = client.get(f"/v1/buyers/{head}").json()
    profile = client.get(f"/v1/buyers/{head}/profile").json()
    assert str(member) not in listed                                          # shown under its head only
    assert listed[str(head)]["tenderCount"] == page["tenderCount"] == profile["tenderCount"] == 3
    assert listed[str(head)]["lastPublishedAt"].startswith("2026-09-02") and page["lastPublishedAt"].startswith("2026-09-02")
    assert listed[str(head)]["openCount"] == page["openCount"] == 3
    assert listed[str(head)]["nameVariants"] == page["nameVariants"] == 1
    assert listed[str(head)]["isDefenceBuyer"] and page["isDefenceBuyer"]   # the family is a defence body (p04)
    assert page["variantNames"] == ["Ministero della Difesa - Direzione degli Armamenti Terrestri"]


def test_the_family_run_renews_the_stored_aggregate_when_it_writes(conn):
    notice(conn, "1-2026", "Agenzia Industrie Difesa")
    notice(conn, "2-2026", "Ministero della Difesa - Agenzia Industrie Difesa")
    conn.execute("INSERT INTO list_snapshot (key, body, computed_at) VALUES (%s, %s, now() - interval '3 hours')",
                 (tenders.BUYER_BASE_KEY, Jsonb(stored([[], [], [], [], []]))))
    conn.commit()
    lines: list[str] = []
    assert buyer_families.run(conn, out=lines.append)["written"] == 1 and len(lines) == 1          # report: nothing written
    assert conn.execute("SELECT computed_at > now() - interval '1 minute' AS fresh FROM list_snapshot WHERE key = %s",
                        (tenders.BUYER_BASE_KEY,)).fetchone()["fresh"] is False
    assert buyer_families.run(conn, write=True, refresh=True)["written"] == 1
    row = conn.execute("SELECT computed_at > now() - interval '1 minute' AS fresh, body FROM list_snapshot WHERE key = %s",
                       (tenders.BUYER_BASE_KEY,)).fetchone()
    assert row["fresh"] is True


def winner(conn, opp: int, name: str, country: str, reg: str | None) -> int:
    org = conn.execute("INSERT INTO organisation (canonical_name, display_name, country, national_reg_no) "
                       "VALUES (%s, %s, %s, %s) RETURNING id", ("rheinmetall electronics", name, country, reg)).fetchone()["id"]
    conn.execute("""INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated,
                                       identifier_as_stated, winners_in_notice, cpv_main, resolution_method,
                                       resolution_confidence)
                    VALUES (%s, %s, %s, %s, %s, 1, '35400000', 'exact_name', 1.0)""", (opp, org, country, name, reg))
    conn.commit()
    return org


def test_a_supplier_page_names_its_namesakes_and_the_numbers_that_keep_them_apart(conn, client):
    rows = [winner(conn, notice(conn, f"{i}-2026", "BAAINBw", country="DE", status="awarded"), "Rheinmetall Electronics GmbH",
                   "DE", reg) for i, reg in ((10, "811127845"), (11, "119356818"), (12, "251121155"))]
    got = client.get(f"/v1/suppliers/{rows[0]}").json()
    assert got["ownNumbers"] == ["811127845"]
    assert [(n["slug"].split("-")[0], n["identifiers"], n["awards"]) for n in got["namesakes"]] == [
        (str(rows[1]), ["119356818"], 1), (str(rows[2]), ["251121155"], 1)]


def test_a_planned_national_notice_is_tied_to_its_planned_ted_twin(conn, client):
    ted = notice(conn, "448143-2026", "BAAINBw", country="DE", status="forthcoming", published=date(2026, 6, 30),
                 cpv=("75000000",))
    bkms = notice(conn, "40e33917", "BAAINBw", country="DE", source="de_bkms", status="forthcoming",
                  published=date(2026, 6, 26), cpv=("75000000",))
    notice(conn, "449000-2026", "BAAINBw", country="DE", status="forthcoming", published=date(2026, 6, 27),
           cpv=("35000000",))                                                   # another planned TED notice, other codes
    assert link_twins.run(conn, methods=("heuristic",))["heuristic"] == 1    # dry run
    link_twins.run(conn, write=True, methods=("heuristic",))
    row = conn.execute("SELECT ted_ref, twin_method, twin_confidence FROM opportunity WHERE id = %s", (bkms,)).fetchone()
    assert (row["ted_ref"], row["twin_method"], float(row["twin_confidence"])) == ("448143-2026", "heuristic", 0.8)
    buyer = buyer_of(conn, ted)
    planned = client.get("/v1/tenders", params={"buyer": buyer, "status": "planned", "scope": "all"}).json()
    assert planned["total"] == 2 and "40e33917" not in {t["noticeId"] for t in planned["items"]}, planned["items"]
