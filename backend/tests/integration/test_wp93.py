"""WP-93 against Postgres: the facts the badge receives (quotes, readings, the EIC work programme's own scope, an AID page's rules),
the ops tool that applies the readings to what is stored, and the call verdict of the assessment API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from dgate import api, db, eligibility
from dgate.readiness import api as readiness_api
from dgate.readiness import seed
from tests.integration.test_wp31 import doc, fields, hold, put
from tests.unit.test_wp93 import DEP12, EIC_ACCELERATOR

pytestmark = pytest.mark.integration

EIC_WP = "https://eic.ec.europa.eu/system/files/EIC-Work-Programme-2026.pdf"
ACC = "HORIZON-EIC-2026-ACCELERATOR-01"
CBCH = "DIGITAL-ECCC-2027-DEPLOY-CYBER-12-CBCH"
DEP12_URL = "https://example.test/dep12.pdf"


@pytest.fixture()
def client(conn):
    readiness_api.reset_cache()
    seed.apply(conn, seed.load_file())
    conn.commit()
    with TestClient(api.app) as c:
        yield c
    readiness_api.reset_cache()


def stored(conn, url: str, text: str) -> None:
    conn.execute("INSERT INTO call_document_text (url, sha256, pages, chars, text) VALUES (%s, 'x', 1, %s, %s) "
                 "ON CONFLICT (url) DO UPDATE SET text = EXCLUDED.text", (url, len(text), text))


def row(conn, key: str, scope: str, document: str, **given) -> None:
    conn.execute(
        """INSERT INTO call_eligibility (url, fields, model, prompt_version, input_tokens, output_tokens, cost_usd, scope, document_url)
           VALUES (%s, %s, 'm', %s, 1, 1, 0, %s, %s)""",
        (key, Jsonb(fields(**given)), eligibility.PROMPT_VERSION, scope, document))
    conn.commit()


def facts_of(client, cid: int) -> dict:
    r = client.get("/v1/fit/facts", params={"ids": str(cid)})
    assert r.status_code == 200, r.text
    return r.json()["items"][str(cid)]


def test_the_ops_tool_reads_the_stored_texts_reports_by_default_writes_with_yes_and_is_idempotent(conn, client):
    from dgate.ops import rule_readings

    acc = put(conn, "acc", topic=ACC, documents=[doc(EIC_WP, "EIC Work Programme")])
    cbch = put(conn, "cbch", programme="DIGITAL", topic=CBCH, documents=[doc(DEP12_URL)])
    stored(conn, EIC_WP, EIC_ACCELERATOR)
    stored(conn, DEP12_URL, DEP12)
    row(conn, f"{EIC_WP}#{ACC}", "general", EIC_WP, sme_only=(False, "The call is not reserved for SMEs.", None),
        eligible_countries=("EU Member States and countries associated to Horizon Europe", "q", eligibility.SCOPE_NOTES["general"]))
    row(conn, f"{DEP12_URL}#{CBCH}", "call_document", DEP12_URL, eligible_countries=("EU Member States; EEA countries (Norway)", "q", None))

    before = facts_of(client, acc)["facts"]
    assert before["sme_only"]["value"] is False and before["sme_only"]["scope"] == "programme"   # the EIC text for the topic: its own
    assert before["eligible_countries"]["note"] is None, "the words that said 'general annexes' are gone"
    assert before["eligible_countries"]["quote"] == "q", "the badge receives the quote"

    report = rule_readings.run(write=False)
    assert len(report.changed) == 2 and report.failed == 0
    assert facts_of(client, acc)["facts"]["sme_only"]["value"] is False, "a report writes nothing"
    assert len(rule_readings.run(write=True).changed) == 2
    after = facts_of(client, acc)["facts"]
    assert after["sme_only"]["value"] is True and "investment component only" in after["sme_only"]["note"]
    hub = facts_of(client, cbch)["facts"]["designated_applicants"]
    assert hub["value"] == "Public bodies acting as National Cyber Hubs" and hub["scope"] == "call_document"
    assert rule_readings.run(write=True).changed == [], "a second run writes nothing"


def test_an_aid_call_gets_the_rules_of_its_page_without_the_page_text(conn, client, monkeypatch, tmp_path):
    from dgate import config
    from dgate.ops import rule_readings
    from dgate.rawstore import build_store

    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    cid = put(conn, "rapid", programme="FR-AID", source="fr_aid", topic="FR-AID-rapid", country="FR")
    src = db.source_id(conn, "fr_aid")
    key = build_store().put("fr_aid/2026/10/23/rapid.json", {
        "slug": "rapid", "title": "RAPID", "modified": "2026-09-01",
        "text": "RAPID s'adresse aux PME et ETI dont l'effectif consolidé de moins de 2000 salariés."})
    db.record_raw(conn, src, "rapid", "h-rapid", key)
    conn.commit()
    assert facts_of(client, cid)["state"] == "no_source"
    assert [c.split(":")[0] for c in rule_readings.run(write=True).changed] == [f"call {cid} (rapid)"]
    item = facts_of(client, cid)
    assert item["state"] == "read" and item["facts"]["max_group_headcount"]["value"] == 1999
    assert item["facts"]["max_group_headcount"]["quote"] == "", "the agency's words are not served"
    page = client.get(f"/v1/funding/{cid}").json()
    assert page["documentEligibility"]["basis"] == "call_page" and page["eligibilityState"] == "read"
    assert rule_readings.run(write=True).changed == []
    config.reset_cache()


def test_the_assessment_of_a_call_carries_the_one_verdict(conn, client):
    url = "https://example.test/dualuse.pdf"
    cid = put(conn, "dual", programme="DIGITAL", topic="DIGITAL-ECCC-2027-DEPLOY-CYBER-11-DUALUSE", documents=[doc(url)])
    hold(conn, url, "call_document",
         eligible_countries=("EU Member States (including OCTs); EEA countries (Norway, Iceland, Liechtenstein)", "Eligible countries: EU and EEA.", None))
    body = {"profile": {"country": "UA", "legal_form": "legal_person", "third_country_control": "ua_eea_only", "control_country": "ua",
                        "headcount": "50_249", "in_group": False}, "statuses": {}, "call": cid}
    r = client.post("/v1/readiness/assess", json=body)
    assert r.status_code == 200, r.text
    got = r.json()["call"]["verdict"]
    assert got["fit"] == "no" and got["word"] == "Blocked by: Country"
    assert got["lines"][0]["key"] == "country" and "not among them" in got["lines"][0]["reason"]
    body["profile"]["country"] = "PL"
    assert client.post("/v1/readiness/assess", json=body).json()["call"]["verdict"]["word"] == "Eligible"
