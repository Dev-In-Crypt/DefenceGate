"""Payments through Creem (creem.io), the merchant of record (WP-124).

Creem sells the plan to the customer: its hosted checkout takes the card, it charges the VAT, issues
the invoices and runs the customer portal (cancel, invoices, payment method). We never see a card or
an invoice. What we hold (migration 0133, docs/DATA_PROTECTION.md): the checkouts we opened, one
subscription row per account (plan, period, state, Creem's customer and subscription ids, the end of
the paid period), and the ids of the webhook events we processed.

Closed by default: billing opens only when the API key, the webhook secret and every product id are
set (`billing_problem`), and the site shows it only when NEXT_PUBLIC_BILLING_OPEN is on as well.
Test mode (Creem's test-api host) unless DGATE_CREEM_TEST_MODE=0.

Requirements (docs/SECURITY_REQUIREMENTS.md, billing):
  B1  every event id is stored; a second delivery is acknowledged and changes nothing;
  B2  HMAC-SHA256 over the raw body, compared in constant time; Creem signs no timestamp header, so the
      event's own `created_at` (inside the signed body) is the clock: older than EVENT_MAX_AGE or in the
      future is refused, and an event older than the last one applied to a subscription changes nothing;
  B3  an event is applied only to the checkout we created (our reference in request_id and metadata, the
      account and product of that checkout) and then to the subscription and customer ids it named:
      never by an e-mail address;
  B4  nothing is granted before a verified event: a checkout grants nothing, the return from the checkout
      page grants nothing;
  B5  two webhook secrets are accepted while one replaces the other.
The plan in force is changed only here (D3).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, Response

from . import accounts
from .accounts import AccountError, current, get_conn, no_store, throttled
from .config import settings
from .ops.notify import notify

log = logging.getLogger("accounts")          # the security log of the accounts (WP-126): one file

PAID = ("pro", "team", "consultant", "founding")
PERIODS = ("monthly", "yearly")
# What each plan allows, of the features that exist: the owner's split of 28 October 2026 (WP-155,
# docs/verification/features/wp155-selfcheck.md). Founding customer is Pro (/pricing: "Everything in Pro"). WP-156 built the
# split's two exports (exports.py). The data API is a licence
# outside the plans (`app_user.api_licensed_at`, dgate/ops/api_licence.py): no plan grants it.
PRO = frozenset(PAID)                                   # Pro and every plan that includes it
TEAM = frozenset({"team", "consultant"})
FEATURES: dict[str, frozenset[str]] = {
    "saved_searches": PRO,
    "email_alerts": PRO,
    # WP-152: a supplier's company report (/suppliers/{slug}/report), so many a month (REPORTS_PER_MONTH). Exists only
    # with DGATE_COMPANY_REPORT_OPEN=1 (`may`).
    "company_report": PRO,
    "competitors_full": PRO,            # a company's whole competitor list (the public answer has FREE_COMPETITORS)
    "signals_full": PRO,                # every row of a company signal, on the page
    "signals_csv": TEAM,                # ... and its CSV
    "consortium_gaps": TEAM,            # /networks/consortium-gaps
    "branded_reports": frozenset({"consultant"}),   # the account's own name on its company reports
    "eligibility_export": PRO,          # WP-156: the eligibility check's results pack (print/PDF and CSV), built in the browser
    "supplier_map_csv": TEAM,           # WP-156: the supplier map's list as CSV (/v1/account/suppliers/export)
    # WP-157: a workspace of up to SEATS users sharing the owner's plan, searches, shortlist and follows (workspace.py)
    "team_workspace": TEAM,
    "client_profiles": frozenset({"consultant"}),   # up to CLIENTS client profiles in the workspace
    # WP-160 (owner, 31 October 2026): contracts ending soon beyond the first rows, and saved searches of that kind with their
    # alerts (expiring.py); the list's CSV is Team. The buyer page's block is free.
    "expiring_contracts": PRO,
    "expiring_contracts_csv": TEAM,
    # WP-162: the "Who to sell to" supplier report (sell_report.py), REPORTS_PER_MONTH as the company report; exists only
    # with DGATE_COMPANY_REPORT_OPEN=1 (`may`)
    "sell_report": PRO,
}
# How many: None is no plan limit.
REPORTS_PER_MONTH: dict[str, int | None] = {"pro": 3, "founding": 3, "team": 15, "consultant": None}
SAVED_SEARCHES: dict[str, int | None] = {"pro": 10, "founding": 10, "team": 50, "consultant": None}
# ponytail: "unlimited" saved searches stop at a ceiling, since each one is run when the list is shown (1000 rows of
# `_search_out` on one page view); page the list or raise it when
# an account reaches it.
SEARCH_CEILING = 1000   # owner, 31 Oct 2026: in practice "unlimited" (was 200)
# WP-157: users of a workspace (the owner included) and client profiles; while no plan is on sale, the Team and Consultant
# numbers (nobody is refused the feature then, WP-124).
SEATS: dict[str, int] = {"team": 5, "consultant": 5}
CLIENTS: dict[str, int] = {"consultant": 15}
SEARCHES_UNSOLD = 10                   # while no plan is on sale: what every account had before the plans (WP-123)
FOUNDING_CAP = 20
FOUNDING_HOLD = timedelta(hours=1)        # an open founding checkout holds a place this long
CHECKOUTS_PER_HOUR = 5                    # per account: nobody fills Creem's dashboard with checkouts
EVENT_MAX_AGE = timedelta(hours=25)       # Creem retries for up to 24 hours after the event
EVENT_MAX_SKEW = timedelta(minutes=5)     # an event "from the future": a clock problem or a forgery
WEBHOOK_MAX = 64 * 1024                   # hardening.BodyLimit holds the route to this
PROVIDER_ANSWER_MAX = 256 * 1024

# Creem's subscription states (docs.creem.io, webhooks) and what each allows:
#   active, trialing                       the plan;
#   past_due                               the plan: a payment failed and Creem retries (its grace period);
#   scheduled_cancel                       the plan until the end of the paid period;
#   unpaid, paused, expired, canceled      Free (expired: the period ended unpaid; canceled: Creem's
#                                          portal cancels at once);
#   disputed (ours, dispute.created)       Free until Creem settles it.
ENTITLING = frozenset({"active", "trialing", "past_due"})
STATUSES = frozenset({"active", "trialing", "past_due", "unpaid", "paused", "scheduled_cancel",
                      "canceled", "expired", "disputed"})
EVENT_STATUS = {
    "subscription.active": "active", "subscription.paid": "active", "subscription.trialing": "trialing",
    "subscription.scheduled_cancel": "scheduled_cancel", "subscription.canceled": "canceled",
    "subscription.expired": "expired", "subscription.past_due": "past_due",
    "subscription.unpaid": "unpaid", "subscription.paused": "paused", "subscription.update": None,
}
# Deleting the account while Creem may still charge it would leave a subscription nobody can manage here:
# deletion waits until the subscription is over (accounts.delete_me). WP-161: `expired` (the period ended unpaid) is over
# too, and so is a cancellation at the end of the period once that end has passed (`over`).
ENDED = frozenset({"canceled", "expired"})


def over(status: str | None, period_end: datetime | None, now: datetime | None = None) -> bool:
    """Creem can charge the subscription no more: none at all, cancelled or expired, or cancelled at the end of a paid
    period that has ended. The one rule of deleting an account and of buying a plan again (WP-161)."""
    if status is None or status in ENDED:
        return True
    return status == "scheduled_cancel" and period_end is not None and period_end <= (now or datetime.now(timezone.utc))

_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_SIG = re.compile(r"^[0-9a-f]{64}$")


# ------------------------------------------------------------------ settings
def products() -> dict[tuple[str, str], str]:
    """(plan, period) -> Creem product id, for the ones that are set."""
    out = {}
    for key, pid in settings().creem_products.items():
        plan, period = key.split("_")
        if pid:
            out[(plan, period)] = pid
    return out


def plan_for_product(product_id: str | None) -> tuple[str, str] | None:
    for key, pid in products().items():
        if product_id and pid == product_id:
            return key
    return None


def billing_problem() -> str | None:
    """Why billing is closed, or None. Every setting must be there: a half-configured billing would
    take a payment it cannot match."""
    cfg = settings()
    missing = [name for name, value in (("DGATE_CREEM_API_KEY", cfg.creem_api_key),
                                        ("DGATE_CREEM_WEBHOOK_SECRET", cfg.creem_webhook_secret)) if not value.strip()]
    missing += [f"DGATE_CREEM_PRODUCT_{k.upper()}" for k, v in cfg.creem_products.items() if not v]
    return ", ".join(missing) or None


def plans_on_sale() -> bool:
    """Every product id is set: the plans exist at Creem, so the paid features are the plans' (the gates
    below). Product ids are not secrets, so the worker (alert digests) holds them too and decides as the
    API does; it holds neither the key nor the webhook secret. Set the key, the secret and the product
    ids together (runbook in docs/verification/accounts/wp124-selfcheck.md)."""
    return all(settings().creem_products.values())


def api_base() -> str:
    cfg = settings()
    if cfg.creem_api_url and cfg.env != "production":
        return cfg.creem_api_url.rstrip("/")
    return "https://test-api.creem.io/v1" if cfg.creem_test_mode else "https://api.creem.io/v1"


# ------------------------------------------------------------------ entitlement
# WP-158: a plan's rank, to keep the larger of a subscription and an association's licence (Founding customer is Pro).
_RANK = {"free": 0, "pro": 1, "founding": 1, "team": 2, "consultant": 3}


def plan_in_force(plan: str | None, status: str | None, period_end: datetime | None,
                  now: datetime | None = None, association: str | None = None, workspace: str | None = None) -> str:
    """The plan a subscription row allows now: the one function every gate goes through. The largest of:
      - the subscription's plan (WP-124);
      - WP-158: `association`, the plan an association's licence gives the account (associations.PLAN_SQL: pro for a
        member, team for its admin);
      - WP-157: `workspace`, the plan in force of the owner of the account's workspace, when that plan has the workspace."""
    sub = "free"
    if plan and status in ENTITLING:
        sub = plan
    elif plan and status == "scheduled_cancel":
        now = now or datetime.now(timezone.utc)
        sub = plan if period_end is None or period_end > now else "free"
    best = sub
    for other in (association, workspace if workspace in FEATURES["team_workspace"] else None):
        if other in _RANK and _RANK[other] > _RANK.get(best, 0):
            best = other
    return best


def plan_of(user: dict[str, Any]) -> str:
    """The plan of an account row as `accounts.current` reads it (`accounts.PLAN_KEYS`): its subscription, its association's
    plan (`assoc_plan`, WP-158) and its workspace owner's subscription and association plan (`ws_*`, WP-157)."""
    owner = plan_in_force(user.get("ws_plan"), user.get("ws_status"), user.get("ws_period_end"),
                          association=user.get("ws_assoc_plan"))
    return plan_in_force(user.get("sub_plan"), user.get("sub_status"), user.get("sub_period_end"),
                         association=user.get("assoc_plan"), workspace=owner)


def allows(plan: str, feature: str) -> bool:
    return plan in FEATURES[feature]


def may(user: dict[str, Any], feature: str) -> bool:
    """Whether the account may use a paid feature. While no plan is on sale nothing can be bought, so
    nothing is withheld: accounts keep saved searches and alerts as WP-123 built them (owner decision
    to confirm, docs/verification/accounts/wp124-selfcheck.md). Once the plans exist, the plan decides. WP-152: the
    company report (and with it the name on reports) is nobody's while its switch (DGATE_COMPANY_REPORT_OPEN) is off."""
    if feature in ("company_report", "branded_reports", "sell_report") and not settings().company_report_open:
        return False
    if not plans_on_sale():
        return True
    return allows(plan_of(user), feature)


def features(user: dict[str, Any]) -> list[str]:
    # WP-158: "association" marks a member of a licensed association (the account area shows its page); no plan grants it
    return [f for f in FEATURES if may(user, f)] + (["association"] if user.get("assoc_plan") else [])


def search_limit(user: dict[str, Any]) -> int:
    """How many saved searches the account may hold and have run: its plan's, under the ceiling."""
    if not plans_on_sale():
        return SEARCHES_UNSOLD
    n = SAVED_SEARCHES.get(plan_of(user), 0)
    return SEARCH_CEILING if n is None else min(n, SEARCH_CEILING)


def seat_limit(user: dict[str, Any]) -> int:
    """WP-157: users a workspace owned by this account may hold, the owner included."""
    return SEATS["team"] if not plans_on_sale() else SEATS.get(plan_of(user), 0)


def client_limit(user: dict[str, Any]) -> int:
    """WP-157: client profiles the account's workspace may hold."""
    return CLIENTS["consultant"] if not plans_on_sale() else CLIENTS.get(plan_of(user), 0)


def report_limit(user: dict[str, Any]) -> int | None:
    """Company reports a calendar month (UTC); None: no limit. Nothing is counted against anyone while no plan is on
    sale (WP-124: nothing is withheld then)."""
    if not plans_on_sale():
        return None
    return REPORTS_PER_MONTH.get(plan_of(user), 0)


MESSAGES = {
    "saved_searches": "saved searches and e-mail alerts are part of Pro: choose a plan under Billing",
    "email_alerts": "saved searches and e-mail alerts are part of Pro: choose a plan under Billing",
    "company_report": "company reports are part of Pro: choose a plan under Billing",
    "competitors_full": "the full list of competitors is part of Pro: choose a plan under Billing",
    "signals_full": "the full list of signals is part of a paid plan: choose one under Billing",
    "signals_csv": "the CSV of a signal is part of Team and Consultant: choose a plan under Billing",
    "consortium_gaps": "the consortium gap analysis is part of Team and Consultant: choose a plan under Billing",
    "branded_reports": "your own name on reports is part of Consultant: choose a plan under Billing",
    "eligibility_export": "the eligibility check's results pack is part of Pro: choose a plan under Billing",
    "supplier_map_csv": "the supplier map as CSV is part of Team and Consultant: choose a plan under Billing",
    "team_workspace": "the team workspace is part of Team and Consultant: choose a plan under Billing",
    "client_profiles": "client profiles are part of Consultant: choose a plan under Billing",
    "expiring_contracts": "the full list of contracts ending soon and its alerts are part of Pro: choose a plan under Billing",
    "expiring_contracts_csv": "the CSV of contracts ending soon is part of Team and Consultant: choose a plan under Billing",
    "sell_report": "supplier reports are part of Pro: choose a plan under Billing",
}


def require(user: dict[str, Any], feature: str) -> None:
    if not may(user, feature):
        raise AccountError(402, "plan_required", MESSAGES[feature])


def founding_left(conn, exclude_account: Any = None) -> int:
    """Places left for Founding customer: 20 minus live founding subscriptions and founding checkouts
    opened in the last hour and not completed (another account's)."""
    taken = conn.execute(
        "SELECT (SELECT count(*) FROM billing_subscription WHERE plan = 'founding' AND status <> ALL(%s)) "
        "     + (SELECT count(*) FROM billing_checkout WHERE plan = 'founding' AND completed_at IS NULL "
        "          AND created_at > now() - %s::interval AND account_id IS DISTINCT FROM %s::uuid) AS n",
        (list(ENDED), FOUNDING_HOLD, exclude_account)).fetchone()["n"]
    return max(0, FOUNDING_CAP - int(taken))


# ------------------------------------------------------------------ Creem's API
class ProviderError(AccountError):
    def __init__(self) -> None:
        super().__init__(502, "payment_provider", "the payment provider did not answer: try again in a moment")


def _creem(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """One POST to Creem's API with the key in `x-api-key`. Nothing of the key, the request or the
    answer is logged. Redirects are not followed; the answer is size-capped."""
    try:
        r = httpx.post(f"{api_base()}{path}", json=body, timeout=10.0, follow_redirects=False,
                       headers={"x-api-key": settings().creem_api_key, "accept": "application/json"})
    except httpx.HTTPError:
        log.warning("billing: provider unreachable path=%s", path)
        raise ProviderError() from None
    if r.status_code >= 300 or len(r.content) > PROVIDER_ANSWER_MAX:
        log.warning("billing: provider answered %s path=%s", r.status_code, path)
        raise ProviderError()
    try:
        out = r.json()
    except ValueError:
        raise ProviderError() from None
    if not isinstance(out, dict):
        raise ProviderError()
    return out


def _provider_url(value: Any) -> str:
    """A URL from Creem's answer that the browser is sent to: https on creem.io (or, outside production,
    the local stand-in's own origin). Anything else is refused, so a bad answer cannot redirect anywhere."""
    if not isinstance(value, str) or len(value) > 2000:
        raise ProviderError()
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    if parts.scheme == "https" and not parts.username and (host == "creem.io" or host.endswith(".creem.io")):
        return value
    cfg = settings()
    if cfg.creem_api_url and cfg.env != "production":
        local = urlsplit(cfg.creem_api_url)
        if (parts.scheme, parts.netloc) == (local.scheme, local.netloc):
            return value
    raise ProviderError()


# ------------------------------------------------------------------ webhook: verification
def signature_ok(raw: bytes, given: str | None) -> bool:
    """`creem-signature`: lowercase hex HMAC-SHA256 of the raw body under the webhook secret. Every
    configured secret is tried (B5), each compared in constant time."""
    cfg = settings()
    if not given or not _SIG.match(given.strip()):
        return False
    ok = False
    for secret in (cfg.creem_webhook_secret, cfg.creem_webhook_secret_previous):
        if secret.strip():
            expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
            ok |= hmac.compare_digest(expected, given.strip())
    return ok


def _id(value: Any) -> str | None:
    """An id that Creem gives either as a string or as an object with `id`."""
    if isinstance(value, dict):
        value = value.get("id")
    return value if isinstance(value, str) and _ID.match(value) else None


def _when(value: Any) -> datetime | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_event(raw: bytes, now: datetime | None = None) -> dict[str, Any]:
    """The event, checked for shape and age. A refused one is a 400 and changes nothing."""
    try:
        event = json.loads(raw)
    except ValueError:
        raise AccountError(400, "bad_event", "not an event") from None
    if not isinstance(event, dict):
        raise AccountError(400, "bad_event", "not an event")
    event_id, kind, created = event.get("id"), event.get("eventType"), event.get("created_at")
    if (not isinstance(event_id, str) or not _ID.match(event_id) or not isinstance(kind, str)
            or len(kind) > 60 or not isinstance(created, int) or isinstance(created, bool)
            or not isinstance(event.get("object"), dict)):
        raise AccountError(400, "bad_event", "not an event")
    try:
        at = datetime.fromtimestamp(created / 1000, timezone.utc)
    except (OverflowError, OSError, ValueError):
        raise AccountError(400, "bad_event", "not an event") from None
    now = now or datetime.now(timezone.utc)
    if at < now - EVENT_MAX_AGE or at > now + EVENT_MAX_SKEW:
        raise AccountError(400, "stale_event", "event outside the accepted time window")
    event["_at"] = at
    return event


# ------------------------------------------------------------------ webhook: applying
def _write(conn, account_id: Any, plan: str, period: str, status: str, customer: str | None,
           subscription: str | None, period_end: datetime | None, event: dict[str, Any],
           refunded: bool = False) -> None:
    conn.execute(
        """INSERT INTO billing_subscription (account_id, plan, period, status, creem_customer_id,
                  creem_subscription_id, current_period_end, refunded_at, last_event_id, last_event_at)
           VALUES (%(a)s, %(plan)s, %(period)s, %(status)s, %(cust)s, %(sub)s, %(end)s,
                   CASE WHEN %(refunded)s THEN %(at)s END, %(eid)s, %(at)s)
           ON CONFLICT (account_id) DO UPDATE SET plan = EXCLUDED.plan, period = EXCLUDED.period,
                  status = EXCLUDED.status,
                  creem_customer_id = coalesce(EXCLUDED.creem_customer_id, billing_subscription.creem_customer_id),
                  creem_subscription_id = coalesce(EXCLUDED.creem_subscription_id,
                                                   billing_subscription.creem_subscription_id),
                  current_period_end = coalesce(EXCLUDED.current_period_end, billing_subscription.current_period_end),
                  refunded_at = coalesce(EXCLUDED.refunded_at, billing_subscription.refunded_at),
                  last_event_id = EXCLUDED.last_event_id, last_event_at = EXCLUDED.last_event_at,
                  updated_at = now()""",
        {"a": account_id, "plan": plan, "period": period, "status": status, "cust": customer,
         "sub": subscription, "end": period_end, "refunded": refunded, "at": event["_at"], "eid": event["id"]})
    # app_user.plan: the plan in force as of this event (the gates compute it again at each request, so a
    # cancellation at the end of a period needs no event to take effect).
    conn.execute("UPDATE app_user SET plan = %s WHERE id = %s",
                 (plan_in_force(plan, status, period_end, event["_at"]), account_id))


def _our_checkout(conn, ref: Any, account: Any, product: str | None) -> dict[str, Any] | None:
    """The checkout we created, when the event names it, its account and its product (B3)."""
    if not isinstance(ref, str) or not _UUID.match(ref) or not isinstance(account, str) or not _UUID.match(account):
        return None
    row = conn.execute("SELECT * FROM billing_checkout WHERE id = %s AND account_id = %s FOR UPDATE",
                       (ref, account)).fetchone()
    if not row or not product or row["product_id"] != product:
        return None
    return row


def _checkout_completed(conn, event: dict[str, Any]) -> str:
    obj = event["object"]
    meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    checkout = _our_checkout(conn, meta.get("checkout_ref"), meta.get("account_id"), _id(obj.get("product")))
    if (not checkout or checkout["creem_checkout_id"] != _id(obj)
            or obj.get("status") not in (None, "completed")):
        return "unmatched"
    sub = obj.get("subscription")
    order = obj.get("order") if isinstance(obj.get("order"), dict) else {}
    customer = _id(obj.get("customer")) or _id(order.get("customer"))
    status = sub.get("status") if isinstance(sub, dict) and sub.get("status") in STATUSES else "active"
    end = _when(sub.get("current_period_end_date")) if isinstance(sub, dict) else None
    live = conn.execute("SELECT * FROM billing_subscription WHERE account_id = %s FOR UPDATE",
                        (checkout["account_id"],)).fetchone()
    conn.execute("UPDATE billing_checkout SET completed_at = coalesce(completed_at, now()) WHERE id = %s",
                 (checkout["id"],))
    if live and live["creem_subscription_id"] not in (None, _id(sub)) and not over(live["status"], live["current_period_end"]):
        # Paid twice (two checkouts opened in two tabs): the first stays, the operator refunds the second.
        notify(f"DefenceGate billing: account {checkout['account_id']} paid a second subscription "
               f"({_id(sub)}); refund it in Creem")
        return "second_subscription"
    if live and live["creem_subscription_id"] == _id(sub) and live["last_event_at"] > event["_at"]:
        return "older"
    _write(conn, checkout["account_id"], checkout["plan"], checkout["period"], status, customer, _id(sub), end, event)
    return "applied"


def _subscription_row(conn, sub_id: str | None) -> dict[str, Any] | None:
    if not sub_id:
        return None
    return conn.execute("SELECT * FROM billing_subscription WHERE creem_subscription_id = %s FOR UPDATE",
                        (sub_id,)).fetchone()


def _subscription_event(conn, event: dict[str, Any]) -> str:
    obj = event["object"]
    sub_id = _id(obj)
    status = EVENT_STATUS[event["eventType"]] or (obj.get("status") if obj.get("status") in STATUSES else None)
    product = _id(obj.get("product"))
    customer = _id(obj.get("customer"))
    row = _subscription_row(conn, sub_id)
    if row is None:
        # Before checkout.completed (Creem does not promise an order): the subscription carries the
        # checkout's metadata, which names our checkout, its account and its product.
        meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        checkout = _our_checkout(conn, meta.get("checkout_ref"), meta.get("account_id"), product)
        if not checkout or status is None:
            return "unmatched"
        live = conn.execute("SELECT status, creem_subscription_id, current_period_end FROM billing_subscription "
                            "WHERE account_id = %s",
                            (checkout["account_id"],)).fetchone()
        if live and live["creem_subscription_id"] and not over(live["status"], live["current_period_end"]):
            return "second_subscription"
        _write(conn, checkout["account_id"], checkout["plan"], checkout["period"], status, customer, sub_id,
               _when(obj.get("current_period_end_date")), event)
        return "applied"
    if row["creem_customer_id"] and customer and row["creem_customer_id"] != customer:
        return "customer_mismatch"
    if row["last_event_at"] > event["_at"]:
        return "older"
    plan, period = plan_for_product(product) or (row["plan"], row["period"])
    _write(conn, row["account_id"], plan, period, status or row["status"], customer, sub_id,
           _when(obj.get("current_period_end_date")), event)
    return "applied"


def _refund_or_dispute(conn, event: dict[str, Any]) -> str:
    obj = event["object"]
    sub = obj.get("subscription")
    transaction = obj.get("transaction") if isinstance(obj.get("transaction"), dict) else {}
    row = _subscription_row(conn, _id(sub) or _id(transaction.get("subscription")))
    if row is None:
        return "unmatched"
    if row["last_event_at"] > event["_at"]:
        return "older"
    if event["eventType"] == "dispute.created":
        status = "disputed"
        notify(f"DefenceGate billing: a dispute was opened for account {row['account_id']}")
    else:   # a refund ends the plan only when Creem says the subscription ended with it
        status = "canceled" if isinstance(sub, dict) and sub.get("status") == "canceled" else row["status"]
    _write(conn, row["account_id"], row["plan"], row["period"], status, None, None, None, event,
           refunded=event["eventType"] == "refund.created")
    return "applied"


def apply_event(conn, event: dict[str, Any]) -> str:
    """B1: the event id first (a second delivery stops here), then the change, in one transaction."""
    first = conn.execute(
        "INSERT INTO billing_event (event_id, event_type, created_at, outcome) VALUES (%s, %s, %s, 'received') "
        "ON CONFLICT (event_id) DO NOTHING RETURNING event_id",
        (event["id"], event["eventType"], event["_at"])).fetchone()
    if not first:
        return "duplicate"
    kind = event["eventType"]
    if kind == "checkout.completed":
        outcome = _checkout_completed(conn, event)
    elif kind in EVENT_STATUS:
        outcome = _subscription_event(conn, event)
    elif kind in ("refund.created", "dispute.created"):
        outcome = _refund_or_dispute(conn, event)
    else:
        outcome = "ignored"
    conn.execute("UPDATE billing_event SET outcome = %s WHERE event_id = %s", (outcome, event["id"]))
    log.info("billing event=%s type=%s outcome=%s", event["id"], kind, outcome)
    return outcome


def prune_events(conn) -> None:
    """Event ids older than 30 days go: an event that old is refused by its age anyway."""
    conn.execute("DELETE FROM billing_event WHERE received_at < now() - interval '30 days'")


# ------------------------------------------------------------------ routes
router = APIRouter(prefix="/v1/account/billing", dependencies=[Depends(accounts.internal_only), Depends(no_store)])
webhook_router = APIRouter(dependencies=[Depends(accounts.internal_headers), Depends(no_store)])


def _subscription_out(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {"plan": row["plan"], "period": row["period"], "status": row["status"],
            "periodEnd": row["current_period_end"], "refundedAt": row["refunded_at"],
            "canManage": row["creem_customer_id"] is not None}


@router.get("")
def billing_state(conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    """What /app/billing shows. Places left for Founding customer only while billing is open (a
    number is shown only when it is true now)."""
    is_open = billing_problem() is None
    row = conn.execute("SELECT * FROM billing_subscription WHERE account_id = %s", (user["id"],)).fetchone()
    return {"open": is_open, "testMode": settings().creem_test_mode, "plan": plan_of(user),
            "features": features(user), "subscription": _subscription_out(row),
            "foundingLeft": founding_left(conn, user["id"]) if is_open else None,
            "foundingCap": FOUNDING_CAP}


class CheckoutIn(accounts._Body):
    plan: Literal["pro", "team", "consultant", "founding"]
    billing: Literal["monthly", "yearly"]


@router.post("/checkout")
def create_checkout(body: CheckoutIn, conn=Depends(get_conn), user=Depends(throttled)) -> dict[str, str]:
    """A Creem checkout for this account, created here so the key never reaches a browser. It grants
    nothing (B4): the verified webhook event does. The answer is the hosted checkout's address."""
    if billing_problem():
        raise AccountError(503, "billing_not_open", "payment opens soon")
    product = products().get((body.plan, body.billing))
    if not product:
        raise AccountError(422, "no_such_plan", "that plan has no such billing period")
    if plan_of(user) != "free":
        raise AccountError(409, "already_subscribed", "this account already has a plan: manage it under Billing")
    recent = conn.execute("SELECT count(*) AS n FROM billing_checkout WHERE account_id = %s "
                          "AND created_at > now() - interval '1 hour'", (user["id"],)).fetchone()["n"]
    if recent >= CHECKOUTS_PER_HOUR:
        raise AccountError(429, "rate_limited", "too many checkouts: try again later", {"Retry-After": "3600"})
    if body.plan == "founding":
        # One founding checkout at a time across the API (a transaction lock): the 20th place is taken once.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('billing_founding'))")
        if founding_left(conn, user["id"]) <= 0:
            raise AccountError(409, "founding_full", "all 20 Founding customer places are taken")
    ref = conn.execute(
        "INSERT INTO billing_checkout (account_id, plan, period, product_id) VALUES (%s, %s, %s, %s) RETURNING id",
        (user["id"], body.plan, body.billing, product)).fetchone()["id"]
    answer = _creem("/checkouts", {
        "product_id": product,
        "request_id": str(ref),
        "success_url": f"{settings().site_url.rstrip('/')}/app/billing?checkout=done",
        "metadata": {"account_id": str(user["id"]), "checkout_ref": str(ref)},
    })
    checkout_id, url = _id(answer.get("id")), _provider_url(answer.get("checkout_url"))
    if not checkout_id:
        raise ProviderError()
    conn.execute("UPDATE billing_checkout SET creem_checkout_id = %s WHERE id = %s", (checkout_id, ref))
    log.info("billing checkout user=%s plan=%s period=%s", user["id"], body.plan, body.billing)
    return {"url": url}


@router.post("/portal")
def customer_portal(conn=Depends(get_conn), user=Depends(throttled)) -> dict[str, str]:
    """Creem's customer portal for this account: cancel, invoices, payment method. Creem cancels from
    there; the canceled event then closes the plan here."""
    row = conn.execute("SELECT creem_customer_id FROM billing_subscription WHERE account_id = %s",
                       (user["id"],)).fetchone()
    if not row or not row["creem_customer_id"]:
        raise AccountError(404, "no_subscription", "this account has no subscription")
    if not settings().creem_api_key.strip():
        raise AccountError(503, "billing_not_open", "payment opens soon")
    answer = _creem("/customers/billing", {"customer_id": row["creem_customer_id"]})
    return {"url": _provider_url(answer.get("customer_portal_link"))}


async def _raw_body(request: Request) -> bytes:
    return await request.body()


@webhook_router.post("/v1/billing/webhook")
def webhook(raw: bytes = Depends(_raw_body), creem_signature: str | None = Header(None, alias="creem-signature"),
            conn=Depends(get_conn)) -> Response:
    """Creem's events, forwarded byte for byte by the site's server (web/app/api/billing/webhook). The
    signature is checked over the raw body before anything else is read. 200 for every verified,
    well-formed event, applied or not, so Creem stops retrying; 401 for a bad signature."""
    if not settings().creem_webhook_secret.strip():
        raise AccountError(503, "billing_not_open", "payment opens soon")
    if len(raw) > WEBHOOK_MAX:
        raise AccountError(413, "too_large", "request body too large")
    if not signature_ok(raw, creem_signature):
        log.warning("billing webhook: bad signature")
        raise AccountError(401, "bad_signature", "signature does not match")
    event = parse_event(raw)
    apply_event(conn, event)
    prune_events(conn)
    return JSONResponse({"ok": True})
