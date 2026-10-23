"""What a call funds, in at most three sentences of the topic's own description (WP-92).

The EU portal's topic document (`TopicDetails.description`, HTML) is written in sections:
Horizon topics in "Expected Outcome:" and "Scope:", EDF and EDIP topics in "Objective:", "Scope:",
"Types of activities", "Functional requirements" and "Expected impact". Only the purpose sections are
read here -- Objective and Expected outcome -- because Scope, the functional requirements and the
activity tables are where a topic describes the system it wants, and the product stores commercial
market information only (docs/CLAUDE.md, scope rules).

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
         r"description|expected\s+results|deliverables|requirements|activities")
_HEADING = re.compile(rf"^\s*(?P<h>{KEPT}|{OTHER})\s*(?::|$)\s*", re.I)
_KEPT = re.compile(rf"^(?:{KEPT})$", re.I)

_BLOCK = re.compile(r"</?(?:p|div|br|h[1-6]|ul|ol|tr|table|section)\b[^>]*>", re.I)
_ITEM = re.compile(r"<li\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")

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
    r"innovat\w*", r"solutions?", r"prototypes?", r"demonstrat\w*", r"uptake", r"deploy\w*", r"adopt\w*",
    r"integrat\w*", r"armed forces", r"end[- ]users?", r"cross-border", r"joint", r"procure\w*", r"production",
    r"manufactur\w*", r"ecosystems?", r"start-ups?", r"skills",
)
_PURPOSE = re.compile(r"\b(?:" + "|".join(PURPOSE_WORDS) + r")\b", re.I)


def _blocks(raw: str) -> list[str]:
    text = _ITEM.sub("\n• ", raw)
    text = _BLOCK.sub("\n", text)
    text = html.unescape(_TAG.sub(" ", text)).replace("\xa0", " ")
    return [re.sub(r"[ \t]+", " ", b).strip() for b in text.split("\n") if b.strip()]


def purpose_text(description: Any) -> list[str]:
    """The blocks of the Objective and Expected outcome sections, in order; nothing else."""
    if not isinstance(description, str) or not description.strip():
        return []
    out: list[str] = []
    keep = False
    for block in _blocks(description):
        m = _HEADING.match(block)
        if m:
            keep = bool(_KEPT.match(re.sub(r"\s+", " ", m.group("h")).strip()))
            block = block[m.end():].strip()
            if not block:
                continue
        if keep:
            out.append(block)
    return out


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


def sentences(description: Any) -> list[tuple[str, str | None]]:
    """Every sentence of the purpose sections with its verdict (None = kept), for tests and the self-check."""
    return [(u, verdict(u)) for b in purpose_text(description) for u in _units(b)]


def funds_summary(details: dict[str, Any] | None) -> str | None:
    """At most three kept sentences of the topic's Objective / Expected outcome, or None."""
    if not isinstance(details, dict):
        return None
    kept: list[str] = []
    for s, why in sentences(details.get("description")):
        if why is None and s not in kept:
            kept.append(s)
        if len(kept) == MAX_SENTENCES:
            break
    return " ".join(kept) or None
