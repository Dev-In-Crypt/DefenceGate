# WP-160 self-check: contracts ending soon

Branch `wp-wp160` from `integration` 85541ff. Test copy `D:\DEFENCEGATE TESTS\wp160\` (own Postgres `dgate-wp160` on port
56160, removed at the end). Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-FEATURES-3.md`, with the owner's changes of
31 October 2026 (gate split, alerts in saved searches, accuracy labels) taking precedence. No portal called, no price in
any file. Production was not read (see "Open").

## What was built

### 1. One end-date rule (`backend/dgate/expiring.py`)

`end_sql(p, estimated=True)` and `basis_sql(p)`: the end the notice states, else its stated start plus its stated
duration, else, for an award notice only, its publication date plus the duration. Where the end comes from is one field,
`endBasis` (`end_basis` on `/v1/opportunities`):

| basis | rule | listed by default | words on every row |
|---|---|---|---|
| `stated` | `contract_end` | yes | "stated end date" |
| `computed` | `contract_start` + duration | yes | "computed from start + duration" |
| `estimated` | award notice, no start: `published_at` + duration (`estimatedFrom: award_published`) | only with `estimated=true` ("Include estimated end dates") | "estimated: award notice publication date + duration" |
| null | a duration with no start on a notice that is not an award, a duration over a century (typo), nothing stated | never | "duration only, no start: no end date" / "no end date stated" |

A renewal is never added to the end: `renewal` / `renewalsMax`, said as "renewal options: up to N renewals" or "renewal
possible". The same rule serves the list, its index, the notice's page (`tenders.get_tender` -> `expiring.periods`),
`/v1/opportunities` (list items and detail, `api.BASE_SELECT`), the saved searches and alerts, the CSV, and
`ops.contract_periods.coverage` (its `ends_12m` now counts stated + computed by this rule, estimates apart in `estimated_12m`).
Unit tests pin each basis (`tests/unit/test_wp160.py::test_each_basis_is_said`), the integration test each basis on a real
database (`test_each_basis_and_estimates_only_when_asked_for`).

One row per contract: one per eForms procedure (its award before its call, then the newest), a national notice hidden when
its TED notice is in the same list, cancelled procedures left out (`test_one_row_per_contract`).

### 2. API

- `GET /v1/tenders/ending?within=3|6|12&country&cpv&buyer&estimated=true` (public, under Caddy's existing `/v1/tenders/*`;
  the router is mounted before the tenders router so `ending` is not read as a slug): the first 10 rows soonest end first,
  `total`, `from`/`to`, `coverage` (per country: dated, estimated; from the data, cached 15 min). With `buyer`: the first
  20 (the buyer page's block, free in full).
- `GET /v1/account/contracts/ending` (internal only, signed in, throttled, `private, no-store`): the whole list, paged;
  `pageSize` > 100 is the CSV.
- `contractPeriod` on `/v1/tenders/{slug}` (and on the ending list's items); `contract_period` on every
  `/v1/opportunities` item and detail.
- Index: migration `0152_wp160_contracts_ending.sql`, a partial expression index `opp_contract_end` on exactly
  `end_sql("")` (`test_the_index_is_the_rule` holds them equal). Bench on the test container, 400,000 defence rows, 3,555
  in the 12-month window: 17 ms with the index (bitmap index scan on `opp_contract_end`), 43 ms without (parallel seq scan
  of a 69 MB table; production's table is far larger).

### 3. Gate (owner, 31 October 2026)

| what | who | enforced in |
|---|---|---|
| first 10 rows of the list | everyone | `expiring.public_ending` (FREE_ROWS) |
| buyer page block, first 20 | everyone (SEO) | `expiring.public_ending` (BUYER_ROWS with `buyer`) |
| the whole list, paged | Pro and up (`expiring_contracts`) | `expiring.full_ending` -> `billing.require` |
| the CSV (more than 100 rows at once) | Team, Consultant (`expiring_contracts_csv`) | `expiring.full_ending` -> `billing.require`; web route `tenders/ending/export.csv` 303s back when refused |
| saved search of kind `ending` and its alert | Pro (`expiring_contracts` as well as `saved_searches` / `email_alerts`) | `accounts.create_search`, `patch_search`, `search_kind_allowed` (paused in the list, left out of the dashboard), `ops/digest.run_digests` |

WP-124 kept: while no plan is on sale `billing.may` refuses nobody. Both states tested:
`test_first_ten_free_the_list_pro_the_csv_team_the_buyer_block_free`, `test_a_search_of_contracts_ending_soon_is_pro`,
`test_no_alert_while_accounts_are_closed_or_without_the_plan`, `tests/unit/test_wp160.py::test_the_gate_is_pro_and_the_csv_team`.

### 4. Alerts (saved searches of kind `ending`)

- `app_saved_search.kind` accepts `ending` (migration 0152); filters `country`, `cpv`, `buyer`, `within` (3/6/12),
  `estimated` (`accounts.clean_filters`, `_ENDING_KEYS`).
- New = entered the window since the last alert: `expiring.entered_at` = the later of the day the end came within N months
  and the first time we saw the notice (`accounts._stamp`, the same function the dashboard's new count uses).
- The mail (`ops/digest._line`): title, buyer, country, "ends YYYY-MM-DD (basis)", renewal, winners, link; section
  "N contracts newly ending within M months".
- Built dark: an `ending` search alerts only with `DGATE_ACCOUNTS_OPEN=1` and the plan; otherwise its window moves on, so
  no backlog is mailed later. Rendered through the mailer's catcher (`test_the_alert_mail_as_the_catcher_writes_it`:
  plain text and HTML parts).
- Ceiling (marked `ponytail:` in `expiring.entered`): a period stored later on a notice seen long ago (a backfill) whose end
  is already inside the window is listed, never mailed as new.

### 5. Web

- `/tenders/ending` (link from the `/tenders` header): 3/6/12 months, buyer country, CPV, "Include estimated end dates";
  the line why it matters; rows with buyer, country, CPV, notice id, the period with its basis and renewal, winners where
  known; the gate line (sign in / Pro / CSV for Team); "Save this search" (kind `ending`, when accounts are open); the
  coverage note from the API's `coverage`, with "Where the end dates come from".
- Tender page: a "Contract period" cell (span, duration, basis, renewal "not added to the end date"), free.
- Buyer page: "Contracts ending in the next 12 months", the first 20, link to `/tenders/ending?buyer=ID`.
- Cabinet: saved searches of kind `ending` are listed, described ("Ending within 6 months, ..."), linked to the list
  (`lib/account-format.ts`); dashboard items render as tenders.
- `lib/contract-period.ts` (words, filters, CSV; `lib/wp160.check.ts`), `components/tenders/contract-period.tsx`.

## Tests (this area only)

- backend: ruff clean; unit 4,191 passed; integration of the touched modules (52 files: accounts, billing, associations,
  tenders, opportunities, digests, WP-15x, WP-159, WP-160) 684 passed after moving the two feature-set pins below.
- web: tsc clean; lib checks (see RESULTS); Playwright `e2e/wp160.spec.ts` (demo build: 1440 and 375 px, light and dark,
  320 px no horizontal scroll), `e2e/wp160-api.spec.ts` (fake API, plans on sale), plus wp155-api, wp154, routes, wp52b-api,
  wp86, and the account specs against the fake account API.

RESULTS: see the end of this file.

Assertions moved on purpose (feature set grew by `expiring_contracts`, `expiring_contracts_csv`):
`tests/unit/test_wp124.py` (two), `tests/unit/test_wp155.py` (TABLE), `tests/integration/test_billing_wp124.py` (two),
`tests/integration/test_associations_wp158.py` (member's Pro list), `web/lib/wp155.check.ts` (PAID_FEATURES).

Screenshots: `D:\DEFENCEGATE TESTS\wp160\shots\` (list, list with estimates, tender stated / duration only, buyer block;
each at 1440 and 375, light and dark; fake-API states anonymous, free, Pro, Consultant).

## Shared edits (small, listed for the merge)

`backend/dgate/billing.py` (FEATURES, MESSAGES), `backend/dgate/api.py` (router mount, BASE_SELECT columns,
OpportunityOut.contract_period), `backend/dgate/tenders.py` (Tender.contractPeriod, get_tender), `backend/dgate/accounts.py`
(saved search kind), `backend/dgate/ops/digest.py`, `backend/dgate/ops/contract_periods.py` (coverage),
`web/lib/types.ts` (ContractPeriod, PAID_FEATURES, SearchKind, dashboard kinds), `web/lib/account-format.ts`,
`web/lib/account.ts`, `web/lib/api.ts`, `web/lib/mock/tenders.ts`, `web/components/account/actions.ts`,
`web/app/(app)/app/page.tsx`, `web/app/(public)/tenders/(list)/page.tsx`, `web/app/(public)/tenders/[slug]/page.tsx`,
`web/app/(public)/buyers/[slug]/page.tsx`, `web/e2e/support/fake-api.mjs` (PRO and Consultant feature lists, two routes),
`web/playwright.config.ts` (fake-api testMatch). `web/lib/pricing.ts` untouched: the orchestrator adds the line.

## Ops

1. Deploy runs migration 0152 (one partial index build on `opportunity`, writes wait for it; then `ANALYZE opportunity`).
2. Evidence on production, read-only (not run here, see Open): `D:\DEFENCEGATE TESTS\wp160\prod-evidence.sql` through
   the postgres container (`SET statement_timeout='30s'`, `BEGIN READ ONLY`): counts per basis and source, and EXPLAIN
   ANALYZE of the list's query (expect `Bitmap Index Scan on opp_contract_end` after the deploy).
3. `python -m dgate.ops.contract_periods` (report) now prints `ends in 12 months` by the list's rule and `(estimated N)`.

## Open

- The `/tenders` link to the list sits under the results (footnote): a link above them was the page's first `/tenders/`
  link, which `routes.spec.ts` and others read as a notice.
- Production EXPLAIN not run: the read-only query through ssh was refused by this session's permissions. The SQL is ready
  (Ops 2); the bench above is the only timing.
- `/pricing` line for the feature (orchestrator: Pro "Contracts ending soon: full list and alerts", Team "its CSV").
- Not built: e-mail alerts beyond saved searches, older BOAMP schemas, a nav entry (the header nav is pinned by
  `lib/wp86.check.ts`; the list is linked from /tenders, the tender page and the buyer page).
- `/tenders/ending` counts as `/tenders/[slug]` in the visit counter (`lib/hits.ts`), harmless.

## RESULTS (31 October 2026, test copy `D:\DEFENCEGATE TESTS\wp160\`)

| check | result |
|---|---|
| ruff | clean |
| backend unit (whole unit suite) | 4,191 passed |
| backend integration, touched area (52 files) | 684 passed (2 pins moved, then rerun of wp160, wp158, wp124, wp159: 72 passed) |
| tsc | 0 errors |
| web lib checks (`node scripts/run-checks.mjs`, pinned clock) | all ok, `wp160.check.ts` included |
| next build | ok |
| Playwright wp160, wp160-api, wp155-api, wp154, routes, wp52b-api, wp86 (desktop, mobile-375, fake-api projects) | 98 passed, 10 skipped (wp154's own skips) |
| account specs against the fake account API (wp150, wp79, wp153) | 22 passed |
