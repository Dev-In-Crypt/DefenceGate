# WP-56 self-check: content-structure fixes without wording decisions

Branch `wp-wp56` (from `integration` 891d85b). Rule of the owner: no approved wording is changed. What was added or deleted as
text is listed under "Strings", item by item. Source of the findings: `ux-audit-content.md`, `ux-audit-funding.md`,
`UX_AUDIT_SUMMARY_2026-10-19.md` (T20, T24, C4, C5, C6).

## Results per item

### 1. T20a, the pointer to "Can you apply?" (F-02)

- Before: the "Rules that apply" card of every call whose regime has no encoded rules (34 national calls, and Horizon and Digital Europe
  calls) said "Its conditions are in the documents under “Can you apply?” and in the official call text." The pages of the 34 national
  calls have no such panel (the panels are Key facts, Scope, Who can apply, Rules that apply, Terms, Source and attribution, Related calls).
- Cause: `web/components/funding/rules-apply.tsx` printed the sentence for every non-encoded regime.
- After: the page passes `canApplyPanel` (true exactly when it renders the "Can you apply?" panel: a read document, `not_read`, or an open
  EDF call). With the panel the words “Can you apply?” are a link to `#can-you-apply-` (the id of that panel); without it the pointer is
  left out and the sentence ends "Its conditions are in the official call text." No new prose.
- Test: `e2e/wp56.spec.ts` (national call 13: no pointer, no `#can-you-apply-`; Horizon call 7 with the panel: link to the existing anchor).

### 2. T20b, text cut at about 700 characters (F-03)

- Where the data is cut: **not in the stored data and not on the page, but in the API.** `dgate.funding.who_can_apply()` derived the two
  rows "Eligible countries" and "Other eligibility conditions" from the stored `eligibility_text` and cut each at `WHO_MAX_CHARS = 700`
  with "…". The stored text (`call.eligibility_text`, served as `conditionsText`) is complete, and so is the "Conditions as published" block.
- After: the API serves each section whole (`WHO_MAX_CHARS` removed). The page shows a value of up to 800 characters whole; a longer value
  as its first ~600 characters (cut at a word, ending "…") and a Details "Show full text, N characters" that holds all of it
  (`web/components/funding/long-text.tsx`, `web/lib/long-text.ts`). Nothing is cut for good.
- How many calls: the audit counted 46 of 193 calls (48 rows, all Horizon: 25 open, 20 forthcoming, 3 closed). I could not re-measure on
  production (the read-only query was refused by the permission system in this run). The orchestrator can count them with the command
  under "Production commands".
- How a re-read fixes it: no re-read of any source is needed, because no stored data is cut. The new code serves the whole section from the
  text already held; the call page revalidates every 300 s, so the pages are complete a few minutes after the deploy.
- Tests: `tests/unit/test_funding_terms.py::test_a_long_section_is_served_whole_not_cut_with_an_ellipsis` replaces
  `test_a_long_section_is_cut_at_a_word_with_an_ellipsis` (its premise, the cut, is what the owner asked to remove; the new test asserts the
  opposite and is not weaker: length above 700, last word present, no ellipsis, value equal to the section). Web: `lib/wp56.check.ts`
  (`textHead`, `fullTextLabel`), `e2e/wp56.spec.ts` (call 8: long list behind "Show full text", opens, last country visible).

### 3. C6, "Conditions as published" and the repeated row

- Before: `details#conditions`, closed, holding one paragraph of up to 8,591 characters; the "On this page" link scrolled to the closed
  summary. "Who can apply" showed "Described in section 6 of the call document." twice (87 pages).
- After: "Conditions as published by the source" is a card with the id `conditions` (the index link lands on it): the first ~600 characters
  (cut at a word) and a Details "Show full text, N characters". A text of up to 800 characters is shown whole. Rows of "Who can apply"
  with exactly the same text are one row: the labels are joined ("Eligible countries and other eligibility conditions"), the text
  appears once (`mergeSameText`, web only; the API keeps both rows as the contract documents).
- Tests: `lib/wp56.check.ts` (`mergeSameText`), `e2e/wp56.spec.ts` (call 8: two rows, one sentence; conditions: head visible, tail hidden until opened).

### 4. C5

- `/regulation` repeated its intro: the page lead ("... Each entry gives the official source, one sentence of it copied word for word,
  and the day we last read it.") and, directly under it, the API notice ("Each entry gives the primary source and one sentence of it,
  copied word for word, and the day we last read it. It is a reading aid ..."). Removed: the second sentence of the lead. The notice (the
  longer text, with "not legal advice") is kept. Test: e2e, "copied word for word" appears once.
- Header and footer navigation, mismatches found (header = `components/dg/header-bar.tsx`, footer = `components/dg/footer.tsx`):
  | Destination | Header | Footer before | Footer now |
  |---|---|---|---|
  | Organisations | Network | Directory | Network |
  | Suppliers | Network | Directory | Network |
  | Ukraine partners | Network | Readiness | Network |
  | Consortium gaps | Network | not linked | Network (link added) |
  | Weekly digest | Data | Directory | Data |
  | Pricing | top level | Data | Directory (the header's top-level pages and the lists only the footer has) |
  | Market | top level, "Market" | Data, "Market overview" | Directory, "Market" |
  Left as they are (not the same destinations, reported): the header has no Glossary, CPV finder, Alerts, Opportunity pack, About, Privacy,
  Terms, Imprint, Deadline calendar, What changed or Closing soon; the header's top-level labels "Funding" and "Readiness" are the footer's
  "Funding calls" and "Readiness check"; the mobile menu is a flat list; "Alerts (not open yet)" is now the last link of Data instead of
  sitting among live pages. The footer is now six columns at lg (grid template changed), still two columns of links where it was.
  Test: `e2e/wp56.spec.ts` compares every sub-menu link of the header with the footer group of the same name (label and address).
- Date formats. The site's format is `formatDateUtc` ("19 Oct 2026", `web/lib/format.ts`). Unified on the pages I own: the
  "Last reviewed" dates of `/requirements` and `/requirements/*` (were 2026-09-07), "Rules last reviewed" in the funding rules block,
  and the dates in the Terms rows of a call page ("Decision expected 2026-12-15", "Project start 2027-01-04 to 2027-01-11"; `isoDatesToSite`).
  Not changed (not mine, or approved wording): the long dates "18 October 2026" in `/privacy`, `/terms`, `/methodology`,
  `/data/sovereignty`; the ISO dates of the readiness roadmap and rule sources (`components/readiness/*`), the citation string of
  `/regulation` entries and the Atom feeds (machine formats on purpose); "(7 September 2026)" in the provenance sentences
  `statusWords`/`originWords` (approved wording, tested).
- Titles over 60 characters and descriptions over 160: one rule in `buildMetadata` (`web/lib/seo-trim.ts`): the title is cut at a word to
  46 characters (60 minus the template " · DefenceGate"), the description at a word to 160, both ending in "…"; a text that fits is
  unchanged. It applies to every page that uses `buildMetadata` (75 call sites), including the tender and call pages: a long title ends
  in "…" and may lose a trailing id such as the topic id.

### 5. C4, /requirements

- `/requirements/ncage`: the 50 identical country rows (31 "NATO countries" and 19 "Tier 2" with the same body, note and status) are two
  groups, each with the shared body name, "N countries", the countries in name order, the note once and the status once. Rows with
  their own content (Spain, Ukraine, "Every country") stay single rows, "Every country" first. Every row's country is kept
  (`groupIssuers`, a group needs at least 3 identical rows). The question "Who issues NCAGE code?" (also in the structured data) uses
  the same grouping: its answer is no longer a 474-word run.
- Cost and time: the cards already show "Not stated in the sources" where a card has no cost or time (`formatRange(null)`); no cell is
  empty in the markup. I kept that wording (it is tested) and did not shorten it to "Not stated".
- Internal identifiers and words removed from the public pages, one by one:
  1. The bracket label "[DefenceGate technical appendix, <section>]" before a quote (`publicPassage`): shown without the label; where a
     body is named before it ("[NSPA, quoted in the DefenceGate technical appendix, NCAGE]", "[Ekontrol (Bureau Veritas partner,
     Ukraine), 2026, quoted in the DefenceGate technical appendix]") the label is the body ("[NSPA]", "[Ekontrol (Bureau Veritas partner,
     Ukraine), 2026]"). Also in the "Rules that apply" block of the call page and in the readiness rule source (`components/readiness/rules.tsx`).
  2. The "Source:" line (`publicRef`): the same rule; with nothing left it reads "See the link" and the link.
  3. "Needed before REQ-AQAP2110." (and REQ-AQAP2310, REQ-EXPORT): the link text is the requirement's name from the catalogue.
  4. `/requirements/export`, "Which programmes ask for it": the leading sentence "You said you move dual-use items to other EU countries."
     is not printed on a static page (`withoutAnswerEcho`, a leading "You said ..." sentence only). The rest of the explanation is unchanged.
  Not removed (provenance statements, approved wording, tested): "Marked verified in the DefenceGate research notes ... (7 September 2026)",
  "Quoted from the DefenceGate research notes of 7 September 2026; ...", "Seen in search results, not fetched directly." They name
  "research notes" and are reported here for the owner's decision. Also left: "(the same body for every country)" in the issuers
  answer (wording; it is false next to the country rows), "Appears in the rules of the general requirements.".

### 6. T24, /funding sorting

- `?programme=edf` (lower case) is the same filter as `EDF` (`parseCallFilters` folds the programme codes to upper case, as it already
  did for countries). Before, the value was dropped silently with no notice.
- Budget sort (API `sort=budget-desc`, mock mirrors it): the chosen currency (EUR by default) first, largest first; then the amounts in
  other currencies, one currency at a time (currency-code order) and largest first within it; then calls with no budget; ties by
  deadline. Before, amounts in other currencies ranked as "no budget" and came out in deadline order (PLN 15M before PLN 350M, F-06).
  Closed calls stay last, as for every sort (documented in `API_CONTRACT.md`, unchanged). The sort label now says which currency leads:
  "Budget, largest first (EUR first)" (the currency of the filter if one is set).
- Deadline sort: nulls were already last; the rule that an open call whose cut-off has passed (rolling) follows the upcoming deadlines stays,
  and its label "Deadline, soonest first" is unchanged (F-07 is that rule; reported, not changed).
- "Cascade funding" (index label) against "Financial support to third parties" (panel title): reported only. The index label is the
  tag and filter name; the panel title is the regulation's term. Wording decision for the owner.
- Tests: `tests/integration/test_funding_api.py::test_budget_order_keeps_each_other_currency_in_amount_order_and_puts_no_budget_last`;
  `lib/wp56.check.ts` (programme case); `e2e/wp56.spec.ts` (same count for `edf` and `EDF`, differs from no filter; the label).

## Strings

Added:

- "Show full text, N characters" (summary of the Details; N with thousands separator, e.g. "8,591").
- "…" at the end of the visible first ~600 characters of a long text, and at the end of a trimmed title or description.
- "and" between two labels joined by the repeated-row merge (`Eligible countries and other eligibility conditions`).
- "N countries" after the body name of a grouped issuer list (e.g. "National codification bureau (NCB) of the country: 31 countries").
- The footer group name "Network" and the footer link "Consortium gaps" (names that the header already has).
- The sort label suffix " (EUR first)" (the currency code is the one in use).

Deleted:

- In "Rules that apply" (pages without a "Can you apply?" panel): "the documents under “Can you apply?” and in" (the sentence ends
  "...are in the official call text.").
- `/regulation` lead: "Each entry gives the official source, one sentence of it copied word for word, and the day we last read it."
- The bracket labels "[DefenceGate technical appendix, ...]" and the words "quoted in the DefenceGate technical appendix" on public pages
  (see C4 item 1-2).
- "You said you move dual-use items to other EU countries." on `/requirements/export` (static page).
- The 50 repeated rows of `/requirements/ncage` (replaced by two groups; each distinct note kept once).
- "Market overview" (footer label, now "Market").
- Nothing from `privacy`, `terms`, `methodology`, positioning or claims.

Changed format only: ISO dates to "7 Sep 2026".

## Tests and checks (run on the server, own dirs `/root/dev-w56`, `/root/dev-w56-web`, database `agent_wp56`)

- Backend: `ruff check .` clean; unit suite and integration suite (`/root/run_w56.sh`): no failure. Tests changed or added:
  `test_a_long_section_is_served_whole_not_cut_with_an_ellipsis` (replaces the cut test, see item 2),
  `test_budget_order_keeps_each_other_currency_in_amount_order_and_puts_no_budget_last` (new). `test_budget_order_puts_the_chosen_currency_first_and_never_mixes_amounts`
  is unchanged and green. The first full run failed five tests only because my dir lacked `web/` and `infra/` (tests that read them); with
  both present the suite is green. No assertion weakened, `addopts` untouched.
- Web: `tsc --noEmit` clean; `npm run check`: every `lib/*.check.ts` ok, including the new `lib/wp56.check.ts` (it first failed on my own
  title-trim expectation; the trim now keeps a whole word that is followed by a comma); `next build` green.
- Playwright (`--workers=1`, desktop and mobile-375, against the mock build). Run 1 (`wp56`, `readiness`, `funding`): 57 passed, 1 skipped,
  2 failed (my new long-text test: the mock text was too short to need the Details; mock list made longer). Run 2 (`wp56`, `wp46`, `routes`,
  `ux`, `layout`): 133 passed, 5 skipped (the skips were there before, plus the footer-group test, which is desktop only), 2 failed (my own
  test again: a locator that matched the start of the conditions twice, once in the page and once inside the Details; fixed with `.first()`).
  `wp56` re-run alone after the fixes: 17 passed, 1 skipped. The other specs were not re-run after those test-only fixes.
- E2E expectations I changed: `readiness.spec.ts` lines 89 and 103 expected the ISO date "Last reviewed 2026-..." on `/requirements`; they now
  expect "Last reviewed 7 Sep 2026" (same strength, new site format). Line 156 (readiness rule source, ISO) is unchanged.
- Mock data (`lib/mock/calls.ts`) extended so the new behaviour has something to show: non-encoded regimes for Horizon, Digital and national
  calls, a "not read" Horizon call with ISO dates in its terms, a Horizon call with a 120-country list, a repeated sentence and a long conditions text.
  The mock budget sort mirrors the API rule.

## What I could not run or measure

- Production count of the calls whose list was cut (the audit says 46 calls, 48 rows). A read-only production query was refused by the
  permission system, so there is no new measurement. Command for the orchestrator (read-only, no change): after the deploy, for the ids
  of the audit (for example 140, 142, 131, 54) `GET /v1/funding/<id>` must give a `whoCanApply` value longer than 700 characters without a final "…".
  Before the deploy, the count: select `id, eligibility_text` of `call` (not suppressed) and apply `funding.who_can_apply` of this branch;
  the number of calls with a value over 700 characters is the number that were cut.
- Not run: the other Playwright specs (`fit`, `changes`, `digest`, `networks`, `suppliers`, `wp36`, `wp45`, `wp47`-`wp49`, `wp53`, `wp54`, `wp57`) and
  the axe/a11y scripts; the specs were not run against production data (mock only). No screenshot comparison of the new six-column footer was made:
  `wp46` (height at most 360 px from lg, links at least 32 px) passes, the look was not inspected by eye.
- Production data was not changed and no `ops/` module was needed.

## Left for the owner or other packages

- Wording, not touched: "Cascade funding" (index) against "Financial support to third parties" (panel title); "(the same body for every
  country)" in the NCAGE answer; "Appears in the rules of the general requirements."; the provenance sentences that name the "DefenceGate research notes";
  "Not stated in the sources" (kept).
- The long dates ("18 October 2026") on `/privacy`, `/terms`, `/methodology`, `/data/sovereignty`; ISO dates in the readiness roadmap and rule sources.
- Title trimming is global (every `buildMetadata` call, including tender and call pages: WP-52b should know that a long tender title now ends in "…").
- Header menus still omit Glossary, CPV finder, Alerts, Opportunity pack, About and the legal pages (footer only).
- Deadline sort label (F-07) and "closed calls last" for the budget sort are unchanged, documented in `API_CONTRACT.md`.
