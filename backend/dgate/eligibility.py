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
"""

from __future__ import annotations

import hashlib
import io
import re
from typing import Any

import httpx
from pydantic import BaseModel

from . import llm
from .config import settings
from .enrichment.base import strict_schema

TASK = "call_eligibility"
PROMPT_VERSION = 1
MAX_PDF_BYTES = 40 * 1024 * 1024
MAX_CHARS = 350_000          # about 90,000 tokens: the longest call documents are cut here
UNVERIFIED_CAP = 0.3


class FactStr(BaseModel):
    value: str | None
    confidence: float
    quote: str | None


class FactBool(BaseModel):
    value: bool | None
    confidence: float
    quote: str | None


class FactInt(BaseModel):
    value: int | None
    confidence: float
    quote: str | None


class FactNum(BaseModel):
    value: float | None
    confidence: float
    quote: str | None


class FactList(BaseModel):
    value: list[str] | None
    confidence: float
    quote: str | None


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
    funding_rate_percent: FactNum       # the main reimbursement or funding rate, in percent
    cascade_funding: FactBool           # financial support to third parties (FSTP / cascade) is part of the action


FIELDS = list(Eligibility.model_fields)

SYSTEM = (
    "You read one EU call document and report who may apply, as a fixed set of facts. "
    "Use only the text you are given. If the document does not state a fact, return value null "
    "and confidence 0: never fill a gap from general knowledge of EU programmes. "
    "For every fact you do state, copy the sentence that states it verbatim into `quote` "
    "(at most 300 characters, no paraphrase, no ellipsis). Confidence is between 0 and 1: "
    "1 means the sentence says it plainly, 0.5 means you combined several sentences, below 0.5 "
    "means you are unsure. If a rule differs by topic or by type of action, report the general "
    "rule and say so in the value. Eligibility and funding conditions only; do not describe the "
    "technical content of the work."
)


def schema() -> dict[str, Any]:
    return strict_schema(Eligibility)


# ----------------------------------------------------------------- the document

def fetch_text(url: str, client: httpx.Client | None = None) -> tuple[str, int, str]:
    """(sha256 of the file, number of pages, text) of a PDF."""
    from pypdf import PdfReader

    http = client or httpx.Client(timeout=120, follow_redirects=True,
                                  headers={"User-Agent": settings().user_agent})
    try:
        r = http.get(url)
    finally:
        if client is None:
            http.close()
    if r.status_code != 200:
        raise ValueError(f"HTTP {r.status_code}")
    if len(r.content) > MAX_PDF_BYTES:
        raise ValueError("file too large")
    if not r.content.startswith(b"%PDF"):
        raise ValueError("not a PDF")
    reader = PdfReader(io.BytesIO(r.content))
    pages = [(p.extract_text() or "") for p in reader.pages]
    text = re.sub(r"[ \t]+", " ", "\n".join(pages))
    return hashlib.sha256(r.content).hexdigest(), len(pages), text


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.casefold()).strip()


def check_quotes(answer: dict[str, Any], text: str) -> dict[str, Any]:
    """Add `verified` to every fact: whether its quote is in the document text. A stated fact
    without a found quote keeps its value but its confidence is capped."""
    haystack = _norm(text)
    out: dict[str, Any] = {}
    for name in FIELDS:
        fact = dict(answer[name])
        stated = fact["value"] is not None
        quote = (fact.get("quote") or "").strip()
        fact["verified"] = bool(stated and quote and _norm(quote) in haystack)
        if stated and not fact["verified"]:
            fact["confidence"] = min(float(fact["confidence"]), UNVERIFIED_CAP)
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


def extract_one(conn, url: str, *, force: bool = False, client: httpx.Client | None = None,
                llm_client: httpx.Client | None = None) -> dict[str, Any]:
    """Fetch (if not held), ask, check the quotes, store. Returns a short report."""
    held = conn.execute("SELECT 1 FROM call_eligibility WHERE url = %s AND prompt_version = %s",
                        (url, PROMPT_VERSION)).fetchone()
    if held and not force:
        return {"url": url, "status": "held"}
    doc = conn.execute("SELECT text FROM call_document_text WHERE url = %s", (url,)).fetchone()
    if doc is None:
        digest, pages, text = fetch_text(url, client)
        truncated = len(text) > MAX_CHARS
        text = text[:MAX_CHARS]
        conn.execute(
            """INSERT INTO call_document_text (url, sha256, pages, chars, truncated, text)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (url) DO UPDATE SET sha256 = EXCLUDED.sha256, pages = EXCLUDED.pages,
                 chars = EXCLUDED.chars, truncated = EXCLUDED.truncated, text = EXCLUDED.text,
                 fetched_at = now()""",
            (url, digest, pages, len(text), truncated, text))
        conn.commit()
    else:
        text = doc["text"]
    answer, usage = llm.complete_json(
        conn, task=TASK, system=SYSTEM, user=f"Call document:\n\n{text}", schema=schema(),
        schema_name="eligibility", max_output_tokens=4000, client=llm_client)
    fields = check_quotes(answer, text)
    from psycopg.types.json import Jsonb

    conn.execute(
        """INSERT INTO call_eligibility (url, fields, model, prompt_version, input_tokens, output_tokens, cost_usd)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (url) DO UPDATE SET fields = EXCLUDED.fields, model = EXCLUDED.model,
             prompt_version = EXCLUDED.prompt_version, input_tokens = EXCLUDED.input_tokens,
             output_tokens = EXCLUDED.output_tokens, cost_usd = EXCLUDED.cost_usd, extracted_at = now()""",
        (url, Jsonb(fields), settings().openai_model, PROMPT_VERSION,
         usage["input_tokens"], usage["output_tokens"], usage["cost_usd"]))
    conn.commit()
    stated = sum(1 for f in fields.values() if f["value"] is not None)
    verified = sum(1 for f in fields.values() if f["verified"])
    return {"url": url, "status": "done", "stated": stated, "verified": verified, **usage}
