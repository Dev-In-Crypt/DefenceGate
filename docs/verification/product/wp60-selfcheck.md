# WP-60 self-check: PLACSP award winners (20 October 2026)

Implementer's own check, before the independent verifier. Branch `wp-wp60` (from `integration` at ac6268d). Tests
ran locally in `D:\DEFENCEGATE TESTS\wp60` against a disposable Postgres 17 container (`dgate-wp60`, port 55460);
the download and the pilot ran on the server only (2.29.42.177), through the worker image with the branch code
mounted read-only (`/root/dev-wp60/backend`). Inputs: `docs/research/ANGLE1_PLACSP_AWARDS_2026-10-20.md`,
`ANGLE1_DATA_CHECK_2026-10-19.md`.

## What was built

| File | What |
|---|---|
| `backend/dgate/sources/placsp.py` | `parse_results` / `award_payload`: per `cac:TenderResult` the result code, lot, award date, tenders received, SME flag, value (net, with VAT, currency) and each `WinningParty` (name, identifier and scheme, country). Never in the `Opportunity`. `parse_feed(results=)` and `fetch_archive(with_results=True)` carry the payload next to each record (through the same disk spool). `fetch_archive(min_free_bytes=)` / `DiskLow`: the free space is checked every 64 MiB of download and after each member parsed |
| `backend/dgate/placsp_awards.py` | `redact` (persons blanked before landing), `read` (winners with the TED loader's rules), `Loader` (land under `placsp_awards/`, source `es_placsp_awards`, then `awards.store_notice`; `land_only` mode), `replay_from_store` (load from the landed payloads without a download; `commit=False` measures and rolls back) |
| `backend/dgate/awards.py` | Spanish person rules in `person_reason`: DNI / NIE, the publisher's masked NIF (`***1234**`, any country), a CIF means a legal entity; capitals-only Spanish names (`GARCIA LOPEZ JUAN`, `MARTINEZ SANCHEZ, ANTONIO`, particles allowed) are persons when the name has no legal form or business word. `is_joint_venture` / `joint_venture_name` (UTE kept as a party, a person member replaced by `[natural person]`; capitals `UTE` only, as "Ute" is a German given name). `store_notice(payload_hash=, payload_updated_at=)`: a PLACSP notice is re-read when its payload changes; a winner no longer named gets `superseded_at`, one named again is current again; TED keeps its read-once behaviour |
| `backend/dgate/pipeline.py` | `_ingest_placsp(awards=factory)`: each kept record's award payload is landed and loaded after its notice, in the same transaction, both writers drained before every commit |
| `backend/dgate/ops/placsp_archives.py` | the archive command: dry run by default, `--yes`, `--from/--to`, `--land-only`, `--from-store`, `--min-free-gb` (3), resumable (`backfill_day` markers `es_placsp-awards` and `-progress`), stops on 429, on low disk, before the live window |
| `backend/dgate/suppliers.py`, `config.py` | `scope()`: superseded rows never served; PLACSP winners (and their person counts) left out unless `DGATE_PLACSP_AWARDS_PUBLIC=true` (default false) |
| `backend/migrations/0092_placsp_awards.sql` | `award_notice.payload_hash`, `payload_updated_at`, `award.superseded_at`, source row `es_placsp_awards` (inactive) |
| `docs/sources/es_placsp.md` | licence reading with verbatim quotes, URLs and date; the twelve questions |
| `docs/DATA_PROTECTION.md` | inventory rows for `placsp_awards/` and the PLACSP `award` rows |

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| 1. Connector reads TenderResult, WinningParty name and identifier, value and currency, award date, lot, tenders received, result code into a separate payload | **met** | `parse_results`; unit test `test_the_results_are_read_per_lot_with_winner_value_date_and_tenders`; on the pilot month: 2,552 results in 1,640 folders |
| Notice content hash and `opportunity_version` do not move because of awards | **met** | unit `test_collecting_the_results_does_not_move_the_notice_payload_or_its_hash`; integration `test_the_awards_do_not_move_the_notice_hash_or_make_a_version` (same entries walked without, then with awards: one version, same hash). Pilot: 51 changed versions out of 86,224 entries, all from the normal replay rules (deadline amendments, remapped corrections) and none with an award field (the payload has none) |
| Landed under its own key shape `placsp_awards/YYYY/MM/DD/...` | **met, as bundles** | keys are `placsp_awards/2026/10/20/run-<tag>-<part>.jsonl.gz#<line>` (the `BundleWriter` of every other source, `ted_awards` included), not one `<id>.json` object per payload: 2,543 single objects a month on the Storage Box was the cost the bundles exist to avoid. `raw_ingest` carries the folder id and hash per payload |
| Stripped of personal data before landing (DNI/NIE, masked NIF, person names incl. capitals, sole traders; keep "natural person" + count; UTE as a joint venture with company members only) | **met as far as rules can be** | `redact`; unit tests (10 Spanish person shapes, 7 company shapes, UTE blanking, no name / number / street / city in the landed JSON); integration `test_the_walk_files_the_notice_and_its_company_winners_and_keeps_no_person` (no person in `organisation`, `organisation_alias`, `award`, raw store). Pilot: 116 distinct persons in 1,640 folders, all blanked; of the 50 company names sampled below, 0 are persons |
| 2. Loader reuses `award`, `award_notice`, `organisation` via the cascade; no new resolution | **met** | `awards.store_notice`, `resolve`, `_namesake_guard`, `_attach_reg` unchanged in kind |
| Idempotent | **met** | integration `test_a_second_walk_writes_nothing` (7 tables counted); `test_the_command_runs_one_month_marks_it_and_skips_it_next_time` (second run: no download) |
| Re-read when a winner changes after the first award | **met** | `test_a_changed_winner_is_read_again_and_the_old_one_superseded_not_deleted` (ADJ to RES with another winner; an older entry read late changes nothing; a newer one naming the first winner again reuses its row) |
| Replayable from the raw store without refetching | **met** | `test_the_winners_are_replayed_from_the_raw_store_without_a_download`, `test_a_land_only_walk_writes_no_award_and_the_store_load_does_it_later`; on production the pilot month was loaded from the store in a rolled-back run (98 s, no request to PLACSP) |
| 3. `ops/` script 2023-01..2026-10, dry run by default (archive list, sizes, disk estimate), `--yes`, resumable with checkpoints, progress log, stops cleanly under 3 GB free | **met, sizes are estimates** | `dgate/ops/placsp_archives.py`. The publisher sends archives chunked without `Content-Length`, ignores `Range` and drops `HEAD` (measured), so the dry run prints estimated sizes (a month 400 MiB as measured, a year the connector's 2 GiB ceiling) and checks the disk while downloading. Tests: units, plan text, disk floor (`test_the_command_stops_cleanly_when_the_disk_is_short`, `test_the_archive_walk_stops_before_the_disk_falls_under_its_floor`) |
| 2025 gap fixed through the normal pipeline path | **built, not run** | the 2025 unit is the annual archive `..._2025.zip`, read in replay mode through `_ingest_placsp` (dedupe and version rules unchanged); integration test shows a notice not held is inserted on that path. The full run is the orchestrator's |
| 4. Licence read, `docs/sources/es_placsp.md` with verbatim quotes, URL, date | **met, with a gap stated** | commercial reuse allowed by the Ministerio de Hacienda aviso legal that the official datos.gob.es entry names as its conditions. **PLACSP's own pages were not read: both portal hosts have `Disallow: /`**. Natural persons: governed by LO 3/2018, not clearly allowed, not kept |
| Winners not shown publicly; `DGATE_PLACSP_AWARDS_PUBLIC=false` by default | **met** | `suppliers.scope()`; `test_the_supplier_map_leaves_placsp_winners_out_unless_switched_on`. **On production the old API code has no such filter, so no PLACSP award row was written there** (see the pilot) |
| Pilot: dry run and `--yes` for one month on production, rows, timing, disk, field rates, natural-person share | **met, land-only** | below |
| Full backend suite locally (ruff, unit, integration) | **met** | ruff clean; unit suite passed; integration suite passed (exit 0) on the branch, against `dgate-wp60` |

## The pilot (production, 2026-09)

1. `docker compose run --rm migrate` with the branch's migrations mounted: applied **0092** (the only pending one).
2. Dry run: printed the plan (the first dry run also tried `HEAD` on the 13 archives; every one was dropped by the
   server, so the code no longer asks).
3. `python -m dgate.ops.placsp_archives --from 2026-09 --to 2026-09 --land-only --yes` in container
   `dgate-wp60-pilot` (worker image, branch code mounted read-only). **`--land-only`, not a full load**: the API in
   production runs the integration code, whose supplier map has no PLACSP filter; writing award rows would have
   published the PLACSP winners at once. The winners were landed, and their load was measured from the store in a
   rolled-back transaction (`--from-store` without `--yes`).

| Measure | Value |
|---|---|
| Archive | `licitacionesPerfilesContratanteCompleto3_202609.zip`: 95,910 entries, 9,686 dropped as updated before 2026-09-01 (the known loose filename match), 86,224 walked |
| Time | 1,203 s: download about 4 min (about 360 MB, about 1.5 MB/s), parse and spool about 2 min, ingest 14.5 min |
| Disk | free 7.26 GB before, 6.82 GB at the lowest (peak use about 440 MB), 7.12 GB after (the temporary files go with the unit); never near the 3 GB floor |
| Memory | about 150 MB of the worker's 2 GiB |
| Notices (normal replay path) | 2 new, 51 changed versions, the rest unchanged |
| Award payloads landed | 2,543 (1,640 folders; a folder's ADJ and RES entries are two payloads), `raw_ingest` 525 kB |
| Results | 2,552: code 9 (formalised) 1,700, 8 (awarded) 689, 3 (deserted) 151, 4 (withdrawn) 10, 5 (not documented) 2 |
| Field presence, on the 2,389 awarded results (8, 9) | winner 100 %; value 100 %; award date 100 %; tenders received 100 %; lot id 44 % (single-lot contracts state none) |
| Winner entries | 2,389: companies 2,229, natural persons 159, one name with contact data |
| NIF present | companies 2,229 of 2,229 (2,172 a Spanish CIF, 57 another scheme, 80 scheme OTROS); persons 116 of 116 distinct (counted at redaction; not stored) |
| Natural-person share | 116 distinct persons against 1,698 company winners kept: **6.4 %** of the winners of a folder (159 of 2,389 lot entries, 6.7 %) |
| Country | ES 2,174, other 24, none 31 (13 left without a country after the CIF rule) |
| UTE | 29 entries, 14 distinct joint ventures kept |
| Load from the store (rolled back) | 98 s; would write **1,698 award rows**, 1,449 notices loaded, 88 with persons only, 103 without a winner, **604 new organisations** (1,065 matched by alias, 29 by national id); nothing kept |
| Production after the pilot | no `award` row of a PLACSP notice (checked: 0); 2,543 `raw_ingest` rows of `es_placsp_awards`; `backfill_day` `es_placsp-awards` 2026-09-01 done |

Sample of 50 kept company names (by hash of the name), read by hand: all 50 are legal entities (49 with a legal
form such as S.L., S.A., S.A.U., one association, one "LANGUAGE CENTRE" trade name). Three are companies named after
a person ("... GOMEZ SL"): legal entities by their CIF and legal form, kept by design. **0 of 50 are natural
persons.**

## Requests to PLACSP made by this package

From the server only, with the connector's User-Agent: one page of the live feed (20 October, to read the result
paths), 13 `HEAD` requests (dropped by the server), one `curl` with a `Range` header to look for a size (the
server ignored the range and sent the file for about two minutes before it was stopped), and the 2026-09 archive
once. Nothing from the laptop.

## Hostile review of the diff

Issues found and fixed: 8.
1. Redacting a payload read back from the store counted every blanked person as one person ("" names collapse):
   landed payloads are no longer redacted again.
2. A UTE re-read from the store failed the person test on its own `[natural person]` member: UTEs are checked by
   member.
3. `ute` as a legal form would have made "Ute Schmidt" (DE) a company: removed; the UTE test is capitals-only and
   Spanish.
4. The first store replay re-landed every payload into new bundles: it now reuses the stored key.
5. The first store replay read by `award_notice`, which a land-only walk never writes: it reads `raw_ingest`, newest
   payload per folder by the entry's own stamp, in landing order (one bundle read once).
6. An older entry read after a newer one could restore the old winner: the entry's stamp is kept and older payloads
   are skipped.
7. `HEAD` and `Range` do not work on the publisher's server: the size check moved into the download.
8. **A full pilot load would have published PLACSP winners on production** (the deployed API has no filter): the
   pilot was run land-only.

Known limits, not fixed:
- `SHOWN` (the displayed spelling of a supplier) may pick a PLACSP spelling for a supplier that is public through TED.
- When PLACSP winners are switched on, a notice published both in PLACSP and in TED counts twice on the map (no twin
  merge of awards).
- The live nightly walk does not collect award results; new awards arrive only through this command (a monthly run
  of the current month, or a later change to wire `with_results` into `fetch_live`).
- Award value and lot are in the landed payload, not in `award` (WP-37 keeps no value per award; an owner decision).
- The Spanish name rule leaves out some companies without a legal form or CIF (by design: a missed supplier is a
  gap, a published person is a harm).
- Whether the 2025 annual archive exists on the server was not checked (a `HEAD` is dropped); if it is missing the
  unit fails and is reported, the others continue.

## Commands for the orchestrator (production)

Deploy first (migration 0092 is applied already; the deploy brings the supplier-map filter), then, outside 06:20 to
08:30 UTC, as a one-off container:

```
cd /opt/dgate
docker compose -f infra/docker-compose.yml --env-file infra/.env run -d --no-deps --name dgate-placsp-awards \
  worker python -m dgate.ops.placsp_archives --from 2023-01 --to 2026-10            # dry run: the plan
docker compose -f infra/docker-compose.yml --env-file infra/.env run -d --no-deps --name dgate-placsp-awards \
  worker python -m dgate.ops.placsp_archives --from 2023-01 --to 2026-10 --yes      # 2026-09 is skipped (done)
docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps \
  worker python -m dgate.ops.placsp_archives --from-store --yes                     # loads 2026-09 (landed only)
```

Rerun the same `--yes` command after an exit 75 (stopped: disk, 429, live window, lost database); it resumes.
Expected: 12 more units (3 annual, 9 monthly) of roughly 0.4 GB (months) to under 2 GB (years) each, one at a time,
peak disk under 2.5 GB above the 3 GB floor; about 20 minutes a month and, by entry count, 2 to 3 hours a year:
**about 10 to 12 hours** in all, with 2025 filled for notices (expect several thousand new notices that year).
Awards: about 30,000 notices and 35,000 to 55,000 award rows, 6,000 to 12,000 new organisations, database growth
20 to 35 MB, raw store tens of MB. To publish the winners: owner decision, then `DGATE_PLACSP_AWARDS_PUBLIC=true` for
the API and a redeploy.

Server scratch of this package: `/root/dev-wp60/` (branch code for the pilot, `rates.py` that measured the field
rates, `disk.log`). Delete when the branch is merged. Local: `D:\DEFENCEGATE TESTS\wp60`, `wp60b`, container
`dgate-wp60`.
