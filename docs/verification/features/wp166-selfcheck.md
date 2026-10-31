# WP-166 self-check: consortium-first front, honest market shares, USI check, partner roles (owner, 31 Oct 2026)

Branch `wp-wp166` from `integration` 2e2af81 (= production). Test copy `D:\DEFENCEGATE TESTS\wp166\` (Postgres `dgate-wp166`, port
56167, removed at the end). No migration. Production read-only: five SELECT/EXPLAIN batches, read-only transactions, timeout 30 s,
none between 15:50 and 16:30 UTC. No price, no person named, no contact field anywhere.

## 1. Front page and navigation around "assemble a consortium for a call"

- Home (`web/app/(public)/page.tsx`): a new section right under the search, "Build a consortium for an EU defence call", four step
  cards through existing pages: Find a call (`/funding`, with the open-call count), Check eligibility (`/check`; each call page
  carries its own check), See the gaps (`/networks/consortium-gaps`), Find partners (`/organisations`). Under them, the
  Ukraine flags in sight with the live counts of the lists they open: calls open to Ukrainian participants (`/funding?ukraine=true`),
  Ukraine Support Instrument calls (`/funding?programme=EDIP-USI`), Ukraine partners. Each step is one link card: hover and focus
  change its edge and tint, never an underline (card rule).
- Funding before tenders, tenders kept: the first tile's actions are Browse funding, then Browse tenders; "Funding closing soon"
  comes before "Tenders closing soon"; a funding row says "Open to Ukrainian participants" where the call is flagged.
- The owner's headline and lead, the tiles, the trust line, the digest and the FAQ are unchanged; titles, canonical and sitemap
  unchanged; no page removed.
- Menu (`web/lib/nav.ts`): "Tenders & funding" now lists Funding, Tenders, **Contracts ending soon** (`/tenders/ending`), Buyers,
  Market overview, in the desktop dropdown, the phone menu and the footer group (all read `MAIN_NAV`). Not a top-level item: the bar
  keeps its four items.

Pins moved on purpose (each marked WP-166 in the file):
- `web/lib/wp86.check.ts`: the children of Tenders & funding (now `/funding`, `/tenders`, `/tenders/ending`, `/buyers`, `/market`),
  plus a new assertion that `/tenders/ending` is no top-level item.
- `web/e2e/wp86.spec.ts`: the links the Tenders & funding button opens.
- `web/e2e/wp117.spec.ts`: the first tile's action order (`/funding`, `/tenders`); the first keyboard stop after the search is the
  first step card (was the first tile action); at 375 px the tenders list stands under the funding list (was the reverse).
- `web/e2e/wp86.spec.ts` (home), `web/e2e/ux.spec.ts` (U15), `web/e2e/wp150.spec.ts`: "the three tiles on the first screen"
  (WP-117/WP-150) became "the consortium path on the first screen, the tiles right after it": on a 1440 x 900 desktop the four
  steps end within the first screen (checked in wp150 and wp166 specs); the tiles still come before the closing lists.
- `web/e2e/routes.spec.ts` ("a tender detail page"): the first `/tenders/...` link of the page is now the menu's
  `/tenders/ending`, so the locator skips it.
- `backend/tests/integration/test_wp32.py`: `PARTNER_KEYS` gains `roles` (item 4).

## 2. Honest market shares

- One text constant `SHARE_NOTE` and the few-contracts rule `FEW_AWARDS` / `fewAwardsLine` in `web/lib/coverage-copy.ts`; one
  component `web/components/dg/share-note.tsx` (`ShareNote`). The note: the figures come from the award notices of TED and the national
  portals we read, which cover only part of defence spending (TED holds about a tenth of EU defence spending, ECIPE Policy Brief
  20/2025); shares are indicative.
- Where it is shown: company page "Where it wins" (with the company's contract count) and "Its share" (`components/dg/competition.tsx`,
  so the company report has it too), the competitors page, the supplier map (`/suppliers`), company signals (`/signals`), the market
  page ("Contract values awarded"), and the supplier report's sections 2 and 3 (`components/sell-report/report.tsx`, with the
  procurement and awarded-contract counts).
- Very few awards: below 10 contracts (the threshold the signals already use for "a few contracts one by one",
  `backend/dgate/signals.py` `SMALL_BELOW`) the note adds "Counted from N contracts only: too few for a share to say much"; each row
  of "Its share" whose slice has fewer than 10 contracts says the same under its label.

## 3. USI check (read-only)

Findings in `docs/verification/features/wp166-usi-check.md`. In short: both USI calls are in our data with the right titles,
deadlines and Ukraine flag and quote. The research's "first call closed 13 October" is wrong: the portal extended it to 10 November
2026 (our data has 10 November). Budgets are the portal's voted EU budget figures (180 and 80 million), the call documents state
totals of 184.5 and 82 million: partial. Ukraine's EDF association: the Commission (DG DEFIS) announced on 16 October 2026 that it
has come into force; our site still says "not confirmed": out of date, not a reader bug, left for a follow-up package. No code or
data fix, no ops module.

## 4. Partner suggestions: past roles and Ukrainian organisations

- Backend: `backend/dgate/partners.py` `past_roles(conn, heads)`: for each live organisation, the projects per role over all its
  participations in CORDIS and the EDF factsheets (coordinator, participant, thirdParty, other = partner / associated partner /
  international partner), through `merged_into`, active participations only, suppressed and natural-person rows left out. Used by
  `GET /v1/funding/{slug}/partners` (`partners[].roles`) and `GET /v1/analytics/consortium-gaps` (`items[].roles`,
  `backend/dgate/network_api.py`). Organisation facts only.
  Cost on production (EXPLAIN ANALYZE, read-only): the 100 organisations with the most participations (76,696 rows) in 1.26 s;
  a page of 20 suggestions is a fraction of that; both answers are cached (10 and 15 minutes).
- Web: `web/components/funding/partner-suggestions.tsx`: each suggestion gets "Past roles, all its projects: coordinator in 3
  projects, participant in 9, third party in 1." (`lib/networks.ts` `pastRolesWords`), a "Ukrainian organisation" tag for country UA
  (`UA_MARK`), and a toggle "Ukrainian organisations only (N)" (the server's country filter, `aria-pressed`); where the area has none
  (and the country list is whole) it says so. Consortium gaps page: the same roles line and UA tag per organisation, and a link to
  the Ukrainian organisations (Ukraine partners) when the gap country is Ukraine.

## Tests

- Backend: `tests/integration/test_wp166.py` (roles on suggestions, all projects counted, inactive ones not, UA filter; roles on
  gap organisations with a merged row). Results below.
- Web: `lib/wp166.check.ts` (roles words, note and few-contracts line, menu place); `e2e/wp166.spec.ts` (home path order and
  links, Ukraine counts equal the list's, funding before tenders, hover and focus without underline in light and dark at 1440 px,
  320 px without horizontal scroll, menu desktop and phone with Contracts ending soon, partner roles / UA mark / UA filter, gap
  roles); `e2e/wp166-api.spec.ts` (fake API: the share note on the company page and the competitors page).

Results in the test copy:
- Backend: ruff clean; unit 4207 passed; integration 1660 passed (Postgres 17, `dgate-wp166`).
- Web: tsc clean; lib checks all ok (wp166 and wp86 included); production build ok. Playwright, desktop + mobile-375 + both
  fake-API projects, first run over 27 specs (home, menu, funding, networks, suppliers, signals, report, contracts ending): 441
  passed, 9 failed (the four pins above and a wrong locator in wp166-api), all fixed; rerun of the 18 affected specs after the fixes
  and the compact step cards: 310 passed, 0 failed (36 skipped by their own width rules).

## Screenshots (`D:\DEFENCEGATE TESTS\wp166\shots\`)

- `home-1280.png`, `home-375.png`, `home-1440-light.png`, `home-1440-dark.png`: the consortium path under the search, the Ukraine line,
  funding before tenders.
- `nav-desktop-1440.png` (Tenders & funding open: Funding, Tenders, Contracts ending soon, Buyers, Market overview),
  `nav-mobile-375.png`.
- `call-partner-roles-1280.png`, `call-partner-roles-375.png`: suggestions with past roles, the Ukrainian tag and the filter.
- `company-share-note-1280.png`, `company-share-note-375.png`: Where it wins and Its share with the note (fake API company).

## Files touched outside the package's own

`web/lib/nav.ts` (menu), `web/playwright.config.ts` (the fake-API spec list gains `wp166-api.spec.ts`), `web/lib/types.ts` and
`web/lib/networks-types.ts` (optional `roles`), `web/lib/mock/networks.ts` (mock roles). Nothing of WP-163 (backend ops/migrate).

## Left out / open

- Ukraine's EDF association wording (USI check row 9): a follow-up package, owner's decision on the 28 closed EDF calls' flag.
- Call budgets: portal figure or call-document total (USI check rows 4 and 7).
- Past roles are not on the organisations directory cards (`/organisations`); the organisation page already lists its projects
  with roles.
