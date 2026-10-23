"""WP-35: eligibility read per topic, and the digest's "new" and "amended" (V-B verifier, 17 October 2026).

Against a real Postgres, the language model a fake client."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from dgate import api, cascade, changes, config, eligibility, stats
from tests.integration.test_changes import age, amend, opp, store
from tests.integration.test_wp31 import doc, hold, put

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)
PDF = "https://example.test/fiche_digital-2027-cyber-11_en.pdf"
NCC, REGCABH = "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC", "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-REGCABH"
TEXT = (f"Financial support to third parties is allowed in topic {NCC} for grants under the following conditions. "
        f"For {REGCABH} consortia need at least two applicants from two countries.")


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
def model_on(monkeypatch):
    monkeypatch.setenv("DGATE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DGATE_OPENAI_MODEL", "test-model")
    monkeypatch.setenv("DGATE_LLM_MONTHLY_CAP_USD", "5")
    config.reset_cache()
    monkeypatch.setattr(eligibility, "fetch_text", lambda url, client=None: ("abc", 9, TEXT))
    yield
    config.reset_cache()


def _model(answer_quote: str):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["input"])
        out = {name: {"value": None, "confidence": 0.0, "quote": None, "note": None} for name in eligibility.FIELDS}
        out["cascade_funding"] = {"value": True, "confidence": 0.9, "quote": answer_quote, "note": None}
        out["consortium_required"] = {"value": True, "confidence": 0.9, "note": None,
                                      "quote": f"For {REGCABH} consortia need at least two applicants from two countries."}
        return httpx.Response(200, json={"status": "completed", "usage": {"input_tokens": 100, "output_tokens": 50},
                                         "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(out)}]}]})
    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def two_topics(conn):
    a = put(conn, "reg", topic=REGCABH, documents=[doc(PDF)])
    b = put(conn, "ncc", topic=NCC, documents=[doc(PDF)])
    return a, b


# ======================================================================= one reading per topic

def test_a_document_shared_by_two_topics_is_read_once_per_topic(conn):
    two_topics(conn)
    put(conn, "alone", topic="DIGITAL-2027-X-ONE", documents=[doc("https://example.test/other.pdf")])
    units = [u for u in eligibility.extraction_units(conn) if u["scope"] == "call_document"]
    assert sorted(u["key"] for u in units) == sorted([
        f"{PDF}#{NCC}", f"{PDF}#{REGCABH}", "https://example.test/other.pdf#DIGITAL-2027-X-ONE"])
    assert {u["url"] for u in units if PDF in u["key"]} == {PDF}
    assert {u["topic"][0] for u in units if PDF in u["key"]} == {NCC, REGCABH}


def test_the_model_is_told_the_topic_and_a_quote_naming_another_topic_is_refused(conn, model_on):
    put(conn, "reg", topic=REGCABH, documents=[doc(PDF)])
    client_, seen = _model(f"Financial support to third parties is allowed in topic {NCC} for grants under the following conditions.")
    report = eligibility.extract_one(conn, PDF, topic=(REGCABH, "Regional Cable Hubs"), llm_client=client_)
    assert report["url"] == f"{PDF}#{REGCABH}" and report["status"] == "done"
    assert REGCABH in seen[0] and "Regional Cable Hubs" in seen[0] and "this topic only" in seen[0]
    row = conn.execute("SELECT fields, prompt_version FROM call_eligibility WHERE url = %s", (f"{PDF}#{REGCABH}",)).fetchone()
    assert row["prompt_version"] == eligibility.PROMPT_VERSION == 4
    assert row["fields"]["cascade_funding"]["verified"] is False and row["fields"]["cascade_funding"]["other_topic"] is True
    assert row["fields"]["consortium_required"]["verified"] is True
    # the document text is held once, under the document
    assert conn.execute("SELECT count(*) AS n FROM call_document_text WHERE url LIKE %s", (PDF + "%",)).fetchone()["n"] == 1
    assert conn.execute("SELECT count(*) AS n FROM call_eligibility").fetchone()["n"] == 1


def test_each_topic_of_the_document_gets_its_own_answer(client, conn, model_on):
    reg, ncc = two_topics(conn)
    for unit in eligibility.extraction_units(conn):
        client_, _ = _model(f"Financial support to third parties is allowed in topic {NCC} for grants under the following conditions.")
        eligibility.extract_one(conn, unit["url"], scope=unit["scope"], topic=unit["topic"], llm_client=client_)
    assert conn.execute("SELECT count(*) AS n FROM call_eligibility").fetchone()["n"] == 2
    cascade.run(conn, write=True)
    got = {r["id"]: r for r in conn.execute("SELECT id, cascade, cascade_reason FROM call").fetchall()}
    assert (got[ncc]["cascade"], got[ncc]["cascade_reason"]) == (True, "call_document")
    assert (got[reg]["cascade"], got[reg]["cascade_reason"]) == (None, "call_document_other_topic")
    assert "cascade_funding" not in client.get(f"/v1/funding/{reg}").json()["documentEligibility"]["facts"]
    assert client.get(f"/v1/funding/{ncc}").json()["documentEligibility"]["facts"]["cascade_funding"]["value"] is True


def test_a_row_read_with_the_old_prompt_is_asked_again(conn, model_on):
    put(conn, "reg", topic=REGCABH, documents=[doc(PDF)])
    key = f"{PDF}#{REGCABH}"
    hold(conn, key, "call_document", sme_only=(True, "q", None))
    conn.execute("UPDATE call_eligibility SET prompt_version = 3 WHERE url = %s", (key,))
    conn.commit()
    client_, seen = _model("x")
    assert eligibility.extract_one(conn, PDF, topic=(REGCABH, "t"), llm_client=client_)["status"] == "done"
    assert len(seen) == 1
    assert eligibility.extract_one(conn, PDF, topic=(REGCABH, "t"), llm_client=client_)["status"] == "held"


def test_a_row_read_before_topics_is_served_until_the_topic_is_read_and_checked_against_the_topic(client, conn):
    reg, ncc = two_topics(conn)
    hold(conn, PDF, "call_document",
         cascade_funding=(True, f"Financial support to third parties is allowed in topic {NCC} for grants.", "NCC only"),
         min_entities=(2, "q", None))
    for cid, cascade_shown in ((reg, False), (ncc, True)):
        facts = client.get(f"/v1/funding/{cid}").json()["documentEligibility"]["facts"]
        assert ("cascade_funding" in facts) is cascade_shown
        assert facts["min_entities"]["value"] == 2
    hold(conn, f"{PDF}#{REGCABH}", "call_document", min_entities=(5, "q", None))
    facts = client.get(f"/v1/funding/{reg}").json()["documentEligibility"]["facts"]
    assert facts["min_entities"]["value"] == 5, "the topic's own row wins over the document's"
    assert client.get(f"/v1/funding/{ncc}").json()["documentEligibility"]["facts"]["min_entities"]["value"] == 2


def test_the_cli_lists_the_keys_and_accepts_one(conn, capsys):
    from dgate.ops import extract_eligibility

    two_topics(conn)
    assert extract_eligibility.main([]) == 0
    out = capsys.readouterr().out
    assert f"{PDF}#{NCC}" in out and f"{PDF}#{REGCABH}" in out
    assert extract_eligibility.main(["--url", f"{PDF}#{NCC}"]) == 0
    out = capsys.readouterr().out
    assert "1 documents" in out and REGCABH not in out


# ======================================================================= the digest: new and amended

def _first_seen(conn, cid: int, at: datetime) -> None:
    conn.execute("UPDATE call SET first_seen_at = %s WHERE id = %s", (at, cid))
    conn.commit()


def test_a_call_published_before_the_window_is_not_new_because_a_source_read_it_now(conn):
    """D1: the first load of a source reads in calls that opened months ago."""
    old = put(conn, "old", status="open")
    recent = put(conn, "recent", status="open")
    unknown = put(conn, "unknown", status="open")
    opened_long_ago = put(conn, "ola", status="open", opens=(NOW - timedelta(days=200)).date())
    for cid in (old, recent, unknown, opened_long_ago):
        _first_seen(conn, cid, NOW - timedelta(days=1))
    conn.execute("UPDATE call SET published_at = %s WHERE id = %s", ((NOW - timedelta(days=200)).date(), old))
    conn.execute("UPDATE call SET published_at = %s WHERE id = %s", ((NOW - timedelta(days=1)).date(), recent))
    conn.execute("UPDATE call SET published_at = NULL, opens_at = NULL WHERE id = %s", (unknown,))
    conn.commit()
    new = {e["row"]["id"] for e in changes.funding_events(conn, countries=[]) if e["kind"] == "call-new"}
    assert new == {recent, unknown}


def test_a_change_the_publisher_made_before_our_first_reading_is_not_an_amendment(client, conn):
    """D2: PLACSP feeds a notice once per modification; the second version minutes after the first is not news."""
    first = opp("D2-A", published=(NOW - timedelta(days=30)).date(), value=100000.0)
    store(conn, first)
    amend(conn, first, "b", value_amount=200000.0)                 # the same day as the first reading
    later = opp("D2-B", published=(NOW - timedelta(days=30)).date(), value=100000.0)
    oid = store(conn, later)
    amend(conn, later, "b", value_amount=200000.0)
    age(conn, oid, 3, version=1)                                   # read three days ago, amended today
    got = client.get("/v1/changes", params={"scope": "all"}).json()
    assert [(i["kind"], i["tender"]["title"]) for i in got["items"]] == [("amended", "Armoured vehicles")]
    assert got["counts"] == {"new": 0, "amended": 1, "awards": 0}


def test_the_migration_lets_a_row_be_keyed_per_topic_and_names_its_document(conn):
    conn.execute("INSERT INTO call_document_text (url, sha256, pages, chars, text) VALUES ('d', 'x', 1, 1, 't')")
    conn.execute("INSERT INTO call_eligibility (url, fields, model, prompt_version, input_tokens, output_tokens, cost_usd, "
                 "document_url) VALUES ('d#T-1-X', '{}', 'm', 4, 1, 1, 0, 'd')")
    assert conn.execute("SELECT document_url FROM call_eligibility").fetchone()["document_url"] == "d"
    conn.rollback()
