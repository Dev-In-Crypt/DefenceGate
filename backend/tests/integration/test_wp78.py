"""WP-78: forthcoming calls are read before closed ones; the EIC work programme is read per topic.

Against a real Postgres, the language model a fake client."""

from __future__ import annotations

import json

import httpx
import pytest

from dgate import eligibility
from tests.integration.test_wp31 import doc, put
from tests.integration.test_wp35 import client, model_on  # noqa: F401 - fixtures

pytestmark = pytest.mark.integration

EIC = "https://eic.ec.europa.eu/document/download/52598755_en?filename=EIC-Work-Programme-2026.pdf"
ACC = "HORIZON-EIC-2026-ACCELERATOR-01"
OWN = "The EIC Accelerator supports single start-ups and SMEs established in a Member State or an Associated Country."
OTHER = "For HORIZON-EIC-2026-PATHFINDEROPEN-01 consortia need at least three entities from three countries."


def test_units_of_forthcoming_calls_come_before_units_of_closed_calls(conn):
    put(conn, "old", status="closed", documents=[doc("https://example.test/a.pdf")])
    put(conn, "old2", status="closed", documents=[doc("https://example.test/a2.pdf")])
    put(conn, "soon", status="forthcoming", documents=[doc("https://example.test/b.pdf")])
    put(conn, "now", status="open", documents=[doc("https://example.test/c.pdf")])
    units = eligibility.extraction_units(conn)
    assert [u["url"] for u in units][:2] == ["https://example.test/c.pdf", "https://example.test/b.pdf"]
    assert units[1]["forthcoming_calls"] == 1


def _model():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["input"])
        out = {name: {"value": None, "confidence": 0.0, "quote": None, "note": None} for name in eligibility.FIELDS}
        out["eligible_countries"] = {"value": "Member States or Associated Countries", "confidence": 1.0, "quote": OWN,
                                     "note": None}
        out["min_entities"] = {"value": 3, "confidence": 1.0, "quote": OTHER, "note": None}
        return httpx.Response(200, json={"status": "completed", "usage": {"input_tokens": 100, "output_tokens": 50},
                                         "output": [{"type": "message", "content": [{"type": "output_text",
                                                                                     "text": json.dumps(out)}]}]})
    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_the_eic_work_programme_is_read_for_each_topic_and_told_which(client, conn, model_on, monkeypatch):  # noqa: F811
    monkeypatch.setattr(eligibility, "fetch_text", lambda url, client=None: ("abc", 9, f"{OWN} {OTHER}"))
    cid = put(conn, "acc", topic=ACC, documents=[doc(EIC, "EIC Work Programme 2026")])
    put(conn, "step", topic="HORIZON-EIC-2026-STEP", documents=[doc(EIC, "EIC Work Programme 2026")])
    units = [u for u in eligibility.extraction_units(conn) if u["scope"] == "general"]
    assert sorted(u["key"] for u in units) == sorted([f"{EIC}#{ACC}", f"{EIC}#HORIZON-EIC-2026-STEP"])
    unit = next(u for u in units if u["key"] == f"{EIC}#{ACC}")
    client_, seen = _model()
    report = eligibility.extract_one(conn, unit["url"], scope="general", topic=unit["topic"], llm_client=client_)
    assert report["url"] == f"{EIC}#{ACC}" and report["status"] == "done"
    assert ACC in seen[0] and "this topic only" in seen[0]
    row = conn.execute("SELECT scope, document_url, fields FROM call_eligibility WHERE url = %s", (f"{EIC}#{ACC}",)).fetchone()
    assert (row["scope"], row["document_url"]) == ("general", EIC)
    assert row["fields"]["min_entities"].get("other_topic") is True, "a quote naming another topic is refused"
    facts = client.get(f"/v1/funding/{cid}").json()["documentEligibility"]["facts"]
    assert set(facts) == {"eligible_countries"} and facts["eligible_countries"]["scope"] == "programme"   # WP-93: the EIC text read for the topic is its own
    assert eligibility.extract_one(conn, unit["url"], scope="general", topic=unit["topic"],
                                   llm_client=client_)["status"] == "held"
    assert len(seen) == 1
