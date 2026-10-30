"""WP-156: the two export features as billing holds them, without a database: the eligibility pack is Pro and up, the supplier
map's CSV Team and Consultant, nobody is refused either while no plan is on sale, and both routes ask billing."""

from __future__ import annotations

import inspect

import pytest

from dgate import api, billing, exports
from dgate.accounts import AccountError

PLANS = ("free", "pro", "team", "consultant", "founding")


def user(plan: str | None) -> dict:
    return {"sub_plan": plan, "sub_status": "active" if plan else None, "sub_period_end": None}


@pytest.mark.parametrize(("feature", "plans"), [("eligibility_export", {"pro", "team", "consultant", "founding"}),
                                                ("supplier_map_csv", {"team", "consultant"})])
def test_each_export_follows_the_plan_once_plans_are_on_sale(monkeypatch, feature, plans):
    monkeypatch.setattr(billing, "plans_on_sale", lambda: True)
    for plan in PLANS:
        if plan in plans:
            billing.require(user(plan), feature)
        else:
            with pytest.raises(AccountError) as e:
                billing.require(user(plan), feature)
            assert (e.value.status, e.value.code) == (402, "plan_required")
    assert billing.MESSAGES[feature].endswith("choose a plan under Billing")


def test_while_no_plan_is_on_sale_nobody_is_refused_an_export(monkeypatch):
    monkeypatch.setattr(billing, "plans_on_sale", lambda: False)
    for feature in ("eligibility_export", "supplier_map_csv"):
        billing.require(user(None), feature)
        assert feature in billing.features(user(None))


def test_both_routes_ask_billing_and_need_a_session():
    for fn, feature in ((exports.supplier_export, "supplier_map_csv"), (exports.eligibility_calls, "eligibility_export")):
        assert f'billing.require(user, "{feature}")' in inspect.getsource(fn)
    assert {r.path for r in exports.account_router.routes} == {"/v1/account/suppliers/export", "/v1/account/eligibility/calls"}
    assert "exports import account_router" in inspect.getsource(api)
    assert exports.EXPORT_MAX == 5000
