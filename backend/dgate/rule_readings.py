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
_EIC_SINGLE = re.compile(r"In\s+the\s+case\s+of\s+single\s+beneficiary\s+projects,\s+mid-?\s?caps\s+and\s+larger\s+companies\s+will\s+not\s+be\s+permitted\.", re.I)


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
    if "PATHFINDER" in t or "PATHFINDERCHALLENGES" in t:
        # WP-102 (B12): the Pathfinder section's rule, the same for every Challenge topic (the model read it for 128, not for 130)
        single = _EIC_SINGLE.search(text)
        if single:
            out["single_beneficiary_excludes"] = _fact("mid-caps and larger companies", single.group(0))
    if "STEP" in t.split("-") or "DEFENCE" in t.split("-"):
        pre = _EIC_PRECOMMIT.search(text)
        if pre:
            out["investor_precommitment"] = _fact(
                True, pre.group(0), "The pre-commitment comes from a single qualified investor, for an equity investment; below 20 % of the round the proposal is ineligible.")
    return out


# ----------------------------------------------------------------- Digital Europe call documents, per topic

# WP-99: the stored texts of production separate the code from the title with an en or em dash ("...-11-NCC – Enhancing", "...-12- CBCH —
# Cross-Border", "...-09-UPTAKE– Uptake"), not "-" or "--": only the headings with a hyphen were found, so of the ECCC topics only the ones
# named again in a "For the topic" paragraph (NATCH, NCH) were read. A heading is one line (a code split over two lines is a table row).
_HEADING = re.compile(r"^[ \t]*(?P<code>[A-Z][A-Z0-9]*(?:-[ \t]?[A-Z0-9]+){3,})[ \t]*(?:-{1,2}|[–—])[ \t]*(?P<title>[A-Z][^\n]*)$", re.M)
_SECTION_END = re.compile(r"^\s*\d{1,2}\.\s+Available\s+budget\b", re.M | re.I)
_DESIGNATED = (
    re.compile(r"only\s+entities\s+designated\s+(?:at\s+Member\s+State\s+level\s+)?as\s+(?P<who>[A-Z][\w\s]+?)\s+are\s+allowed\s+to\s+apply", re.I),
    re.compile(r"This\s+(?:topic|call)\s+targets\s+exclusively\s+(?P<who>[A-Z][\w\s]+?)(?=\s+which\b|\s+that\b|,|\.)", re.I),
    re.compile(r"target(?:ed)?\s+stakeholders\s+(?:under\s+[^.]{0,30}?)?are\s+(?P<who>public\s+bodies\s+acting\s+as\s+[A-Z][\w\s]+?)(?=,|\.|\s+as\s+identified)", re.I),
    # WP-102 (A23, COORDPREP): "The action is targeted at public bodies that have been designated or entrusted by the relevant Member State
    # with responsibilities in the area of cybersecurity, ..." (others join as partners: _PARTNERS)
    re.compile(r"The\s+action\s+is\s+targeted\s+at\s+(?P<who>public\s+bodies\s+that\s+have\s+been\s+designated\s+or\s+entrusted\s+by\s+the\s+relevant\s+"
               r"Member\s+State\s+with\s+responsibilities\s+in\s+the\s+area\s+of\s+cybersecurity)", re.I),
)
_PARTNERS = re.compile(r"[^.]*\b(?:other\s+relevant\s+public\s+or\s+private\s+partners\s+may\s+also\s+participate|in\s+consortium\s+with)\b[^.]*\.", re.I)


def _norm_code(code: str) -> str:
    return re.sub(r"-\s+", "-", code).upper()


def _same(mine: str, other: str) -> bool:
    """`other` names exactly this topic: the same code, or the same call prefix and an abbreviation of the last part (the document writes
    NCH for the portal's NATCH). Stricter than eligibility._same_topic on purpose: the call's own code (a prefix of every topic's) and
    another year's code are not this topic, or one topic's designated bodies are read for every topic of the document (production
    report of 23 October 2026: all 11 topics of DEP-10, 11 and 12)."""
    a, b = mine.upper(), other.upper()
    if a == b:
        return True
    (pa, _, la), (pb, _, lb) = a.rpartition("-"), b.rpartition("-")
    if pa != pb or not pa:
        return False
    short, long = sorted((la, lb), key=len)
    it = iter(long)
    return len(short) >= 3 and short[0] == long[0] and all(ch in it for ch in short)


def _wrapped_toc(text: str, m: re.Match[str]) -> bool:
    """A table-of-contents line whose title wraps: its dot leaders are on the next line."""
    start = m.end() + 1
    end = text.find("\n", start)
    return "...." in text[start:end if end >= 0 else len(text)]


def topic_section(text: str, topic: str) -> str:
    """The part of a call document about one topic: from its heading to the next topic's, or to "3. Available budget". Lines of the
    table of contents (dot leaders) and of the budget table are not headings."""
    heads = [m for m in _HEADING.finditer(text) if "...." not in m.group(0) and "EUR" not in m.group("title") and not _wrapped_toc(text, m)]
    found = ""
    for i, m in enumerate(heads):
        if not _same(topic, _norm_code(m.group("code"))):
            continue
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        stop = _SECTION_END.search(text, m.end())
        part = text[m.end():min(end, stop.start() if stop else end)]
        # the same heading twice (a page header repeats it): the topic's section is the longest part
        found = part if len(part) > len(found) else found
    return found


def _for_this_topic(text: str, topic: str) -> list[str]:
    """Paragraphs elsewhere in the document that begin "For the topic <code>" and name this topic (section 6, consortium composition)."""
    out = []
    for m in re.finditer(r"For\s+the\s+topic\s+(?P<code>[A-Z][A-Z0-9]*(?:-\s?[A-Z0-9]+){3,})(?P<rest>.*?)(?=For\s+the\s+topic\s|\n\s*\n|$)", text, re.S):
        if _same(topic, _norm_code(m.group("code"))):
            out.append(m.group("rest")[:600])           # the paragraph about this topic, not the rest of the document
    return out


def designated(text: str, topic: str) -> dict[str, dict[str, Any]]:
    """Who alone may apply to one topic of a Digital Europe call document, when the document says so in one of the fixed phrases."""
    if not topic.upper().startswith("DIGITAL-"):
        return {}
    section = topic_section(text, topic)
    parts = [section, *_for_this_topic(text, topic)]
    # WP-99: the strongest phrase first, wherever it is ("only entities designated ... are allowed to apply" in the eligibility section
    # beats "targeted stakeholders are public bodies acting as ..." in the topic's own section)
    for pattern, part in ((pattern, part) for pattern in _DESIGNATED for part in parts):
        m = pattern.search(part)
        if m:
            who = _clean(m.group("who"))
            # the sentence, from its start (after a full stop, a colon or a heading line) to its full stop; a page footer or the heading
            # "Targeted stakeholders" before it is not part of it
            start = max(part.rfind(".", 0, m.start()), part.rfind(":", 0, m.start()), part.rfind("\n\n", 0, m.start())) + 1
            end = part.find(".", m.end())
            quote = re.sub(r"^.*?Targeted\s+stakeholders\s+", "", part[start:end + 1 if end >= 0 else len(part)], flags=re.I | re.S)
            partners = _PARTNERS.search(section)
            others = re.sub(r"^\s*Targeted\s+stakeholders\s+", "", partners.group(0), flags=re.I) if partners else ""
            note = f"Others may take part in a consortium with them: {_clean(others)}" if partners else None
            return {"designated_applicants": _fact(who, quote, note)}
    return {}


def read_document(text: str, topic: str | None) -> dict[str, dict[str, Any]]:
    """Every reading of a stored call text for one topic (the EIC work programme or a call document); without a topic, what the general
    annexes state for every call of a kind (WP-102)."""
    if not text:
        return {}
    if not topic:
        return general_annexes(text)
    return {**eic(text, topic), **designated(text, topic)}


# ----------------------------------------------------------------- WP-102: the Horizon Europe general annexes

# Annex H, "Requirements for all types of actions supporting PCP or PPI": the procurers prepare and execute the procurement; others take part
# only in additional activities and only without a conflict of interest (B6: a supplier is no beneficiary of a PPI). Served for PCP and PPI
# actions only (eligibility._served_fact).
_PCP_PPI = re.compile(r"Other\s+entities\s+\(e\.g\.\s*end\s*-?\s*users\)\s+that\s+do\s+not\s+have\s+a\s+conflict\s+of\s+interest\s+with\s+the\s+PCP/PPI"
                      r"[^.]*\.", re.I)


def general_annexes(text: str) -> dict[str, dict[str, Any]]:
    m = _PCP_PPI.search(text or "")
    if not m:
        return {}
    return {"procurement_conflict": _fact(True, m.group(0), "The procurement is prepared and executed by public procurers (or entities with "
                                                              "their mandate); other entities take part only in additional activities.")}


# ----------------------------------------------------------------- WP-102: the topic's conditions as the portal publishes them

_FOOTNOTE = re.compile(r"\[\[.*?\]\]", re.S)
_INVOLVES = re.compile(r"This\s+topic\s+requires\s+the\s+(?:active\s+)?involvement,?\s+as\s+beneficiaries,?\s+of:?\s+(?P<who>at\s+least\s+\d+\s+[^.]+?)\.(?=\s|$)", re.I)
_CAP = re.compile(r"Participation\s+of\s+non-SME\s+industries\s+and\s+Research\s+and\s+Technology\s+Organisations\s+\(RTOs\)\s+is\s+not\s+excluded,\s+"
                  r"but\s+it\s+must\s+be\s+limited\s+to\s+(?P<n>\d{1,2})\s?%\s+of\s+the\s+proposed\s+budget\.", re.I)
_CONTROL = re.compile(r"entities\s+established\s+in\s+an\s+eligible\s+country\s+listed\s+above,\s+but\s+which\s+are\s+directly\s+or\s+indirectly\s+controlled\s+"
                      r"by\s+a\s+non-eligible\s+country\s+or\s+by\s+a\s+non-eligible\s+country\s+entity,\s+(?P<verb>shall|may)\s+not\s+participate\s+in\s+the\s+action"
                      r"(?P<unless>\s+unless\s+it\s+can\s+be\s+demonstrated,\s+by\s+means\s+of\s+guarantees\s+approved\s+by\s+the\s+eligible\s+country\s+of\s+establishment[^.]*)?\.", re.I)
_JU_COUNTRIES = re.compile(r"participation\s+is\s+limited\s+to\s+legal\s+entities\s+established\s+in\s+(?P<who>Member\s+States\s+or\s+Participating\s+States\s+of\s+the\s+"
                           r"[A-Za-z]+\s+JU)\s*\[\s*At\s+the\s+moment\s+of\s+the\s+adoption\s+of\s+[^,\]]{0,60},\s+the\s+Participating\s+States\s+of\s+[A-Za-z]+\s+JU\s+are\s+"
                           r"(?P<list>[^\]]{10,900}?)\.?\s*\]", re.I)
_JU_LATER = re.compile(r"In\s+addition,\s+legal\s+entities\s+which\s+are\s+established\s+in\s+associated\s+countries\s+to\s+Horizon\s+Europe\s+that\s+become\s+a\s+"
                       r"participant\s+state\s+to\s+[A-Za-z]+\s+JU\s+before\s+the\s+signature\s+of\s+the\s+grant\s+agreement\s+will\s+also\s+become\s+eligible\.", re.I)
_MSCA_DN = re.compile(r"[^.]*must\s+fulfil\s+all\s+the\s+admissibility\s+and\s+eligibility\s+conditions\s+of\s+the\s+MSCA\s+Doctoral\s+Networks\s+call[^.]*\.", re.I)
# The rule that sentence points to, in the MSCA part of the work programme (Horizon Europe Work Programme 2026-2027, 2. Marie
# Skłodowska-Curie Actions, MSCA Doctoral Networks, 1.3.1 Participating organisations), word for word.
MSCA_DN_SOURCE = "Horizon Europe Work Programme 2026-2027, 2. Marie Skłodowska-Curie Actions, MSCA Doctoral Networks, 1.3.1 Participating organisations"
MSCA_DN_RULE = ("Applications must be submitted by a consortium including at least three independent legal entities, each established in a "
                "different EU Member State or Horizon Europe Associated Country and with at least one of them established in an EU Member State.")


def read_conditions(text: str | None, topic: str | None) -> dict[str, dict[str, Any]]:
    """The rules a Horizon Europe topic's conditions text (the portal's, `call.eligibility_text`) states in fixed words. Read when the call
    is served (eligibility.assemble), so nothing is stored: the quote is the text's own, without its footnotes."""
    if not text or not (topic or "").upper().startswith("HORIZON-"):
        return {}
    flat = re.sub(r"\s+", " ", _FOOTNOTE.sub("", text))
    out: dict[str, dict[str, Any]] = {}
    m = _INVOLVES.search(flat)
    if m:
        out["required_partners"] = _fact(f"{m.group('who').strip()}, as beneficiaries", m.group(0))
    m = _CAP.search(flat)
    if m:
        out["non_sme_budget_cap"] = _fact(int(m.group("n")), m.group(0))
    m = _CONTROL.search(flat)
    if m:
        out["ownership_control_restriction"] = _fact(True, m.group(0), (
            "Participation is possible only with guarantees approved by the eligible country of establishment." if m.group("unless")
            else "Entities controlled from a non-eligible country shall not participate; the text states no way round."))
    m = _JU_COUNTRIES.search(flat)
    if m:
        later = _JU_LATER.search(flat)
        out["eligible_countries"] = _fact(f"{m.group('who')}: {m.group('list').strip()}", m.group(0), later.group(0) if later else None)
    m = _MSCA_DN.search(flat)
    if m:
        note = f"The MSCA Doctoral Networks rule ({MSCA_DN_SOURCE}): {MSCA_DN_RULE}"
        out["consortium_required"] = _fact(True, m.group(0).strip(), note)
        out["min_entities"] = _fact(3, m.group(0).strip(), note)
        out["min_countries"] = _fact(3, m.group(0).strip(), note)
    return out


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
