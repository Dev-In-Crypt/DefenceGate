"""Who may apply to a call, from the call's own eligibility facts first (WP-92).

The list badge ("Companies can take part" / "Public buyers only", funding.WHO_MAY_APPLY) was read from the
programme rules alone. Where the call document (or the topic's own conditions) has been read
(`call_eligibility`, served through `eligibility.read_many`), its verified facts decide instead:

  * `designated_applicants` with no consortium  -> designated (WP-99: "Designated bodies only");
    route for others
  * `sme_only` true                            -> companies, and `sme_only` (the card adds "SMEs only");
  * an entity type naming a company or a       -> companies;
    private legal entity
  * every entity type a public body            -> public (Member State procurement agencies, ministries,
                                                  contracting authorities...);
  * anything else                              -> nothing stored: the programme rules decide.

A fact read from the work programme's general annexes is a rule of the programme, not of the call: it is used
last, and only for "a company can take part", where the call's own facts settle nothing (WP-132): the Horizon
Europe annexes' "Any legal entity ... is eligible to participate" (21 open Horizon calls were missing from "Open to
companies" while the same pages said any legal entity may take part). A mandatory consortium and its country
composition are not a badge: "Can I apply?" on the call page states them (web/lib/funding-path.ts applySummary);
the "Minimum consortium" row of the call's terms is `consortium_of`.
"""

from __future__ import annotations

import re
from typing import Any

from . import eligibility, verdict

# the same test as the verdict's designated line (verdict.check, web/lib/eligibility-check.ts)
_PARTNER_ROUTE = re.compile(r"partners?|in (?:a )?consortium with|may (?:also )?join", re.I)
OWN_SCOPES = ("call_document", "topic", "programme")   # WP-93: the EIC work programme read for the topic is its own text
EVIDENCE_MAX = 400

_PRIVATE = re.compile(r"\b(?:compan(?:y|ies)|enterprises?|smes?|small and medium|mid-caps?|private|undertakings?|"
                      r"industr\w*|business(?:es)?|start-ups?|firms?|any legal entit\w*|all legal entit\w*)\b", re.I)
_LEGAL = re.compile(r"\blegal (?:entit\w*|persons?)\b", re.I)
_PUBLIC = re.compile(r"\b(?:public (?:bod(?:y|ies)|authorit\w*|entit\w*|legal entit\w*|buyers?|administrations?|"
                     r"procurers?|sector bod\w*)|contracting authorit\w*|procurement agenc\w*|central purchasing bod\w*|"
                     r"ministr\w*|member states?'? (?:authorit\w*|administrations?|governments?)|governments?|"
                     r"national authorit\w*|armed forces|"
                     r"defence agenc\w*|international organisations?)\b", re.I)


_ELIGIBLE_ARE = re.compile(r"\blegal entit\w*\s*\((?:public|private) (?:or|and) (?:public|private)", re.I)
# WP-113 (/funding/170): a national call's own text naming SMEs as the applicants (Vinnova's web text, in Swedish and as served)
_SME_CALL = re.compile(r"[^.]*\b(?:(?:is |are )?aimed at (?:\w+ ){0,2}small and medium-sized enterprises|"
                       r"riktar sig till (?:\w+ ){0,2}små och medelstora företag)[^.]*\.?", re.I)


def own_text_facts(cond: dict[str, Any] | None, text: str | None) -> dict[str, Any]:
    """The facts of a call whose rules no document reading holds (state `no_source`): the rules the agency's page states in fixed words
    (`conditions_raw.rules_read`, AID: eligibility.page_rules) and a call text that names SMEs as the applicants."""
    page = eligibility.page_rules(cond)
    facts: dict[str, Any] = dict(page["facts"]) if page else {}
    for candidate in [text, *((cond or {}).get("web_text_sv") or [])]:
        m = _SME_CALL.search(str(candidate or ""))
        if m:
            facts["sme_only"] = {"value": True, "quote": m.group(0).strip(), "scope": "call_document", "note": None, "confidence": 1.0}
            break
    return facts


def _kind(item: str) -> str | None:
    if _PRIVATE.search(item):
        return "companies"
    if _PUBLIC.search(item):
        return "public"
    if _LEGAL.search(item):          # "legal entities" with no public qualifier: a company is one
        return "companies"
    return None


_ANY_LEGAL = re.compile(r"\bany legal entit\w*", re.I)


def _general_companies(facts: dict[str, Any]) -> str | None:
    """The sentence of the work programme's general annexes that lets any legal entity take part, or None (WP-132). The sentence
    "Any legal entity ... is eligible to participate" is the evidence where a general fact quotes it; else an entity list that names
    legal persons."""
    general = [f for f in (facts.get("sme_only"), facts.get("entity_types")) if f and f["scope"] == "general"]
    for f in general:
        if _ANY_LEGAL.search(str(f.get("quote") or "")):
            return str(f["quote"])[:EVIDENCE_MAX]
    for f in general:
        items = [str(t) for t in f["value"]] if isinstance(f["value"], list) else []
        if any(_kind(t) == "companies" for t in items):
            return (f.get("quote") or "; ".join(items))[:EVIDENCE_MAX] or None
    return None


def decide(facts: dict[str, Any]) -> tuple[str | None, bool | None, str | None]:
    """(who, sme_only, evidence) from one call's served facts; (None, None, None) when they say nothing."""
    got = _own(facts)
    if got[0] is None:
        general = _general_companies(facts)
        if general:
            return "companies", None, general
    return got


def _own(facts: dict[str, Any]) -> tuple[str | None, bool | None, str | None]:
    # WP-99: only designated bodies may apply (National Cyber Hubs, the Cross-Border Cyber Hubs' public bodies), with no route for anybody
    # else: not "Companies can take part" because the entity list also names legal entities. With a consortium route (the NCC topic) a
    # company can take part, as a partner, and the list below decides.
    des = facts.get("designated_applicants")
    if des and des["scope"] in OWN_SCOPES and not _PARTNER_ROUTE.search(verdict.own_note(des)):
        return "designated", None, (des.get("quote") or str(des.get("value") or ""))[:EVIDENCE_MAX] or None
    sme = facts.get("sme_only")
    if sme and sme["scope"] in OWN_SCOPES and sme["value"] is True:
        return "companies", True, (sme.get("quote") or "")[:EVIDENCE_MAX] or None
    # WP-113 (/funding/188 RAPID): a cap on the applicant's consolidated staff count is a rule for a company
    cap = facts.get("max_group_headcount")
    if cap and cap["scope"] in OWN_SCOPES and cap.get("value") is not None:
        return "companies", None, (cap.get("note") or cap.get("quote") or "")[:EVIDENCE_MAX] or None
    types = facts.get("entity_types")
    if not (types and types["scope"] in OWN_SCOPES and isinstance(types["value"], list) and types["value"]):
        # WP-113 (/funding/125): the entity list was not verified, but the verified "not only SMEs" fact quotes the call's own
        # sentence on who may apply ("be legal entities (public or private bodies)")
        quote = str((sme or {}).get("quote") or "")
        if sme and sme["scope"] in OWN_SCOPES and sme["value"] is False and _ELIGIBLE_ARE.search(quote) and _kind(quote) == "companies":
            return "companies", None, quote[:EVIDENCE_MAX]
        return None, None, None
    kinds = [_kind(str(t)) for t in types["value"]]
    evidence = (types.get("quote") or "")[:EVIDENCE_MAX] or None
    if "companies" in kinds:
        return "companies", None, evidence
    if all(k == "public" for k in kinds):
        return "public", None, evidence
    return None, None, None


_RESEARCH = re.compile(r"\b(?:universit\w*|research|academi\w*|higher education|rtos?|any legal entit\w*|all legal entit\w*|"
                       r"legal (?:entit\w*|persons?))\b", re.I)


def research_of(facts: dict[str, Any]) -> bool | None:
    """WP-109 (p09: a filter "Universities and research organisations"): whether a university or a research organisation may apply, from
    the call's own facts. False where only designated bodies, only SMEs (and small mid-caps) or only public bodies may; True where an entity
    type names universities, research bodies or legal entities in general; None where the call's own facts say nothing."""
    who, sme, _ = decide(facts)
    if who == "designated" or sme is True:
        return False
    types = facts.get("entity_types")
    if not (types and types["scope"] in OWN_SCOPES and isinstance(types["value"], list) and types["value"]):
        return False if who == "public" else None
    if verdict.small_kinds_only(facts):
        return False
    if any(_RESEARCH.search(str(t)) for t in types["value"]):
        return True
    return False if who == "public" else None


# Where a fact was read, as the "Minimum consortium" row says it (WP-132)
_READ_IN = {"call_document": "the call document", "topic": "the topic's conditions", "programme": "the EIC work programme",
            "general": "the work programme's general annexes"}


def _count(f: dict[str, Any] | None) -> int | None:
    v = (f or {}).get("value")
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def consortium_of(facts: dict[str, Any]) -> str | None:
    """WP-132: the call's "Minimum consortium" row from its verified facts, with where they were read; None when they say nothing.
    It replaces the topic text's "at least N ..." (sources/eu_portal.consortium_rule) where the call's facts speak: that sentence is
    often about some partners only ("at least 2 Border or Coast Guard Authorities from at least 2 Member States", 39), and two EIC
    Pathfinder calls said "3 legal entities" beside "a single legal entity may apply" (128, 129). A single applicant allowed is the
    minimum."""
    single, n, k = facts.get("single_applicant_allowed"), facts.get("min_entities"), facts.get("min_countries")
    if (single and single["value"] is True) or _count(n) == 1:
        where = single if single and single["value"] is True else n
        return f"None: a single legal entity may apply ({_READ_IN.get(where['scope'], 'the rules read')})"
    if (_count(n) or 0) < 2:
        return None
    used = [n] + ([k] if (_count(k) or 0) >= 2 else [])
    places = list(dict.fromkeys(_READ_IN.get(f["scope"], "the rules read") for f in used))
    text = f"At least {_count(n)} legal entities" + (f" from at least {_count(k)} countries" if len(used) == 2 else "")
    return f"{text} ({'; '.join(places)})"


def run(conn, *, write: bool = False) -> dict[str, int]:
    """Decide every call. Writes only the calls whose answer changed; a second run changes nothing."""
    rows = conn.execute(
        """SELECT id, topic_code, type_of_action, conditions_raw, eligibility_text,
                  who_may_apply_doc, sme_only, who_may_apply_evidence, research_may_apply_doc, consortium_rule
             FROM call ORDER BY id""").fetchall()
    served = eligibility.read_many(
        conn, [(r["id"], r["conditions_raw"], r["eligibility_text"], r["topic_code"], r["type_of_action"]) for r in rows])
    # `changed`: the who-may-apply answer; `research_changed`: only the research answer (WP-109) changed
    counts = {"calls": len(rows), "public": 0, "companies": 0, "designated": 0, "sme_only": 0, "research": 0, "changed": 0, "research_changed": 0,
              "consortium": 0, "consortium_changed": 0}
    for r in rows:
        facts = served[r["id"]]["facts"] or own_text_facts(r["conditions_raw"], r["eligibility_text"])
        # WP-132: the "Minimum consortium" row, written on its own (the answers below may be unchanged)
        rule = consortium_of(served[r["id"]]["facts"])
        counts["consortium"] += rule is not None
        if rule != r["consortium_rule"]:
            counts["consortium_changed"] += 1
            if write:
                conn.execute("UPDATE call SET consortium_rule = %s WHERE id = %s", (rule, r["id"]))
        who, sme, evidence = decide(facts)
        research = research_of(facts)
        if who:
            counts[who] += 1
        counts["sme_only"] += sme is True
        counts["research"] += research is True
        if (who, sme, evidence) != (r["who_may_apply_doc"], r["sme_only"], r["who_may_apply_evidence"]):
            counts["changed"] += 1
        elif research != r["research_may_apply_doc"]:
            counts["research_changed"] += 1
        else:
            continue
        if write:
            conn.execute("UPDATE call SET who_may_apply_doc = %s, sme_only = %s, who_may_apply_evidence = %s, research_may_apply_doc = %s "
                         "WHERE id = %s", (who, sme, evidence, research, r["id"]))
    if write:
        conn.commit()
    return counts
