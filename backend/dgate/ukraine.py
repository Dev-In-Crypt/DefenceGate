"""Is a funding call open to Ukrainian participants? A derived flag on the call, with the reason and the evidence.

`call.open_to_ukraine` is TRUE or FALSE only where something we hold says so, and NULL ("unknown")
where nothing does. Unknown is not "no". The reason says how it was decided and the evidence is the
sentence it rests on. In this order:

  1. `call_document`  the verified fact `eligible_countries` read from the call's own document names
                      Ukraine as an eligible country (or says it is not).
  2. `call_document_closed_list`  the call document lists the eligible countries one by one (Member
                      States and the EEA countries Norway, Iceland, Liechtenstein) and does not name
                      Ukraine or associated countries: Ukraine is not on the list. False (V2-B9: the
                      Digital Europe cybersecurity calls).
  3. `topic_text`     the same fact read from the topic's own conditions text.
  4. `call_text`      a sentence of the call's conditions text that names Ukraine.
  5. `topic_text_associated`  a Horizon Europe topic whose own conditions limit participation to
                      "legal entities established in Member States and Associated Countries", and the
                      general annexes list Ukraine among the countries associated to Horizon Europe.
                      Two sentences we hold; true (V2-B9).
  5b. `horizon_associated`  WP-99: a Horizon Europe call (the EIC is part of it) whose own list of eligible countries (the call's or the
                      topic's, not the general annexes') is open to the countries associated to Horizon Europe, read as the verdict
                      reads it (verdict.country_status, web/lib/eligibility-check.ts countryStatus); Ukraine is one (the same
                      association list, verdict.ASSOCIATED, from the general annexes). The badge, the filter and the verdict agree.
  6. `programme_rule` the regime's own Regulation decides: the Ukraine Support Instrument is open to
                      Ukraine (Regulation (EU) 2025/2643, Article 26(1)). The EDIP Programme: recipients must be
                      established in the Union or an associated country, and Ukraine is not one (Articles 9(1) and 2),
                      but the call documents name Ukraine in other roles (a member of a SEAP, a state that designates a
                      procurement agent, a recipient of additional quantities) and none says whether a Ukrainian
                      entity may apply. A flag stronger than the document is not served (V3-A): it is unknown, with
                      the Regulation's sentence as the evidence, unless the document itself says Ukraine is (not) eligible.
  7. `edf_association_unconfirmed`  an EDF call: Ukraine may take part as an associated country
                      "in accordance with the conditions laid down in the EU-Ukraine Association
                      Agreement" (Regulation (EU) 2021/697, Article 5, as replaced), the EDF call
                      documents say participation of entities established in Ukraine "is pending the
                      signature of the association agreement", and no primary text read on 18 October 2026
                      says that agreement is in force. Unknown, conditional on the agreement.
  8. `not_stated`     nothing states it. Unknown.

The work programme's general annexes never decide it alone (a topic may restrict who takes part): only
together with a topic sentence that sends the call to the associated countries. Derived data:
`ops/ukraine_flags.py` fills it, idempotently.
"""

from __future__ import annotations

import re
from typing import Any

from . import eligibility, verdict
from .regime import EDF, EDIP, HORIZON, USI, regime_of

REASONS = ("call_document", "call_document_closed_list", "topic_text", "call_text", "topic_text_associated", "horizon_associated",
           "programme_rule", "edf_association_unconfirmed", "not_stated")
EVIDENCE_MAX = 450

# Verbatim from the Official Journal text (CELLAR), read on 18 October 2026.
USI_RULE = ("Only legal entities established in the Union or in Ukraine and having their executive management "
            "structures in the Union or in Ukraine shall be eligible to be recipients of Union funding under this Regulation. "
            "(Regulation (EU) 2025/2643, Article 26(1))")
EDIP_RECIPIENTS = ("Recipients of EDIP funding must be established in the Union or in an associated country, and Ukraine "
                   "is not one (Regulation (EU) 2025/2643, Articles 9(1) and 2).")
EDIP_RULE = (f"{EDIP_RECIPIENTS} No sentence we hold says whether entities established in Ukraine may apply to this call: "
             "its document names Ukraine only in other roles, if at all.")
EDF_RULE = ("Ukraine, in accordance with the conditions laid down in the EU-Ukraine Association Agreement. "
            "(Regulation (EU) 2021/697, Article 5, as replaced by Regulation (EU) 2025/2653)")
# The footnote on "countries associated to the EDF Programme" in all 10 EDF call documents of 2026 read
# on 18 October 2026 (latest versions dated 8 September 2026), word for word.
EDF_PENDING = ("Participation of entities established in Ukraine is pending the signature of the association "
               "agreement to EDF (see countries currently negotiating association agreements below).")
EDF_EVIDENCE = (f"EDF call documents, 2026: “{EDF_PENDING}” Regulation (EU) 2025/2653, Article 3(1): Ukraine "
                "“in accordance with the conditions laid down in the EU-Ukraine Association Agreement”. "
                "No text we could read says that agreement is in force.")
HORIZON_ANNEX = "The general annexes of the Horizon Europe work programme list Ukraine among the countries associated to Horizon Europe."

_UKRAINE = re.compile(r"\bUkrain\w*", re.I)
_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+|\s+[−–•]\s+|\n+")
_NEGATIVE = re.compile(r"\b(?:not\s+(?:eligible|allowed|permitted)|ineligible|excluded?|may\s+not|cannot|no\s+participation)\b", re.I)
# "Legal entities established in the non-government controlled areas of Ukraine are not eligible": a
# territorial exclusion inside a call that is open to Ukraine, not a refusal of Ukraine.
_TERRITORY = re.compile(r"non[\s-]*government|occupied|temporarily", re.I)
# A sentence that names Ukraine counts only when it is about who may take part ("to support Ukraine's
# reconstruction" is a topic, not an eligibility rule).
_CUE = re.compile(r"eligib|establish|particip|applican|apply|entit|countr|associated|beneficiar|recipient", re.I)
# A list of eligible countries that names the EEA countries one by one and no associated countries or Ukraine.
_EEA_NAMED = re.compile(r"\b(?:Norway|Iceland|Liechtenstein)\b")
_ASSOCIATED = re.compile(r"associated|Ukrain", re.I)
# "participation in this topic is limited to legal entities established in Member States and Associated Countries."
# Not a list that adds or names other countries ("...and the following additional associated countries: Canada").
_HORIZON_TOPIC = re.compile(
    r"[^.]*\blimited\s+to\s+legal\s+entities\s+established\s+in\s+Member\s+States\s+and\s+Associated\s+Countries\s*\.", re.I)


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
    if eligibility.names_other_topic(quote, topic_code):
        return None                       # the document names topics and this is not one of them
    # A bare list item ("− Ukraine") is no evidence on its own: the list it stands in is.
    return value, (sentence if sentence and len(sentence) >= 25 else _clip(quote))


def _closed_list(fact: dict[str, Any]) -> str | None:
    """The sentence of a call document that lists the eligible countries one by one without Ukraine or associated countries."""
    quote = fact.get("quote") or ""
    if fact.get("scope") == "call_document" and _EEA_NAMED.search(quote) and not _ASSOCIATED.search(quote):
        return _clip(quote)
    return None


def decide(call: dict[str, Any], facts: dict[str, Any]) -> tuple[bool | None, str, str | None]:
    """(flag, reason, evidence) of one call. `facts` are its verified eligibility facts as served
    (`eligibility.read_many`); `call` has `programme_code`, `topic_code` and `eligibility_text`."""
    regime = regime_of(call.get("programme_code") or "", call.get("topic_code"))
    fact = facts.get("eligible_countries")
    if fact and fact["scope"] != "general":
        answer = _fact_answer(call.get("topic_code"), fact)
        if answer is not None and answer[0] and regime is EDIP:
            # The document names Ukraine (as a possible member of a SEAP, say) but the recipients of EDIP
            # funding are not Ukrainian entities: a participant is not a recipient (V2-B9). Neither yes nor no.
            return None, "programme_rule", _clip(f"{EDIP_RECIPIENTS} The call document also says: “{answer[1]}”")
        if answer is not None:
            return answer[0], ("topic_text" if fact["scope"] == "topic" else "call_document"), answer[1]
        listed = _closed_list(fact)
        if listed:
            return False, "call_document_closed_list", listed
    value, sentence = text_statement(call.get("eligibility_text"))
    if value is not None:
        return value, "call_text", sentence
    if regime is USI:
        return True, "programme_rule", _clip(USI_RULE)
    if regime is EDIP:
        return None, "programme_rule", _clip(EDIP_RULE)
    if regime is EDF:
        return None, "edf_association_unconfirmed", _clip(EDF_EVIDENCE)
    if regime is HORIZON:
        topic = eligibility.topic_text(call.get("eligibility_text"))
        m = _HORIZON_TOPIC.search(re.sub(r"\s+", " ", topic or ""))
        if m:
            return True, "topic_text_associated", _clip(f"Topic conditions: “{m.group(0).strip()}” {HORIZON_ANNEX}")
        if fact and fact["scope"] != "general":
            ok, _ = verdict.country_status(fact, "UA", {"programme": HORIZON.code, "topic": call.get("topic_code") or ""})
            if ok == "yes":
                listed = fact.get("quote") or str(fact.get("value") or "")
                return True, "horizon_associated", _clip(f"Eligible countries: “{listed}” {HORIZON_ANNEX}")
    return None, "not_stated", None


def run(conn, *, write: bool = False) -> dict[str, int]:
    """Decide every call. Writes only the calls whose answer changed; a second run changes nothing."""
    rows = conn.execute(
        """SELECT c.id, p.code AS programme_code, c.topic_code, c.type_of_action, c.conditions_raw, c.eligibility_text,
                  c.open_to_ukraine, c.open_to_ukraine_reason, c.open_to_ukraine_evidence
             FROM call c JOIN programme p ON p.id = c.programme_id ORDER BY c.id""").fetchall()
    served = eligibility.read_many(
        conn, [(r["id"], r["conditions_raw"], r["eligibility_text"], r["topic_code"], r["type_of_action"]) for r in rows])
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
