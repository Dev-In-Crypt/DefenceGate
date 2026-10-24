# WP-98 self-check: search (persona round of 23 October 2026, section C, items 1 to 4)

Branch `wp-wp98` from `wp-wp97` (58d6bd9). Scope after the coordinator's split: items 1 to 4 of section C of
`D:\DEFENCEGATE TESTS\ux-oct23\SUMMARY.md` (multi-word search, words of other languages, buyer abbreviations, global search
speed and the `q=drone&status=all` 503). Items 5 to 7 (presets, sort by code and supplier value column, coverage line and TED-only
view) are WP-98b's; nothing here touches `CPV_PRESETS`, a coverage constant or the buyer/supplier sorts. Not changed: WP-88 copy
rules, WP-93 verdicts, WP-95 value logic, WP-97 report logic. One migration, **0111**. No deploy, no push, no production read or
write, no external call.

## 1. What changed

| # | Finding (persona) | Change | Test |
|---|---|---|---|
| 1 | "spare parts" 0 in Germany, "spare" 1 (p03) | The tender search already needed every word, in any order; what failed was a run of words against the English titles of the notice's codes ("parts" alone names too many codes and was read on titles only). `cpv_labels.codes_for_words`: the codes whose title has every word; used for a typed run of words and for the whole query. Buyers (every word in the name of the family's head or of a member), funding (`textsearch`) and companies were already every word, any order; companies now every word within one name (canonical, or one name it was published under). | unit `test_wp98.py::test_a_run_of_words_...`; integration `test_wp98.py::test_every_word_in_any_order_...`, `::test_the_company_search_...` |
| 2 | fardamento 0, Drohnen, brandstof, amunicja, vêtements, night vision 0 (p02, p03, p04, p06, p08, p09) | One keyword map, `web/lib/data/search-terms.json` = `backend/dgate/data/search-terms.json` (byte-identical, unit test), no model: 8 groups (uniforms/footwear/clothing, spare and machined parts, drones, fuel, logistics, ammunition/explosives/pyrotechnics, night vision, body armour) with terms in EN, PT, ES, FR, DE, PL, NL (and IT where obvious) and each group's CPV prefixes (all under codes of the vocabulary). `search_terms.expand`: a run of words that is a term is one slot any term of its group fills; the typed words keep their old reading (titles, buyer name, code titles), the group's other terms are matched as phrases in the titles only. Applied in `_tender_filters`, so the list, export, scope counts, calendar, change feed and the global search's tender part read it alike. `/v1/tenders` and `/v1/search` return `alsoSearched` and `searchGroups`; /tenders and /search say "Also searched, the same product in other languages: ..." and, with nothing found, link "Tenders under the product codes of <group> (CPV ...)" (the list's own CPV filter, other filters kept). The demo data reads the same map (`lib/search-terms.ts`). The search box hint says so. | unit: one case per language and group (48); `wp98.check.ts`; integration: one case per language (13); `wp98.spec.ts` |
| 3 | BAAINBw, DMO, DGA, JAE MALE; the BE "Ministère de la Défense" never shown (p03, p06, p09) | `buyers` in the map: an abbreviation (folded, a space inside optional) also finds the families whose head or member name holds every word of a full name; those families are found first on their own (trigram index of 0111) and listed first. Without an abbreviation, a buyer whose name is the search itself comes first, then most tenders. `/v1/search` says `buyerNamed` when its first buyer is the one the words name, and the search page then shows that buyer's open tenders line (WP-96's) however many buyers matched. | unit `test_an_abbreviation_names_its_buyer`; integration `test_an_abbreviation_finds_the_buyer_and_it_comes_first` |
| 4 | "took too long" on companies/buyers, 4-8 s; `q=drone&status=all` 503 (p02, p03, p04, p06, p08, p09) | Companies: the names are matched first (`org.id = ANY(ARRAY(...))`, an InitPlan over new trigram indexes on `dg_fold(organisation.canonical_name)` and `dg_fold(award.name_as_stated)`, migration 0111) and the award set is read for those companies only: 1.2 s to 0.03 s. Tender list: a searched part whose order an index could walk (`status=all`'s closed part, closed, planned, sorted lists) is first counted up to 3,000 in a 0.6 s box (`_few`); when that small, it is read by its matches and sorted (`(o.id IS NULL), <order>`), and the count is reused as its total. A rare word over every status walked the deadline index through most closed notices to fill a page (0.53 s locally for 686 matches; the walk grows with the archive and with load), the likeliest cause of the production 503; a common word keeps the index walk. Synonym terms as regular expressions in chunks of 4 per column (one alternation of 11 terms made pg_trgm hand back 12,966 candidates for 1,306 matches; 4: exact), titles only. The list caches (`cache_list`, 5 min) already cover each part of the global search; no extra cache was added (a whole-search cache would keep a part's "slow" for 5 minutes). | integration `test_a_rare_word_over_every_status_is_read_by_its_matches` (the closed part sorted, the order and totals page after page, a common word read along the index); `test_search.py` unchanged and green |

## 2. Timings

Local, no production data: a synthetic archive of production size (`D:\DEFENCEGATE TESTS\wp98\perf\gen.py`: 357,000 notices, 300,035
organisations, 95,818 award rows, the named buyer families; word frequencies Zipf-like so that "drone" is in 311 English titles and
3 open notices, as production's 3). Postgres 17 in Docker, the API through TestClient, `statement_timeout` 5 s (the API role's), list
caches off, first call of each (`perf/timing.py`, results `perf/before.json`, `perf/after.json`, `perf/after-warmbase.json`). "Before"
is 58d6bd9 on the same data. Seconds.

Global search, each part (tenders / buyers / companies-won / whole search; funding and EU-project organisations under 0.03 s in all
rows, the synthetic set has no network data):

| q | before | after | after, buyer aggregate held (as production: worker snapshot + 5 min) |
|---|---|---|---|
| Ministère de la Défense | 0.34 / 1.50 / 1.19 / 3.58 | 0.28 / 1.31 / 0.03 / 1.69 | 0.25 / 0.77 / 0.03 |
| Rheinmetall | 0.12 / 1.34 / 0.53 / 1.91 | 0.11 / 1.31 / 0.05 / 1.42 | 0.11 / 0.73 / 0.05 |
| Thales | 0.11 / 1.80 / 1.28 / 4.28 (companies "slow") | 0.11 / 1.28 / 0.06 / 1.45 | 0.11 / 0.73 / 0.06 |
| fardamento | 0.25 / 1.22 / 1.19 / 3.56 | 1.70 / 1.28 / 0.02 / 2.99 | 1.94 / 0.83 / 0.02 |
| BAAINBw | 0.27 / 5.62 / 1.19 / 2.81 | 0.26 / 1.30 / 0.03 / 1.62 | 0.26 / 0.81 / 0.03 |
| drone | 0.56 / 1.36 / 1.22 / 2.83 | 1.17 / 1.34 / 0.01 / 2.53 | 1.20 / 0.70 / 0.02 |
| spare parts | 0.55 / 1.56 / 1.23 / 3.30 | 2.03 / 1.25 / 0.03 / 3.36 | 2.09 / 0.73 / 0.03 |
| DMO | 0.20 / 1.27 / 1.20 / 2.75 | 0.19 / 1.38 / 0.05 / 1.97 | 0.20 / 0.74 / 0.05 |

With the parts in the list caches the whole search answers in 0.05 to 0.2 s. No part answered "slow" after the change.

Tender lists (before / after):

| request | before | after |
|---|---|---|
| `/v1/tenders?q=drone&status=all` | 0.81 (689 notices) | 2.62 (1,469: Drohne, dron, unmanned ... now count) |
| `/v1/tenders?q=drone` | 0.17 (3) | 1.17 (9) |
| `/v1/tenders?q=spare parts&country=DE&status=all` | 1.03 | 2.16 |
| `/v1/tenders?q=fardamento&status=all` | 0.88 | 4.72 (see below) |
| `/v1/tenders/scope-counts?q=drone&status=all` | 0.47 | 1.19 |
| `/v1/suppliers` | 0.36 | 0.38 |

What the numbers say: the company part is fixed (1.2 s to 0.03 s, the "took too long" of p02/p03/p06/p09); the buyer part is the
buyer aggregate (`buyer_base`), 1.3 s cold here and 0.7 to 0.8 s once held, which production holds; the abbreviations cost nothing
extra once their families are looked up on their own (DMO 1.67 s to 0.77 s with that change). The tender part got slower where the
words now mean more: every extra term is one more `dg_fold` of each candidate title (34 µs a call, measured), and a synonym search
reads 3 to 20 times the notices. All parts are under 2 s except the tender part of "spare parts" (2.03 s; its group has 17 terms) and
the `status=all` list of "fardamento", whose group matches "uniform" in 64,541 synthetic titles (the generator's English word list is
too small; on production "uniform" is far rarer): its rest part runs into the existing count time boxes (two of 1.2 s) and still
answers well inside 5 s. **The production 503 was not reproduced locally** (0.81 s before): the fix removes the index walk that is the
likeliest cause; it should be checked on the server after the deploy (`/v1/tenders?q=drone&status=all`, warm and cold).

## 3. Tests

Local, `D:\DEFENCEGATE TESTS\wp98` (own venv, Python 3.11; Postgres 17 container `dgate-wp98` on 55498, the timing database `dgperf`
beside the test database; TZ=UTC; web mock env of `web.yml`; E2E_PORT 3098; Playwright 4 workers), final code:

| Check | Result | Time |
|---|---|---|
| ruff | All checks passed | |
| unit (`pytest`) | **3627 passed**, 1306 deselected (63 new in `test_wp98.py`) | 35 s |
| integration (`pytest -m integration`) | **1306 passed**, 0 failed (18 new in `test_wp98.py`) | 12 min 51 s |
| `tsc --noEmit` | exit 0 | 3 s |
| `npm run check` (`scripts/run-checks.mjs`, with the new `wp98.check.ts`) | all ok | 198 s |
| `next build` (mock) | exit 0 | 55 s |
| Playwright, desktop + 375 px | **726 passed, 56 skipped** (as before), 0 failed | 2 min 41 s |

An earlier full Playwright run failed the new spec (two links of the same name on a card; the card's id is its heading's) and, once
each, `wp49.spec.ts` "a radio applies at once" and `wp80.spec.ts` on 375 px (3 s time boxes under load); both passed on the rerun and in
the final run above. An earlier integration run of `test_search.py` failed on an exact dict comparison of a group once a `firstNamed`
field was added to every group: the field became `buyerNamed` on the search answer itself and the test is unchanged. No test was
deleted, skipped or weakened.

New: `backend/dgate/search_terms.py`, `backend/dgate/data/search-terms.json`, `backend/migrations/0111_supplier_name_search.sql`,
`backend/tests/unit/test_wp98.py`, `backend/tests/integration/test_wp98.py`, `web/lib/data/search-terms.json`, `web/lib/search-terms.ts`,
`web/lib/wp98.check.ts`, `web/components/tenders/search-terms-note.tsx`, `web/e2e/wp98.spec.ts`. Changed: `tenders.py` (search SQL,
`_few`, buyer search order, `alsoSearched`/`searchGroups`), `cpv_labels.py`, `suppliers.py` (name search), `search.py`, the /tenders
and /search pages, `lib/search.ts`, `lib/types.ts`, `lib/mock/tenders.ts`, the tender search hint, `list-page.tsx` (empty text may
hold a link).

### After merging integration (b480e8e, then f395b8f: WP-100, WP-98b, WP-99)

Two conflicts, both kept: `list_buyers` order (WP-98b's `sort=cpv` by the count under the codes when asked; otherwise WP-98's named
buyer first, then most tenders) and the tender search hint (WP-98's sentence, WP-98b's preset rows below it). `_tender_filters` merged
without conflict (WP-100's export parameters are outside it). Synonyms: WP-99's funding table (`textsearch.SYNONYMS`, ASAP -> EDIP) and
this map are kept apart on purpose: the funding rows are funding ideas over a few hundred English calls ("logistics" -> supply,
mobility), which would be wrong for tender titles, and the tender map holds product words of seven languages; the one shared idea,
drone, is a superset here. Migrations: 0111 (this), 0112 (WP-99). Runs on the merged code: ruff clean; unit **3643 passed**;
integration **1316 passed**, 0 failed (11 min 37 s); tsc 0; lib checks all ok; next build 0; Playwright **761 passed, 57 skipped**,
0 failed (a first run beside the integration suite failed `digest.spec.ts` and `wp49.spec.ts` once each on time boxes; the rerun alone
passed everything).

## 4. Migration 0111

Two trigram GIN indexes, `organisation_name_fold` on `dg_fold(organisation.canonical_name)` and `award_name_fold` on
`dg_fold(award.name_as_stated)`. Additive, idempotent, no row written. On production create them `CONCURRENTLY` first (the statements
are in the file's header) so the migration is a no-op and takes no lock.

## 5. Open decisions for the owner

- **The keyword map** is ours: 8 groups, the terms and each group's codes. Say if a term is wrong for a language or a group should be
  added (helmets, tents, medical, IT, catering ...). A term is matched as the start of a word ("dron" finds drony, dronów, drone).
- **Synonyms read titles only**, not buyer names (the typed word still reads the buyer's name). A product word in another language
  rarely names a buyer, and over buyer names the short terms (UAV, UAS) cost 5 s.
- **Companies: every word within one name.** Before, one word could match the company's name and another a name it was published
  under; now all words must be in the same one. No case of the first kind is known.
- **Cost of synonyms**: a searched tender list costs about 1 to 2 s more for a word with a group (one more fold of each candidate title
  per term). A stored folded title column (one more column and index on `opportunity`, written by trigger, backfilled in batches)
  would make every title search several times cheaper; it is a table-wide write on production, so it is not done here.
- **The abbreviation list** holds BAAINBw, DMO, DGA, JAE MALE (and JAEMALE) and FMV; more are one JSON row each.
- **Production check** of `q=drone&status=all` after the deploy (the 503 was not reproduced locally).
