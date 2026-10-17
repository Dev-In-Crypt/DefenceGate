"""The one place that talks to the language model (OpenAI Responses API, structured output).

Three rules, in this order, on every call:
  1. no key, no call;
  2. the month's spend plus the worst case of this call must stay within
     `DGATE_LLM_MONTHLY_CAP_USD`, or `CapReached` is raised before anything is sent;
  3. what the call cost is written to `llm_usage` before the answer is used.
The prices are configured, not looked up, and sit on the high side (`config.py`).
Nothing here logs the key or the prompt.
"""

from __future__ import annotations

import json
import time
from datetime import date
from typing import Any

import httpx

from .config import settings

URL = "https://api.openai.com/v1/responses"
CHARS_PER_TOKEN = 3          # a pessimistic estimate for the input, for the cap only


class LLMError(RuntimeError):
    pass


class CapReached(LLMError):
    pass


def month_spent(conn) -> float:
    row = conn.execute(
        "SELECT COALESCE(sum(cost_usd), 0) AS s FROM llm_usage WHERE day >= date_trunc('month', now())::date"
    ).fetchone()
    return float(row["s"])


def cost_of(input_tokens: int, output_tokens: int) -> float:
    cfg = settings()
    return input_tokens / 1e6 * cfg.llm_price_in_per_m + output_tokens / 1e6 * cfg.llm_price_out_per_m


def _text_of(body: dict[str, Any]) -> str:
    if body.get("status") not in (None, "completed"):
        raise LLMError(f"the model did not finish: {body.get('status')} {body.get('incomplete_details')}")
    parts = []
    for item in body.get("output") or []:
        for c in item.get("content") or []:
            if c.get("type") == "output_text":
                parts.append(c.get("text") or "")
            elif c.get("type") == "refusal":
                raise LLMError("the model refused")
    if not parts:
        raise LLMError("no text in the answer")
    return "".join(parts)


def complete_json(conn, *, task: str, system: str, user: str, schema: dict[str, Any],
                  schema_name: str, max_output_tokens: int = 4000,
                  client: httpx.Client | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """One structured answer. Returns (the parsed JSON, {input_tokens, output_tokens, cost_usd})."""
    cfg = settings()
    if not cfg.openai_api_key or not cfg.openai_model:
        raise LLMError("no key or model configured")
    worst = cost_of((len(system) + len(user)) // CHARS_PER_TOKEN + 1, max_output_tokens)
    spent = month_spent(conn)
    if spent + worst > cfg.llm_monthly_cap_usd:
        raise CapReached(f"month spend {spent:.3f} + this call at most {worst:.3f} "
                         f"is over the cap {cfg.llm_monthly_cap_usd:.2f} USD")
    payload = {
        "model": cfg.openai_model,
        "instructions": system,
        "input": user,
        "max_output_tokens": max_output_tokens,
        "store": False,
        "text": {"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}},
    }
    own = client is None
    http = client or httpx.Client(timeout=180)
    try:
        for attempt in range(3):
            r = http.post(URL, json=payload, headers={"Authorization": f"Bearer {cfg.openai_api_key}"})
            if r.status_code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            break
    finally:
        if own:
            http.close()
    if r.status_code != 200:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
    body = r.json()
    usage = body.get("usage") or {}
    tin, tout = int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
    cost = cost_of(tin, tout)
    conn.execute(
        """INSERT INTO llm_usage (day, task, model, requests, input_tokens, output_tokens, cost_usd)
           VALUES (%s, %s, %s, 1, %s, %s, %s)
           ON CONFLICT (day, task, model) DO UPDATE SET
             requests = llm_usage.requests + 1,
             input_tokens = llm_usage.input_tokens + EXCLUDED.input_tokens,
             output_tokens = llm_usage.output_tokens + EXCLUDED.output_tokens,
             cost_usd = llm_usage.cost_usd + EXCLUDED.cost_usd""",
        (date.today(), task, cfg.openai_model, tin, tout, round(cost, 5)))
    conn.commit()
    try:
        data = json.loads(_text_of(body))
    except json.JSONDecodeError as exc:
        raise LLMError(f"the answer is not JSON: {exc}") from exc
    return data, {"input_tokens": tin, "output_tokens": tout, "cost_usd": round(cost, 5)}
