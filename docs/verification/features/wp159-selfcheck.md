# WP-159 self-check: contract periods and API sources

Branch `wp-wp159` from `integration` 53dc50d. Test copy `D:\DEFENCEGATE TESTS\wp159\` (own Postgres `dgate-wp159` on port
56159, removed at the end). No screenshots: nothing in the web changed (no forecast UI, as the brief says). No
production access, no portal called. The only external page read was the TED field list
(`docs.ted.europa.eu/ODS/latest/reuse/field-list.html`, one request; the host has no robots.txt, 404).

## What was built

### 1. Contract periods, going forward (migration 0151)

One reader, `normalise.contract_period(g)`, over TED's own field names (one entry per lot):

| eForms | TED search field (field list, 30 Oct 2026) | stored as |
|---|---|---|
| BT-36 duration (OPA-36 number, BT-36 unit) | `duration-period-value-lot`, `duration-period-unit-lot` | `contract_duration` + `contract_duration_unit` (DAY/WEEK/MONTH/YEAR, as stated) |
| BT-536 start | `contract-duration-start-date-lot` | `contract_start` |
| BT-537 end | `contract-duration-end-date-lot` | `contract_end` |
| BT-58 max renewals | `renewal-maximum-lot` | `contract_renewals_max` |
| BT-57 renewal description | `renewal-description-lot` (presence only) | `contract_renewal` (TRUE or NULL) |

Several lots: earliest start, latest end, longest duration (compared in months, stored as stated), most renewals. A
fractional duration becomes whole months; a duration over 100 years, an unknown unit, a year outside 1990-2100 and an
end before the start are not read. Value and unit pair by position, or by the one unit every lot states; never guessed.

The sources that feed it:
- **TED**: the six fields are added to `ted.TED_FIELDS`; `from_ted` reads them. Result notices are TED opportunities
  too, so awards get their period on the same row (`read_award` reads winners only and was not touched).
- **BKMS**: `de_bkms.ted_fields` reads `ProcurementProjectLot/ProcurementProject/PlannedPeriod` and `ContractExtension`
  (`MaximumNumberNumeric`, `Renewal`) into the TED names, so `from_de_bkms` gets it through `from_ted`. Parts skipped.
- **BOAMP eForms**: `normalise._fr_eforms_period` reads the same elements from the JSON body (`{"@unitCode", "#text"}`)
  and hands them to the same reader. The older French schemas (2015-2023 `DUREE_MOIS` etc.) are **not** read.
- **PLACSP**: `placsp.contract_period(cfs)` reads `cac:PlannedPeriod` (UN/ECE units MON/ANN/DAY/WEE) of the folder's
  `ProcurementProject` and of each lot's, and `cac:ContractExtension` (any text other than "No"/"Sin prórrogas" =
  renewal stated; CODICE has no renewal count). Called from `parse_entry`, so it lands in the normalised payload the raw
  store keeps. `award_payload` was not changed: the period is on the folder's own row.

Storage: non-versioned columns on `opportunity` by the existing recipe, no `award_notice` change:
- `Opportunity` fields `contract_*`; `db.CONTRACT_PERIOD_COLUMNS`;
- `db.opportunity_payload`: absent while empty, so no hash moves for a notice without a period (PLACSP hashes it);
- `db._DATE_FIELDS` (+ `contract_start`, `contract_end`), `db._serving_columns`, `db.KEPT_WHEN_ABSENT` (a version
  that does not state a period never erases one);
- `db.upsert_opportunity`, the no-version UPDATE: `COALESCE(new, held)` for each column. So a notice re-read with a
  period and nothing versioned changed gets the period and **no version** (integration test below).
- not in `VERSIONED_FIELDS`. Migration 0151 adds the six columns and a `NOT VALID` check (no table scan).
- `ops.repair_ted`: the columns are in `REMAPPED`, `DIRECT_COLUMNS` (written without a version), `PRESERVE` and
  `CARRIED_COLUMNS` (a period held only on the serving row is not erased by a refetch that states none).

### 2. Backfill (ops, report by default, `--yes` to write)

`python -m dgate.ops.contract_periods` (new, `backend/dgate/ops/contract_periods.py`):
- no argument: coverage of the stored periods per source (kept notices: period, end, duration, renewal, ends in the
  next 12 months);
- `--backfill de_bkms|fr_boamp [--yes] [--limit N] [--workers N]`: each notice's latest landed payload is mapped again
  and its period written on the serving row (no version; only values the payload states; idempotent). Report mode
  rolls back.

### 3. API sources

- `config.api_key_sources` default `ted,nl_tenderned` (TenderNed is CC0). Not BKMS (inactive, GDPR items open); Vinnova
  feeds calls, which keys cannot read.
- `infra/docker-compose.yml`, `api` service: `DGATE_API_KEYS_OPEN: ${DGATE_API_KEYS_OPEN:-0}` and
  `DGATE_API_KEY_SOURCES: ${DGATE_API_KEY_SOURCES:-ted,nl_tenderned}` (keys still off).
- Migration 0151: `se_vinnova` licence CC0 (0026 already set it; set again only where it differs), `de_bkms` licence
  CC0 (Open-Data-Richtlinie section 4). `de_bkms` stays `active = FALSE`, `commercial_ok = NULL`.

## Gates

No paid feature and no `billing` entry: the periods are stored, not served, and the key list is the existing WP-153
gate (`apikeys.dispatch`, `DGATE_API_KEYS_OPEN` off).

## Tests

- Unit `backend/tests/unit/test_wp159.py` (24): the reader (lots, units, fractions, mismatched lists, typos, renewal),
  TED fields requested and mapped, BKMS through `from_ted`, BOAMP eForms (lot as list or dict, Part skipped), PLACSP
  period and "No" extension, payload absent while empty / not versioned / kept when absent, date round trip, the
  `repair_ted` plan (period as a direct column, never erased), the backfill's `moves`, the default key sources.
- Integration `backend/tests/integration/test_wp159.py` (4): a stated period writes no version and a later version
  keeps it; the BKMS backfill from a filesystem raw store (report writes nothing, `--yes` fills, second run unchanged,
  coverage); the licences read CC0 and the migration leaves `active` and `commercial_ok` alone; a key reads TED and TenderNed by default, not PLACSP.
- Full runs in the test copy: see "Results" below.

No existing test was changed.

## Ops to run on production (orchestrator, in this order)

1. Migrate (0151). Before deploying the TED change: one dry-run request to confirm TED accepts the six field names,
   e.g. `docker compose run --rm worker python -m dgate.ops.repair_ted --refetch --limit 100 --epoch 159` (report
   only, one request to TED: an external call, so with the owner's yes). If TED refuses a name, the daily TED pull
   would fail: drop that name from `ted.TED_FIELDS` before deploying.
2. `docker compose run --rm worker python -m dgate.ops.contract_periods --backfill de_bkms` (report), then `--yes`.
3. The same for `fr_boamp`.
4. `docker compose run --rm worker python -m dgate.ops.contract_periods` (coverage per source) for the report.
5. Owner's yes only (external): TED history `python -m dgate.ops.repair_ted --refetch --epoch 159 --yes` (about one
   request per 100 TED notices, one a second); PLACSP `python -m dgate.pipeline placsp-backfill --start 2022-01
   --no-resume` (archive downloads; replayed entries older than the held one are "stale" and skipped, the held entry
   itself gets its period without a version).

Expected coverage after steps 2-3 (from docs/research/RETENDER_CHECK_2026-10-27.md, raw store of 27 Oct): BKMS about
79 % of awards and 76 % of contract notices with a duration or an end; BOAMP eForms notices (2024+) 31-75 % of awards
and 53-86 % of contract notices. BOAMP 2015-2023 stays empty (older schemas not read).

## Left out, open

- BOAMP older schemas (`DUREE_MOIS`, `DUREE_JOURS`, `DATE_DEBUT/FIN`, `RECONDUCTIONS`): most of France's 2015-2023
  periods; a second reader.
- Framework flag and framework duration (BT-109/`FrameworkAgreement`): not asked.
- Serving: no API field, no filter "ending between", no UI. The columns are ready for it.
- The TED field names are from the documentation page, not yet from a live answer (step 1 above). Pre-eForms TED
  notices: unknown whether the API returns these fields for them.
- PLACSP: whether live CODICE entries carry `PlannedPeriod` widely is unmeasured (the fixtures carry none).

## Shared files touched

`backend/dgate/config.py` (one default), `infra/docker-compose.yml` (two env lines), `backend/dgate/apikeys.py`
(docstring), `backend/dgate/db.py`, `backend/dgate/normalise.py`, `backend/dgate/sources/{ted,de_bkms,placsp}.py`,
`backend/dgate/ops/repair_ted.py`. Not `billing.py`, not `app-nav.tsx`, not `web/lib/pricing.ts`.

## Results

In `D:\DEFENCEGATE TESTS\wp159\` (logs there): ruff clean; unit 4,157 passed (43 s); integration 1,609 passed
(18 min, own Postgres on 56159). After the last lint and test edits: unit suite again green, and
`test_wp113`, `test_wp159`, `test_api_keys_wp153`, `test_repair_ted` integration green. mypy (informational): no new
finding in the changed files (477 in the tree against 479 on `integration`). No web file changed, so tsc, lib checks
and Playwright were not run. Container `dgate-wp159` removed at the end.
