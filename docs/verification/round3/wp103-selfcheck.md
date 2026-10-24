# WP-103 self-check: award and value correctness (round 3, 24 October 2026)

Branch `wp103` (from `integration`). Evidence: D:\DEFENCEGATE TESTS\ux-oct24 (SUMMARY.md WP-103, NOTES-received.md,
p01/p04/p05/p07/p10 problems.csv, p10 ted-verify.json, p07 indra-calloffs-as-ceiling.txt). Production was read only
(SELECTs in `BEGIN READ ONLY`, landed payloads read from the raw store inside the worker container; nothing fetched from
TED or PLACSP, nothing written). Test copy D:\DEFENCEGATE TESTS\wp103 (Postgres 17 on port 55503).

## Items

### 1. Value kind: TED framework maximum only is a ceiling (STRABAG 638010-2024) and result = framework maximum (Arquus 38915-2026)

- Before: `award_notice` 112981 (638010-2024) EUR 280,000,000 kind `contract`; 130453 (38915-2026) EUR 2,449,392,735
  `contract`. The award records landed on 18 October carry no value field at all (loaded before WP-95), so the kinds came
  from the stored total and the title. TED states the maxima as `framework-maximum-value-lot` (p10 ted-verify.json),
  and the title of 638010-2024 is misspelt "Rahmenvereinbarong", which the title rule missed.
- Change: `award_value.TED_VALUE_FIELDS` also asks TED's own names `framework-maximum-value-lot` (BT-709) and
  `tender-value` (BT-720), read alike; the title rule reads `rahmenvereinba*`. `ops/award_values --all` asks TED again
  for every notice with winners (not only those without a kind). A framework maximum present makes the value a ceiling
  whatever the result value says: Arquus is shown as "Framework ceiling" with the page's existing sentence, never summed.
- Tests: unit `test_teds_own_field_names_for_the_framework_maximum_and_the_tenders_are_read`,
  `test_the_widened_rule_keeps_frameworks_and_plain_titles`; integration
  `test_all_asks_ted_again_and_reads_teds_own_name_of_the_framework_maximum`.
- After (on production, once run): STRABAG and Arquus framework ceilings; STRABAG leaves the top of the DE ranking.

### 2. Call-offs "CB ... AM", "Basado AM", "CBAM" are contracts (Indra, EUR 59.5 m)

- Before: 29 Indra call-offs held as `framework` (titles "CB Cuarto AM", "5º Basado AM 202340A1", "20º CB en el AM",
  "CB Nº2 Acuerdo Marco", ...): the WP-95 rule needed "CB" right before "AM" and "basado en"; "AM 2023..." then read as
  a framework.
- Change: a title that has a call-off word (`CB`, `CD`, `basado`, `derivado`) and a framework word (`AM`, `acuerdo
  marco`) anywhere is a call-off (`award_value._CALL_OFF_WORD`, `_FRAMEWORK_WORD`). `ops/award_values` step 4 turns the
  PLACSP rows held as framework whose title now reads as a call-off into contracts.
- Measured on the 1,847 PLACSP award rows held as framework on production (titles exported read-only): 612 become
  contracts, EUR 306,793,827; all 29 of the persona's Indra list among them. A random sample of 25 flipped titles and
  15 kept ones read by hand: all flipped are call-offs, all kept are frameworks.
- Tests: unit `test_a_call_off_that_writes_cb_or_basado_apart_from_the_am_is_a_contract` (14 spellings); integration
  `test_award_values_sets_aside_the_implausible_figure_and_makes_call_offs_contracts` (Indra's call-off enters the sum,
  the framework stays out).

### 3. Implausible outliers flagged and kept out of the top of value rankings (World Aviation 220199-2026)

- Before: `award_notice` 133044: EUR 7,274,615,930 `contract` for one lot estimated at EUR 7,317,073.17 (the serving
  row already kept the estimate, `normalise._CONTRADICTED_*`); top of `/v1/suppliers?sort=value-EUR`.
- Change: `award_value.contradicted`: a figure of a billion or more, over a hundred times the notice's own estimate, is
  set aside; the estimate stands as kind `estimate` (never summed, not in the value orders). The figure is kept in
  `award_notice.value_set_aside` (migration 0115) and the tender page says it ("The award states EUR 7,274,615,930, over
  a hundred times the buyer's estimate: most likely an entry in the wrong unit, so it is in no sum or ranking").
  `ops/award_values` step 3 (no TED request) applies it to what is held, then renews the value orders.
- Expected on production: 3 notices (220199-2026 contract; 622840-2026 and 593313-2026, ceilings of EUR 5.39 bn and
  6.65 bn over lot sums of EUR 1.75 m and 2.7 m).
- Not done: the PLN 600,000,652 monument contest (pl_atlas 33625) is an open notice's estimate, not an award; there is no
  estimate to contradict it, and no rule by product code was found that would not also hit real programmes. Its status:
  published 2025-10-24, it is served "Closed" from 25 October 2026 by the 365-day rule.
- Tests: unit `test_a_figure_its_own_estimate_contradicts_is_set_aside_and_the_estimate_stands`; integration (as 2).

### 4. VEAT winners and values (375694-2026) and recent TED awards without winners (728479-2026)

- Before: 375694-2026 is eForms subtype 25 (VEAT); `awards.AWARD_SUBTYPES` held 29-37 and E1-E6 only, so no VEAT of the
  eForms era was ever read (874 such notices of the defence scope unread). 728479-2026 (21 Oct, Spanish army uniforms)
  is kept by its listed buyer alone (scope supply); the loader read the core scope only, while the supplier map counts
  the whole defence scope (`award_set.NOTICES`): 22,171 can-standard notices of the defence scope had no read at all.
  And the TED award load is a command (`pipeline awards`), not a scheduled job: last runs 18 and 23 October.
- Change (second commit, after review): subtypes 25-28 are result notices. The loader stays core-scope only (owner
  decision of 22 October 2026; the widening of the first commit is reverted). The tender API says `winnersRead`; an
  awarded page whose winners were not read says so (`web/lib/award-lines.winnersNotReadLine`): a core notice "not read
  yet by DefenceGate; the original notice names the winners"; a notice outside the core scope (728479-2026) "not read
  by DefenceGate: winners are read for the notices of the defence core scope, and this notice is listed for its buyer
  only; the original notice names them".
- Scheduled (owner, 24 October 2026): `ted_awards_daily` in the worker at 14:10 UTC (no other job holds hour 14: ingests
  04-07, health/controls 07, twins/families/digest 09-11, Sunday requalify 12, backups/networks 02; warm_lists at :50),
  `run_awards(limit=1500)` (DGATE_TED_AWARDS_HOUR / _MINUTE / _LIMIT): 15 requests of 100 plus at most one document per
  older-format notice, under 30 minutes; `ingest_run` under `ted_awards` with the floor set to every notice asked (one
  TED does not return makes the run partial); `refresh_award_twins` and the supplier value orders after it, as the CLI.
  Also `python -m dgate.worker --once ted-awards`.
- Tests: unit `test_veat_notices_are_result_notices`, `test_worker.py::test_the_ted_award_load_is_daily_bounded_and_away_from_the_heavy_jobs`
  (and the CLI job list gains `ted-awards`); integration `test_core_veat_notices_are_read_and_supply_scope_ones_are_not`,
  `test_the_tender_page_says_whether_the_winners_were_read`; web lib check `wp103.check.ts`.
- After (on production, recounted read-only under the core scope, 24 October 2026): the next award load has 461
  candidates, all eForms VEAT (subtypes 25-28) of the core scope; every other core result notice since 2023 is read
  already. Outside the core scope, 32,537 result notices stay unread by decision (23,647 eForms, 8,222 older-format
  can-standard, 413 eForms VEAT, 173 older VEAT, 82 others); their pages carry the out-of-scope line. 461 notices are
  5 requests: the first scheduled run drains it.

### 5. DefenceGate's own re-read versions are flagged and kept out of changes, feeds and counts

- Before: 17 PLACSP versions observed 15 October 06:48-06:49 changed value by / 1.21 (VAT; / 1.07 IGIC), set the legal
  basis and moved the publication date months back, without a note: the held version had been written by the mapper
  before 12 October (no entry stamp), and `db._same_entry_state` compares the held publication date with the new entry
  stamp, which differed because the entry had been stamped again since.
- Change: `db.older_mapping` (a held version without an entry stamp, an incoming one with it): with only mapper-owned
  fields changed the version is annotated `remapped` as it is written, the existing note kind every reader skips
  (`changes.NOT_A_CHANGE`, the timeline's corrections). No version is updated or deleted. `ops/tag_rereads` annotates the
  versions already written by the same rule (report by default, `--yes` writes, idempotent).
- Expected on production: 409 versions (380 observed 13 Oct, 17 on 14 Oct, 12 on 15 Oct). Five more of 15 Oct also
  changed the status with the source's own status code moving; they are a real status change and stay listed (their value
  line still shows the VAT difference: open item, a per-field note would be needed).
- Tests: unit `test_a_version_after_one_of_the_older_mapping_is_the_mappings`; integration
  `test_a_version_read_again_after_the_older_mapping_is_annotated_and_not_a_change`,
  `test_tag_rereads_annotates_the_versions_written_before_and_a_second_run_writes_nothing`.

### 6. Ley 24/2011 as the defence-directive signal

- Before: 2,861 notices with legal basis "Ley 24/2011 (defensa y seguridad)", none with `sig_legal_basis`.
- Change: `classify._LEGAL_BASIS_DEFENCE` reads Ley 24/2011 (Spain's transposition of 2009/81/EC), with its own reason
  line; the web chip reads it too (`web/lib/tender-basis.ts`).
- Data: `python -m dgate.reprocess --reclassify-serving --source es_placsp` (dry run) then `--yes`; and `--source
  es_placsp_agg`. Expected: the 2,861 rows gain the signal (some move from supply to core).
- Tests: unit `test_ley_24_2011_is_the_defence_directive`; integration `test_reclassify_serving_reads_ley_24_2011_as_the_directive`;
  web lib check `ui.check.ts`.

### 7. 2009/81 legal basis never "Weak defence signal"

- Before: Polish police 7.62 rounds and Cyprus police UAVs (2009/81/EC, security buyer) "Weak defence signal".
- Change: the level is the measured precision and is unchanged (its tests stand); the words (`confidence.label`) say what
  it rests on: "Defence and security directive, security buyer", "Defence directive, civil buyer", "Defence directive,
  unlisted buyer". "Weak defence signal" is left for notices without the directive.
- Tests: unit `test_a_directive_notice_is_never_called_a_weak_signal`.

### 8. Stale statuses

- PINs 2017-2024 "Planned": a planned notice with no deadline published over 365 days ago is served `expired`
  (`api.EFFECTIVE_STATUS_SQL` and its Python twin). Production: 4,613 of 5,196 planned TED notices, 409 of 599 pl_ezam,
  113 of 115 pl_atlas, 76 of 92 PLACSP, 44 of 48 BOAMP, 25 of 45 de_bkms. Read at query time: no data written.
- DE 283577 and the BAAINBw "open without deadline and link": de_bkms open notices with no deadline are mostly
  procedures without a call (`de-comp-wo-call`, `de-comp-neg-wo-call`, `de-restricted-wo-call`): an open notice of a
  `*-wo-call` procedure with no deadline is served `expired` (closed), 33 notices. The notice file of 22738298 states no
  issue or publication date and no link at all (checked in the landed XML), and its id is not an eForms id, so no page
  address can be built (WP-96 builds it for eForms ids); nothing to read. "beabsichtigte Beschränkte Ausschreibung" and
  "Interessenbekundungsverfahren" (41) are left open: they invite expressions of interest.
- 600 M PLN monument: see 3.
- Tests: unit `test_a_planned_notice_without_a_deadline_expires_after_a_year`,
  `test_an_open_notice_of_a_procedure_without_a_call_and_no_deadline_is_not_open`; integration
  `test_stale_planned_and_no_call_notices_are_not_planned_or_open`; the WP-52 test of the SQL stands.

### 9. Feed "New" vs page "Cancelled" (AU ZLT-50)

- Before: TED 700655-2026 first seen 12 Oct as open, re-mapped the same day to cancelled (a result notice with no award);
  the change list and feed said "New" only.
- Change: a new entry whose notice is cancelled since says so: "Cancelled since" tag on the page, "New (cancelled
  since): ..." in the Atom title, "Cancelled since." in its summary.
- Tests: web lib check `atom.check.ts`.
- Not done: winner and value on award rows of the change list (the list item is the tenders list item; WP-106 owns
  "Awarded with winner and value kind in lists").

### 10. "3 versions observed" shows one

- Before: 220199-2026: "3 versions observed" over Version 1 and "2 corrections by DefenceGate" (folded; the API does give
  each correction's changes).
- Change: the line counts the versions listed and the corrections apart: "One version observed so far, and 2 corrections
  by DefenceGate (below)."

## Files outside the package (smallest changes)

- `backend/dgate/api.py`: the effective status rule (8) and the Python twin's `procedure` argument.
- `backend/dgate/tenders.py`: `awarded()` returns `winnersRead` and `awardValue.setAside`; the two `effective_status`
  calls pass the procedure.
- `backend/dgate/db.py`: `older_mapping` in `upsert_opportunity` (5).
- `backend/dgate/worker.py`, `backend/dgate/config.py`: the daily `ted_awards_daily` job and its three settings (4).
- `backend/dgate/confidence.py`: the label words (7).
- `web/app/(public)/tenders/[slug]/page.tsx`, `web/lib/types.ts`: the not-read line, the set-aside sentence, the
  version count. `web/components/changes/change-entry.tsx`, `web/lib/atom.ts`: "cancelled since". `web/lib/tender-basis.ts`:
  Ley 24/2011 chip.

## Ops to run on production (orchestrator), in order

1. Deploy (migration 0115 adds `award_notice.value_set_aside`).
2. `python -m dgate.ops.tag_rereads` (report: 409 versions) then `--yes`.
3. `python -m dgate.reprocess --reclassify-serving --source es_placsp` (dry run) then `--yes`; the same for `es_placsp_agg`.
4. `python -m dgate.ops.award_values --no-fetch` (report: 3 set aside, 612 call-offs to contract) then `--no-fetch --yes`.
5. `python -m dgate.ops.award_values --all` (report; asks TED about 90 times) then `--all --yes` (STRABAG, Arquus and
   every kind derived without TED's fields).
6. Nothing to run by hand for the award load: `ted_awards_daily` (14:10 UTC) reads the 461 core VEAT notices on its first
   run. To run it at once: `python -m dgate.pipeline awards` (asks TED, 5 requests).

## Test changed to the new specification (not weakened)

- `tests/unit/test_worker.py::test_every_job_is_reachable_from_the_cli`: the expected job set gains `ted-awards`.

- `tests/integration/test_confidence.py::test_every_tender_carries_its_level_and_the_reason` computes the expected
  label with `label(...)`; it now passes the directive and the buyer class too (item 7). Same rows, same assertions.

## Checks (test copy D:\DEFENCEGATE TESTS\wp103, 24 October 2026)

- ruff: clean. Unit: 3672 passed. Integration (Postgres 17, port 55503): 1329 passed, 0 failed (17 min 41 s).
- Web: `tsc --noEmit` clean; `npm run check` (lib checks) all ok, including the new asserts in `atom.check.ts` and
  `ui.check.ts`.
- Second round (revert of the scope widening, daily award job, page-line checks; fresh container): ruff clean, unit
  3673 passed, integration 1329 passed (13 min 37 s); tsc clean; lib checks all ok incl. `wp103.check.ts`; `next build`
  exit 0 under the lock.
- Second round: the three tender-page lines (winners not read, set-aside figure, version count with the remapped
  corrections apart) are functions in `web/lib/award-lines.ts`, held by the lib check `wp103.check.ts`; a production
  build was run while holding D:\DEFENCEGATE TESTS\web-build.lock. No Playwright spec (the lib check covers the lines).
