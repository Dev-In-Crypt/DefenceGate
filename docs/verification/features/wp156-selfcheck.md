# WP-156 self-check: the two exports of the plan split (30 Oct 2026)

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-FEATURES-2.md` (WP-156). Branch `wp-wp156` on `integration`. Nothing merged,
pushed or deployed; no production access. Test copy `D:\DEFENCEGATE TESTS\wp156\` (Postgres `dgate-wp156` on 56156, deleted at the
end). Screenshots: `D:\DEFENCEGATE TESTS\wp156\shots\`. No price is written anywhere in this change. No migration (nothing is stored).

## What was built

| Feature (billing.FEATURES) | Plans | What the customer gets | Where |
|---|---|---|---|
| `eligibility_export` | Pro, Founding, Team, Consultant | Cabinet page **Eligibility pack** (`/app/eligibility`, menu entry when `me.features` has it): every open call the saved profile fits (eligible, or nothing known blocks it), with the verdict, each rule line with the document's sentence, the call's page and its source link; **Print or save as PDF** (`window.print()`, A4 print CSS without the account menu) and **Download CSV** (one row per rule line). | `backend/dgate/exports.py:eligibility_calls`, `web/app/(app)/app/eligibility/page.tsx`, `web/components/account/eligibility-pack.tsx`, `web/lib/eligibility-pack.ts` |
| `supplier_map_csv` | Team, Consultant | **Download this list as CSV** under the supplier map: the list under the page's filters and order, up to 5,000 companies (the page itself stops at position 500), legal entities only, with a truncation row when cut and the source credit. | `backend/dgate/exports.py:supplier_export`, `web/app/(public)/suppliers/export.csv/route.ts`, `web/app/(public)/suppliers/page.tsx` |

The eligibility pack is built in the browser: the API answer (`GET /v1/account/eligibility/calls`) is the open calls and the facts
`/v1/fit/facts` serves, the same for every account; the profile and the verdicts never leave the browser. The verdict is the one
verdict of a call (`lib/fit.ts:callFit`), the list badge's and the call page's, with the profile's programme verdict from the
existing `POST /api/readiness/assess` (the request the readiness pages make; it carries the answers the rules read, as today).

## How each gate is enforced

| Gate | File:function | Refusal |
|---|---|---|
| Session | `exports.py` routes depend on `accounts.throttled` (session, 30 calls a minute per account) and the router on `accounts.internal_only`, `accounts.no_store` | 401; `private, no-store` |
| `supplier_map_csv` | `backend/dgate/exports.py:supplier_export` → `billing.require(user, "supplier_map_csv")` | 402 `plan_required`, message "the supplier map as CSV is part of Team and Consultant" |
| `eligibility_export` | `backend/dgate/exports.py:eligibility_calls` → `billing.require(user, "eligibility_export")` | 402 `plan_required`, message "the eligibility check's results pack is part of Pro" |
| WP-124 rule (no plan on sale: nobody refused) | `billing.may` unchanged: both features go through it | — |
| Accounts closed (DGATE_ACCOUNTS_OPEN) | both need a session; the CSV link is shown only when `/v1/account/status` says `open` or `plansOnSale` (`suppliers/page.tsx`) | link hidden |
| Site, CSV | `web/app/(public)/suppliers/export.csv/route.ts:GET`: any refusal (401, 402, a filter the list refuses, the API down) is a 303 back to `/suppliers?<same query>`, `private, no-store` | 303 |
| Site, pack | `web/app/(app)/app/eligibility/page.tsx`: without the feature the page says the plans and links Billing (no API call); the menu entry is keyed on `me.features` (`components/account/app-nav.tsx`, `PACK`) | plan text |
| Legal entities only | `suppliers.supplier_rows` over `award_set.scope()` (`WINNERS`: `individual_reason IS NULL`, not suppressed, not excluded) | a natural person is never a row |
| Cap | `exports.EXPORT_MAX` = 5,000 rows; `exports.PACK_MAX` = 1,000 calls (the answer gives `total`, the page says when not all were compared) | — |
| SECURITY_REQUIREMENTS O3 | both routes write `account event=supplier_export|eligibility_export user=<id> rows=<n>` (`accounts._audit`) | — |
| CSV injection | `lib/csv.ts:toCsv` (a cell starting `= + - @` gets an apostrophe), UTF-8 BOM, CRLF | — |

`suppliers.list_suppliers` now calls `suppliers.supplier_rows` (the old body, unchanged, with `limit`/`offset` as parameters), so
the export is the public list's query and order exactly; the list keeps its MAX_OFFSET check. `partners.fit_facts` now calls
`partners.facts_of` (the old body) so the pack reads the badge's facts for every open call at once without the 100-id limit of the
public endpoint.

## Tests

- Backend unit `backend/tests/unit/test_wp156.py`: each export follows the plan with plans on sale, nobody refused while none is on
  sale, both routes call `billing.require` and are registered.
- Backend integration `backend/tests/integration/test_wp156.py` (real Postgres): the export goes past MAX_OFFSET up to the cap, in
  the public list's order, without the sole trader, with contract values, the list's 422s, the O3 log line; the plan table with
  plans on sale (Free, Pro, Founding refused; Team, Consultant served); the eligibility answer lists only open calls, soonest first,
  with the badge's facts and quotes, the log line, the plan table (Free refused, Pro and up served); paging past one list page and
  the cap.
- Web lib check `web/lib/eligibility-pack.check.ts`: the pack's verdict is `callFit`'s; a small company fits both read calls, a large
  one is blocked by the SME-only call; unread calls counted, never listed; CSV row shape, dates, rolling calls, formula quote defused.
- Playwright against the fake API `web/e2e/wp156-api.spec.ts` (desktop 1280 and 375 px): the CSV link under the list; anonymous and Pro
  sent back to the list; Consultant downloads the file (BOM, header, values, defused formula name, truncation row); the pack page
  for an account without the feature (plan text, no menu entry), for Pro (menu entry, two calls of three, quotes, summary, CSV
  download, print hides the menu and the buttons), for a large company (one call), without a profile (the way to make one).

Results in the test copy: ruff clean; backend unit suite green; full integration suite 1,606 passed and 2 failed on the first run
(the two pinned feature sets in `test_billing_wp124.py`, fixed below), then those files and `test_wp156`, `test_wp155`, `test_wp32`,
`test_wp39` green (101 passed); tsc clean; all lib checks green (`run-checks.mjs` with the CI environment, `DG_USE_MOCK=1`); build
green; Playwright `wp156-api`, `wp155-api`, `wp152-api`, `suppliers`, `wp116` 70 passed (desktop, 375 px, fake-API projects; 320 px
no horizontal scroll and 1440 px shots inside wp156); account specs against the fake account API (wp150, wp79, wp153) 22 passed.

Assertions changed on purpose (they pin the feature list, which this change extends):
`backend/tests/integration/test_billing_wp124.py` (features while no plan is on sale; Pro's features),
`backend/tests/unit/test_wp124.py` (the set of FEATURES; the features of a free account while no plan is on sale),
`backend/tests/unit/test_wp155.py` (`TABLE`), `web/lib/wp155.check.ts` (`PAID_FEATURES`). The fake API's Pro sessions gain
`eligibility_export` and the Consultant session `supplier_map_csv` (the owner's table); it also answers `/v1/suppliers` now.

## Shared files touched (small)

`backend/dgate/billing.py` (FEATURES, MESSAGES, comment), `backend/dgate/api.py` (router), `backend/dgate/suppliers.py`
(`supplier_rows` split out), `backend/dgate/partners.py` (`facts_of` split out), `web/components/account/app-nav.tsx` and
`web/app/(app)/app/layout.tsx` (the menu entry), `web/lib/account.ts` (two calls, `timeoutMs` on `AccountInit`), `web/lib/types.ts`
(`PAID_FEATURES`), `web/app/robots.ts` (disallow `/suppliers/export.csv`), `web/playwright.config.ts` (the spec in the fake-API
projects), `web/e2e/support/fake-api.mjs`, `web/app/(public)/suppliers/page.tsx` (filters moved to `web/lib/supplier-filters.ts`,
the CSV line). Not touched: `web/lib/pricing.ts` and its tests (the orchestrator moves "Coming" at merge), config.py, compose.

## Personal data

None new. The supplier export holds legal entities only (as the public map); the eligibility pack's answers stay in the browser,
as the readiness check's. No DATA_PROTECTION draft needed.

## Ops to run

None. No migration, no switch: both features are live for an account the moment it has the plan (while no plan is on sale, for
every signed-in account), and invisible while accounts are closed.

## Left out / open

- Not timed on production (no access in this brief): the unfiltered 5,000-row export (one list query without the page cut, the
  shown-name subquery for each row and one contract-value query over 5,000 companies). The site waits 60 s for it
  (`getSupplierExport`). Before selling Team: time `GET /v1/account/suppliers/export` unfiltered once on the server.
- The pack lists open calls only (not forthcoming ones) and compares at most 1,000 (the answer says how many are open).
- No link to the pack from `/readiness/results` (a public page that does not read the session); the cabinet menu is the way in.
- A refused CSV goes back to the list without a message; the link's own words say who has it.
- `/pricing` still says "Coming" for both: the orchestrator's change at merge.
