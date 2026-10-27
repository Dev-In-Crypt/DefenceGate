"""WP-154: the paid part's gate and the funding signal's programme filter, without a database."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from dgate import billing, config, signals


@pytest.fixture()
def cfg(monkeypatch):
    def set_(**env):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        config.reset_cache()
    yield set_
    config.reset_cache()


def test_the_full_list_is_closed_by_default_and_then_follows_the_plan(cfg, monkeypatch):
    free = {"sub_plan": None, "sub_status": None, "sub_period_end": None}
    team = {"sub_plan": "team", "sub_status": "active", "sub_period_end": None}
    cfg()
    assert not signals.full_open() and not signals.may_see_full(team)
    cfg(DGATE_SIGNALS_FULL_OPEN="true")
    monkeypatch.setattr(billing, "plans_on_sale", lambda: False)
    assert signals.may_see_full(free)                       # nothing on sale: nothing withheld, as billing.may
    monkeypatch.setattr(billing, "plans_on_sale", lambda: True)
    assert not signals.may_see_full(free) and signals.may_see_full(team)
    assert signals.PLANS == frozenset(billing.PAID)


def test_programmes_are_the_defence_ones_only():
    assert signals._programmes("edf, EDIP,EDF") == ["EDF", "EDIP"]
    assert signals._programmes(None) == []
    with pytest.raises(HTTPException):
        signals._programmes("HORIZON")
