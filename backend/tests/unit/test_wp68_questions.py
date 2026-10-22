"""WP-68: the supplier page asks the questions of the German rules and the EU dual-use question (WP-64 fields that no page asked).

The request body is the generated fixture `web/e2e/fixtures/request-de-sup.json` (dgate.readiness.export), which the web's own check
(`web/lib/wp68.check.ts`) and e2e spec (`web/e2e/wp68.spec.ts`) prove the page sends. Here: without the page's answers each of those
rules is "unknown" and asks its question; with them it is met, not met or a condition to check, and "I am not sure" on a
classification flags a specialist. A company outside Germany is not concerned by the German rules whatever it answers.
"""

from __future__ import annotations

import json
from pathlib import Path

from dgate.readiness import api
from dgate.readiness.seed import load_file

ROOT = Path(__file__).resolve().parents[3]
CONTENT = load_file()
ASKED = ("de_vs_vertraulich", "ghb_admitted", "sibe_appointed", "de_vs_nfd", "vsnfd_declaration_signed", "vsnfd_merkblatt",
         "de_ausfuhrliste", "dualuse_annex_i")
RULES = ("DE-GHB-ADMISSION", "DE-GHB-COST", "DE-SIBE", "DE-VSNFD", "DE-EXPORT-BAFA", "EU-DUALUSE-EXPERT")


def request():
    return json.loads((ROOT / "web" / "e2e" / "fixtures" / "request-de-sup.json").read_text(encoding="utf-8"))


def assess(profile, statuses):
    payload = api.assess_payload(CONTENT, api.ProfileIn(**profile).to_engine(), statuses)
    general = [r for a in payload["general"] for r in a["rules"]]
    missing = [m["field"] for a in payload["general"] for m in a["missing"]]
    return {r["rule"]: r["outcome"] for r in general if r["rule"] in RULES}, missing, [c["rule"] for c in payload["consultants"]]


def test_without_the_supplier_page_the_german_and_dual_use_rules_ask():
    body = request()
    profile = {k: v for k, v in body["profile"].items() if k not in ASKED}
    outcomes, missing, _ = assess(profile, {**body["statuses"], "REQ-EXPORT": "unknown"})
    assert outcomes == {r: "unknown" for r in RULES}
    assert set(ASKED) | {"REQ-EXPORT"} <= set(missing)


def test_with_the_answers_each_rule_is_met_not_met_or_a_condition():
    body = request()
    outcomes, missing, consultants = assess(body["profile"], body["statuses"])
    assert outcomes == {
        "DE-GHB-ADMISSION": "conditional",   # VS-VERTRAULICH, not yet under the Geheimschutzbetreuung: only the VS-Auftraggeber can apply
        "DE-GHB-COST": "info",
        "DE-SIBE": "met",
        "DE-VSNFD": "not_met",               # the declaration is signed, the contract does not incorporate the Merkblatt
        "DE-EXPORT-BAFA": "conditional",     # not sure whether the item is in Ausfuhrliste Part I
        "EU-DUALUSE-EXPERT": "conditional",  # not sure whether it is in Annex I of Regulation (EU) 2021/821
    }
    assert missing == []
    # "not sure" on a classification: a specialist settles it
    assert {"EU-DUALUSE-EXPERT", "DE-EXPORT-BAFA"} <= set(consultants)


def test_no_and_neither_leave_the_rules_out():
    body = request()
    profile = {**body["profile"], "de_vs_vertraulich": False, "de_vs_nfd": False, "de_ausfuhrliste": "neither", "dualuse_annex_i": "no"}
    for k in ("ghb_admitted", "sibe_appointed", "vsnfd_declaration_signed", "vsnfd_merkblatt"):
        profile.pop(k)                        # hidden on the page after a "no", so not sent
    outcomes, missing, consultants = assess(profile, body["statuses"])
    assert outcomes == {r: "not_applicable" for r in RULES}
    assert missing == []
    assert not {"EU-DUALUSE-EXPERT", "DE-EXPORT-BAFA"} & set(consultants)


def test_admitted_and_licensed_are_met():
    body = request()
    profile = {**body["profile"], "ghb_admitted": True, "vsnfd_merkblatt": True, "de_ausfuhrliste": "part_i_b", "dualuse_annex_i": "no"}
    outcomes, _, _ = assess(profile, {**body["statuses"], "REQ-EXPORT": "held"})
    assert outcomes["DE-GHB-ADMISSION"] == "met"
    assert outcomes["DE-VSNFD"] == "met"
    assert outcomes["DE-EXPORT-BAFA"] == "met"            # Section B and an export outside the EU: the licence is held
    assert outcomes["EU-DUALUSE-EXPERT"] == "not_applicable"


def test_the_german_rules_do_not_concern_a_company_elsewhere():
    body = request()
    profile = {**body["profile"], "country": "ES"}
    outcomes, _, _ = assess(profile, body["statuses"])
    assert {r: o for r, o in outcomes.items() if r.startswith("DE-")} == {r: "not_applicable" for r in RULES if r.startswith("DE-")}
    # the dual-use rule has no country condition: a Spanish company not sure about Annex I gets the same check
    assert outcomes["EU-DUALUSE-EXPERT"] == "conditional"
