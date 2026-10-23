"""What a call funds, in at most three sentences of the topic's own description (WP-92).

The EU portal's topic document (`TopicDetails.description`, HTML) is written in sections:
Horizon topics in "Expected Outcome:" and "Scope:", EDF and EDIP topics in "Objective:", "Scope:",
"Types of activities", "Functional requirements" and "Expected impact". Only the purpose sections are
read here -- Objective and Expected outcome -- because Scope, the functional requirements and the
activity tables are where a topic describes the system it wants, and the product stores commercial
market information only (docs/CLAUDE.md, scope rules).

On production (probe of 23 October 2026) the headings are `<p class="topicdescriptionkind">Scope:</p>` paragraphs, and the
2026 EDF topics have no Objective at all (Scope, Targeted types of activities, Indicative budget). For an EDF or EDIP topic
with no Objective / Expected outcome section, the first sentence of Scope alone may be read, only when it opens with
"The objective of this topic is", "The aim of this topic is" or "This topic aims to", and through the same filter.

Each sentence of those sections then has to pass a strict filter, and the filter fails closed:

  * a sentence with a figure (a year aside) is dropped -- units, percentages, TRL levels, ranges;
  * a sentence with a specification word (range, payload, accuracy, frequency, latency, endurance,
    speed, altitude, requirement, "shall", design, architecture...) is dropped;
  * a sentence naming a system (an acronym not on the short list of programme and policy names, or a
    named platform) is dropped;
  * a sentence that is not positively recognised as saying what the call is for (aim, support,
    develop, strengthen, industry, SMEs, capability...) is dropped: unclassified is not kept;
  * a lead-in that ends in a colon, a link, an address, a fragment, is dropped.

What is left, up to three sentences, is the summary; nothing left is no summary, and the page keeps
its link to the official topic text. The full description is never stored outside the raw store.
"""

from __future__ import annotations

import html
import re
from typing import Any

MAX_SENTENCES = 3
MIN_CHARS = 40
MAX_CHARS = 400

# Section headings, as the portal writes them at the start of a block. Only the first group is read.
KEPT = r"expected\s*outcomes?|objectives?|specific\s+objectives?|general\s+objectives?"
OTHER = (r"scope|expected\s+impacts?|types?\s+of\s+activities|functional\s+requirements|"
         r"technical\s+requirements|specific\s+(?:topic\s+)?conditions|eligible\s+activities|"
         r"targeted\s+stakeholders|additional\s+information|specific\s+challenge|"
         r"general\s+conditions|topic\s+conditions|"
         r"description|expected\s+results|deliverables|requirements|activities|"
         r"targeted\s+types\s+of\s+activities|indicative\s+budget|budget|management\s+mode|form\s+of\s+funding")
_HEADING = re.compile(rf"^\s*(?P<h>{KEPT}|{OTHER})\s*(?::|$)\s*", re.I)
_KEPT = re.compile(rf"^(?:{KEPT})$", re.I)
_SCOPE = re.compile(r"^scope$", re.I)

# The portal's own heading markup (production, 23 October 2026): `<p class="topicdescriptionkind">Scope:</p>`.
# Whatever its label, such a paragraph is a heading; it is marked before the tags go.
HEADING_MARK = "\x01"
_KIND = re.compile(r"<p\b[^>]*class\s*=\s*[\"'][^\"']*\btopicdescriptionkind\b[^\"']*[\"'][^>]*>(.*?)</p>", re.I | re.S)

# EDF and EDIP topics of 2026 have no Objective section: their Scope opens with the aim. Only that first sentence of
# Scope may be read, only when it opens with one of these phrases, and only through the same filter.
AIM_OPENING = re.compile(r"^(?:the\s+(?:objective|aim)\s+of\s+this\s+topic\s+is|this\s+topic\s+aims\s+to)\b", re.I)
AIM_PROGRAMMES = ("EDF", "EDIP")

_BLOCK = re.compile(r"</?(?:p|div|br|h[1-6]|ul|ol|tr|table|section)\b[^>]*>", re.I)
_ITEM = re.compile(r"<li\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
# "e.g." and "i.e." end no sentence: "integrated systems (e.g. Air and missile defence)" was cut at "(e.g." (23 Oct 2026)
_SPLIT = re.compile(r"(?<=[.!?])(?<!\be\.g\.)(?<!\bi\.e\.)\s+(?=[A-Z(\"'])")

# A year is not a figure of a system; every other digit is treated as one.
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_DIGIT = re.compile(r"\d")

SPEC_WORDS = (
    "range", "ranges", "payload", "payloads", "accuracy", "accurate", "resolution", "frequency", "frequencies",
    "bandwidth", "latency", "latencies", "performance", "performances", "endurance", "speed", "speeds", "velocity",
    "altitude", "altitudes", "specification", "specifications", "specified", "shall", "requirement", "requirements",
    "calibre", "caliber", "armour", "armor", "weight", "mass", "power consumption", "detection", "detect", "detecting",
    "throughput", "precision", "sensitivity", "signature", "signatures", "stealth", "waveform", "waveforms",
    "algorithm", "algorithms", "architecture", "architectures", "design", "designs", "designed", "warhead", "warheads",
    "propulsion", "thrust", "ballistic", "lethality", "lethal", "kinetic", "guidance", "survivability",
    "trl", "technology readiness", "readiness level", "km", "kg", "ghz", "mhz", "db", "nm", "mach", "knots",
    "per cent", "percent", "dimension", "dimensions", "footprint", "radius", "wavelength", "spectrum", "spectral",
    "sensor performance", "protection level", "mtbf", "operating envelope", "kill chain", "firing", "fire control",
    # the words of tenders._TECHNICAL (WP-90's commercial subject) that the rules above do not already cover
    "tolerance", "tolerances", "mil-std", "stanag",
    # the words of the 2026 EDF Scope openings (production probe, 23 October 2026)
    "prototype", "prototypes", "prototyping", "hardware", "interceptor", "interceptors", "integrated with",
)
_SPEC = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in SPEC_WORDS) + r")\b", re.I)

# Named system designs. An acronym is a name; these are the policy and programme names a purpose
# sentence uses and that name no system.
ACRONYMS_OK = {"EU", "EDF", "EDIP", "EDIDP", "EDIRPA", "ASAP", "SME", "SMES", "SMEs", "NATO", "PESCO", "CSDP", "CARD",
               "EDA", "EDTIB", "EDTIBS", "R&D", "R&I", "RTD", "ICT", "AI", "CBRN", "CBRNE", "US", "UK", "UA", "EEA",
               "EFTA", "STEP", "USI", "EIC", "EUDIS", "HORIZON", "CEF", "TEN-T", "DG", "DEFIS", "ESA", "ECCC",
               "MS", "CDP", "EUMS", "EEAS", "SEAP", "SEAPS", "SEAPs", "FSTP", "IP", "IPR", "IPRS", "SDG", "SDGS"}
_ACRONYM = re.compile(r"(?<![\w&-])[A-Z][A-Z&]*[A-Z](?:-[A-Z]+)?s?(?![\w&])")
NAMED_SYSTEMS = ("eurodrone", "eurofighter", "typhoon", "rafale", "gripen", "leopard", "patriot", "meteor", "taurus",
                 "aster", "boxer", "tiger", "galileo", "copernicus", "iris", "essor", "twister", "fcas", "mgcs",
                 "male rpas", "a400m", "nh90")
_NAMED = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in NAMED_SYSTEMS) + r")\b", re.I)

# What a sentence about the purpose of a call says. A sentence with none of these is not classified, and dropped.
PURPOSE_WORDS = (
    r"aims?", r"aimed", r"objective", r"goal", r"purpose", r"expected to", r"outcomes?", r"contribut\w*", r"support\w*",
    r"develop\w*", r"strengthen\w*", r"improv\w*", r"enhanc\w*", r"foster\w*", r"enabl\w*", r"increas\w*",
    r"reduc\w* (?:the )?dependenc\w*", r"competitive\w*", r"industr\w*", r"smes?", r"market\w*", r"cooperat\w*",
    r"collaborat\w*", r"interoperab\w*", r"capabilit\w*", r"autonomy", r"resilien\w*", r"supply chains?",
    r"innovat\w*", r"solutions?", r"demonstrat\w*", r"uptake", r"deploy\w*", r"adopt\w*",
    r"integrat\w*", r"armed forces", r"end[- ]users?", r"cross-border", r"joint", r"procure\w*", r"production",
    r"manufactur\w*", r"ecosystems?", r"start-ups?", r"skills",
)
_PURPOSE = re.compile(r"\b(?:" + "|".join(PURPOSE_WORDS) + r")\b", re.I)


def _blocks(raw: str) -> list[str]:
    text = _KIND.sub(lambda m: f"\n{HEADING_MARK}{_TAG.sub(' ', m.group(1))}\n", raw)
    text = _ITEM.sub("\n• ", text)
    text = _BLOCK.sub("\n", text)
    text = html.unescape(_TAG.sub(" ", text)).replace("\xa0", " ")
    return [re.sub(r"[ \t]+", " ", b).strip() for b in text.split("\n") if b.strip()]


def _sections(description: Any) -> list[tuple[str | None, str]]:
    """(section, block) in order: section `kept` (Objective, Expected outcome), `scope`, `other`, or None before any
    heading. A `topicdescriptionkind` paragraph is a heading whatever it says; so is a block that opens with a known label."""
    if not isinstance(description, str) or not description.strip():
        return []
    out: list[tuple[str | None, str]] = []
    section: str | None = None
    for block in _blocks(description):
        label, rest = None, block
        if block.startswith(HEADING_MARK):
            label, rest = block[1:].strip().rstrip(":").strip(), ""
        else:
            m = _HEADING.match(block)
            if m:
                label, rest = m.group("h"), block[m.end():].strip()
        if label is not None:
            label = re.sub(r"\s+", " ", label).strip()
            section = "kept" if _KEPT.match(label) else "scope" if _SCOPE.match(label) else "other"
        if rest:
            out.append((section, rest))
    return out


def purpose_text(description: Any) -> list[str]:
    """The blocks of the Objective and Expected outcome sections, in order; nothing else."""
    return [b for s, b in _sections(description) if s == "kept"]


def verdict(sentence: str) -> str | None:
    """Why a sentence is dropped, or None when it is kept. Fail closed: no purpose word is a drop."""
    s = sentence.strip()
    if not (MIN_CHARS <= len(s) <= MAX_CHARS):
        return "length"
    if s.endswith(":") or s[-1] not in ".!":
        return "fragment"
    if "@" in s or "http" in s.lower() or "www." in s.lower():
        return "link"
    if _DIGIT.search(_YEAR.sub("", s)) or "%" in s:
        return "figure"
    if _SPEC.search(s):
        return "specification"
    if _NAMED.search(s) or any(a not in ACRONYMS_OK and a.removesuffix("s") not in ACRONYMS_OK
                               for a in _ACRONYM.findall(s)):
        return "named system"
    if not _PURPOSE.search(s):
        return "unclassified"
    return None


def _units(block: str) -> list[str]:
    if block.startswith("•"):
        item = block.lstrip("• ").strip().rstrip(";,").strip()
        item = re.sub(r"\s+(?:and|or)$", "", item)
        if not item:
            return []
        item = item[0].upper() + item[1:]
        return [item if item[-1] in ".!?:" else item + "."]
    return [u.strip() for u in _SPLIT.split(block) if u.strip()]


def scope_aim(description: Any) -> tuple[str, str | None] | None:
    """The first sentence of Scope with its verdict, for a topic with no Objective / Expected outcome section: kept
    only when it opens with an aim phrase (AIM_OPENING) and passes `verdict`. None when there is no Scope sentence."""
    blocks = [b for s, b in _sections(description) if s == "scope"]
    units = _units(blocks[0]) if blocks else []
    if not units:
        return None
    first = units[0]
    return first, (verdict(first) if AIM_OPENING.match(first) else "not an aim sentence")


def sentences(description: Any, identifier: str | None = None) -> list[tuple[str, str | None]]:
    """Every sentence read with its verdict (None = kept), for tests and the self-check: the purpose sections, or, for
    an EDF / EDIP topic that has none, the first sentence of Scope (`scope_aim`)."""
    out = [(u, verdict(u)) for b in purpose_text(description) for u in _units(b)]
    if not out and (identifier or "").upper().startswith(AIM_PROGRAMMES):
        aim = scope_aim(description)
        out = [aim] if aim else []
    return out


def funds_summary(details: dict[str, Any] | None) -> str | None:
    """At most three kept sentences of the topic's Objective / Expected outcome (or its Scope's aim sentence), or None."""
    if not isinstance(details, dict):
        return None
    kept: list[str] = []
    for s, why in sentences(details.get("description"), str(details.get("identifier") or "")):
        if why is None and s not in kept:
            kept.append(s)
        if len(kept) == MAX_SENTENCES:
            break
    return " ".join(kept) or None
