# WP-151 self-check: French buyers across BOAMP's 2024 eForms switch

Branch `wp-wp151` (base `integration` a27adb8). Backend only; no migration needed (no new column or table).

## Cause, with the evidence available

Finding (RETENDER_CHECK_2026-10-27, "Two data findings", item 1): of BOAMP notices published 2024+, 343 of
2,365 (15%) resolve to a buyer organisation that also has a 2015-2023 BOAMP notice; 2023 against 2021-22: 96%.

**Production was not read.** The session's permission classifier refused the read-only SSH/psql step
("[Production Reads]"), so the per-pattern counts the brief asks for are not in this file. The SELECTs are
prepared in `D:\DEFENCEGATE TESTS\wp151\evidence.sql` (read-only transaction, 120 s timeout: orgs per era,
HTML references per era, new-only orgs with a TED number, name samples), and the ops report below gives
the id-based counts. Both are for the orchestrator to run with the owner's permission.

What the code and the landed payloads show (payload samples from the raw store, October 2026, and the
fixtures):

1. **The BOAMP mapper reads no buyer number.** `from_boamp` sets only `buyer_name_raw = nomacheteur`, so
   `resolve_organisation` never had stage 0 (identifier) for France's national source; every BOAMP buyer
   was resolved by its name alone. TED, for the same French buyers, has used the SIRET since 12 Oct.
2. **Every BOAMP shape states the buyer's SIRET**, at a different path:
   - older schemas (2015-2023): `donnees.IDENTITE.CODE_IDENT_NATIONAL` (19-182081: `MINARM/DGA/DO/S2A`,
     15000035400012);
   - national form `FNSimple`: `organisme.codeIdentificationNational` with `typeIdentificationNational.siret`
     (26-98956 SID Sud-Est, 26-100516 DID SDS, 26-103716 DID Cayenne);
   - eForms: `efac:Organization/efac:Company/cac:PartyLegalEntity/cbc:CompanyID` of the organisation the
     `cac:ContractingParty` names; the review body and the mediator sit beside it with their own numbers
     (24-21716: buyer ORG-0003 Ville de Reims 21510421700017, ORG-0001 the administrative court).
3. **The name is written differently across the switch.** The older schemas' `nomacheteur` is the service
   label (`MINARM/DGA/DO/S2A`, `Marine/DCSSF/DSSF Toulon`); eForms-era records carry the eForms or form
   name (`SID Sud-Est`, `Centre de soutien technique et administratif`, the eForms party name
   `Direction d'Infrastructure de la Défense de Saint-Denis (DID SDS)`), so exact-name resolution opened a
   new organisation for each. The number is the same in both eras for an establishment.
4. **HTML character references in eForms-era names.** `Département de l&#039;Oise` (fixture 26-74042,
   2026): `normalise_org_name` kept `&` and turned `#039;` into a word, `departement de l& 039 oise`, never
   equal to the older `departement de l oise`.

Pattern counts over the ~2,000 split buyers: **not measured** (production not read). The ops report prints
them per method (pairs by SIRET, pairs by exact name, and every left-out reason).

## Change

- `normalise._fr_buyer_identifier` + `from_boamp(...).buyer_identifier`: the SIRET (or SIREN) from the three
  shapes above; exactly one buyer number or none (a joint procurement, junk, other lengths give none);
  through `normalise_identifier(..., "FR")`. `buyer_identifier` is not a versioned field and is left out of
  the payload while empty, so no new version and no hash move for a notice whose content is unchanged.
- `normalise.normalise_org_name`: `html.unescape` before anything else (the matching key only; the stated
  name is kept as written).
- `db` resolution cascade unchanged: with the number now passed, stage 0 (identifier, `names_compatible`
  guard of D8) applies to BOAMP as it does to TED. Tried and withdrawn: treating two SIRETs of one SIREN
  under one name as one buyer. `test_buyer_cleanup::test_sid_sud_est_with_its_own_number_is_a_flagged_body_of_its_own`
  pins the opposite decision (a service stating its own establishment number is a body of its own), so the
  existing rule stays.
- `ops/backfill_buyer_identifiers.collect_identifiers`: an `identify` parameter (default unchanged, the TED
  reader), so the BOAMP repair reuses the greedy bundle cover.
- New `ops/boamp_buyer_ids.py` (report by default, `--yes`, `--undo FROM TO`):
  - reads one landed payload per BOAMP buyer organisation (fewest bundles, up to 3 rounds);
  - **by SIRET** (`boamp_siret`, 0.90): a number stated by exactly two live French organisations (its
    registered holder counted), one with BOAMP notices before 2024, one with BOAMP notices from 2024 only;
  - **by exact name** (`boamp_exact_name`, 0.95): the same rule over today's normalised stated names
    (aliases), which catches the HTML references;
  - left out, with the reason printed: one eForms-era buyer and several older ones, the reverse, several of
    each, both rows on one side, a holder with no BOAMP notice, two different registered numbers, a row in
    two name pairs;
  - a number stated by one organisation only is attached to it (logged in `organisation_repair`, action
    `boamp_identifier_attached`), so its next notice resolves by number;
  - merges through `db.merge_organisations` (older row kept, absorbed row marked `merged_into` with method
    and confidence, `merged` candidate row, aliases and serving rows re-pointed, archive untouched), one
    transaction per pair; then buyer families and the directory table, as `accept_merge_candidates` does;
  - prints its undo: `--undo FROM TO` is `ops.undo_merges` over the run's window and two methods, plus the
    numbers it attached.
  Follow-up after `--yes`: `python -m dgate.reprocess --reclassify-serving --yes`.

## Tests

- `tests/unit/test_wp151.py` (6): SIRET from the older, FNSimple and eForms shapes (buyer's, not the review
  body's; spaces removed), none for a joint procurement / junk / no number; HTML references; the plan's pairs, left-out reasons, attachments and registered-number precedence; a landed record.
- `tests/integration/test_wp151.py` (3): a new notice joins its buyer by SIRET; an HTML reference is the same
  buyer; the ops module on a split state
  built as the old mapper left it: the report changes nothing (organisations, notices, aliases, candidates,
  versions compared), `--yes` merges the SIRET pair and the name pair with method and confidence, leaves the
  one-new-two-old group, attaches the lone number, touches no version; the next eForms notice resolves to
  the kept row; the undo restores every row, number and candidate.
- Full suite in `D:\DEFENCEGATE TESTS\wp151` (own venv, Postgres `dgate-wp151`), 27 Oct 2026: ruff clean;
  unit 4,105 passed; integration 1,575 passed (0 failed). mypy on `ops/boamp_buyer_ids.py`: no finding in it.

## Ops report counts (production)

**Not run**: the production read was refused in this session. Expected to be run once by the orchestrator:

    docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps worker \
        python -m dgate.ops.boamp_buyer_ids

then `--yes` after reading it, then `--reclassify-serving`. Rough expectation from the finding only: up to
about 2,000 from-2024-only organisations, of which the one-to-one SIRET pairs rejoin; a ministry's shared
number shows as "N eForms-era buyers, M older ones" and is left.

## Open items

- Production evidence (evidence.sql) and the ops report counts: need the read permission.
- Display: eForms-era BOAMP names keep `&#039;` in `buyer_name_raw` (only the matching key decodes it); a
  mapper-side decode would write a new version per such notice, so it is left for a decision.
- A new eForms name variant whose words share nothing with the kept row's name and that has no alias yet
  still opens an organisation of its own (the D8 guard); the next run of the ops module pairs it.
