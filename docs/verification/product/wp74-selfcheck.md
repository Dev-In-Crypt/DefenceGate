# WP-74 self-check: undo the merge batch of 21 October 2026, and fix the rule

Branch `wp-wp74` (from `integration` e0d3d2e). Builder's own check; an independent verifier checks again.

## What was built

| File | What |
|---|---|
| `backend/dgate/ops/undo_merges.py` | reverses exactly the WP-72 batch (dry run default, `--yes`, one transaction, idempotent) |
| `backend/migrations/0097_merge_candidate_statuses.sql` | candidate statuses `undone` and `rejected_public_units` (CHECK widened; additive, idempotent) |
| `backend/dgate/buyer_family.py` | `is_public_body`, `is_sub_unit` (vocabulary over stored names, plus flag, `org_role`, `legal_form`) |
| `backend/dgate/ops/accept_merge_candidates.py` | refusal `public_body`; with `--yes` such pairs become `rejected_public_units` and the buyer families are rebuilt; Dutch "p a" (care of) added to `ACTING_FOR` |
| `backend/dgate/ops/buyer_families.py` | rule `shared_tax_id`: rows joined by `rejected_public_units` pairs form one buyer family under the parent body's row; the daily job keeps them |
| `backend/tests/unit/test_wp74.py`, `backend/tests/integration/test_wp74.py` | new tests |
| `backend/tests/unit/test_wp72.py`, `backend/tests/integration/test_wp72.py` | the example "commune de montoir de bretagne" / "mairie de ..." was a public pair; under the new rule it is refused by design, so the WP-72 tests use two company names for the same assertions (nothing weakened: same counts asserted) |

## 1. Undo (acceptance: exact batch, counts, 20 sampled notices, idempotent)

How the batch is found and each part derived (all from what `db.merge_organisations` left behind):

- **Batch**: `merge_method = 'identifier'` and `merged_at` in 2026-10-21 18:00-19:00 UTC; every row must
  have its `merged` candidate pair decided in the window, and the count must equal `--expect` (6641),
  or the run stops (`BatchMismatch`) before writing. Production: 6,641 rows under 500 heads, all with
  a candidate pair; no head was merged since. The 505 `identifier` merges of 12 Oct are outside the window.
- **Rows**: `merged_into`, `merge_method`, `merge_confidence`, `merged_at` back to NULL.
- **Aliases**: an alias on a head with `prev_organisation_id` that leads (through merges that stay) to a
  member of that head goes back to the member; `prev_organisation_id` is cleared when it equals the
  member (the merge set it from NULL via COALESCE), kept when it names an older origin.
- **Notices**: per notice on a head, the `buyer_org_id` of its latest `opportunity_version` observed
  before the batch, followed through the merges that stay; re-pointed only when that lands on a member
  of the same head. Verified on production first by SQL: of 3,165 notices on heads, 463 archive a member
  directly, 2 archive a row merged into a member earlier, 2,232 archive the head itself, 468 archive a
  row merged into the head on 12 Oct (stays). The archive is not written.
- **National number**: the merge moves a member's `national_reg_no` to a head without one and stamps the
  head `identifier_method='identifier'` with the group confidence (>= 0.97; resolution stamps 0.90).
  The member keeps its own `identifier_method`. Production: 303 heads carry the stamp and each has
  exactly one member with a method and no number (the donor). Restored: head number/method/confidence
  NULL, donor gets the number back (head first: unique index on (country, number)).
- **Defence-buyer flag**: no audit trail of flags exists (the candidate rows the merge inserts carry no
  flag). Rule: head flagged, no `defence_buyer_source`, a flagged member, and not in the seed file
  (seed-buyers writes no source either). Production: 6 heads flagged; 5 carry their own source
  (`derived_rule`, `namesake`); 1 (225806 'ministere de l interieur depafi sailmi', member 260514
  flagged by `derived_rule`) had it from the merge and is cleared.
- **Candidates**: the 6,655 pairs decided `merged` in the window (resolve_organisation rows, including
  the 2,892 head-member pairs the merge's ON CONFLICT updated) go back to `pending`; the 3,749 audit
  rows the merge inserted (`detected_by='ops.accept_merge_candidates'`, created in the window) become
  `undone`. Production has no `rejected` candidates at all, so no reviewer decision is overwritten.
- **Directory**: `networks.refresh_organisation_network` after the commit.

Production dry run (read-only: run inside the worker container with `PGOPTIONS=-c default_transaction_read_only=on`, 15 s):

```
batch 2026-10-21 18:00:00+00 .. 2026-10-21 19:00:00+00: 6641 rows under 500 heads (every one with its
candidate pair); aliases back 6825; notices back 465 (kept on the head: 2701); numbers back to their row
303; defence-buyer flags cleared 1 [225806]; candidates to pending 6655, audit rows to undone 3749
```

(2,701 kept: one notice arrived on a head after the batch, resolved through a moved alias; it stays on
the head and the next ingestion resolves such names to the unmerged rows.)

20 sampled notices (old buyer -> new buyer), verdict = the new buyer is the row the notice was archived with:

| notice | old (head) | new (member) | ok |
|---|---|---|---|
| 385721 | 33106 renfe fabricacion y mantenimiento sociedad mercant.. | 127142 renfe fabricacion y mantenimiento sociedad mercant.. | yes |
| 301438 | 33106 renfe fabricacion y mantenimiento .. | 127142 renfe fabricacion y mantenimiento .. | yes |
| 308860 | 28888 sid idf | 220714 esid idf - etablissement du service d infrastructure.. | yes |
| 279104 | 33106 renfe fabricacion .. | 127142 renfe fabricacion .. | yes |
| 261925 | 288 sykehusinnkjop hf | 163745 luftambulansetjenesten hf v sykehusinnkjop hf | yes |
| 156752 | 122337 council of europe directorate general of administration | 147259 dga council of europe directorate general of admin.. | yes |
| 312193 | 32292 renfe operadora dg economico financiera g de area .. | 90268 entidad publica empresarial renfe operadora direcc.. | yes |
| 40245 | 157846 bundesministerium fur inneres | 36560 republik osterreich vertreten durch den bundesmini.. | yes |
| 54475 | 157846 bundesministerium fur inneres | 36560 republik osterreich vertreten durch den bundesmini.. | yes |
| 299909 | 33106 renfe fabricacion .. | 127142 renfe fabricacion .. | yes |
| 298513 | 33106 renfe fabricacion .. | 127142 renfe fabricacion .. | yes |
| 213171 | 122337 council of europe dga | 147259 dga council of europe .. | yes |
| 129682 | 65265 telewizja polska z siedziba w warszawie .. | 173 telewizja polska w likwidacji | yes |
| 208685 | 122337 council of europe dga | 147259 dga council of europe .. | yes |
| 211808 | 122337 council of europe dga | 147259 dga council of europe .. | yes |
| 298045 | 33106 renfe fabricacion .. | 127142 renfe fabricacion .. | yes |
| 301848 | 64819 secretaria general de sanidad y consumo | 157887 subdireccion general de asuntos generales y econom.. | yes |
| 279549 | 33106 renfe fabricacion .. | 127142 renfe fabricacion .. | yes |
| 213900 | 122337 council of europe dga | 147259 dga council of europe .. | yes |
| 157377 | 122337 council of europe dga | 147259 dga council of europe .. | yes |

"yes" means the id equals what the archived payload says (the code path); whether the two rows were
really two buyers is the question rule 2 answers next.

Idempotence: integration test runs the undo twice; the second finds no batch (`{"rows": 0}`) and writes nothing.

## 2. Rule fix (acceptance: never auto-merge public bodies by a shared tax id; companies still merge; families)

A pair is refused `public_body` when either side is a defence buyer, has `org_role='buyer'`, a public
legal form, or a name that `buyer_vocab.buyer_class_of` classes as defence, security, municipal,
health, education, fire_rescue, international or infrastructure, or that matches the administration
vocabulary (`PUBLIC_NAME`: ministry, government, agency, Land/Bundesamt, statens, rijks, communaute,
-kreis, stad, region, -etaten, -verket ...) or the unit vocabulary (`SUB_UNIT`: departamento,
consejeria, conselleria, area de gobierno, direccion, direzione, dipartimento, directia, direction,
service de, Abteilung, Fachbereich, Referat, afdeling, wydzial, odbor, тп, дирекция, διευθυνση ...).
On production `org_role` is set on 14 rows and `legal_form` on none, so the name carries the rule.

With `--yes` the refused pairs are marked `rejected_public_units` and `ops.buyer_families` (also run
daily by the worker, which rebuilds the table from the stored pairs, so nothing is lost) shows each
connected set as one buyer under the parent body: the row whose name is not a unit's, without " - ",
that most other names in the set begin with, then the most defence notices. A set with no such row
stays apart (Madrid's "area de gobierno ..." rows unless an "ayuntamiento de madrid" row is in the set).

Dry runs on production (read-only, 60 s with `--no-office-splits`):

- **The batch's own 6,655 pairs under the new rule** (simulation from their pre-batch ids, scratch
  script, read-only): 5,738 refused `public_body`, 99 `acting_for_another_body`, 818 accepted in 127
  groups (815 rows). The cases named in the brief are all refused: Gobierno Vasco, Madrid areas, the
  Italian ministries, Diputacion de Barcelona, Romsilva (`directia`), ASFINAG (infrastructure),
  KU Leuven associations (`associatie`, "p a"). The accepted groups are spelling variants or branches of
  one company or one body (largest: Grand Port Maritime de Nantes Saint-Nazaire 18 spellings, RAI 17,
  ARIA 17, EDIA 16, VNF 13, REN 12).
- **The still-pending pairs today** (77,332 strong): accepted 9,988 pairs in 6,920 groups (9,975 rows to
  merge); refused `public_body` 26,097, `different_reg` 37,783, `acting_for_another_body` 1,280,
  `group_different_reg` 1,906, `already_one` 255, others 23. Buyer families after: 533 groups / 1,032
  member rows (383 rows to write, 3 removed), of which 288 `shared_tax_id` families with 381 members
  (e.g. CZ 'ministerstvo obrany' <- 'ceska republika - ministerstvo obrany' ..; NL 'ministerie van
  defensie' <- '.. dosco'; NO 'forsvarsbygg' <- 'forsvarsbygg anskaffelser' ..).
- After the undo both pools are pending: expected about 84,000 strong pairs, about 10,800 accepted
  (about 10,790 rows merged), about 31,800 marked `rejected_public_units`.

30 sampled pairs the new rule still ACCEPTS (current pending pool; verdict: same body?):

| # | pair | same body |
|---|---|---|
| 169090 RO | secom drobeta-turnu severin ~ secom - drobeta turnu severin | yes |
| 1085137 DK | faxe og hylleholt boligforening ~ faxe og hylleholdt boligforening | yes |
| 1035835 NL | bonaire brandstof terminals ~ bonaire bon transition | unsure |
| 125297 ES | lantik - lantik ~ lantik lantik | yes |
| 34978 ES | xestion do solo de galicia xestur s a ~ xestion do solo de galicia | yes |
| 667181 FR | vallee sud-grand-paris ~ vallee sud - grand paris 92 | yes |
| 433437 SE | nordiska museet ~ -stiftelsen nordiska museet | yes |
| 1114806 FR | federation departementale d energie de la somme ~ territoire d energie somme | yes (renamed) |
| 1081848 PT | escola profissional de vila do conde ~ .. l da | yes |
| 1020702 IT | aler bergamo lecco sondrio ~ a l e r bergamo lecco e sondrio | yes |
| 512736 FR | office du tourisme de saint-martin ~ office de tourisme de saint martin 978 | yes |
| 90262 NL | ubr his ~ (minist)erie van volksgezondheid welzijn en sport dtv | **no** (truncated ministry name escapes the vocabulary) |
| 639511 NO | risor og tvedestrand-regionens avfallsselskap ~ risor- og tvedestrandregionens .. | yes |
| 548007 FI | helsingin kaupungin asunnot ~ .. c o heka-myllypuro | yes |
| 857165 FR | ehpad public de villefranche sur mer ~ ehpad la sofieta de villefranche-sur-mer | unsure |
| 402240 NO | posten norge ~ posten bring | yes |
| 822262 NL | ssc iuc dji ~ sic dji | **no** (two units of the Dutch justice agency) |
| 729660 FR | series mania ~ association du festival international des series | yes |
| 1086638 IT | autorita garante della concorrenza e del mercato ~ (typo) | yes |
| 835846 IT | azienda territoriale per l edilizia residenziale ~ (same) | yes |
| 376260 FR | seli procedures formalisee ~ seli procedures formalisees | yes |
| 990417 FR | cnaf ~ caisse nationale des allocations familiales | yes |
| 835842 DE | freie und hansestadt hamburg - behorde fur stadtentwicklung ~ (same) | yes |
| 906235 PL | inlife instytut rozrodu zwierzat .. ~ (variant) | yes |
| 734853 BG | институт по електроника акад емил джаков ~ институт по електроника бан | yes |
| 230735 DK | provas - haderslev affald a s ~ provas affald a s | yes |
| 340634 PL | regionalne centrum gospodarki wodno sciekowej ~ (hyphen) | yes |
| 1200186 PT | cooperativa de ensino escola profissional .. ~ (same) | yes |
| 553644 SI | os nhr hrastnik ~ osnovna sola narodnega heroja rajka hrastnik | yes |
| 68387 BG | институт по океанология бан ~ институт по океанология | yes |

26 yes, 2 no, 2 unsure. The two wrong ones are two-row groups of a Dutch government body whose names
carry no word of the vocabulary; the vocabulary is the known ceiling (a register of public bodies
would close it). 30 sampled REFUSED pairs are in the dry-run output (all public bodies; a few are
spelling variants of one body, e.g. 'mairie de mimizan' ~ 'commune de mimizan': not merged, shown as
one family instead, which costs nothing).

## Production commands (orchestrator; in this order)

Deploy `wp-wp74` first (migration 0097 must be applied before the undo writes `undone`). Then, on the server:

```
cd /opt/dgate
# 1. undo: dry run, check the counts against the ones above (6641 / 500 / 6825 / 465 / 303 / 1 / 6655 / 3749)
docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps worker python -m dgate.ops.undo_merges
docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps worker python -m dgate.ops.undo_merges --yes
# 2. the merge run under the new rule: dry run, then write
docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps worker python -m dgate.ops.accept_merge_candidates --no-office-splits
docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps worker python -m dgate.ops.accept_merge_candidates --yes --no-office-splits
```

Volume: undo touches 6,641 organisation rows, 6,825 aliases, 465 notices, ~10,400 candidate rows in one
transaction (seconds), then rebuilds the directory table. The merge run writes ~31,800 candidate
statuses, merges ~10,800 rows (one commit per group, as WP-72), rewrites ~400 family rows, rebuilds the
directory. No new table; disk negligible. `--limit N` caps the merged groups if the orchestrator wants
to go in steps (public pairs are marked in full on the first `--yes`).

## Tests and checks (local, `D:\DEFENCEGATE TESTS\wp74`, own venv, throwaway Postgres 17 on 55474)

- ruff: clean.
- unit: all green (full suite).
- integration: full suite with `-m integration`: all green (exit 0), including `test_wp74.py` (6 tests),
  `test_wp72.py` and `test_buyer_families.py`.
- New tests fail without the behaviour: undo restores rows, aliases (including an alias moved by an older
  merge), notices (direct and through an older merge), the number, the flag (and keeps a seeded flag),
  candidate statuses, refuses a window with the wrong count, second run is a no-op; the accept run
  refuses public pairs, marks them, writes `shared_tax_id` families under the parent and the daily job
  keeps them, still merges a company pair; units with no parent row stay apart; vocabulary cases from
  the production names.

## Self-review (hostile pass)

Found and fixed: (1) the first vocabulary let ASFINAG, KU Leuven, Landratsamt Miesbach, Goteborgs stad
through (dry run on the batch): `infrastructure` class, `associatie`, Dutch "p a", `lra`, `stad` ...
added; (2) family heads were typos or abbreviations with 0 notices ('ministersvo obrany',
'defensie'): head rank now prefers the name the others begin with, then notices; (3) ruff B023 on the
rank closure; (4) the WP-72 tests used a commune pair that the new rule refuses by design: changed to
companies with the same assertions. 4 issues found, 4 fixed.

## Not done / could not check

- The undo and the new merge run were not executed on production (dry runs only, as the brief says).
- The family counts for the batch's own public units (Gobierno Vasco, Madrid ...) can only be measured
  after the undo: while those rows are merged, the family rule skips them.
- The vocabulary misses some public bodies (2 of 30 sampled accepted pairs); those still merge.
- `sig_buyer` on notices of head 225806 is not recomputed by the undo; the next reclassification does it.
- Scratch on the server: `/root/wp74-dry` and `/tmp/wp74` inside `dgate-worker-1` (code copy for the
  read-only dry runs): both removed. Local: `D:\DEFENCEGATE TESTS\wp74` and the container `dgate-wp74`.
