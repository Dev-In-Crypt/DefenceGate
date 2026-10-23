"""WP-87 (UX audit of 22 October 2026, section 2: correctness and trust), against a real Postgres.

1. number pairs that agree: the calendar holds what the list counts, a buyer's profile is in the list's unit, a supplier's
   rows are its contracts; 2. the calendar and the changes take the list's filters and refuse what they do not read;
3. an open notice is never a "Closed" card; 4. the default views lead with core defence and defence calls;
6. a contract value under 1,000 is in no sum; 9. renamed bodies and supplier duplicates."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, stats
from dgate import weekly_digest as W
from dgate.normalise import Call, Opportunity
from dgate.ops import buyer_families, curated_renames, org_dedupe
from tests.integration.test_changes import opp, store
from tests.integration.test_supplier_map import FakeTed, rec

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)
FUTURE = NOW + timedelta(days=30)
PAST = NOW - timedelta(days=30)


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


@pytest.fixture()
def env(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path
    config.reset_cache()


def put(conn, native_id: str, *, status: str = "open", deadline=FUTURE, tag: str = "a", cpv=None, **kw) -> int:
    o = replace(opp(native_id, deadline=deadline, **kw), status=status)
    if cpv:
        o = replace(o, cpv_codes=list(cpv))
    return store(conn, o, tag)


def get(client, path: str, **params) -> dict:
    r = client.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ======================================================================= 2. calendar and changes take the list's filters

def test_the_calendar_reads_the_lists_filters_and_holds_what_the_list_counts(client, conn):
    put(conn, "RADAR", cpv=("35720000",), title="Radar spares")
    put(conn, "TRUCK", cpv=("34100000",), title="Trucks", deadline=NOW + timedelta(days=10))
    put(conn, "TRUCK-BOAT", cpv=("34500000",), title="Boat trucks", kind="supply", deadline=NOW + timedelta(days=12))
    put(conn, "NO-DEADLINE", deadline=None)
    put(conn, "LONG", deadline=NOW + timedelta(days=4 * 365))
    for params in ({}, {"cpv": "34"}, {"q": "trucks"}, {"scope": "core"}, {"goods": "defence"},
                   {"cpv": "35", "country": "FR"}):
        cal = get(client, "/v1/tenders/calendar", **params)
        listed = get(client, "/v1/tenders", status="open", pageSize=250, **{"from": NOW.date().isoformat()}, **params)
        # the number pair of the audit: the calendar's tenders are the list's open tenders with a deadline ahead
        assert cal["total"] == listed["total"], params
        assert sorted(i["noticeId"] for i in cal["items"]) == sorted(t["noticeId"] for t in listed["items"]), params
    assert [i["noticeId"] for i in get(client, "/v1/tenders/calendar", cpv="34")["items"]] == ["TRUCK", "TRUCK-BOAT"]
    assert [i["noticeId"] for i in get(client, "/v1/tenders/calendar", q="radar")["items"]] == ["RADAR"]
    long = [i for i in get(client, "/v1/tenders/calendar")["items"] if i["noticeId"] == "LONG"][0]
    assert "deadline-more-than-3y" in long["anomalies"]          # the site leaves it off the calendar and says so


def test_an_unknown_parameter_is_refused_not_ignored(client, conn):
    put(conn, "A")
    for path in ("/v1/tenders/calendar", "/v1/changes"):
        r = client.get(path, params={"cpvv": "35"})
        assert r.status_code == 422, path
        assert "cpvv" not in r.text and "this endpoint takes" in r.text      # names what it takes, never what was sent
    assert client.get("/v1/changes", params={"cpv": "35"}).status_code == 200


def test_the_changes_read_the_lists_filters(client, conn):
    store(conn, opp("C-RADAR", title="Radar spares"))
    store(conn, replace(opp("C-TRUCK", title="Trucks", value=50_000), cpv_codes=["34100000"]))
    all_ = get(client, "/v1/changes")
    assert all_["total"] == 2
    trucks = get(client, "/v1/changes", cpv="34")
    assert [c["tender"]["noticeId"] for c in trucks["items"]] == ["C-TRUCK"]
    assert trucks["total"] == 1 and trucks["counts"] == {"new": 1, "amended": 0, "awards": 0}
    assert [c["tender"]["noticeId"] for c in get(client, "/v1/changes", q="radar")["items"]] == ["C-RADAR"]
    assert get(client, "/v1/changes", min="10000", currency="EUR")["total"] == 1
    assert get(client, "/v1/changes", **{"from": (NOW + timedelta(days=60)).date().isoformat()})["total"] == 0
    # a funding call has no CPV code: with a tender filter, no funding part rather than an unfiltered one
    call = Call(programme_code="EDF", native_id="F-1", title="Drones call", topic_code="EDF-F-1",
                deadline_at=FUTURE, status="open", regime="defence")
    db.upsert_call(conn, call, "hash-f1", db.source_id(conn, "eu_portal"))
    conn.commit()
    assert get(client, "/v1/changes")["fundingTotal"] == 1
    assert get(client, "/v1/changes", cpv="34")["fundingTotal"] == 0


# ======================================================================= 3. open is never a "Closed" card

def test_a_dynamic_purchasing_system_past_its_first_deadline_is_open_and_says_so(client, conn):
    put(conn, "TED-DPS", source="ted", country="ES", deadline=PAST)
    oid = put(conn, "ES-DPS", source="es_placsp", country="ES", deadline=NOW + timedelta(days=400), ted_ref="TED-DPS",
              title="Sistema dinamico de adquisicion de repuestos")
    listed = get(client, "/v1/tenders", status="open", scope="all", country="ES")
    assert [t["noticeId"] for t in listed["items"]] == ["ES-DPS"]
    card = listed["items"][0]
    # the card keeps the notice's own deadline, so it reads open, not "Closed" beside the Open filter
    assert card["status"] == "open" and card["statusNative"] == "open" and card["deadlineFrom"] is None
    assert datetime.fromisoformat(card["deadline"]) > NOW and "first-deadline-passed" in card["anomalies"]
    page = get(client, f"/v1/tenders/{oid}")
    assert page["deadline"] == card["deadline"] and "first-deadline-passed" in page["anomalies"]
    cal = [i for i in get(client, "/v1/tenders/calendar", scope="all", country="ES")["items"] if i["noticeId"] == "ES-DPS"]
    assert cal and cal[0]["deadline"] == card["deadline"] and "first-deadline-passed" in cal[0]["anomalies"]
    # a TED twin's deadline still ahead keeps the typo rule (the twin's is shown)
    put(conn, "TED-2", source="ted", country="FR", deadline=NOW + timedelta(days=20))
    put(conn, "ES-2", source="es_placsp", country="ES", deadline=NOW + timedelta(days=400), ted_ref="TED-2")
    es2 = [t for t in get(client, "/v1/tenders", scope="all", country="ES")["items"] if t["noticeId"] == "ES-2"][0]
    assert es2["deadlineFrom"] == "ted_twin" and "first-deadline-passed" not in es2["anomalies"]


# ======================================================================= 4. the default views lead with core defence

def test_the_default_tender_list_leads_with_core_notices_and_counts_the_same(client, conn):
    put(conn, "SUPPLY-SOON", kind="supply", deadline=NOW + timedelta(days=2), title="Musical instruments")
    put(conn, "CORE-LATER", deadline=NOW + timedelta(days=20))
    put(conn, "CORE-SOON", deadline=NOW + timedelta(days=5))
    default = get(client, "/v1/tenders")
    assert [t["noticeId"] for t in default["items"]] == ["CORE-SOON", "CORE-LATER", "SUPPLY-SOON"]
    assert get(client, "/v1/tenders", sort="core-first")["items"] == default["items"]
    plain = get(client, "/v1/tenders", sort="deadline-asc")
    assert [t["noticeId"] for t in plain["items"]] == ["SUPPLY-SOON", "CORE-SOON", "CORE-LATER"]
    assert default["total"] == plain["total"] == 3
    # a page at a time, across the two parts
    pages = [t["noticeId"] for p in (1, 2, 3) for t in get(client, "/v1/tenders", pageSize=1, page=p)["items"]]
    assert pages == ["CORE-SOON", "CORE-LATER", "SUPPLY-SOON"]
    assert get(client, "/v1/tenders", pageSize=1, page=3)["total"] == 3


def _call(conn, native_id: str, regime: str, days: int) -> None:
    db.upsert_call(conn, Call(programme_code="HORIZON", native_id=native_id, title=f"Call {native_id}",
                              topic_code=f"HORIZON-{native_id}", deadline_at=NOW + timedelta(days=days),
                              status="open", regime=regime), f"hash-{native_id}", db.source_id(conn, "eu_portal"))
    conn.commit()


def test_the_funding_list_and_the_digest_list_defence_calls_first(client, conn):
    _call(conn, "DUAL-SOON", "dual_use", 3)
    _call(conn, "DEF-LATER", "defence", 30)
    _call(conn, "DEF-SOON", "defence", 10)
    regimes = [c["regime"] for c in get(client, "/v1/funding")["items"]]
    assert regimes == ["defence", "defence", "dual-use"]
    asked = [c["regime"] for c in get(client, "/v1/funding", sort="deadline-asc")["items"]]
    assert asked == ["dual-use", "defence", "defence"]                     # a sort asked for is honoured as it is
    assert get(client, "/v1/funding")["total"] == 3
    # the week the calls were first collected in: all three are its new calls, the defence ones first
    issue = W.build_all(conn, W.week_id(NOW.date()), now=NOW, only=[])[""]
    assert [c["regime"] for c in issue["callsNew"]] == ["defence", "defence", "dual-use"]


# ======================================================================= 1. a buyer's figures in one unit

def test_a_buyer_profile_counts_what_its_list_shows_and_its_years_add_up(client, conn):
    today = NOW.date()
    put(conn, "T-1", source="ted", country="PL", published=today, deadline=NOW + timedelta(days=20))
    put(conn, "PL-1", source="pl_ezam", country="PL", published=today, deadline=NOW + timedelta(days=20), ted_ref="T-1")
    put(conn, "T-2", source="ted", country="PL", published=date(today.year - 8, 5, 1), deadline=PAST, status="awarded")
    put(conn, "T-3", source="ted", country="PL", published=today, deadline=PAST, status="awarded")
    buyer = next(b for b in get(client, "/v1/buyers")["items"] if b["country"] == "PL")
    prof = get(client, f"/v1/buyers/{buyer['slug']}/profile")
    listed = get(client, "/v1/tenders", buyer=buyer["id"], status="all", scope="core")
    # the TED notice and its national copy are one: the profile's total is the list's, and the sources add up to it
    assert prof["tenderCount"] == listed["total"] == 3
    assert sum(s["count"] for s in prof["sources"]) == prof["tenderCount"]
    assert sum(y["count"] for y in prof["perYear"]) + prof["perYearEarlier"] + prof["perYearUndated"] == prof["tenderCount"]
    assert prof["perYearEarlier"] == 1
    assert prof["amendments"]["notices"] == 3 and prof["amendments"]["observedFrom"] is not None


def test_a_tender_links_its_buyers_family_head(client, conn):
    head = put(conn, "H-1", country="DE")
    member = put(conn, "M-1", country="DE")
    head_org = conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s", (head,)).fetchone()["buyer_org_id"]
    other = db.resolve_organisation(conn, "BAAINBw K2 4", "DE", src_id=db.source_id(conn, "ted"))
    conn.execute("UPDATE opportunity SET buyer_org_id = %s, buyer_name_raw = 'BAAINBw K2 4' WHERE id = %s", (other, member))
    conn.execute("INSERT INTO buyer_family_member (org_id, head_org_id, method, confidence) VALUES (%s, %s, 'rule:baainbw', 0.9)",
                 (other, head_org))
    conn.commit()
    card = [t for t in get(client, "/v1/tenders", scope="all")["items"] if t["noticeId"] == "M-1"][0]
    assert card["buyerSlug"].startswith(f"{head_org}-") and card["buyerName"] == "BAAINBw K2 4"


# ======================================================================= 1/6. a supplier's rows are its contracts

def _ted(conn, native_id: str, *, pid: str | None, buyer: str = "Ministerio de Defensa", value: float | None = None) -> int:
    o = Opportunity(source_code="ted", native_id=native_id, buyer_name_raw=buyer, title_original="Repuestos",
                    title_en="Spare parts", country="LT", published_at=date(2026, 3, 1), cpv_codes=["35400000"],
                    status="awarded", is_defence=True, sig_legal_basis=True, sig_cpv=True, notice_subtype="29",
                    procedure_identifier=pid, value_amount=value, value_currency="EUR" if value else None,
                    value_kind="total" if value else None, source_url=f"https://ted.example/{native_id}")
    src = db.source_id(conn, "ted")
    o.buyer_org_id = db.resolve_organisation(conn, buyer, "LT", src_id=src)
    oid, _ = db.upsert_opportunity(conn, o, f"hash-{native_id}", src)
    conn.commit()
    return oid


def test_one_contract_published_twice_is_one_row_and_a_unit_price_is_in_no_sum(conn, env, client, monkeypatch):
    _ted(conn, "474829-2024", pid="proc-lt-1")
    _ted(conn, "467138-2024", pid="proc-lt-1")
    _ted(conn, "1-2026", pid="proc-2", value=48)
    _ted(conn, "2-2026", pid="proc-3", value=250_000)
    who = ("Hensoldt Sensors GmbH", "DEU", "DE811222333")
    from dgate import awards
    awards.run_awards(client=FakeTed([rec(n, [who]) for n in ("474829-2024", "467138-2024", "1-2026", "2-2026")]).client(),
                      pause=0, sleep=lambda s: None)
    slug = get(client, "/v1/suppliers", q="hensoldt")["items"][0]["slug"]
    prof = get(client, f"/v1/suppliers/{slug}")
    assert prof["noticeCount"] == 3 and len(prof["notices"]) == 3        # 3 contracts, 3 rows (was 4 rows)
    twice = [n for n in prof["notices"] if n["alsoPublished"]]
    assert len(twice) == 1 and {twice[0]["noticeId"], twice[0]["alsoPublished"][0]["noticeId"]} == {"474829-2024", "467138-2024"}
    unit = [n for n in prof["notices"] if n["noticeId"] == "1-2026"][0]
    assert unit["valueAmount"] == 48.0 and unit["valueSuspect"] is True
    assert prof["values"]["byCurrency"] == [{"currency": "EUR", "amount": 250_000.0, "count": 1, "lotEstimates": 0}]
    assert prof["values"]["suspect"] == 1 and prof["values"]["withoutValue"] == 1
    # a PLACSP awarded amount of 300 is a contract total (a Spanish minor contract): summed, not flagged
    # WP-95: a TED row carries its notice's value too now, so the PLACSP amount is a PLACSP notice's
    conn.execute("UPDATE opportunity SET source_id = (SELECT id FROM source WHERE code = 'es_placsp') "
                 "WHERE native_id = '2-2026'")
    conn.execute("UPDATE award SET value_amount = 300, value_currency = 'EUR', value_kind = 'contract' WHERE opportunity_id = "
                 "(SELECT id FROM opportunity WHERE native_id = '2-2026')")
    conn.commit()
    monkeypatch.setenv("DGATE_PLACSP_AWARDS_PUBLIC", "true")      # the PLACSP winners on the map
    from dgate import config
    config.reset_cache()
    again = get(client, f"/v1/suppliers/{slug}")
    placsp = [n for n in again["notices"] if n["noticeId"] == "2-2026"][0]
    assert placsp["valueAmount"] == 300.0 and placsp["valueSuspect"] is False
    assert again["values"]["byCurrency"] == [{"currency": "EUR", "amount": 300.0, "count": 1, "lotEstimates": 0}]
    assert again["values"]["suspect"] == 1                    # the TED-stated EUR 48 still is
    # the buyer table is per buyer family: two rows of one body are one line
    assert len(prof["buyers"]) == 1 and prof["buyers"][0]["awards"] == 3


# ======================================================================= 9. renamed bodies and duplicates

def test_a_renamed_buyer_joins_its_successors_family_with_its_method(conn):
    src = db.source_id(conn, "ted")
    o_old = db.resolve_organisation(conn, "Skarb Panstwa - Inspektorat Uzbrojenia", "PL", src_id=src)
    o_new = db.resolve_organisation(conn, "Agencja Uzbrojenia", "PL", src_id=src)
    for native_id, org in (("IU-1", o_old), ("IU-2", o_old), ("AU-1", o_new)):
        store(conn, replace(opp(native_id, country="PL"), buyer_name_raw="x"), "a")
        conn.execute("UPDATE opportunity SET buyer_org_id = %s WHERE native_id = %s", (org, native_id))
    conn.commit()
    lines: list[str] = []
    dry = curated_renames.run(conn, apply=False, out=lines.append)
    assert dry["buyer_rows"] == 1 and conn.execute("SELECT count(*) AS n FROM buyer_family_member").fetchone()["n"] == 0
    assert any("inspektorat" in line for line in lines)
    curated_renames.run(conn, apply=True, out=lines.append)
    row = conn.execute("SELECT head_org_id, method, confidence FROM buyer_family_member WHERE org_id = %s", (o_old,)).fetchone()
    # the successor heads the family although the predecessor has more notices; method and confidence are stored
    assert (row["head_org_id"], row["method"], float(row["confidence"])) == (o_new, "curated_rename", 0.95)
    assert buyer_families.run(conn, write=True)["written"] == 0              # the daily job keeps it


def _org(conn, name: str, country: str = "PL", **cols) -> int:
    oid = conn.execute("INSERT INTO organisation (canonical_name, display_name, country) VALUES (%s, %s, %s) RETURNING id",
                       (name.lower(), name, country)).fetchone()["id"]
    for k, v in cols.items():
        conn.execute(f"UPDATE organisation SET {k} = %s WHERE id = %s", (v, oid))
    conn.commit()
    return oid


def test_a_curated_organisation_rename_merges_with_its_method_and_refuses_two_numbers(conn):
    new = _org(conn, "Siec Badawcza Lukasiewicz - Instytut Lotnictwa", eu_pic="999111222")
    spaced = _org(conn, "SIEC BADAWCZA LUKASIEWICZ - INSTYTUTLOTNICTWA")
    old = _org(conn, "Instytut Lotnictwa")
    out: list[str] = []
    assert curated_renames.run(conn, apply=False, out=out.append)["org_rows_to_merge"] == 2
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE merged_into IS NOT NULL").fetchone()["n"] == 0
    curated_renames.run(conn, apply=True, out=out.append)
    rows = {r["id"]: r for r in conn.execute("SELECT id, merged_into, merge_method, merge_confidence FROM organisation").fetchall()}
    for oid in (spaced, old):
        assert rows[oid]["merged_into"] == new and rows[oid]["merge_method"] == "curated_rename"
        assert float(rows[oid]["merge_confidence"]) == 0.95
    assert curated_renames.run(conn, apply=False, out=out.append)["org_rows_to_merge"] == 0      # idempotent


def test_a_curated_rename_with_two_pics_waits_for_a_person(conn):
    _org(conn, "Siec Badawcza Lukasiewicz - Instytut Lotnictwa", eu_pic="999111222")
    _org(conn, "Instytut Lotnictwa", eu_pic="999000111")
    out: list[str] = []
    got = curated_renames.run(conn, apply=True, out=out.append)
    assert got["org_refused"] == 1 and got["merged"] == 0 and any("two different PICs" in line for line in out)


def test_contract_winners_of_one_name_are_merged_and_public_winners_are_not(conn, env):
    a = _org(conn, "Hensoldt Optronics GmbH", "DE")
    b = _org(conn, "HENSOLDT Optronics GmbH", "DE")
    c = _org(conn, "Hensoldt Nexeya France", "FR")
    d = _org(conn, "HENSOLDT NEXEYA FRANCE SAS 1 rue de la Chaussee 91300 Massy", "FR")
    e = _org(conn, "Gmina Kolbuszowa", "PL")
    f = _org(conn, "Gmina Kolbuszowa", "PL")
    oid = _ted(conn, "9-2026", pid="p9")
    for org in (a, b, c, d, e, f):
        conn.execute("INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated, "
                     "winners_in_notice, resolution_method, resolution_confidence) "
                     "VALUES (%s, %s, 'DE', 'x', 1, 'test', 1.0)", (oid, org))
    conn.commit()
    lines: list[str] = []
    got = org_dedupe.run(conn, apply=True, out=lines.append)
    merged = {r["id"]: r["merged_into"] for r in conn.execute("SELECT id, merged_into FROM organisation").fetchall()}
    assert {merged[a], merged[b]} == {None, a} or {merged[a], merged[b]} == {None, b}
    assert {merged[c], merged[d]} - {None} in ({c}, {d})                      # the address after the legal form is cut
    assert merged[e] is None and merged[f] is None and got["left_public_body"] == 1


def test_the_site_search_lists_tenders_in_the_lists_default_order(client, conn):
    """WP-86's search runs each list with its defaults: its tender group follows the core-first order and the list's total."""
    put(conn, "SUPPLY-SOON", kind="supply", deadline=NOW + timedelta(days=2), title="Armoured spares supply")
    put(conn, "CORE-LATER", deadline=NOW + timedelta(days=20), title="Armoured spares core")
    got = get(client, "/v1/search", q="armoured")["tenders"]
    listed = get(client, "/v1/tenders", q="armoured")
    assert [t["noticeId"] for t in got["items"]] == [t["noticeId"] for t in listed["items"]] == ["CORE-LATER", "SUPPLY-SOON"]
    assert got["total"] == listed["total"] == 2
