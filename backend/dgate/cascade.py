"""Cascade funding (financial support to third parties, FSTP) as a flag on the call.

A call "has cascade funding" when the money passes through its beneficiaries to third parties
(small firms, start-ups) by open calls of their own. This decides the flag from what we hold, in
this order, and stores how (`call.cascade_reason`) and the sentence it rests on (`cascade_evidence`):

  1. `call_document`  the verified fact `cascade_funding` read from the call's own document
     (`eligibility.py`). A document that covers several topics may name the topics where it is
     allowed: then the call's topic code decides, and a topic the quote does not name stays
     undecided (`call_document_other_topic`). A fact with a qualification ("allowed for X only") is
     not taken as the call's answer.
  2. `topic_text`     the same fact read from the topic's own conditions text.
  3. `call_text`      a sentence of the call's conditions text that states it. The mention that is
     only the title of an annex or a guide ("Information on financial support to third parties
     (HE)", "Guidelines on FSTP implementation") is not a statement: a Horizon call lists that
     form whether or not it has cascade funding.
  4. `not_stated`     nothing states it: the flag is NULL, which is "not determined", not "no".

The general annexes never decide it: whether a call has FSTP is that call's own rule.
Derived data: `ops/cascade_flags.py` fills it, idempotently; nothing else writes the columns.
"""

from __future__ import annotations

import re
from typing import Any

from . import eligibility

REASONS = ("call_document", "topic_text", "call_text", "call_document_other_topic", "not_stated")
EVIDENCE_MAX = 300

_TERM = re.compile(r"financial\s+support\s+to\s+third\s+parties|\bFSTP\b|\bcascade\s+fund", re.I)
# The titles of annexes and guides that every Horizon / EDF call lists.
_TITLES = re.compile(
    r"Information\s+on\s+financial\s+support\s+to\s+third\s+parties(?:\s*\(HE\))?"
    r"|Guidelines\s+on\s+FSTP\s+implementation(?:\s*-\s*[A-Z0-9]+)?", re.I)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[(“\"])")
_NEGATIVE = re.compile(r"\b(?:not\s+(?:allowed|permitted|possible|eligible)|may\s+not|must\s+not|cannot|can\s+not|"
                       r"no\s+financial\s+support|not\s+foreseen|not\s+applicable)\b", re.I)
_POSITIVE = re.compile(r"\b(?:may|must|shall|can|will|is\s+allowed|are\s+allowed|allowed|permitted|provide|"
                       r"included?|foreseen|required|envisaged)\b", re.I)
_TOPIC_CODE = re.compile(r"\b[A-Z]{3,}(?:-[A-Z0-9]+){2,}\b")


def text_statement(text: str | None) -> tuple[bool | None, str | None]:
    """(yes/no, the sentence) when the conditions text states it; (None, None) otherwise. A text
    with a yes and a no is not decided."""
    cleaned = _TITLES.sub(" ", text or "")
    found: list[tuple[bool, str]] = []
    for sentence in _SENTENCE_END.split(cleaned):
        if not _TERM.search(sentence):
            continue
        sentence = re.sub(r"\s+", " ", sentence).strip()
        if _NEGATIVE.search(sentence):
            found.append((False, sentence))
        elif _POSITIVE.search(sentence):
            found.append((True, sentence))
    answers = {v for v, _ in found}
    if len(answers) != 1:
        return None, None
    return found[0][0], found[0][1][:EVIDENCE_MAX]


def _document_answer(topic_code: str | None, fact: dict[str, Any]) -> tuple[bool | None, str] | None:
    """What a fact read from a call document says about this call: (answer, reason), or None when
    it is not an answer for this call (a qualification), so that the next source is tried."""
    quote = fact.get("quote") or ""
    named = _TOPIC_CODE.findall(quote)
    negative = bool(_NEGATIVE.search(quote))
    if named:
        mine = bool(topic_code) and any(topic_code == t or topic_code.startswith(t) for t in named)
        if negative:
            return (False, "call_document") if mine else None
        return (True, "call_document") if mine else (None, "call_document_other_topic")
    value = fact.get("value")
    if value is True and re.search(r"\bonly\b", fact.get("note") or "", re.I):
        return None
    if value is False and fact.get("note"):
        return None
    return (bool(value), "call_document")


def decide(call: dict[str, Any], facts: dict[str, Any]) -> tuple[bool | None, str, str | None]:
    """(flag, reason, evidence) of one call. `facts` are its verified eligibility facts as served
    (`eligibility.read_many`); `call` has `topic_code` and `eligibility_text`."""
    fact = facts.get("cascade_funding")
    if fact and fact["scope"] != "general":
        if fact["scope"] == "topic":
            return bool(fact["value"]), "topic_text", (fact["quote"] or "")[:EVIDENCE_MAX]
        answer = _document_answer(call.get("topic_code"), fact)
        if answer is not None:
            value, reason = answer
            return value, reason, fact["quote"][:EVIDENCE_MAX]
    value, sentence = text_statement(call.get("eligibility_text"))
    if value is not None:
        return value, "call_text", sentence
    return None, "not_stated", None


def run(conn, *, write: bool = False) -> dict[str, int]:
    """Decide every call. Writes only the calls whose answer changed; a second run changes nothing."""
    rows = conn.execute(
        """SELECT id, topic_code, conditions_raw, eligibility_text, cascade, cascade_reason, cascade_evidence
             FROM call ORDER BY id""").fetchall()
    served = eligibility.read_many(conn, [(r["id"], r["conditions_raw"], r["eligibility_text"]) for r in rows])
    counts = {"calls": len(rows), "yes": 0, "no": 0, "undecided": 0, "changed": 0}
    for r in rows:
        flag, reason, evidence = decide(r, served[r["id"]]["facts"])
        counts["yes" if flag is True else "no" if flag is False else "undecided"] += 1
        if (flag, reason, evidence) == (r["cascade"], r["cascade_reason"], r["cascade_evidence"]):
            continue
        counts["changed"] += 1
        if write:
            conn.execute(
                """UPDATE call SET cascade = %s, cascade_reason = %s, cascade_evidence = %s,
                                   cascade_decided_at = now() WHERE id = %s""",
                (flag, reason, evidence, r["id"]))
    if write:
        conn.commit()
    return counts
