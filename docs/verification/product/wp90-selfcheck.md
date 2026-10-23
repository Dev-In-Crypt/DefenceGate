# WP-90 self-check: the analyst path (UX audit of 22 October 2026, section 5)

Branch `wp-wp90` from `integration` (6b719e1: WP-86 to WP-89 merged; integration's 05bbe60, the buyer list's two-step CPV filter,
merged in before the final runs). Persona Jonas: a German defence-electronics BD analyst who reads TED daily (audit dumps and
screenshots in `D:\DEFENCEGATE TESTS\ux-oct22\analyst\`). Owner priorities: usability, completeness, correctness. Not changed:
WP-87's numbers logic (every count below goes through `_tender_filters`, `_count` and the collapse rules as before), WP-88's copy
rules (one sentence before content, method collapsed, attribution lines on screen). **No migration** (0105/0106 are reserved on
other branches; none was needed: see 2 below). No deploy, no push, no production read or write, no secret, no model call.

## What WP-87 had already done (checked, not rebuilt)

/calendar, calendar.ics and /changes read the list's filters (q, country, cpv, scope, goods, dates, value) and refuse a parameter
they do not read (422); a filtered /tenders linked "Deadline calendar of this search" and "Changes of this search (Atom)";
calendar.ics states its 3,000 (API) and 5,000 (file) ceilings in X-WR-CALDESC and `x-dg-events`; the Atom subtitle says when its
2,400 entries cut the window. Missing were: one control, a webcal address, the status in the feed, the calendar's silent
three-years-ahead cut, and the filters below.

## 1. What changed, item by item

| # | Audit finding | Change | Test |
|---|---|---|---|
| 1 | Subscribe to the current selection; no silent cap | "Subscribe to this search" above the results on /tenders (`components/tenders/subscribe.tsx`, a native `details`, shown whatever the result count): "Add the deadlines to your calendar" (`webcal://<site>/calendar.ics?kind=tenders&...`), "Download the calendar file (.ics)", "Atom feed of new tenders and changes", built by `lib/analyst.ts subscription()` from exactly the list's filters (q, country, cpv, main code only, excluded codes, scope, goods, deadline and value range; the feed also the status, as of now). A Closed or Planned search has no calendar and says why. The ceilings are said under each link (3,000 tenders, deadlines more than three years ahead left out; 2,400 feed entries, 14 days) and in the files: calendar.ics now also names the open tenders it leaves out for a deadline more than three years ahead (`buildIcs` `longRunning`; it was the one silent cut). The Atom link left the export box (one control); the calendar page link stays there. Backend: `/v1/changes?status=` (the list's status over `_tender_filters`). | `wp90.check.ts` §1 (every parameter of both is one the feed reads; sort, page, size never travel); `test_wp90.py::test_the_calendar_and_the_change_feed_hold_exactly_the_lists_notices`; `wp90.spec.ts` (the .ics holds one event per listed tender and nothing else; the feed holds no notice outside the search) |
| 2 | Search by English CPV names and the TED English title | The archive stores TED's English title (`title_en`) and the list already searched it. New: a search word also matches the English title of one of the notice's own CPV codes (`dgate/cpv_labels.py`, the site's CPV 2008 file copied to `dgate/data/cpv-full.json`, held identical by a unit test): words of 3+ letters, a word in more than 200 titles ("services") read on titles only. SQL: `OR dgate_cpv_heads(o.cpv_codes) && codes` per word, the GIN index of migration 0099, so no new index. The box says: "Searches titles in the original language and in English where TED gives one, buyer names, and the English names of the notice's product codes." | `test_wp90.py::test_a_search_word_finds_...` (list, export, scope counts, calendar); `test_wp90.py` unit; `wp90.check.ts` §2; `wp90.spec.ts` search |
| 3 | CPV presets, main CPV only, exclude a code, more per page, deadline presets, buyer country open | `CPV_PRESETS` (`lib/analyst.ts`, one constant, official codes, titles checked against the vocabulary): Military electronics 35700000; Radar and sonar 35722000, 35723000, 38115000, 38113000; Communications 35710000, 32000000; Vehicles and parts 35400000, 34100000, 34300000; Ammunition and weapons 35300000; Uniforms and protective gear 35810000, 18100000. A preset is a link that sets the ordinary CPV filter to the codes' prefixes (editable, marked when active). "Main product code only" (`cpvMain=true`, the notice's first code), "Leave out product codes" (`notCpv`, e.g. 3511; the labels avoid the words "CPV code", which the CPV field's existing tests find by), "Tenders per page" 10/25/50 (`size`; the API's snapshots stay page size 10), "Next 7 / 14 / 30 days" (from today, UTC), "Buyer country" open by default on /tenders (folded on /buyers as before). Backend: `cpvMain`, `notCpv` on the list, export, scope counts, calendar and changes, and in saved searches. | `test_wp90.py::test_main_cpv_only_and_an_excluded_code`; `wp90.check.ts` §3; `wp90.spec.ts` presets; `wp47.spec.ts` (rewritten: the country group is open) |
| 4 | Tender page: commercial description, lots, documents, "Same notice in other sources" as a link, corrections collapsed | `GET /v1/tenders/{slug}` adds `subject`: the first sentence of the stored description (TED `description-lot`/`-proc`, BOAMP, TenderNed, ...), at most 300 characters, **null when it holds a figure with a physical unit (mm, km, MHz, kg ...), a specification word (specification, performance, tolerance, frequency, calibre, STANAG ...) or anything that reads as a contact** (`tenders.commercial_subject`): commercial market information only. Shown as "Subject, as the notice states it: ...". Lots were already shown ("Lots", `lot_count`). `documentsUrl`: the procurement documents' address where a source states it as such: Germany's Bekanntmachungsservice (BT-15), for the notice or its national twin ("Procurement documents" beside "View original"); TED's own document links are not stored, so a TED-only notice has none. "Same notice in other sources": each copy names its number and links its own page here ("Open this copy here", always working) beside the source's address when there is one. The version history lists the publisher's changes; our re-readings fold under "N corrections by DefenceGate, not changes by the publisher". | `test_wp90.py::test_the_tender_page_states_...`; unit `test_the_commercial_subject_...`; `wp90.spec.ts` tender page |
| 5 | Buyer page: top suppliers, website, CPV filter | New `GET /v1/buyers/{slug}/suppliers`: the supplier map's award set (`award_set.scope`: defence scope, three years, legal entities only, a TED+PLACSP twin once) under the buyer family, most contracts first, at most 10, with the totals; natural persons are never in it (`award_set.WINNERS`). The page: "Top suppliers of this buyer", one sentence, a table linking each supplier page, the attribution on screen, the method collapsed. A CPV field narrows the buyer's own open, planned and earlier tenders (the list's `/v1/tenders?buyer=&cpv=` reading, not the buyer list, so integration's two-step buyer-list form is untouched); the figures above stay all of its tenders and a line says how many are under the code. **Website: not stored** (no column holds an organisation's address; the notices' buyer URL is not mapped): not built. | `test_wp90.py::test_a_buyers_top_suppliers_...` (counts equal the supplier page's per-buyer count; a marked person is not named); `wp90.spec.ts` buyer page |
| 6 | Supplier page: prominent open-segment banner | The page's one line is now a marked banner: "Open segment only: TED (and Spain's PLACSP where it holds the company's awards) award notices of the last three years; the company's real volume is larger." Coverage and method stay in About this data. | `wp90.spec.ts` supplier page |
| 7 | /changes: change-type filter; digest "this week" link | `kind` = `new`, `amended`, `deadline`, `value` (value or currency), `status` (the API's `changes.of_kind`, over the lines the archive already lists); a "Kind of change" select on /changes; the counts stay the window's. `week` may be the week under way (`changes.week_end`: Monday to now; a week to come is 404; the digest still has no issue for it): the digest links "This week so far, in What changed" (`/changes?week=<this week>`), the page heads it "This week so far: 19 to 23 October 2026". | `test_wp90.py::test_the_change_list_by_kind_of_change`, `::test_the_week_under_way_...`; `test_wp52.py` (rewritten: the current week answers 200, a week to come 404); `wp52b.check.ts` (rewritten, same); `wp90.spec.ts` changes |
| 8 | Funding call page: deadline in Key facts | "Deadline" (or "Cut-off" for a rolling call) in Key facts, as the badge states it (date only, or a time in UTC). | `wp90.spec.ts` funding call |

## 2. The 5 s budget

No index migration: the CPV part of the search is an array overlap on the existing GIN index `opp_cpv_heads` (0099). Measured
locally on 300,000 synthetic defence notices (Postgres 17 in Docker, the API through TestClient, warm, list cache off):

| Request | List | Scope counts |
|---|---|---|
| `status=closed` (baseline) | 0.14 s | 0.16 s |
| `q=ersatzteile&status=closed` (title words, as before) | 1.07 s | 2.20 s |
| `q=radar&status=closed` (CPV titles, about a fifth of the rows) | 0.89 s | 1.58 s |
| `q=radar` (open) | 0.35 s | 0.28 s |
| `q=radar&status=all&page=20` | 1.27 s | 1.46 s |
| `notCpv=3511&status=closed` | 0.61 s | 1.12 s |
| `cpv=357&status=closed` (baseline for a code filter) | 0.52 s | 0.96 s |

A CPV-title word costs what a title word costs; the counts keep their 1.2 s time boxes. Production is larger (357,000 notices) and
was not touched; the API's 5 s statement timeout still bounds every query.

## 3. Tests

Local, `D:\DEFENCEGATE TESTS\wp90` (own venv, Python 3.11; Postgres 17 container `dgate-wp90` on 55490; TZ=UTC; web mock env of
`web.yml`; E2E_PORT 3090; Playwright 4 workers), final code (after the merge of integration):

| Check | Result | Time |
|---|---|---|
| ruff | All checks passed | |
| unit (`pytest`) | **3298 passed**, 1242 deselected (15 new in `test_wp90.py`) | 21 s |
| integration (`pytest -m integration`) | **1242 passed**, 0 failed (7 new in `test_wp90.py`) | 9 min 10 s |
| `tsc --noEmit` | exit 0 | 4 s |
| `npm run check` (`scripts/run-checks.mjs`, 42 files with the new `wp90.check.ts`) | all ok | 106 s |
| `next build` (mock) | exit 0 | 39 s |
| Playwright, desktop + 375 px | **654 passed, 56 skipped** (the fake-API group and width-specific tests, as before), 0 failed | 2 min 20 s |

An earlier full integration run failed one test, `test_tender_export.py::test_a_long_closed_result_pages_...`: it calls
`export_tenders` as a plain function, so the new filters arrived as their `Query(...)` defaults. `_tender_filters` now reads a
non-string `notCpv` and a non-`True` `cpvMain` as not set (one guard for every caller, accounts' saved searches included); the run
above is after that fix. An earlier web run failed `routes.spec.ts` (`getByLabel('CPV code')` matched the new fields too): the new
fields are labelled "Main product code only" and "Leave out product codes".

Rewritten (owner-approved changes of behaviour or visible text; none deleted or skipped): `test_wp52.py` (the week under way is
listed up to now instead of 404), `wp52b.check.ts` (the same in the demo data), `wp47.spec.ts` (the Buyer country group is open
on /tenders), `wp87.spec.ts` (the filtered list's feed link is the Subscribe control's, with `status=open`).

New: `backend/tests/unit/test_wp90.py`, `backend/tests/integration/test_wp90.py`, `web/lib/wp90.check.ts`, `web/e2e/wp90.spec.ts`
(9 tests x 2 widths).

Screenshots, `docs/verification/product/wp90/` (demo data, desktop 1280 and 375 px, written by `wp90.spec.ts` with WP90_SHOTS):
`tenders-subscribe`, `tenders-presets`, `tender-subject`, `tender-corrections`, `buyer-top-suppliers`, `changes-kind`.

## 4. Open decisions for the owner

- **Serving one sentence of the description.** The archive held the notices' descriptions and served none (`api.py` whitelisted
  them out). `subject` now serves the first sentence where it passes the commercial filter (no unit figures, no specification
  words, no contact, e-mails redacted). The filter is a word list: a technical sentence without those words would pass, and a
  plain commercial one with "5 m" would be dropped. Confirm the rule, or ask for it to be off.
- **The feed of a search carries its status.** The Atom of "Open" holds what is open today, so a notice that closed or was
  cancelled drops out of it (its last change with it). The alternative is a feed of every status for the same filters.
- **Organisation website**: not stored; it would need a source mapping (TED `buyer-internet-address` and the national
  equivalents) and a migration. Not built.
- **TED procurement-document links**: TED's `document-url-lot` is not mapped, so only Bekanntmachungsservice notices (and their
  TED twins) have a documents link.
- **Snapshots**: the list's snapshot keys now name `cpvMain` and `notCpv` (signature defaults, the worker builds the same keys);
  snapshots made before the deploy are not found until the worker's next run (the lists are read live meanwhile).
- **Page size 25/50**: read live (the snapshots and the warm lists are for 10); a larger page costs more per request.
- **Presets**: the code sets are ours, from the vocabulary; say if a group should hold other codes.
