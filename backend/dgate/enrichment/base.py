"""What an enrichment task is.

A task turns one archived notice into one validated, structured result. It
declares the model, the output schema, how to build the prompt, and -- the part
that decides what gets paid for -- exactly which input the result depends on.

The input hash covers the task's name, its prompt version, the model, and the
input fields. Change any of them and every notice is due again; change none and
nothing is. Bump `prompt_version` whenever the prompt's wording changes in a way
that should invalidate old results.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel


def canonical_json(value: Any) -> str:
    """Stable serialisation: sorted keys, no whitespace variation."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      default=str)


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The Pydantic model's JSON schema, closed to extra properties.

    Structured outputs need `additionalProperties: false` on every object and
    every property listed as required; Pydantic emits neither by default.
    """
    schema = model.model_json_schema()

    def close(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                node["additionalProperties"] = False
                if "properties" in node:
                    node["required"] = list(node["properties"])
            for value in node.values():
                close(value)
        elif isinstance(node, list):
            for item in node:
                close(item)

    close(schema)
    return schema


@dataclass(frozen=True)
class Task:
    """One enrichment task.

    `build_input` reads what the task needs from an archived version payload and
    returns a plain dict; it is the only thing hashed besides the task's own
    identity, so it must contain everything the output depends on and nothing
    that varies without changing the meaning (timestamps, database ids).
    """

    name: str
    model: str
    output: type[BaseModel]
    system_prompt: str
    build_input: Callable[[dict[str, Any]], dict[str, Any] | None]
    build_user_message: Callable[[dict[str, Any]], str]
    prompt_version: int = 1
    max_tokens: int = 16000
    # Applies a validated result to the serving layer. Default: store only.
    apply: Callable[[Any, int, BaseModel], None] | None = field(default=None)

    def input_hash(self, task_input: dict[str, Any]) -> str:
        identity = {
            "task": self.name,
            "prompt_version": self.prompt_version,
            "model": self.model,
            "system": hashlib.sha256(self.system_prompt.encode("utf-8")).hexdigest(),
            "input": task_input,
        }
        return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()

    def request_params(self, task_input: dict[str, Any]) -> dict[str, Any]:
        """Messages API parameters, identical for synchronous and batch calls.

        The system prompt carries `cache_control`: it is the stable prefix every
        request for this task shares, so repeated calls read it from cache.
        """
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": [{"type": "text", "text": self.system_prompt,
                        "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": self.build_user_message(task_input)}],
            "output_config": {"format": {"type": "json_schema",
                                         "schema": strict_schema(self.output)}},
        }

    def parse(self, message: Any) -> BaseModel:
        """Validate a finished message against the task's schema.

        Raises ValueError for anything other than a complete answer: a refusal,
        a truncated response, or JSON that does not match the schema. The runner
        records that as the job's error rather than storing a half result.
        """
        stop = getattr(message, "stop_reason", None)
        if stop == "refusal":
            raise ValueError("model declined the request (stop_reason=refusal)")
        if stop == "max_tokens":
            raise ValueError(f"response truncated at max_tokens={self.max_tokens}")
        text = next((b.text for b in getattr(message, "content", [])
                     if getattr(b, "type", None) == "text"), None)
        if text is None:
            raise ValueError("response has no text block")
        return self.output.model_validate_json(text)


_REGISTRY: dict[str, Task] = {}


def register(task: Task) -> Task:
    if task.name in _REGISTRY and _REGISTRY[task.name] is not task:
        raise ValueError(f"enrichment task {task.name!r} is already registered")
    _REGISTRY[task.name] = task
    return task


def get_task(name: str) -> Task:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown enrichment task {name!r}; registered: "
                       f"{sorted(_REGISTRY)}") from None
