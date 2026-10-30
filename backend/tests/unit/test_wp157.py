"""WP-157 without a database: a workspace member's plan, the seat and client numbers in both states, the sharing scope."""

from __future__ import annotations

import pytest

from dgate import accounts, billing


def user(plan: str | None, owner_plan: str | None = None, ws: str | None = None) -> dict:
    return {"id": "u", "sub_plan": plan, "sub_status": "active" if plan else None, "sub_period_end": None,
            "ws_id": ws, "ws_plan": owner_plan, "ws_status": "active" if owner_plan else None, "ws_period_end": None}


@pytest.fixture()
def on_sale(monkeypatch):
    monkeypatch.setattr(billing, "plans_on_sale", lambda: True)


def test_a_member_has_the_owner_s_plan_when_it_has_the_workspace_and_is_higher():
    assert billing.plan_of(user(None, "team")) == "team"
    assert billing.plan_of(user(None, "consultant")) == "consultant"
    assert billing.plan_of(user("pro", "team")) == "team"
    assert billing.plan_of(user("consultant", "team")) == "consultant"       # its own is higher
    assert billing.plan_of(user(None, "pro")) == "free"                       # Pro has no workspace: nothing shared
    assert billing.plan_of(user("founding", "pro")) == "founding"
    ended = {**user(None, "team"), "ws_status": "canceled"}
    assert billing.plan_of(ended) == "free"


def test_seats_and_clients_per_plan(on_sale):
    assert [billing.seat_limit(user(p)) for p in ("free", "pro", "team", "consultant", "founding")] == [0, 0, 5, 5, 0]
    assert [billing.client_limit(user(p)) for p in ("free", "pro", "team", "consultant", "founding")] == [0, 0, 0, 15, 0]


def test_while_no_plan_is_on_sale_every_account_has_the_team_and_consultant_numbers(monkeypatch):
    monkeypatch.setattr(billing, "plans_on_sale", lambda: False)
    assert billing.seat_limit(user(None)) == 5 and billing.client_limit(user(None)) == 15
    assert billing.may(user(None), "team_workspace") and billing.may(user(None), "client_profiles")


def test_the_sharing_scope_is_the_workspace_only_while_the_plan_has_it(on_sale):
    assert accounts.shared_scope(user(None, "team", ws="w"))[1] == ("u", "w")
    assert accounts.shared_scope(user(None, "pro", ws="w"))[1] == ("u", None)
    assert accounts.shared_scope(user("team"))[1] == ("u", None)
