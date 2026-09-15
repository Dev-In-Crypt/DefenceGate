"""The enrichment task definition: what is hashed, what is sent, what is accepted."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from dgate.enrichment.base import Task, strict_schema


class Out(BaseModel):
    title_en: str
    tags: list[str]


def make_task(**over) -> Task:
    fields = dict(
        name="unit_task", model="claude-sonnet-5", output=Out,
        system_prompt="Translate the title.",
        build_input=lambda payload: {"title": payload["title_original"]},
        build_user_message=lambda task_input: task_input["title"],
    )
    fields.update(over)
    return Task(**fields)


def message(text: str, stop: str = "end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])


def test_the_same_input_always_hashes_the_same():
    task = make_task()
    assert task.input_hash({"title": "a", "n": 1}) == task.input_hash({"n": 1, "title": "a"})


@pytest.mark.parametrize("change", [
    {"model": "claude-opus-5"},
    {"prompt_version": 2},
    {"system_prompt": "Translate the title into English."},
    {"name": "other_task"},
])
def test_anything_the_result_depends_on_changes_the_hash(change):
    """A new prompt or model must invalidate old results; they were paid for
    under different terms and would otherwise be served as current."""
    assert make_task().input_hash({"title": "a"}) != make_task(**change).input_hash({"title": "a"})


def test_a_different_input_changes_the_hash():
    task = make_task()
    assert task.input_hash({"title": "a"}) != task.input_hash({"title": "b"})


def test_the_output_schema_is_closed():
    """Structured outputs reject a schema that allows extra properties."""
    schema = strict_schema(Out)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"title_en", "tags"}


def test_the_system_prompt_is_marked_for_caching():
    params = make_task().request_params({"title": "a"})
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert params["output_config"]["format"]["type"] == "json_schema"


def test_a_valid_answer_parses():
    assert make_task().parse(message('{"title_en": "Rations", "tags": []}')).title_en == "Rations"


@pytest.mark.parametrize("bad, reason", [
    (message("", stop="refusal"), "refusal"),
    (message('{"title_en": "Ra', stop="max_tokens"), "truncated"),
    (message('{"title_en": 3}'), "validation"),
])
def test_an_incomplete_answer_is_refused_not_stored(bad, reason):
    with pytest.raises(ValueError):
        make_task().parse(bad)
