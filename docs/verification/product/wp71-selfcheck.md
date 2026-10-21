# WP-71 self-check: backend fixes of the QA audit (21 October 2026)

- Branch `wp-wp71`, from `integration` at `135bbb0`.
- Audits:
  - `docs/verification/product/qa-full-backend.md` (H1, H2 and the mediums listed in the brief)
  - `qa-full-database.md` finding 2 (e-mail addresses in archived TED versions)
- Tests ran locally in `D:\DEFENCEGATE TESTS\wp71`:
  - own venv
  - throwaway container `dgate-wp71` (Postgres 17, port 55471)
- Production was read-only:
  - short SELECTs with `statement_timeout` 30 s and `default_transaction_read_only`
  - two small read-only probes of the raw store through the worker container, which print counts only and never a name
- Nothing was written to production, deployed or pushed.

## Findings

| # | Finding | State | Where | Tests |
|---|---|---|---|---|
| H1 | e-Zam `contractors[]` landed unstripped | **fixed** | `normalise._strip_nested` and `contractor_is_person`, called by `strip_personal_data` for every source at every depth. A contractor is a person when its national id is a PESEL (11 digits) or `awards.person_reason(name, country PL)` says so: sole-trader forms, PL trading names without a legal form, given names, "osoba fizyczna", or an empty name. Its name becomes `[natural person]`; NIP, city, province and address fields are dropped; companies are kept. A NIP alone cannot tell a CEIDG sole trader from a company, so the name decides there. | unit `test_wp71.py` (3 tests) |
| H1 | already-landed payloads | **tool prepared, not run** | `dgate/ops/restrip.py raw` (report only unless `--yes`), see the commands below | unit `test_restrip_raw_rewrites_a_bundle_in_place_only_with_yes` |
| M5 | top-level-only stripping for every other source | **fixed** | `PERSONAL_DATA_FIELDS` and the eForms person elements (`FamilyName`, `FirstName`, `UltimateBeneficialOwner`, `TechnicalCommitteePerson`, `Telefax`, `Telephone`, `ElectronicMail`, `Contact`, ...) are dropped at any depth, compared on the local name (`cbc:FamilyName`). An organisation with `NaturalPersonIndicator` true keeps only `PartyIdentification`, as `strip_eforms_xml` already did for BKMS. This applies to the BOAMP `donnees` body too. | unit (3 tests) |
| M6 | TED award redaction gaps | **fixed** | `awards._redact` now tests every name the record states: a `winner-name` outside the tenderer list, and every language's list. A per-language identifier block goes when any person is blanked. | unit (2 tests) |
| DB-2 | ~220 archived TED versions with e-mail addresses, ~100 written on 12 Oct | **root cause fixed; rows: break-glass SQL prepared, not run** | The 12 and 14 October writer was `ops.repair_ted`: `plan_change` starts from the current version's payload (pre-sweep), so the old `description` was carried into the new version. `db.append_version` (the one writer of every later version: repair_ted, remap_source, repair_reversions, ingestion) and `upsert_opportunity` now run `scrub_opportunity` on a copy of the record. | integration `test_a_version_written_from_an_old_payload_carries_no_address`, `test_the_restrip_dry_run_finds_the_archived_address_and_writes_nothing` |
| H2 | `/v1/calls/{id}` served BDNS/NCBR text ungated and unredacted | **fixed** | The rule of `/v1/funding/{slug}`: `eligibility_text` and `conditions` only for `SOURCE_TEXT_SOURCES` with `commercial_ok IS TRUE`, through `redact_emails`. Phones are not redacted anywhere in the API (by design, `strip_personal_data` docstring). The gate stops BDNS/NCBR/MATINE/fr_aid text entirely, so their phones do not go out either. | integration (1 test, also checks the flag withdrawing the text) |
| M1 | `/v1/health` degraded during every run | **fixed** | The latest *finished* run is judged. A run in progress is reported (`running_since`) and is a problem only past `db.STALE_RUN_HOURS` (24 h). A partial run under its floor, or with no reason, is unhealthy. A partial run with a stated reason (portal short, feed stale, quarantine) is a `warning` (new `warning_sources`), not degraded. | integration (3 tests); `test_health.py` unchanged and green |
| M2 | connections outside the pool | **fixed** | `db.api_connect()` is now used by api, regulation, partners and readiness. Health has its own bound of 2 (`db.HEALTH_CONNECTIONS`, a separate gate name), so it still answers while the API bound is full. | existing `test_wp49` (saturated pool, health answers) green |
| M3 | PLACSP stale check by day | **fixed** | When both sides carry `source_updated_at`, the instants are compared (`db._instant`). Otherwise the day is compared, as before. | integration (1 test) |
| M4 | `valid_to` rewritable, two open versions possible | **fixed** | Migration `0094_archive_open_version_guard.sql`: the trigger (same name, so the RUNBOOK break-glass step still works) refuses any change to a non-NULL `valid_to`. A unique partial index `opportunity_version_one_open` allows one open version per opportunity. | integration (1 test) |
| M7 | PLACSP drops entries silently; backfill marks the unit done | **fixed** | `parse_feed(counts=)` counts `entries_failed`. `fetch_archive` counts failed entries and skipped members into `observe`. The live run is `partial` with "N feed entries could not be parsed (quarantined, see the log)", as is the monthly-archive fallback. `ops/placsp_archives` raises `Incomplete`, keeps what was read, lists the unit as failed and does not call `mark_backfill_day`. | unit (1 test), integration `test_a_month_with_an_unreadable_member_is_loaded_but_not_marked_done` |
| M9 | IPv6 /48 bypass and O(n) rebuild | **fixed** | IPv6 is bucketed per /48 (`hardening.IPV6_PREFIX`). Pruning above `MAX_BUCKETS` happens at most every 5 s, then evicts the least recently seen down to half. | unit (1 new test); `test_hardening` /64 test changed to /48, see below |
| M10 | X-Forwarded-For from any internal container; secret optional | **fixed (infra, needs a redeploy of api, web, caddy)** | New compose network `edge` (10.250.71.0/29, outside Docker's pools and the host's routes, checked). Caddy has the fixed address 10.250.71.2 there, the API alias `api-edge` exists only there, the Caddyfile proxies to `api-edge:8000`, and uvicorn uses `--forwarded-allow-ips 10.250.71.2`. `DGATE_INTERNAL_SECRET` is `:?` required for api and web in compose. The API sets `DGATE_ENV=production` and refuses to start without the secret (`config.require_production_secrets`, run in the app's lifespan, not at import: the worker imports parts of `api`). `.env.example` documents it without a value. Production already sets the secret (read-only `grep -c`, value not read). `docker compose config` validated locally. | unit (2 tests) |
| M8 | hand-raised 422s not in the contract's shape | **fixed** | One app-level handler: every `HTTPException(422, "text")` of every router, and the DataError handler, answer `{detail: [{loc, msg, type}]}`. Other statuses are unchanged. | integration (1 test). Three existing tests read `detail` as a string and now read `detail[0]["msg"]`, same check, contract shape: `test_funding_api.py:244`, `test_wp39.py:186`, `test_wp57.py:34` |
| M15 | date filters in the session time zone | **fixed** | `/v1/opportunities` and `/v1/calls` `deadline_after`/`deadline_before` are whole UTC days (`api.day_start`/`day_end`). `/v1/funding` `to` uses `time.max` UTC, as tenders does. | unit (1 test), integration (1 test) |
| 4 | mypy note in docs/CLAUDE.md | **not changed** | mypy was not fixed (the audit counts 384 errors in 42 files). `docs/CLAUDE.md` (owner file) still says 20; left for the owner. | – |

Not in scope and not touched: M11-M14, M16-M18, the lows, the CORDIS files (WP-70), the web (WP-67), and the database-audit findings other than 2 (WP-72).

### Tests changed (not weakened)

- `tests/unit/test_hardening.py::test_an_ipv6_client_is_its_64_not_one_bucket_per_address` is now `..._is_its_48_...`. It asserts the stricter key: two /64s of one /48 share a bucket, and two /48s do not.
- The three 422 shape reads listed under M8.

## Machine results

| Check | Result |
|---|---|
| `ruff check .` | clean |
| unit (`pytest`, default gate) | 2,981 passed (2,966 before + 15 new) |
| integration (`-m integration`, local PG 17, fresh database) | 1,156 passed (1,145 before + 11 new), 8 min 24 s |
| new unit tests against the pre-fix code (`git archive HEAD` copy) | 14 of 15 fail; the one that passes is the idempotence guard (strip twice = strip once) |

## Hostile review of the diff

I found 4 issues and fixed all 4:

1. `scrub_opportunity(replace(opp))` re-ran `Opportunity.__post_init__`, which re-derives `sig_cpv_military`. That could undo a deliberate demotion (the municipal fire-extinguisher rule). It now uses `copy.copy`.
2. `restrip raw` would have rewritten a bundle with a line that does not parse, which moves every later line number. Such a bundle is now counted and not rewritten.
3. The integration test that flips `source.commercial_ok` leaked into later tests (`source` is not emptied between tests). It now restores the values in `finally`.
4. Putting the secret check at import time would have crashed the worker, which imports `dgate.api` lazily through funding and tenders and has `DGATE_ENV=production` and no secret. The check moved to the app's lifespan.

Known limits:

- `contractor_is_person` errs on the side of hiding. In the production sample, 32 % of named contractors read as persons, mostly Polish trading names without a legal form, which are sole proprietorships in law. Every nameless entry is treated as a person. Nothing downstream reads `contractors`, so this costs no product value.
- `restrip raw` rewrites bundles in place. `raw_ingest.content_hash` keeps meaning the payload as first landed. Single objects (1 for pl_ezam) are counted and not rewritten, because compaction verifies them by hash. `de_bkms` is refused.
- The Storage Box snapshots keep the old bytes until they roll off. Deleting them is the owner's decision.

## Production measurements (read-only, 21 October 2026)

Archive guard (M4), before migration 0094:

| Check | Count |
|---|---|
| opportunities with more than one open version | 0 |
| `valid_to` before `valid_from` | 0 |
| opportunities with no open version | 0 |

The unique index will build.

Archived versions with an e-mail address anywhere in the payload (full scan, 17.8 s), 221 in all:

| source | observed | `remapped` note | versions |
|---|---|---|---|
| pl_atlas | 2026-09-13 | no | 1 |
| ted | 2026-09-17 | no | 21 |
| ted | 2026-09-19 | no | 86 |
| ted | 2026-10-12 | **yes** | 107 |
| ted | 2026-10-14 | **yes** | 6 |

These are the versions `restrip archive` plans to redact. 113 carry the `remapped` note: the `ops.repair_ted` runs.

e-Zamowienia:

- `raw_ingest` holds 3,398,295 rows (8 Sep to 21 Oct) in 3,465 objects. The store listing shows 3,484 bundles and 1 single object.
- 16,560 result notices are held.
- 0 archived pl_ezam versions have a `contractors` key. The archive payload is the normalised record, so H1 is in the raw store only, not in the archive as the audit assumed.

Raw-store samples (counts only):

| Sample | Records | Contractor entries | Read as persons | Records with a person contractor |
|---|---|---|---|---|
| 5 bundles spread over the store | 5,448 | 4,512 | 3,018 | 2,356 |
| 4 bundles from the middle | – | 4,902 | 3,232 | – |

The 4-bundle sample, by reason:

| Reason | Entries |
|---|---|
| no name | 2,433 |
| trading name | 668 |
| person name | 131 |
| entity | 1,670 |

Calls whose text `/v1/calls/{id}` served before the fix:

| Source | Text | Conditions |
|---|---|---|
| es_bdns | 4 | 4 |
| pl_ncbr | 7 | 7 |
| fr_aid | 0 | 15 |
| fi_matine | 0 | 1 |

All of these are now withheld. eu_portal (159) and se_vinnova (7) are still served, redacted.

Other counts:

- `ted_awards` raw rows: 6,615 (M6 re-strip candidates).
- Serving rows with an e-mail address in a text column: 4. These are not part of this package; an ordinary UPDATE fixes them, see DATA_PROTECTION.

`docs/DATA_PROTECTION.md` was updated with the archive count (221, cause and tool) and the pl_ezam raw-store row.

## Production commands (for the orchestrator; none were run)

After merge and deploy:

```
cd /opt/dgate && git pull --ff-only
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d --build migrate api worker web caddy
```

- `migrate` applies 0094. The unique index builds on about 700 k rows in seconds and takes a brief lock.
- `caddy` and `api` are recreated on the new `edge` network.

Check:

```
docker exec dgate-api-1 python -c "import urllib.request,json;print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/v1/health'))['status'])"
```

A public request should still be rate-limited per visitor. The Caddy log shows the visitor's address, not 10.250.71.2.

Raw store, report only (slow: the SFTP listing of pl_ezam took about 10 minutes, then every bundle is read). Run after the PLACSP archive load, with `DGATE_SFTP_CONNECTIONS=2`:

```
docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps -e DGATE_SFTP_CONNECTIONS=2 worker python -m dgate.ops.restrip raw --source pl_ezam --limit 20
docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps -e DGATE_SFTP_CONNECTIONS=2 worker python -m dgate.ops.restrip raw --source pl_ezam
# then, on the owner's decision (overwrites the landed payloads with the stripped ones; at most 3,484 writes):
docker compose ... run --rm --no-deps worker python -m dgate.ops.restrip raw --source pl_ezam --yes
# same for ted, ted_awards, fr_boamp, nl_tenderned, se_vinnova, eu_portal (report first)
```

Archive (prepare only; the owner runs the SQL as the owner role with api and worker stopped):

```
docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps -T worker python -m dgate.ops.restrip archive --emit-sql - > /root/restrip-wp71.sql
# expected: to_redact 221 (ted 220, pl_atlas 1), or fewer if rows changed
docker compose ... stop api worker
docker exec -i dgate-postgres-1 psql -U dgate -d dgate -v ON_ERROR_STOP=1 < /root/restrip-wp71.sql
docker compose ... start api worker
```

`docs/RUNBOOK.md`, "Data subject requests", step 4, lives on `master`: the integration branch has no RUNBOOK. Each UPDATE applies only if the row's md5 is still the planned one. The file holds redacted payloads only; delete it after the run.

## Scratch

- Local: the container `dgate-wp71` and the `head/` copy were removed; the venv in `D:\DEFENCEGATE TESTS\wp71\.venv` is kept for a rerun (delete the folder when done).
- Production: nothing was created. The probes were read-only and piped through stdin.
