# WP-129 self-check: a person-reviewed list of merge candidates; two doubtful name-only rejoins

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP129.md`. Branch `wp-wp129` from `integration` (7ba8543). No migration.
Evidence: `D:\DEFENCEGATE TESTS\verify-oct25\merge-review\` (decisions.csv, accept-ids.txt, second-candidates.csv).
Production was read only through the postgres container (`default_transaction_read_only`, `statement_timeout` 30 s, 11
queries); nothing ran inside a production container and no ops module ran there. The expected counts below come from
those reads with the new planning code run on my copy of the rows (`D:\DEFENCEGATE TESTS\wp129\sim*.py`, `prod70.json`).

## 1. `ops.accept_merge_candidates --ids-file PATH`

Before: the script read only `identifier` >= 0.97 candidates, refused every public body (and with `--yes` marked such
pairs `rejected_public_units`) and every pair with two different registration numbers, so none of the 64 ACCEPT rows of
the review could be merged by it (the 70 are method `cleared_register_number`, 0.90, all Polish public bodies).

Change (`backend/dgate/ops/accept_merge_candidates.py`, `run_reviewed` and helpers):
- `--ids-file PATH` (or `-` for standard input) decides the listed candidates, of any method, and nothing else. The
  normal run, its public-body marking and its refusals are unchanged.
- Judgement rules are the person's for those ids: public body, acting for another, short name, legal form, sister
  company, no second signal. The report counts what they would have said (`judgement_rules_overridden`).
- Fact rules still refuse: not pending, one organisation already, different countries, suppressed, natural person, and
  two different numbers of one kind anywhere in the group (`number_kinds`: Polish NIP, REGON 9/14, KRS written with its
  leading zeros; a Polish VAT number counts as the NIP; elsewhere one kind per column; VAT and PIC one each). A NIP on one
  row and a REGON on the other is merged with `allow_identifier_conflict=True`; each row keeps its own number.
- Head: not the row named generically (`org_repair.ambiguous_name`, or another row's name without its place: 'zaklad
  karny' beside 'zaklad karny we wronki'), then most defence notices, then the one holding a registration number, a PIC,
  the lowest id. A `head` column in the file overrides (it must be a row of the group, else the group is refused). The
  report prints every group's head and members.
- Every merge stores method `person_review` (added to `MERGE_METHODS`) and the reviewer's confidence (else the candidate's),
  with the evidence "candidate N (method): ...; accepted by a person's review: <reviewer's evidence>".
- After a group merges, every other pending candidate between two of its live rows (either end may be a row already
  merged into one) is marked `merged`; a stale candidate between a row and its own merged row is left alone.
- REJECT rows become `rejected` with " | rejected by a person's review: <reason>" appended to the evidence; UNSURE rows
  stay pending. Report by default; `--yes` writes and prints the undo window.
- `--undo-batch FROM TO` reverses such a batch (`ops.undo_merges` with `person_review`), and puts the candidates of other
  methods that the batch marked `merged` back to pending. Rejections stay (a person's decision, not a merge).
- `ops.undo_merges` (WP-74's file, one condition): a number a merge moved to a head goes back to its row for any merge
  method; the 0.97 stamp is still required for plain `identifier` (resolution stamps that method with 0.90). Without it a
  `person_review` merge at 0.85 would not give a moved number back. Read on production: no planned group moves a number
  (every head that meets a member with a number holds one itself).

### The ids file

CSV, one candidate per line; blank lines and lines beginning with `#` are skipped.

- No header (first cell a number): `candidate_id[,head_org_id]`, every line ACCEPT.
- With a header: `candidate_id` and, when present, `decision` (ACCEPT, REJECT, UNSURE; empty = ACCEPT), `head`,
  `confidence` (0..1), `evidence` or `reason`. The reviewer's `decisions.csv` is read as it is (its name columns are
  ignored).

```
# reviewed 25 Oct 2026
2508797
2508862,195698
```
```
candidate_id,decision,head,confidence,evidence
2508797,ACCEPT,,0.95,identical names; both defence buyers
2508831,REJECT,,0.85,a faculty and its university (parent and unit)
2508832,UNSURE,,0.50,open: are the faculties one buyer
```

Repo file: `docs/verification/round6/wp129-accept-ids.txt`, the reviewer's 64 accepted ids (ids only). `decisions.csv`
stays in `D:\DEFENCEGATE TESTS\verify-oct25\merge-review\`: it holds organisation names and free text. It is the file to
run, because it carries the REJECT reasons and the reviewer's confidences (the ids file alone gives the same 62 groups
and heads, at the candidates' 0.90).

### Expected on production (`--ids-file decisions.csv`, report)

- reviewed {ACCEPT 64, REJECT 5, UNSURE 1}; 64 accepted in **62 groups, 64 rows to merge**; refused {}.
- judgement rules overridden: `public_body` 36, `different_reg` 28 (NIP beside REGON).
- two groups of three: head 15020 <- 17526, 19288 (candidates 2508828, 2508847); head 27510 <- 14239, 305911 (2508822,
  2508849). Head 195698 'zaklad karny we wronki' <- 286425 'zaklad karny' (2508862); head 29561 '.. tarnowskie gory' <-
  284785 (2508859); head 483 'powiat inowroclawski' <- 200865 (2508833).
- other pending candidates to `merged`: 84 (148 pending between the groups' live rows, less the 64 reviewed).
- to reject 5 (2508825, 2508831, 2508834, 2508865, 2508866); unsure left pending 1 (2508832).
- with `--yes`: merged 64 rows in 62 groups, rejected 5, then the undo window.

Heads the review may want to override with a `head` column (each is a correct body, the display name is long):
159186 'gmina parzeczew urzad gminy w parzeczewie' over 294442 'gmina parzeczew'; 69720 'powiat otwocki reprezentowany
przez zarzad powiatu' over 334391 'powiat otwocki'. The rule cannot tell an added office or organ from an added place.

Tests: `tests/unit/test_wp129.py` (file formats, number kinds, plan: overrides, facts, group of three, generic head,
head column), `tests/integration/test_wp129.py::test_a_reviewed_list_is_merged_rejected_and_undone_by_its_window`
(report writes nothing; merge with method, confidence, both numbers kept, a moved number; other candidates merged; reject
with reason; unsure pending; second run merges nothing; undo by the window: rows, number, candidates back, rejection kept).

## 2. The two name-only rejoins into 9314

Before: rows 305776 and 331149 were joined into 9314 'miejski zaklad uslug komunalnych' on 25 Oct 07:07 by
`false_identifier_rejoin` (same name, false number cleared). Read on production: none of the three rows has a notice, an
award, a participation, a family membership or a version payload naming it (305776 and 331149 have no alias either), so
no notice says which body they are. Their numbers do: 305776's cleared value was a NIP+REGON pair held by 14015 'miejski zaklad uslug komunalnych sp z o o
w walbrzychu' and 303793 (Walbrzych); 331149's a 10-digit value failing the NIP check; 9314 holds a different REGON, and
285559 a fourth one of the same name. Four bodies at least bear the name: both joins are wrong.

Change (`backend/dgate/ops/org_repair.py`):
- `_UNIT_WORDS` gains `uslug komunalnych komunalna`, so `ambiguous_name` calls the municipal service companies without a
  town generic: `false-ids` never rejoins them by name again, and `namesakes` finds the joins already made.
- `namesakes` keeps a row whose cleared value states its head's number (`agrees`: the value, its register form or either
  half of a NIP+REGON pair equals the head's registration or VAT number): such a row was joined by the number, not the name.
  Production: 329120 into 7563 'miejski zarzad uslug komunalnych' (its pair's NIP is 7563's) stays.

Expected on production (`python -m dgate.ops.org_repair --step namesakes`, report): rejoined rows 6763; **1 group, 2
rows** (head 9314: 305776, 331149); 1 row stays (number agrees). With `--yes` exactly those two are undone through
`ops.undo_merges` with `only` (their candidates 2501416, 2501417 become `undone`); nothing else changes. The vocabulary was
checked against all 6763 live rejoins: it catches only these three rows.

Other rejoins into generic-name rows (not undone here; the same rule would need `zakladow` in the vocabulary):
- head 9206 'zespol zakladow opieki zdrowotnej' <- 314495, 314541, 314952 (cleared values were case references, not the
  head's number);
- head 10219 'samodzielny publiczny zaklad opieki zdrowotnej zespol zakladow' <- 286437, 287255 (6-digit values, not the
  head's number; the head holds none);
- head 284785 'wielospecjalistyczny szpital powiatowy' <- 10353: the cleared pair states 284785's number, a correct join.
None of these rows has a notice.

Tests: `tests/unit/test_wp129.py` (generic names, `agrees`), `tests/integration/test_wp129.py::
test_a_rejoin_into_a_generic_municipal_company_is_undone_unless_its_cleared_number_was_the_heads`.

## Ops, in order (orchestrator)

1. `python -m dgate.ops.org_repair --step namesakes` -> 1 group, 2 rows, 1 kept; then `--yes`.
2. `python -m dgate.ops.accept_merge_candidates --ids-file - < decisions.csv` (e.g. `docker compose ... run --rm -T worker
   python -m dgate.ops.accept_merge_candidates --ids-file - < decisions.csv`) -> 62 groups, 64 rows, 84 other candidates,
   5 to reject, 1 unsure; then the same with `--yes` (keep the printed undo window).

## Batched tests (my copy, Postgres 17 on 55529)

ruff clean; unit 260 passed (test_wp72, 74, 76, 96, 104, 111, 115_org_identifiers, 119, 129); integration 51 passed
(test_wp72, 74, 76, 96, 104, 115, 119, 126, 129).

## Open

- After step 1, row 305776 is on its own again; a re-run of `org_repair --step held-ids` would propose 305776 ~ 14015
  (its cleared pair's NIP is 14015's: probably the Walbrzych company). A person decides.
- 2508832 (Politechnika Warszawska / its business school) stays pending for the owner's question in decisions.csv.
- The five health-care rejoins above, if the owner wants the generic-name rule widened to them.
