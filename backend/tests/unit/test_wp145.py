"""WP-145: EDIP calls whose own document says Ukrainian entities cannot receive funding.

The stored call documents of the 10 EDIP calls (production, 26 October 2026; the passages that name Ukraine, the eligible countries and
funding are in tests/fixtures/wp145_edip_documents.json) never say so: they name Ukraine as a member of a SEAP, as a state that designates
a procurement agent or that receives additional quantities. So no EDIP call is marked, and the flag stays the Regulation's answer
(`programme_rule`). Where a document does say it, the reason is `call_document_no_funding`, the evidence its sentence, and the verdict
blocks a Ukrainian applicant with it (web/lib/wp145.check.ts is the browser's twin)."""

from __future__ import annotations

import json
from pathlib import Path

from dgate import ukraine, verdict

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DOCS = json.loads((FIXTURES / "wp145_edip_documents.json").read_text(encoding="utf-8"))
DATA = Path(__file__).resolve().parents[3] / "web" / "lib" / "data"
SAID = "Entities established in Ukraine are not eligible to receive funding under this call."
# the EDIP calls and their documents on production (call.conditions_raw.documents, label "Call document")
CALLS = {
    "call-fiche_edf-edip-p-2026-fnlc-cpa_en.pdf": ["EDF-EDIP-P-2026-FNLC-CPA-AMEW", "EDF-EDIP-P-2026-FNLC-CPA-CDS"],
    "call-fiche_edf-edip-p-2027-fnlc-cpa_en.pdf": ["EDF-EDIP-P-2027-FNLC-CPA-AMDS", "EDF-EDIP-P-2027-FNLC-CPA-C5ISRS", "EDF-EDIP-P-2027-FNLC-CPA-GNPS"],
    "call-fiche_edf-edip-p-2026-2027-fnlc-sa_en.pdf": ["EDF-EDIP-P-2026-2027-FNLC-SA-SEAP"],
    "call-fiche_edf-edip-p-2026-ls-ira_en.pdf": ["EDF-EDIP-P-2026-LS-IRA-EC"],
    "call-fiche_edf-edip-p-2027-ls-ira_en.pdf": ["EDF-EDIP-P-2027-LS-IRA-KEC", "EDF-EDIP-P-2027-LS-IRA-PE"],
    "call-fiche_edf-edip-p-2026-fnlc-csa_en.pdf": ["EDF-EDIP-P-2026-FNLC-CSA-PREP"],
}


def _doc(name: str) -> str:
    return next(text for url, text in DOCS.items() if url.endswith("/" + name))


def test_no_stored_edip_call_document_says_ukrainian_entities_cannot_receive_funding():
    assert sum(len(v) for v in CALLS.values()) == 10 and len(DOCS) == 6
    for name, topics in CALLS.items():
        text = _doc(name)
        assert "Ukrain" in text, name
        assert ukraine.no_funding_sentence(text) is None, name
        for topic in topics:
            flag, reason, _ = ukraine.decide({"programme_code": "EDF", "topic_code": topic, "eligibility_text": None, "document_text": text}, {})
            assert (flag, reason) == (None, "programme_rule"), topic


def test_a_sentence_that_refuses_funding_to_ukrainian_entities_is_found_and_the_roles_of_ukraine_are_not():
    for said in (SAID, "Ukrainian entities may participate as associated partners, without any funding under the grant.",
                 "Legal entities controlled by Ukraine cannot be beneficiaries."):
        assert ukraine.no_funding_sentence(f"Eligibility. In order to be eligible, the applicants must: be legal entities. {said} Other text.") == said
    for not_it in ("Associated countries and Ukraine can normally be also part of the SEAP.",
                   "for instance a SEAP that includes Ukraine as a member would not be eligible",
                   "Legal entities established in the non-government controlled areas of Ukraine are not eligible.",
                   "If Ukraine and/or Moldova receive at least 5% of the value of the common procurement contract, bonus of 5%."):
        assert ukraine.no_funding_sentence(not_it) is None, not_it
    # the PDF breaks lines inside a sentence
    assert ukraine.no_funding_sentence("Entities established in\nUkraine are not eligible to receive\nfunding.") == "Entities established in Ukraine are not eligible to receive funding."


def test_an_edip_document_that_says_it_decides_the_reason_and_a_usi_call_never_gets_it():
    edip = {"programme_code": "EDF", "topic_code": "EDF-EDIP-P-2027-LS-IRA-PE", "eligibility_text": None, "document_text": f"x. {SAID} y."}
    assert ukraine.decide(edip, {}) == (None, ukraine.NO_FUNDING, SAID)
    assert ukraine.NO_FUNDING in ukraine.REASONS
    usi = {**edip, "topic_code": "EDF-EDIP-USI-2027-LS-IRA-CUXS"}
    assert ukraine.decide(usi, {})[1] != ukraine.NO_FUNDING
    edf = {**edip, "topic_code": "EDF-2026-DA-GROUND-MBT"}
    assert ukraine.decide(edf, {})[1] != ukraine.NO_FUNDING


def _fit(key: str, said: str | None) -> dict:
    data = json.loads((DATA / "wp93-pairs.json").read_text(encoding="utf-8"))
    c = data["after"]["117"]
    answers = data["requests"][key]["profile"]
    return verdict.call_fit({"state": c["state"], "facts": c["facts"], "programme": c["programme"], "topic": c["topic"], "ukraineNoFunding": said},
                            answers, data["assessments"][key])


def test_the_verdict_blocks_a_ukrainian_applicant_with_the_documents_sentence_and_nobody_else():
    ua = _fit("P5", SAID)
    assert ua["fit"] == "no" and verdict.UA_NO_FUNDING in ua["blockedBy"]
    line = next(x for x in ua["result"]["lines"] if x["key"] == "ukraine_funding")
    assert (line["label"], line["verdict"], line["reason"], line["quote"]) == (verdict.UA_NO_FUNDING, "no", verdict.UA_NO_FUNDING_REASON, SAID)
    assert not any(x["key"] == "ukraine_funding" for x in _fit("P5", None)["result"]["lines"])
    es = _fit("P1", SAID)
    assert not any(x["key"] == "ukraine_funding" for x in es["result"]["lines"]) and verdict.UA_NO_FUNDING not in es["blockedBy"]
