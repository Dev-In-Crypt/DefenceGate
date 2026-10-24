# WP-115 self-check: organisation identifiers and buyer records

Branch `wp-wp115` from `integration` (ea00dca). Findings: coverage audit of 24 October 2026, db section
(`D:\DEFENCEGATE TESTS\coverage-oct24\db\problems.csv`). Production was read only: short SELECTs through the postgres
container (each under 30 s, `default_transaction_read_only`), no script in any production container. The dry-run
figures below are those SELECTs, written to mirror the ops module's rules; the module itself runs on production only
when the orchestrator starts it.

## 1. Case references stored as registration numbers

Before: `normalise_identifier` accepted any value with five digits, so a Polish case reference ("DEZ/26/019/2020",
"ZP.271.2.2021") stated in TED's buyer-identifier field became `national_reg_no`, and `_attach_identifier` made a new
row for every new reference: organisation 8302's name on 340 rows, 31924 on 204, 9270 on 201. Live rows with a
non-numeric number: 4,346 PL, 11,952 ES (most ES ones are valid CIFs; 4,088 others are 14-digit platform codes).

Change: `normalise.normalise_identifier` (the one function every path uses: buyer resolution, award winners, the
networks cascade, supplier identity) checks PL and ES numbers against their register: PL NIP (10, check digit),
REGON (9 or 14, check digit), KRS (10 with leading zeros); a PESEL (11) is refused. ES NIF: DNI, NIE, CIF by check
character; "ESA28015865" is read as the CIF A28015865. Other countries are unchanged. `ops/org_repair --step
false-ids` clears the numbers that fail (logged in the new `organisation_repair` with their value, except a number
shaped like a person's), merges each row split only by a false number into the row of the same name and country that
holds a valid number or none (`false_identifier_rejoin`, 0.95, the exact-name match it would have had), holds a group
with two numbers of one register (two bodies; a NIP beside a REGON is one body), and lists every group by ids.
`--undo FROM TO` reverses the merges (`ops.undo_merges`) and restores the numbers.

Dry run on production (SQL mirror, 24 Oct):

| country | decision | groups | rows | numbers cleared | rows rejoined | largest |
|---|---|---|---|---|---|---|
| PL | rejoin | 1,154 | 6,024 | 4,588 | 4,445 | 340 (8302) |
| PL | held (two numbers of one register) | 88 | 629 | 315 | 0 | 40 |
| PL | clear only (no sibling) | 374 | 374 | 374 | 0 | 1 |
| ES | rejoin | 2,312 | 4,719 | 2,441 | 2,406 | 24 |
| ES | held | 20 | 63 | 22 | 0 | 5 |
| ES | clear only | 2,549 | 2,549 | 2,549 | 0 | 1 |

Every group (country, decision, rows, cleared, first id): `D:\DEFENCEGATE TESTS\wp115\false-ids-groups-prod.psv`
(6,497 groups; ids only, no names). The 340-row hospital: 338 numbers cleared and rejoined into 8302, its NIP and its
REGON rows stay.

Tests: `tests/unit/test_wp115_org_identifiers.py` (register checks, plan decisions), integration
`test_wp115.py::test_a_case_reference_does_not_split_the_buyer`, `::test_rows_split_by_false_numbers_rejoin_and_the_undo_restores_them`.

## 2. Merge chains

Before: 3 rows merged into a row that is itself merged (88258>96915>78656, 430892>430736>429896, 435421>432402>432657),
awards on them; one-step readers (`COALESCE(merged_into, id)`) land on a merged row.
Change: `db.merge_organisations` re-points every row already merged into the absorbed one (`db.repoint_merged`,
logged with the old pointer; `ops.undo_merges` puts them back when it undoes the later merge). `org_repair --step
chains` flattens the stored chains. Dry run on production: 3 rows, 4 awards on the chain members themselves.
Test: `test_wp115.py::test_a_merge_never_leaves_a_chain_and_old_chains_are_flattened`.

## 3. Contact details in names and aliases

Before: 805 names with "tel <number>", aliases with 95 e-mails and 693 phone numbers (audit regexes).
Change: `normalise.strip_name_contacts` cuts a telephone, fax or e-mail block and what follows; `normalise_org_name`
and `db._resolve_organisation` (the alias's raw name) apply it, so no new row carries one. `org_repair --step contacts`
cleans stored names and aliases, prints counts only and keeps no copy. Production (coarse SQL filter, an upper bound):
960 organisation rows, 1,029 aliases, 96 with an e-mail. `docs/DATA_PROTECTION.md` inventory updated.
Tests: unit `test_contact_block_cut_from_names`, integration `test_contact_block_is_not_stored_with_a_new_buyer`,
`test_contact_details_are_cleaned_from_stored_names_and_aliases` (asserts no value appears in the output).

## 4. Organisations linked to nothing; the merge queue

What they are (production, 24 Oct, five id-range SELECTs): 342,476 live rows with no notice, award or participation.
By first alias: TED exact-name 225,045, BOAMP 33,422, no alias at all 27,297 (rows made by `_attach_identifier` /
the namesake guard, which write no alias: the false-number rows of item 1 are among them), pl_atlas 19,786, de_bkms
11,219 (+1,551 by identifier), es_placsp 10,743, pl_ezam 5,944, es_placsp_agg 5,715, TED by identifier 874; 835 are
flagged defence buyers (seed and derived lists). Creation path: `pipeline._finalise` resolves the buyer of every
fetched notice before the classifier decides, and only defence-relevant notices are stored, so the buyer row of a
dropped notice stays.

Merge queue: of 129,684 pending candidates 125,442 involve an unlinked row, 98,931 two (identifier 38,989 of 48,923;
identifier_name_mismatch 25,940; same_name_different_identifier 24,175; trigram 9,645). They can be skipped without
deleting anything: a merge of two unreferenced rows changes nothing a reader sees. A pair with one referenced row
is still decided (a public parent body that publishes nothing heads its units' buyer family, WP-74).

Change in `ops/accept_merge_candidates`: pairs of two unreferenced rows are skipped and stay pending (`unlinked` in
the refusals); details are read 1,000 ids at a time; `statement_timeout` 60 s; a run merges at most 200 groups by
default (`--limit`). Root cause of the 5.5-minute statement: the `buys` test (`EXISTS ... opportunity WHERE
buyer_org_id = g.id`) had only the partial index `opp_buyer_org ... WHERE is_defence`; EXPLAIN on production shows a
sequential scan of `opportunity` per organisation. Migration 0127 adds `opp_buyer_org_all ON opportunity
(buyer_org_id)` (create it CONCURRENTLY first on production, as 0096).
Tests: `test_wp115.py::test_the_merge_queue_skips_rows_nothing_references`; wp72/wp76 merge tests give their bare
organisation rows a project participation (`tests/integration/wp115_links.py`) so their assertions stand unchanged.

## 5. The buyer as the winner of its own award

Before: TED 624641-2025, buyer 215 (Ministerie van Defensie, NL), award 4346 to 429647 "het ministerie van defensie"
filed as a Swedish supplier with a Swedish number.
Change: `awards.store_notice` skips a winner whose name has the buyer's words (`same_name_as_buyer`, checked before
resolving, so no row is made) or that resolves to the buyer's organisation or its buyer/directory family
(`is_buyer_body`); counted as `skipped_buyer_as_winner`. `org_repair --step winners` marks stored ones
`excluded_reason = 'buyer_as_winner'` (the row stays). Dry run on production: 5 of 48,541 current awards (1 same
organisation, 1 same family, 4 same name; overlapping).
Test: `test_wp115.py::test_the_buyer_is_not_the_winner_of_its_own_award`.

## Files outside the package's list

- `dgate/awards.py` (item 5: the award reader), `dgate/ops/accept_merge_candidates.py` (item 4),
  `dgate/ops/undo_merges.py` (restores pointers `repoint_merged` moved), `docs/DATA_PROTECTION.md`.
- Test fixtures changed, assertions unchanged: made-up Spanish CIFs and a Polish NIP given valid check digits
  (`test_placsp_awards.py`, `test_placsp_award_twins.py`, `test_networks_resolution.py`); wp72/wp76 bare rows linked.
- e-Zamowienia and PLACSP mappers: they set no buyer identifier; nothing changed there (WP-113's fields untouched).

## Ops to run on production (orchestrator)

1. `CREATE INDEX CONCURRENTLY IF NOT EXISTS opp_buyer_org_all ON opportunity (buyer_org_id);` then migrate (0127).
2. `python -m dgate.ops.org_repair` (all reports), then `--step false-ids --yes`, `--step chains --yes`,
   `--step contacts --yes`, `--step winners --yes`, at night. Expected: about 10,290 numbers cleared, 6,851 rows
   rejoined, 3 pointers, under 1,000 names and 1,029 aliases cleaned, 5 awards marked. It prints its undo window.
3. `ops.accept_merge_candidates` from now on runs in batches of 200 groups by default.

## Open

- Same-name rows without numbers (17,191 groups) are not merged here; only rows split by a false number are.
- A cleared number shaped like a person's (PESEL, DNI/NIE) is not kept, so its clearing has no undo.
- The 14-digit Spanish platform codes are not NIFs and are cleared; if they turn out to identify bodies, they belong
  in a column of their own, not in `national_reg_no`.
