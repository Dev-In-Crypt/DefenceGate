# WP-86 self-check: menu, site search, home, Check my company (22 October 2026)

Branch `wp-wp86` from `integration` (1ce494d). Task: section 1 of the UX audit of 22 October 2026
(`D:\DEFENCEGATE TESTS\ux-oct22\SUMMARY.md`), owner approved the same day ("fix everything that can be fixed; priorities: usability,
completeness, correctness"). No deploy, no push, no migration, no production read or write, no secret, no model call. Not touched (WP-87's
areas): backend counts, calendar and feeds, tender and buyer pages, list defaults; nor /privacy, /terms.

## 1. The menu (header, phone menu, footer)

`web/lib/nav.ts` (new) is the one list; the header (`components/dg/header-bar.tsx`, a client component) and the footer
(`components/dg/footer.tsx`, a server component) both read it, so they cannot drift.

| Header item | Opens | Small menu |
|---|---|---|
| Tenders | /tenders | Tenders, Market overview |
| Funding | /funding | |
| Buyers | /buyers | |
| Companies | /companies (redirect to /suppliers) | Companies, Ukraine partners, Consortium gaps |
| Check my company | /check (new) | Check my company, Requirements, Regulatory tracker |
| What's new | (a button, no page) | What changed, Weekly digest, Deadline calendar |
| search field | /search (new) | |

Footer: Directory (Tenders, Market overview, Funding, Buyers), Companies, Check my company, What's new (the header's groups, same
links), About the data (Source status, Methodology, Where the data runs, Glossary, CPV finder), About (About DefenceGate, Pricing,
Opportunity pack, Alerts (not open yet)); legal line: Privacy notice, Terms of use, Imprint. Pricing and the pack left the header.

**Every label is the h1 of its page** (e2e `wp86.spec.ts` visits every header and footer link and compares). To get there:

| Page | h1 before | h1 now | or label changed |
|---|---|---|---|
| /funding | Funding calls | Funding | |
| /suppliers, /organisations | Defence supplier map / Organisations in funded projects | Companies (two tabs) | |
| /networks/ukraine-partners | Who partners with Ukrainian organisations | Ukraine partners | |
| /networks/consortium-gaps | Gaps in consortia | Consortium gaps | |
| /requirements | Requirements for EU defence programmes | Requirements | |
| /methodology | How we collect and classify | Methodology | |
| /market | Market overview | (kept) | label Market -> Market overview |
| /about, /privacy, /terms | About DefenceGate, Privacy notice, Terms of use | (kept; /privacy and /terms not edited) | labels follow the h1 |
| /alerts | Alerts and saved searches | (kept) | label stays "Alerts (not open yet)" as instructed: the one exception |

Page titles (`<title>`, meta) are unchanged. Breadcrumbs: Home > Companies > Won contracts / In EU-funded projects; the readiness
pages sit under Home > Check my company.

Phone (below 1280 px): the menu starts with the search field (focus goes there), then every item: a group's page, then each of its
other pages (before, a child with the parent's address was hidden: Organisations, Source status); What's new is a heading over its
three links. Every row is 44 px (e2e). Footer links are 44 px on a phone, 32 px from lg.

## 2. Companies, Check my company, old addresses

- Companies (`components/dg/companies-tabs.tsx`): h1 "Companies", a tab row "Won contracts" (/suppliers) and "In EU-funded
  projects" (/organisations), one sentence per tab, then "Also: Ukraine partners · Consortium gaps". Each tab is the list it was,
  at its own address, so every filter, page and link still works; the long leads moved out (the supplier map's coverage card,
  right under it, keeps the "TED holds only part" caveat). `ListPage` got an optional `head` slot for the tabs.
- `/companies` redirects (307, not permanent: which tab opens first may change) to /suppliers (`next.config.ts`).
- Check my company (`app/(public)/check/page.tsx`): "What do you want?" with two answers, EU defence funding -> /readiness (the
  readiness check) and Become a supplier to defence buyers -> /readiness/supplier; a line to the Spain automotive landing; then
  Requirements and Regulatory tracker. Links only: works without script, keeps nothing, no new privacy wording.
- Old addresses: none removed. /suppliers, /organisations, /networks/*, /readiness, /readiness/supplier,
  /readiness/spain-automotive, /market, /data, /methodology, /digest, /pricing, /pack, /alerts, /glossary, /cpv answer 200 (e2e).
- Sitemap: /check added; /companies (a redirect) and /search (noindex) not listed (e2e).

## 3. Site search

Backend `backend/dgate/search.py` (new), `GET /v1/search?q=&limit=5`, contract in `docs/design/API_CONTRACT.md` (WP-86 section).
Each group is the list endpoint function itself, called with the list's opening filters and `q`, `pageSize=5`: no search engine,
no new index, the lists' own caches. So a group's total is what its "see all" link opens (integration test compares every group
with its list for five queries). The organisation directory opens on the defence programmes on the site (`web/lib/networks.ts`),
so its group asks the same (`OPENS_ON`). Groups run one after another on the request's one connection inside 4.5 s: each statement
gets what is left less 0.3 s per group still to come (`SET LOCAL statement_timeout` in a savepoint); a group out of time answers
`error: "slow"` and the rest still answer (integration test with a 3 s sleeping group). Rate limit 15 tokens (the five separate
searches cost 22; unit test).

Web: `web/lib/search.ts` (the call; without the API the demo lists' own answers), `components/dg/site-search.tsx` (one GET form:
compact in the header and phone menu, full on home and /search), `app/(public)/search/page.tsx`: groups Tenders, Funding, Buyers,
Companies (Won contracts, In EU-funded projects), top 5 each with "See all N ..." to `/<list>?q=`; "No ... match" per group; a
search the service did not answer says so and links the lists. Noindex.

### Timings (local, synthetic data, list cache off)

`D:\DEFENCEGATE TESTS\wp86\probe\perf_search.py`, throwaway database `perf` in `dgate-wp86`: the WP-85 data set (330,000 defence
and 200,000 civil notices, 70,000 award rows, 11,500 winners) plus 3,000 open notices with a deadline ahead ("radar", "drone",
"Rheinmetall" in some titles), Rheinmetall / Indra / BAAINBw names on winners and a buyer, 200,000 organisations in the network
(5 % EDF), 2,000 calls. Five runs each through the API (TestClient), median (range), and each list alone:

| q | /v1/search | tenders | funding | buyers | suppliers | organisations | groups found |
|---|---|---|---|---|---|---|---|
| Rheinmetall | 1.10 s (1.09-1.15) | 0.13 | 0.02 | 0.20 | 0.68 | 0.01 | tenders 23, suppliers 19, organisations 40 |
| BAAINBw | 0.70 s (0.69-0.74) | 0.05 | 0.02 | 0.20 | 0.40 | 0.00 | buyers 1 |
| Indra | 0.93 s (0.91-0.95) | 0.01 | 0.02 | 0.19 | 0.61 | 0.00 | suppliers 10, organisations 40 |
| drone | 0.80 s (0.78-0.81) | 0.07 | 0.04 | 0.20 | 0.39 | 0.00 | tenders 22, funding 30 |
| radar | 0.78 s (0.77-0.78) | 0.03 | 0.02 | 0.19 | 0.40 | 0.01 | tenders 40, funding 24, organisations 40 |

The supplier name search is most of it (the same statement as `/suppliers?q=`, WP-85 measured 1.5 s for a broad name on its data).
WP-80 measured production at 1.5-3x local times: 2-3.5 s at worst, inside the 4.5 s budget; the budget cuts a slow group rather
than the answer. Production's real numbers (and whether "BAAINBw" is in the stored buyer name) are to be confirmed after deploy.

## 4. Home

- One sentence for whom: "For suppliers, bid teams and advisers: notices from TED and national portals, each linked to its
  original source, with changes to dates, values and status kept." (the earlier lead with the audience in front; the four audience
  cards it replaces are gone, their content is the sentence.)
- Three task buttons (nav "Start here"): Find a tender (/tenders), Find funding (/funding), I make parts: who buys and who wins my
  products? (/readiness/spain-automotive); the site search under them; "Free to browse. No account needed."
- Removed: the tenders finder (country, CPV, word: the filters are on /tenders), "What is in here" (the scope tiles; the
  explanation stays on /tenders, WP-87/88 handle its wording), "Built for the people who bid, advise and write". Kept: the figures,
  the examples line, the CPV finder link, Tenders closing next and Funding calls closing soon (moved up, right under the hero), the
  three parts (links now "Companies in EU-funded projects" and "Check my company"), What changed, Why DefenceGate, How it works,
  Please note, Questions. No new claim.
- Height (demo build): desktop 5,718 -> 4,849 px; phone 12,552 -> 10,622 px. On a phone the three tasks and the search are on the
  first screen (e2e checks the search's bottom edge is within the viewport at 375 x 812).

## 5. Tests

Rewritten for the new structure (owner-approved; none deleted or skipped):

- `e2e/routes.spec.ts`: home finder tests -> the tasks and the site search, "Find a tender" then the /tenders filters; "the header
  has Market, Methodology under Data" -> Market overview under Tenders, Methodology in the footer's About the data; the dash test
  reads the hero's figures (the scope tiles left home); /methodology h1.
- `e2e/ux.spec.ts`: U15 (the three parts link Check my company; they stand after the closing lists and before Why DefenceGate),
  U16 (Companies: more pages; the phone menu focuses the search field), h1 of the renamed pages.
- `e2e/fit.spec.ts` (three parts link), `e2e/wp46.spec.ts` (hero: the search in the copy column; footer <= 400 px and its new
  labels), `e2e/wp48.spec.ts` ("Find a tender" under the lead), `e2e/wp56.spec.ts` C5 (groups by `data-group`, Tenders' menu in
  Directory, every header link in the footer), `e2e/wp58.spec.ts` (Escape in the Companies menu), `e2e/wp68.spec.ts` (Spain
  automotive linked from /check and home instead of the Readiness menu), `e2e/wp73.spec.ts`, `networks.spec.ts`,
  `suppliers.spec.ts`, `readiness.spec.ts`, `wp45/47/57/85.spec.ts` (the renamed h1s).

New: `e2e/wp86.spec.ts` (labels = h1 for every header and footer link; header items and footer groups; phone menu with every item
and 44 px targets; search groups and "see all"; header and home search; home tasks above the fold; Check my company routing; old
addresses, /companies redirect and sitemap), `lib/wp86.check.ts` (menu structure), `backend/tests/integration/test_search.py`
(3 tests), `test_hardening.py::test_the_site_search_is_priced_like_the_five_list_searches_it_runs`.

Local, `D:\DEFENCEGATE TESTS\wp86` (own venv, Python 3.11; Postgres 17 container `dgate-wp86` on 55486; TZ=UTC; the web mock env of
`web.yml`; E2E_PORT 3086; Playwright 4 workers), on the final code:

| Check | Result |
|---|---|
| ruff | All checks passed |
| unit (`pytest`) | **3272 passed**, 1218 deselected |
| integration (`pytest -m integration`) | **1218 passed**, 0 failed (10 min 46 s) |
| `tsc --noEmit` | exit 0 |
| `npm run check` | all ok (incl. new `wp86.check.ts`) |
| `next build` (mock) | exit 0 (the usual Windows "failed to copy traced files" warning of the standalone output, as in WP-85) |
| Playwright, desktop + 375 px | **544 passed, 50 skipped** (the fake-API group as before, plus 3 width-specific tests of wp86), 0 failed |

Screenshots: `docs/verification/product/wp86/` (before-*/after-*: home, menu open, Companies tabs, Check my company / readiness,
search results; desktop 1280 and phone 375).

## 6. Open decisions and limits

- **Funding label/h1**: the h1 of /funding is now "Funding" (the menu's word); "Funding calls" was more descriptive. Reversible in one
  line if the owner prefers "Funding calls" for both.
- **/alerts** keeps its label "Alerts (not open yet)" (instruction), so it is the one footer label that is not its h1.
- **Footer height**: six groups and the legal line make the footer up to about 370 px from lg (limit in `wp46.spec.ts` 360 -> 400).
- **List defaults belong to WP-87**: the search follows the API's defaults (and the organisation directory's opening filter). If
  WP-87 changes a list's default on the site only (not in the API), `search.OPENS_ON` must follow, or a group's count and its "see all"
  list differ.
- The search is word-for-word the lists' searches: tenders by title (original language) and buyer name, buyers by name, companies by
  name, funding by call text. "BAAINBw" finds the buyer only if its stored name holds that word; synonyms are out of scope (audit
  sections 5 and 6).
- Timings are local on synthetic data; production confirmation after deploy (read-only): `/v1/search?q=Rheinmetall` and `?q=radar`
  with the list cache cold.
