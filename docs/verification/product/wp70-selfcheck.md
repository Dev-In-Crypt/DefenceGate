# WP-70 self-check: the missing CORDIS amounts from the official bulk exports

Branch `wp-wp70` from `integration` 135bbb0. Builder's own check; an independent verifier checks it again.

## What was built

* `backend/dgate/ops/cordis_bulk.py`: finds the current CSV packages on the data.europa.eu dataset pages, downloads them
  (operator command `--download`, streamed, one at a time, 1 s apart, refused if the disk would keep under 3 GB), reads
  `project.csv` and `organization.csv` streamed from the zip (54 MB of memory for all three), stages the rows of our
  projects in a session temp table, matches them to the stored participations, prints the changes by programme and
  reason, and with `--yes` writes them and rebuilds `organisation_network`. Dry run by default; idempotent.
* `docs/sources/cordis.md`, section "The bulk packages": URLs, sizes, dates, sha256, licence (quoted), shape, rules.
* Tests: `tests/unit/test_cordis_bulk.py` (16: reader, 13 rule cases, URL discovery, disk guard and no second fetch),
  `tests/integration/test_wp70_cordis_bulk.py` (4: fill, undouble, keep, resettle, dry run writes nothing, second run
  changes nothing, directory sum; an organisation met twice; a fill that would withhold its project; two of our rows on
  one PIC).

## Acceptance criteria

| # | Criterion | Met | Evidence |
|---|---|---|---|
| 1 | Find the current bulk URLs from the official dataset pages; document them and the licence (quoted) | yes | `bulk_urls` (tested with a fake hub); `docs/sources/cordis.md` table and licence quote from `cordis.europa.eu/about/legal`, label `COM_REUSE` from data.europa.eu |
| 2 | Download and read the organisation files streamed, no full load | yes | `download` streams to a `.partial` file and renames; `read_package` iterates `csv.DictReader` over the zip member; only the project-number map (85,128 short strings) is held. Measured on the server: 14 s for 466,792 rows, max RSS 54 MB |
| 3 | Fill only missing or wrong fields: amounts where ours are null or doubled (project + PIC + role), country where empty; never overwrite a stated value unless contradicted and documented; never store contact persons | yes, with one finding | amounts: rules in the module docstring and `docs/sources/cordis.md`; a stated amount is replaced only when it is an exact multiple of the bulk figure (the WP-43 defect, documented); 6,563 other differences are kept and counted. Country: **nothing to fill**: `organisation.country` is NOT NULL (migration 0001) and the loader skips an organisation without one, so the dry run shows `country_empty 0`; the module compares and counts (`country_differs_kept 5`) and writes no country. Contacts: the files hold no contact person (only a link to a contact form); the reader takes 5 columns (`READ`) and a unit test asserts no other value comes out |
| 4 | Idempotent; dry run prints counts by programme | yes | integration test: second `--yes` run `changed == 0`; dry run leaves the rows equal; output below |
| 5 | Refresh the directory rows after writing | yes | `networks.refresh_organisation_network` after the writes; integration test checks the directory sum (280,000) |
| 6 | Dry run on production once, counts in the report | yes | below (run three times: the first found the over-total case, the module was fixed, then the final dry run; plus two read-only diagnostics) |
| 7 | ruff, unit and integration suites locally | see "Tests" | |

## Production dry run (21 October 2026, 16:10 UTC)

Run inside `dgate-worker-1` with the module file copied to `/tmp/wp70` (removed afterwards), no `--yes`: the session
temp table and everything else rolled back. 77 s.

```
  H2020    differs_kept       1127
  H2020    fill_over_total        3
  H2020    filled              186
  H2020    multiple             11
  H2020    role_differs         53
  HORIZON  differs_kept       5436
  HORIZON  fill_over_total       24
  HORIZON  filled             1569
  HORIZON  multiple             50
  HORIZON  role_differs        304
would change: {'bulk_participants': 432976, 'bulk_participants_not_stored': 52478, 'bulk_rows': 466792,
 'bulk_rows_no_project': 33107, 'bulk_rows_skipped': 473, 'changed': 1816, 'country_differs_kept': 5, 'country_empty': 0,
 'differs_kept': 6563, 'fill_over_total': 27, 'filled': 1755, 'matched': 380498, 'multiple': 61, 'participations': 382153,
 'project_by_grant_number': 6010, 'role_differs': 357, 'to_gross_of_third_parties': 328, 'to_linked_third_party': 140,
 'to_plain': 1348}
```

Reading it: **1,816 participations would change**: 1,615 get an amount where they had none (1,755 `filled`, of which
140 are third parties that the bulk also states at 0 and that only change note from `no_payment_stated` to
`linked_third_party`), 61 doubled or tripled amounts are corrected. FP7 changes nothing: its 129,142 matched rows equal the
bulk (the FP7 package is from January 2025 and the open data holds the same figures; its 7,348 `no_payment_stated`
rows are empty in the bulk too). Matched: 380,498 of 382,153 stored participations (99.6 %).

Where the `no_payment_stated` rows go (read-only diagnostic, 9,997 rows):

| programme, role | fillable | bulk states none | no bulk row | role differs |
|---|---|---|---|---|
| FP7 coordinator / participant | 0 | 7,348 | 129 | 0 |
| H2020 coordinator / participant / international partner | 164 | 63 | 3 | 0 |
| H2020 third party | 25 | 0 | 0 | 1 |
| Horizon Europe coordinator / participant | 1,473 | 0 | 36 | 11 |
| Horizon Europe associated partner | 0 | 586 | 17 | 0 |
| Horizon Europe third party | 120 | 0 | 17 | 0 |

1,782 fillable = 1,755 filled + 27 dropped by the over-total rule. The verification's 2,356 is not a count I could
reproduce; of the H2020 and Horizon Europe coordinators and participants without a payment, 1,636 of 1,749 are fillable (the
1,749 of WP-41's note).

**The over-total rule, found by the first dry run.** Without it 22 projects (70 rows) would have become
`exceeds_project_total`: e.g. a Horizon Europe grant of 2,495,360 whose open data pays the whole amount to one host and
nothing to two others, while the bulk gives the others a share (and the host less, a kept difference). Filling would have
withheld three amounts shown today. Now the fills of such a project are dropped (`fill_over_total`, 27 rows) and its stated
amounts stay; tested.

**Differences kept** (6,563): ratio ours / bulk 0.9-1.1: 3,034; 0.5-0.9: 1,180; 1.1-2: 1,153; under 0.5: 190; 2 or more
but not an exact multiple: 1,006. Sampled 10, e.g. CIRCULOOS 426,250 vs 452,500, TauEB 1,202,500 vs 1,499,000: the bulk is a
later copy with amendments. Not changed: a rule "the newer file wins" was not given; it is the owner's decision (it would
also want the column switched to the net figure, which the project pages print).

## 18 rows checked by hand against the CORDIS project pages

Random sample (seed 7070) of the rows the module would change; page `https://cordis.europa.eu/project/id/<grant>`
(robots.txt allows `/project/id/`), one request every 2 s; the page prints the net EU contribution of each participant.

| Grant | Acronym | PIC | Role | Ours now | Would be | Page | Verdict |
|---|---|---|---|---|---|---|---|
| 101182162 | SOPHIA | 966418470 | participant | NULL, no payment | 252,787.50 | 252,787.50 | yes |
| 101181132 | TexMat | 994801543 | participant | NULL | 804,625.00 | 804,625.00 | yes |
| 101241773 | TRANSBIT | 999864846 | coordinator | NULL | 150,000.00 | 150,000.00 | yes |
| 101059425 | LET'S CARE | 907287173 | participant | NULL | 57,770.99 | 57,770.99 | yes |
| 101099192 | PLANKT-ON | 999865331 | participant | NULL | 537,100.00 | 537,100.00 | yes |
| 101181686 | ArcticKnows | 941828873 | participant | NULL | 275,906.25 | 275,906.25 | yes |
| 101213727 | PIXEurope | 901837907 | participant | NULL | 2,397,368.85 | 2,397,368.85 | yes |
| 101233874 | RenoVisor | 950466238 | participant | NULL | 107,197.50 | 107,197.50 | yes |
| 101235234 | AGRISOL | 953382543 | participant | NULL | 264,864.21 | 264,864.21 | yes |
| 101036756 | ZeroPM | 998224867 | participant | NULL | 1,592,702.50 | 1,592,702.50 | yes |
| 101194414 | MOSAIC | 887418081 | participant | NULL | 156,340.19 (gross_of_third_parties) | 156,340.19 | yes |
| 101226104 | BTL-COP | 997513178 | participant | NULL | 177,750.00 | 177,750.00 | yes |
| 101182871 | BIOGREENET | 998214876 | participant | NULL | 296,609.39 | 296,609.39 | yes |
| 101131534 | DynaSun | 999876292 | participant | 147,200.00 | 73,600.00 (doubled) | 73,600.00 | yes |
| 101182003 | FRANCESCA | 943272233 | participant | NULL | 111,387.50 | 111,387.50 | yes |
| 101070177 | ICOS | 950302793 | participant | NULL | 0.00 | 0.00 | yes |
| 101034366 | FACILITATE | 994666034 | participant | NULL | 0.00 | 0.00 | yes |
| 101233379 | KINETIKA | 904315481 | participant | NULL | 178,062.50 | 178,062.50 | yes |

18 of 18 yes. (In these rows the bulk's gross and net figures are equal, so the page's net figure is a fair check.)

## Tests

* `ruff check .`: all checks passed.
* Unit (`pytest`): 2,982 passed, 1,149 deselected.
* Integration (`pytest -m integration`, local Postgres 17 container `dgate-wp70`): 1,149 passed, 2,982 deselected (8 min 44 s);
  the 4 WP-70 tests again after the last docstring edit: 4 passed.

## Self-review as a hostile reviewer: 4 issues found, 4 fixed

1. Third parties held as `linked_third_party` would have been filled with a positive bulk figure while their
   beneficiary keeps the gross: double counting. Removed; they stay as the loader stores them.
2. The first version held all 382,000 joined rows in memory: now a named cursor, one project at a time.
3. The over-total case above (found by the production dry run, not by the tests): rule and test added.
4. The country step wrote `organisation.country` where NULL, which cannot exist (NOT NULL): replaced by a comparison
   that writes nothing; the docstring said "amounts and countries", corrected.

Also checked: the dry run issues no UPDATE (the write branch is behind `apply`), the temp table needs only the default
TEMP privilege (the dry run ran as `dgate_worker`), no new table or migration, no grant needed, no worker job added.

## Not done, and why

* **No country was written**: there is no empty country to fill (above).
* **52,478 bulk participants we do not store** (including the 16,012 roles the SPARQL service names no organisation for,
  and Horizon Europe projects newer than the SPARQL copy: 33,107 bulk rows have no project of ours) are only counted:
  inserting participations and projects is a load, not a fill, and outside this package.
* **Project totals** (`project.eu_contribution`, NULL for recent Horizon Europe grants such as MetaTune) are not filled
  from `ecMaxContribution`: the package was scoped to participations.
* **Differences kept** and the **net figure**: owner decisions, above.
* The `--yes` run on production: left to the orchestrator.

## Production commands (for the orchestrator)

After the branch is merged and the worker image rebuilt (the module must be in it). The three packages are on the server
in `/root/wp70` (125 MB, mine; delete afterwards).

```
cd /opt/dgate
docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps -v /root/wp70:/bulk:ro \
    worker python -m dgate.ops.cordis_bulk --dir /bulk          # dry run: expect changed 1816
docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps -v /root/wp70:/bulk:ro \
    worker python -m dgate.ops.cordis_bulk --dir /bulk --yes    # writes 1,816 participation rows, rebuilds the directory
rm -rf /root/wp70
```

Expected: about 80 s plus the directory rebuild; 1,816 row updates (a few MB of WAL), no new rows, no disk to speak of.
A run within the same month gives the same counts; a second `--yes` changes 0.

## Scratch

Server: `/root/wp70` (the three zips, `dryrun.log`, `sample.json`; kept for the `--yes` run), `/root/wp70scripts` and
`/root/dev-wp70` (deleted). Worker container `/tmp/wp70` (deleted after each run). Laptop: `D:\DEFENCEGATE TESTS\wp70`
and the container `dgate-wp70` (removed after the suites ran). No scratch table: the temp table lives only in the session.
