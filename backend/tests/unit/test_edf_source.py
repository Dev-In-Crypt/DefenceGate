"""The EDF factsheet source (WP-26): the file names of five call years, the results pages, the
text of a PDF without its technical description, and the quote check. No network, no model."""

from __future__ import annotations

import pytest

from dgate.sources import edf_factsheets as edf
from tests.pdfmaker import MEMBERS, SECRET, factsheet_pdf

# Real file names from the five results pages of 17 October 2026: (year, name, acronym, GA, action, step)
NAMES = [
    (2025, "FACTSHEET_EDF_2025_DA_SI_GROUND_DAMM_101304876_EURODAMM.pdf", "EURODAMM", "101304876", "DA", False),
    (2025, "FACTSHEET_EDF_2025_LS_RA_SI_CYBER_3RAV_STEP_101304998_STRATUS.pdf", "STRATUS", "101304998", "RA", True),
    (2025, "FACTSHEET_EDF_2025_CSA_101305005_EOA-V2.pdf", "EOA-V2", "101305005", "CSA", False),
    (2025, "FACTSHEET_EDF_2025_LS_DA_SME_NT_101305039_GEDIRIS_0.pdf", "GEDIRIS", "101305039", "DA", False),
    (2025, "FACTSHEET_EDF_2025_RA_SGA_MCBRN_MCM_STEP_101254210_RESILIENCE_R_2025.pdf",
     "RESILIENCE_R_2025", "101254210", "RA", True),
    (2024, "FACTSHEET_EDF_2024_HYROGLIVE.pdf", "HYROGLIVE", None, None, False),
    (2024, "FACTSHEET_EDF_2024_DA_C4ISR_COMS_STEP_101218568_5G_COMPAD_2_0.pdf",
     "5G_COMPAD_2", "101218568", "DA", True),
    (2023, "FACTSHEET_EDF-2023-LS-DA-SME-NT_101168111_MPortISTAR.pdf", "MPortISTAR", "101168111", "DA", False),
    (2023, "EDF-2023-RA-SPACE-PSA BODYGUARD.pdf", "BODYGUARD", None, "RA", False),
    (2023, "EDF-2023-RA-SENS-EMSP_FESPAN.pdf", "FESPAN", None, "RA", False),
    (2023, "EDF-2023-DA-AIR-STFS NG-MIMA.pdf", "NG-MIMA", None, "DA", False),
    (2023, "EDF-2023-RA-SI-MATCOMP-HPM_101168222_ADMIRABLE.pdf", "ADMIRABLE", "101168222", "RA", False),
    (2023, "EDF-2023-_DA-MCBRN-FCS CBRN SoS.pdf", "CBRN SoS", None, "DA", False),
    (2023, "EDF-2023-DA-GROUND-IFS FIRES 2.pdf", "FIRES 2", None, "DA", False),
    (2023, "FACTSHEET_EDF-2023-LS-RA-SMERO-NT_101168102_CAPSARII v2.pdf", "CAPSARII", "101168102", "RA", False),
    (2022, "REACTII-Factsheet_EDF22.pdf", "REACTII", None, None, False),
    (2022, "EUCINF - Factsheet_EDF22.pdf", "EUCINF", None, None, False),
    (2022, "AIDEDex - Factsheet_EDF22_0.pdf", "AIDEDex", None, None, False),
    (2022, "SWAT-SHOAL-Factsheet_EDF22.pdf", "SWAT-SHOAL", None, None, False),
    (2022, "ODINS'EYE II-Factsheet_EDF22.pdf", "ODINS'EYE II", None, None, False),
    (2021, "Factsheet_EDF21_EPIIC.pdf", "EPIIC", None, None, False),
    (2021, "Factsheet_EDF21_EU HYDEF.pdf", "EU HYDEF", None, None, False),
    (2021, "Factsheet_EDF21_FaRADAI_0.pdf", "FaRADAI", None, None, False),
    (2021, "Factsheet_EDF21_ ACHILE_0.pdf", "ACHILE", None, None, False),
    (2021, "Factsheet_EDF21_MOSAIC_updated.pdf", "MOSAIC", None, None, False),
]


@pytest.mark.parametrize("year,name,acronym,ga,action,step", NAMES)
def test_the_file_name_of_every_call_year_is_read(year, name, acronym, ga, action, step):
    info = edf.parse_filename(name, year)
    assert info is not None, name
    assert (info.acronym, info.ga_number, info.action, info.step) == (acronym, ga, action, step)
    assert info.year == year


def test_the_topic_code_and_category_are_decoded():
    info = edf.parse_filename("FACTSHEET_EDF_2025_DA_SI_GROUND_DAMM_101304876_EURODAMM.pdf", 2025)
    assert info.topic_code == "EDF-2025-DA-SI-GROUND-DAMM" and info.category == "GROUND"
    lump = edf.parse_filename("FACTSHEET_EDF_2024_LS_RA_SMERO_NT_101224636_ARRAYS.pdf", 2024)
    assert lump.lump_sum and lump.category == "SMERO"


def test_a_file_that_is_not_a_project_is_not_parsed():
    for name in ("EDF 2025 results - general factsheet v7.pdf", "PESCO Related Projects.pdf",
                 "Factsheet - EDF2021 - Results of the Calls for Proposals - General Overview.pdf"):
        assert edf.parse_filename(name, 2025) is None


def test_the_key_of_a_project_is_its_year_and_its_acronym_without_punctuation():
    a = edf.parse_filename("FACTSHEET_EDF_2025_LS_DA_SME_NT_101305039_GEDIRIS.pdf", 2025)
    b = edf.parse_filename("FACTSHEET_EDF_2025_LS_DA_SME_NT_101305039_GEDIRIS_0.pdf", 2025)
    assert a.key == b.key == "2025:gediris"            # the same file uploaded twice is one project


LINK_PAGE = """<a href="/document/download/aaa_en?filename=EDF%202025%20results%20-%20general%20factsheet%20v7.pdf">g</a>
<a href="/document/download/bbb_en?filename=FACTSHEET_EDF_2025_CSA_101305005_EOA-V2.pdf">p</a>
<a href="/document/download/bbb_en?filename=FACTSHEET_EDF_2025_CSA_101305005_EOA-V2.pdf">again</a>
<a href="/document/download/ccc_en?filename=PESCO%20Related%20Projects.pdf">pesco</a>
<a href="/other/page">x</a>
<a href="/document/download/ddd_en?filename=notes.docx">d</a>"""


def test_a_results_page_gives_each_project_factsheet_once_and_no_general_factsheet():
    links = edf.factsheet_links(LINK_PAGE, "https://defence-industry-space.ec.europa.eu/x_en")
    assert [lk.filename for lk in links] == ["FACTSHEET_EDF_2025_CSA_101305005_EOA-V2.pdf"]
    assert links[0].url.startswith("https://defence-industry-space.ec.europa.eu/document/download/bbb")


SITEMAP = """<urlset>
<url><loc>https://defence-industry-space.ec.europa.eu/funding-and-grants/calls-proposals/european-defence-fund-2021-calls-proposals-results_en</loc></url>
<url><loc>https://defence-industry-space.ec.europa.eu/funding-and-grants/calls-proposals/result-edf-2022-calls-proposals_en</loc></url>
<url><loc>https://defence-industry-space.ec.europa.eu/funding-opportunities-0/calls-proposals/results-edf-2023-calls-proposals_en</loc></url>
<url><loc>https://defence-industry-space.ec.europa.eu/funding-opportunities/calls-proposals/result-edf-2024-calls-proposals_en</loc></url>
<url><loc>https://defence-industry-space.ec.europa.eu/funding-opportunities/calls-proposals/result-edf-2025-calls-proposals_en</loc></url>
<url><loc>https://defence-industry-space.ec.europa.eu/funding-opportunities/calls-proposals/result-edf-2025-calls-proposals_de</loc></url>
<url><loc>https://defence-industry-space.ec.europa.eu/edf-faq_en</loc></url>
</urlset>"""


def test_the_four_url_shapes_of_the_results_pages_are_found_in_the_sitemap():
    pages = edf.result_pages(SITEMAP)
    assert sorted(pages) == [2021, 2022, 2023, 2024, 2025]
    assert all(u.endswith("_en") for u in pages.values())       # one language, English


# ------------------------------------------------------------------ the PDF

def test_the_text_of_a_factsheet_has_its_consortium_and_not_its_technical_description():
    text = edf.read_pdf(factsheet_pdf())
    assert text.pages == 2 and len(text.sha256) == 64
    for needle in ("TALGEN CYBERSECURITY OU", "SAFRAN ELECTRONICS & DEFENSE", "Estonia", "36 Months"):
        assert needle in text.layout
    assert SECRET not in text.layout and SECRET not in text.plain
    assert "SHORT DESCRIPTION" not in text.layout


def test_a_name_wrapped_over_two_lines_is_whole_only_in_the_plain_text_or_next_to_its_country():
    text = edf.read_pdf(factsheet_pdf())
    wrapped = "FUNDACION CENTRO TECNOLOXICO DE TELECOMUNICACIONS DE GALICIA"
    answer = {"participants": [{"name": wrapped, "country": "Spain", "role": "participant",
                                "is_sme": None}], "coordinator": None}
    kept, dropped = edf.check_names(answer, text)
    assert len(kept["participants"]) == 1 and dropped["not_in_text"] == 0


def test_a_participant_the_document_does_not_print_is_dropped_and_counted():
    text = edf.read_pdf(factsheet_pdf())
    answer = {"coordinator": {"name": "PHANTOM CORP", "country": "France"},
              "participants": [
                  {"name": "TALGEN CYBERSECURITY OU", "country": "Estonia", "role": "coordinator", "is_sme": None},
                  {"name": "PHANTOM CORP", "country": "France", "role": "participant", "is_sme": None},
                  {"name": "Aliter Technologies AS", "country": "Slovakia", "role": "participant", "is_sme": None},
                  {"name": "ALITER TECHNOLOGIES, AS", "country": "Slovakia", "role": "participant", "is_sme": None},
                  {"name": "TALGEN CYBERSECURITY", "country": "Narnia", "role": "participant", "is_sme": None},
              ]}
    kept, dropped = edf.check_names(answer, text)
    names = [p["name"] for p in kept["participants"]]
    assert "PHANTOM CORP" not in names and kept["coordinator"] is None
    assert dropped["not_in_text"] == 1 and dropped["duplicate"] == 1 and dropped["no_country"] == 1
    assert [p["country_iso"] for p in kept["participants"]] == ["EE", "SK", None]


def test_two_coordinators_are_a_misreading_and_neither_is_believed():
    text = edf.read_pdf(factsheet_pdf())
    two = [{"name": n, "country": c, "role": "coordinator", "is_sme": None}
           for n, c in (("TALGEN CYBERSECURITY OU", "Estonia"), ("ALITER TECHNOLOGIES, AS", "Slovakia"))]
    kept, dropped = edf.check_names({"participants": two, "coordinator": None}, text)
    assert {p["role"] for p in kept["participants"]} == {"participant"}
    assert dropped["coordinator_doubtful"] == 1


def test_country_names_become_iso_codes():
    assert edf.country_code("Czechia") == "CZ" and edf.country_code(" The Netherlands.") == "NL"
    assert edf.country_code("Ukraine") == "UA" and edf.country_code("Atlantis") is None
    assert edf.country_code(None) is None


def test_the_members_helper_matches_what_the_tests_assume():
    assert len(MEMBERS) == 5


def test_a_download_that_is_not_a_pdf_is_refused():
    import httpx

    def handler(request):
        return httpx.Response(200, content=b"<html>login</html>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ValueError, match="not a PDF"):
            edf.fetch_pdf(http, "https://example.test/x.pdf")


def test_the_schema_the_model_must_answer_in_is_strict():
    from dgate.enrichment.base import strict_schema

    schema = strict_schema(edf.Factsheet)

    def walk(node):
        if isinstance(node, dict):
            if "properties" in node:
                assert node["additionalProperties"] is False
                assert node["required"] == list(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    assert set(schema["properties"]) == {"acronym", "title", "coordinator", "participants",
                                         "eu_contribution", "total_cost", "duration_months"}


def test_a_link_to_another_host_is_not_a_factsheet():
    html = '<a href="https://evil.example/document/download/x_en?filename=FACTSHEET_EDF_2025_CSA_101305005_EOA.pdf">x</a>'
    assert edf.factsheet_links(html, "https://defence-industry-space.ec.europa.eu/x_en") == []


def test_a_pdf_with_too_many_pages_is_refused():
    from tests.pdfmaker import make_pdf

    pdf = make_pdf([[(50, 800, f"page {i}")] for i in range(edf.MAX_PAGES + 1)])
    with pytest.raises(ValueError, match="not a factsheet"):
        edf.read_pdf(pdf)


def test_fetch_pdf_waits_out_a_429_and_slows_the_pace(monkeypatch):
    import httpx

    answers = [httpx.Response(429, headers={"retry-after": "3"}), httpx.Response(200, content=b"%PDF-1.4 x")]
    waits: list[float] = []
    pace = {"delay": 1.0}
    with httpx.Client(transport=httpx.MockTransport(lambda r: answers.pop(0))) as http:
        assert edf.fetch_pdf(http, "https://example.test/x.pdf", sleep=waits.append, pace=pace)             .startswith(b"%PDF")
    assert waits == [3.0] and pace["delay"] == 2.0


def test_fetch_pdf_gives_up_with_rate_limited_after_its_attempts():
    import httpx

    from dgate.sources import RateLimited

    waits: list[float] = []
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429))) as http:
        with pytest.raises(RateLimited):
            edf.fetch_pdf(http, "https://example.test/x.pdf", attempts=3, sleep=waits.append)
    assert waits == [10.0, 20.0]


def test_the_acronym_the_model_reports_is_used_only_when_the_file_prints_it():
    from dgate import networks

    info = edf.parse_filename("FACTSHEET_EDF_2024_DA_C4ISR_COMS_STEP_101218568_5G_COMPAD_2_0.pdf", 2024)
    text = edf.FactsheetText("h", 2, "5G COMPAD 2.0" + chr(10) + "5G COMPAD 2.0 - something", "x")
    printed = networks._edf_project_values(info, {"acronym": "5G COMPAD 2.0", "title": "T"}, "u", 1, text)
    invented = networks._edf_project_values(info, {"acronym": "SOMETHING ELSE", "title": "T"}, "u", 1, text)
    assert printed["acronym"] == "5G COMPAD 2.0"
    assert invented["acronym"] == "5G COMPAD 2"             # the file name's, underscores as spaces


def test_the_table_is_read_without_a_model_wrapped_names_and_the_coordinator_marker_included():
    text = edf.read_pdf(factsheet_pdf())
    rows = edf.table_rows(text.layout)
    assert ("TALGEN CYBERSECURITY OU", "Estonia") in rows           # "(Coordinator)" removed
    assert ("ALITER TECHNOLOGIES, AS", "Slovakia") in rows
    assert ("FUNDACION CENTRO TECNOLOXICO DE TELECOMUNICACIONS DE GALICIA", "Spain") in rows
    assert len(rows) == 4


def test_a_country_the_model_paired_wrongly_is_replaced_by_the_one_on_the_name_row_and_a_missing_row_is_counted():
    text = edf.read_pdf(factsheet_pdf())
    answer = {"coordinator": None, "participants": [
        {"name": "TALGEN CYBERSECURITY OU", "country": "Estonia", "role": "coordinator", "is_sme": None},
        {"name": "ALITER TECHNOLOGIES, AS", "country": "Spain", "role": "participant", "is_sme": None},   # wrong
        {"name": "SAFRAN ELECTRONICS & DEFENSE", "country": "France", "role": "participant", "is_sme": None},
    ]}                                                                    # the Galicia centre is left out
    kept, dropped = edf.check_names(answer, text)
    assert {p["name"]: p["country_iso"] for p in kept["participants"]}["ALITER TECHNOLOGIES, AS"] == "SK"
    assert dropped["country_corrected"] == 1 and dropped["missing_from_answer"] == 1


def test_a_layout_the_table_reader_does_not_know_changes_nothing():
    text = edf.FactsheetText("h", 1, "no table here", "ALITER TECHNOLOGIES, AS")
    answer = {"coordinator": None, "participants": [
        {"name": "ALITER TECHNOLOGIES, AS", "country": "Spain", "role": "participant", "is_sme": None}]}
    kept, dropped = edf.check_names(answer, text)
    assert kept["participants"][0]["country_iso"] == "ES" and dropped["country_corrected"] == 0
    assert dropped["missing_from_answer"] == 0
