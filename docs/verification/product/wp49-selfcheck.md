# WP-49 self-check: empty budgets explained, the currency filter, one filter behaviour, slow clicks, connection exhaustion

Branch `wp-wp49` (from `integration` d23b5e2). Server runs in `/root/dev-w49` (database `agent_wp49`), 19 October 2026.
Source: `docs/verification/product/investigate-ux4.md` (its server timings were inflated by its own runaway query; the numbers below are mine, measured under a server load average of 4 to 11, with two other agents running).

Results of the checks that ran on the server:

- `ruff check .`: clean. Unit suite and integration suite: green: the final full run after the fix above (unit, then integration, about 1,150 tests in all) ended with no failure.
- `tsc --noEmit`, `npm run check` (all `lib/*.check.ts`, among them the new `wp49.check.ts` and the changed `wp20.check.ts`): green. `next build` (demo data, `node:22-alpine`, `next.config.ts` with the new `experimental` options): compiled, no warning, all routes listed.
- Playwright: **not run** (it does not run on the server). `e2e/wp49.spec.ts` (7 tests) is new and unrun; see "Not run".
- **A real browser on the final build** (built-in browser pane, the demo build served from the server through an SSH tunnel, stopped afterwards): see "Checked in a browser" below. This is what stands in for the e2e of section 3.
- The first full integration run had one failure, `test_a_long_closed_result_pages_inside_the_api_roles_five_seconds`: it passed `currency="EUR"` to `export_tenders` as a stand-in for the default, and an explicit EUR is now a filter (those notices state no value). It now passes `None`, the default; the behaviour change is the intended one and the test still checks what it checked (paging under the 5 s budget).

## 1. Empty budgets and empty values say why, from data we hold

### 1a. Calls (`budgetNote`)

`backend/dgate/funding.py` `budget_note()`; the field `budgetNote` is on `/v1/funding` and `/v1/funding/{slug}` when `budget` is null, null otherwise. `web/components/dg/data-display.tsx` `BudgetDisplay` replaces "Not available" on the call card, the call page (short line plus the full sentence), the calendar rows.

| Case (production, open calls 18 October) | Reason code | What the card says | Where the reason comes from |
|---|---|---|---|
| EIC Accelerator 2026 (`budgetYearMap {"2026": "0"}`) | `portal_zero` | "The portal states 0 for this topic" | the stored `conditions_raw.budget_line` (the portal's own line) |
| EDF-EDIP-P-2026-FNLC-CSA-PREP (empty `budgetYearMap`) | `portal_empty` | "The portal gives no figure for this topic" | the same stored line |
| an EU topic with no line in the portal's table | `portal_no_line` | same short line | no `budget_line` stored |
| Vinnova (1 open, 4 of 6 closed) | `source_no_field` | "Vinnova publishes no budget field" | `sources/vinnova.py`: the register has no budget field and the parser refuses per-project ceilings on purpose |
| French AID (4 open, 11 closed) | `source_no_total` | "No total stated by the agency", and "Ceiling per project: EUR x" where `max_aid_eur_per_project` is stored | `normalise.py:1640` stores it for the calls whose page states one |
| any other national source | `source_none` | "The source states no budget" | |

The page text for the zero case says the work programme is where the amount is set and, only when the call links a document called a work programme, that it is "linked under Documents". **No figure of ours is shown**: the Vinnova stage ceilings (500,000 / 2 million / 5 million SEK) are prose, not a stored field, so they are not shown (the task said: per-project ceiling only if a stored field holds it). Reading them from the prose is the investigator's option B for Vinnova; it needs a parser the connector deliberately does not have, for one open call, and was not built.

Tests: `tests/unit/test_wp49.py` (seven cases, among them "no digit in the Vinnova text" and "the work programme is called linked only when it is"), `tests/integration/test_wp49.py::test_a_call_without_a_budget_says_why_and_one_with_a_budget_says_nothing` (through the API, six sources), `lib/wp49.check.ts` (the demo data carries the note on every call without a budget and on none with one).

### 1b. Tenders: "Estimated value: Not stated by the buyer in N %" was not true for two sources

Cause: `lib/source-status.ts` took the share of notices with no stated value per source from `valueStatedCount` and always said "by the buyer". For `pl_ezam` (52,251 notices, 100 %) and `nl_tenderned` (475, 100 %) our connector never reads a value (`normalise.from_ezamowienia` sets `value_amount=None`, `from_tenderned` has no value at all), so the buyer may well have stated one.

Fix:
- `normalise.VALUE_NOT_READ_SOURCES = {pl_ezam, nl_tenderned}`, a unit test that both mappers leave the value empty (so the set cannot go stale unseen).
- `/v1/sources` gains `valueRead` (false for those two, true for the other tender sources, null for grant sources). Integration test.
- The site says "Not collected from this source: we do not read estimated values from its notices yet." for them (whatever the count), and for every other source "No usable estimated value in N % of notices from this source." On the notice's own page it is followed by what that counts: none stated, a placeholder such as 0 or 1, a kind of amount we do not read yet (TED's share mixes the three; 3 of the 30 sampled nulls were a kind of amount we do not read). `wp20.check.ts` was changed for the new wording, not weakened: it keeps the 20-notice minimum and the "no count: no sentence" cases and adds the not-read case.

### 1c. What it would take to read the value (documented, not built)

Read-only look at the raw store (production, worker container, scripts removed from the host, two helper files left in `dgate-worker-1:/tmp`, see deletion candidates):

- **pl_ezam**: 20 of 20 current board records have `htmlBody: null`; the listing has no value field. The value is on the BZP notice document, a separate request per notice. 52,251 held notices plus about 2,500 a working day: at one request a second the backfill is about 14.5 hours and the daily top-up 40 minutes. I did not call the portal (the repository rule: no calls to procurement portals from automated runs), so the endpoint and the field are unverified. Needs: owner approval of the load, a look at the portal's terms, a replay ops module (dry run by default, `--yes`) that fetches the document of notices without a value and updates `opportunity.value_*` through `upsert_opportunity` (new versions, `value_kind` of its own), and a floor. Notices with a TED twin already show the twin's value.
- **nl_tenderned**: the held payload (list row plus `detail`, 32 keys) has no value field; `detail.links.pdf` points at the notice PDF. 475 notices: a backfill is about 8 minutes, but the XML/PDF endpoint and its fields are unverified.
- **TED, the 3 of 30 dropped values** (framework maximum 710797-2026, single payable amount 703229-2026, 16 lot award values 700840-2026): **not implemented**. Reasons: (1) the field names (`framework-maximum-value-lot`, `framework-value-notice`, `result-value-lot`) were confirmed by the investigator, not by me, and a wrong name in `TED_FIELDS` makes TED refuse the whole daily request; (2) the raw store holds only the fields that were requested, so the effect starts with new notices and an old notice needs a re-fetch (about 94,000 notices, 380 requests of 250); (3) the semantics are not clean: a framework maximum is a ceiling over the framework's life, a lot award value is an awarded value, neither is "the estimated value of this notice", and `value_kind` ('total', 'estimated', 'lot_sum', 'first_lot') has no label for them in the API, the CSV (`valueKindLabel`) or the card. A clean version adds two kinds (`framework_max`, `lot_award_sum`) used only when nothing else is stated, their labels on the card and in the CSV, the three fields, a replay of the 94,000, and a TED test fixture per field. About a day plus the re-fetch; it recovers up to about 10 % of the TED nulls, mostly award notices.

## 2. The currency filter

Cause (as the investigator found, confirmed in code): the API applied `currency` only inside `if min or max`, so a currency alone changed nothing; the UI dropped `EUR` from the address and counted a currency as no active filter.

Change:
- API (`/v1/tenders`, `/v1/tenders/export`, `/v1/tenders/scope-counts`, `/v1/funding`): `currency` has no default. Alone it adds `value_currency = X AND value_amount > 1` (calls: `currency = X AND budget IS NOT NULL`), so a placeholder never counts as a value in X. With a range the semantics are as before, EUR when none is given. Nothing is converted. Saved searches (`accounts._call_kwargs`) pass the stored currency or none.
- Web: the currency select has "Any currency" as its first and default choice, EUR is a choice like the others and stays in the address; a currency counts in the group's number, in "N active" on the phone button, in `describeCallFilters` ("a budget stated in SEK") and in the page's `noindex` rule; the hint under the group says what each part does. The demo data follows the same rule.
- Tests: `test_a_currency_alone_lists_the_notices_that_state_a_value_in_it`, the range test (EUR default unchanged), export and scope counts, the call list, a bad code (422); `lib/wp49.check.ts` (parse, address, count, demo data); e2e `tenders: a currency alone ...` (cards all in PLN, fewer than before, the group shows 1, Back removes it and the select returns to "Any currency"), `EUR is a choice ...`, `funding: a currency alone ...`.
- Not changed on purpose: changing the currency after setting a range keeps the numbers under the new label (the presets are plain numbers, the label says the currency; a reset would drop a choice the visitor made). The page does not yet print "showing notices with a stated value in PLN" in the result line; the hint explains it.
- Deploy note: the key of the pre-computed list snapshots (`list_snapshot`) includes the arguments, and `currency` default changed from "EUR" to none, so the snapshots written before the deploy are not found until the worker writes new ones (every 4 hours). After the deploy run `python -m dgate.ops.warm_lists --yes` once (production commands below).

Measured on production data with the new code (read-only, API role, 5 s budget, server load 4 to 11):

| Request | Cold | Result |
|---|---|---|
| open, relevant, no currency (the default list) | 3.6 s | 1,571 |
| same + `currency=PLN` / `EUR` / `SEK` | 1.9 / 1.7 / 0.7 s | 58 / 539 / 14 |
| all statuses, all scopes + `currency=PLN` | 5.2 s, over the 5 s budget (503 "took too long", then the page keeps the last answer) | |
| same + `min=100000` (the old path) | 4.1 s | 24,316 |
| funding, `currency=SEK` / `EUR` / PLN with all statuses | 0.14 / 0.13 / 0.12 s | 0 open / 55 / 6 |

The all-statuses case is as slow as the ranged case before it; the cost is the collapse rule over the 200,000 rows, not the currency. Left as it is.

## 3. One filter behaviour

`components/funding/filter-panel.tsx` (`useLiveForm`, shared by `FilterPanel` and the new `LiveForm`), `lib/filter-query.ts`, `components/dg/live-list.tsx`.

| Control | Before | Now |
|---|---|---|
| checkbox | request at once, per tick | waits 400 ms for the next tick (three ticks, one request) |
| radio, select, date | at once | at once |
| search box | on Enter | on Enter (unchanged) |
| text box (CPV, suppliers fields) | when left | when left or Enter (unchanged) |
| submit / Apply | `replace` | applied at once, nothing sent if the filters did not change |
| history | `router.replace`: Back left the page | `router.push` once per settled set; Back undoes it **and the form follows** (see below) |
| address | `?status=open&scope=relevant&country=PL` | `?country=PL`: the page's defaults (`status`, `scope`; organisations' `programme=EDF`; suppliers' `sort`) are left out |
| pending | `aria-busy` that nothing styled | the results are dimmed (50 %) with a bar across the top, `aria-busy`, a spinner and "· updating" on the phone's "Show filters" button, a polite status line for a screen reader; cards stay clickable |
| the sort select and the pagination links | replace, no sign | push, and the same pending state |

Pages: `/tenders`, `/funding` (and its sub-lists), `/buyers`, `/organisations` through `FilterPanel` + `ResultsRegion`; `/suppliers` through `LiveForm` (its form is horizontal, no folding); `/calendar` through `FilterPanel` alone. On a phone the same code runs (the panel is the same form behind "Show filters"; the spinner is in the button because the list is below the open panel). **Unchanged, explicit "Apply" forms**: `/changes`, `/market`, `/digest`, `/networks/consortium-gaps`, `/networks/ukraine-partners`, the finders on the home page and the organisation profile; they are plain GET forms and stay so.

Back/Forward: the form is uncontrolled (`defaultChecked`), so after Back the boxes would have shown the state before it. The hook compares the address with the form each time a new page of the route arrives (and only when no change of the visitor's is waiting or in flight) and rebuilds the form from the page when they differ. That also fixes "Clear all", which left ticked boxes ticked. Folded groups reset on such a rebuild; not on an ordinary filter change.

Tests: `lib/wp49.check.ts` (query: defaults, empties, repeats, page; comparison: order, page, defaults), e2e `a run of ticks is one request and one history entry; one tick waits for the next` (two ticks inside the debounce: nothing after 150 ms, `country=DE,PL` after, history +1, no `status`/`scope` in the address, Back clears the address and both boxes, Forward restores), `a radio applies at once`. **None of the e2e ran.**

## 4. Slow clicks

Findings that changed the plan:

- **`loading.tsx` was not added.** The investigator's list included `/funding` and the detail routes. The file `app/(public)/funding/(list)/layout.tsx` records why the funding list has none: WP-43 (verification 3, finding 4) found that a `loading.tsx` makes the server send the skeleton in place and the page as a hidden block that a script swaps in, so a visitor without scripts or a crawler saw "Loading" and no call, and the e2e tests of WP-43 assert the opposite. The detail pages are the pages that rank in search, so the same applies to them. `/tenders` and `/buyers` lists still have theirs (WP-43 noted it and left it).
- What was done instead, with no change to the server's HTML: `components/dg/card-link.tsx` uses Next's `useLinkStatus` (Next 15.5): from the click until the next page is there the card is dimmed (`has-[[data-link-pending]]`), a spinner sits after the title and a screen reader gets "Opening". The same hook reports pagination clicks to the list's pending state.
- **Prefetch**: card links (call, tender, buyer, organisation), the buyer link inside a tender card, the calendar rows and the pagination links are `prefetch={false}`. The prefetch of a dynamic route without `loading.tsx` is its layout shell only (214 bytes, measured by the investigator): forty requests per list page that warmed nothing. Header and footer links keep theirs. e2e `the pagination links and the cards do not prefetch` (a negative check; it would also pass if nothing prefetched at all).
- **Cold detail pages**: the notice page now reads the archive and the source list while it reads the notice (they need only the slug), and the call page reads the open calls its related list comes from while it reads the call. `getRelatedCalls` was replaced by `getOpenCallsForRelated` + `relatedCallsFrom`. The saving is one round trip of the cold render (0.2 to 0.6 s on the investigator's numbers); not measured by me.
- `staleTimes` (router cache for back/forward, option H) was **not** set: it would also cache the signed-in pages for the same time.

### `/v1/buyers`: one aggregate for every filter

The aggregate (`aggregate_sql()`, a pass over every core notice) does not depend on the filters, which run over its 1,972 families afterwards, and was run again for each new filter. `tenders.buyer_base()` keeps its rows (5 columns) for five minutes in the API's memory, single flight, a failure not kept, off when `DGATE_LIST_CACHE_SECONDS=0`; the same SQL then reads them back as `unnest` arrays, so the filters, the name search (`dg_fold`), the order and the page are the code that was tested before.

Measured on production, the same seven requests with the code in the image (before) and with this branch (after), one cold first request, server load 4 to 11:

| Request | Before | After |
|---|---|---|
| `country=PL` (first) | 7.8 s, 503 | 2.5 s (computes the aggregate) |
| `country=DE` | 5.2 s, 503 | 0.54 s |
| `country=FR` | 2.4 s | 0.20 s |
| `q=ministry` | 2.4 s | 0.56 s |
| `hasOpen=true` | 3.0 s | 1.9 s (outlier, see below) |
| `country=PL` again | 1.8 s | 0.63 s |
| `country=SE` | 1.7 s | 0.15 s |

The totals of the five requests that answered in both runs are equal (PL 136, FR 327, `q` 209, `hasOpen` 130, SE 24). `hasOpen` after is slower than its siblings; I could not tell load noise from a plan difference and did not repeat it. A warm repeat is also served by the existing `cache_list` for five minutes.

Test: `test_the_buyer_aggregate_is_computed_once_for_every_filter_and_the_filters_still_work` (five distinct queries, one pass; the cache is reset after the test so it cannot reach the next one), and the existing buyer tests (`test_buyer_families`, `test_wp20`, `test_tenders_api`, `test_suppression`, `test_stats`) run unchanged on the new path.

## 5. Connection exhaustion

Cause: one API process, a thread pool of 40, and a new connection per request with no bound; the role `dgate_api` allows 30. A burst (the `next build` prerender, or a spike) exceeded the role: "too many connections for role dgate_api".

Change:
- `db.bounded_connect(dsn, size, wait)`: a semaphore per (DSN, size) around `connect`. A request over the bound waits `DGATE_POOL_WAIT_MS` (3 s) and then gets `PoolBusy`; `api.py` answers it, and the role's own `TooManyConnections`, with **503 `{"detail": "the service is busy; retry shortly"}` and `Retry-After: 2`**. Defaults: 24 for the API role (limit 30), 8 for the accounts role (limit 10); `DGATE_API_CONNECTIONS`, `DGATE_APP_CONNECTIONS`. Used by `api.get_conn`, `funding.get_conn` (which `changes` and `network_api` import), `stats._connection` and `accounts.get_conn`. `psycopg_pool` is not a dependency, so a connection is still opened per use; the bound is what protects the role.
- `/v1/health` uses the headroom (`get_conn_reserved`), so a saturated pool does not make the container look dead.
- Web build: `next.config.ts` `experimental.staticGenerationMaxConcurrency: 3` (default 8 per worker) and `staticGenerationRetryCount: 3`.
- Why the home page said "The list could not be loaded": it catches every error of its lists and renders that sentence. In a fresh build container `withLastGood` holds nothing, and its key for "closing tenders" carries today's date, so a failure at the wrong minute had no last good answer; the page, prerendered with the sentence, was served until the next revalidation (60 s). Now the home page **throws** when the two closing lists did not come: a build tries the page again and then fails, and a revalidation that fails keeps the last page that rendered (Next's behaviour for ISR). The two error branches of the page were removed with it.
- Tests: `tests/unit/test_wp49.py` (a request over the bound waits then is refused and never connects, a slot is returned when the work fails, a waiting request gets the slot when it is freed, two DSNs are counted apart); `tests/integration/test_wp49.py` (the one slot taken: `/v1/sources` answers 503 with `Retry-After: 2`, `/v1/health` still 200, then 200 again; 16 requests over a bound of 2 are all served).

## Checked in a browser (demo build, final code)

- `/tenders`, two checkboxes (PL, DE) clicked in one tick: the address was still clean 150 ms later, `?country=DE%2CPL` after, history length +1, 4 cards. Back: address clean, both boxes unchecked, 10 cards. Forward: both boxes checked again, 4 cards.
- Currency select set to PLN: `?currency=PLN`, 2 cards, both stating PLN and none EUR, the "Estimated value" group shows `1`; Back: address clean, select back to "Any currency", 10 cards.
- With the page's `fetch` delayed by 1.5 s, one radio click (`status=closed`): 0.7 s later the results section carried `data-busy`/`aria-busy`, the filter panel `aria-busy="true"` and the status line said "Updating the results"; at the end the address was `?status=closed` and all of it was cleared.
- With the page's `fetch` delayed by 2 s, a click on a card title: 0.7 s later the card held the spinner and the screen-reader text "Opening" while the page was still `/tenders`; then the notice page opened.
- The call with no budget (Spanish, demo data) reads "The source states no budget" in the Budget cell of its card.
- Not looked at: how it looks (the screenshot of the pane timed out twice and the opacity transition does not run while the pane is not painting; the built CSS contains `.opacity-50` and the `:has([data-link-pending])` rule), a phone width, dark theme.

## Hostile review of my own diff

Found and fixed during the work (8): (1) the buyer-base cache outlived the test that filled it and fed the next test a stale aggregate, and a TTL of 0 still read the entry: the cache is bypassed when the list caches are off and the test resets it; (2) a `sent` marker in the filter hook could stay set when a navigation finished without ever showing `pending`, and then hide the same filter chosen again after Back: it is reset when a new page arrives; (3) `formToQuery` was in a client file and not testable: the pure part moved to `lib/filter-query.ts`; (4) ruff import layout of the unit test; (5) `getRelatedCalls` became dead and was removed; (6) `loading.tsx` as asked contradicts the WP-43 finding recorded in the funding layout and its tests: not added; (7) the long "no usable value" sentence would have wrapped to five lines in a home card: the card says the short sentence, the notice page adds what it counts; (8) the export test that modelled the default with `"EUR"` (above), found by the full run; and the e2e for the call with no budget first looked at page 1 of all calls, where that call is not (it is Spanish: the test filters by country).

Known and left: the debounce applies to checkboxes only (a radio and a select are one deliberate choice); a rebuild of the form after Back closes the folded groups the visitor had opened; the mobile panel stays open after a change (the list is below it, the button shows the spinner); the three `/v1/buyers/{slug}` calls still run the whole aggregate per slug (not touched); `has-[...]` needs a browser with `:has()` (all current ones) and degrades to no dimming.

## Not run

- Playwright, any spec (the existing ones and the 7 new). The new ones were written against the markup and the demo data; the likeliest to need a fix in CI are the Back test (it relies on the form being rebuilt after `goBack`), the history-length assertion, and the option click of the currency list on desktop.
- A phone width, the dark theme and the look of the dimmed list in a browser.
- The `has-[...]` dimming, the `useLinkStatus` spinner, `staticGenerationMaxConcurrency` taking effect (`next build` accepted the options; the number of concurrent API requests during the build was not counted).
- The effect of `Retry-After` on the browser or on Next's fetch: the web does not honour it; its own retry is the build's `staticGenerationRetryCount`.
- A load test of the pool against the live API (not allowed on production); the test uses a bound of 1 and 2.

## Production commands (for the orchestrator; none changes data)

1. Deploy the backend image and rebuild the web image as usual (no migration).
2. After the API restart, once: `docker compose ... exec worker python -m dgate.ops.warm_lists --yes` (rewrites the list snapshots under the new key; it is the job the worker runs every 4 hours, its duration not measured by me).
3. Optional, to be explicit about the bound: nothing to set; the defaults are 24 / 8 / 3000 ms. To change: `DGATE_API_CONNECTIONS`, `DGATE_APP_CONNECTIONS`, `DGATE_POOL_WAIT_MS` in `infra/.env`.
4. No ops module for data was written: the budget and value wording needs no data change, and the value reading of `pl_ezam`, `nl_tenderned` and TED is documented, not built (section 1c).

## Scratch

Deleted by me at the end: `/root/dev-w49` (with the hard-linked `node_modules`, the demo build and the scripts), `/root/run_w49*.sh`, `/root/w49_*.py`, the suite log, the database `agent_wp49`, the container `w49-site`. Left (the container user may not delete them): `dgate-worker-1:/tmp/w49_nl.py` and `w49_ez.py`, read-only helpers; they go with the next container recreate.
