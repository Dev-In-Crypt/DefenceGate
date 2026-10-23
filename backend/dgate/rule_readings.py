"""Rules read from the stored text of a call by fixed patterns, not by the model (WP-93).

The production check of 23 October 2026 (D:/DEFENCEGATE TESTS/elig-check/FINDINGS.md) found rules the model's reading missed or got
wrong. Each one below is a sentence the official text states in fixed words; it is found by a pattern, quoted verbatim from the text
it was found in (so the quote is always in the document, the same test `eligibility.check_quotes` applies), and stored as a fact with
`origin: "rule_reading"` beside the model's facts. A reading replaces the model's fact of the same name. A pattern that does not match
reads nothing: the model's fact, or nothing, stands (fail closed).

  * EIC Accelerator (EIC work programme 2026, V "Can you apply?"): "a single company classified as a SME" is the applicant, and a
    small mid-cap only for "investment component only" support. The model read "not reserved for SMEs" (finding 2).
  * EIC STEP Scale Up and STEP Scale Up Defence (VI, VII): "The pre-commitment represents at least 20% of the total target funding
    round": without it a proposal is ineligible (finding 2).
  * Digital Europe call documents (the ECCC cybersecurity calls), per topic: "only entities designated ... as National Cyber Hubs are
    allowed to apply", "This topic targets exclusively National Coordination Centres", "The targeted stakeholders ... are public bodies
    acting as National Cyber Hubs" (finding 4), with the sentence that lets others join a consortium with them where there is one.
  * The agency pages of the AID (France): RAPID's consolidated staff count under 2,000, and the Cyber Defense Factory's staff of French
    nationality (finding 6). Their page text is not served (`funding.SOURCE_TEXT_SOURCES`), so these facts are served without a quote.

`python -m dgate.ops.rule_readings` applies them to what is already stored; `eligibility.extract_one` applies them to every new reading.
"""

from __future__ import annotations

import re
from typing import Any

ORIGIN = "rule_reading"
QUOTE_MAX = 400


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()[:QUOTE_MAX]


def _fact(value: Any, quote: str, note: str | None = None) -> dict[str, Any]:
    return {"value": value, "confidence": 1.0, "quote": _clean(quote), "note": note, "verified": True, "origin": ORIGIN}


# ----------------------------------------------------------------- the EIC work programme

_EIC_SME = re.compile(r"a\s+single\s+company\s+classified\s+as\s+an?\s+SME,?\s+and\s+established\s+within\s+a\s+Member\s+State\s+or\s+an\s+"
                      r"Associated\s+Country", re.I)
_EIC_MIDCAP = re.compile(r"a\s+single\s+company\s+classified\s+as\s+a\s+small\s+mid-?\s?cap\s+\(up\s+to\s+499\s+employees\)\s+established\s+in\s+a\s+"
                         r"Member\s+State\s+or\s+an\s+Associated\s+Country,\s+but\s+only\s+for\s+\S+investment\s+component\s+only\S+\s+support"
                         r"(?:\s+or\s+for\s+\S+blended\s+finance\S+\s+in\s+exceptional\s+cases\s+for\s+rapid\s+scale\s+up\s+purposes)?", re.I)
_EIC_PRECOMMIT = re.compile(r"The\s+pre-commitment\s+represents\s+at\s+least\s+20\s?%\s+of\s+the\s+total\s+target\s+funding\s+round"
                            r"(?:\s+you\s+are\s+aiming\s+to\s+raise)?\.?", re.I)


def _is_eic(topic: str) -> bool:
    return "-EIC-" in topic.upper()


def eic(text: str, topic: str) -> dict[str, dict[str, Any]]:
    """The readings of the EIC work programme for one EIC topic."""
    t = topic.upper()
    out: dict[str, dict[str, Any]] = {}
    if not _is_eic(t):
        return out
    if "ACCELERATOR" in t:
        sme, mid = _EIC_SME.search(text), _EIC_MIDCAP.search(text)
        if sme:
            note = (f"A small mid-cap (up to 499 employees) may apply only for “investment component only” support, or for blended finance "
                    f"in exceptional cases: {_clean(mid.group(0))}") if mid else None
            out["sme_only"] = _fact(True, sme.group(0), note)
    if "STEP" in t.split("-") or "DEFENCE" in t.split("-"):
        pre = _EIC_PRECOMMIT.search(text)
        if pre:
            out["investor_precommitment"] = _fact(
                True, pre.group(0), "The pre-commitment comes from a single qualified investor, for an equity investment; below 20 % of the round the proposal is ineligible.")
    return out


# ----------------------------------------------------------------- Digital Europe call documents, per topic

_HEADING = re.compile(r"^\s*(?P<code>[A-Z][A-Z0-9]*(?:-\s?[A-Z0-9]+){3,})\s*-{1,2}\s+(?P<title>[A-Z][^\n]*)$", re.M)
_SECTION_END = re.compile(r"^\s*\d{1,2}\.\s+Available\s+budget\b", re.M | re.I)
_DESIGNATED = (
    re.compile(r"only\s+entities\s+designated\s+(?:at\s+Member\s+State\s+level\s+)?as\s+(?P<who>[A-Z][\w\s]+?)\s+are\s+allowed\s+to\s+apply", re.I),
    re.compile(r"This\s+(?:topic|call)\s+targets\s+exclusively\s+(?P<who>[A-Z][\w\s]+?)(?=\s+which\b|\s+that\b|,|\.)", re.I),
    re.compile(r"target(?:ed)?\s+stakeholders\s+(?:under\s+[^.]{0,30}?)?are\s+(?P<who>public\s+bodies\s+acting\s+as\s+[A-Z][\w\s]+?)(?=,|\.|\s+as\s+identified)", re.I),
)
_PARTNERS = re.compile(r"[^.]*\b(?:other\s+relevant\s+public\s+or\s+private\s+partners\s+may\s+also\s+participate|in\s+consortium\s+with)\b[^.]*\.", re.I)


def _norm_code(code: str) -> str:
    return re.sub(r"-\s+", "-", code).upper()


def _same(mine: str, other: str) -> bool:
    from .eligibility import _same_topic

    return _same_topic(mine, other)


def topic_section(text: str, topic: str) -> str:
    """The part of a call document about one topic: from its heading to the next topic's, or to "3. Available budget". Lines of the
    table of contents (dot leaders) and of the budget table are not headings."""
    heads = [m for m in _HEADING.finditer(text) if "...." not in m.group(0) and "EUR" not in m.group("title")]
    for i, m in enumerate(heads):
        if not _same(topic, _norm_code(m.group("code"))):
            continue
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        stop = _SECTION_END.search(text, m.end())
        return text[m.end():min(end, stop.start() if stop else end)]
    return ""


def _for_this_topic(text: str, topic: str) -> list[str]:
    """Paragraphs elsewhere in the document that begin "For the topic <code>" and name this topic (section 6, consortium composition)."""
    out = []
    for m in re.finditer(r"For\s+the\s+topic\s+(?P<code>[A-Z][A-Z0-9]*(?:-\s?[A-Z0-9]+){3,})(?P<rest>.*?)(?=For\s+the\s+topic\s|\n\s*\n|$)", text, re.S):
        if _same(topic, _norm_code(m.group("code"))):
            out.append(m.group("rest"))
    return out


def designated(text: str, topic: str) -> dict[str, dict[str, Any]]:
    """Who alone may apply to one topic of a Digital Europe call document, when the document says so in one of the fixed phrases."""
    if not topic.upper().startswith("DIGITAL-"):
        return {}
    section = topic_section(text, topic)
    for part in [section, *_for_this_topic(text, topic)]:
        for pattern in _DESIGNATED:
            m = pattern.search(part)
            if not m:
                continue
            who = _clean(m.group("who"))
            # the sentence, from its start (after a full stop, a colon or a heading line) to its full stop
            start = max(part.rfind(".", 0, m.start()), part.rfind(":", 0, m.start()), part.rfind("\n\n", 0, m.start())) + 1
            end = part.find(".", m.end())
            quote = re.sub(r"^\s*Targeted\s+stakeholders\s+", "", part[start:end + 1 if end >= 0 else len(part)], flags=re.I)
            partners = _PARTNERS.search(section)
            others = re.sub(r"^\s*Targeted\s+stakeholders\s+", "", partners.group(0), flags=re.I) if partners else ""
            note = f"Others may take part in a consortium with them: {_clean(others)}" if partners else None
            return {"designated_applicants": _fact(who, quote, note)}
    return {}


def read_document(text: str, topic: str | None) -> dict[str, dict[str, Any]]:
    """Every reading of a stored call text for one topic (the EIC work programme or a call document)."""
    if not topic or not text:
        return {}
    return {**eic(text, topic), **designated(text, topic)}


# ----------------------------------------------------------------- the AID's pages (France)

_RAPID = re.compile(r"effectif\s+consolid[ée]\s+(?:de\s+)?(?:moins\s+de|inf[ée]rieur\s+[àa])\s+(?P<n>\d[\d\s.]{0,6}\d)\s+salari[ée]s", re.I)
_NATIONALITY = re.compile(r"Seuls\s+des\s+personnels\s+de\s+nationalit[ée]\s+(?P<n>fran[cç]aise)\s+peuvent\s+d[ée]poser\s+un\s+dossier(?:\s+et\s+contribuer\s+au\s+projet)?", re.I)


def read_aid_page(text: str | None) -> dict[str, dict[str, Any]]:
    """The rules an AID call page states in fixed words. Served without the quote: the agency's text is not served."""
    out: dict[str, dict[str, Any]] = {}
    m = _RAPID.search(text or "")
    if m:
        n = int(re.sub(r"\D", "", m.group("n")))
        out["max_group_headcount"] = _fact(n - 1, m.group(0), f"The consolidated staff count, counted with the group, must be under {n}.")
    m = _NATIONALITY.search(text or "")
    if m:
        out["staff_nationality"] = _fact("French", m.group(0), "Only staff of French nationality may submit the application and contribute to the project.")
    return out
