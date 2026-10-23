# WP-87 self-check: correctness and trust (UX audit of 22 October 2026, section 2)

Branch `wp-wp87` from `integration` (1ce494d). Task: section 2 of `D:\DEFENCEGATE TESTS\ux-oct22\SUMMARY.md`; owner, 22 October
2026: fix everything that can be fixed (usability, completeness, correctness). WP-86 owns the header, footer, home page, menu,
global search and readiness entry: none of their files is edited here, except that the shared scope names
(`lib/taxonomy.ts SCOPE_CHOICES`, the owner's plain names) also reach the home page's counters (see section 9). No deploy, no
push, no production read or write, no secret, no model call. One migration: none.

## 1. Number pairs: agree, or say why

| Pair of the audit | Cause found | Fix | Proof |
|---|---|---|---|
| Tenders with a deadline ahead 1,486 (list, `from=today`) vs calendar 1,390 | The calendar leaves off the long-running notices (deadline over 3 years ahead) and said so only at the foot of the page | `/v1/tenders/calendar` now counts the list's own set (open, deadline stated, the list's filters and collapse); the page says beside its count "Tenders: 1,390 deadlines of the 1,486 open tenders with a deadline ahead that the tenders list counts under these filters; 96 have a deadline more than 3 years ahead ... and are left off", with a link to that very list (`lib/calendar-counts.ts`) | integration `test_wp87.py::test_the_calendar_reads_the_lists_filters_and_holds_what_the_list_counts` (calendar `total` = list `total` with `from=today`, same notices, six filter sets); check `wp87.check.ts` (the sentence, the link); e2e `wp87.spec.ts` |
| calendar.ics: 500 events, a silent cap | `ICS_MAX_EVENTS = 500` | ceiling 5,000 (above the API's 3,000 tenders and every call); when a cut ever happens, or the API holds more tenders than it sent, the calendar's description says so; the page says "It holds every one of the N events these filters give"; a response header `x-dg-events: N of M`; the feed takes the list's filters (a filtered feed is the paging) | check (1,500 events, no cut, the cut sentences); e2e `calendar.ics holds every event of its filters ...` |
| Open funding 63 (/funding) vs calendar 58 | The calendar lists open calls with a coming deadline; a call past its last cut-off that keeps taking submissions, or without a date, is open with nothing to put on a day | the page says "Funding calls: 58 deadlines of the 63 open calls the funding list counts; 5 have no coming deadline (submission continues past the last cut-off, or no date is stated)" | check |
| BAAINBw: "Tenders in archive 3,335" vs years 4,324 vs "0 of 5,380 notices" (3,721 + 1,659) and "With an amendment 0 %" | The buyer list counts notices shown once (collapse rules); the profile counted every row (TED and its national copy twice), and the years only the last six | `stats.buyer_profile`: every figure over the list's unit (`collapse_clauses`, notices shown once), so the sources add up to the total; `perYearEarlier` and `perYearUndated` so the years add up; the page's "Tenders in archive" is the profile's total; the amendment share is shown only after six months of watching (`amendments.observedFrom`), with "Not shown yet: we have watched this buyer's notices only since Sep 2026" until then | integration `test_a_buyer_profile_counts_what_its_list_shows_and_its_years_add_up` (a TED + national pair counts once; profile total = buyer list total; sources and years add up), `test_stats.py` (extended); check (bars, the six months); e2e (the years add up to the total, the share waits) |
| "Data updated 07:29 UTC" (/tenders) vs "Last collection run 13:29 UTC" (footer) | Two definitions: the list's is the newest run of the tender sources, the footer's of any source (13:29 was AID, a funding source) | one definition for the lists: `meta.updatedBy` names the source; /tenders and /funding say "Latest run of its sources: 22 Oct 2026, 07:29 UTC (TED)". The footer is WP-86's file: **open for WP-86**, it should say "of any source" or name it | integration `test_tenders_read_side.py::test_the_lists_say_when_their_sources_were_last_collected` (extended: `updatedBy`); check |
| Two "Counts as of" on /tenders (18:02 / 18:56) | The list and its scope counts are two answers, each kept for minutes | one stamp when they are of the same minute; otherwise "List as of 18:56 UTC" in the header and "Scope counts as of 18:02 UTC, worked out apart from the list (as of 18:56 UTC); notices that opened or closed in between make them differ" in the scope box (`list-count.listStamps`) | check |
| Hensoldt Sensors "Contracts won 12" vs 13 rows (474829-2024 and 467138-2024) | The count is of procurements (`award_set.KEY`), the rows were award rows | the profile lists one row per procurement, newest notice first, the other publication under it ("Also published in ... (counted once)"); 4x the rows are read so 50 contracts still fill the list | integration `test_one_contract_published_twice_is_one_row_and_a_unit_price_is_in_no_sum` |

## 2. Calendar, calendar.ics and the change feed take the list's filters

- API: `/v1/tenders/calendar` takes `q, country, cpv, scope, goods, from, to, min, max, currency` (+ `maxItems`); `/v1/changes`
  takes `q, cpv, from, to, min, max, currency` besides its own; both read them with the list's `_tender_filters`. A parameter an
  endpoint does not take is a **422** (`tenders.known_params`, a dependency that walks the route's declared parameters; the
  answer lists what it takes and never echoes what was sent). `/v1/changes` with a tender-only filter has no funding part.
- Site: `/calendar` and `/calendar.ics` read the list's filters (`CalendarParams.tender`), pass them to the API, keep them in the
  form and in the feed's address; a tender-only filter takes the funding calls out of "Tenders and funding calls" and says so;
  an unknown parameter is said ("Ignored filter: x (not a filter of this page)") on the pages and is a 422 on `.ics` and
  `.atom`. `/changes` has a search and a CPV field and keeps the other list filters; its Atom link carries every filter.
- From a filtered list: /tenders' result tools link "Deadline calendar of this search" and "Changes of this search (Atom feed)"
  with the list's filters (`calendarHrefFor`, `toChangeQuery`).
- Proof: integration `test_the_calendar_reads_the_lists_filters...`, `test_an_unknown_parameter_is_refused_not_ignored`,
  `test_the_changes_read_the_lists_filters`; check (`parseChangeFilters`, `unknownParams`, `calendarNotices`); e2e (calendar,
  .ics, /changes, .atom 422, the links of a filtered list).
- Not changed (open decision): `/changes.atom?week=...&kind=...` stays the last 14 days, the week and the kind dropped, as
  WP-52's tests fix it (`wp52b-api.spec.ts`, `wp52b.spec.ts`). The task's rule ("never silently ignored") would make it a 422 or
  honour them; that reverses a recorded decision, so it is left to the owner.

## 3. "Open" never shows a "Closed" card

Cause: a national notice whose deadline is more than 90 days from its TED twin's showed the twin's (WP-28: a typo rule). For a
dynamic purchasing system the TED deadline is the first round's, long past, while the national notice (and the list's own
status, which reads the notice's deadline) is open: an Open list showed "Closed" cards. Rule now (`tenders.shown_deadline`, used
by the list, the page and the calendar): when the twin's deadline has passed and the notice's own is ahead, the notice's own is
shown and `anomalies` holds `first-deadline-passed`; the card reads "Open (dynamic purchasing system): first deadline passed"
(a title or procedure that says DPS in Spanish, French, Polish, German, Dutch or English) or "Open: first deadline passed", with
the anomaly's note. A twin deadline still ahead keeps the typo rule. Proof: unit `test_wp87.py` (four cases), integration
`test_a_dynamic_purchasing_system_past_its_first_deadline_is_open_and_says_so` (list, page and calendar agree; the typo rule
stays), check (`tenderStatusView`, `firstDeadlineLabel`).

## 4. Core defence and defence calls first, plain names

- `/v1/tenders`: the default view (open, defence-relevant, no sort) is `core-first`: core notices, then the other purchases,
  each part soonest deadline first, read as the `all` list is (two parts by index, the total unchanged). `sort=deadline-asc` is
  the plain order and is now written into the address when chosen. Sort menu: "Military goods and works first, then soonest
  deadline". Proof: integration `test_the_default_tender_list_leads_with_core_notices_and_counts_the_same` (order, pages across
  the two parts, totals); unit; e2e.
- `/v1/funding`: with no sort, defence calls first then dual-use (each in deadline order); the page heads the dual-use part
  "Dual-use calls" with "Show only defence calls". The weekly digest lists each section's defence calls first and the dual-use
  ones under "Dual-use calls (N)" (`regime` on each call; an issue stored before shows as it is until the worker rebuilds the
  last two weeks). Nothing is dropped. Proof: integration `test_the_funding_list_and_the_digest_list_defence_calls_first`;
  check (`dualUseStart`, `splitByRegime`); e2e.
- Scope names (filters, cards, change page; URL values unchanged): "All defence", "Military goods and works", "Other purchases
  by armed forces", "Everything, also dual-use purchases of civil buyers"; card badge "Military goods and works" / "Other
  purchase by armed forces". e2e `routes.spec.ts` updated to the new names (the scope test itself unchanged).

## 5. Copy

- Mojibake "e-ZamГіwienia": the source was a literal in `backend/dgate/demand.py` (the demand answer's `coverage`), saved through
  a Windows-1251 pipe by WP-81 (760e080); a second one in the same file, "Santa BГЎrbara" (the prime list's source note). Both
  fixed at the source; nothing stored carries them (the text is built per request; the demo answer `web/lib/mock/demand.json`
  was correct). Guards: unit `test_no_text_was_read_with_the_wrong_encoding` (every `dgate/*.py`), check (every
  `web/lib|app|components` file).
- "41 companieswould be named": the sample sentence on /readiness/spain-automotive now reads, in the report's numbers (WP-81
  names every legal entity; `total.winners` = the winners page's `total`): "365 companies won them. The report names every one
  of them: the 38 with the most contracts, and every prime contractor or large defence group, under “who to approach”, and all
  365 on its list of winners. 11 of those listed are marked as a prime contractor or large defence group." (`approachSentence`,
  check). The live numbers are production's.

## 6. Suspect values, plain words

- A contract value under 1,000 (in its currency) is shown as published with "value as published, probably a unit price" and is
  in no sum: `suppliers.sums_select` (the supplier profile and the demand answer's winners use it), `values.suspect` counted,
  the block says "N contracts state a value under 1,000 (probably a unit price, not the contract's value) and are left out of the
  sums." Proof: unit `test_wp81_values.py` (new tests), integration `test_one_contract_published_twice...` (EUR 48 out of the sum),
  check, e2e. Existing tests whose fixtures used values under 1,000 for ordinary contracts (PLN 300, PLN 500, EUR 900) now use
  3,000 / 5,000 / 9,000; their assertions are otherwise the same, plus `suspect: 0`.
- "The portal states 0" → "Amount not stated" (the card's short line; the page's text still says the portal states 0 and where the
  amount is set). `test_wp49.py` updated to the new short line.
- "EU contribution: Not stated" for an organisation or programme row of EDF projects only (Leonardo, 74 EDF projects): "Not
  published per participant (EDF factsheets state no amounts)" (`contributionMissing`); other programmes keep "Not stated".

## 7. /data

- A source whose last run is OK with no minimum to compare it with ("Met expected minimum: Not measured", SEDIA with 1 record) is
  "OK (incremental run)" with the note "No minimum is set for this source, so the run is not measured against one: it fetched 1
  record, reading only what changed since the run before." It counts among "OK (run on time)". Check.
- CORDIS "Last run --" beside "last ran 4 days ago": **not reproduced**. Every dump and screenshot of /data in the audit
  (`funding\t__data.txt`, `ia\pages.json`, `analyst\t6-01-data.png`) shows "Last run 17 Oct 2026, 19:10 UTC" beside the note;
  both read the same field (`lastRunAt`; the note is null without it). Nothing changed; to look at on production if seen again.

## 8. CPV division names

Divisions 16, 41, 76 and 77 had no entry in `taxonomy.CPV_LABELS`; added with the vocabulary's titles. The check now asserts that
every division of `cpv-full.json` has a name. e2e: every row of /suppliers' division table has a name.

## 9. Duplicates: why each was not merged, and the fix

| Case | Why not merged | Fix |
|---|---|---|
| BAAINBw, `/buyers/28871-baainbw` | 28871 is a member of the `DE:rule:baainbw` family (`docs/verification/ux/buyer-families-review.md`), so its page redirects to the head; but every tender of a member linked the member's own id, so a second BAAINBw URL was all over the site | a tender's `buyerSlug` is the family head's (`tenders._present` reads `dgate_buyer_head`). If `/buyers/28871-baainbw` still renders a page of its own on production, the family row is missing: read-only `SELECT dgate_buyer_head(28871), (SELECT method FROM buyer_family_member WHERE org_id = 28871)` |
| Inspektorat Uzbrojenia / Agencja Uzbrojenia (renamed 1 January 2022) | Kept apart on purpose (WP-22: "a rename is not a merge") | curated rename list `buyer_family.RENAMES`: the predecessor joins the successor's family with method `curated_rename`, confidence 0.95, the evidence stored in code; the successor heads the family whatever the counts. Public bodies are never merged: display layer only (`buyer_family_member`). Applied by `python -m dgate.ops.curated_renames` (report) / `--yes` (it runs `ops.buyer_families`, which the worker repeats daily) |
| Hensoldt Optronics GmbH (426742 / 428552), Rolls-Royce Solutions GmbH | Same key ("hensoldt optronics", "rolls royce solutions"), but `ops.org_dedupe` looked only at organisations of a project: contract winners were never in its focus | the focus is project organisations **and** contract winners (current award rows). A group that only winners bring in is left alone when a row of it is a public body (`buyer_family.is_public_body`): never merged by this company rule. The other refusals stand (two PICs, registration or VAT numbers, legal forms). If the two Hensoldt rows hold two different numbers, the dry run lists them as left apart: then it is a person's decision |
| Hensoldt Nexeya France, one with the address in the name | The key kept the address: "hensoldt nexeya france 1 rue ... massy" | `resolution.names.key_of` cuts an address written after a legal form (a form word that is not the first, then two or more words with a digit); the legacy key is unchanged, so stored aliases are found as before. Unit `test_an_address_after_the_legal_form_is_not_part_of_the_name` |
| "Siec Badawcza Lukasiewicz-Instytut Lotnictwa" vs "...Instytutlotnictwa" | The rule exists (`name_key_spaces`, 0.90); the likely reasons it did not run are two PICs (CORDIS registers both) or a batch not yet run | curated list `ops.curated_renames.ORG_RENAMES`: "Instytut Lotnictwa" (renamed into the Łukasiewicz network on 1 April 2019) and the joined spelling merge into the successor's row, method `curated_rename`, 0.95, evidence stored (`db.merge_organisations`); refused and reported when the rows hold two different PICs, registration or VAT numbers |
| "Intendente de las Palmas" twice in Suyfa's buyer table | The supplier profile grouped buyers by organisation row | grouped by buyer family head (`dgate_buyer_head`) |

Proof: integration `test_a_tender_links_its_buyers_family_head`, `test_a_renamed_buyer_joins_its_successors_family_with_its_method`,
`test_a_curated_organisation_rename_merges_with_its_method_and_refuses_two_numbers`, `test_a_curated_rename_with_two_pics_waits_for_a_person`,
`test_contract_winners_of_one_name_are_merged_and_public_winners_are_not`, `test_one_contract_published_twice...` (buyers per family);
unit `test_buyer_family.py` (the rename assertion "a rename is not a merge" replaced by the owner's decision: one family, method
and confidence asserted), `test_wp87.py` (`plan` with the public guard).

## 10. Contrast and tap targets

- Helper text: `--ink-muted` is #56605A on #F4F1EA, **5.79:1** (light); #A5B1A9 on #0F1D17 7.83:1 and on #1F3328 6.06:1 (dark):
  above 4.5:1 in both themes; the audit's "borderline" is not borne out by the tokens. Probe of /tenders in a browser (light and
  dark, filters open): no visible text in its background's colour, no 12-14 px text below 4.5:1; the elements the audit found with
  text colour equal to the background are visually hidden labels (`.sr-only`, e.g. the space between a country code and its name).
  e2e `/tenders (light|dark): no visible text in its background's colour ...` keeps it so.
- Supplier profile: the 33 checkboxes and radios were 20 px (their label row is 44 px and clickable); the box is now 24 px
  (`dg/form.tsx Choice`, every form of the site). The five field labels (16 px tall) label a 44 px field, the equivalent larger
  target (WCAG 2.5.8 exception); the skip link is 1 px until focused. e2e `the supplier profile's controls are at least 24 px`.

## 11. Budget (5 s API)

See section 12 for the measurements.

## 12. Test runs

See the table below (filled after the runs).

## 13. Ops commands for the orchestrator (production, after deploy)

1. `docker compose ... run --rm --no-deps worker python -m dgate.ops.curated_renames` (report), then with `--yes`.
2. `docker compose ... run --rm --no-deps worker python -m dgate.ops.org_dedupe` (report: now contract winners too; read the
   groups and the `left_public_body` count), then `--yes --limit 200` in batches.
3. Read-only: `SELECT dgate_buyer_head(28871), (SELECT method FROM buyer_family_member WHERE org_id = 28871);` and
   `SELECT id, country, canonical_name, eu_pic, national_reg_no, vat_number, merged_into FROM organisation WHERE id IN (426742, 428552);`
4. `python -m dgate.ops.build_digest --yes` (or wait for the worker's daily run): the last two weeks get `regime` on their calls.
5. Nothing else: no migration; the list snapshots (`ops.warm_lists`) pick up the new parameters of `/v1/changes` at their next run.
