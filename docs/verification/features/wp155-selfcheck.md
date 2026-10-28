# WP-155 self-check: the owner's plan split for the new features (28 Oct 2026)

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP155.md`. Branch `wp-wp155` on `integration`. Nothing merged, pushed or deployed;
no production access. Test copy `D:\DEFENCEGATE TESTS\wp155\` (Postgres `dgate-wp155` on 56155, deleted at the end). Screenshots:
`D:\DEFENCEGATE TESTS\wp155\shots\`. No price is written anywhere in this change.

## The table, and how each cell is enforced

One place decides every gate: `backend/dgate/billing.py` `FEATURES` (which plans have a feature), `REPORTS_PER_MONTH` and
`SAVED_SEARCHES` (how many), read through `billing.may` / `require` / `report_limit` / `search_limit`. Founding customer is Pro
(billing.py said so already: `PAID` includes it everywhere and /pricing says "Everything in Pro"; nothing said otherwise).

| Feature | Free (anonymous / signed in, no plan) | Pro (and Founding) | Team | Consultant | Enforced in |
|---|---|---|---|---|---|
| Competitors on a company page | top 5 (`competition.FREE_COMPETITORS`) | full list | full list | full list | public answer cut in `competition.py:competition`; full list `competition.py:full_competition` (`/v1/account/suppliers/{slug}/competition`, `require(competitors_full)`); site: `components/dg/competition.tsx:CompetitorsCard` link, new page `app/(public)/suppliers/[slug]/competitors/page.tsx`, and the report uses the full list when allowed |
| Where it wins, its share | everything | same | same | same | unchanged (`competition.py:analyse`) |
| Company report | the sample only | 3 a calendar month | 15 a month | unlimited, own name on it | `competition.py:open_report` (`POST /v1/account/suppliers/{slug}/report`: `require(company_report)`, `report_limit`, table `company_report_open`, migration 0147); site: `app/(public)/suppliers/[slug]/report/page.tsx` |
| Company signals | first 10 rows per tab; anonymous rows leave small companies out | full list on the page | full list and CSV | full list and CSV | `signals.py:answer` (`public`, `not_small`), `first_signal` (`/v1/account/signals/{kind}/first`), `full_signal` (`require(signals_full)`; a page over `PAGE_MAX` = 100 rows is the CSV: `require(signals_csv)`); site: `app/(public)/signals/page.tsx`, CSV link only when the API says `csv` |
| Data API with keys | no | no | no | no (licence only) | `apikeys.py:create_key` (403 `no_licence`), `apikeys.py:authenticate` (a key of an unlicensed account is refused), `accounts.py:_user_out` (`api_keys` only with the licence); licence set only by `python -m dgate.ops.api_licence` |
| Saved searches and alerts | none | up to 10 | up to 50 | unlimited (ceiling 200) | `accounts.py:create_search` (409 `limit_reached` at `search_limit`), `_search_out` / `list_searches` / dashboard (searches over the number are paused, the oldest run), `ops/digest.py:run_digests` (paused ones mail nothing) |
| Eligibility-check export | no | yes | yes | yes | **not built** (pricing: "Coming"); nothing to gate |
| Consortium gap analysis | no | no | yes | yes | `app/(public)/networks/consortium-gaps/page.tsx:gapGate` (the analytics API is not public: Caddy does not route `/v1/analytics`) |
| Supplier-map export | no | no | yes | yes | **not built** (pricing: "Coming"); nothing to gate |
| Branded reports | no | no | no | yes | `accounts.py:patch_me` (`require(branded_reports)` to set the name), `competition.py:open_report` (prints it only with the feature) |

### Rule 7 (WP-124): while no plan is on sale nobody is refused

`billing.may` returns True for every feature while `plans_on_sale()` is false (unchanged), `report_limit` is None (nothing
counted against anyone) and `search_limit` is 10 (what every account had before). Every new gate goes through `billing.require`,
so each one holds the rule. The gap page asks `/v1/account/status` (`plansOnSale`, new) before it looks at the visitor at all.
The two exceptions are the owner's rules, not plan gates: the full competitor list and small companies' signal rows need a
sign-in (rule 1), and reports need `DGATE_COMPANY_REPORT_OPEN` as before.

## Decisions taken here

- **Small company (rule 1):** fewer than **10** awarded procurements in the award set's whole window (three years, every country
  and CPV code, whatever the page's filters), `signals.SMALL_BELOW`. Why 10: below about three a year, a row's counts and its
  per-period sums are that company's few contracts one by one, i.e. its whole public defence business at a glance, which is the
  mosaic effect the rule is about; from ten on the sums are aggregates. The anonymous answer is the first 10 rows of companies
  that are not small; `total` still counts every row, and the page says "N of M companies shown; sign in for the rest. Rows of
  companies with fewer than 10 awarded procurements in three years are shown only after sign-in." A signed-in account without a
  plan gets the true first 10 (`/first`). For the funding tab the same rule applies, so research bodies and SMEs without
  procurements are not in the anonymous rows (see open questions).
- **Sample report (rule 5):** `DGATE_SAMPLE_REPORT_SLUG`, default `406963-indra-sistemas-sa`: Indra Sistemas SA, a large listed
  Spanish prime, 417 contracts on the supplier map in the saved companies page of the October content re-audit, the company most
  linked in our own docs, a legal entity (no natural person). Compared as the live organisation, so a merge does not lose it.
  Open to everyone, signed in or not, never counted; every report paywall links to it. Needs the report switch on, as every report.
- **Report count (rule 4):** one row per account, calendar month (UTC) and live company; the same company again that month is the
  same row and is not refused even when the month's number is reached. A refusal is 402 `report_quota`: "no company reports left
  this month: 3 of 3 opened; the count starts again on 2026-11-01 (UTC)". Two tabs cannot both take the last report (an advisory
  lock per account). A report whose figures are being renewed is not opened, so not counted.
- **Name on reports (rule 6):** `app_user.report_name`, settings block "Name on reports" (shown with `branded_reports`), 80
  characters, control and direction characters removed, one line (`accounts.clean_report_name`); React prints it as text. Printed
  beside the logo in the print head; on screen a line says it will be.
- **API licence (rule 3):** `app_user.api_licensed_at`, set only by `python -m dgate.ops.api_licence --email X [--revoke] [--yes]`
  (report by default; security log lines `api_licence_granted` / `api_licence_revoked` with the account id). Keys still need
  `DGATE_API_KEYS_OPEN`. Withdrawing the licence refuses the account's keys at once; granting it again lets unexpired, unrevoked
  keys work again.
- **"Full list" of competitors** stays the list as built (the first 20, `COMPETITORS`, with the total said). See open questions.

## Tests

Backend unit `tests/unit/test_wp155.py` (10): the table as `FEATURES` holds it, Founding = Pro, the numbers per plan, each gate
in the "on sale" state for every plan, nothing withheld while not on sale, the report switch, the report month, the name cleaning.
Backend integration `tests/integration/test_wp155.py` (8), per cell:

| Cell | Test |
|---|---|
| competitors 5 / full | `test_the_public_answer_names_five_competitors_and_a_signed_in_account_the_rest` (anonymous 5, signed in 8 while not on sale, free 402, every paid plan 8) |
| reports sample / 3 / 15 / unlimited | `test_reports_are_counted_once_per_company_and_month_against_the_plan`, `test_the_sample_report_is_open_to_everyone_and_never_counted` |
| own name (Consultant) | `test_the_name_on_reports_is_the_consultants_and_plain_text` |
| signals 10 / full / CSV, mosaic | `test_small_companies_rows_need_a_sign_in_and_the_csv_is_team_and_up` |
| saved searches 10 / 50 / pause | `test_saved_searches_follow_the_plan_and_those_over_it_pause` |
| API licence only | `test_keys_need_a_licence_that_only_the_operator_grants` |
| plans on sale flag | `test_the_status_says_whether_plans_are_on_sale` |

Web: `lib/wp155.check.ts` (the line under the first rows in each state, the feature list), Playwright `e2e/wp155-api.spec.ts`
(@fake-api, plans on sale: competitors anonymous / free / Pro, the report sample / paywall / Pro count / used quota / Consultant name
in print, signals anonymous / free / Pro / Consultant, gap analysis anonymous / Pro / Consultant). The "not on sale" state on the
site is the demo build's, covered by the existing wp152, wp154, networks and wp63 specs, which still pass.

Assertions changed because they pin a gate changed on purpose:
- `tests/unit/test_wp124.py`: the set of `FEATURES` and `features(free)` while not on sale (now every built feature).
- `tests/unit/test_wp152.py`: the company report is Pro and up (was Consultant, a placeholder).
- `tests/integration/test_billing_wp124.py`: `features` while not on sale and on Pro (two lines).
Test set-up changed (no assertion): `tests/integration/test_wp154_signals.py` reads WP-154's rows without the mosaic rule
(`SMALL_BELOW` 0, an autouse fixture; the rule has its own test); `tests/integration/test_api_keys_wp153.py` signs in accounts
that hold the licence (its `sign_in` grants it; the refusal without one is in test_wp155). The fake API of the e2e suite
(`e2e/support/fake-api.mjs`) gained the account routes of the split and answers `/v1/account/status` with `plansOnSale: true`
(`open: false` as its 404 meant before).

Runs in the test copy (28 Oct 2026): ruff clean; backend unit suite green (exit 0); full integration suite 1,603 passed and the two
`test_billing_wp124` assertions above failing as expected before they were moved, then `test_billing_wp124` + `test_wp155` 55
passed; tsc clean; every lib check ok (with the CI environment, `DG_USE_MOCK=1`, the pinned clock); `next build` ok. Playwright on
that build, the specs that open the changed pages (36 files, desktop, 375 px and the two fake-API projects): 552 passed, 56
skipped (gated account specs), 2 failed, both in `wp155-api` "the company report": the date format of my own expectation ("1 Nov
2026", fixed) and once a React hydration warning (#418) on the anonymous report gate on desktop, which did not come back in
`--repeat-each=3` of `wp155-api` and `wp152-api` on both fake-API projects (48 passed). The account specs against the fake account API
(wp150, wp79, wp153) 22 passed. The full Playwright suite was not run (batch rule).

## Screenshots (`D:\DEFENCEGATE TESTS\wp155\shots\`, desktop 1280 and mobile 375)

Free states: `supplier-free`, `competitors-anonymous`, `competitors-free`, `report-gate-anonymous`, `report-sample-anonymous`,
`signals-anonymous`, `signals-free`, `gaps-anonymous`. Paid states: `competitors-pro`, `report-pro`, `report-quota-used`,
`report-consultant-print`, `signals-pro`, `signals-consultant`, `gaps-consultant`.

## Files

Backend: `dgate/billing.py`, `dgate/competition.py`, `dgate/signals.py`, `dgate/apikeys.py`, `dgate/accounts.py`, `dgate/api.py`,
`dgate/config.py`, `dgate/ops/digest.py`, new `dgate/ops/api_licence.py`, new `migrations/0147_wp155_plan_split.sql`. Web:
`lib/types.ts`, `lib/account.ts`, `lib/signals.ts`, `components/dg/competition.tsx`, `components/account/actions.ts`,
`app/(public)/suppliers/[slug]/page.tsx`, `.../report/page.tsx`, new `.../competitors/page.tsx`, `app/(public)/signals/page.tsx`,
`app/(public)/networks/consortium-gaps/page.tsx` (outside the listed area: the gap analysis is a cell of the table),
`app/(app)/app/settings/page.tsx`, `app/(app)/app/actions.ts`, `app/(app)/app/keys/page.tsx`, `app/(app)/app/searches/page.tsx`
(the paused line), `playwright.config.ts` (one spec name). Draft: `docs/legal/drafts/data-protection-plan-split-draft.md` (new
personal data: the name on reports, the report counts, the licence date; nothing published).

## Open questions for the owner

1. **Pricing page copy** (`web/lib/pricing.ts`) still lists the old features per plan; it does not yet say reports a month, full
   competitors, signals and CSV, 50 / unlimited searches, or that the gap analysis leaves Free ("free on the site today"). Not
   changed here (owner's copy, and the file holds the prices). It should change before the plans go on sale.
2. **Consortium gap analysis leaves Free** once the plans are on sale: the page is public and indexed today. Confirm, and whether
   the Partners pages (named with it on /pricing) stay free (they do here).
3. **Small company = under 10 procurements in three years** also hides from anonymous visitors most funding-tab rows (research
   bodies and SMEs with few or no procurements). Keep, or use a funding-specific rule for that tab?
4. **"Full list" of competitors** is the first 20 with the total said. Raise it (e.g. 50) for paid plans?
5. **Unlimited saved searches** stop at 200 (each is run when the list is shown). Enough?
6. **Sample report** default Indra Sistemas SA; the operator can set another with `DGATE_SAMPLE_REPORT_SLUG` (to pass through
   `infra/docker-compose.yml` if changed; the default needs nothing).
7. After a move to a smaller plan the oldest saved searches keep running and the newest pause: or the other way round?
