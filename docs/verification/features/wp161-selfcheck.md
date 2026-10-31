# WP-161 self-check: launch-day rehearsal

Branch `wp-wp161` from `integration` 85541ff (= production). Test copy `D:\DEFENCEGATE TESTS\wp161\` (own Postgres `dgate-wp161`
on port 56161, removed at the end). Screenshots in `D:\DEFENCEGATE TESTS\wp161\shots\`. Nothing left the machine: mail into the
catcher (`ops/mailer._catcher`), Creem's API answered by `tests/creem_mock.py` on 127.0.0.1, webhook events signed locally with a
test secret, no procurement portal, no production access.

## How the rehearsal ran

- **API**: the real API (`tests/e2e_api.py`) on a throwaway database `launch`, migrated and seeded with a small market through
  the integration tests' own helpers (`wp161\seed.py`: a company with 8 rivals, 14 companies with a new-market signal, open TED,
  TenderNed and BOAMP tenders, two open calls). Every launch switch on: `DGATE_ACCOUNTS_OPEN=1`, `DGATE_COMPANY_REPORT_OPEN=1`,
  `DGATE_SIGNALS_FULL_OPEN=1`, `DGATE_API_KEYS_OPEN=1`, `DGATE_INTERNAL_SECRET` set (the site's header required), all seven
  Creem product ids, key and webhook secret set to local test values (plans on sale, billing open, test mode). Launcher
  `wp161\api-up.ps1`.
- **Worker jobs**: `python -m dgate.worker --once digest` and `--once association-digest` against the same database.
- **Ops modules**: `python -m dgate.ops.association` and `python -m dgate.ops.api_licence`, report mode first, then `--yes`.
- **Customer walk, API**: `wp161\rehearsal.py` drives the API as the site does (internal header, session header, client IP),
  reads every mail from the catcher, opens a checkout through the API and delivers Creem's `checkout.completed` signed with the
  test secret: the plan is granted exactly as on launch day (no shortcut into `billing_subscription`). 188 checks; findings
  `wp161\findings-*.json`, logs `run3.log` (before the fixes), `run4.log`, `run5.log` (after).
- **Customer walk, site**: a production build with `NEXT_PUBLIC_BILLING_OPEN=1` against that live API behind https
  (`wp161\web-run.ps1` phase b, walk `wp161\walk.spec.ts`, not committed): pricing, sign-up, the confirmation link from the
  catcher, sign-in, every cabinet page as Free, "Continue to payment" to the Creem stand-in's checkout, the signed event through
  the site's own `/api/billing/webhook`, the cabinet and the gated pages as Pro. Page texts dumped to `walk-*.txt`.

## Findings

Severity: blocker (a paying customer cannot get what they paid for, or the launch cannot happen), high (a paid path breaks or
a legal duty fails), medium (a customer is misled or stuck), low (cosmetic or operator-only).

| # | Path | Step | Expected | Got | Severity | State |
|---|---|---|---|---|---|---|
| 1 | Company signals, full lists and CSV (Pro, Team) | switch everything on as on launch day (`=1`) | full lists open for Pro, CSV for Team | 404 `not_open` for every plan: `DGATE_SIGNALS_FULL_OPEN` opened only with `true` (every other switch takes `1`), and `infra/docker-compose.yml` did not pass it to the API at all, so `infra/.env` could never open it | high | fixed |
| 2 | Account deletion | a subscription expired (period ended unpaid), then "Delete account" | 204, data gone | 409 `subscription_active`: only `canceled` counted as over; the customer can neither cancel (nothing to cancel) nor delete (GDPR Art. 17 self-service blocked) | high | fixed |
| 3 | Buying again | a cancellation at the end of the period has run out (plan Free), the customer buys again | the new plan | paid, but the event was taken for a second subscription: plan stayed Free and the operator was told to refund it | high | fixed |
| 4 | Saved-search alert mails (owner check 2) | stop the alerts from the mail | a link that works without signing in, `List-Unsubscribe` | only "Change or stop these alerts: /app/searches" (sign-in needed), no header | medium | fixed |
| 5 | /imprint (owner check 3) | no provider details set (as today, production and launch day alike: the page reads no setting) | no empty label, no placeholder | seven labels each "[to be provided]" and a "Draft, text pending" box | medium | fixed |
| 6 | /pricing with billing open | read the page as a customer on launch day | true copy | lead and FAQ "no paid plan is on sale yet", "Opens with sign-in" on every paid feature | medium | fixed |
| 7 | Free account, /app/searches and the dashboard, plans on sale | an empty list | what it takes to save one | "choose Save this search", which the API then refuses (402) | medium | fixed |
| 8 | /alerts with plans on sale | the lead | true copy | "sign in to save searches ... and get alerts" (both are Pro now) | low | fixed |
| 9b | Footer on every page, billing open | the alerts link | its page's h1 | "Alerts (not open yet)" while sign-in is open | low | fixed |
| 9 | /app/billing for a member of a team workspace | the plan line | "Team, through the workspace" | "Your plan is Free." (the member has the owner's Team plan) | low | fixed |
| 10 | Every "contact details in the imprint" (about, API licence, association page, privacy notice, removal requests) | find how to write to us | an address | the imprint has none until the owner gives the provider's details; on-request sales (association and API licences) have no contact route | blocker | owner |
| 11 | /pricing (lib/pricing.ts, the orchestrator's file) | read with plans on sale | true copy | "Consortium gap analysis (free on the site today, until plans go on sale)" is false once on sale (the page then gates it, `consortium-gaps/page.tsx`); "Unlimited saved searches" stops at 200 (`billing.SEARCH_CEILING`, the 201st is refused "at most 200 saved searches on your plan") | medium | orchestrator |
| 12 | Sign-up on a launch announcement | more than 120 sign-ups and resets in one hour | every customer gets the mail | A3's site-wide ceiling (`accounts.LIMIT_GLOBAL` = 120 account mails an hour) answers 429 "too many requests" to everyone past it and pages the operator | medium | owner decision (a security value; raise it for launch day or keep) |
| 13 | `ops.association --create/--license` | the report after `--yes` | the licence's last day, as the dry run says | prints the day after (the end is exclusive, `_end`); the member page says "ends at 1 Nov ... 00:00 UTC" for a 31 Oct last day | low | listed |
| 14 | Checkout while a subscription is `unpaid` or `paused` | plan Free, the customer pays again | one subscription | a second subscription the operator must refund (the first may still be charged by Creem) | low | listed (rare; Creem's dunning decides) |
| 15 | Rehearsal artefacts, not findings | 50 searches or 200 in a minute | - | the per-account bucket (30 calls a minute, `accounts.USER_RATE`) answers 429 with `Retry-After`; the walk waits it out. Per-IP mail limits likewise (each rehearsal customer came from its own address) | - | none |

Counts: 1 blocker (owner), 3 high (fixed), 6 medium (4 fixed, 1 orchestrator, 1 owner decision), 5 low (3 fixed, 2 listed). Fixed in code: 10.

### What passed (188 checks, `run4.log` + `run5.log`)

1. **Accounts**: sign-up (202), confirmation mail in the catcher (`From: DefenceGate <no-reply@...>`), sign-in refused before
   confirming (403), confirm once (second use 400), sign-in, `/me` (Free, the chosen plan remembered, terms current), reset
   (same 202 for an unknown address, no mail), new password signs every session out, "password changed" mail, old password
   refused, sign-out (session gone), delete with a wrong password refused, delete: **0 rows** for that account in `app_user`,
   `app_session`, `app_saved_search`, `app_shortlist`, `app_follow`, `app_auth_token`, `billing_checkout`,
   `billing_subscription`, `company_report_open`, `api_key`, `workspace_member`, `association_member`, and no invitation to
   the address.
2. **Plans**, each granted by checkout + signed `checkout.completed`: Free refused everything paid (402) and sees the first 10
   signal rows signed in (public: 10 of 14); Pro and Founding: 10 saved searches then 409, 3 reports then 402 `report_quota`,
   full competitors, full signals, no signal CSV, eligibility export yes, supplier map no, no workspace, no clients; Team: 50
   searches, 15 reports, signal CSV, supplier map, workspace with 5 seats; Consultant: 200 searches (ceiling), unlimited
   reports, 15 client profiles then 409, `branded_reports` only here. Founding places 19 of 20 after one; a second checkout
   with a plan in force 409. **Downgrade** Team to Pro (`subscription.update` naming the Pro product): the 50 searches kept,
   40 paused, a new one refused, workspace kept but inactive (sharing stops), supplier map 402, shortlist kept. **Expiry**:
   Free, every search kept and paused, reports 402, buying again works, deleting works (after fix 2). **Cancelled period run
   out**: buying again gives the plan (after fix 3).
3. **Team**: invitation mail with the join link; the link opened by another account 403 (and stays valid); accept; second
   use 400; the member has Team, sees the owner's search (not editable: delete 404), the shortlist with its note, the owner sees
   the member's follow; 5 seats full, the 6th invitation 409 `seats_full`; removal (member back to Free, its follow no longer
   shared), leave, the owner cannot leave (409); an expired link 400.
4. **Consultant**: 15 clients, a search for a client, the switcher (`?client=`) lists only its searches, the firm's name and
   the client's name on the company report.
5. **Association**: create and add members in report mode first (nothing written), then `--yes`; module output names no
   address; member Pro, admin Team, admin page "2 of 50"; digest opt-in; the worker stored the issues and sent the
   co-branded digest: `From: Baltic Defence Cluster via DefenceGate <no-reply@...>`, heading with the association's name,
   `List-Unsubscribe`, plain text and HTML; the stop link (no sign-in) switched it off; 50 seats filled, the 51st refused.
6. **API keys**: no licence 403; licence in report mode then `--yes`; a wrong password refused (K2); the key shown once, only its
   hash stored; list 200 with only `ted` and `nl_tenderned`, `private, no-store`; `source=fr_boamp` 403
   `source_not_licensed`; TenderNed 200; archive out of scope 403; another route 403; rate limit 429 with `Retry-After`;
   revoked key 401.
7. **Security (docs/SECURITY_REQUIREMENTS.md)**: O1 across tenants, each a 404: another owner removing my member or cancelling
   my invitation by id, renaming my search, using my client id on a report, editing my client, listing my client's searches,
   revoking my key. A6: the account API without the internal header 403, with a foreign `Origin` 403. Invite tokens one-time and
   address-bound (above). No e-mail address and no token in the API log or the security log (441 lines, account ids only).
   Tokens travel only as `?token=` (dropped from the proxy's log) or in POST bodies.
8. **Pages and copy** (build B against the live API): sign-up shows the chosen plan and the texts' versions; billing in test
   mode ("Test mode: no real payment is taken."), "Continue to payment" to the stand-in's checkout, the plan active after the
   signed event, a forged event through the site's route refused (401); the gated pages say which plan (supplier CSV and signal
   CSV 303 back to their pages for Pro, "part of the Team and Consultant plans"; consortium gaps "part of the Team and
   Consultant plans: see Billing"). Before the fixes, the copy findings 6 to 9 above.

## Owner checks of 31 October

1. **Payments in test mode only, no real charge.** No live key, secret or product id in the repository (`git grep` for
   Creem key, `whsec_`, `prod_` shapes: only test values in tests). Creem is called only from `billing._creem`, and only when
   the API key is set; with any setting missing `billing_problem()` closes billing (checkout 503). Test mode is the default
   (`DGATE_CREEM_TEST_MODE` unset = `test-api.creem.io`); the local stand-in URL is ignored in production. The webhook checks
   the HMAC over the raw body before reading it: unsigned and forged events are refused 401 and change nothing (new test
   `test_a_forged_or_unsigned_billing_event_changes_nothing`; the site's route forwards byte for byte, Playwright
   `wp161.spec.ts` against the fake). **For a real test-mode payment** the owner needs: a Creem account in test mode with the
   seven products, its test API key and webhook secret in `infra/.env` (`DGATE_CREEM_API_KEY`, `DGATE_CREEM_WEBHOOK_SECRET`,
   `DGATE_CREEM_PRODUCT_*`, `DGATE_CREEM_TEST_MODE` left at 1), the webhook URL `https://<domain>/api/billing/webhook` in Creem's
   dashboard, `NEXT_PUBLIC_BILLING_OPEN=1` at the web build, then one purchase with Creem's test card and a cancel in its
   portal (runbook in `docs/verification/accounts/wp124-selfcheck.md`). Nothing of that was built or called here.
2. **Double opt-in.** Every subscription is made by a signed-in account, and sign-in requires a confirmed address: the
   registration sends a confirmation link (single use, 24 hours, hashed), sign-in is refused until it is used (403
   `not_verified`), an unconfirmed registration is deleted after two days, and the address cannot be changed afterwards. Saved
   search alerts are switched on by the account holder on the search; the association digest is off by default
   (`association_member.digest DEFAULT false`) and switched on by the member on `/app/association`; the operator adding a member
   sends nothing. So nothing is ever mailed to an address that has not confirmed itself, and the confirmation mail is the
   double opt-in; a second confirmation per subscription was not added (it would confirm an address already confirmed; owner
   to decide if a lawyer wants it). **Unsubscribe without sign-in**: the association digest had it; the alert mails did not
   (finding 4, fixed). No public, address-only subscription exists (`/alerts` and `/digest` offer feeds, not mail).
3. **Imprint without company data**: finding 5, fixed. The page reads no environment setting, so production and launch day
   render the same: "The provider's details are not published yet. They will be here before any plan is sold.", no label, no
   placeholder, no draft box; the details go into `PROVIDER` in `web/app/(public)/imprint/page.tsx` and only the fields given are
   shown. The footer links to the imprint only (no company data in it). The pages that send people to "the contact details in
   the imprint" are finding 10 (owner).

## Fixes (root cause, one test each)

| # | Change | Test |
|---|---|---|
| 1 | `config.signals_full_open` opens with `1` (and still `true`); `infra/docker-compose.yml` passes `DGATE_SIGNALS_FULL_OPEN: ${DGATE_SIGNALS_FULL_OPEN:-0}` to the API | `tests/unit/test_wp161.py`: every launch switch reaches the API closed by default and opens with `1` (8 cases) |
| 2, 3 | `billing.over(status, period_end)`: the one rule of "Creem can charge it no more" (none, `canceled`, `expired`, or `scheduled_cancel` past its period end); `ENDED` gains `expired`; used by `accounts.delete_me` and both "second subscription" checks of the webhook | `tests/integration/test_wp161.py`: `test_an_account_whose_subscription_expired_can_be_deleted`, `test_a_cancellation_whose_period_ran_out_lets_the_account_buy_again_and_be_deleted` |
| 4 | migration 0153 `app_user.alerts_stop_token` (random, unique, as the association's token); `POST /v1/account/alerts/unsubscribe` (no session, same answer for any token, sets every search of that account to `off`, audit line); the alert mail ends "Stop all these alerts: /unsubscribe?kind=alerts&token=..." and carries `List-Unsubscribe`; `/unsubscribe` handles `kind=alerts` (button, POST) | `test_an_alert_mail_can_be_stopped_without_signing_in`; Playwright `wp161.spec.ts` (the stop page) |
| 5 | `/imprint` shows only the provider fields given; none given: one sentence, no draft box | Playwright `wp46.spec.ts` (assertion changed on purpose, below) and `wp161.spec.ts` |
| 6 | `/pricing`: lead, description, the first FAQ answer and the "Opens with sign-in" tags follow `BILLING_OPEN`; the closed build is unchanged | Playwright `wp122.spec.ts` (runs in both builds; the lead assertion now follows the build, below) |
| 7 | `/app/searches` and the dashboard: a Free account (no `saved_searches` feature) is told the plans that have it, with links to Billing and Pricing | Playwright `wp161.spec.ts` (Free, then Team) |
| 8 | `/alerts` lead with `plansOnSale` | the rehearsal walk (build B); no committed test (the fake account API has one status for every spec) |
| 9b | `lib/nav.ts`: the footer's alerts link follows `BILLING_OPEN` ("Alerts and saved searches", the page's h1) | Playwright `wp122.spec.ts` (both builds) |
| 9 | `/app/billing`: a plan with no subscription of its own and a workspace says it comes from the team workspace | tsc and the walk; no committed test (no member persona in the fake account API) |

The test helper `sent` of `tests/integration/test_accounts.py` now accepts the mailer's keyword arguments (the alert mail passes
`headers=`), and one `lambda *a: False` became `lambda *a, **k: False`; nothing asserted changed.

Assertions changed on purpose: `web/e2e/wp46.spec.ts` (the imprint's seven placeholders, pinned before the owner's check 3 of
31 October); `web/e2e/wp122.spec.ts` (the lead now differs with billing open).

## Files

Backend: `dgate/config.py`, `dgate/billing.py`, `dgate/accounts.py` (deletion rule, alert stop route), `dgate/ops/digest.py`,
`migrations/0153_wp161_alert_stop.sql`, `tests/unit/test_wp161.py`, `tests/integration/test_wp161.py`,
`tests/integration/test_accounts.py` (helper only). Infra: `infra/docker-compose.yml` (one env line). Web:
`app/(public)/imprint/page.tsx`, `app/(public)/pricing/page.tsx`, `app/(public)/alerts/page.tsx`,
`app/(public)/unsubscribe/page.tsx` and `actions.ts`, `app/(app)/app/searches/page.tsx`, `app/(app)/app/page.tsx`,
`app/(app)/app/billing/page.tsx`, `lib/account.ts` (`unsubscribeAlerts`), `lib/nav.ts` (footer label), `e2e/wp161.spec.ts` (new), `e2e/support/fake-accounts.mjs`
(the "launch" customer, a signed webhook, the alerts stop route), `e2e/wp46.spec.ts`, `e2e/wp122.spec.ts`. Docs: this file,
`docs/legal/drafts/data-protection-alert-stop-draft.md` (DRAFT inventory rows for the new token; nothing published).
Not touched: `web/lib/pricing.ts` and its tests, WP-160's files.

## Tests run (test copy, final code)

| Check | Result |
|---|---|
| ruff | clean |
| backend unit (whole suite) | 4187 passed |
| backend integration, the areas touched: `test_wp161`, `test_billing_wp124`, `test_accounts`, `test_accounts_passwords`, `test_accounts_wp123`, `test_wp157_workspace`, `test_associations_wp158`, `test_wp154_signals`, `test_wp155`, `test_wp152`, `test_wp156`, `test_api_keys_wp153`, `test_security_hardening` | 232 passed |
| tsc, web lib checks | clean, pass |
| `next build` (default) and Playwright desktop + mobile-375: `wp161`, `wp46`, `wp158`, `wp124`, `wp157`, `wp122`, `wp86` (public parts) | 68 passed, 28 skipped (the other build's or the fake API's) |
| Playwright against the fake account API (https): `wp161`, `wp150`, `wp79`, `wp153`, `wp157`, `wp158` | 39 passed, 1 skipped (wp157's screenshot test on mobile, by design) |
| `next build` with `NEXT_PUBLIC_BILLING_OPEN=1` against the live API: the walk; `wp122` on that build | walk 2 passed; wp122 14 passed, 2 skipped (billing-off tests) |

## Ops (owner / orchestrator, after merge and deploy; nothing was run on production)

1. Migration 0153 runs with the deploy (`python -m dgate.migrate`): one column with a per-row random default on `app_user`.
2. Launch day, in `infra/.env`: `DGATE_ACCOUNTS_OPEN=1`, `DGATE_ACCOUNT_KEY`, the SMTP relay (`DGATE_SMTP_*`),
   `DGATE_COMPANY_REPORT_OPEN=1`, `DGATE_SIGNALS_FULL_OPEN=1` (now reaches the API), `DGATE_API_KEYS_OPEN=1`, the Creem key,
   webhook secret and seven product ids; recreate `api` and `worker`; rebuild `web` with `NEXT_PUBLIC_BILLING_OPEN=1`.
3. Publish the provider's details in the imprint before the first sale (finding 10), the privacy rows of the draft, and the
   pricing.ts lines of finding 11.

## Open questions for the owner

- Raise `LIMIT_GLOBAL` (120 account mails an hour, site-wide) for the launch announcement? (finding 12)
- A second confirmation mail per digest subscription on top of the confirmed account, or is the account's confirmation enough?
- "Unlimited saved searches" (Consultant): keep the 200 ceiling and change the wording, or raise the ceiling?
