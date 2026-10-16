"""What a call page says about the funder, who can apply and the official documents
(ux-funding F2, F6, F9). The texts are shortened from stored topic documents of 24 September 2026."""

from __future__ import annotations

from dgate import funding
from dgate.sources import eu_portal

EDF_TEXT = (
    "Conditions 1. Admissibility conditions: Proposal page limit and layout described in section 5 of the "
    "call document . Proposal page limits and layout: described in Part B of the Application Form available "
    "in the Submission System. 2. Eligible countries described in section 6 of the call document . "
    "3. Other eligibility conditions described in section 6 of the call document . "
    "4. Financial and operational capacity and exclusion described in section 7 of the call document .")

CL3_TEXT = (
    "General conditions 1. Admissibility Conditions: Proposal page limit and layout described in Annex A. "
    "2. Eligible Countries described in Annex B of the Work Programme General Annexes. A number of non-EU "
    "countries have made specific provisions. 3. Other Eligible Conditions The following additional "
    "eligibility criteria apply: this topic requires at least 2 Police Authorities from 2 Member States. "
    "4. Financial and operational capacity and exclusion described in Annex C.")


def test_who_can_apply_takes_the_two_sections_in_the_sources_words():
    rows = funding.who_can_apply(EDF_TEXT, [])
    assert rows == [
        {"label": "Eligible countries", "value": "Described in section 6 of the call document."},
        {"label": "Other eligibility conditions", "value": "Described in section 6 of the call document."},
    ]


def test_a_section_runs_to_the_next_numbered_heading_and_keeps_the_extra_criteria():
    rows = {r["label"]: r["value"] for r in funding.who_can_apply(CL3_TEXT, [])}
    assert rows["Eligible countries"].startswith("Described in Annex B")
    assert rows["Eligible countries"].endswith("specific provisions.")
    assert "at least 2 Police Authorities" in rows["Other eligibility conditions"]
    assert "Financial" not in rows["Other eligibility conditions"]


def test_no_text_or_no_such_section_is_an_empty_answer_not_a_guess():
    assert funding.who_can_apply(None, []) == []
    assert funding.who_can_apply("Conditions: see the call.", []) == []


def test_a_long_section_is_cut_at_a_word_with_an_ellipsis():
    text = "2. Eligible countries " + "word " * 400 + "3. Other eligibility conditions x"
    value = funding.who_can_apply(text, [])[0]["value"]
    assert len(value) <= funding.WHO_MAX_CHARS + 1 and value.endswith("…")


def test_the_applicants_of_a_national_call_come_from_its_structured_rows():
    terms = [{"label": "Applicants", "value": "SME, University"}, {"label": "Programme type", "value": "FENG"}]
    assert funding.who_can_apply(None, terms) == [{"label": "Applicants", "value": "SME, University"}]


def test_the_funder_is_the_issuing_body_the_programme_or_the_commission():
    assert funding.funder_of("PL-NCBR", "Narodowe Centrum Badan i Rozwoju (NCBR)", "NCBR competitions") \
        == "Narodowe Centrum Badan i Rozwoju (NCBR)"
    assert funding.funder_of("PL-NCBR", None, "NCBR competitions") == "NCBR competitions"
    assert funding.funder_of("EDF", None, "European Defence Fund") == "European Commission"
    assert funding.funder_of("HORIZON", "  ", "Horizon Europe") == "European Commission"


CONDITIONS_HTML = (
    '<div><h4>Conditions</h4><p>described in section 6 of the <u><a href="https://ec.europa.eu/info/'
    'funding-tenders/opportunities/docs/2021-2027/edf/wp-call/2027/call-fiche_x_en.pdf" target="_blank">'
    'call document</a></u>.</p><ul><li><a href="https://ec.europa.eu/info/funding-tenders/opportunities/docs/'
    '2021-2027/edf/temp-form/af/af_edip-and-usi_en.pdf">Application Form (EDIP and USI)</a></li>'
    '<li><a href="https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/edf/wp-call/2027/'
    'call-fiche_x_en.pdf">call document</a></li>'
    '<li><a href="https://cybersecurity-centre.europa.eu/document/abc_en">Work Programme &amp; annexes</a></li>'
    '<li><a href="http://ec.europa.eu/plain.pdf">Plain http</a></li>'
    '<li><a href="https://evil.example.com/a.pdf">Elsewhere</a></li>'
    '<li><a href="mailto:someone@example.com">Mail</a></li>'
    '<li><a href="https://ec.europa.eu/empty.pdf"> </a></li></div>')


def test_the_connector_keeps_the_commission_hosted_documents_once_each_in_the_sources_words():
    docs = eu_portal.call_documents({"conditions": CONDITIONS_HTML})
    assert [d["label"] for d in docs] == ["Call document", "Application Form (EDIP and USI)",
                                          "Work Programme & annexes"]
    assert all(d["url"].startswith("https://") for d in docs)


def test_no_conditions_block_is_no_documents():
    assert eu_portal.call_documents({}) == []
    assert eu_portal.call_documents({"conditions": 5}) == []


def test_documents_are_stored_with_the_detail_fields_and_served_only_as_https_links():
    fields = eu_portal.detail_fields({"conditions": CONDITIONS_HTML, "identifier": "X"}, "X")
    stored = fields["conditions_raw"]["documents"]
    assert len(stored) == 3
    served = funding.documents_of({"documents": [*stored, {"label": "Bad", "url": "javascript:alert(1)"},
                                                  {"label": "Plain", "url": "http://ec.europa.eu/x"},
                                                  "junk", {"url": "https://ec.europa.eu/y"}]})
    assert [d["label"] for d in served] == ["Call document", "Application Form (EDIP and USI)",
                                            "Work Programme & annexes"]
