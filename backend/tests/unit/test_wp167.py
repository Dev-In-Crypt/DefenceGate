"""WP-167 (owner, 31 October 2026): Ukraine's EDF association is in force since 16 October 2026, and the call document's own budget total.

The sentences below are the two Ukraine Support Instrument call documents as stored (`call_document_text`, read on production on
31 October 2026, whitespace joined): the PDF text glues the footnote number to the amount ("EUR 184 500 0008").
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from dgate import funding, ukraine, verdict
from dgate.sources import eu_portal

ROOT = Path(__file__).resolve().parents[3]

USI_2026 = ("3. Available budget The estimated available call budget is EUR 184 500 0008. Specific budget information per topic can be "
            "found in the table below: 8 including EUR 180 000 000 from voted EU budget, in line with Commission Implementing Decision "
            "C(2026) 2174 final of 30.3.2026 on the financing of the Europ")
USI_2027 = ("3. Available budget The estimated available call budget is EUR 82 000 0008. Specific budget information per topic can be "
            "found in the table below: Topic Topic budget 1 — Unmanned systems and counter-unmanned systems EUR 82 000 000 The "
            "availability of the call budget still depends on the final adoption of ... submitted by post (see section 11). 8 including "
            "EUR 80 000 000 from voted EU budget, in line with Commission Impl")
EDF_DA = "The estimated available call budget is EUR 422 000 000. Specific budget information per topic can be found in the table below"
DIGITAL = "The estimated available call budget is EUR 4.000.000. Specific budget information per topic can be found in the table below: "


# ---------------------------------------------------------------- the call document's budget

def test_the_two_usi_documents_state_a_total_and_its_voted_eu_budget_part():
    assert eu_portal.document_budget(USI_2026) == {"total": 184_500_000, "voted": 180_000_000}
    assert eu_portal.document_budget(USI_2027) == {"total": 82_000_000, "voted": 80_000_000}


def test_a_document_without_the_footnote_has_a_total_only_and_one_without_the_sentence_none():
    assert eu_portal.document_budget(EDF_DA) == {"total": 422_000_000, "voted": None}
    assert eu_portal.document_budget(DIGITAL) == {"total": 4_000_000, "voted": None}
    assert eu_portal.document_budget("3. Available budget ....... 9") is None and eu_portal.document_budget(None) is None


def row(budget, scope="topic", doc=None):
    return {"budget": budget, "budget_scope": scope, "currency": "EUR", "document_budget": doc}


URL = "https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/edf/wp-call/2026/call-fiche_edf-edip-usi-2026-ls-ira_en.pdf"


def test_the_document_total_is_served_next_to_the_portal_figure_only_where_they_measure_the_same_and_differ():
    usi = {"total": 184_500_000, "voted": 180_000_000, "url": URL}
    # call 118: the portal states 180 000 000, the voted EU budget; the document's total is 184 500 000
    assert funding.document_budget_of(row(180_000_000, doc=usi)) == {
        "amount": 184_500_000.0, "votedEu": 180_000_000.0, "currency": "EUR", "documentUrl": URL}
    assert funding.document_budget_of(row(184_500_000, doc=usi)) is None, "no difference, nothing to add"
    # a topic's own budget of a call whose document states the call's total only: another quantity, not shown
    assert funding.document_budget_of(row(50_000_000, doc={"total": 422_000_000, "voted": None, "url": URL})) is None
    # the portal's figure is the call's (shared by its topics) and the document says another total: shown
    assert funding.document_budget_of(row(400_000_000, "call", {"total": 422_000_000, "voted": None, "url": URL}))["amount"] == 422_000_000
    assert funding.document_budget_of(row(None, doc=usi)) is None and funding.document_budget_of(row(180_000_000)) is None
    assert funding.document_budget_of(row(180_000_000, doc={**usi, "url": "javascript:alert(1)"})) is None


# ---------------------------------------------------------------- the flag

EDF_FACT = {"eligible_countries": {"value": "x", "quote": "listed EEA countries and countries associated to the EDF Programme (‘EDF associated "
                                   "countries’)", "note": None, "confidence": 1.0, "scope": "call_document"}}


def edf(deadline):
    return {"programme_code": "EDF", "topic_code": "EDF-2027-DA-X", "eligibility_text": None, "deadline_at": deadline}


def test_an_open_edf_call_is_open_to_ukraine_with_the_commissions_sentence():
    for deadline in (datetime(2027, 3, 1, tzinfo=timezone.utc), datetime(2026, 10, 15, 22, tzinfo=timezone.utc), None):
        flag, reason, evidence = ukraine.decide(edf(deadline), EDF_FACT)
        assert (flag, reason) == (True, "edf_association"), deadline
        assert ukraine.EDF_IN_FORCE in evidence and "16 October 2026" in evidence


def test_an_edf_call_that_closed_before_16_october_2026_keeps_its_answer_and_says_why():
    for deadline in (datetime(2026, 9, 29, 15, tzinfo=timezone.utc), datetime(2026, 10, 15, 21, 59, tzinfo=timezone.utc)):
        flag, reason, evidence = ukraine.decide(edf(deadline), EDF_FACT)
        assert (flag, reason) == (None, "edf_closed_before_association"), deadline
        assert evidence.startswith("This call closed before 16 October 2026") and ukraine.EDF_PENDING in evidence


def test_the_call_document_still_comes_first():
    no = {"eligible_countries": {**EDF_FACT["eligible_countries"], "quote": "Legal entities established in Ukraine are not eligible."}}
    assert ukraine.decide(edf(None), no)[:2] == (False, "call_document")


def test_the_reason_names_and_the_web_agree():
    assert "edf_association_unconfirmed" not in ukraine.REASONS and {"edf_association", "edf_closed_before_association"} <= set(ukraine.REASONS)
    web = (ROOT / "web" / "lib" / "ukraine.ts").read_text(encoding="utf-8")
    assert all(f"'{r}'" in web for r in ("edf_association", "edf_closed_before_association", "edf_association_unconfirmed"))
    assert ukraine.EDF_IN_FORCE_URL in web and ukraine.EDF_IN_FORCE in web


# ---------------------------------------------------------------- the eligibility check

def test_the_verdict_counts_ukraine_as_associated_to_the_edf_except_for_a_call_closed_before_the_day():
    fact = {**EDF_FACT["eligible_countries"], "value": EDF_FACT["eligible_countries"]["quote"]}     # the verdict reads the value
    ctx ={"programme": "EDF", "topic": "EDF-2027-DA-X"}
    assert verdict.country_status(fact, "UA", ctx) == ("yes", verdict.EDF_UA_YES)
    assert verdict.country_status(fact, "UA", {**ctx, "ukraineBeforeAssociation": True}) == ("check", verdict.EDF_UA_BEFORE)
    assert verdict.country_status(fact, "NO", {**ctx, "ukraineBeforeAssociation": True})[0] == "yes", "Norway is not touched"
    # EDIP stays as it was: Ukraine is not an associated country of the Programme
    assert verdict.country_status({**fact, "quote": "EDIP associated countries", "value": "EU Member States and EDIP associated countries"},
                                  "UA", {"programme": "EDF", "topic": "EDF-EDIP-P-2027-FNLC-CPA-X"})[0] == "no"
    web = (ROOT / "web" / "lib" / "eligibility-check.ts").read_text(encoding="utf-8")
    assert verdict.EDF_UA_YES in web and verdict.EDF_UA_BEFORE in web, "the browser says the same words"
