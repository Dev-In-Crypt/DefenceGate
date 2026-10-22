"""WP-78: the open calls that had no readable source (Chips JU guides, the EIC work programme per topic)."""

from __future__ import annotations

import httpx
import pytest

from dgate import eligibility
from tests.unit.test_eligibility import PDF

CHIPS = "https://www.chips-ju.europa.eu"
GUIDE = f"{CHIPS}/CallDocumentLink/?id=7FEE6E1B"
APPENDIX = f"{CHIPS}/viewfile/?id=a8627a97"
EIC = "https://eic.ec.europa.eu/document/download/52598755_en?filename=EIC-Work-Programme-2026.pdf"
ACC = "HORIZON-EIC-2026-ACCELERATOR-01"


def test_a_chips_ju_viewer_page_is_followed_to_its_file_on_the_same_site():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if "/File/download.aspx" in str(request.url):
            return httpx.Response(200, content=PDF, headers={"content-type": "application/octet-stream"})
        page = ("<script>const fileUrl = '/File/download.aspx?entity=rec_calldocuments&attribute=rec_file&ID=7fee';"
                "const fileName = 'Guide_for_applicants_AI_SG.pdf';</script>")
        return httpx.Response(200, text=page, headers={"content-type": "text/html; charset=utf-8"})
    _, pages, text = eligibility.fetch_text(GUIDE, httpx.Client(transport=httpx.MockTransport(handler)))
    assert pages == 1 and "Hello" in text
    assert seen[1] == f"{CHIPS}/File/download.aspx?entity=rec_calldocuments&attribute=rec_file&ID=7fee"


def test_a_viewer_page_naming_a_file_on_another_site_is_not_followed():
    page = "<script>const fileUrl = 'https://elsewhere.test/File/download.aspx?ID=1';</script>"
    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, text=page, headers={"content-type": "text/html"})))
    with pytest.raises(ValueError, match="not a PDF"):
        eligibility.fetch_text(GUIDE, http)


def _docs(*labels_urls):
    return {"documents": [{"label": label, "url": url} for label, url in labels_urls]}


def test_a_chips_ju_guide_for_applicants_is_read_as_the_call_document_of_its_topic():
    cond = _docs(("Appendix 8 of the Chips JU Workprogramme", APPENDIX),
                 ("Guide for applicants - DIGITAL-JU-CHIPS-2026-AI1-SG", GUIDE),
                 ("Ownership Control Declaration form template", f"{CHIPS}/x"))
    got = eligibility.sources_of(cond, None, "DIGITAL-JU-CHIPS-2026-AI1-SG")
    assert [(s.scope, s.key, s.document) for s in got] == [
        ("call_document", f"{GUIDE}#DIGITAL-JU-CHIPS-2026-AI1-SG", GUIDE)]


def test_without_a_guide_the_work_programme_appendix_is_read_for_the_topic():
    cond = _docs(("Appendix 8 of Work Programme - Chips for Europe Initiative", APPENDIX), ("Call Details", f"{CHIPS}/c"))
    got = eligibility.sources_of(cond, None, "DIGITAL-JU-CHIPS-2026-SG-JAPAN")
    assert [(s.scope, s.document, s.topic) for s in got] == [("call_document", APPENDIX, "DIGITAL-JU-CHIPS-2026-SG-JAPAN")]


def test_an_appendix_of_another_work_programme_is_not_taken_for_a_call_document():
    annex = ("https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/horizon/wp-call/2026-2027/"
             "wp-15-general-annexes_horizon-2026-2027_en.pdf")
    cond = _docs(("Appendix 1 of the Horizon Europe Work Programme", "https://example.test/app1.pdf"), ("Annex A", annex))
    assert [s.scope for s in eligibility.sources_of(cond, None, "HORIZON-CL3-2026-01-BM-03")] == ["general"]


def test_a_call_document_still_wins_over_a_guide_and_an_appendix():
    cond = _docs(("Guide for applicants", GUIDE), ("Call document", "https://example.test/call.pdf"),
                 ("Appendix 6.v6 of the Chips JU Workprogramme", APPENDIX))
    assert [s.document for s in eligibility.sources_of(cond, None, "T-1-X")] == ["https://example.test/call.pdf"]


def test_the_eic_work_programme_is_read_once_per_topic_and_the_row_read_before_stays_served():
    cond = _docs(("EIC Work Programme 2026", EIC))
    (src,) = eligibility.sources_of(cond, None, ACC)
    assert (src.scope, src.key, src.document, src.topic, src.url) == ("general", f"{EIC}#{ACC}", EIC, ACC, EIC)
    assert eligibility.sources_of(cond, None)[0].key == EIC, "without a topic code the row is the document's"
    old = {"fields": {"eligible_countries": {"value": "Member States", "quote": "q", "verified": True,
                                             "confidence": 1.0, "note": None}}, "extracted_at": "2026-10-18"}
    assert eligibility.assemble([src], {EIC: old}, ACC, "ACC")["facts"]["eligible_countries"]["value"] == "Member States"
    mine = {"fields": {"eligible_countries": {"value": "Member States or Associated Countries", "quote": "q2",
                                              "verified": True, "confidence": 1.0, "note": None}},
            "extracted_at": "2026-10-22"}
    got = eligibility.assemble([src], {EIC: old, f"{EIC}#{ACC}": mine}, ACC, "ACC")
    assert got["facts"]["eligible_countries"]["value"] == "Member States or Associated Countries"


def test_the_horizon_general_annexes_stay_one_row_for_all_topics():
    annex = ("https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/horizon/wp-call/2026-2027/"
             "wp-15-general-annexes_horizon-2026-2027_en.pdf")
    (src,) = eligibility.sources_of(_docs(("Annex A", annex)), None, "HORIZON-CL3-2026-01-BM-03")
    assert (src.key, src.document, src.topic) == (annex, None, None)
