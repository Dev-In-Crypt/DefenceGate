"""Is a funding call open to Ukrainian participants? A derived flag on the call, with the reason and the evidence.

`call.open_to_ukraine` is TRUE or FALSE only where something we hold says so, and NULL ("unknown")
where nothing does. Unknown is not "no". The reason says how it was decided and the evidence is the
sentence it rests on. In this order:

  1. `call_document`  the verified fact `eligible_countries` read from the call's own document names
                      Ukraine as an eligible country (or says it is not).
  2. `topic_text`     the same fact read from the topic's own conditions text.
  3. `call_text`      a sentence of the call's conditions text that names Ukraine.
  4. `programme_rule` the regime's own Regulation decides: the Ukraine Support Instrument is open to
                      Ukraine (Regulation (EU) 2025/2643, Article 26(1)); the EDIP Programme is not,
                      its associated countries being EEA EFTA states (Article 2).
  5. `edf_association_unconfirmed`  an EDF call: Ukraine may take part as an associated country
                      "in accordance with the conditions laid down in the EU-Ukraine Association
                      Agreement" (Regulation (EU) 2021/697, Article 5, as replaced), and no primary
                      text read on 18 October 2026 says that agreement is in force. Unknown.
  6. `not_stated`     nothing states it. Unknown.

The work programme's general annexes never decide it (a topic may restrict who takes part), and a
Horizon, Digital Europe or national call is decided from its own facts and text alone: no rule of
those programmes is encoded. Derived data: `ops/ukraine_flags.py` fills it, idempotently.
"""

from __future__ import annotations

import re
from typing import Any

from . import cascade, eligibility
from .regime import EDF, EDIP, USI, regime_of

REASONS = ("call_document", "topic_text", "call_text", "programme_rule", "edf_association_unconfirmed", "not_stated")
EVIDENCE_MAX = 300

# Verbatim from the Official Journal text (CELLAR), read on 18 October 2026.
USI_RULE = ("Only legal entities established in the Union or in Ukraine and having their executive management "
            "structures in the Union or in Ukraine shall be eligible to be recipients of Union funding under this Regulation. "
            "(Regulation (EU) 2025/2643, Article 26(1))")
EDIP_RULE = ("‘associated countries’ means members of the European Free Trade Association which are members of the "
             "European Economic Area that apply this Regulation in accordance with the Agreement on the European Economic "
             "Area; (Regulation (EU) 2025/2643, Article 2)")
EDF_RULE = ("Ukraine, in accordance with the conditions laid down in the EU-Ukraine Association Agreement. "
            "(Regulation (EU) 2021/697, Article 5, as replaced by Regulation (EU) 2025/2653)")

_UKRAINE = re.compile(r"\bUkrain\w*", re.I)
_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+|\s+[−–•]\s+|\n+")
_NEGATIVE = re.compile(r"\b(?:not\s+(?:eligible|allowed|permitted)|ineligible|excluded?|may\s+not|cannot|no\s+participation)\b", re.I)
# "Legal entities established in the non-government controlled areas of Ukraine are not eligible": a
# territorial exclusion inside a call that is open to Ukraine, not a refusal of Ukraine.
_TERRITORY = re.compile(r"non[\s-]*government|occupied|temporarily", re.I)
# A sentence that names Ukraine counts only when it is about who may take part ("to support Ukraine's
# reconstruction" is a topic, not an eligibility rule).
_CUE = re.compile(r"eligib|establish|particip|applican|apply|entit|countr|associated|beneficiar|recipient", re.I)
_TOPIC_CODE = cascade._TOPIC_CODE


def _clip(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:EVIDENCE_MAX]


def text_statement(text: str | None, *, about_participation: bool = False) -> tuple[bool | None, str | None]:
    """(yes/no, the sentence) when the text names Ukraine as an eligible country or as not eligible;
    (None, None) when it does not name Ukraine, or says both. `about_participation`: the text is already
    known to be about who may take part (an eligible-countries fact), so a bare list item counts."""
    found: list[tuple[bool, str]] = []
    for part in _SENTENCE_END.split(text or ""):
        if not _UKRAINE.search(part):
            continue
        sentence = _clip(part)
        if _TERRITORY.search(sentence) or not (about_participation or _CUE.search(sentence)):
            continue
        found.append((not _NEGATIVE.search(sentence), sentence))
    answers = {v for v, _ in found}
    if len(answers) != 1:
        return None, None
    return found[0][0], found[0][1]


def _fact_answer(topic_code: str | None, fact: dict[str, Any]) -> tuple[bool, str] | None:
    """What a verified `eligible_countries` fact says about Ukraine for this call, or None."""
    quote = fact.get("quote") or ""
    value, sentence = text_statement(quote, about_participation=True)
    if value is None:
        return None
    named = _TOPIC_CODE.findall(quote)
    if named and not (topic_code and any(topic_code == t or topic_code.startswith(t) for t in named)):
        return None                       # the document names topics and this is not one of them
    return value, sentence or ""


def decide(call: dict[str, Any], facts: dict[str, Any]) -> tuple[bool | None, str, str | None]:
    """(flag, reason, evidence) of one call. `facts` are its verified eligibility facts as served
    (`eligibility.read_many`); `call` has `programme_code`, `topic_code` and `eligibility_text`."""
    fact = facts.get("eligible_countries")
    if fact and fact["scope"] != "general":
        answer = _fact_answer(call.get("topic_code"), fact)
        if answer is not None:
            return answer[0], ("topic_text" if fact["scope"] == "topic" else "call_document"), answer[1]
    value, sentence = text_statement(call.get("eligibility_text"))
    if value is not None:
        return value, "call_text", sentence
    regime = regime_of(call.get("programme_code") or "", call.get("topic_code"))
    if regime is USI:
        return True, "programme_rule", _clip(USI_RULE)
    if regime is EDIP:
        return False, "programme_rule", _clip(EDIP_RULE)
    if regime is EDF:
        return None, "edf_association_unconfirmed", _clip(EDF_RULE)
    return None, "not_stated", None


def run(conn, *, write: bool = False) -> dict[str, int]:
    """Decide every call. Writes only the calls whose answer changed; a second run changes nothing."""
    rows = conn.execute(
        """SELECT c.id, p.code AS programme_code, c.topic_code, c.conditions_raw, c.eligibility_text,
                  c.open_to_ukraine, c.open_to_ukraine_reason, c.open_to_ukraine_evidence
             FROM call c JOIN programme p ON p.id = c.programme_id ORDER BY c.id""").fetchall()
    served = eligibility.read_many(conn, [(r["id"], r["conditions_raw"], r["eligibility_text"]) for r in rows])
    counts = {"calls": len(rows), "yes": 0, "no": 0, "unknown": 0, "changed": 0}
    for r in rows:
        flag, reason, evidence = decide(r, served[r["id"]]["facts"])
        counts["yes" if flag is True else "no" if flag is False else "unknown"] += 1
        if (flag, reason, evidence) == (r["open_to_ukraine"], r["open_to_ukraine_reason"], r["open_to_ukraine_evidence"]):
            continue
        counts["changed"] += 1
        if write:
            conn.execute(
                """UPDATE call SET open_to_ukraine = %s, open_to_ukraine_reason = %s, open_to_ukraine_evidence = %s,
                                   open_to_ukraine_decided_at = now() WHERE id = %s""",
                (flag, reason, evidence, r["id"]))
    if write:
        conn.commit()
    return counts
