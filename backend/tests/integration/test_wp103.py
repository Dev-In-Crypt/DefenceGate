"""WP-103 (persona round of 24 October 2026) against a real Postgres: VEAT and supply-scope result notices are read for
their winners, a figure the notice's own estimate contradicts is set aside, PLACSP call-offs held as ceilings become
contracts, TED's own field names give the framework ceiling, DefenceGate's re-read versions are annotated and stay out of
the change list, the stale statuses, Ley 24/2011 as the directive, and an award page whose winners were not read."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, awards, config, db, reprocess, stats
from dgate.normalise import Opportunity
from dgate.ops import award_values, tag_rereads
from tests.integration.test_wp95 import FakeTed, award, award_notice, notice, org

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


def result_notice(conn, native: str, *, subtype: str, status_native: str, core: bool) -> int:
    """A TED result notice; `core=False`: kept by its listed buyer alone (scope supply), as 728479-2026."""
    return conn.execute(
        """INSERT INTO opportunity (source_id, native_id, buyer_name_raw, country, title_original, published_at, cpv_codes,
                                    is_defence, sig_legal_basis, sig_cpv, sig_cpv_military, sig_buyer, buyer_class,
                                    notice_subtype, status, status_native, value_amount, value_currency, value_kind)
           VALUES ((SELECT id FROM source WHERE code = 'ted'), %s, 'Ministerio de Defensa', 'ES', 'Trajes', %s, %s, true,
                   %s, %s, %s, %s, 'defence', %s, 'awarded', %s, 1000000, 'EUR', 'total') RETURNING id""",
        (native, RECENT, ["35510000"] if core else ["18222100"], core, core, core, not core, subtype,
         status_native)).fetchone()["id"]


def winner(name: str) -> dict:
    return {"winner-name": {"spa": [name]}, "organisation-name-tenderer": {"spa": [name]},
            "organisation-country-tenderer": ["ESP"]}


def test_veat_and_supply_scope_result_notices_are_read_for_their_winners(conn, env):
    """375694-2026 (VEAT, subtype 25) and 728479-2026 (kept by its buyer alone) were never candidates."""
    veat = result_notice(conn, "375694-2026", subtype="25", status_native="veat", core=True)
    supply = result_notice(conn, "728479-2026", subtype="29", status_native="can-standard", core=False)
    conn.commit()
    fake = FakeTed({"375694-2026": {"publication-number": "375694-2026", **winner("F.B. Design S.r.l."),
                                    "BT-161-NoticeResult": "50783895.10"},
                    "728479-2026": {"publication-number": "728479-2026", **winner("Textil Santanderina SA")}})
    c = awards.run_awards(client=fake.client(), pause=0, sleep=lambda s: None)
    assert c["candidates"] == 2 and c["awards_new"] == 2
    read = {r["opportunity_id"]: r for r in conn.execute("SELECT * FROM award_notice").fetchall()}
    assert set(read) == {veat, supply}
    assert (float(read[veat]["value_amount"]), read[veat]["value_kind"]) == (50783895.10, "contract")


def test_the_tender_page_says_whether_the_winners_were_read(conn, client):
    oid = result_notice(conn, "728480-2026", subtype="29", status_native="can-standard", core=True)
    conn.commit()
    got = client.get(f"/v1/tenders/{oid}").json()
    assert (got["awardedTo"], got["winnersRead"]) == ([], False)
    award_notice(conn, oid)
    conn.commit()
    assert client.get(f"/v1/tenders/{oid}").json()["winnersRead"] is True


@pytest.fixture
def held(conn, env):
    """World Aviation 220199-2026 as held (contract EUR 7.27 bn over an estimate of 7.3 m), an Indra call-off held as a
    framework ceiling, Arquus 38915-2026 held as a contract, and a plain framework that stays."""
    pt = org(conn, "forca aerea", "PT", is_defence_buyer=True)
    wa = org(conn, "world aviation", "ES")
    t = notice(conn, "ted", "220199-2026", buyer=pt, country="PT", value=(7317073.17, "EUR", "estimated"))
    award(conn, t, wa, "World Aviation SL", value=(7274615930.0, "EUR", "contract"))
    award_notice(conn, t, value_amount=7274615930, value_currency="EUR", value_kind="contract")
    jae = org(conn, "jae", "ES", is_defence_buyer=True)
    indra = org(conn, "indra sistemas", "ES")
    off = notice(conn, "es_placsp", "2026/EA02/00001023E", buyer=jae,
                 title="20264007 Sostenimiento de aulas virtuales de tiro (5º Basado AM 202340A1)")
    award(conn, off, indra, "INDRA SISTEMAS SA", value=(123966.94, "EUR", "framework"))
    award_notice(conn, off)
    fw = notice(conn, "es_placsp", "2023/EA02/00000001E", buyer=jae, title="Acuerdo Marco para aulas virtuales de tiro")
    award(conn, fw, indra, "INDRA SISTEMAS SA", value=(900000.0, "EUR", "framework"))
    award_notice(conn, fw)
    fr = org(conn, "dga", "FR", is_defence_buyer=True)
    arquus = org(conn, "arquus", "FR")
    a = notice(conn, "ted", "38915-2026", buyer=fr, country="FR", value=(2449392735.0, "EUR", "total"))
    award(conn, a, arquus, "ARQUUS", value=(2449392735.0, "EUR", "contract"))
    award_notice(conn, a, value_amount=2449392735, value_currency="EUR", value_kind="contract")
    conn.commit()
    return {"wa": t, "off": off, "fw": fw, "arquus": a, "indra": indra}


def test_award_values_sets_aside_the_implausible_figure_and_makes_call_offs_contracts(conn, client, held):
    report = award_values.run_set_aside(conn, write=False)
    report.update(award_values.run_placsp(conn, write=False))
    conn.rollback()
    assert report["ted_values_set_aside"] == 1 and report["placsp_call_offs_framework_to_contract"] == 1
    assert conn.execute("SELECT value_set_aside FROM award_notice WHERE opportunity_id = %s",
                        (held["wa"],)).fetchone()["value_set_aside"] is None                      # a report writes nothing
    award_values.run_set_aside(conn, write=True)
    award_values.run_placsp(conn, write=True)
    n = conn.execute("SELECT * FROM award_notice WHERE opportunity_id = %s", (held["wa"],)).fetchone()
    assert (float(n["value_amount"]), n["value_kind"], float(n["value_set_aside"])) == (7317073.17, "estimate", 7274615930.0)
    a = conn.execute("SELECT value_amount, value_kind FROM award WHERE opportunity_id = %s", (held["wa"],)).fetchone()
    assert (float(a["value_amount"]), a["value_kind"]) == (7317073.17, "estimate")
    kinds = {r["opportunity_id"]: r["value_kind"] for r in conn.execute("SELECT opportunity_id, value_kind FROM award")}
    assert kinds[held["off"]] == "contract" and kinds[held["fw"]] == "framework"
    # the page says what was published and that it is not used
    v = client.get(f"/v1/tenders/{held['wa']}").json()["awardValue"]
    assert v == {"amount": 7317073.17, "currency": "EUR", "kind": "estimate", "setAside": 7274615930.0}
    # out of the contract sums: Indra's call-off is in, World Aviation has no contract value
    assert client.get(f"/v1/suppliers/{held['indra']}").json()["values"]["byCurrency"][0]["amount"] == 123966.94
    again = award_values.run_set_aside(conn, write=True)
    again.update(award_values.run_placsp(conn, write=True))
    assert again["ted_values_set_aside"] == 0 and again["placsp_call_offs_framework_to_contract"] == 0


def test_all_asks_ted_again_and_reads_teds_own_name_of_the_framework_maximum(conn, env, held, monkeypatch):
    fake = FakeTed({"38915-2026": {"publication-number": "38915-2026", "framework-maximum-value-lot": ["2449392735"],
                                   "tender-value": ["2449392735"]},
                    "220199-2026": {"publication-number": "220199-2026", "BT-161-NoticeResult": "7274615930"}})
    monkeypatch.setattr(award_values, "new_client", lambda **kw: fake.client())
    assert award_values.run_ted(conn, fetch=True, write=False, pause=0)["ted_notices"] == 0   # both hold a kind
    c = award_values.run_ted(conn, fetch=True, write=True, pause=0, every=True)
    assert c["ted_contract_to_framework"] == 1 and c["ted_contract_to_estimate"] == 1
    assert "framework-maximum-value-lot" in fake.fields[0]
    n = conn.execute("SELECT value_kind FROM award_notice WHERE opportunity_id = %s", (held["arquus"],)).fetchone()
    assert n["value_kind"] == "framework"


# --------------------------------------------------------------------------------------- re-read versions

def placsp(native: str, **over) -> Opportunity:
    base = dict(source_code="es_placsp", native_id=native, buyer_name_raw="Jefatura de Asuntos Economicos", country="ES",
                title_original="Suministro de repuestos", published_at=date.today() - timedelta(days=3),
                deadline_at=datetime.now(timezone.utc) + timedelta(days=20), cpv_codes=["35400000"], status="open",
                status_native="PUB", is_defence=True, sig_cpv=True, sig_cpv_military=True, buyer_class="defence",
                value_amount=71000.0, value_currency="EUR")
    return Opportunity(**{**base, **over})


def store(conn, o: Opportunity, tag: str) -> int:
    src = db.source_id(conn, o.source_code)
    o.buyer_org_id = db.resolve_organisation(conn, o.buyer_name_raw, o.country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, o, f"h-{o.native_id}-{tag}", src)
    conn.commit()
    return oid


def test_a_version_read_again_after_the_older_mapping_is_annotated_and_not_a_change(conn, client):
    """2026/ETSAE0206/00000782E (p10): 71,000 -> 58,677.69 and the publication date months back, shown as amended."""
    old = placsp("2026/ETSAE0206/00000782E")
    oid = store(conn, old, "a")
    new = replace(old, value_amount=58677.69, legal_basis="Ley 24/2011 (defensa y seguridad)",
                  published_at=date.today() - timedelta(days=100),
                  source_updated_at=datetime.now(timezone.utc) - timedelta(hours=2))
    store(conn, new, "b")
    notes = conn.execute("""SELECT n.kind FROM opportunity_version_note n JOIN opportunity_version v
                              ON v.id = n.opportunity_version_id WHERE v.opportunity_id = %s AND v.version = 2""",
                         (oid,)).fetchall()
    assert [r["kind"] for r in notes] == ["remapped"]
    assert not [i for i in client.get("/v1/changes").json()["items"] if i["kind"] == "amended"]


def test_tag_rereads_annotates_the_versions_written_before_and_a_second_run_writes_nothing(conn, env):
    old = placsp("2026/ETSAE0904/00000468E", value_amount=45274.11)
    oid = store(conn, old, "a")
    # a version as the live walk of 15 October wrote it: through the one writer, without the annotation
    new = replace(old, value_amount=37416.62, legal_basis="Ley 9/2017 (LCSP)",
                  source_updated_at=datetime.now(timezone.utc) - timedelta(hours=2))
    db.append_version(conn, oid, new, "h-b", ["legal_basis", "value_amount"], after=1)
    # and a real amendment of a stamped entry, which stays one
    later = replace(new, deadline_at=new.deadline_at + timedelta(days=7),
                    source_updated_at=datetime.now(timezone.utc) - timedelta(hours=1))
    db.append_version(conn, oid, later, "h-c", ["deadline_at"], after=2)
    conn.commit()
    c, _ = tag_rereads.run(conn, write=False)
    assert c["versions"] == 1
    c, _ = tag_rereads.run(conn, write=True)
    assert c["annotated"] == 1
    kinds = {r["version"]: r["kind"] for r in conn.execute(
        """SELECT v.version, n.kind FROM opportunity_version v LEFT JOIN opportunity_version_note n
             ON n.opportunity_version_id = v.id WHERE v.opportunity_id = %s""", (oid,)).fetchall()}
    assert kinds == {1: None, 2: "remapped", 3: None}
    assert tag_rereads.run(conn, write=True)[0]["versions"] == 0


# --------------------------------------------------------------------------------------- statuses and the directive

def test_stale_planned_and_no_call_notices_are_not_planned_or_open(conn):
    src = db.source_id(conn, "ted")
    rows = {}
    for native, status, procedure, published in (("106569-2024", "forthcoming", None, date.today() - timedelta(days=700)),
                                                 ("1-2026", "forthcoming", None, date.today() - timedelta(days=30)),
                                                 ("283577", "open", "de-comp-wo-call", None),
                                                 ("283578", "open", "de-restricted-w-call", None)):
        rows[native] = conn.execute(
            """INSERT INTO opportunity (source_id, native_id, title_original, buyer_name_raw, country, status, procedure_type,
                                        published_at, is_defence)
               VALUES (%s, %s, 'x', 'BAAINBw', 'DE', %s, %s, %s, true) RETURNING id""",
            (src, native, status, procedure, published)).fetchone()["id"]
    got = {r["native_id"]: r["s"] for r in conn.execute(
        f"SELECT o.native_id, {api.EFFECTIVE_STATUS_SQL} AS s FROM opportunity o WHERE o.id = ANY(%s)",
        (list(rows.values()),)).fetchall()}
    assert got == {"106569-2024": "expired", "1-2026": "forthcoming", "283577": "expired", "283578": "open"}


def test_reclassify_serving_reads_ley_24_2011_as_the_directive(conn, env):
    oid = conn.execute(
        """INSERT INTO opportunity (source_id, native_id, title_original, country, status, legal_basis, cpv_codes,
                                    buyer_name_raw, is_defence, sig_buyer, buyer_class)
           VALUES ((SELECT id FROM source WHERE code = 'es_placsp'), '2026/ETSAE0906/00004361E', 'Repuestos IVECO LMV', 'ES',
                   'awarded', 'Ley 24/2011 (defensa y seguridad)', '{34330000}', 'Jefatura', true, true, 'defence')
           RETURNING id""").fetchone()["id"]
    conn.commit()
    counts = reprocess.reclassify_serving(conn, source="es_placsp", dry_run=False)
    assert counts["changed"] >= 1
    assert conn.execute("SELECT sig_legal_basis FROM opportunity WHERE id = %s", (oid,)).fetchone()["sig_legal_basis"]
