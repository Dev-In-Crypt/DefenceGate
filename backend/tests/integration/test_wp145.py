"""WP-145: the stored call document of an EDIP call that says Ukrainian entities cannot receive funding marks the call
(`ukraine.run`, the ops step `dgate.ops.ukraine_flags`), the list and the detail serve it, the list filters by it, and the
verdict of a Ukrainian applicant is blocked with its sentence. A silent document and a USI call are not marked.

Against a real Postgres. No language model and no network: the document texts are rows written by the test."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dgate import api, stats, ukraine
from dgate.readiness import api as readiness_api
from tests.integration.test_wp31 import doc, hold, put

pytestmark = pytest.mark.integration

BASE = "https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/edf/wp-call/2027/"
SAID = "Entities established in Ukraine are not eligible to receive funding under this call."
FIXTURE = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "wp145_edip_documents.json").read_text(encoding="utf-8"))
SILENT = next(t for u, t in FIXTURE.items() if u.endswith("call-fiche_edf-edip-p-2027-ls-ira_en.pdf"))
WP93 = json.loads((Path(__file__).resolve().parents[3] / "web" / "lib" / "data" / "wp93-pairs.json").read_text(encoding="utf-8"))
COUNTRIES = ("be established in one of the eligible countries, i.e.: EU Member States (including OCTs) and listed EEA countries "
             "and countries associated to the EDIP Programme")


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    readiness_api.reset_cache()
    yield
    stats.reset_cache()
    readiness_api.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def stored(conn, url: str, text: str) -> None:
    conn.execute("INSERT INTO call_document_text (url, sha256, pages, chars, text) VALUES (%s, 'x', 1, %s, %s)", (url, len(text), text))
    conn.commit()


def test_a_document_that_refuses_funding_to_ukrainian_entities_marks_its_edip_call_and_nothing_else(client, conn):
    stored(conn, BASE + "said.pdf", f"6. Eligibility\nIn order to be eligible, the applicants must: be legal entities.\n{SAID}\nOther text.")
    stored(conn, BASE + "silent.pdf", SILENT)
    stored(conn, BASE + "usi.pdf", f"Eligibility. {SAID}")
    said = put(conn, "said", programme="EDF", topic="EDF-EDIP-P-2027-LS-IRA-PE", documents=[doc(BASE + "said.pdf")])
    hold(conn, BASE + "said.pdf", "call_document", eligible_countries=(COUNTRIES, COUNTRIES, None))
    silent = put(conn, "silent", programme="EDF", topic="EDF-EDIP-P-2027-LS-IRA-KEC", documents=[doc(BASE + "silent.pdf")])
    usi = put(conn, "usi", programme="EDF", topic="EDF-EDIP-USI-2027-LS-IRA-CUXS", documents=[doc(BASE + "usi.pdf")])
    # a document that is not the call document (the online manual, say) is not read for it
    other = put(conn, "other", programme="EDF", topic="EDF-EDIP-P-2026-LS-IRA-EC", documents=[doc(BASE + "usi.pdf", "Online Manual")])

    report = ukraine.run(conn, write=False)
    assert report["no_funding"] == 1 and report["calls"] == 4
    assert conn.execute("SELECT count(*) AS n FROM call WHERE open_to_ukraine_reason IS NOT NULL").fetchone()["n"] == 0, "a report writes nothing"
    assert ukraine.run(conn, write=True)["no_funding"] == 1
    got = {r["id"]: r for r in conn.execute("SELECT id, open_to_ukraine AS flag, open_to_ukraine_reason AS reason, "
                                            "open_to_ukraine_evidence AS evidence FROM call").fetchall()}
    assert (got[said]["flag"], got[said]["reason"], got[said]["evidence"]) == (None, ukraine.NO_FUNDING, SAID)
    assert (got[silent]["flag"], got[silent]["reason"]) == (None, "programme_rule"), "the document is silent: the Regulation's answer as before"
    assert (got[other]["flag"], got[other]["reason"]) == (None, "programme_rule")
    assert got[usi]["reason"] != ukraine.NO_FUNDING and got[usi]["flag"] is True
    assert ukraine.run(conn, write=True)["changed"] == 0, "a second run changes nothing"

    # the list: the badge's field and the filter
    everything = client.get("/v1/funding", params={"status": "all"}).json()
    assert {c["id"]: c["ukraineNoFunding"] for c in everything["items"]} == {str(said): True, str(silent): False, str(usi): False, str(other): False}
    only = client.get("/v1/funding", params={"status": "all", "uaNoFunding": "true"}).json()
    assert only["total"] == 1 and [c["id"] for c in only["items"]] == [str(said)]
    assert client.get("/v1/funding", params={"uaNoFunding": "yes"}).status_code == 422
    # the detail: the line's reason and the document's sentence
    body = client.get(f"/v1/funding/{said}").json()
    assert body["ukraineNoFunding"] is True and body["ukraineBasis"] == {"reason": ukraine.NO_FUNDING, "evidence": SAID}
    # the badge's facts carry the sentence, and the verdict of a Ukrainian applicant is blocked with it
    facts = client.get("/v1/fit/facts", params={"ids": f"{said},{silent}"}).json()["items"]
    assert facts[str(said)]["ukraineNoFunding"] == SAID and facts[str(silent)]["ukraineNoFunding"] is None
    answers = WP93["requests"]["P5"]["profile"]
    assert answers["country"] == "UA"
    v = readiness_api.call_verdict(conn, said, answers, {"assessments": [], "roadmap": []})
    assert v["fit"] == "no" and "No funding for Ukrainian entities" in v["blockedBy"]
    line = next(x for x in v["lines"] if x["key"] == "ukraine_funding")
    assert line["verdict"] == "no" and line["reason"].startswith("The call document says Ukrainian entities cannot receive funding")
    assert not any(x["key"] == "ukraine_funding" for x in readiness_api.call_verdict(conn, silent, answers, {"assessments": [], "roadmap": []})["lines"])
