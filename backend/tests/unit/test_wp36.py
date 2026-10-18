"""WP-36: the regime of a funding call, the "open to Ukraine" flag, the rules block, the regulatory tracker.

Pure functions and the seed files; no database (the integration tests are in tests/integration/test_wp36.py).
"""

from __future__ import annotations

import dataclasses
import json
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from dgate import regulation, rules_apply, ukraine
from dgate.readiness.seed import load_file as load_rules
from dgate.regime import ALSO_READ, CEF, DIGITAL, EDF, EDIP, HORIZON, NATIONAL, USI, regime_of

ROOT = Path(__file__).resolve().parents[3]
CALLS = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "calls_programme_topic.json").read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- the regime

@pytest.mark.parametrize("programme, topic, regime", [
    ("EDF", "EDF-2026-DA-GROUND-MBT", EDF),
    ("EDF", "EDF-2026-LS-RA-SI-ENERENV-NTFE", EDF),
    ("EDF", "EDF-EDIP-P-2026-FNLC-CPA-AMEW", EDIP),
    ("EDF", "EDF-EDIP-USI-2026-LS-IRA-MAB", USI),
    ("EDF", "edf-edip-usi-2027-ls-ira-cuxs", USI),                  # the portal's codes are upper case; a lower-case one is the same
    ("EDF", None, EDF),
    ("EDIP", "EDIP-2026-ANYTHING", EDIP),
    ("HORIZON", "HORIZON-EIC-2026-DEFENCE-01", HORIZON),
    ("DIGITAL", "DIGITAL-2026-AI-08", DIGITAL),
    ("CEF2027", "CEF-T-2026-MILMOB-WORKS", CEF),
    ("FR-AID", "", NATIONAL),
    ("PL-NCBR", "5. konkurs", NATIONAL),
    ("FI-MATINE", "MATINE-2027", NATIONAL),
])
def test_the_regime_comes_from_the_programme_and_the_topic_code(programme, topic, regime):
    assert regime_of(programme, topic) is regime


def test_a_programme_it_does_not_know_has_no_regime():
    assert regime_of("EDIDP", "EDIDP-2020-X") is None            # the predecessor of the EDF has no calls and its own legal basis
    assert regime_of("SOMETHING-NEW", "X") is None


def test_every_one_of_the_193_calls_has_a_regime_and_the_counts_are_these():
    assert len(CALLS) == 193
    got = Counter(regime_of(c["programme"], c["topic"]).code for c in CALLS)          # None would raise
    assert got == {"HORIZON": 67, "DIGITAL": 51, "EDF": 28, "EDIP": 10, "EDIP-USI": 2, "NATIONAL": 34, "CEF": 1}
    # The calls with no rules encoded are exactly those of programmes that have no readiness programme.
    unencoded = {regime_of(c["programme"], c["topic"]).code for c in CALLS if regime_of(c["programme"], c["topic"]).readiness is None}
    assert unencoded == {"HORIZON", "DIGITAL", "NATIONAL", "CEF"}


def test_the_edip_and_usi_calls_are_found_by_their_topic_code_alone():
    edip = [c["topic"] for c in CALLS if regime_of(c["programme"], c["topic"]) is EDIP]
    usi = [c["topic"] for c in CALLS if regime_of(c["programme"], c["topic"]) is USI]
    assert all(t.startswith("EDF-EDIP-P-") for t in edip) and all(t.startswith("EDF-EDIP-USI-") for t in usi)
    assert not any(t.startswith("EDF-EDIP-") for c in CALLS for t in [c["topic"]] if regime_of(c["programme"], t) is EDF)


def test_every_readiness_programme_a_regime_names_exists_in_the_seed():
    codes = set(load_rules().programmes)
    for regime in (EDF, EDIP, USI):
        assert regime.readiness in codes


# ----------------------------------------------------------------------------- the rules block

def block(programme, topic, content=None):
    return rules_apply.build(content or load_rules(), programme, topic)


def test_an_edf_call_lists_the_headline_rules_each_with_its_verbatim_source():
    b = block("EDF", "EDF-2026-DA-GROUND-MBT")
    assert b["encoded"] and b["regime"]["code"] == "EDF"
    # WP-33 added the legal-entity rule (D2); the block lists whatever establishment, control, threshold and
    # categorical rules the seed holds.
    assert [r["rule"] for r in b["rules"]] == ["EDF-LEGAL-ENTITY", "EDF-ESTABLISH", "EDF-EXEC-MGMT", "EDF-CONTROL"]
    for r in b["rules"]:
        assert r["source"]["url"].startswith("http") and r["source"]["ref"] and len(r["source"]["text"]) > 40
        assert r["source"]["lastReviewed"] and r["requirement"] == "REQ-EDF-ELIG"
    assert "legal advice" in b["notice"] and b["alsoRead"] is None
    # Registration (the PIC) and the AQAP are not headline conditions of who may take part.
    assert not {"EDF-PIC", "EDF-AQAP"} & {r["rule"] for r in b["rules"]}


def test_the_usi_and_edip_blocks_show_the_territory_and_origin_rules_the_seed_now_holds():
    """WP-33 put the 35 % origin rules in the seed (verifier D1), so the Official Journal supplement
    (`alsoRead`) is no longer needed for them."""
    b = block("EDF", "EDF-EDIP-USI-2026-LS-IRA-MAB")
    assert b["regime"]["code"] == "EDIP-USI"
    codes = [r["rule"] for r in b["rules"]]
    assert "USI-TERRITORY" in codes and "USI-ORIGIN-35" in codes and b["alsoRead"] is None
    edip = block("EDF", "EDF-EDIP-P-2026-FNLC-CPA-CDS")
    assert "EDIP-ORIGIN-35" in [r["rule"] for r in edip["rules"]] and edip["alsoRead"] is None


def test_the_origin_share_is_not_shown_twice_once_the_seed_has_it_as_a_rule():
    content = load_rules()
    edip = content.programmes["EDIP"]
    rule = dataclasses.replace(edip.rules[0], code="EDIP-ORIGIN-35", kind="threshold", title="Origin of components")
    with_rule = dataclasses.replace(content, programmes={**content.programmes, "EDIP": dataclasses.replace(edip, rules=(*edip.rules, rule))})
    b = block("EDF", "EDF-EDIP-P-2026-FNLC-CPA-CDS", with_rule)
    assert b["alsoRead"] is None and "EDIP-ORIGIN-35" in [r["rule"] for r in b["rules"]]


def test_a_regime_without_rules_is_named_and_says_none_are_encoded():
    for programme, topic in (("HORIZON", "HORIZON-EIC-2026-DEFENCE-01"), ("DIGITAL", "DIGITAL-2026-X"), ("FR-AID", "")):
        b = block(programme, topic)
        assert b["encoded"] is False and b["rules"] == [] and b["alsoRead"] is None and b["regime"]["name"]


def test_without_the_rules_loaded_the_block_still_names_the_regime():
    b = rules_apply.build(None, "EDF", "EDF-2026-DA-X")
    assert b["encoded"] is False and b["regime"]["code"] == "EDF"
    assert rules_apply.build(None, "EDIDP", "X") is None


def test_the_also_read_sentences_are_the_35_percent_rule_of_the_same_regulation_the_seed_cites():
    assert {a["url"] for a in ALSO_READ.values()} == {"http://data.europa.eu/eli/reg/2025/2643/oj"}
    assert all("35 %" in a["text"] and "Regulation (EU) 2025/2643" in a["ref"] for a in ALSO_READ.values())


# ----------------------------------------------------------------------------- the Ukraine flag

def fact(quote, scope="call_document", value="x"):
    return {"value": value, "quote": quote, "note": None, "confidence": 1.0, "scope": scope}


def call(programme="HORIZON", topic="HORIZON-X-2026-01", text=None):
    return {"programme_code": programme, "topic_code": topic, "eligibility_text": text}


def test_a_call_document_that_names_ukraine_among_the_eligible_countries_decides():
    quote = "be established in one of the eligible countries, i.e.: − EU Member States (including OCTs) − non-EU countries: − Ukraine"
    flag, reason, evidence = ukraine.decide(call("EDF", "EDF-EDIP-USI-2027-LS-IRA-CUXS"), {"eligible_countries": fact(quote)})
    assert (flag, reason) == (True, "call_document") and evidence == "Ukraine"


def test_the_territorial_exclusion_is_not_a_refusal_of_ukraine():
    quote = "− non-EU countries: − Ukraine Legal entities established in the non -government controlled areas of Ukraine are not eligible for funding."
    flag, reason, _ = ukraine.decide(call("EDF", "EDF-EDIP-USI-2026-LS-IRA-MAB"), {"eligible_countries": fact(quote)})
    assert flag is True and reason == "programme_rule"          # the sentence is skipped; the regulation of the regime says yes


def test_the_usi_regulation_decides_without_any_document():
    flag, reason, evidence = ukraine.decide(call("EDF", "EDF-EDIP-USI-2026-LS-IRA-MAB"), {})
    assert (flag, reason) == (True, "programme_rule") and "Article 26(1)" in evidence and len(evidence) <= ukraine.EVIDENCE_MAX


def test_an_edip_programme_call_is_not_open_to_ukraine_whatever_the_document_lists():
    quote = "contracting authorities from EU Member States and EDIP associated countries (i.e. Norway)."
    for facts in ({}, {"eligible_countries": fact(quote)}):
        flag, reason, evidence = ukraine.decide(call("EDF", "EDF-EDIP-P-2026-FNLC-CPA-AMEW"), facts)
        assert (flag, reason) == (False, "programme_rule") and "Article 2" in evidence


def test_an_edf_call_is_unknown_until_a_primary_text_says_the_association_is_in_force():
    quote = "listed EEA countries and countries associated to the EDF Programme (‘EDF associated countries’)"
    for facts in ({}, {"eligible_countries": fact(quote)}):
        flag, reason, evidence = ukraine.decide(call("EDF", "EDF-2026-DA-GROUND-MBT"), facts)
        assert flag is None and reason == "edf_association_unconfirmed" and "EU-Ukraine Association Agreement" in evidence


def test_an_edf_document_that_itself_names_ukraine_still_decides():
    flag, reason, _ = ukraine.decide(call("EDF", "EDF-2026-DA-X"), {"eligible_countries": fact("eligible countries: EU Member States, Norway and Ukraine")})
    assert (flag, reason) == (True, "call_document")


def test_the_general_annexes_never_decide_it():
    facts = {"eligible_countries": fact("Annex B lists the associated countries: Norway, Ukraine, Israel", scope="general")}
    assert ukraine.decide(call("HORIZON"), facts) == (None, "not_stated", None)


def test_a_topic_text_and_a_call_text_decide_and_say_where_from():
    f = {"eligible_countries": fact("Legal entities established in Ukraine are eligible to participate.", scope="topic")}
    assert ukraine.decide(call(), f)[:2] == (True, "topic_text")
    flag, reason, evidence = ukraine.decide(call(text="Entities established in Ukraine are not eligible for this topic."), {})
    assert (flag, reason) == (False, "call_text") and "not eligible" in evidence


def test_a_sentence_about_the_topic_is_not_a_sentence_about_who_may_take_part():
    text = "This topic supports the reconstruction of Ukraine's energy grid with open standards."
    assert ukraine.text_statement(text) == (None, None)


def test_a_text_that_says_both_is_not_decided():
    text = "Entities established in Ukraine are eligible. Entities established in Ukraine are not eligible for lot 2."
    assert ukraine.text_statement(text) == (None, None)


def test_a_document_that_names_other_topics_is_not_an_answer_for_this_one():
    quote = "Ukraine-based entities are eligible for topics HORIZON-AAA-2026-01 only."
    assert ukraine.decide(call(topic="HORIZON-BBB-2026-02"), {"eligible_countries": fact(quote)}) == (None, "not_stated", None)
    assert ukraine.decide(call(topic="HORIZON-AAA-2026-01"), {"eligible_countries": fact(quote)})[:2] == (True, "call_document")


def test_a_national_call_and_a_horizon_call_with_nothing_stated_are_unknown():
    for programme in ("FR-AID", "HORIZON", "DIGITAL", "CEF2027"):
        assert ukraine.decide(call(programme), {}) == (None, "not_stated", None)


def test_the_evidence_is_cut_to_the_limit():
    flag, _, evidence = ukraine.decide(call(text="Legal entities established in Ukraine are eligible " + "and entities " * 80), {})
    assert flag is True and len(evidence) == ukraine.EVIDENCE_MAX


# ----------------------------------------------------------------------------- the regulatory tracker

SEED = json.loads(regulation.SEED_PATH.read_text(encoding="utf-8"))


def raw(**over):
    e = dict(SEED["entries"][0])
    e.update(over)
    return {"entries": [e]}


def test_the_seed_is_valid_and_has_the_entries_the_brief_names():
    entries = regulation.load_file()
    assert len(entries) >= 12
    instruments = {e["instrument"] for e in entries}
    assert {"SAFE", "EDIP", "EDF", "Directive 2009/81/EC", "Regulation (EU) 2021/821"} <= instruments


def test_every_entry_has_a_primary_source_a_verbatim_sentence_and_a_check_date():
    for e in regulation.load_file():
        assert e["source_url"].startswith(("https://", "http://data.europa.eu/")), e["code"]
        assert len(e["source_quote"]) >= regulation.MIN_QUOTE_CHARS and e["source_ref"] and e["affected"], e["code"]
        checked = date.fromisoformat(e["checked_on"])
        assert date(2026, 10, 18) <= checked <= date.today(), e["code"]
        assert e["status"] in regulation.STATUSES


def test_a_claim_no_primary_text_confirms_is_marked_unconfirmed_and_says_what_is_open():
    unconfirmed = [e for e in regulation.load_file() if e["status"] == "unconfirmed"]
    assert {e["code"] for e in unconfirmed} == {"safe-uk-unconfirmed", "edf-ukraine-in-force-unconfirmed"}
    for e in unconfirmed:
        assert "found no" in e["what_changed"]


def test_no_unverified_claim_of_the_analysis_is_in_the_seed():
    text = json.dumps(SEED, ensure_ascii=False).lower()
    for claim in ("talks broke down", "korea", "turkey", "japan", "19 national plans", "european preference was not", "2028", "2029"):
        assert claim not in text, claim


def test_the_links_lead_to_pages_that_exist():
    rules = load_rules()
    for e in regulation.load_file():
        for ln in e["links"]:
            if ln["kind"] == "requirement":
                assert ln["code"] in rules.requirements, (e["code"], ln["code"])
            elif ln["kind"] == "programme":
                assert ln["code"] in rules.programmes, (e["code"], ln["code"])
            else:
                assert ln["code"].startswith("/"), (e["code"], ln["code"])


@pytest.mark.parametrize("over, message", [
    ({"source_quote": "too short"}, "verbatim sentence"),
    ({"status": "done"}, "status"),
    ({"source_url": "ftp://x"}, "source_url"),
    ({"checked_on": "yesterday"}, "checked_on"),
    ({"event_date": None}, "event_date"),
    ({"affected": " "}, "affected"),
    ({"links": [{"kind": "requirement", "code": "REQ-X"}]}, "link"),
])
def test_an_invalid_entry_is_refused_and_named(over, message):
    with pytest.raises(regulation.SeedError, match=message):
        regulation.parse(raw(**over))


def test_a_duplicate_code_and_an_empty_file_are_refused():
    with pytest.raises(regulation.SeedError, match="unique code"):
        regulation.parse({"entries": [SEED["entries"][0], SEED["entries"][0]]})
    with pytest.raises(regulation.SeedError, match="no entries"):
        regulation.parse({"entries": []})


def test_the_payload_lists_the_newest_event_first_and_the_last_check():
    p = regulation.payload(regulation.load_file())
    days = [e["eventDate"] for e in p["entries"]]
    assert days == sorted(days, reverse=True) and p["lastChecked"] == "2026-10-18"
    assert regulation.payload([])["lastChecked"] is None


def test_the_site_mock_is_what_the_seed_serves():
    assert (ROOT / regulation.MOCK_PATH).read_text(encoding="utf-8") == regulation.mock_text(), \
        "run: python -m dgate.regulation --export <repository root>"
