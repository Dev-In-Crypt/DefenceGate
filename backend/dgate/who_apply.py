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

A fact read from the work programme's general annexes is a rule of the programme, not of the call, and is
not used here. A mandatory consortium and its country composition are not a badge: "Can I apply?" on the
call page states them (web/lib/funding-path.ts applySummary).
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


def _kind(item: str) -> str | None:
    if _PRIVATE.search(item):
        return "companies"
    if _PUBLIC.search(item):
        return "public"
    if _LEGAL.search(item):          # "legal entities" with no public qualifier: a company is one
        return "companies"
    return None


def decide(facts: dict[str, Any]) -> tuple[str | None, bool | None, str | None]:
    """(who, sme_only, evidence) from one call's served facts; (None, None, None) when they say nothing."""
    # WP-99: only designated bodies may apply (National Cyber Hubs, the Cross-Border Cyber Hubs' public bodies), with no route for anybody
    # else: not "Companies can take part" because the entity list also names legal entities. With a consortium route (the NCC topic) a
    # company can take part, as a partner, and the list below decides.
    des = facts.get("designated_applicants")
    if des and des["scope"] in OWN_SCOPES and not _PARTNER_ROUTE.search(verdict.own_note(des)):
        return "designated", None, (des.get("quote") or str(des.get("value") or ""))[:EVIDENCE_MAX] or None
    sme = facts.get("sme_only")
    if sme and sme["scope"] in OWN_SCOPES and sme["value"] is True:
        return "companies", True, (sme.get("quote") or "")[:EVIDENCE_MAX] or None
    types = facts.get("entity_types")
    if not (types and types["scope"] in OWN_SCOPES and isinstance(types["value"], list) and types["value"]):
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


def run(conn, *, write: bool = False) -> dict[str, int]:
    """Decide every call. Writes only the calls whose answer changed; a second run changes nothing."""
    rows = conn.execute(
        """SELECT id, topic_code, type_of_action, conditions_raw, eligibility_text,
                  who_may_apply_doc, sme_only, who_may_apply_evidence, research_may_apply_doc
             FROM call ORDER BY id""").fetchall()
    served = eligibility.read_many(
        conn, [(r["id"], r["conditions_raw"], r["eligibility_text"], r["topic_code"], r["type_of_action"]) for r in rows])
    # `changed`: the who-may-apply answer; `research_changed`: only the research answer (WP-109) changed
    counts = {"calls": len(rows), "public": 0, "companies": 0, "designated": 0, "sme_only": 0, "research": 0, "changed": 0, "research_changed": 0}
    for r in rows:
        facts = served[r["id"]]["facts"]
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
