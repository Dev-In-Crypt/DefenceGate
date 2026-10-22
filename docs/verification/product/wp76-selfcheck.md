# WP-76 self-check: organisation merges safe enough to run

Branch `wp-wp76` (from `integration` f606b51). Builder's own check; an independent verifier checks again.
Nothing was written on production, nothing deployed or pushed, `--yes` not run.

## What was built

| File | What |
|---|---|
| `backend/dgate/buyer_family.py` | `public_signal()` (why a row is public: `defence_buyer`, `buyer_role`, `legal_form`, `identifier`, `name`); `PUBLIC_ID` + `public_identifier()`; `PUBLIC_NAME` widened for every country held; `PUBLIC_NAME_BY_COUNTRY` (NL state abbreviations, IT ASP/UOC/central purchasing bodies); `is_public_body()` is now a wrapper |
| `backend/dgate/ops/accept_merge_candidates.py` | second-signal rule (`agreement`, `name_similarity`, `_long_form`, `legal_forms`); new refusals `no_second_signal`, `different_legal_form`, `sister_company`; `ACTING_FOR` widened, `ACTING_FOR_NORDIC`; per-merge method and confidence; `--sample`, batch sample and window after each `--yes`; `--undo-batch FROM TO` |
| `backend/dgate/ops/undo_merges.py` | takes a tuple of merge methods (default `('identifier',)`, WP-74 behaviour unchanged); counts a member's candidate pair once (the merge now leaves both the original `identifier` pair and its own audit row) |
| `backend/dgate/ops/buyer_cleanup.py` | reads `merge_method LIKE 'identifier%'` so the new method names stay in its scope |
| `backend/tests/unit/test_wp76.py`, `backend/tests/integration/test_wp76.py` | new |
| `backend/tests/unit/test_wp72.py`, `backend/tests/integration/test_wp72.py` | fixtures adjusted to the new rule (see Tests) |

No migration: the method lives in the existing `organisation.merge_method` / candidate `match_method` text columns.

## 1. Public-body and sub-unit detection

A pair is refused `public_body` (with `--yes`: marked `rejected_public_units`, shown as a buyer family, as WP-74) when either row:

- is a defence buyer, or has the **buyer role**: `org_role='buyer'`, or it publishes notices (`EXISTS opportunity.buyer_org_id`) and none of its names (stored, display, five alias raw names) states a company legal form. A buying S.A./GmbH/AB (utility, exhibition centre) is still a company.
- has a public legal form (`PUBLIC_FORM`, as WP-74);
- has an **identifier shaped like a public body's** (`PUBLIC_ID`, reg or VAT): FR SIREN/SIRET/VAT beginning 1 or 2; ES NIF P/Q/S; IT codice fiscale 8/9 (11 digits); BE enterprise number 02/03; SE 2xxxxxxxxx; PT 6xxxxxxxx; EE 70/75; LV 9000...; HU 15......; NL OIN 00000001/00000004; DE Leitweg-ID (labelled, `99x` federal, or the flattened `digits+letter...` form). Read against 307 sampled identifiers of the pending pairs (all FR 1/2, ES P/Q/S, IT 8/9, BE 02/03, SE 2 rows were public bodies; company counter-examples are in the unit tests). PL, CZ, DK, NO, FI, RO, BG, GR identifiers carry no public marker: the name decides there.
- has a **name** of an administration or a unit: WP-74's vocabulary plus NL (gemeente, ministerie, rijkswaterstaat, provincie, waterschap, dienst, zbo, and NL-only ubr/dji/ssc/dtv/rvo/cjib...), DE/AT (Behörde, Amt, Stadt, Landkreis, Gemeinde, Zweckverband, Magistrat, Bundes..., social insurance), FR (ministère, direction, préfecture, commune, mairie, département, conseil départemental/régional, SDIS, CCAS, SIVOM, rectorat, CAF/CPAM/URSSAF/MSA), IT (comune, provincia, regione, ente, CUC, questura, ALER/ATER, INPS/INAIL), ES (ayuntamiento, diputación, cabildo, xunta, mancomunidad, mesa del, rectorado, seguridad social, mutua), PL (urząd, gmina, starostwo, wojewódzki, powiat, komenda, jednostka wojskowa, sąd, prokuratura, nadleśnictwo), CZ/SK, SE, FI, DK, NO, BE, PT, RO, EE, LV, LT, HU, HR/SI, BG (община, районн, областн, здравноосигурителна), GR, IE/GB.

## 2. Stricter acceptance

Same identifier (as before) AND no contradiction AND at least one agreeing signal:

- `name`: `difflib` ratio of the networks keys (legal forms, hyphens, transliteration folded) >= **0.85**;
- `legal_form`: both rows state the same legal-form class (`resolution.names.legal_form_of` over stored, display and alias raw names) and one name is the other's long form (`_long_form`: the longer begins with the shorter and adds two or more words that do not repeat it or carry an inner legal form, or it is the same name twice).
- city/postcode: **not available** — no table stores an address of an organisation; not used.

New contradictions (pair waits, stays `pending`): `different_legal_form` (both state forms, none shared), `sister_company` (one name has a group word — holding, service, betrieb, drift, beteiligung, verwaltung, management, immobilien, netz — the other not), and more agent phrases (`vertreten durch`, `bijgestaan door`, `c o`, `på vegne af`, `en nombre ...`, `maîtrise d'ouvrage déléguée`, `X et SCCV ...`; in NO/DK `v`/`ved`).

Per merge: `merge_method` = `identifier+name` | `identifier+legal_form` | `identifier+name+legal_form`, `merge_confidence` = 0.97 + 0.01 per agreeing signal (0.98 / 0.99), candidate audit row with the same method and evidence "...; agreeing: name".

## 3. Staged execution

- `--yes --limit N` merges the N largest accepted groups and prints `--sample N` merged pairs of that batch and its exact window as a ready `--undo-batch` command. Run again for the next batch (merged pairs are no longer pending). Public pairs are marked on the first `--yes` (as WP-74).
- `--undo-batch FROM TO [--yes]` runs `undo_merges.run` (WP-74's logic: rows, aliases, notices, moved number, flag, candidates back to pending / audit rows to `undone`, directory refresh) for that window and all four methods, without an expected count; dry run without `--yes`; idempotent.

## 4. Dry run on production (22 October 2026, ~12:40 UTC)

How: the copy of the code into the worker container (WP-74's way) was refused by the session's permission classifier, so the inputs of `plan()` were read with read-only SQL (`default_transaction_read_only=on`, the brief's psql path; the exact `strong_pairs` query and the `organisations()` columns, alias raw names `ORDER BY id LIMIT 5`) and `plan()` / `sample_pairs()` of this branch were run on them locally. The buyer-family preview (`buyer_families.run(write=False)`) was therefore not run. Load stayed below 1.9.

| | pairs |
|---|---|
| strong pending candidates (`identifier` >= 0.97) | 84,013 |
| **accepted** | **3,744** in 2,762 groups (3,738 rows to merge): identifier+name 3,059, +name+legal_form 529, +legal_form 156 |
| **refused as public** (marked `rejected_public_units`) | **34,535** |
| **left pending** for a person | **45,734**: different_reg 37,265, acting_for_another_body 4,363, no_second_signal 3,475, already_one 255, group_different_reg 150, sister_company 149, different_legal_form 54, different_pic 11, natural_person 10, different_vat 2 |

Before (WP-74 rule, same data): 10,807 accepted, 31,847 public. Group sizes: 2,188 of 1 member, largest 15 (EDIA, ARIA spellings). First 200 groups = 789 rows.

### 60 sampled accepted pairs (the script's own hash sample), judged

Read: names, raw alias names, countries, identifiers. None of the 120 rows publishes a defence notice we hold (their aliases come from TED notices outside the archive: 117 rows, de_bkms 2, PLACSP 1); 3 CORDIS participations (Hulleras del Norte: CO2 capture, hydropower storage; Etra) agree with the names.

| # | ctry | method | pair | same body |
|---|---|---|---|---|
| 1 | RO | name | secom drobeta-turnu severin ~ secom - drobeta turnu severin | yes |
| 2 | DK | name | faxe og hylleholt ~ hylleholdt boligforening | yes |
| 3 | ES | name | lantik - lantik ~ lantik lantik | yes |
| 4 | ES | name | xestion do solo de galicia xestur s a ~ xestion do solo de galicia | yes |
| 5 | PT | name | escola profissional de vila do conde (Unipessoal Lda) ~ .. l da | yes |
| 6 | FR | name | office du tourisme de saint-martin ~ office de tourisme de saint martin 978 | yes |
| 7 | NO | name | risor og tvedestrand-regionens ~ risor- og tvedestrandregionens avfallsselskap | yes |
| 8 | IT | name | ATER di pordenone ~ azienda territoriale per l edilizia residenziale | yes |
| 9 | FR | name | seli procedures formalisee ~ formalisees | yes |
| 10 | PL | name | regionalne centrum gospodarki wodno sciekowej ~ wodno-sciekowej | yes |
| 11 | PT | name | cooperativa .. centro juvenil de campanha crl ~ c r l | yes |
| 12 | BG | name | институт по океанология бан ~ институт по океанология | yes |
| 13 | ES | name | hulleras del norte s m e ~ s a s m e | yes |
| 14 | PT | name+form | resinorte .. ~ resinorte - .. (both SA) | yes |
| 15 | IT | name | gestione ambientale integrata dell astigiano ~ gaia - .. | yes |
| 16 | DE | name | stiftung oper in berlin - buhnenservice ~ buhenenservice (typo) | yes |
| 17 | RO | name+form | societatea de transport bucuresti stb ~ stb sa | yes |
| 18 | ES | name+form | proteinas y grasas del principado ~ s a u | yes |
| 19 | PL | name | centrum onkologii .. lukaszczyka w bydgoszczy (two word orders) | yes |
| 20 | BE | name | vzw katholiek secundair onderwijs hasselt .. sint jozef ~ - sint jozef | yes |
| 21 | SK | form | clk spol s r o ~ clk spol | yes |
| 22 | GR | name | ειδικη υπηρεσια .. - διαχειριστικη ~ ..-διαχειριστικη | yes |
| 23 | PT | name | adc - aguas da covilha e m ~ adc aguas da covilha e m | yes |
| 24 | DK | name+form | provas - haderslev forsyningsservice a s ~ provas-haderslev forsyningsservice a s | yes |
| 25 | IT | name+form | lereti ~ lereti s p a | yes |
| 26 | DE | name | zukunft - umwelt - gesellschaft zug ggmbh ~ .. ggmbh | yes |
| 27 | GR | name | επιτελικη δομη εσπα υππεθ ~ ε σ π α υ παι θ | yes |
| 28 | PT | name+form | a v - aguas de valongo s a ~ a v - aguas de valongo | yes |
| 29 | FR | name | sft routier de frejus ~ du frejus | yes |
| 30 | IT | name | azienda veneziana della mobilita a ~ .. mobilita | yes |
| 31 | IT | name | etra societa benefit ~ etra societa di benefit | yes |
| 32 | PT | name | cascais dinamica .. ~ cascais dinamica - .. e m s a | yes |
| 33 | CZ | form | hph spol ~ hph spol s r o | yes |
| 34 | BG | name | електроразпределение север ад ~ енергоразпределение север ад (same BULSTAT, typo) | yes |
| 35 | ES | name+form | marina de badalona ~ s a | yes |
| 36 | HR | name | hrvatska narodna banka ~ bank8a | yes |
| 37 | ES | name | c a c teatro arriaga ~ cac teatro arriaga s a | yes |
| 38 | PT | name | didaxis - cooperativa de ensino c r l ~ crl | yes |
| 39 | IT | name | azienda speciale servizi sanitari di vergiate ~ asssv azienza .. | yes |
| 40 | PT | name | lotacor - servico de lotas dos acores ~ servico dos acores | yes |
| 41 | FR | name | pas-de-calais habitat ~ pas de calais habitat | yes |
| 42 | FR | name | spic - arena loire trelaze ~ .. 49 | yes |
| 43 | NO | name | nordmore interkommunale renovasjonsselskap iks nir ~ .. iks | yes |
| 44 | CZ | name+form | cez energo ~ cez energo s r o | yes |
| 45 | CZ | name | technicke sluzby mesta kralupy ~ kralup nad vltavou | yes |
| 46 | ES | name | fundacion .. oscar niemeyer principado ~ - principado | yes |
| 47 | SE | form | varmdobostader aktiebolag ~ varmdobostader (AB) | yes |
| 48 | ES | name | fundacio ~ fundacion barcelona capital nautica ac24 | yes |
| 49 | PT | name+form | ren servicos ~ ren servicos s a | yes |
| 50 | SK | name | ustav na vykon vazby .. kosice ~ .. (same IČO) | yes |
| 51 | BG | name | водоснабдяване и канализация - варна оод ~ .. варна | yes |
| 52 | FR | name | edm electricite de mayotte ~ de la mayotte | yes |
| 53 | FR | name | d hlm les foyers de seine et marne ~ les foyers .. | yes |
| 54 | IT | name | co r d a r valsesia ~ cordar valsesia | yes |
| 55 | GR | name | γ ν ελενα βενιζελου - αλεξανδρα (two punctuations) | yes |
| 56 | SE | name+form | vatten och avfallskompetens i norr ~ vatten- och .. | yes |
| 57 | NO | name | digitale gardermoen is ~ ko (IS converted to KO, same org number) | yes |
| 58 | IT | name | scr piemonte ~ s c r - piemonte s p a | yes |
| 59 | IT | name | irccs fondazione pascale ~ fondazione g pascale | yes |
| 60 | FR | name | sci activites courrier de proximite ~ activites courrier de proximite (same SIREN) | yes |

**60 yes, 0 no, 0 unsure.** The WP-74 sample's two wrong pairs ('ubr his' / '..erie van volksgezondheid ..', 'ssc iuc dji' / 'sic dji') are now refused `public_body`, its two unsure ones are refused (EHPAD: public) or wait (Bonaire Brandstof Terminals / Bonaire Bon Transition: no long form).

How the rule got there (each step measured on the same data, risky pairs read by hand): the first second-signal version accepted 4,369, and its low-similarity tail showed agents (`vertreten durch`, `bijgestaan door`, `c o`, Nordic `v`), lists of companies and sister companies ('verkehrsbetrieb hamm' / 'energie- und wasserversorgung hamm', 'verdo' / 'verdo holding', 'medfacilities' / '.. betrieb', 'femern' / 'femern landanlaeg', 'provas .. forsyning' / '.. forsyningsservice'); each became a refusal or a stricter legal-form rule, and the unsure pair #38 of the second sample ('provas' holding vs service company, CVR could not be checked) led to `sister_company`.

## Production commands (orchestrator; deploy `wp-wp76` first, no migration)

```
cd /opt/dgate
C="docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps worker python -m dgate.ops.accept_merge_candidates"
# 0. dry run: expect about 3,744 accepted / 34,535 public / 45,734 pending (pairs arriving since 22 Oct move these a little)
$C --no-office-splits --sample 60
# 1. first batch: the 200 largest groups (~790 rows); marks the ~34,500 public pairs; prints 30 merged pairs and the window
$C --yes --no-office-splits --limit 200 --sample 30
# 2. check: read the 30 printed pairs; any wrong one -> undo with the printed window and stop:
#    $C --undo-batch '<FROM>' '<TO>'          (dry run: counts)
#    $C --undo-batch '<FROM>' '<TO>' --yes
# 3. the rest, 2,000 groups per batch (two batches: ~2,560 groups left), reading each printed sample
$C --yes --no-office-splits --limit 2000 --sample 30
$C --yes --no-office-splits --limit 2000 --sample 30
# 4. lists
docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps worker python -m dgate.ops.warm_lists --yes
```

Each batch rebuilds the buyer families and the directory table (as WP-72/74). Volume: ~3,740 merges, ~34,500 candidate statuses, no new table.

## Tests and checks (local, `D:\DEFENCEGATE TESTS\wp76`, own venv via uv, throwaway Postgres 17 `dgate-wp76` on 55476)

- ruff: clean. Unit: full suite green. Integration: full `-m integration` suite (results in the last section).
- New unit tests (`test_wp76.py`): public identifiers per country and company counter-examples, a shape read in its own country only, public names of every country (incl. the two WP-74 errors), companies not public, buyer role with/without company form, legal forms from alias names, name/legal-form agreement and its refusals (sister, list, agent prefix), the plan (public, no_second_signal, different_legal_form, recorded method 0.99), agent phrases, Nordic `v` vs Czech `v`, sister_company, social insurance, the CLI (`--limit`, `--sample`, `--undo-batch`).
- New integration test (`test_wp76.py`): three groups merged in three batches with `identifier+name` / 0.98 stored, a lone number left pending, a SIRET 2... pair marked `rejected_public_units`; the second batch undone by its window (dry run writes nothing; alias back, original pair `pending`, audit row `undone`, other batches and pending/public pairs untouched; second undo finds nothing).
- Changed tests (rule changed by design, assertions kept): `unit/test_wp72.py` — the fixture rows share one name (the second signal), the head test uses a company SIRET (4...: the old 2... is a local authority's), its group confidence is 0.98 instead of 0.97, and the "accepted" case gives both rows the same company name; `integration/test_wp72.py` — company SIRET and 'chantiers de l atlantique s a' as the second name, method `identifier+name` and confidence 0.98 asserted instead of `identifier`/0.97. Same counts asserted otherwise.

## Self-review (hostile pass)

Found and fixed: (1) the undo counted two candidate rows per merged member with the new method names (`-1 rows without a pair`): counts distinct pairs now; (2) `buyer_cleanup` read only `merge_method = 'identifier'`: now `LIKE 'identifier%'`; (3) a shared word was too weak for the legal-form signal (Hamm sister companies): replaced by `_long_form`; (4) "anywhere inside" let '50hertz offshore die 50hertz transmission ..' through: begins-with only; (5) agents and lists (8 phrases), Nordic `v`/`ved`; (6) different legal forms under one number (SCI/SAS, SRL/SA) now wait; (7) sister companies; (8) BG/FR/DE/AT social-insurance funds were not public. 8 found, 8 fixed.

## Not done / could not check

- The dry run is the branch's `plan()` on production rows read by read-only SQL, not the module run inside the worker (copying code into the production container was refused by the permission classifier); the buyer-family preview of the public pairs was not computed. The orchestrator's step 0 above is the real dry run.
- City/postcode signal: no stored address exists.
- The vocabulary and identifier shapes are not a register; recall is traded for precision (3,475 pairs wait on `no_second_signal`, many correct).
- Scratch: local only (`D:\DEFENCEGATE TESTS\wp76`, container `dgate-wp76`; the CSV dumps of names/identifiers in the session scratchpad were deleted). Checked on the server: no `/root/wp76-dgate.tgz`, no `/tmp/wp76` in `dgate-worker-1`.

## Test results (22 October 2026, final tree, Windows, Python 3.11, Postgres 17)

- `python -m ruff check .`: All checks passed.
- `python -m pytest` (unit, default gate): exit 0.
- `DGATE_TEST_DSN=... python -m pytest -m integration`: exit 0 (full suite, including test_wp72/74/76).
