"""WP-158 without a database: the plan an association gives (through billing.plan_in_force) in both states of the plans,
the digest mail's text, and the per-mail sender name of the mailer."""

from __future__ import annotations

import pytest

from dgate import associations, billing, config
from dgate.ops import mailer


def user(plan: str | None = None, assoc: str | None = None) -> dict:
    return {"sub_plan": plan, "sub_status": "active" if plan else None, "sub_period_end": None, "assoc_plan": assoc}


@pytest.fixture()
def on_sale(monkeypatch):
    monkeypatch.setattr(billing, "plans_on_sale", lambda: True)


def test_the_larger_of_the_subscription_and_the_association_is_in_force():
    assert billing.plan_of(user(None, "pro")) == "pro"
    assert billing.plan_of(user(None, "team")) == "team"
    assert billing.plan_of(user("consultant", "pro")) == "consultant"
    assert billing.plan_of(user("founding", "pro")) == "founding"
    assert billing.plan_of(user("pro", "team")) == "team"
    assert billing.plan_of(user(None, "anything else")) == "free"
    assert billing.plan_in_force("team", "expired", None, association="pro") == "pro"
    assert billing.plan_in_force(None, None, None) == "free"


def test_on_sale_a_member_has_the_pro_set_and_the_admin_the_team_set(on_sale):
    member, admin, nobody = user(None, "pro"), user(None, "team"), user()
    for f in billing.FEATURES:
        if f in ("company_report", "branded_reports"):
            continue                                     # behind their own switch (WP-152)
        assert billing.may(member, f) is billing.allows("pro", f), f
        assert billing.may(admin, f) is billing.allows("team", f), f
    assert billing.may(member, "saved_searches") and not billing.may(member, "signals_csv")
    assert billing.may(admin, "signals_csv") and billing.may(admin, "consortium_gaps")
    assert not billing.may(nobody, "saved_searches")
    with pytest.raises(billing.AccountError):
        billing.require(member, "consortium_gaps")
    assert "association" in billing.features(member) and "association" not in billing.features(nobody)


def test_while_no_plan_is_on_sale_nobody_is_refused(monkeypatch):
    monkeypatch.setattr(billing, "plans_on_sale", lambda: False)
    for u in (user(), user(None, "pro"), user(None, "team")):
        assert all(billing.may(u, f) for f in billing.FEATURES if f not in ("company_report", "branded_reports"))
    assert "association" in billing.features(user(None, "pro"))


ISSUE = {
    "week": "2026-W43", "country": "ES", "cpv": ["3541"],
    "counts": {"tendersNew": 12, "tendersAmended": 0, "callsNew": 1, "callsAmended": 0, "callsOpened": 0,
               "callsClosing": 0, "cascade": 0},
    "tendersNew": [{"title": f"Tender {i}", "slug": f"t-{i}", "buyerName": "Ministerio de Defensa", "country": "ES",
                    "deadline": "2026-11-20T00:00:00Z"} for i in range(12)],
    "tendersAmended": [], "callsOpened": [], "callsClosing": [],
    "callsNew": [{"title": "A call", "slug": "c-1", "funder": "EDF", "funderCountry": "EU", "deadline": None}],
}


def test_the_mail_carries_the_association_s_name_the_issue_and_the_stop_link():
    subject, body = associations.render(ISSUE, "Cluster Example", "https://site.test", "https://site.test/unsubscribe?token=x")
    assert subject == "Cluster Example: weekly defence digest, 2026-W43"
    assert body.startswith("Cluster Example: the weekly digest")
    assert "New defence tenders: 12" in body and "... and 2 more" in body
    assert body.count("https://site.test/tenders/") == associations.SECTION_MAX
    assert "deadline 2026-11-20" in body and "deadline no deadline stated" in body
    assert "https://site.test/digest/2026-W43?country=ES&cpv=3541" in body
    assert "Amended tenders" not in body                                    # an empty section is left out
    assert body.rstrip().endswith("Stop it: https://site.test/unsubscribe?token=x")
    html = mailer.to_html(body)
    assert '<a href="https://site.test/unsubscribe?token=x">' in html


def test_a_mail_goes_out_under_the_association_s_name_from_our_address(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_MAIL_CATCHER_DIR", str(tmp_path))
    monkeypatch.setenv("DGATE_SMTP_FROM", "digest@example.test")
    config.reset_cache()
    try:
        msg = mailer.build_message("a@example.test", "s", "b", sender_name="Cluster Ñ via DefenceGate",
                                   headers={"List-Unsubscribe": "<https://site.test/unsubscribe?token=x>"})
        assert "digest@example.test" in msg["From"] and "via DefenceGate" in str(msg["From"])
        assert msg["List-Unsubscribe"] == "<https://site.test/unsubscribe?token=x>"
        assert mailer.build_message("a@example.test", "s", "b")["From"] == "DefenceGate <digest@example.test>"
        assert mailer.send_mail("a@example.test", "s", "b", sender_name="X\r\nBcc: b@example.test") is False
        assert mailer.send_mail("a@example.test", "s", "b", sender_name="Cluster via DefenceGate") is True
        assert len(list(tmp_path.glob("*.eml"))) == 1
    finally:
        config.reset_cache()
