# WP-124 self-check: payments through Creem (merchant of record), test mode, off by default

Branch `wp-wp124` from `integration` 7ba8543 (accounts WP-123 and pricing WP-122 merged). Builder's own check; an
independent verifier checks again. Tests ran in `D:\DEFENCEGATE TESTS\wp124` (own venv, throwaway Postgres 17
`dgate-wp124` on 55524, removed at the end). Creem was never called: its public documentation (docs.creem.io: webhooks,
customer portal, API introduction, TypeScript SDK) was read, and every test answers for Creem (a recorder in the
integration tests, `backend/tests/creem_mock.py` in the end-to-end test). Production not touched; nothing pushed,
merged or deployed; no secret in any file (test values only, named as such).

## What is built

| Item of the brief | Built | Where |
|---|---|---|
| Settings, names only | `DGATE_CREEM_API_KEY`, `DGATE_CREEM_WEBHOOK_SECRET`, `DGATE_CREEM_WEBHOOK_SECRET_PREVIOUS` (B5, rotation), `DGATE_CREEM_TEST_MODE` (default 1: `https://test-api.creem.io/v1`), `DGATE_CREEM_PRODUCT_{PRO,TEAM,CONSULTANT}_{MONTHLY,YEARLY}`, `DGATE_CREEM_PRODUCT_FOUNDING_YEARLY`. Key and secrets go to `api` only; the 7 product ids to `api` and `worker` (the worker decides who gets alert digests and holds no secret) | `dgate/config.py`, `infra/docker-compose.yml`, `infra/.env.example` |
| Closed by default | billing open = every setting set (`billing.billing_problem`) AND accounts open; the site also needs `NEXT_PUBLIC_BILLING_OPEN` (`lib/plans.billingOpen`). Closed: `/app/billing` says "Payment opens soon. Nothing is charged until then.", the checkout route answers 503 and calls nothing, the webhook answers 503 | `dgate/billing.py`, `web/app/(app)/app/billing/page.tsx` |
| Flow | pricing "Choose Pro, monthly" -> `/signup?plan=pro&billing=monthly` (WP-123 keeps the choice; the sentence now says "You pay for it after you sign in, under Billing." when payment is open) -> confirmation -> sign-in -> every account page shows "You chose Pro, monthly. Your plan is Free until it is paid. [Continue to payment]" -> `/app/billing` "Continue to payment" (server action) -> API `POST /v1/account/billing/checkout` creates the Creem checkout (`product_id`, `request_id` = our checkout reference, `success_url` = `<site>/app/billing?checkout=done`, `metadata` = account id + checkout reference; no e-mail address sent) -> Creem's hosted checkout -> back to `/app/billing` ("Your payment is being confirmed ...") | `billing.create_checkout`, `web/app/(app)/app/actions.ts` |
| Cancel URL | Creem's checkout API takes a `success_url` only (no cancel URL is documented); leaving the checkout is the browser's back button to `/app/billing`. Nothing is created or granted by an abandoned checkout | open item for the owner to check in Creem's dashboard |
| Webhook | Creem -> `https://<domain>/api/billing/webhook` (the site, the only public way in) -> forwarded byte for byte with `creem-signature` to the internal API `POST /v1/billing/webhook` (not in the Caddy allow-list; refuses `Origin`/`X-Forwarded-For`, checks `X-DG-Internal`). Caddy, the site and the API cap it at 64 KiB (every other request stays at 4 KB / 16 KiB) | `web/app/api/billing/webhook/route.ts`, `infra/Caddyfile`, `dgate/hardening.py`, `billing.webhook` |
| Signature | HMAC-SHA256 of the raw body under the webhook secret, lowercase hex, `hmac.compare_digest`; both secrets during a rotation | `billing.signature_ok` |
| Stale / replay | Creem signs no timestamp header, so the event's own `created_at` (inside the signed body) is the clock: older than 25 h (Creem retries for 24 h) or more than 5 min ahead is a 400 and changes nothing; every event id is stored (`billing_event`, 30 days), a second delivery is a 200 that changes nothing; an event older than the last one applied to the subscription changes nothing (`older`) | `billing.parse_event`, `billing.apply_event` |
| Mapping (B3) | `checkout.completed` applies only when it names a checkout we created (Creem checkout id), with that checkout's account (metadata) and product; it stores Creem's customer and subscription ids. `subscription.*` events apply by that subscription id (and customer id when given); before `checkout.completed` they apply through the metadata of our checkout. Never by an e-mail address | `_checkout_completed`, `_subscription_event` |
| States | `active`, `paid` -> active; `trialing`; `past_due` (Creem retries: the plan stays open, Creem's grace); `scheduled_cancel` (open to the end of the paid period, then Free without another event); `unpaid`, `paused`, `expired`, `canceled` -> Free; `subscription.update` takes the new product and state; `refund.created` records the time and ends the plan only when Creem says the subscription is cancelled; `dispute.created` -> `disputed` (Free) and the operator is told; anything else acknowledged and ignored | `billing.plan_in_force`, `EVENT_STATUS` |
| Table | `billing_subscription`: plan, period, status, Creem customer and subscription ids, current period end, refund time, last event id and time. `billing_checkout`: our reference, account, plan, period, product, Creem checkout id, opened / completed. `billing_event`: id, type, time, outcome. No card data, no address, no amount, no invoice | migration `0133_wp124_billing.sql` |
| Entitlements | one table and one function: `billing.FEATURES` (`saved_searches`, `email_alerts`: Pro, Team, Consultant, Founding customer, as on /pricing) and `billing.may(user, feature)`. Gated: creating and changing a saved search (402 `plan_required`), running it (list and dashboard), alert digests. Free keeps everything /pricing lists as free; shortlist and follows are not on /pricing as paid and are not gated; nothing "Coming" is built | `billing.py`, `accounts.create_search/patch_search/_search_out/dashboard`, `ops/digest.py` |
| Downgrade | the searches stay (listed, exported, deletable) and are shown "Paused: your plan has no saved searches or alerts ..."; they are not run and no digest is sent (their alert window moves on, so a later plan does not mail the backlog) | `/app/searches` |
| /app/billing | plan and period, status in words, "Renews on <date>" / "Open until <date>" / "Paid until <date>", refund note, "Manage subscription" -> Creem's customer portal (`POST /customers/billing` with the stored customer id -> `customer_portal_link`: cancel, invoices, payment method), test-mode line, the chosen plan's "Continue to payment" and every other plan and period with its price | `web/app/(app)/app/billing/page.tsx`, `lib/billing.ts` |
| Founding customer cap | 20 minus live founding subscriptions (any state but cancelled/expired) minus other accounts' founding checkouts opened in the last hour and not completed, under a transaction lock: the 20th place is taken once. "N of 20 places left." only on `/app/billing` (dynamic, the count of now) and only while billing is open; `/pricing` (rebuilt hourly) shows no number, as a stale one would not be true | `billing.founding_left`, `create_checkout` |
| Deletion with a subscription | the safe option: deletion is refused (409 `subscription_active`) until the subscription is cancelled; Settings says so before the form and after a refusal. Cancelling at Creem from our side was not chosen: an API cancel that failed half-way would delete the account and leave Creem charging | `accounts.delete_me`, Settings |
| Where the browser may be sent | only https on `creem.io` / `*.creem.io` (API and site both check the answer); outside production, the local stand-in's own origin for the e2e test (`DGATE_CREEM_API_URL` on the API, `DG_E2E_CREEM_ORIGIN` on the site; neither in compose) | `billing._provider_url`, `lib/account.providerUrl` |

### Owner decision to confirm: what accounts get while no plan is on sale

While the 7 product ids are not all set, `billing.may` allows every paid feature: nothing can be bought, so nothing is
withheld, and accounts behave as WP-123 built them (saved searches and alerts for every account). The gate switches on
by itself when the products are set. The alternative (gate always: no saved searches for anyone until Creem is live) is
one line in `billing.may`; say if you want it.

## Security review against SECURITY_REQUIREMENTS.md (billing B1-B5, D3, the standing rules)

| # | Requirement | How | Test |
|---|---|---|---|
| B1 | processed event ids; a repeat is acknowledged and ignored | `billing_event` PK, `INSERT ... ON CONFLICT DO NOTHING` in the same transaction as the change | `test_a_replayed_event_is_acknowledged_and_changes_state_once` |
| B2 | signature over the raw body, time tolerance, out-of-order by the object's own time | HMAC hex, constant time; `created_at` window (25 h / 5 min, see above: Creem has no signed timestamp header and retries for 24 h, so 5 minutes would refuse its own retries); `last_event_at` per subscription | `test_a_wrong_secret_or_a_malformed_signature_is_refused_and_changes_nothing`, `test_a_stale_or_future_event_is_refused_and_changes_nothing`, `test_an_older_event_arriving_later_changes_nothing`, unit `test_the_signature_is_hmac_sha256_hex_of_the_raw_body`, `test_a_stale_or_future_event_is_refused`, `test_the_comparison_is_constant_time` |
| B3 | keyed on the provider's customer id stored at checkout, never on an e-mail | Creem creates the customer at payment, not before, so the key is our checkout (created server-side, its id sent as `request_id` and metadata) and then the subscription and customer ids that the verified `checkout.completed` names | `test_an_event_naming_another_account_or_product_changes_nothing`, `test_an_event_with_an_accounts_email_but_not_its_ids_changes_nothing`, `test_a_subscription_event_before_the_checkout_event_is_matched_by_our_checkout` |
| B4 | nothing granted before a verified event | the checkout and the return URL grant nothing | `test_a_checkout_is_created_server_side_with_the_account_in_its_metadata_and_grants_nothing`, e2e (Free after returning from the checkout) |
| B5 | webhook secret rotatable without downtime | `DGATE_CREEM_WEBHOOK_SECRET_PREVIOUS`; runbook below | `test_the_previous_webhook_secret_verifies_during_a_rotation`, unit `test_both_secrets_verify_during_a_rotation` |
| D3 | plan changed only through the billing path | `app_user.plan` and `billing_subscription` written only by `billing._write`; no route sets a plan; the profile patch refuses the field | `test_the_plan_is_changed_by_no_other_route` |
| Key never in the browser | the checkout and portal calls are made by the API; the site's server holds no Creem setting | unit `test_the_creem_key_and_secrets_go_to_the_api_only_and_the_product_ids_to_api_and_worker`, `test_no_creem_secret_is_in_the_settings_repr`, `test_the_export_holds_the_subscription_and_no_secret` |
| Least privilege | grants in the migration that creates the tables (as 0131) | migration 0133 |
| Size caps | webhook 64 KiB (Caddy, site, API), provider answer 256 KiB, no redirects followed, 10 s timeout | `test_the_webhook_takes_a_large_event_and_refuses_one_over_64_kib`, unit `test_caddy_lets_the_webhook_through_to_the_site_with_its_own_size_cap`, e2e (413 at the site) |
| Internal only | the webhook route of the API refuses `Origin` and `X-Forwarded-For` | `test_the_webhook_is_internal_like_the_account_routes` |
| Open redirect | provider URLs checked on both sides | `test_a_provider_answer_pointing_off_creem_is_refused_and_leaves_no_checkout`, unit `test_only_https_creem_addresses_are_handed_to_the_browser` |
| Security log | billing lines with event id, type, outcome, account id; no key, secret, address or payload | DATA_PROTECTION.md row |

Residual (stated, not fixed): two checkouts opened in two tabs and both paid make two subscriptions: the first is kept,
the second is not applied and the operator is told by the alert channel to refund it (`second_subscription`,
`test_a_second_paid_subscription_is_not_overwritten_and_the_operator_is_told`); the founding cap can be passed only by
a checkout held longer than an hour and then paid (Creem's checkout sessions are short; the overshoot is at most the
number of such late payments).

Proposed rows for `docs/SECURITY_REQUIREMENTS.md` (on master; not in this checkout): "Billing B1-B5: built 25 October
2026 (Creem, merchant of record), `backend/dgate/billing.py`, migration 0133, `backend/tests/integration/test_billing_wp124.py`";
B2 note: "Creem: no signed timestamp header; the signed `created_at` with a 25-hour window (Creem's 24-hour retries)";
B3 note: "Creem: keyed on our checkout reference, then on the subscription and customer ids of the verified checkout event".

## Runbook: Creem settings and webhook secret rotation (B5)

Opening payment (test mode first):
1. In Creem (test mode): create the 7 products (Pro monthly EUR 59, Pro yearly 590, Team monthly 149, Team yearly 1,490,
   Consultant monthly 299, Consultant yearly 2,990, Founding customer yearly 390; prices excl. VAT, as on /pricing), an API
   key, and a webhook to `https://<domain>/api/billing/webhook` (copy its secret).
2. On the server, in `infra/.env`: `DGATE_CREEM_API_KEY`, `DGATE_CREEM_WEBHOOK_SECRET`, the 7 `DGATE_CREEM_PRODUCT_*`
   ids, `DGATE_CREEM_TEST_MODE=1`. Redeploy `api` and `worker`. The gate on saved searches and alerts switches on with the
   product ids.
3. Publish privacy 1.7 and terms 2.2 with the payment additions (drafts), then `NEXT_PUBLIC_BILLING_OPEN=1` and rebuild
   `web`.
4. Test with Creem's test cards; then live keys, live product ids, `DGATE_CREEM_TEST_MODE=0`, a live webhook and its
   secret, and redeploy `api` and `worker`.

Rotating the webhook secret: put the current secret into `DGATE_CREEM_WEBHOOK_SECRET_PREVIOUS`, create the new one in
Creem, put it into `DGATE_CREEM_WEBHOOK_SECRET`, redeploy `api`; once Creem signs with the new one (a test event from
the dashboard verifies), empty `DGATE_CREEM_WEBHOOK_SECRET_PREVIOUS` and redeploy `api`.

## Tests (batched scope)

| Check | Result |
|---|---|
| `ruff check .` | clean |
| pytest unit: `test_wp124.py` (new, 34: signature valid / wrong secret / malformed / previous secret, constant time, event age, malformed events, the plan of each state, the entitlement table, closed by default, test mode, URLs handed to the browser, compose / env example / Caddyfile), with `test_wp123`, `test_accounts`, `test_compose_env`, `test_mailer`, `test_credentials`, `test_wp34`, `test_wp71`, `test_wp127`, `test_migrate`, `test_hardening`, `test_worker` | 236 passed |
| pytest integration: `test_billing_wp124.py` (new, 47: closed by default, checkout, signature, stale, replay, rotation, internal only, size, every event mapping, out of order, B3, second subscription, gate, downgrade, digests, founding cap and hold, portal, deletion, export, D3), with `test_accounts`, `test_accounts_passwords`, `test_accounts_wp123`, `test_security_hardening`, `test_wp34`, `test_site_qa2`, `test_readiness_api` | 249 passed |
| web `tsc --noEmit`; lib checks `wp124` (new), `wp123`, `wp122` | clean; ok |
| `next build`, default (billing closed) and with `NEXT_PUBLIC_BILLING_OPEN=1` | both built |
| Playwright, default build, no API: `wp124` (closed part), `wp123`, `wp122`, `wp79`, `wp116` | 68 passed, 24 skipped (the API-only parts) |
| Playwright `wp79` against WP-79's fake account API (https proxy) | 14 passed |
| Playwright `wp123` against the real API (catcher, https proxy; the API with the billing settings on) | 4 passed (desktop, 375 px) |
| Playwright `wp124` against the real API, billing-open build, Creem stand-in: pricing -> signup -> confirm -> sign in -> saving a search refused while Free -> continue to payment -> stand-in checkout -> return grants nothing -> forged event 401, signed `checkout.completed` 200 -> "Pro, monthly. Status: Active. Renews on" -> search saved and running -> Manage subscription -> stand-in portal -> signed `subscription.canceled` -> "Free. Status: Cancelled." -> the search kept and "Paused" -> saving refused; and `/app/billing` at 1280 and 375 px | 3 passed |
| Caddyfile | `caddy validate` (caddy:2 image) valid |

Tests changed (none deleted, skipped or weakened): `tests/conftest.py` TABLES gains the three billing tables (they are
emptied like the other account tables). No other existing test was edited: `/me` keeps its `plan` object exactly as
WP-123 tested it, and the paid features are a new top-level `features` list.

## Files outside the package's own

`backend/dgate/hardening.py` (BodyLimit: 64 KiB on `/v1/billing/webhook`), `infra/Caddyfile` (64 KB on
`/api/billing/webhook`, 4 KB elsewhere as before), `backend/dgate/ops/digest.py` (the alert gate), `backend/tests/e2e_api.py`
(starts the Creem stand-in when asked), the WP-123 account pages (`signup`, `auth/verify`, settings, app layout and
menu: the plan sentence, the payment step, "Billing" in the menu, deletion with a subscription).

## Owner

- Create in Creem: the account (test mode first), 7 products (above), an API key, a webhook to
  `https://<domain>/api/billing/webhook` with its secret. Check whether the checkout can carry a cancel/return URL.
- Set on the server (names only): `DGATE_CREEM_API_KEY`, `DGATE_CREEM_WEBHOOK_SECRET`, `DGATE_CREEM_TEST_MODE`,
  `DGATE_CREEM_PRODUCT_PRO_MONTHLY`, `DGATE_CREEM_PRODUCT_PRO_YEARLY`, `DGATE_CREEM_PRODUCT_TEAM_MONTHLY`,
  `DGATE_CREEM_PRODUCT_TEAM_YEARLY`, `DGATE_CREEM_PRODUCT_CONSULTANT_MONTHLY`, `DGATE_CREEM_PRODUCT_CONSULTANT_YEARLY`,
  `DGATE_CREEM_PRODUCT_FOUNDING_YEARLY` (and `DGATE_CREEM_WEBHOOK_SECRET_PREVIOUS` only during a rotation); later
  `NEXT_PUBLIC_BILLING_OPEN=1` for the web build.
- Approve the drafts: `docs/legal/drafts/terms-v2.2-draft.md` (new term "Paid plans") and
  `docs/legal/drafts/privacy-v1.7-draft.md` (payments additions); Creem's legal entity and country, its privacy notice
  link, the refund rule, "price fixed" for Founding customer.
- Confirm the decision above (paid features free while no plan is on sale).
- `/pricing` still says "no paid plan is on sale yet" and "Is anything charged now? No": true while billing is closed;
  it has to change in the same release that opens billing (WP-122's copy and its test, not changed here).

Deploy (orchestrator): migration 0133 (additive: three new tables and their grants), then `api`, `worker`, `web`, and
Caddy (the Caddyfile changed). Nothing opens until the settings are set.
