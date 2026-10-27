# WP-154 self-check: company signals for investors (/signals)

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-FEATURES-1.md`, section WP-154. Branch `wp-wp154` on `integration`. Nothing merged,
pushed or deployed. No migration was needed (0146 stays free). Screenshots: `D:\DEFENCEGATE TESTS\wp154\shots\` (demo data, desktop
1440x900 and mobile 375x812, light and dark, the three tabs).

## What was built

A new page `/signals` with three tabs, each a list of facts with their sources. One line on every tab: "Facts from public records, not
investment advice." (a `NoteLine` with "How we count" beside it). The service (tabs, filters, first row) is on the first screen at
1440x900 and 375x812.

| Tab | A row is | Each row links to |
|---|---|---|
| Growing in defence | a company whose awarded procurements of the last 12 months exceed those of the 12 months before, at least 2 (`MIN_RECENT`); both counts; where both periods state contract values in one currency, both sums with how many are valued | the supplier page (`/suppliers/{slug}`), the newest notice at its source (TED link) and our copy (`/tenders/{slug}`) |
| New markets | a company's first win with the buyers of a country in the last 12 months, when it won elsewhere before and never in that country in the rest of the three-year window | the supplier page, the first notice there (source and our copy) |
| New EU defence funding | a company in a project of the latest call year of the EU defence programmes (EDF, EDIDP, EDIP, PADR), its first such participation flagged ("First EU defence project"), first-timers first | the organisation page (`/organisations/{slug}`), each project page (`/projects/{slug}`, which carries the factsheet or CORDIS link) |

Filters: company country (code or English name, as the supplier map), CPV code or its start (procurement tabs), programme (funding tab).
The API refuses a filter that does not belong to the tab (422), and the page offers only the right ones.

Backend: `backend/dgate/signals.py` (new), `GET /v1/signals/{kind}` (public: the first 10 rows and the total) and
`GET /v1/account/signals/{kind}` (paid part, below). Web: `web/app/(public)/signals/page.tsx`, `web/app/(public)/signals/export.csv/route.ts`,
`web/lib/signals.ts`, `web/lib/mock/signals.ts`, `getSignal` in `web/lib/api.ts`, `getFullSignal` in `web/lib/account.ts`; a footer
link "Company signals" in the About group (`web/lib/nav.ts`; not in the header menu, see open question 3).

## One definition of everything (no second "award" or "defence buyer")

- The rows are `award_set` (`FROM`, `scope()`: defence scope, not removed, legal-entity winners, the PLACSP switch and the TED+PLACSP twin
  rule), the unit is the procurement (`KEY_HASH`), the filters are `suppliers._filters` (supplier's country, any CPV code under a prefix).
- A procurement's date is its newest notice's, as the supplier page's years count it (`get_supplier` `byYear`).
- Values are `suppliers.value_of` + `best` + `value_totals`: contract values only, per currency, never converted, a unit price under
  EUR 1,000 counted but in no sum, frameworks and estimates never added.
- The company and its slug are the supplier map's (live organisation, `suppliers.shown` spelling), so a row's link is its page.
- Participations are `network_api`'s: active only, through merges (`organisation_merged_live`), `YEAR` = start year else call year.
- The integration test checks that the supplier page's `noticeCount` equals the signal's two counts for the same company (the four
  procurements of the two-year window, a procedure published in two notices counted once).

## The paid part, behind one switch

`DGATE_SIGNALS_FULL_OPEN` (backend, default off). Off: the public answer says `fullOpen: false`, the page shows the first 10 rows and
"The first 10 of N companies." (no CSV, no prompt); `/v1/account/signals/*` answers 404 `not_open`. On: a signed-out visitor is told
"The full list and its CSV are part of a paid plan: sign in or see pricing"; a signed-in account whose plan is not in `signals.PLANS`
gets 402 and "choose one under Billing"; an allowed account gets the whole list 50 a page with pagination and "Download CSV"
(`/signals/export.csv`, up to 2,000 rows, a truncation row when cut, source credit and the not-advice line on every row).
`signals.PLANS` is every paid plan for now (one constant for the owner to narrow). While no plan is on sale every signed-in account may,
as `billing.may` decides for the existing features. `billing.FEATURES` is not touched (its tests pin it, and WP-152/153 may add theirs).

## Personal data and wording

- Natural persons: the award set leaves out every winner with `individual_reason`; the funding signal leaves out every organisation with
  `individual_reason` or `suppressed`. Tested with a sole trader holding the most wins and a person in an EDF project: neither appears.
- No new personal data is stored; nothing in `DATA_PROTECTION.md` or the privacy notice changes, so no draft was needed.
- Wording: facts and counts with their sources; no "invest", "buy", "opportunity", score or prediction. Privacy and terms untouched.
- Note for the owner: `suppliers.py`'s docstring says "nothing is derived from several notices into a ranking, a share or a dependency
  score". "Growing" is an order derived from counts over many notices (the brief asks for it). It names no share and no dependency, but it
  is a ranking; the owner lifted the freeze for this idea, so it is built, and it is said here.

## Known data defect: one company in several organisation rows

Nothing is merged. A company split over several rows (Rheinmetall Electronics 426698 / 428360 / 430165) is several companies to every
signal: its growth is split between rows (each row may fall under `MIN_RECENT` or show a smaller rise), and a new market can show for one
row when another row of the same company already won there. The size of this on production could not be measured (production access was
denied in this session, see below). The signals do not make the defect worse than the supplier map does: they read the same rows.

## Tests

| Check | Result |
|---|---|
| ruff | clean |
| backend unit (incl. new `tests/unit/test_wp154.py`: gate, programme filter) | 4,101 passed |
| backend integration (incl. new `tests/integration/test_wp154_signals.py`, 5 tests) | 1,577 passed (own Postgres 17) |
| tsc | 0 errors |
| lib checks (`node scripts/run-checks.mjs`, incl. new `lib/wp154.check.ts`: filters, paid states, value line, CSV rows) | all ok |
| Playwright `e2e/wp154.spec.ts` + `e2e/wp86.spec.ts` (footer links, every footer label is its page's h1), desktop and mobile-375 | 25 passed, 6 skipped (phone-only and screenshot tests), 1 failed: `wp86.spec.ts:93` mobile header search timed out waiting for the menu's field under 4 workers, twice; alone (1 worker) it passes in both projects. It touches the header menu only, which this change does not touch: a timing race, not a regression |

Test copy `D:\DEFENCEGATE TESTS\wp154\` (Postgres on port 56154: the brief's 55454 sits in a range Windows reserves, 55395-55494).

The integration tests cover: growing counts and sums (unit price excluded, a two-notice procedure once), the supplier page's equal count,
the filters (country by name, CPV prefix, refusals), new markets (needs a win elsewhere before; home market already won excluded), no person
or removed company in any row, the funding signal (latest call year, first participations first, merged organisation counted under its
live row, inactive participation and non-defence programme ignored, EDIDP filter gives none), and the paid part (first 10 public, no paging
on the public answer, 401 / 404 closed / 200 with nothing on sale / 402 free account with plans on sale / 200 paying account,
`private, no-store`).

Not covered by an automated test: the page in the signed-in states (the e2e site has no account API for this page; the states are a pure
function, `fullState`, checked in `lib/wp154.check.ts`), and the CSV route end to end.

## Production reads not done (access denied in this session)

The read-only SELECTs below should be run by the orchestrator before the owner decides (each with `SET statement_timeout = '30s'`):
1. Row counts per signal: `/v1/signals/growing`, `/markets`, `/funding` `total` (with the PLACSP switch as on production).
2. Time of each ranked query cold (the growing one aggregates the award set's last two years per company and procurement, as
   `/v1/suppliers/summary` does over three years: expected well under a second; it is cached 30 minutes per day and filter set).
3. The latest call year the funding signal finds (the EDF factsheets carry the call year only, no start date) and how many organisations
   are first-timers in it.
4. For the duplicate defect: how many growing rows belong to a company group (`company_group_member`) with another row in the list.

## Left out (smallest version first)

- "New markets" by buyer type (only by buyer country): the buyer class is a scope signal, not a stable type a reader would recognise.
- A share of a market, value growth in a converted currency, and any company-group roll-up (a group is listed by its member rows).
- The API path is not added to Caddy's public allow-list (`infra/caddy/Caddyfile`): the site reads it over the compose network; infra
  is untouched.
- Alerts on new signals, saved signal searches, and the signals in the cabinet.

## Open questions for the owner

1. Which plan carries the full list and the CSV (`signals.PLANS`, every paid plan now)?
2. `MIN_RECENT` = 2 for "growing" (1 against 0 is no trend): keep, or raise to 3?
3. Where the page goes in the menu (it is in the footer's About group only; the header menu is pinned by WP-86/117).
4. Index the page in search engines (it is indexed unfiltered now, like the other lists; filtered views are noindex)?
