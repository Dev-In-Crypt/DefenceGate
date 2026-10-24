"""WP-104 (persona round of 24 October 2026): entities on a real Postgres. The twin rule's wrong family (/buyers/9770, the
Polish cyberspace centre carrying the Ministry of National Defence) undone by the family run itself; supplier merges
under the owner's rule with method, confidence and an undo that puts back the merges and the country corrections; the
group total of a curated company group; one name per buyer in the demand answer."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, stats
from dgate.normalise import Opportunity
from dgate.ops import buyer_families, company_groups, supplier_dedupe

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


def notice(conn, native_id: str, buyer: str, *, country: str = "PL", source: str = "ted", ted_ref: str | None = None,
           twin_method: str | None = None) -> int:
    opp = Opportunity(source_code=source, native_id=native_id, buyer_name_raw=buyer, title_original=f"Notice {native_id}",
                      title_en=f"Notice {native_id}", country=country, published_at=date.today() - timedelta(days=10),
                      deadline_at=FUTURE, cpv_codes=["35400000"], status="open", is_defence=True, sig_cpv=True,
                      sig_cpv_military=True, sig_buyer=False, dual_use=False, buyer_class="defence", ted_ref=ted_ref)
    src = db.source_id(conn, source)
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{source}-{native_id}", src)
    if twin_method:
        conn.execute("UPDATE opportunity SET twin_method = %s WHERE id = %s", (twin_method, oid))
    conn.commit()
    return oid


def buyer_of(conn, opp: int) -> int:
    return conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s", (opp,)).fetchone()["buyer_org_id"]


# ------------------------------------------------------------------ 1. /buyers/9770

def test_the_ministry_is_taken_out_of_its_cyberspace_centres_family(conn, client):
    czc = "Centrum Zasobów Cyberprzestrzeni Sił Zbrojnych"
    mon = "Ministerstwo Obrony Narodowej"
    centre = buyer_of(conn, notice(conn, "1-2026", czc))
    ministry = buyer_of(conn, notice(conn, "2-2026", mon))
    for i in range(3, 6):                                  # the ministry's own TED notices and their national copies
        notice(conn, f"{i}-2026", mon)
        notice(conn, f"TED-{i}-2026", mon, source="pl_atlas", ted_ref=f"{i}-2026", twin_method="stated_ted_ref")
    for i in range(6, 8):                                  # the centre's TED notices, named after the ministry nationally
        notice(conn, f"{i}-2026", czc)
        notice(conn, f"TED-{i}-2026", mon, source="pl_atlas", ted_ref=f"{i}-2026", twin_method="stated_ted_ref")
    # what production holds since 23 October: the ministry a twin member of the centre's family
    conn.execute("""INSERT INTO buyer_family_member (org_id, head_org_id, method, confidence)
                    VALUES (%s, %s, 'twin_notice', 0.85)""", (ministry, centre))
    conn.commit()
    before = client.get(f"/v1/buyers/{centre}").json()
    lines: list[str] = []
    report = buyer_families.run(conn, out=lines.append)
    assert report["removed"] == 1 and report["written"] == 0
    assert lines == [f"  remove {ministry:>7} -> {centre:>7} twin_notice 0.85"]
    assert conn.execute("SELECT count(*) AS n FROM buyer_family_member").fetchone()["n"] == 1    # report only
    buyer_families.run(conn, write=True)
    assert conn.execute("SELECT count(*) AS n FROM buyer_family_member").fetchone()["n"] == 0
    stats.reset_cache()
    after = client.get(f"/v1/buyers/{centre}").json()
    assert after["openCount"] < before["openCount"] and after["openCount"] == 3          # its own notices only
    assert buyer_families.run(conn, write=True)["written"] == 0                            # the daily job keeps it


# ------------------------------------------------------------------ 2. supplier merges

def winner(conn, opp: int, name: str, country: str, ident: str | None = None, value: float | None = None) -> int:
    org = conn.execute("INSERT INTO organisation (canonical_name, display_name, country) VALUES (%s, %s, %s) RETURNING id",
                       (name.lower(), name, country)).fetchone()["id"]
    conn.execute("""INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated,
                                       identifier_as_stated, winners_in_notice, cpv_main, resolution_method,
                                       resolution_confidence, value_amount, value_currency, value_kind)
                    VALUES (%s, %s, %s, %s, %s, 1, '35400000', 'exact_name', 1.0, %s, %s, %s)""",
                 (opp, org, country, name, ident, value, "EUR" if value else None, "contract" if value else None))
    conn.commit()
    return org


def test_shared_numbers_merge_across_a_conflict_and_a_wrong_country_with_undo(conn):
    hk = [winner(conn, notice(conn, f"{i}-2026", "BAAINBw", country="DE"), n, "DE", ident)
          for i, (n, ident) in enumerate([("Heckler & Koch GmbH", "HRB481250"), ("Heckler & Koch GmbH", "N0047964B"),
                                          ("Heckler & Koch GmbH", "N0047964B"), ("Heckler und Koch", "N0047964B"),
                                          ("HECKLER AND KOCH GMBH.", "DE0000CGC00430")], start=10)]
    conn.execute("UPDATE award SET identifier_as_stated = 'HRB481250' WHERE organisation_id = %s", (hk[0],))
    # the first row also states the Spanish number in a second notice
    conn.execute("""INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated, identifier_as_stated,
                                       winners_in_notice, cpv_main, resolution_method, resolution_confidence)
                    VALUES (%s, %s, 'DE', 'Heckler & Koch GmbH', 'N0047964B', 1, '35400000', 'alias', 0.9)""",
                 (notice(conn, "20-2026", "BAAINBw", country="DE"), hk[0]))
    pil = winner(conn, notice(conn, "30-2026", "armasuisse", country="CH"), "Pilatus Aircraft Ltd", "CH", "15030004652")
    for i in (31, 32):
        notice_id = notice(conn, f"{i}-2026", "armasuisse", country="CH")
        conn.execute("""INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated,
                                           winners_in_notice, cpv_main, resolution_method, resolution_confidence)
                        VALUES (%s, %s, 'CH', 'Pilatus Aircraft Ltd', 1, '35400000', 'alias', 0.9)""", (notice_id, pil))
    pil_bg = winner(conn, notice(conn, "33-2026", "Ministry of Defence", country="BG"), "PILATUS AIRCRAFT LIMITED", "BG",
                    "15030004652")
    conn.commit()
    lines: list[str] = []
    report = supplier_dedupe.run(conn, out=lines.append)
    assert report["merged"] == 0 and report["rows_to_merge"] == 4
    assert f"  pair {hk[0]} <- {hk[1]} company_number 0.97" in lines and f"  pair {pil} <- {pil_bg} company_number 0.97" in lines
    done = supplier_dedupe.run(conn, apply=True, out=lines.append)
    assert done["merged"] == 4 and done["recountried"] == 1
    rows = {r["id"]: r for r in conn.execute(
        "SELECT id, merged_into, merge_method, merge_confidence, country FROM organisation WHERE id = ANY(%s)",
        (hk + [pil, pil_bg],)).fetchall()}
    assert {i for i in rows if rows[i]["merged_into"] == hk[0]} == set(hk[1:4]) and rows[hk[4]]["merged_into"] is None
    assert rows[pil_bg]["merged_into"] == pil and rows[pil_bg]["country"].strip() == "BG"       # the row keeps its country
    assert conn.execute("SELECT supplier_country FROM award WHERE organisation_id = %s",
                        (pil_bg,)).fetchone()["supplier_country"] == "CH"                      # its award rows move
    fix = conn.execute("SELECT old_country, new_country, basis FROM organisation_country_fix WHERE org_id = %s",
                       (pil_bg,)).fetchone()
    assert (fix["old_country"], fix["new_country"], fix["basis"]) == ("BG", "CH", "company_number_twin")
    assert supplier_dedupe.run(conn, out=lines.append)["groups"] == 0                         # idempotent
    start, end = done["batch_window"]
    supplier_dedupe.undo_batch(conn, start, end, apply=True, out=lines.append)
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE merged_into IS NOT NULL").fetchone()["n"] == 0
    assert conn.execute("SELECT supplier_country FROM award WHERE organisation_id = %s",
                        (pil_bg,)).fetchone()["supplier_country"] == "BG"


# ------------------------------------------------------------------ 3. group totals

def test_a_company_group_shows_its_total_per_currency(conn, client):
    leo = winner(conn, notice(conn, "40-2026", "NAVARM", country="IT"), "Leonardo S.p.A.", "IT", value=3_000_000.0)
    winner(conn, notice(conn, "41-2026", "Armament Agency", country="PL"), "Leonardo PZL-Swidnik S.A.", "PL", value=2_000_000.0)
    winner(conn, notice(conn, "42-2026", "NAVARM", country="IT"), "Fincantieri S.p.A.", "IT", value=9_000_000.0)
    company_groups.run(conn, write=True, out=lambda _: None)
    got = client.get("/v1/suppliers", params={"group": "leonardo"}).json()
    assert {i["name"] for i in got["items"]} == {"Leonardo S.p.A.", "Leonardo PZL-Swidnik S.A."}
    assert got["groupTotals"] == [{"currency": "EUR", "amount": 5_000_000.0, "count": 2, "lotEstimates": 0}]
    assert client.get("/v1/suppliers").json()["groupTotals"] is None
    assert leo


# ------------------------------------------------------------------ 4. one name per buyer in the demand answer

def test_a_buyer_is_named_alike_in_every_winners_lines(conn, monkeypatch):
    jw = conn.execute("INSERT INTO organisation (canonical_name, country, is_defence_buyer) VALUES "
                      "('jednostka wojskowa 4724', 'PL', true) RETURNING id").fetchone()["id"]
    a = conn.execute("INSERT INTO organisation (canonical_name, country) VALUES ('works 11', 'PL') RETURNING id").fetchone()["id"]
    b = conn.execute("INSERT INTO organisation (canonical_name, country) VALUES ('mesko', 'PL') RETURNING id").fetchone()["id"]
    for i, (raw, org, name) in enumerate([("Jednostka Wojskowa 4724", a, "Works 11 Sp. z o.o.")] * 3
                                          + [("Skarb Państwa - Jednostka Wojskowa 4724", b, "Mesko S.A.")] * 2):
        opp = conn.execute(
            """INSERT INTO opportunity (source_id, native_id, buyer_org_id, buyer_name_raw, country, title_original,
                                        published_at, cpv_codes, is_defence, sig_legal_basis, buyer_class)
               VALUES ((SELECT id FROM source WHERE code = 'ted'), %s, %s, %s, 'PL', 'Amunicja', %s, ARRAY['35330000'],
                       true, true, 'defence') RETURNING id""",
            (f"{50 + i}-2026", jw, raw, date.today() - timedelta(days=30))).fetchone()["id"]
        conn.execute("""INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated, winners_in_notice,
                                           cpv_main, resolution_method, resolution_confidence)
                        VALUES (%s, %s, 'PL', %s, 1, '35330000', 'exact_name', 1.0)""", (opp, org, name))
    conn.commit()
    monkeypatch.setenv("DGATE_PLACSP_AWARDS_PUBLIC", "true")
    config.reset_cache()
    r = TestClient(api.app).post("/v1/readiness/demand", json={"cpv": ["35330000"], "countries": ["PL"]})
    assert r.status_code == 200, r.text
    names = {b["name"] for w in r.json()["approach"]["winners"] for b in w["buyers"]}
    assert names == {"Jednostka Wojskowa 4724"}
