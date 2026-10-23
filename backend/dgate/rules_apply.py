"""The "rules that apply" block of a funding call (WP-36): which regime the call is under and the
headline conditions of that regime, with the verbatim source of each. No verdict: that is the
readiness check's job, and the block links to it.

The regime is read from the call's identifiers (`regime.py`); the conditions are the active rules of
the matching readiness programme (`seeds/requirements.json`), so a rule edited there changes here.
Only the rules that decide who may take part (establishment, control, an origin threshold or a
categorical exclusion) are headlines; registration and quality conditions are on the requirement pages.
"""

from __future__ import annotations

from typing import Any

from .readiness.content import Content, Rule
from .readiness.engine import assess_rule
from .regime import ALSO_READ, action_of, regime_of

HEADLINE_KINDS = ("establishment", "control", "threshold", "categorical")
NOTICE = "Indicative, not legal advice. The call text and the contracting authority decide."

# WP-91 (UX audit 6: "Can I apply?" on the first screen of a call). The engine's own outcome of each establishment rule for one
# country of each group the rules name (EU, EEA EFTA, Ukraine, any other), with only the country and the call's kind of action
# known: every other answer is missing, so a rule that needs one stays "unknown" and names it (`asks`), never "met". The page
# picks the group of the visitor's country; the rule texts are the seed's, so a rule edited there changes here.
SUMMARY_GROUPS = {"EU": "DE", "EEA_EFTA": "NO", "UA": "UA", "OTHER": "XX"}


def _outcomes(rules: list[Rule], fields: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for x in rules:
        r = assess_rule(x, fields, {})
        if r.outcome != "not_applicable":
            out.append({"rule": r.rule, "title": r.title, "outcome": r.outcome, "asks": list(r.asks), "reason": r.reason})
    return out


def by_country(rules: list[Rule], action: str | None) -> dict[str, list[dict[str, Any]]]:
    """The establishment rules' outcomes per country group (see SUMMARY_GROUPS)."""
    est = [x for x in rules if x.kind == "establishment"]
    return {group: _outcomes(est, {"country": country, "action": action}) for group, country in SUMMARY_GROUPS.items()}


def for_company(rules: list[Rule], action: str | None) -> list[dict[str, Any]]:
    """The categorical rules on who may apply (EDIP-CPA-APPLICANT ...), for a company or research body: `not_met` says a company
    cannot apply to this call (common procurement is for contracting authorities, international organisations, SEAPs, the EDA)."""
    who = [x for x in rules if x.kind == "categorical" and "applicant_kind" in str(x.condition)]
    return _outcomes(who, {"applicant_kind": "company_or_research", "action": action})


def scoped_actions(rule: Rule) -> set[str] | None:
    """The kinds of action a rule is scoped to (`applies_when` on the field `action`), or None for a rule of every action."""
    found: set[str] = set()

    def walk(expr: dict[str, Any] | None) -> None:
        if not expr:
            return
        for sub in expr.get("all", []):
            walk(sub)
        if expr.get("field") == "action":
            found.update([expr["is"]] if "is" in expr else expr.get("in", []))

    walk(rule.applies_when)
    return found or None


def build(content: Content | None, programme_code: str, topic_code: str | None) -> dict[str, Any] | None:
    """The block for one call, or None when the programme is not one `regime_of` knows."""
    regime = regime_of(programme_code, topic_code)
    if regime is None:
        return None
    out: dict[str, Any] = {
        "regime": {"code": regime.code, "name": regime.name, "why": regime.why},
        "encoded": False, "rules": [], "alsoRead": None, "notice": NOTICE, "action": action_of(programme_code, topic_code),
    }
    programme = content.programmes.get(regime.readiness) if content and regime.readiness else None
    if programme is None:
        return out
    fixes = {code: r.code for r in content.requirements.values() for code in r.extras.get("rules", [])}
    action = out["action"]
    # a rule for one kind of action (who may apply to common procurement) is shown on the calls of that action only
    rules = [x for x in programme.rules if x.kind in HEADLINE_KINDS and x.obligation == "mandatory"
             and (scoped_actions(x) is None or action in scoped_actions(x))]
    out["encoded"] = True
    out["programme"] = {"code": programme.code, "name": programme.name, "legalBasis": programme.legal_basis}
    out["rules"] = [{
        "rule": x.code, "title": x.title, "kind": x.kind, "requirement": fixes.get(x.code) or x.requirement,
        "caveat": x.texts.get("caveat"),
        "source": {"url": x.source_url, "ref": x.source_ref, "text": x.source_text, "origin": x.text_origin,
                   "verificationStatus": x.status, "lastReviewed": x.last_reviewed},
    } for x in rules]
    out["byCountry"] = by_country(rules, action)
    out["forCompany"] = for_company(rules, action)
    # The origin share of EDIP and the Ukraine Support Instrument, until the seed carries it as a rule.
    if regime.code in ALSO_READ and not any(x.kind == "threshold" for x in rules):
        a = ALSO_READ[regime.code]
        out["alsoRead"] = {"label": a["label"], "ref": a["ref"], "text": a["text"], "url": a["url"]}
    return out
