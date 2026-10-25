# WP-119 self-check: data rules and repair of the 25 October writes

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP119.md`; evidence `D:\DEFENCEGATE TESTS\verify-oct25\data\`.
Branch `wp-wp119` from `integration`. No migration. Production was read only (SELECTs through the postgres container,
30 s timeout); the expected counts below are those read-only queries run with the branch's rules on 25 October 2026
(the new steps are not deployed, so no ops report could run there). Every repair is a report by default and writes only
with `--yes`; every write is logged in `organisation_repair` (or `award_notice.value_set_aside`) with what it replaced.
Natural persons are never named; no `opportunity_version` row is written.

## 1. Award values, rule "lots" (major)

- Before: 16 notices with `value_set_aside_reason = 'lots'`; 11 of them served an absurd lot sum for a plausible total
  (Marine Alutech 676175-2026 EUR 2 for 76 m, 639939-2025 EUR 2 for 35 m, Surcom SEK 13, Embraer USD 230, PIT-RADWAR,
  CONCEPT, WIL, DSA CZK 34,000 for 120 m, 494823-2026 CZK 229,586 for 1.95 bn, 175814-2025 HUF x107, 542411-2026 x206).
- Cause: `award_value.implausible_against` (over 100 times from 10 million) let any smaller lot or tender sum replace the
  notice total, and the WP-108 branch for "TED answers the tenders only" let the parts stand whenever they were not a
  unit error of the total.
- Change (`award_value`): `unit_error_of(amount, parts)`: a clean thousandfold, or a hundredfold with the cents read as
  units (not a round hundredfold), from 1 million. A lot or tender sum replaces a total only then (`_checked`). Where TED
  answers only the parts and they sum to under a hundredth of the notice's own total, the total stands (a placeholder).
  FASER 394720-2025 (x1000), 107790-2025, 677494-2026 (x1000), 313429-2026 (PLN 741,576,016.16 = 7,415,760.16 x100) and
  142545-2026 (120,969,785 = 1,209,697.85 without its separator) stay set aside: the digits are the same.
- Repair: `python -m dgate.ops.award_values --no-fetch` step 5 `run_recheck` (no TED request): every lots/procedure
  set-aside is checked again from `value_set_aside` (the original) and the standing value (the parts); where the rules
  no longer choose it, the original stands again, and the award row of a one-winner notice with it.
- Expected: `recheck_lots 16, recheck_lots_restored 11, recheck_procedure 3, recheck_procedure_restored 1,
  recheck_award_rows 12` (all 12 are one-winner notices). Step 3 (`run_set_aside`) then finds 0 new set-asides
  (checked: no held contract/framework value is a new cents-unit error of its procedure's estimate).
- "5 vs 3 procedure set-asides": the WP-108 report (`--no-fetch`, 24 Oct) counted 5 by the procedure check (499753,
  502578, 313429, 107790, 451107). The `--all` re-read that followed asks TED, and the lots check runs before the
  procedure check, so 313429-2026 and 107790-2025 were set aside against their own tenders (reason `lots`, same figure
  set aside). 3 + 2 = 5: nothing was lost.
- 451107-2025 / award 122907: EUR 23,918.70 is the estimate of the procedure's 2023 contract notice 784584-2023 (same
  eForms procedure 20641a3c-...); x958 is no unit error, and under the 2009/81 threshold no TED defence framework is
  estimated at 24 k. The procedure check now needs a billion and x100, or a unit error (INCM's 1.159 bn vs 1.45 m stays).
  Repaired by step 5: back to EUR 22,922,861, kind framework (title "Raamovereenkomst").
- Tests: unit `test_a_lot_sum_of_a_few_units_never_replaces_the_notice_total`,
  `test_a_lot_sum_replaces_the_total_only_when_the_total_is_a_clean_unit_error_of_it`,
  `test_the_procedure_check_needs_a_billion_or_a_unit_error`; integration
  `test_the_recheck_puts_back_the_totals_the_narrowed_rules_no_longer_set_aside` (Marine Alutech, FASER, 451107; a
  second run writes nothing). WP-108's tests pass unchanged.
- Not changed: the 464 current EUR award rows under EUR 100 are 431 PLACSP contract + 25 PLACSP framework + 8 TED
  rows, none set aside by these rules (PLACSP amounts are the platform's own); see open items.

## 2. Buyer as winner

- Before: 4 awards `buyer_as_winner`; 9359 (SPIE FACILITIES EUR 4 m, buyer ESID Rennes) through `buyer_family_member`
  296433 -> 219944 `twin_notice`, 3570 (DEF OUEST vs PFC Ouest, EUR 442,000) on the one word "ouest".
- Change: `awards.same_name_as_buyer` needs more than one shared word or the whole name; `awards.is_buyer_body` ignores a
  `twin_notice` family; `ops.buyer_families.all_groups` never puts a copy's buyer row into a twin's family when the row
  wins contracts (an award row) and its name is no public body's (SPIE; the university rows with awards stay public).
- BOAMP 24-21330: the mapper reads `nomacheteur` verbatim (`normalise.from_boamp`); the stored notice names SPIE
  FACILITIES as the buyer, so this is the source's own field (the payload is in the raw store, not in the database, and
  was not read: see open items).
- Repair, in this order: `python -m dgate.ops.buyer_families --changes` (report: `remove 296433 -> 219944 twin_notice`;
  any other line is drift since the last run), then `--yes`; `python -m dgate.ops.org_repair --step winners-check`
  (report: `excluded_as_buyer 4, counted_again 2, awards [(3570, 841870-2025), (9359, 109763-2024)]`), then `--yes`.
  9508 (Norwegian Defence Materiel Organisation, same organisation) and 4346 (Het Ministerie van Defensie) stay.
- Tests: unit `test_a_name_match_with_the_buyer_needs_more_than_one_shared_word`; integration
  `test_a_company_put_into_its_buyers_family_by_a_twin_notice_is_counted_again` (family row removed, both counted, the
  winners step leaves them, the undo restores).

## 3. False identifiers

- Before (organisation_repair, 10,276 `clear_false_identifier`): 167 PL 19-digit NIP+REGON values; 10 ES rows with a
  foreign-prefixed value; 220 PL 6-8 digit values.
- Change: `normalise_identifier` keeps the NIP of a NIP+REGON / REGON+NIP pair (`normalise.pl_number_pair`, each by its
  check digit: 165 of the 167 split validly, 2 do not); `normalise.pl_unpadded_regon`: a REGON stored without its
  leading zeros, restored only when the 9-digit form passes the REGON check digit and the value is neither a TERYT
  code (most of the 220 are gmina TERYT codes, e.g. 3024022 Gmina Duszniki) nor a case number ending in a year. A KRS
  number has no check digit, so a short one cannot be told from a case number: never restored (honest answer to
  "may be KRS"). `supplier_identity.foreign_vat`: an EU VAT number of another country (VIES shapes) or GB; the
  false-ids step moves it to `vat_number` on a company row (never a public body: "RO..." case numbers of Gmina
  Radymno), and `awards._attach_reg` keeps such a number as the winner's VAT number from now on.
- Of the 10 ES values the verifier listed, 7 are valid VAT numbers (CZ, DE Bruggemann, FR, GB x2, PT, BE); Scienion's
  "DE" + 7 digits is no German VAT number (9 digits), and the SE and the second DE value are words, not numbers.
- Repair: `python -m dgate.ops.org_repair --step restore-ids` (report), then `--yes`, after `namesakes`. Expected:
  `nip_regon_pair 165` (72 already there on the live row, 64 held by another row of PL, 29 restored: 21 on the live
  row, 8 on their own merged row), `unpadded_regon 16` (1 already there, 8 held by another row, 7 restored: 3 live, 4
  own), `foreign_vat 7` (7 restored on the live row). Undo: `--undo FROM TO` clears exactly what was restored.
- Tests: unit pair/REGON/VAT/plan tests; integration `test_cleared_numbers_the_rules_keep_are_restored_from_the_log_and_
  the_undo_clears_them`, `test_the_false_ids_step_moves_a_foreign_vat_number_and_respells_a_pair`.

## 4. Rejoin of namesakes

- Before: 'powiat tomaszowski' (head 304079, 36 rows): two counties.
- Change: `org_repair.ambiguous_name`: the ten Polish powiat names two counties bear (bielski, brzeski, grodziski,
  krosnienski, nowodworski, opolski, ostrowski, sredzki, swidnicki, tomaszowski), or a unit's name whose every word of
  three letters or more is a public-unit word (no place). Such a group is decided `namesake`: false numbers cleared,
  never merged. Parallel case-number series were measured and dropped as a signal: 110 rejoin groups hold two or more
  case prefixes, mostly one body's departments (hospital DAZ/DEZ, Narodowy Bank Polski).
- Repair: `python -m dgate.ops.org_repair --step namesakes` (report lists every group), then `--yes`: `ops.undo_merges`
  for exactly those rows (new `only` filter; candidate rows of those pairs only). Expected: 12 groups, 84 rows:
  powiat tomaszowski 36, zarzad drog miejskich 12, zaklad remontow i konserwacji drog 10, powiatowe centrum zdrowia w
  restrukturyzacji 8, powiatowy osrodek dokumentacji geodezyjnej i kartograficznej 7, miejskie przedsiebiorstwo
  oczyszczania 4, przedsiebiorstwo komunalne spolka z o o 2, and 1 each: direccion general de servicios (ES), zaklad
  wodociagow kanalizacji i energetyki cieplnej, miejski zaklad wodociagow i kanalizacji spolka z o o, powiatowy zarzad
  drog, powiat opolski.
- Tests: unit `test_names_two_public_bodies_bear`, plan test; integration
  `test_a_rejoin_under_a_name_two_counties_bear_is_undone_and_others_stay`.

## 5. Rejoin head choice (PIC and participations)

- Before: 24 groups whose absorbed row held the PIC and every participation (Universitat de Girona 138, URV 137, NCBR
  95, IRB Barcelona 91); 836 participations on merged rows, 561 of them on rejoined rows.
- Change: `db.merge_organisations` -> `db.carry_to_head`: the head takes the PIC (with its method) and the VAT number it
  lacks, each move logged on the absorbed row (`merge_moved_pic|vat`); `ops.undo_merges.move_back` puts them back on an
  undo. With the PIC on the head, the CORDIS loader (`networks`, `resolution.cascade._by_pic`) finds the head directly.
- Participations: NOT re-pointed. The brief asked them to follow the merge, but WP-41 made "a merge re-points nothing
  of the networks" a tested rule (`test_wp41_networks::test_rows_with_one_key_are_merged_into_the_row_with_the_pic_and_
  the_directory_counts_them_once`, "nothing re-pointed or deleted": reversible, the directory reads them through
  `merged_into` and counts them on the live row). Moving them failed that test in the batched run; the test was not
  changed. The directory already shows the 24 groups correctly. Owner decision needed if participations should move
  (then that WP-41 assertion changes with it).
- Repair: `python -m dgate.ops.org_repair --step pics` (report), then `--yes` (directory rebuilt). Expected:
  `rejoined_rows_holding_something 25, heads 24, pic 24, vat 20, awards_twice 0, participations_read_through_the_merge
  561`.
- Tests: integration `test_the_head_of_a_rejoin_takes_the_pic_and_the_undo_gives_it_back`,
  `test_a_merge_now_carries_the_pic_and_counts_a_winner_named_twice_once`.

## 6. Sign Polska / Sign 4 Security, a winner counted twice

- Before: 7 notices with one live winner twice: Sign (262623-2024, 224193-2025: two companies merged by
  `company_number`, their stated names 0.88 alike through one address), Vogtmann-Herold, Works 11 x2, Norrenbrock,
  Magtel (spellings of one company).
- Change: `supplier_dedupe._pair_conflict`: two winners of one notice are not one company unless their names are one
  name typed differently (`spelling_variants`: same key, same without spaces, keys two characters apart) or a person
  read them (`REVIEWED`); `db.carry_to_head` marks an absorbed row's award on a notice the head already won
  `excluded_reason = 'same_winner_twice'` (counted once; the undo clears it).
- Repair: `python -m dgate.ops.org_repair --step twice` (report), then `--yes`. Expected: `notices 7,
  rows_taken_apart [430144]` (undone through `ops.undo_merges`, supplier_dedupe's methods), `awards_counted_once
  [184825, 184977, 185356, 185849, 19402]` (the row on the live organisation stays; Norrenbrock's two absorbed rows keep
  the lower id 184824). No award or version row is deleted.
- Tests: unit `test_two_winners_of_one_notice_are_merged_only_as_spellings_of_one_name`; integration
  `test_two_companies_named_side_by_side_are_taken_apart_and_spellings_counted_once`.

## 7. TenderNed main CPV in the archive

- Before: 145 of 481 TenderNed rows: the current version's `cpv_codes` keep the old first code; the serving row has
  the flagged main code first (WP-113, an attribute update).
- Choice: show the corrected main code consistently, no new version. The archive compares a CPV list as a set
  (`db.same_value`), so a new "remapped" version would record a change the archive's own rule says is none, 145 times.
  `/v1/opportunities/{id}/versions` now lists the serving row's main code first in every snapshot that holds it
  elsewhere, with the note `{"kind": "main_code", ...}` saying so (`api.main_code_first`). The version rows are not
  touched; the tender page's history (`/v1/tenders/{slug}/versions`) already drops a re-ordered CPV line.
- Test: unit `test_the_archive_snapshot_lists_the_serving_rows_main_code_first`; integration
  `test_the_archive_lists_the_serving_rows_main_code_first_with_a_note` (the stored payload unchanged).
- No ops step.

## 8. /data "Refused since" for pl_ezam

- Before: 25 Oct 06:51 (the first run whose message carried the refusal text, i.e. when the check was deployed).
- Change: `funding.run_signals`: the refusal row goes back over the runs before it that fetched nothing and did not
  succeed. From ingest_run: success 446 (23 Oct 10:27), empty partial runs 460-469 from 24 Oct 06:45, refusal text
  from 482. Expected on /data after deploy: "Refused since 24 Oct 2026 06:45 UTC".
- Test: integration `test_refused_since_is_when_the_runs_stopped_fetching_not_when_they_first_said_why`.

## Ops to run on production (orchestrator), in order

1. Deploy (no migration).
2. `python -m dgate.ops.award_values --no-fetch` (report: step 5 as in item 1), then `--no-fetch --yes`.
3. `python -m dgate.ops.buyer_families --changes`, then `--yes` (item 2).
4. `python -m dgate.ops.org_repair --step winners-check`, then `--yes`.
5. `python -m dgate.ops.org_repair --step namesakes`, then `--yes`.
6. `python -m dgate.ops.org_repair --step pics`, then `--yes`.
7. `python -m dgate.ops.org_repair --step restore-ids`, then `--yes`.
8. `python -m dgate.ops.org_repair --step twice`, then `--yes`.
   Each `--yes` of org_repair prints its undo window. Steps 5, 6 and 8 rebuild the directory table.

## Tests run (batched scope)

In D:\DEFENCEGATE TESTS\wp119 (own venv, Postgres 17 on 55519): ruff clean; unit suite green; integration: the 55
files that touch the changed modules (award_values, buyer_families, org_repair, supplier_dedupe, undo_merges,
merge_organisations callers, awards, versions API, health): 697 passed, 1 failed (the WP-41 participation assertion,
see item 5); after the fix the merge-related files (wp119, wp41_networks, wp115, wp96, wp104, wp111, wp74, wp76,
buyer_cleanup, networks_resolution, wp72, wp43_directory) 108 passed. The full suite is the orchestrator's.

## Open items

- BOAMP 24-21330 payload (raw store) not read: whether DILA's own `nomacheteur` names SPIE (a mandate) or our landing
  shifted a field; the family rule no longer depends on it.
- 64 PL NIP+REGON pairs and 8 short REGONs are held by another live PL row: probably the same body under another
  spelling; left for the merge queue, not merged here.
- Participations on merged rows (836) stay there by the WP-41 rule (item 5): owner decision if they should move.
- 431 PLACSP award rows under EUR 100 (unit prices or placeholders) are counted in contract sums; not in this package.
