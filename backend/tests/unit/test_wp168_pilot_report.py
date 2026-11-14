"""WP-168: the pilot report, one test per section on fixture payloads (the JSON the site serves), and the whole document."""

from __future__ import annotations

from datetime import date
from html.parser import HTMLParser

import pytest

from dgate.ops import pilot_report as pr

DOC = "https://ec.europa.eu/info/funding-tenders/opportunities/docs/x/call-fiche_x_en.pdf"


def fact(value, quote="", note=None):
    return {"value": value, "quote": quote, "note": note, "confidence": 1.0, "scope": "call_document"}


def usi_call(**over):
    call = {
        "id": "113", "slug": "113-unmanned-systems", "title": "Unmanned systems", "programme": "EDIP-USI",
        "programmeName": "EDIP Ukraine Support Instrument", "callId": "EDF-EDIP-USI-2027-LS-IRA", "topicId": "EDF-EDIP-USI-2027-LS-IRA-CUXS",
        "status": "open", "openingDate": "2026-06-17T00:00:00Z", "deadline": "2027-02-16T16:00:00Z", "deadlineIsDate": False,
        "budget": {"amount": 80_000_000.0, "currency": "EUR"}, "budgetScope": "topic", "budgetNote": None,
        "documentBudget": {"amount": 82_000_000.0, "votedEu": 80_000_000.0, "currency": "EUR", "documentUrl": DOC},
        "openToUkraine": True, "ukraineBasis": {"reason": "call_document", "evidence": "non-EU countries: − Ukraine"},
        "whoMayApply": "companies",
        "whoMayApplyLimits": [{"kind": "control", "quote": "not be subject to control by a non-associated third country", "note": None}],
        "eligibility": [{"label": "Minimum consortium", "value": "None: a single legal entity may apply (the call document)"}],
        "documentEligibility": {"documentUrl": DOC, "extractedAt": "2026-10-18T08:14:29Z", "basis": "call_document", "facts": {
            "eligible_countries": fact("EU Member States; Ukraine", "be established in one of the eligible countries"),
            "min_entities": fact(1, "If a single applicant, it must be a legal entity established in Ukraine."),
            "min_countries": fact(1),
            "consortium_required": fact(False, "Single applicants or consortia may apply."),
            "funding_rate": fact("100%", "reimbursed at 100%"),
        }},
        "eligibilitySources": [{"scope": "call_document", "label": "Call document", "url": DOC, "extractedAt": "2026-10-18T08:14:29Z"}],
        "source": {"sourceName": "EU Funding and Tenders Portal", "retrievedAt": "2026-11-14T04:20:00Z", "licence": "Commission Decision 2011/833/EU",
                   "url": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/edf-edip-usi-2027-ls-ira-cuxs"},
    }
    return {**call, **over}


def partner(i, name, country, *, slug=True, evidence=("1", "2")):
    return {"organisationId": str(i), "slug": f"{i}-{name.lower().replace(' ', '-')}" if slug else None, "name": name, "country": country,
            "projects": 3, "coordinated": 1, "topical": 2, "roles": {"coordinator": 4, "participant": 9, "thirdParty": 0, "other": 0},
            "evidence": [{"projectId": p, "acronym": f"P{p}", "title": "t", "year": 2024, "role": "participant"} for p in evidence]}


PARTNERS = {
    "area": {"kind": "edf-related", "label": "EDF capability categories AIR and GROUND", "rule": "EDF projects of AIR and GROUND.",
             "projects": 27, "organisations": 320, "firstYear": 2023, "lastYear": 2025, "topicWords": ["unmanned"]},
    "partners": [partner(1, "Alpha SA", "FR"), partner(2, "Bravo GmbH", "DE", evidence=("2", "3")),
                 partner(3, "Name not shown", None, slug=False, evidence=("9",))],
    "total": 320, "note": None,
    "source": {"readAt": "2026-11-01T00:00:00Z", "sources": ["CORDIS, European Commission"], "licence": "Commission Decision 2011/833/EU"},
}


def project(pid, countries, coordinator="FR"):
    members = [{"organisation": {"country": c}, "role": "participant"} for c in countries]
    return {"id": pid, "memberCount": len(countries), "countryCount": len(set(countries) - {None}),
            "coordinator": {"country": coordinator}, "members": members}


PROJECTS = {"1": project("1", ["FR", "DE", "IT", "ES"]), "2": project("2", ["FR", "DE", "IT", "ES", "GR", None]),
            "3": project("3", ["DE", "FR"], coordinator="DE"), "9": project("9", ["IT", "FR", "BE"], coordinator="IT")}


class Fake:
    """The public endpoints as fixture payloads; records what was asked."""

    def __init__(self, call=None):
        self._call = call or usi_call()
        self.asked: list[tuple] = []

    def call(self, ref):
        self.asked.append(("call", ref))
        return self._call

    def partners(self, call_id, *, prefer=None, country=None, limit=pr.PARTNERS):
        self.asked.append(("partners", prefer, country))
        if country == "UA":
            return {**PARTNERS, "partners": [], "total": 0}
        return PARTNERS

    def project(self, pid):
        self.asked.append(("project", pid))
        return PROJECTS[pid]

    def organisation(self, slug):
        i = int(slug.split("-")[0])
        return {"slug": slug, "name": {7: "Gamma SL", 8: "Delta Oy"}[i], "country": {7: "ES", 8: "FI"}[i],
                "counts": {"projects": 2, "coordinated": 0}}

    def ukraine_partners(self):
        ref = lambda i, n, c: {"id": str(i), "slug": f"{i}-x", "name": n, "country": c}  # noqa: E731
        return {"since": 2021, "totals": {"ukrainianOrganisations": 2}, "definition": "A coordinator is the organisation that leads.",
                "ukrainianOrganisations": [{"organisation": ref(5, "Kyiv Lab", "UA"), "projects": 3, "relevantProjects": 1, "coordinated": 0,
                                            "lastYear": 2025}],
                "coordinators": [{"organisation": ref(6, "Echo SpA", "IT"), "projects": 2, "defenceProjects": 1, "dualUseProjects": 1,
                                  "ukrainianParticipants": [{"organisation": ref(5, "Kyiv Lab", "UA"), "projects": 2}]}]}


# ------------------------------------------------------------------ 1 the call
def test_section_call_states_the_portal_budget_with_its_scope_and_the_document_total_as_the_documents():
    out = pr.section_call(usi_call())
    assert "EUR 80,000,000 (budget of this topic)" in out
    assert "Call document total: EUR 82 million, including EUR 80 million from the voted EU budget" in out
    assert "16 Feb 2027, 16:00 UTC" in out and "17 Jun 2026" in out
    assert 'href="https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/edf-edip-usi-2027-ls-ira-cuxs"' in out
    assert 'href="https://defencegatehub.com/funding/113-unmanned-systems"' in out
    shared = pr.section_call(usi_call(budgetScope="call", documentBudget=None))
    assert "shared across several topics of the same call" in shared and "Call document total" not in shared


# ------------------------------------------------------------------ 2 who may apply
def test_section_who_quotes_each_fact_and_links_its_document():
    out = pr.section_who(usi_call())
    assert "Companies can take part" in out
    assert "<q>be established in one of the eligible countries</q>" in out
    assert f'<a href="{DOC}">the call document</a> on 18 Oct 2026' in out
    assert "Funding rate" not in out, "a fact about money is not a rule of who may apply"
    assert "not be subject to control" in out


@pytest.mark.parametrize("flag, reason, word", [
    (True, "call_document", "Eligible"), (True, "edf_association", "Eligible"),
    (None, "programme_rule", "Check"), (None, "call_document_no_funding", "Check"), (None, "edf_closed_before_association", "Check"),
    (None, "not_stated", "Check"), (None, None, "Check"), (False, "call_document_closed_list", "Not eligible"),
])
def test_the_ukraine_verdict_is_never_stronger_than_the_flag(flag, reason, word):
    call = usi_call(openToUkraine=flag, ukraineBasis={"reason": reason, "evidence": "the sentence"} if reason else None)
    assert pr.ukraine_verdict(call)[0] == word
    out = pr.section_who(call)
    assert f'data-ukraine="{word.lower()}"' in out
    assert ("<q>the sentence</q>" in out) == bool(reason)


def test_a_usi_call_open_to_ukraine_says_the_territory_limit_and_an_edf_one_links_the_commission():
    assert "non-government controlled areas" in pr.ukraine_verdict(usi_call())[1]
    edf = pr.section_who(usi_call(programme="EDF", ukraineBasis={"reason": "edf_association", "evidence": "x"}))
    assert pr.EDF_IN_FORCE_URL in edf


def test_a_call_whose_rules_are_not_read_says_so_and_links_where_they_are():
    out = pr.section_who(usi_call(documentEligibility=None))
    assert "have not been read yet" in out and f'href="{DOC}"' in out


# ------------------------------------------------------------------ 3 matching organisations
def test_section_partners_lists_organisations_with_roles_and_links_and_never_an_unnamed_member():
    out = pr.section_partners(PARTNERS, country="PL", ua_area=None, ua=None)
    assert 'href="https://defencegatehub.com/organisations/1-alpha-sa">Alpha SA</a>' in out
    assert "coordinator 4, participant 9" in out and "2 on the topic" in out
    assert 'href="https://defencegatehub.com/projects/1">P1</a> (2024, participant)' in out
    assert "Name not shown" not in out
    assert "Organisations established in PL are listed first" in out
    assert "No organisation established in PL took part" in out


def test_section_partners_with_ukraine_adds_the_area_count_the_ukrainian_organisations_and_their_eu_coordinators():
    src = Fake()
    out = pr.section_partners(PARTNERS, country=None, ua_area=src.partners("113", country="UA"), ua=src.ukraine_partners())
    assert "0 organisations established in Ukraine" in out
    assert "Kyiv Lab" in out and "Echo SpA" in out and "1 / 1" in out


def test_no_area_says_why():
    out = pr.section_partners({"area": None, "partners": [], "note": "No earlier projects can be compared."}, country=None, ua_area=None, ua=None)
    assert "No earlier projects can be compared." in out


# ------------------------------------------------------------------ 4 consortium gaps
def test_the_typical_consortium_of_the_evidence_projects():
    ids = pr.sample_ids(PARTNERS)
    assert ids == ["1", "2", "3", "9"]
    typ = pr.typical([PROJECTS[i] for i in ids[:3]])
    assert typ["members"] == (4, 2, 6) and typ["countries"] == (4, 2, 5)
    assert dict(typ["presence"])["FR"] == 1 and round(dict(typ["presence"])["GR"], 2) == 0.33
    assert typ["coordinators"] == [("FR", 2), ("DE", 1)]


def test_section_gaps_without_a_consortium_is_the_typical_one_marked_indicative():
    out = pr.section_gaps(usi_call(), [PROJECTS["1"], PROJECTS["2"]], None)
    assert "EDF/CORDIS data, indicative" in out and "Members: median 5, from 4 to 6" in out
    assert "Minimum consortium: None: a single legal entity may apply" in out and "Single applicants or consortia may apply." in out
    assert "No consortium was given" in out


def test_section_gaps_names_what_a_given_consortium_lacks():
    members = [{"slug": "7-gamma-sl", "name": "Gamma SL", "country": "ES", "projects": 2, "coordinated": 0}]
    found = pr.gaps(usi_call(), pr.typical([PROJECTS["1"], PROJECTS["2"]]), members)
    assert any("median of 5 members" in g for g in found)
    assert any("missing from the consortium: DE, FR, IT, GR" in g for g in found), "countries in at least half of the projects, missing"
    assert any("coordinated" in g for g in found) and any("Ukraine" in g for g in found)
    strict = usi_call()
    strict["documentEligibility"]["facts"]["min_entities"] = fact(3)
    assert any("at least 3 legal entities" in g for g in pr.gaps(strict, None, members))
    out = pr.section_gaps(usi_call(), [PROJECTS["1"]], members)
    assert 'href="https://defencegatehub.com/organisations/7-gamma-sl">Gamma SL</a>' in out


# ------------------------------------------------------------------ 5 method and the document
def test_section_method_names_the_sources_dates_and_limits():
    out = pr.section_method(usi_call(), PARTNERS, 3)
    assert "EU Funding and Tenders Portal, retrieved 14 Nov 2026" in out and "CORDIS, European Commission" in out
    assert "3 comparable projects" in out and "natural persons are never named" in out and pr.DISCLAIMER in out


class _Balanced(HTMLParser):
    VOID = {"meta", "br", "link", "img", "hr", "input"}

    def __init__(self):
        super().__init__()
        self.stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack[-1] == tag, f"</{tag}> closes {self.stack[-1:]}"
        self.stack.pop()


def valid_html(doc: str) -> None:
    assert doc.startswith("<!doctype html>")
    p = _Balanced()
    p.feed(doc)
    p.close()
    assert p.stack == [], p.stack


def test_the_whole_document_is_valid_html_with_five_sections_and_the_footer():
    src = Fake()
    doc = pr.build(src, "EDF-EDIP-USI-2027-LS-IRA-CUXS", country="DE", ukraine=True, consortium=["7-gamma-sl", "8-delta-oy"],
                   today=date(2026, 11, 14))
    valid_html(doc)
    assert doc.count('class="report-section"') == 5
    assert "Pilot report, prepared by DefenceGate on 14 November 2026." in doc
    assert "@page { size: A4" in doc and "<script" not in doc
    assert ("partners", "DE", None) in src.asked and ("partners", None, "UA") in src.asked
    assert [a[1] for a in src.asked if a[0] == "project"] == ["1", "2", "3", "9"]
    assert "@" not in doc.replace("@media", "").replace("@page", ""), "no e-mail address"


def test_text_from_the_payloads_is_escaped():
    doc = pr.build(Fake(usi_call(title="<script>x</script>")), "113", today=date(2026, 11, 14))
    assert "<script>x" not in doc and "&lt;script&gt;x" in doc
