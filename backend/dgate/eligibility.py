"""Eligibility of an EU call, read from its call document (PDF) by a language model.

The portal's own condition text only points to the call document ("Eligible countries:
described in section 6"), so the rules are in the PDF. This fetches the PDF, keeps its
text (`call_document_text`), asks the model for a fixed set of facts, and stores the answer
(`call_eligibility`). Three safeguards against a confident wrong answer:

  * every fact carries a verbatim quote, and the quote is looked up in the document text;
    a fact whose quote is not found is kept but marked `verified: false` and its confidence
    is capped at 0.3 (the site must not show it as a rule);
  * a fact the document does not state is null, not guessed from general EU rules;
  * the cost is capped (`llm.py`).

Commercial and eligibility information only: no technical content of the work is extracted.

Calls with no call document (most Horizon topics) have their rules in two other places, and
`sources_of` maps a call to them deterministically (WP-31):

  * `general`  the work programme's general annexes (or the EIC work programme), one PDF shared
               by many calls, read once;
  * `topic`    the topic's own conditions text, as the portal publishes it (sections 3 and 6),
               when it says more than "described in Annex B".

Each row of `call_eligibility` records which of the three it is (`scope`), and the note of a
fact read from a general or topic source says so, so the site never presents a general rule as
the topic's own. The prompt for a call document is unchanged (`PROMPT_VERSION` stays).
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel

from . import llm
from .config import settings
from .enrichment.base import strict_schema

TASK = "call_eligibility"
PROMPT_VERSION = 3
MAX_PDF_BYTES = 40 * 1024 * 1024
MAX_CHARS = 350_000          # about 90,000 tokens: the longest call documents are cut here
UNVERIFIED_CAP = 0.3


class FactStr(BaseModel):
    value: str | None
    confidence: float
    quote: str | None
    note: str | None


class FactBool(BaseModel):
    value: bool | None
    confidence: float
    quote: str | None
    note: str | None


class FactInt(BaseModel):
    value: int | None
    confidence: float
    quote: str | None
    note: str | None


class FactList(BaseModel):
    value: list[str] | None
    confidence: float
    quote: str | None
    note: str | None


class Eligibility(BaseModel):
    eligible_countries: FactStr         # where applicants must be established, in the document's words
    entity_types: FactList              # who may apply: SME, university, public body, any legal entity...
    consortium_required: FactBool       # must applicants form a consortium
    min_entities: FactInt               # smallest number of legal entities in a consortium
    min_countries: FactInt              # smallest number of different countries among them
    single_applicant_allowed: FactBool
    sme_only: FactBool                  # reserved for small and medium enterprises
    natural_persons_allowed: FactBool
    ownership_control_restriction: FactBool   # entities controlled by non-eligible countries/entities are excluded
    funding_rate: FactStr               # the funding or reimbursement rate, in the document's words (a range or a ceiling stays a range)
    cascade_funding: FactBool           # financial support to third parties (FSTP / cascade) is part of the action


FIELDS = list(Eligibility.model_fields)

SYSTEM = (
    "You read one EU call document and report who may apply, as a fixed set of facts. "
    "Use only the text you are given. If the document does not state a fact, return value null "
    "and confidence 0: never fill a gap from general knowledge of EU programmes. "
    "For every fact you do state, copy the sentence that states it verbatim into `quote` "
    "(at most 300 characters, no paraphrase, no ellipsis). Confidence is between 0 and 1: "
    "1 means the sentence says it plainly, 0.5 means you combined several sentences, below 0.5 "
    "means you are unsure. `note` is a short qualification when the fact holds only under a "
    "condition (for example: only if the applicant is a specific kind of body), otherwise null. "
    "A yes/no fact states the general rule; an exception to it goes in the note, never in the "
    "value (if natural persons are not eligible except sole traders, the value is false and the "
    "note names the exception). If the document states a rule only for one topic or one type of "
    "action, or the rule differs between them, say so in the note and report the lowest or most "
    "general case in the value. Eligibility and funding conditions only; do not describe the "
    "technical content of the work."
)


def schema() -> dict[str, Any]:
    return strict_schema(Eligibility)


# ----------------------------------------------------------------- the document

def _get_pdf(http: httpx.Client, url: str) -> bytes:
    r = http.get(url)
    if r.status_code != 200:
        raise ValueError(f"HTTP {r.status_code}")
    content = r.content
    if not content.startswith(b"%PDF") and "text/html" in r.headers.get("content-type", ""):
        # The ECCC site serves a page whose download link is the file.
        m = re.search(r'href="(/document/download/[^"]+)"', r.text)
        if m:
            r2 = http.get(urljoin(str(r.url), m.group(1)))
            if r2.status_code == 200:
                content = r2.content
    if len(content) > MAX_PDF_BYTES:
        raise ValueError("file too large")
    if not content.startswith(b"%PDF"):
        raise ValueError("not a PDF")
    return content


def fetch_text(url: str, client: httpx.Client | None = None) -> tuple[str, int, str]:
    """(sha256 of the file, number of pages, text) of a PDF."""
    from pypdf import PdfReader

    http = client or httpx.Client(timeout=120, follow_redirects=True,
                                  headers={"User-Agent": settings().user_agent})
    try:
        content = _get_pdf(http, url)
    finally:
        if client is None:
            http.close()
    reader = PdfReader(io.BytesIO(content))
    pages = [(p.extract_text() or "") for p in reader.pages]
    text = re.sub(r"[ \t]+", " ", "\n".join(pages))
    return hashlib.sha256(content).hexdigest(), len(pages), text


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.casefold()).strip()


def check_quotes(answer: dict[str, Any], text: str) -> dict[str, Any]:
    """Add `verified` to every fact: whether its quote is in the document text. A stated fact
    without a found quote keeps its value but its confidence is capped."""
    haystack = _norm(text)
    out: dict[str, Any] = {}

    def found(quote: str) -> bool:
        q = _norm(quote)
        # A long quote the model cut short or tidied at its end is still the document's sentence.
        return bool(q) and (q in haystack or (len(q) >= 100 and q[:100] in haystack))

    for name in FIELDS:
        fact = dict(answer[name])
        stated = fact["value"] is not None
        quote = (fact.get("quote") or "").strip()
        fact["verified"] = bool(stated and found(quote))
        if stated and not fact["verified"]:
            fact["confidence"] = min(float(fact["confidence"]), UNVERIFIED_CAP)
        out[name] = fact
    return out


# ----------------------------------------------------------------- where the rules are

SCOPES = ("call_document", "general", "topic")
TOPIC_KEY_PREFIX = "call-text:"

# The general annexes of a Horizon work programme, and the EIC's own work programme: one PDF each,
# shared by every call of the programme. Taken from the URLs the portal lists with the call.
_GENERAL_ANNEXES = re.compile(r"/wp-\d+-general-annexes_[a-z]+-(\d{4})(?:-(\d{4}))?_en\.pdf", re.I)
_EIC_PROGRAMME = re.compile(r"[/=]EIC-Work-Programme-(\d{4})\.pdf", re.I)

# What a general or topic source is, said in the note of every fact read from it.
SCOPE_NOTES = {
    "general": "General rule of the work programme annexes; the topic or the type of action may add or change it.",
    "topic": "Stated in this topic's own conditions.",
}
USER_HEADERS = {
    "call_document": "Call document:\n\n",
    "general": ("General annexes of the work programme. They apply to every call of the programme, "
                "and a topic may add conditions of its own:\n\n"),
    "topic": ("Conditions of one topic, as the funding portal publishes them. The general rules are in "
              "the work programme annexes and are not part of this text:\n\n"),
}

_SECTION_3 = re.compile(r"\b3\.\s+Other\s+Eligib\w*\s+Conditions?\b(.*?)(?=\b4\.\s+Financial\b|\Z)", re.I | re.S)
_SECTION_6 = re.compile(r"\b6\.\s+Legal\s+and\s+financial\s+set-?up\b(.*?)(?=Application\s+and\s+evaluation\s+forms|\Z)",
                        re.I | re.S)
# Boilerplate that points elsewhere: "described in Annex B of the Work Programme General Annexes."
_POINTER = re.compile(r"(?:Specific\s+conditions\s+)?described\s+in\s+[^.]*?(?:Annexes?|Work\s+Programme|\])[^.]*\.?", re.I)
MIN_TOPIC_CHARS = 60


@dataclass(frozen=True)
class Source:
    """Where some of a call's rules are written. `key` is the call_eligibility key: the document's
    URL, or 'call-text:<hash>' for a topic's own text (held in `text`)."""
    scope: str
    key: str
    label: str
    text: str | None = None


def topic_text(eligibility_text: str | None) -> str | None:
    """The topic's own conditions (sections 3 and 6 of the portal's text), or None when they only
    point to the annexes. Deterministic; the text is the portal's, unedited apart from e-mail addresses."""
    raw = eligibility_text or ""
    parts = []
    for pattern in (_SECTION_3, _SECTION_6):
        m = pattern.search(raw)
        if m:
            body = re.sub(r"\s+", " ", m.group(1)).strip()
            if len(_POINTER.sub("", body).strip(" .;:-")) >= MIN_TOPIC_CHARS:
                parts.append(body)
    if not parts:
        return None
    from .normalise import redact_emails

    # What is stored and sent to the model carries no e-mail address, whatever the portal text held.
    return redact_emails("\n\n".join(parts))


def topic_key(text: str) -> str:
    return TOPIC_KEY_PREFIX + hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _general_annex(urls: list[str]) -> str | None:
    """The one general source of a call: the EIC work programme when the call lists it (its text
    says "described in Annex 2 of the EIC Work Programme"; the Horizon annexes it also lists are
    older boilerplate), otherwise the newest Horizon general annexes."""
    eic = [(int(m.group(1)), "eic.ec.europa.eu/system/files" in u, u) for u in urls
           if (m := _EIC_PROGRAMME.search(u))]
    if eic:
        return max(eic)[2]
    best: tuple[tuple[int, int], str] | None = None
    for u in urls:
        m = _GENERAL_ANNEXES.search(u)
        if m:
            years = (int(m.group(1)), int(m.group(2) or m.group(1)))
            if best is None or (years, u) > best:
                best = (years, u)
    return best[1] if best else None


def sources_of(cond: dict[str, Any] | None, eligibility_text: str | None) -> list[Source]:
    """The sources of a call's eligibility rules, from what the portal listed with it. A call with
    a call document is read from that document alone. Without one: the general annexes (or the EIC
    work programme) when the portal lists them, and the topic's own text when it says more than a
    pointer. Nothing is guessed from the call's name."""
    docs = [d for d in (cond or {}).get("documents") or []
            if isinstance(d, dict) and isinstance(d.get("url"), str) and d["url"].startswith("https://")]
    calls = [d for d in docs if str(d.get("label", "")).lower().startswith("call document")]
    if calls:
        return [Source("call_document", d["url"], str(d.get("label") or "Call document")) for d in calls]
    out: list[Source] = []
    general = _general_annex([d["url"] for d in docs])
    if general:
        label = "EIC work programme" if _EIC_PROGRAMME.search(general) else "General annexes of the work programme"
        out.append(Source("general", general, label))
    text = topic_text(eligibility_text)
    if text:
        out.append(Source("topic", topic_key(text), "Conditions stated for this topic", text))
    return out


def annotate_scope(fields: dict[str, Any], scope: str) -> dict[str, Any]:
    """Say, in the note of every stated fact, whether it is a general rule or the topic's own."""
    prefix = SCOPE_NOTES.get(scope)
    if not prefix:
        return fields
    out = {}
    for name, fact in fields.items():
        fact = dict(fact)
        if fact.get("value") is not None:
            fact["note"] = f"{prefix} {fact['note']}".strip() if fact.get("note") else prefix
        out[name] = fact
    return out


# ----------------------------------------------------------------- the run

def call_documents(conn) -> list[dict[str, Any]]:
    """The distinct call-document URLs of the EU calls, open calls first."""
    rows = conn.execute(
        """SELECT d->>'url' AS url, count(*) AS calls,
                  count(*) FILTER (WHERE c.status = 'open') AS open_calls
             FROM call c JOIN source s ON s.id = c.source_id,
                  jsonb_array_elements(COALESCE(c.conditions_raw->'documents', '[]'::jsonb)) d
            WHERE s.code = 'eu_portal' AND lower(d->>'label') LIKE 'call document%%'
            GROUP BY 1 ORDER BY open_calls DESC, calls DESC, url""").fetchall()
    return [dict(r) for r in rows]


def extraction_units(conn) -> list[dict[str, Any]]:
    """Everything to read, once each: call documents, general annexes and topic texts, with the
    number of EU calls (and open ones) each serves, open calls first."""
    rows = conn.execute(
        """SELECT c.status, c.conditions_raw, c.eligibility_text
             FROM call c JOIN source s ON s.id = c.source_id WHERE s.code = 'eu_portal'""").fetchall()
    units: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        for src in sources_of(r["conditions_raw"], r["eligibility_text"]):
            u = units.setdefault((src.scope, src.key), {
                "url": src.key, "scope": src.scope, "label": src.label, "text": src.text,
                "calls": 0, "open_calls": 0})
            u["calls"] += 1
            u["open_calls"] += 1 if r["status"] == "open" else 0
    return sorted(units.values(), key=lambda u: (-u["open_calls"], -u["calls"], u["url"]))


def extract_one(conn, url: str, *, force: bool = False, client: httpx.Client | None = None,
                llm_client: httpx.Client | None = None, scope: str = "call_document",
                text: str | None = None) -> dict[str, Any]:
    """Fetch (if not held), ask, check the quotes, store. Returns a short report.
    `text` is a topic's own conditions: it is kept as the document and nothing is fetched."""
    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}")
    held = conn.execute("SELECT 1 FROM call_eligibility WHERE url = %s AND prompt_version = %s",
                        (url, PROMPT_VERSION)).fetchone()
    if held and not force:
        return {"url": url, "status": "held"}
    doc = conn.execute("SELECT text FROM call_document_text WHERE url = %s", (url,)).fetchone()
    if text is not None:
        digest, pages, body = hashlib.sha256(text.encode("utf-8")).hexdigest(), 1, text
    elif doc is None:
        digest, pages, body = fetch_text(url, client)
    else:
        digest, pages, body = None, 0, doc["text"]
    if digest is not None:
        truncated = len(body) > MAX_CHARS
        body = body[:MAX_CHARS]
        conn.execute(
            """INSERT INTO call_document_text (url, sha256, pages, chars, truncated, text)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (url) DO UPDATE SET sha256 = EXCLUDED.sha256, pages = EXCLUDED.pages,
                 chars = EXCLUDED.chars, truncated = EXCLUDED.truncated, text = EXCLUDED.text,
                 fetched_at = now()""",
            (url, digest, pages, len(body), truncated, body))
        conn.commit()
    answer, usage = llm.complete_json(
        conn, task=TASK, system=SYSTEM, user=f"{USER_HEADERS[scope]}{body}", schema=schema(),
        schema_name="eligibility", max_output_tokens=7000, client=llm_client)
    fields = annotate_scope(check_quotes(answer, body), scope)
    from psycopg.types.json import Jsonb

    conn.execute(
        """INSERT INTO call_eligibility (url, fields, model, prompt_version, input_tokens, output_tokens, cost_usd, scope)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (url) DO UPDATE SET fields = EXCLUDED.fields, model = EXCLUDED.model,
             prompt_version = EXCLUDED.prompt_version, input_tokens = EXCLUDED.input_tokens,
             output_tokens = EXCLUDED.output_tokens, cost_usd = EXCLUDED.cost_usd, scope = EXCLUDED.scope,
             extracted_at = now()""",
        (url, Jsonb(fields), settings().openai_model, PROMPT_VERSION,
         usage["input_tokens"], usage["output_tokens"], usage["cost_usd"], scope))
    conn.commit()
    stated = sum(1 for f in fields.values() if f["value"] is not None)
    verified = sum(1 for f in fields.values() if f["verified"])
    return {"url": url, "status": "done", "scope": scope, "stated": stated, "verified": verified, **usage}


# ----------------------------------------------------------------- what the site serves

def _served_fact(fact: dict[str, Any], scope: str) -> dict[str, Any] | None:
    from .normalise import redact_emails

    if not (fact.get("verified") and fact.get("value") is not None and fact.get("quote")):
        return None
    return {"value": fact["value"], "note": redact_emails(fact["note"]) if fact.get("note") else None,
            "quote": redact_emails(fact["quote"]), "confidence": fact["confidence"], "scope": scope}


def read_many(conn, calls: list[tuple[Any, dict[str, Any] | None, str | None]]) -> dict[Any, dict[str, Any]]:
    """What is known of the eligibility of each call, for (id, conditions_raw, eligibility_text)
    triples, in one query. Per call: `state` is `read` (verified facts), `not_read` (its sources are
    known and none has been read) or `no_source` (the portal lists nothing we can read); `sources`
    are the places the rules are written, `facts` the verified ones. A call-document fact stands
    alone; otherwise a topic's own fact wins over the general annexes' one, and each fact says
    which it is (`scope`)."""
    mapped = {cid: sources_of(cond, text) for cid, cond, text in calls}
    keys = sorted({s.key for srcs in mapped.values() for s in srcs})
    held = {r["url"]: r for r in conn.execute(
        "SELECT url, fields, extracted_at FROM call_eligibility WHERE url = ANY(%s)", (keys,)).fetchall()} if keys else {}
    out: dict[Any, dict[str, Any]] = {}
    for cid, srcs in mapped.items():
        if not srcs:
            out[cid] = {"state": "no_source", "basis": None, "sources": [], "facts": {}}
            continue
        read = [(s, held[s.key]) for s in srcs if s.key in held]
        if srcs[0].scope == "call_document":
            read = sorted(read, key=lambda p: p[1]["extracted_at"], reverse=True)[:1]   # the latest document read
        facts: dict[str, Any] = {}
        for s, row in sorted(read, key=lambda p: SCOPES.index(p[0].scope)):   # general first, so that the topic's own wins
            for name, fact in row["fields"].items():
                served = _served_fact(fact, s.scope)
                if served:
                    facts[name] = served
        sources = [{"scope": s.scope, "label": s.label,
                    "url": s.key if s.key.startswith("https://") else None,
                    "extractedAt": held[s.key]["extracted_at"] if s.key in held else None} for s in srcs]
        out[cid] = {"state": "read" if facts else "not_read",
                    "basis": "call_document" if srcs[0].scope == "call_document" else "work_programme",
                    "sources": sources, "facts": facts}
    return out


def summary_line(facts: dict[str, Any]) -> str | None:
    """One line for a list or a digest, only from verified facts. Never a verdict."""
    parts = []
    n, k = facts.get("min_entities"), facts.get("min_countries")
    if n and isinstance(n["value"], int):
        parts.append(f"consortium of at least {n['value']} entities" +
                     (f" from {k['value']} countries" if k and isinstance(k["value"], int) else ""))
    elif facts.get("single_applicant_allowed", {}).get("value") is True:
        parts.append("a single applicant may apply")
    if facts.get("sme_only", {}).get("value") is True:
        parts.append("SMEs only")
    if facts.get("ownership_control_restriction", {}).get("value") is True:
        parts.append("ownership control restriction")
    if facts.get("cascade_funding", {}).get("value") is True:
        parts.append("financial support to third parties")
    if not parts:
        return None
    text = "; ".join(parts)
    text = text[0].upper() + text[1:] + "."
    general = any(f["scope"] != "call_document" for f in facts.values())
    return text + " Read from the work programme text; the topic may add conditions." if general else text
