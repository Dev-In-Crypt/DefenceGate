"""Who may apply to a call, from the call's own eligibility facts first (WP-92).

The list badge ("Companies can take part" / "Public buyers only", funding.WHO_MAY_APPLY) was read from the
programme rules alone. Where the call document (or the topic's own conditions) has been read
(`call_eligibility`, served through `eligibility.read_many`), its verified facts decide instead:

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

from . import eligibility

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


def run(conn, *, write: bool = False) -> dict[str, int]:
    """Decide every call. Writes only the calls whose answer changed; a second run changes nothing."""
    rows = conn.execute(
        """SELECT id, topic_code, type_of_action, conditions_raw, eligibility_text,
                  who_may_apply_doc, sme_only, who_may_apply_evidence
             FROM call ORDER BY id""").fetchall()
    served = eligibility.read_many(
        conn, [(r["id"], r["conditions_raw"], r["eligibility_text"], r["topic_code"], r["type_of_action"]) for r in rows])
    counts = {"calls": len(rows), "public": 0, "companies": 0, "sme_only": 0, "changed": 0}
    for r in rows:
        who, sme, evidence = decide(served[r["id"]]["facts"])
        if who:
            counts[who] += 1
        counts["sme_only"] += sme is True
        if (who, sme, evidence) == (r["who_may_apply_doc"], r["sme_only"], r["who_may_apply_evidence"]):
            continue
        counts["changed"] += 1
        if write:
            conn.execute("UPDATE call SET who_may_apply_doc = %s, sme_only = %s, who_may_apply_evidence = %s WHERE id = %s",
                         (who, sme, evidence, r["id"]))
    if write:
        conn.commit()
    return counts
