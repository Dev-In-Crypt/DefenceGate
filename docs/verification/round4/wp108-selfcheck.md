# WP-108 self-check: award values and version history (round 4, 24 October 2026)

Branch `wp-wp108` (from `integration` at e0d73b7). Evidence: D:\DEFENCEGATE TESTS\ux-oct24b (NOTES.md p10, p04, p02, p07;
p10 ted-verify.json, 33-t-videoscopio.txt, 47-s-faser.txt; p02 shots/incm.txt; p04 txt/m-digest.txt, m-changes.txt;
p07 t-it-2025.csv). Production was read only: a few SELECTs through the postgres container (statement timeout 60 s), two
landed award records read from the raw store inside the worker container. Nothing fetched from TED or PLACSP, nothing
written. Test copy D:\DEFENCEGATE TESTS\wp108 (Postgres 17 on port 55508). Migration 0120.

## Items

### 1. Implausible award values without an estimate (FASER 394720-2025, INCM 499753-2026)

- Before: `award_notice` 122066 (394720-2025) PLN 7,247,040,000 `contract`; 215950 (499753-2026) EUR 1,159,000,000
  `contract`. Neither has an estimate, so WP-103's rule (over 100 times the notice's own estimate) could not apply. Their
  award records were landed on 18 October without any value field (read before WP-95), so the stored total stood. TED's
  `tender-value` for FASER sums to PLN 7,247,040 (p10 ted-verify.json): an exact x1000. INCM's procedure (eForms
  identifier 4d442456-...) has a contract notice 126958-2026 estimated at EUR 1,450,000 (ratio 799).
- Change (`award_value`): `implausible_against(amount, other)`: over 100 times `other` from 10 million, or exactly 1000 times
  it from 1 million. Checked against (a) the sum of the notice's own parts: BT-118 framework maximum vs its lots' BT-709
  maxima, BT-161 notice value vs its winning tenders' BT-720 values, and the stored total vs the parts TED answers when it
  answers only them (the FASER case in ted-verify.json); the parts' sum then stands, same kind; (b) the procedure's value,
  `procedure_value` (new in `awards.VALUE_COLUMNS`: the largest estimate of another notice of the same procedure, same
  currency, index `opp_procedure_identifier`); the procedure's estimate then stands, kind `estimate`. The figure goes to
  `award_notice.value_set_aside` (WP-103) with the reason in the new `value_set_aside_reason` (`estimate` | `lots` |
  `procedure`; the 3 rows of WP-103 are `estimate`, set by migration 0120). API `awardValue.setAsideReason` (left out for
  `estimate`, so WP-103's objects are unchanged). Page: `setAsideNote` says which check and "exactly a thousand times"
  where it is one.
- Ops (`python -m dgate.ops.award_values`, report by default, `--yes` to write): step 3 now runs both DB-only checks
  (estimate, procedure) with no TED request (`--no-fetch` is enough); the lots check needs TED's value fields, so it runs
  in step 1 (`--all` asks TED again for every notice with winners, about 90 requests).
- Production read-only counts (24 October, the step-3 rule as SQL):
  - estimate check (WP-103): 3 held already.
  - procedure check: 5 notices
    - 499753-2026 contract EUR 1,159,000,000, procedure estimate EUR 1,450,000 (x799), INCM
    - 502578-2026 contract EUR 1,159,000,000, same procedure (x799), the second publication of the same award
    - 313429-2026 contract PLN 741,576,016.16, estimate PLN 6,053,843 (x122), Polish military uniforms
    - 107790-2025 contract EUR 690,000,000, estimate EUR 690,000 (exactly x1000), Portuguese warship engines
    - 451107-2025 framework EUR 22,922,861, estimate EUR 23,918.70 (x958), Dutch security equipment
  - lots / x1000 check: not countable without asking TED (the 18 October records carry no value fields; I made no TED
    request). 4,298 TED contract/framework values of 1 million or more are held; the `--all` report counts the hits as
    `ted_set_aside_lots`. FASER is one of them by the persona's TED evidence (PLN 7,247,040,000 = 1000 x 7,247,040).
  - Plausible large values checked by hand and left alone: 419618-2026 (PLN 9.3 bn, no procedure value, no parts),
    666181-2026 (DKK 2.035 bn framework vs DKK 77 m estimate, x26), Arquus 38915-2026 (ceiling = tenders).
- Tests: unit `test_faser_...`, `test_incm_...`, `test_the_checks_leave_plausible_figures_alone`; integration
  `test_the_procedure_check_sets_aside_incm_without_a_ted_request_and_a_second_run_writes_nothing` (award row an estimate,
  API reason, out of the supplier's contract sums, idempotent), `test_the_lots_check_sets_aside_faser_when_ted_answers_its_tenders`;
  web `lib/wp108.check.ts` (the notes).
- After (once run): FASER PLN 7,247,040 contract (leaves the PL top); INCM EUR 1,450,000 estimate, out of the contract sums
  (the Portuguese Army's 1.17 bn falls by 1.159 bn), its page says what the award states and why it is not used.

### 2. Re-read versions not tagged (11 Spanish "Amended" of 14-15 October; videoscopio 2812)

- Before: 12 PLACSP versions of 14-15 October (production, read only), all with the previous version unstamped and this one
  stamped (the older mapping, `db.older_mapping`), value / 1.21 (11) or / 1.07 (1, IGIC: 2026/EA14/00002782E), legal basis
  and mostly the publication date moved, and also the source's status code (EV/PUB to ADJ/RES: the award). The WP-103 rule
  (tag_rereads and `upsert_opportunity`) tags a whole version only when every changed field is the mapper's, and `status`
  is the mapper's only when the source's code did not move: these 12 were left out. Cause: the award in the same version,
  not the IGIC rate or the dates (both were already covered).
- Change: never touching a version row (notes only). New note kind `remapped_fields` with a `fields` column (migration
  0120): the mapper fields of such a version are noted (`db.mapper_fields`), its status change stays the publisher's.
  Beside a real change a value counts as the mapper's only where it moved by a Spanish tax ratio (VAT 21/10/4 %, IGIC 7/3 %):
  2026/EA15/00002526 went up eightfold with its deadline and keeps its value line. `upsert_opportunity` notes new
  versions the same way; `ops/tag_rereads` notes those written before (report by default, `--yes`), and reports the
  ratios. Readers: `tenders.timeline` splits such a version (the noted fields fold into the counts and the change list and
  are a correction entry on the page); every reader of the archive (page, /changes, feeds, digest, amendment counts) goes
  through it. A reader that does not know the kind sees the version as before.
- Production report (the tag_rereads candidates as SQL, observed since 12 October): 15 versions, all with a real change
  beside the mapper's fields: the 12 above (ratio 1.21 x11, 1.07 x1), 2026/EA15/00002526 (legal basis and procedure noted,
  value x8 and deadline stay), 2026/AR46U/00001420E and 2026/AR44U/00003632E (legal basis, procedure; status PUB/EV to RES
  stays). `--yes` writes 15 notes, no version row.
- Tests: unit `test_mapper_fields_split_a_reread_that_came_with_the_award`,
  `test_videoscopio_the_noted_fields_are_a_correction_and_the_award_the_publishers_change`; integration
  `test_a_reread_that_came_with_the_award_notes_the_mapper_fields_and_keeps_the_award`,
  `test_tag_rereads_notes_the_mapper_fields_of_the_versions_written_before` (IGIC, notes only, second run writes nothing).
- After (once run): 2812 lists "Status changed from Open to Awarded" as the buyer's; the value / 1.21, legal basis and
  publication date as a DefenceGate correction of 15 Oct; /changes shows the status line only.

### 3. "2 corrections (below)" with nothing below

- Before: the corrections were inside a closed `<details>` (WP-90's fold); the persona's page text shows the count and the
  summary and nothing else.
- Change: each correction in one open line under the version history, with date, fields, before and after
  (`award-lines.correctionLines`: "Corrected 15 Oct 2026: Estimated value EUR 45,980 to EUR 38,000; Published 28 Sep 2026 to
  3 Sep 2026"); the fold with the full entries stays under it (WP-90's spec holds it closed, unchanged).
- Tests: `lib/wp108.check.ts`, Playwright `e2e/wp108.spec.ts` (two lines visible on the demo notice 11, fold closed).

### 4. "Publication date moved back" with the award shown as a buyer change

- Change: on the page (`timeline(corrections=True)`), a publication date that moved in the version that made the notice
  awarded is not a line of the buyer's change: the version carries it as `redated` and the page says "The source dated the
  notice again when it published the award (...): not a change by the buyer". The change list, feeds and digest never
  listed the publication date (`changes.CHANGE_FIELDS`); what they did list for 2812, the value / 1.21, goes with item 2.
  WP-52's fold of later corrections into that line is unchanged (the counts keep it).
- Tests: unit `test_a_publication_date_moved_with_the_award_is_the_source_redating_not_an_amendment`; wp108.check
  (`redatedLine`, rendered under the version).

### 5. Weekly digest shows the cancelled AU ZLT-50 as new

- Before: a stored issue keeps each tender as it was in that week; /changes and its feed say "Cancelled since" (WP-103),
  the digest did not.
- Change: `weekly_digest.with_current_status` adds each tender row's effective status now (`DigestTender.statusNative`,
  one query when the issue is served); the digest page tags a new notice cancelled since "Cancelled since", the digest feed
  writes "New notice (cancelled since): ...".
- Tests: integration `test_the_digest_says_the_status_of_a_notice_now`; wp108.check (`cancelledSince`, headlines, the tag).

### 6. Award labels in search and on the page (220199-2026 search, V7000 375694-2026)

- Change: `tender-status.searchStatusLine` (the status of a notice that is not open, the deadline of an open one) and
  `searchTenderNoun` ("tender" rather than "open tender" when a match is not open), used by the search page's row line and
  "See ..." link only (the page is WP-110's: two expressions changed, nothing else). `noticeValueLabel`: an awarded notice's
  own TED total where no award value was read is "Value in the award notice" with "The total the award notice states; not
  told apart as a contract value or a framework ceiling", never "Estimated value ... Total" (tender page, its metadata
  description, list cards).
- Tests: wp108.check.

### 7. Tender CSV value kind: empty vs "not stated"

- Before: rows without a value had an empty `value_kind`, award totals of unknown kind "not stated" (p07 t-it-2025.csv:
  57 such rows, all with a value; 24 empty without one).
- Change: one word, `VALUE_KIND_NOT_STATED` = "not stated", for both: every row says its value kind.
- Tests: wp108.check (and wp100/wp106 checks unchanged and green).

## Files touched outside the package's list

- `web/app/(public)/search/page.tsx` (WP-110's page): the row line and the "See ..." noun call the two new label functions.
- `web/components/dg/cards.tsx`: the list card's fallback value label calls `noticeValueLabel`.
- `web/components/digest/digest-view.tsx`, `web/lib/digest.ts`: the "Cancelled since" tag and feed line (item 5).
- `web/lib/export.ts`, `web/lib/export-tables.ts`: item 7.
- `backend/dgate/tenders.py`: `timeline` (items 2-4), `TenderVersion`, `AwardValue`, `awarded` / `award_summaries`.

## Runs (test copy)

- Backend: ruff clean; unit 3,775 passed; integration 1,365 passed (918 s).
- Web: tsc clean; all lib checks (`scripts/run-checks.mjs`, wp108 included) green; `next build` green; Playwright wp108,
  wp90, wp95, wp86, wp96: 48 passed, 1 failed on the first run (wp86 mobile header search, a 60 s timeout waiting for the
  menu's search box, 4 workers on a shared machine), green on the re-run of wp86 + wp108 (15 passed). Not touched by this
  package.

## Ops to run on production (orchestrator)

1. Deploy (migration 0120 runs with `migrate`).
2. `python -m dgate.ops.tag_rereads` (report: 15 versions, all "mapper fields only"), then `--yes` (15 notes).
3. `python -m dgate.ops.award_values --no-fetch` (report: step 3 sets aside 5 by the procedure check), then `--no-fetch --yes`.
4. `python -m dgate.ops.award_values --all` (asks TED, about 90 requests: the lots check, FASER among it; also WP-103's
   pending `--all`), then `--all --yes`. The report's `ted_set_aside_lots` is the count item 1 asks for.

## Open

- The lots check's production count is known only after step 4 (no TED request from here).
- The search page's "See ..." link still leads to the open list (WP-110); only its words follow the matches now.
