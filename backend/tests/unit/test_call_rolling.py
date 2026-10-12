"""A call that takes submissions continuously or in several cut-offs is `rolling`.

The SQL keeps such a call open past its stored deadline (funding.ROLLING_MODELS); the
site needs to say why ("Open: rolling submission, last cut-off 13 Oct 2026") instead of
reading a passed date as closed. `is_rolling` is the same rule on the served row.
"""

from __future__ import annotations

import pytest

from dgate.funding import ROLLING_MODELS, is_rolling


@pytest.mark.parametrize("model,expected", [
    ("continuous", True), ("Continuous", True), ("rolling", True), ("multiple cut-off", True),
    (" Multiple cut-off ", True), ("single-stage", False), ("two-stage", False), ("", False),
    (None, False),
])
def test_the_deadline_model_decides(model, expected):
    assert is_rolling({"deadline_model": model}) is expected


def test_a_call_with_no_conditions_is_not_rolling():
    assert is_rolling(None) is False
    assert is_rolling({}) is False


def test_the_python_rule_names_the_same_models_as_the_sql():
    for name in ("continuous", "rolling", "multiple cut-off"):
        assert f"'{name}'" in ROLLING_MODELS
