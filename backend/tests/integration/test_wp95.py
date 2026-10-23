"""WP-95 (persona round of 23 October 2026, section A1) against a real Postgres: value kinds on the supplier page and in the
supplier report, the award notice's winners and value, the winners of older-format TED notices, the backfill commands, the
catch-all rule and the Latvian agency through the serving rows, and the change list's new awards and lots."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from dgate import api, awards, config, db, reprocess, stats
from dgate.normalise import Opportunity
from dgate.ops import award_values, buyer_cleanup, co_buyers
from dgate.rawstore import build_store

pytestmark = pytest.mark.integration

RECENT = date.today() - timedelta(days=40)


@pytest.fixture
def env(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("DGATE_PLACSP_AWARDS_PUBLIC", "true")
    config.reset_cache()
    stats.reset_cache()
    yield tmp_path
    config.reset_cache()
    stats.reset_cache()


@pytest.fixture
def client(env):
    with TestClient(api.app) as c:
        yield c


def org(conn, name: str, country: str, **extra) -> int:
    cols = ["canonical_name", "country", *extra]
    return conn.execute(f"INSERT INTO organisation ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id",
                        [name, country, *extra.values()]).fetchone()["id"]


def notice(conn, source: str, native: str, *, title: str = "Repuestos", buyer: int | None = None, country: str = "ES",
           value: tuple[float, str, str | None] | None = None, subtype: str | None = "29", status_native: str | None = None,
           cpv: tuple[str, ...] = ("35420000",), core: bool = True, published: date = RECENT) -> int:
    amount, currency, kind = value or (None, None, None)
    return conn.execute(
        """INSERT INTO opportunity (source_id, native_id, buyer_org_id, buyer_name_raw, country, title_original, published_at,
                                    cpv_codes, is_defence, sig_legal_basis, sig_cpv, sig_cpv_military, buyer_class, value_amount,
                                    value_currency, value_kind, notice_subtype, status, status_native, source_url)
           VALUES ((SELECT id FROM source WHERE code = %s), %s, %s, 'JAE MALE', %s, %s, %s, %s, true, %s, true, true, 'defence',
                   %s, %s, %s, %s, 'awarded', %s, %s) RETURNING id""",
        (source, native, buyer, country, title, published, list(cpv), core, amount, currency, kind, subtype, status_native,
         f"https://example.test/{native}")).fetchone()["id"]


def award(conn, opp: int, winner: int, name: str, *, value: tuple[float, str, str | None] | None = None,
          winners: int = 1, country: str = "ES") -> int:
    amount, currency, kind = value or (None, None, None)
    return conn.execute(
        """INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated, winners_in_notice, cpv_main,
                              resolution_method, resolution_confidence, value_amount, value_currency, value_kind)
           VALUES (%s, %s, %s, %s, %s, '35420000', 'exact_name', 1.0, %s, %s, %s) RETURNING id""",
        (opp, winner, country, name, winners, amount, currency, kind)).fetchone()["id"]


def award_notice(conn, opp: int, **cols) -> None:
    keys = ["opportunity_id", "status", "winners_seen", "winners_kept", *cols]
    conn.execute(f"INSERT INTO award_notice ({', '.join(keys)}) VALUES ({', '.join(['%s'] * len(keys))})",
                 [opp, "loaded", 1, 1, *cols.values()])


# --------------------------------------------------------------------- 1. values by kind on the supplier page

@pytest.fixture
def madzeal(conn, env):
    """MADZEAL as the persona found it: a framework (TED ceiling), its call-off (PLACSP contract, linked), a contract, an
    estimate, a TED framework maximum and a TED notice still without a kind (read as before WP-95)."""
    jae = org(conn, "jae mando de apoyo logistico", "ES", is_defence_buyer=True)
    m = org(conn, "madzeal", "ES")
    fw = notice(conn, "ted", "389204-2026", title="ACUERDO MARCO - Suministro abierto de repuestos IVECO", buyer=jae)
    award(conn, fw, m, "Madzeal, S.L.", value=(1250000.0, "EUR", "framework"))
    award_notice(conn, fw, value_amount=1250000, value_currency="EUR", value_kind="framework")
    placsp_fw = notice(conn, "es_placsp", "2025/AR43U/00001894E", title="ACUERDO MARCO - Suministro abierto IVECO", buyer=jae)
    off = notice(conn, "es_placsp", "2026/AR43U/00002206E",
                 title="2018AYM2059S - TEAR - 1º CB AM (2025/AR43U/00001894) - Suministro Abierto de repuestos", buyer=jae)
    award(conn, off, m, "MADZEAL S.L.", value=(500000.0, "EUR", "contract"))
    award_notice(conn, off, framework_id=placsp_fw)
    c = notice(conn, "es_placsp", "2026/ETSAE0906/00003787E", title="Adquisición de baterías de arranque", buyer=jae)
    award(conn, c, m, "MADZEAL S.L.", value=(743802.0, "EUR", "contract"))
    e = notice(conn, "ted", "712069-2026", title="Industrieunterstützung BV 206", buyer=jae)
    award(conn, e, m, "Madzeal, S.L.", value=(1160000.0, "EUR", "estimate"))
    old = notice(conn, "ted", "100-2026", title="Repuestos Pizarro", buyer=jae, value=(41000.0, "EUR", "lot_sum"))
    award(conn, old, m, "Madzeal, S.L.")              # no kind yet: a sum of lot estimates is an estimate now
    small = notice(conn, "ted", "101-2026", title="Tornillos", buyer=jae, value=(48.0, "EUR", "total"))
    award(conn, small, m, "Madzeal, S.L.")             # a unit price (WP-87): in no sum
    conn.commit()
    return {"org": m, "framework": fw, "placsp_framework": placsp_fw, "call_off": off}


def test_only_contract_values_are_summed_and_ceilings_and_estimates_are_listed_apart(client, madzeal):
    s = client.get(f"/v1/suppliers/{madzeal['org']}").json()
    v = s["values"]
    assert v["byCurrency"] == [{"currency": "EUR", "amount": 1243802.0, "count": 2, "lotEstimates": 0}]
    assert v["frameworks"] == [{"currency": "EUR", "amount": 1250000.0, "count": 1, "lotEstimates": 0}]
    assert v["estimates"] == [{"currency": "EUR", "amount": 1201000.0, "count": 2, "lotEstimates": 0}]
    assert (v["of"], v["withoutValue"], v["suspect"]) == (6, 0, 1)
    # the largest contracts, with their notices, contract values only
    assert [(c["noticeId"], c["amount"]) for c in v["largest"]] == [("2026/ETSAE0906/00003787E", 743802.0),
                                                                     ("2026/AR43U/00002206E", 500000.0)]
    rows = {n["noticeId"]: n for n in s["notices"]}
    assert rows["389204-2026"]["valueKind"] == "framework" and rows["712069-2026"]["valueKind"] == "estimate"
    assert rows["2026/ETSAE0906/00003787E"]["valueKind"] == "contract" and rows["100-2026"]["valueKind"] == "estimate"
    # the call-off names its framework, with the framework's page
    fw = rows["2026/AR43U/00002206E"]["framework"]
    assert fw["noticeId"] == "2025/AR43U/00001894E" and fw["slug"].startswith(f"{madzeal['placsp_framework']}-")
    assert rows["389204-2026"]["framework"] is None


def test_a_twin_pair_is_valued_by_its_contract_value_before_a_ceiling(conn, client, madzeal):
    # the PLACSP copy of the IVECO framework states the award as a contract value: the pair is one procurement, valued once
    m = madzeal["org"]
    twin = award(conn, madzeal["placsp_framework"], m, "MADZEAL SL", value=(1100000.0, "EUR", "contract"))
    keep = conn.execute("SELECT id FROM award WHERE opportunity_id = %s", (madzeal["framework"],)).fetchone()["id"]
    conn.execute("INSERT INTO award_twin_set (award_id, preferred_id, procedure_method, winner_method) VALUES (%s, %s, "
                 "'procedure_id', 'organisation')", (twin, keep))
    conn.commit()
    v = client.get(f"/v1/suppliers/{m}").json()["values"]
    assert v["byCurrency"][0]["amount"] == 1243802.0 + 1100000.0 and v["frameworks"] == []


def test_the_supplier_report_shows_the_kinds_and_the_largest_contracts(conn, client, madzeal):
    r = client.post("/v1/readiness/demand", json={"cpv": ["35420000"], "countries": ["ES"]})
    assert r.status_code == 200, r.text
    w = {x["name"]: x for x in r.json()["approach"]["winners"]}
    v = next(x for n, x in w.items() if n.lower().startswith("madzeal"))["values"]
    assert v["byCurrency"][0]["amount"] == 1243802.0
    assert v["frameworks"][0]["amount"] == 1250000.0 and len(v["largest"]) == 2


# ------------------------------------------------------------------------------ 2. the award notice's own page

def test_an_award_notice_names_its_legal_entity_winners_and_says_what_its_value_is(conn, client, madzeal):
    jae = conn.execute("SELECT id FROM organisation WHERE canonical_name = 'jae mando de apoyo logistico'").fetchone()["id"]
    radar = notice(conn, "ted", "518727-2026", title="Radar", buyer=jae, country="RO")
    indra = org(conn, "indra sistemas", "ES")
    person = org(conn, "juan perez garcia", "ES", individual_reason="natural_person")
    award(conn, radar, indra, "INDRA SISTEMAS S.A.", value=(80817296.0, "EUR", "contract"))
    award(conn, radar, person, "Juan Perez Garcia")
    award_notice(conn, radar, value_amount=80817296, value_currency="EUR", value_kind="contract", skipped_person=1)
    conn.execute("UPDATE opportunity SET other_buyers = ARRAY['Valsts policija'] WHERE id = %s", (radar,))
    conn.commit()
    t = client.get(f"/v1/tenders/{radar}").json()
    assert [(w["name"], w["country"]) for w in t["awardedTo"]] == [("INDRA SISTEMAS S.A.", "ES")]
    assert t["awardedTo"][0]["slug"].startswith(f"{indra}-")
    assert "Juan" not in json.dumps(t) and "Perez" not in json.dumps(t)
    assert t["awardedPersons"] == 1
    assert t["awardValue"] == {"amount": 80817296.0, "currency": "EUR", "kind": "contract"}
    assert t["otherBuyers"] == ["Valsts policija"]
    # the framework notice: its value is a ceiling; a notice with no award has none of this
    f = client.get(f"/v1/tenders/{madzeal['framework']}").json()
    assert f["awardValue"]["kind"] == "framework" and f["awardedTo"][0]["name"] == "Madzeal, S.L."
    plain = notice(conn, "ted", "1-2026", title="Open call", buyer=jae)
    conn.commit()
    p = client.get(f"/v1/tenders/{plain}").json()
    assert (p["awardedTo"], p["awardedPersons"], p["awardValue"], p["otherBuyers"]) == ([], 0, None, [])


def test_a_winner_outside_the_supplier_maps_window_is_named_without_a_link(conn, client, madzeal):
    jae = conn.execute("SELECT id FROM organisation WHERE canonical_name = 'jae mando de apoyo logistico'").fetchone()["id"]
    old = notice(conn, "ted", "5-2019", title="Old", buyer=jae, published=date(2019, 5, 1))
    award(conn, old, org(conn, "old works", "ES"), "Old Works SA")
    conn.commit()
    w = client.get(f"/v1/tenders/{old}").json()["awardedTo"]
    assert w == [{"name": "Old Works SA", "slug": None, "country": "ES", "valueAmount": None, "valueCurrency": None,
                  "valueKind": None}]


# --------------------------------------------------------- 3. TED: values and older-format winners at load time

class FakeTed:
    """The search API by publication number, and the notice document by its URL."""

    def __init__(self, records: dict[str, dict], documents: dict[str, bytes] | None = None):
        self.records, self.documents, self.asked, self.fields = records, documents or {}, [], []

    def client(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                number = re.search(r"/notice/([^/]+)/xml", str(request.url)).group(1)
                doc = self.documents.get(number)
                return httpx.Response(200, content=doc) if doc else httpx.Response(404)
            body = json.loads(request.content)
            numbers = re.search(r"IN \(([^)]*)\)", body["query"]).group(1).split()
            self.asked.append(numbers)
            self.fields.append(body["fields"])
            return httpx.Response(200, json={"notices": [self.records[n] for n in numbers if n in self.records]})
        return httpx.Client(transport=httpx.MockTransport(handler))


LEGACY_DOC = b"""<?xml version="1.0" encoding="UTF-8"?>
<TED_EXPORT xmlns="http://publications.europa.eu/resource/schema/ted/R2.0.9/publication"><FORM_SECTION><F18_2014>
 <AWARD_CONTRACT><AWARDED_CONTRACT><CONTRACTORS><CONTRACTOR><ADDRESS_CONTRACTOR>
  <OFFICIALNAME>FINCANTIERI S.P.A.</OFFICIALNAME><NATIONALID>00397130584</NATIONALID><COUNTRY VALUE="IT"/>
 </ADDRESS_CONTRACTOR></CONTRACTOR></CONTRACTORS></AWARDED_CONTRACT></AWARD_CONTRACT></F18_2014></FORM_SECTION></TED_EXPORT>"""


def ted_notice(conn, native: str, *, subtype: str | None, status_native: str | None, value=None, legal=True) -> int:
    o = Opportunity(source_code="ted", native_id=native, buyer_name_raw="Ministero della Difesa", title_original="Repair",
                    country="IT", published_at=date(2024, 1, 22), cpv_codes=["50640000"], status="awarded",
                    status_native=status_native, is_defence=True, sig_legal_basis=legal, sig_cpv=True, sig_cpv_military=True,
                    notice_subtype=subtype, value_amount=value[0] if value else None, value_currency="EUR" if value else None,
                    value_kind=value[1] if value else None, legal_basis="32009L0081")
    src = db.source_id(conn, "ted")
    o.buyer_org_id = db.resolve_organisation(conn, o.buyer_name_raw, "IT", src_id=src)
    oid, _ = db.upsert_opportunity(conn, o, f"h-{native}", src)
    conn.commit()
    return oid


def test_an_older_format_result_notice_is_read_and_its_winners_come_from_its_document(conn, env):
    """TED 40783-2024: no subtype (older format), so it was never asked for; Fincantieri had no win."""
    legacy = ted_notice(conn, "40783-2024", subtype=None, status_native="can-standard", value=(1000000.0, "total"))
    ted_notice(conn, "40784-2024", subtype=None, status_native="cn-standard")        # a contract notice: not asked
    fake = FakeTed({"40783-2024": {"publication-number": "40783-2024"}}, {"40783-2024": LEGACY_DOC})
    c = awards.run_awards(client=fake.client(), pause=0, sleep=lambda s: None)
    assert c["candidates"] == 1 and fake.asked == [["40783-2024"]]
    assert (c["legacy_documents"], c["legacy_with_winners"], c["awards_new"]) == (1, 1, 1)
    row = conn.execute("SELECT a.*, o.canonical_name FROM award a JOIN organisation o ON o.id = a.organisation_id").fetchone()
    assert (row["opportunity_id"], row["canonical_name"], row["supplier_country"]) == (legacy, "fincantieri", "IT")
    # the older format's total is the awarded total: a contract value, on the notice and its one winner
    assert (float(row["value_amount"]), row["value_kind"]) == (1000000.0, "contract")
    n = conn.execute("SELECT * FROM award_notice WHERE opportunity_id = %s", (legacy,)).fetchone()
    assert (float(n["value_amount"]), n["value_kind"]) == (1000000.0, "contract")
    # the value fields were asked with the winners
    assert "BT-118-NoticeResult" in fake.fields[0] and "winner-name" in fake.fields[0]


def test_an_older_format_notice_whose_document_names_nobody_is_marked_read(conn, env):
    ted_notice(conn, "40785-2024", subtype=None, status_native="can-standard")
    c = awards.run_awards(client=FakeTed({"40785-2024": {"publication-number": "40785-2024"}}).client(), pause=0,
                          sleep=lambda s: None)
    assert (c["legacy_documents"], c["legacy_with_winners"], c["notices_no_winner_data"]) == (1, 0, 1)


def test_an_eforms_framework_maximum_is_stored_as_a_ceiling(conn, env):
    oid = ted_notice(conn, "390572-2026", subtype="29", status_native="can-standard", value=(11930000.0, "total"))
    fake = FakeTed({"390572-2026": {"publication-number": "390572-2026", "BT-118-NoticeResult": "11930000.00",
                                    "winner-name": {"deu": ["Rheinmetall Landsysteme GmbH"]},
                                    "organisation-name-tenderer": {"deu": ["Rheinmetall Landsysteme GmbH"]},
                                    "organisation-country-tenderer": ["DEU"]}})
    awards.run_awards(client=fake.client(), pause=0, sleep=lambda s: None)
    a = conn.execute("SELECT value_amount, value_kind FROM award WHERE opportunity_id = %s", (oid,)).fetchone()
    assert (float(a["value_amount"]), a["value_kind"]) == (11930000.0, "framework")


# --------------------------------------------------------------------------------- the backfill commands

def test_award_values_fills_the_kinds_of_the_rows_held_and_a_second_run_writes_nothing(conn, env, monkeypatch):
    jae = org(conn, "jae", "ES", is_defence_buyer=True)
    m = org(conn, "madzeal", "ES")
    t1 = notice(conn, "ted", "390572-2026", buyer=jae, value=(11930000.0, "EUR", "total"))
    award(conn, t1, m, "Madzeal")
    award_notice(conn, t1)
    t2 = notice(conn, "ted", "200-2026", buyer=jae, value=(5000.0, "EUR", "total"))
    award(conn, t2, m, "Madzeal")
    award_notice(conn, t2)
    fw = notice(conn, "es_placsp", "2025/AR43U/00001894E", title="ACUERDO MARCO - repuestos IVECO", buyer=jae)
    award(conn, fw, m, "Madzeal", value=(1250000.0, "EUR", None))
    award_notice(conn, fw)
    off = notice(conn, "es_placsp", "2026/AR43U/00002206E", title="1º CB AM (2025/AR43U/00001894) - repuestos", buyer=jae)
    award(conn, off, m, "Madzeal", value=(500000.0, "EUR", None))
    award_notice(conn, off)
    conn.commit()
    fake = FakeTed({"390572-2026": {"publication-number": "390572-2026", "BT-118-NoticeResult": "11930000.00"},
                    "200-2026": {"publication-number": "200-2026", "BT-161-NoticeResult": "5000"}})
    monkeypatch.setattr(award_values, "new_client", lambda **kw: fake.client())
    report = award_values.run_ted(conn, fetch=True, write=False, pause=0)
    report.update(award_values.run_placsp(conn, write=False))
    conn.rollback()
    assert report["ted_framework"] == 1 and report["ted_contract"] == 1 and report["ted_notices_changed"] == 2
    assert report["placsp_framework"] == 1 and report["placsp_contract"] == 1 and report["placsp_framework_links_new"] == 1
    assert conn.execute("SELECT count(*) AS n FROM award WHERE value_kind IS NOT NULL").fetchone()["n"] == 0   # a report
    award_values.run_ted(conn, fetch=True, write=True, pause=0)
    award_values.run_placsp(conn, write=True)
    kinds = {r["native_id"]: (r["value_kind"], r["framework_id"]) for r in conn.execute(
        """SELECT o.native_id, a.value_kind, n.framework_id FROM award a JOIN opportunity o ON o.id = a.opportunity_id
             JOIN award_notice n ON n.opportunity_id = o.id""").fetchall()}
    assert kinds == {"390572-2026": ("framework", None), "200-2026": ("contract", None),
                     "2025/AR43U/00001894E": ("framework", None), "2026/AR43U/00002206E": ("contract", fw)}
    again = award_values.run_ted(conn, fetch=True, write=True, pause=0)
    again.update(award_values.run_placsp(conn, write=True))
    assert again["ted_notices"] == 0 and again["placsp_rows_changed"] == 0 and again["placsp_framework_links_new"] == 0


def test_award_values_without_fetching_reads_the_stored_values(conn, env):
    jae = org(conn, "jae", "ES", is_defence_buyer=True)
    t = notice(conn, "ted", "300-2026", buyer=jae, value=(40000.0, "EUR", "lot_sum"))
    award(conn, t, org(conn, "x", "ES"), "X SA")
    award_notice(conn, t)
    conn.commit()
    award_values.run_ted(conn, fetch=False, write=True)
    assert conn.execute("SELECT value_kind FROM award").fetchone()["value_kind"] == "estimate"


def test_co_buyers_reads_the_other_buyers_from_the_landed_payload(conn, env):
    oid = ted_notice(conn, "711894-2026", subtype="16", status_native="cn-standard")
    store = build_store()
    payload = {"publication-number": "711894-2026", "buyer-name": {"lav": ["Nodrošinājuma valsts aģentūra", "Valsts policija"]}}
    key = store.put("ted/2026/10/15/711894-2026.json", payload)
    db.record_raw(conn, db.source_id(conn, "ted"), "711894-2026", "h-raw", key)
    conn.commit()
    got = co_buyers.run(conn, write=False, store=store)
    assert got["joint"] == 1
    assert conn.execute("SELECT other_buyers FROM opportunity WHERE id = %s", (oid,)).fetchone()["other_buyers"] is None
    co_buyers.run(conn, write=True, store=store)
    assert conn.execute("SELECT other_buyers FROM opportunity WHERE id = %s", (oid,)).fetchone()["other_buyers"] == [
        "Valsts policija"]
    assert co_buyers.run(conn, write=True, store=store)["notices"] == 0


# ------------------------------------------------------------------------------- 4. classification on stored rows

def test_reclassify_serving_takes_a_civil_buyers_catch_all_notice_out_of_defence(conn, env):
    codes = [f"{4500 + i:04d}0000" for i in range(70)] + ["35420000"]
    o = Opportunity(source_code="ted", native_id="77-2026", buyer_name_raw="Ayuntamiento de Bétera", title_original="DPS",
                    country="ES", published_at=date(2026, 9, 1), cpv_codes=codes, status="open", is_defence=True,
                    sig_cpv=True, sig_cpv_military=True, buyer_class="municipal")
    src = db.source_id(conn, "ted")
    o.buyer_org_id = db.resolve_organisation(conn, o.buyer_name_raw, "ES", src_id=src)
    oid, _ = db.upsert_opportunity(conn, o, "h-77", src)
    conn.commit()
    counts = reprocess.reclassify_serving(conn, dry_run=False)
    assert counts["defence_to_not"] == 1
    row = conn.execute("SELECT is_defence, sig_cpv_military FROM opportunity WHERE id = %s", (oid,)).fetchone()
    assert (row["is_defence"], row["sig_cpv_military"]) == (False, True)       # the signal column still says the code is there


def test_the_cleanup_unflags_the_latvian_interior_agency_even_with_directive_notices(conn, env):
    nva = org(conn, "nodrosinajuma valsts agentura", "LV", is_defence_buyer=True)
    conn.execute("UPDATE organisation SET defence_buyer_source = 'derived_rule' WHERE id = %s", (nva,))
    oid = notice(conn, "ted", "711894-2026", buyer=nva, country="LV")
    conn.execute("UPDATE opportunity SET sig_legal_basis = true, sig_buyer = true WHERE id = %s", (oid,))
    conn.commit()
    done = buyer_cleanup.run(conn, apply=True, out=lambda *_: None)
    assert done["unflagged"] >= 1
    assert conn.execute("SELECT is_defence_buyer FROM organisation WHERE id = %s", (nva,)).fetchone()["is_defence_buyer"] is False


# --------------------------------------------------------------------------------------------- 5. /changes

def test_new_awards_are_listed_apart_and_the_lots_of_a_notice_are_one_row(conn, client):
    now = datetime.now(timezone.utc)
    src = db.source_id(conn, "ted")

    def put(native, title, status):
        o = Opportunity(source_code="ted", native_id=native, buyer_name_raw="45 Wojskowy Oddzial Gospodarczy",
                        title_original=title, country="PL", published_at=now.date(), deadline_at=now + timedelta(days=20),
                        cpv_codes=["35300000"], status=status, is_defence=True, sig_cpv=True, sig_cpv_military=True,
                        sig_legal_basis=True, buyer_class="defence")
        o.buyer_org_id = db.resolve_organisation(conn, o.buyer_name_raw, "PL", src_id=src)
        db.upsert_opportunity(conn, o, f"h-{native}", src)

    put("C1", "Część I: Dostawa smaru", "open")
    put("C2", "Część II: Dostawa smaru", "open")
    put("A1", "Dostawa amunicji 9 mm", "awarded")
    conn.commit()
    body = client.get("/v1/changes").json()
    assert body["counts"] == {"new": 1, "amended": 0, "awards": 1}
    assert body["total"] == 2
    kinds = {i["tender"]["noticeId"]: (i["kind"], i["repeats"]) for i in body["items"]}
    assert kinds["A1"] == ("award", 1)
    assert next(v for k, v in kinds.items() if k in ("C1", "C2")) == ("new", 2)
    only = client.get("/v1/changes", params={"kind": "award"}).json()
    assert [i["tender"]["noticeId"] for i in only["items"]] == ["A1"]
    assert {i["tender"]["noticeId"] for i in client.get("/v1/changes", params={"kind": "new"}).json()["items"]} <= {"C1", "C2"}
