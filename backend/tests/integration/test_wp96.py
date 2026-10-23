"""WP-96 (persona round of 23 October 2026, A2): supplier duplicates and groups, buyer families, buyer counts in the list's
default scope, supplier countries, the calendar's notices without a deadline, the market's amendment share."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, db, stats
from dgate.normalise import Opportunity
from dgate.ops import buyer_families, company_groups, supplier_countries, supplier_dedupe

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


def notice(conn, native_id: str, buyer: str = "Bundesamt fuer Ausruestung", *, country: str = "DE", source: str = "ted",
           core: bool = True, status: str = "awarded", deadline: datetime | None = None, ted_ref: str | None = None,
           twin_method: str | None = None) -> int:
    """A defence notice: `core` (a military code from a defence body) or of the other scope (only the buyer is listed)."""
    opp = Opportunity(source_code=source, native_id=native_id, buyer_name_raw=buyer, title_original=f"Notice {native_id}",
                      title_en=f"Notice {native_id}", country=country, published_at=date.today() - timedelta(days=10),
                      deadline_at=deadline, cpv_codes=["35400000"] if core else ["60100000"], status=status,
                      is_defence=True, sig_cpv=core, sig_cpv_military=core, sig_buyer=not core, dual_use=False,
                      buyer_class="defence", ted_ref=ted_ref)
    src = db.source_id(conn, source)
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{source}-{native_id}", src)
    if twin_method:
        conn.execute("UPDATE opportunity SET twin_method = %s WHERE id = %s", (twin_method, oid))
    conn.commit()
    return oid


def winner(conn, opp: int, name: str, country: str, ident: str | None = None, reg: str | None = None) -> int:
    org = conn.execute("INSERT INTO organisation (canonical_name, display_name, country, national_reg_no) "
                       "VALUES (%s, %s, %s, %s) RETURNING id", (name.lower(), name, country, reg)).fetchone()["id"]
    conn.execute("""INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated,
                                       identifier_as_stated, winners_in_notice, cpv_main, resolution_method,
                                       resolution_confidence)
                    VALUES (%s, %s, %s, %s, %s, 1, '35400000', 'exact_name', 1.0)""", (opp, org, country, name, ident))
    conn.commit()
    return org


# ------------------------------------------------------------------ 1. supplier duplicates and groups

def test_supplier_duplicates_merge_with_method_and_confidence_and_undo(conn, client):
    saab_ab = winner(conn, notice(conn, "1-2026"), "Saab AB", "SE", reg="5560360793")
    saab_akt = winner(conn, notice(conn, "2-2026"), "SAAB Aktiebolag", "SE", ident="SE556036079301")
    re1 = winner(conn, notice(conn, "3-2026"), "Rheinmetall Electronics GmbH", "DE", ident="DE119356818")
    re2 = winner(conn, notice(conn, "4-2026"), "Rheinmetall Electronics GmbH", "DE", ident="DE251121155")
    land = winner(conn, notice(conn, "5-2026"), "Rheinmetall Landsysteme GmbH", "DE")
    land2 = winner(conn, notice(conn, "6-2026"), "Rheinmetall Land Systeme GmbH", "DE")
    leo = winner(conn, notice(conn, "7-2026"), "Leonardo", "IT", ident="00401990585")
    leo_spa = winner(conn, notice(conn, "8-2026"), "Leonardo S.p.A.", "IT", ident="00881841001")

    lines: list[str] = []
    report = supplier_dedupe.run(conn, out=lines.append)
    assert report["groups"] == 2 and report["merged"] == 0 and report["it_pairs_waiting"] == 1
    assert report["left"]["different_company_numbers"] == 2          # Rheinmetall Electronics, Leonardo
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE merged_into IS NOT NULL").fetchone()["n"] == 0

    done = supplier_dedupe.run(conn, apply=True, out=lines.append)
    assert done["merged"] == 2
    rows = {r["id"]: r for r in conn.execute(
        "SELECT id, merged_into, merge_method, merge_confidence FROM organisation WHERE id = ANY(%s)",
        ([saab_ab, saab_akt, land, land2, re1, re2, leo, leo_spa],)).fetchall()}
    merged = {i for i in rows if rows[i]["merged_into"]}
    assert len(merged & {saab_ab, saab_akt}) == 1 and len(merged & {land, land2}) == 1
    assert not merged & {re1, re2, leo, leo_spa}
    assert {(rows[i]["merge_method"], float(rows[i]["merge_confidence"])) for i in merged} == {
        ("company_number", 0.97), ("name_key_spaces", 0.90)}
    audit = conn.execute("SELECT count(*) AS n FROM organisation_merge_candidate WHERE detected_by = %s AND status = 'merged'",
                         (supplier_dedupe.DETECTED_BY,)).fetchone()["n"]
    assert audit == 2
    saab = client.get("/v1/suppliers", params={"q": "saab"}).json()
    assert saab["total"] == 1 and saab["items"][0]["awardCount"] == 2
    assert supplier_dedupe.run(conn, out=lines.append)["groups"] == 0        # idempotent

    start, end = done["batch_window"]
    supplier_dedupe.undo_batch(conn, start, end, apply=True, out=lines.append)
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE merged_into IS NOT NULL").fetchone()["n"] == 0


def test_italian_numbers_of_one_stated_name_merge(conn):
    leo = winner(conn, notice(conn, "1-2026"), "Leonardo", "IT", ident="00401990585")
    spa = winner(conn, notice(conn, "2-2026"), "Leonardo S.p.A.", "IT", ident="00881841001")
    # a notice states the one name with the codice fiscale, another the same name with the partita IVA
    for n, ident in (("3-2026", "00401990585"), ("4-2026", "00881841001")):
        conn.execute("""INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated,
                                           identifier_as_stated, winners_in_notice, cpv_main, resolution_method,
                                           resolution_confidence)
                        VALUES (%s, %s, 'IT', 'LEONARDO SPA', %s, 1, '35400000', 'exact_name', 1.0)""",
                     (notice(conn, n), leo if ident.startswith("004") else spa, ident))
    conn.commit()
    out = supplier_dedupe.run(conn, apply=True, out=lambda *_: None)
    assert out["by_method"] == {"it_tax_pair": 1} and out["merged"] == 1


def test_curated_groups_are_listed_with_their_source_and_found_by_the_group_name(conn, client):
    mesko = winner(conn, notice(conn, "1-2026", country="PL"), "Mesko S.A.", "PL")
    winner(conn, notice(conn, "2-2026", country="PL"), "Huta Stalowa Wola S.A.", "PL")
    winner(conn, notice(conn, "3-2026", country="PL"), "WB Electronics S.A.", "PL")
    rhm = winner(conn, notice(conn, "4-2026"), "Rheinmetall Electronics GmbH", "DE")
    lines: list[str] = []
    assert company_groups.run(conn, out=lines.append)["to_write"] == 3
    assert conn.execute("SELECT count(*) AS n FROM company_group_member").fetchone()["n"] == 0     # report only
    assert company_groups.run(conn, write=True, out=lines.append)["written"] == 3
    row = conn.execute("SELECT method, confidence, evidence FROM company_group_member WHERE org_id = %s",
                       (mesko,)).fetchone()
    assert row["method"] == "curated_group" and float(row["confidence"]) == 0.90 and "pgzsa.pl" in row["evidence"]
    got = client.get("/v1/suppliers", params={"group": "pgz"}).json()
    assert {i["name"] for i in got["items"]} == {"Mesko S.A.", "Huta Stalowa Wola S.A."}
    assert {i["name"] for i in client.get("/v1/suppliers", params={"q": "Polska Grupa Zbrojeniowa"}).json()["items"]} == {
        "Mesko S.A.", "Huta Stalowa Wola S.A."}
    assert client.get("/v1/suppliers", params={"group": "nope"}).status_code == 422
    page = client.get(f"/v1/suppliers/{rhm}").json()
    assert page["group"]["key"] == "rheinmetall" and page["group"]["members"] == 1 and "rheinmetall.com" in page["group"]["source"]
    assert company_groups.run(conn, write=True, out=lines.append)["written"] == 0               # idempotent


# ------------------------------------------------------------------ 2. buyer families

def test_dutch_ministry_variants_and_a_twin_copy_are_one_buyer(conn, client):
    notice(conn, "100-2026", "Ministerie van Defensie", country="NL", status="open", deadline=FUTURE)
    notice(conn, "101-2026", "Defence Materiel Organisation (DMO)", country="NL", status="open", deadline=FUTURE)
    notice(conn, "146213-2026", "Ministry of Defence", country="NL", status="open", deadline=FUTURE)
    # a buyer row whose notice is the national copy of a TED notice of another row: the copy follows the twin
    notice(conn, "200-2026", "Rijksvastgoedbedrijf", country="NL", status="open", deadline=FUTURE)
    notice(conn, "TN-1", "RVB Defensie Vastgoed", country="NL", source="nl_tenderned", ted_ref="200-2026",
           twin_method="stated_ted_ref", status="open", deadline=FUTURE)
    counts = buyer_families.run(conn, write=True)
    assert counts["groups"] >= 2
    fam = {r["name"]: (r["head"], r["method"]) for r in conn.execute(
        """SELECT o.canonical_name AS name, m.head_org_id AS head, m.method FROM buyer_family_member m
             JOIN organisation o ON o.id = m.org_id""").fetchall()}
    heads = {h for h, _ in fam.values()}
    assert any(m == "twin_notice" for _, m in fam.values())
    nl = {b["name"]: b for b in client.get("/v1/buyers", params={"country": "NL"}).json()["items"]}
    mod = next(b for n, b in nl.items() if "efensie" in n or "efence" in n)
    assert len(nl) == 2 and mod["openCount"] == 3 and mod["nameVariants"] == 2
    assert len(heads) == 2
    assert fam["rvb defensie vastgoed"][1] == "twin_notice"


# ------------------------------------------------------------------ 3. buyer counts in the list's default scope

def test_a_buyer_counts_what_its_tender_list_shows(conn, client):
    notice(conn, "1-2026", "Ministerie van Defensie", country="NL", status="open", deadline=FUTURE)
    for i in range(2, 6):
        notice(conn, f"{i}-2026", "Ministerie van Defensie", country="NL", core=False, status="open", deadline=FUTURE)
    org = conn.execute("SELECT buyer_org_id FROM opportunity LIMIT 1").fetchone()["buyer_org_id"]
    b = client.get(f"/v1/buyers/{org}").json()
    listed = client.get("/v1/tenders", params={"buyer": org}).json()
    assert b["openCount"] == listed["total"] == 5 and b["openCoreCount"] == 1 and b["scope"] == "relevant"
    profile = client.get(f"/v1/buyers/{org}/profile").json()
    assert profile["tenderCount"] == 5 and profile["openNow"] == 5 and profile["scope"] == "relevant"
    # a buyer with only other purchases has a page and a row on the list now
    only = notice(conn, "9-2026", "Commando DienstenCentra", country="BE", core=False, status="open", deadline=FUTURE)
    only_org = conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s", (only,)).fetchone()["buyer_org_id"]
    assert client.get(f"/v1/buyers/{only_org}").json()["openCoreCount"] == 0


# ------------------------------------------------------------------ 4. supplier countries

def test_winner_countries_are_corrected_and_put_back(conn):
    fin = winner(conn, notice(conn, "1-2026"), "Saab Finland Oy", "SE")
    uk = winner(conn, notice(conn, "2-2026"), "BAE Systems plc", "UK")
    ok = winner(conn, notice(conn, "3-2026"), "Saab AB", "SE")
    lines: list[str] = []
    report = supplier_countries.run(conn, out=lines.append)
    assert report["to_correct"] == 2 and report["written"] == 0
    done = supplier_countries.run(conn, apply=True, out=lines.append)
    assert done["written"] == 2
    country = {r["id"]: r["country"].strip() for r in conn.execute(
        "SELECT id, country FROM organisation WHERE id = ANY(%s)", ([fin, uk, ok],)).fetchall()}
    assert country == {fin: "FI", uk: "GB", ok: "SE"}
    assert {r["supplier_country"] for r in conn.execute(
        "SELECT supplier_country FROM award WHERE organisation_id = %s", (fin,)).fetchall()} == {"FI"}
    fix = conn.execute("SELECT old_country, new_country, basis, award_rows FROM organisation_country_fix "
                       "WHERE org_id = %s", (fin,)).fetchone()
    assert (fix["old_country"], fix["new_country"], fix["basis"], fix["award_rows"]) == ("SE", "FI", "name", 1)
    assert supplier_countries.run(conn, out=lines.append)["to_correct"] == 0           # idempotent
    start, end = done["batch_window"]
    assert supplier_countries.undo(conn, start, end, apply=True, out=lines.append) == 2
    assert conn.execute("SELECT country FROM organisation WHERE id = %s", (fin,)).fetchone()["country"].strip() == "SE"


# ------------------------------------------------------------------ 7. numbers

def test_the_calendar_counts_the_open_tenders_without_a_deadline(conn, client):
    notice(conn, "1-2026", status="open", deadline=FUTURE)
    notice(conn, "2-2026", status="open", deadline=None)
    cal = client.get("/v1/tenders/calendar").json()
    assert cal["total"] == 1 and cal["withoutDeadline"] == 1
    assert client.get("/v1/tenders/calendar", params={"from": date.today().isoformat()}).json()["withoutDeadline"] == 0


def test_the_market_says_since_when_it_watched_the_amendments(conn, client):
    notice(conn, "1-2026", status="open", deadline=FUTURE)
    m = client.get("/v1/stats/market").json()
    assert m["amendments"]["observedFrom"] is not None and m["scope"] == "core"


# ------------------------------------------------------------------ the Latvian Interior agency (coordinator's item)

def test_only_the_person_rejected_flag_is_withdrawn(conn):
    from dgate.ops import buyer_cleanup

    nva = conn.execute("INSERT INTO organisation (canonical_name, country, is_defence_buyer, defence_buyer_source) "
                       "VALUES ('nodrosinajuma valsts agentura', 'LV', TRUE, 'seed') RETURNING id").fetchone()["id"]
    other = conn.execute("INSERT INTO organisation (canonical_name, country, is_defence_buyer, defence_buyer_source) "
                         "VALUES ('nodrosinajuma pavelnieciba', 'LV', TRUE, 'derived_rule') RETURNING id").fetchone()["id"]
    conn.commit()
    lines: list[str] = []
    assert buyer_cleanup.rejected_only(conn, out=lines.append) == 1
    assert conn.execute("SELECT is_defence_buyer FROM organisation WHERE id = %s", (nva,)).fetchone()["is_defence_buyer"]
    assert buyer_cleanup.rejected_only(conn, apply=True, out=lines.append) == 1
    flags = {r["id"]: r["is_defence_buyer"] for r in conn.execute(
        "SELECT id, is_defence_buyer FROM organisation WHERE id = ANY(%s)", ([nva, other],)).fetchall()}
    assert flags == {nva: False, other: True}
