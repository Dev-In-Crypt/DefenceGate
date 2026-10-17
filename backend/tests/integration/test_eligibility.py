"""Eligibility extraction end to end with a fake model and a fake document (no network)."""

from __future__ import annotations

import json

import httpx
import pytest

from dgate import config, eligibility, llm

pytestmark = pytest.mark.integration

URL = "https://example.test/call-fiche_demo_en.pdf"
TEXT = ("Section 6. Eligible countries. Applicants must be legal entities established in Member States "
        "or associated countries. Consortia need at least three independent legal entities.")


def _body(fields):
    return {"status": "completed", "usage": {"input_tokens": 1000, "output_tokens": 200},
            "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(fields)}]}]}


def _fields():
    blank = {"value": None, "confidence": 0.0, "quote": None}
    f = {name: dict(blank) for name in eligibility.FIELDS}
    f["eligible_countries"] = {"value": "Member States and associated countries", "confidence": 0.95,
                               "quote": "Applicants must be legal entities established in Member States or associated countries."}
    f["min_entities"] = {"value": 3, "confidence": 0.9, "quote": "at least five independent legal entities"}  # not in the text
    return f


@pytest.fixture()
def model_on(monkeypatch):
    monkeypatch.setenv("DGATE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DGATE_OPENAI_MODEL", "test-model")
    monkeypatch.setenv("DGATE_LLM_MONTHLY_CAP_USD", "5")
    config.reset_cache()
    yield
    config.reset_cache()


def _client(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.headers["authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "test-model" and body["store"] is False
        assert body["text"]["format"]["strict"] is True
        return httpx.Response(200, json=_body(_fields()))
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_extract_stores_the_facts_checks_the_quotes_and_records_the_cost(conn, model_on, monkeypatch):
    monkeypatch.setattr(eligibility, "fetch_text", lambda url, client=None: ("abc", 3, TEXT))
    calls: list = []
    report = eligibility.extract_one(conn, URL, llm_client=_client(calls))
    assert report["status"] == "done" and report["stated"] == 2 and report["verified"] == 1
    row = conn.execute("SELECT fields, cost_usd FROM call_eligibility WHERE url = %s", (URL,)).fetchone()
    assert row["fields"]["eligible_countries"]["verified"] is True
    assert row["fields"]["min_entities"]["verified"] is False
    assert row["fields"]["min_entities"]["confidence"] == eligibility.UNVERIFIED_CAP
    assert float(row["cost_usd"]) == pytest.approx(0.0006, abs=1e-5)       # 1000 in, 200 out at 0.30 / 1.50 per million
    assert float(llm.month_spent(conn)) == pytest.approx(float(row["cost_usd"]))
    # Held: a second run asks nothing.
    again = eligibility.extract_one(conn, URL, llm_client=_client(calls))
    assert again["status"] == "held" and len(calls) == 1


def test_the_monthly_cap_stops_the_call_before_anything_is_sent(conn, model_on, monkeypatch):
    monkeypatch.setenv("DGATE_LLM_MONTHLY_CAP_USD", "0.000001")
    config.reset_cache()
    monkeypatch.setattr(eligibility, "fetch_text", lambda url, client=None: ("abc", 3, TEXT))
    calls: list = []
    with pytest.raises(llm.CapReached):
        eligibility.extract_one(conn, URL, llm_client=_client(calls))
    assert calls == []
    assert conn.execute("SELECT count(*) AS n FROM call_eligibility").fetchone()["n"] == 0


def test_no_key_means_no_call(conn, monkeypatch):
    monkeypatch.setenv("DGATE_OPENAI_API_KEY", "")
    config.reset_cache()
    monkeypatch.setattr(eligibility, "fetch_text", lambda url, client=None: ("abc", 3, TEXT))
    with pytest.raises(llm.LLMError):
        eligibility.extract_one(conn, URL, llm_client=_client([]))
    config.reset_cache()


def test_a_model_error_costs_nothing_and_stores_nothing(conn, model_on, monkeypatch):
    monkeypatch.setattr(eligibility, "fetch_text", lambda url, client=None: ("abc", 3, TEXT))
    bad = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400, json={"error": "bad"})))
    with pytest.raises(llm.LLMError):
        eligibility.extract_one(conn, URL, llm_client=bad)
    assert llm.month_spent(conn) == 0
    assert conn.execute("SELECT count(*) AS n FROM call_eligibility").fetchone()["n"] == 0
