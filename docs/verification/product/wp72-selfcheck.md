# WP-72 self-check: database and data fixes from the QA audit

Branch `wp-wp72` from `integration` at 135bbb0. Audit: `docs/verification/product/qa-full-database.md` (21 Oct 2026).
Production was used read-only: SQL with `default_transaction_read_only=on` and `statement_timeout` 30 s, and the
three new or changed ops modules run as **dry runs only** from a scratch copy of this branch's `dgate/` in the worker
container (`/tmp/wp72`, `PYTHONPATH=/tmp/wp72`, `PGOPTIONS=-c default_transaction_read_only=on`). Load stayed between
0.9 and 2.3 (ceiling 6). Nothing was written on production, nothing deployed, no portal called, no model called.
Tests ran locally in `D:\DEFENCEGATE TESTS\wp72` (own venv via uv, throwaway Postgres 17 container `dgate-wp72`).

Migration numbers used: **0096** (the parallel WP-70/WP-71 had none yet; renumber on merge if they take it).

## 1. Performance

**Cause.** The tenders list of one country (`country=MT`, 165 defence rows) and a buyer page (`buyer=196`) walk the
whole list index of their order (`opp_list_published`, `opp_list_deadline_asc`, `opp_list_deadline_desc`, about
290,000 entries) and filter: production EXPLAIN (no ANALYZE) of the list SQL generated from the code, total costs
157,000 to 180,000 for every order (MT published, MT closed, MT all/rest, buyer 196 published, closed, all/rest).
The default lists are fine (`default closed` LIMIT cost 84; `open` uses `opp_open_candidates`). A second cause is in the
SQL: the filters were `o.country = ANY(%s)` and `o.buyer_org_id = ANY(ARRAY(SELECT unnest(dgate_family_ids(%s))))`,
which give the planner no ordered path even with a (country, order) index.

**Change.**
- `migrations/0096_country_and_buyer_list_indexes.sql`: six partial indexes `WHERE is_defence AND NOT suppressed`,
  (country | buyer_org_id) + each of the three list orders. About 14 MB each (the existing list indexes are 12-16 MB),
  so about 85 MB. Additive, `IF NOT EXISTS`, ends with `ANALYZE opportunity`.
- `tenders._tender_filters(..., conn=)`: one country is `o.country = %s`; the buyer's family is read first
  (`dgate_family_ids`) and a one-row family is `o.buyer_org_id = %s`, a larger one `= ANY(<the ids>)`. Same rows as
  before (integration test), the collapse rules copy the clause as before.
- Measured on a synthetic 380,000-row copy (285,000 defence, MT 165 rows, a buyer with 6,350), `EXPLAIN ANALYZE`:
  MT closed 23.1 ms -> 0.65 ms, MT all/rest 19.5 -> 0.72, MT published 18.1 -> 2.2, buyer 196 published 25.6 -> 0.17,
  buyer 196 all/rest 26.2 -> 0.16, each on the new index of its order. (Production's collapse sub-plans are dearer per
  row, so the absolute gain there is larger.)
- `raw_ingest` indexes (audit: `raw_ingest_pkey` 496 MB and `raw_plain_key` 451 MB with `idx_scan = 0` since the
  statistics reset): **not dropped, no drop migration.** Neither is provably unused: `raw_plain_key` (partial on keys
  without `#`) is the index `ops/compact_raw._still_referenced` and the repointing in `compact_raw` rely on before an
  object is deleted ("the literal NOT LIKE is what keeps this query on the partial index"), and `raw_ingest_pkey` is
  the primary key the compaction and `bundle_audit` updates use (`WHERE r.id = ...`). `raw_hash` (1.9 GB) and
  `raw_recent` (887 MB) are in use (220,000 and 28 scans). Outside `raw_ingest`, two indexes no code reads: `opp_search`
  (35 MB, GIN on `search_tsv`, no `@@` anywhere) and `opp_core_published` (5.7 MB, superseded by `_v2` in 0045, already
  in DELETION_CANDIDATES). Not dropped here (outside the brief); listed for the owner.
- `infra/docker-compose.yml`, service `postgres`: `shared_buffers=768MB`, `effective_cache_size=2GB`, `work_mem=16MB`,
  `maintenance_work_mem=128MB`, `autovacuum_work_mem=64MB`, `random_page_cost=1.1`, `effective_io_concurrency=200`,
  `shared_preload_libraries=pg_stat_statements`, `shm_size: 256mb`; the reasoning is in the file. Measured on the host:
  3,819 MB RAM, 2 cores, used 1,655 MB, buff/cache 2,346 MB; containers: worker 560 MB (limit 2 GB), web 166 MB and
  api 114 MB (limit 512 MB each), postgres 307 MB; current settings 128 MB / 4 MB / 64 MB / 4; `/dev/shm` 64 MB.
  768 MB rather than 1 GB because the worker's limit is 2 GB and the PLACSP loads run beside it.

**Production commands (orchestrator).**

```bash
ssh -i ~/.ssh/hetzner_key root@2.29.42.177
# a) the indexes, before the deploy, one at a time (no write lock; about a minute each; ~85 MB disk)
for ddl in \
 "opp_list_country_published ON opportunity (country, (coalesce(published_at, notice_date)) DESC NULLS LAST, id DESC)" \
 "opp_list_country_deadline_asc ON opportunity (country, deadline_at ASC NULLS LAST, id ASC)" \
 "opp_list_country_deadline_desc ON opportunity (country, deadline_at DESC NULLS LAST, published_at DESC NULLS LAST, id DESC)" \
 "opp_list_buyer_published ON opportunity (buyer_org_id, (coalesce(published_at, notice_date)) DESC NULLS LAST, id DESC)" \
 "opp_list_buyer_deadline_asc ON opportunity (buyer_org_id, deadline_at ASC NULLS LAST, id ASC)" \
 "opp_list_buyer_deadline_desc ON opportunity (buyer_org_id, deadline_at DESC NULLS LAST, published_at DESC NULLS LAST, id DESC)"; do
  docker exec dgate-postgres-1 psql -U dgate -d dgate -v ON_ERROR_STOP=1 -c "CREATE INDEX CONCURRENTLY IF NOT EXISTS $ddl WHERE is_defence AND NOT suppressed"
done
# (a failed CONCURRENTLY build leaves an INVALID index: DROP INDEX CONCURRENTLY <name>; and run it again)
# b) deploy the branch as usual; migrate applies 0096 (no-op indexes + ANALYZE opportunity)
# c) the Postgres settings: a restart of the postgres container, 10-30 s of API 503s; pick a moment without a load
docker exec dgate-postgres-1 psql -U dgate -d dgate -c "CHECKPOINT"
cd /opt/dgate && docker compose -f infra/docker-compose.yml up -d postgres
docker exec dgate-postgres-1 psql -U dgate -d dgate -Atc "SHOW shared_buffers; SHOW work_mem; SHOW random_page_cost; SHOW shared_preload_libraries"
docker exec dgate-postgres-1 df -h /dev/shm          # 256M
docker exec dgate-postgres-1 psql -U dgate -d dgate -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements"
curl -fsS https://<api>/v1/health >/dev/null && free -m
#    if api or worker do not reconnect on their own: docker compose -f infra/docker-compose.yml restart api worker
# rollback of c): restore the previous infra/docker-compose.yml (git), then
#    docker exec dgate-postgres-1 psql -U dgate -d dgate -c "DROP EXTENSION IF EXISTS pg_stat_statements"
#    cd /opt/dgate && docker compose -f infra/docker-compose.yml up -d postgres
#    (the settings are command-line flags only; nothing is written to postgresql.auto.conf)
# d) after c): EXPLAIN the MT and buyer 196 lists again (expect opp_list_country_* / opp_list_buyer_*)
```

## 2. Classification leak through a dual-use twin

**Cause.** `pipeline._twin_is_defence` set `sig_linked_defence` when the twin was merely `is_defence`, and
`SUPPLY_SQL` puts every linked row in `supply` (the default `relevant` list). A TED notice that is only dual-use
(military CPV demoted for a civil buyer) therefore lifted its national copy above itself.

**Change.** `classify.OWN_RELEVANCE_SQL` / `own_relevance_sql(alias)` and the Python twin `relevant_on_its_own`: the
twin counts only when it is in `core` or `supply` **by its own signals, with its own link read as false** (so two
twins cannot qualify each other). Used in both directions of `pipeline._twin_is_defence`, and in the two candidate
selections of `reprocess` (`--twin-linked`, `--linked`). `reprocess.RULES_EPOCH` -> `twin-defence-2`.
New ops module `dgate/ops/linked_defence.py` (dry run by default, `--yes`): for every stored `sig_linked_defence` row
whose twin no longer counts, `sig_linked_defence = false` and `is_defence` derived again from the other stored signals;
no version (classification is ours, as `refresh_classification`), nothing deleted, only ever clears, so a second run
does nothing. The audit's rule ("only when the linked notice is core or supply") is the one implemented.

**Dry run on production** (21 Oct 2026, 16:29 UTC):
`linked rows 23,888: twin still counts 23,307, to clear 581` (pl_ezam 314, de_bkms 228, es_placsp 34, es_placsp_agg 3,
nl_tenderned 1, fr_boamp 1). All 581 were in `supply`; after the change none is relevant (the twin is held in all 581
and is not relevant on its own); 265 have no other signal and leave `is_defence` (the audit's 264), 316 keep
`is_defence` through another signal (a demoted military CPV) and move to the dual-use-only bucket (`scope=all`).
More than the audit's 264 because the audit counted only rows with no other signal. 15 sampled rows, read by hand,
all correctly not defence-relevant (yes = the fix is right): Radomsko town misc. supplies, Powiat Plonski equipment,
Gmina Biala Piska fire engines, Gmina Niepolomice workshop PCs, Powiat Belchatowski teaching aids, Maritime Search and
Rescue software (x3), State Fire Service command vehicle, agricultural school tractors and machines (x3), psychiatric
institute medical supplies, a Spanish port authority supply, a town council's uniforms: 15/15 yes.

```bash
docker compose -f infra/docker-compose.yml run --rm worker python -m dgate.ops.linked_defence        # dry run, ~15 s
docker compose -f infra/docker-compose.yml run --rm worker python -m dgate.ops.linked_defence --yes  # 581 rows
docker compose -f infra/docker-compose.yml run --rm worker python -m dgate.ops.warm_lists --yes
```

## 3. Calls whose source status lags the dates

**Cause.** The rule already exists (`funding.EFFECTIVE_STATUS`, used by `/v1/funding`, the calendar, the .ics, the
CSV), and on production it already settles all 11 audit rows (9 forthcoming with `opens_at` passed and deadline ahead
-> open, 52256939 -> closed; 49662814 is `continuous`, open by design). But the older `/v1/calls` (and
`/v1/calls/{id}`) filtered and served the raw `c.status`.

**Change.** `/v1/calls` filters by `EFFECTIVE_STATUS` and both endpoints serve it as `status` (`evaluated` is still
filterable as the source's word). No daily refresh job: the status is a function of the dates and now, computed at
read time in one expression; a stored refresh would only lag it. No production command.

## 4. Sources

- **de_bkms `source_url`.** The stored day-file payloads name no page on oeffentlichevergabe.de (read 8 payloads from
  the raw store: the only URLs are buyer web sites and the procurement-documents address), so a portal URL built from
  the notice id could not be verified from our data and was **not built**. Instead the mapper reads BT-15
  (`CallForTendersDocumentReference/Attachment/ExternalReference/URI`), the notice on the buyer's own tendering
  platform, through `http_url`. Verified on stored payloads: 25944212 ->
  `https://www.meinauftrag.rib.de/public/DetailsByPlatformIdAndTenderId/platformId/1/tenderId/304786`, 3103c91b-... ->
  `https://vergabeplattform.bwi.de/NetServer/TenderingProcedureDetails?function=_Details&TenderOID=54321-Tender-19eb096a108-72fb98ad587ab986`,
  f1c9072b-... -> `https://www.evergabe-online.de/tenderdocuments.html?id=887673`, adcff337-... ->
  `https://vergabe.hilgmbh.de/VMPSatellite/notice/CXT6YYDDYYQAJ2A6/documents`, 21493452 ->
  `https://vergabe.niedersachsen.de/Satellite/notice/CXQ6YY5D88X`. Held rows get it through `ops.remap_source --source
  de_bkms` (new mapper entry; `source_url` added to the fields it may move and to the facts it never erases), as
  `remapped` versions. Dry run on production, first 400 rows: **272 versions, all of them `source_url` only**, 128
  unchanged (no BT-15 in the notice), 0 failed: about 8,600 of the 12,700 rows.
- **es_placsp `published_at` (37 %)**: not derivable from what we hold, documented in `docs/sources/es_placsp.md`:
  13,499 rows, award/formalisation/cancellation entries; the raw store keeps the mapped record, not the CODICE entry;
  the 1,076 with a dated earlier version were already re-read by `remap_source --epoch 2` (551 of the 552 stamped
  dates are after the notice's deadline, i.e. award dates, refused); `notice_date` is set on 13,466 (99.8 %) and is
  what the lists sort and label by. A real call date needs the archive replay (`placsp-backfill`).
- **pl_ezam and nl_tenderned values**: not in the stored payloads, documented (confirms WP-49 1c on fresh samples):
  6 pl_ezam board records of Dec 2025 - Oct 2026 have `htmlBody: null` and no value field (only the boolean
  `isTenderAmountBelowEU`); 2 TenderNed records (list row + `detail`) have no value field. Reading a value needs a
  per-notice document request, an owner decision (WP-49 section 1c). Nothing changed.

```bash
docker compose -f infra/docker-compose.yml run --rm worker python -m dgate.ops.remap_source --source de_bkms            # dry run, ~25 min (raw store reads)
docker compose -f infra/docker-compose.yml run --rm worker python -m dgate.ops.remap_source --source de_bkms --yes      # ~8,600 versions, ~11 MB
```

## 5. Organisations

**Cause.** `resolve_organisation` writes candidate pairs and never merges; nothing processed the `identifier` ones.

**Change.** New ops module `dgate/ops/accept_merge_candidates.py` (dry run by default, `--yes`, `--limit`). It accepts
only `match_method = 'identifier'` with stored confidence >= 0.97 (one organisation holds the number the notice
states, the notice's name is filed under the other). Refused, and left `pending`: different countries; two different
registration numbers, VAT numbers or PICs anywhere in the joined group (also through a third row); suppressed rows;
natural persons; a name saying one body acts for another (`per conto`, `pour le compte`, `repres par`, `im Auftrag`,
`w imieniu`, `on behalf` ...: the number is then the agent's; found in 2 of the first 30 hand-read pairs). Head = most
defence notices, then the PIC holder, then the lowest id. Each merge goes through `db.merge_organisations` with method
`identifier` and the candidate's confidence stored, aliases and notices re-pointed, nothing deleted; the group's
candidates are marked `merged`; the directory table is rebuilt. Public bodies split by office id are not merged
(different identifiers): BAAINBw's 67 rows carry 67 different numbers; the 61 that buy are all in the buyer family
`rule:baainbw` (migration 0055, `ops.buyer_families`), so the buyer page already shows one buyer.

**Dry run on production** (16:35 UTC): pending 164,790 by method: identifier@0.97 83,987,
identifier_name_mismatch@0.50 35,561, same_name_different_identifier@0.50 30,660, trigram (0.90-1.00) 13,162,
folded_name@0.90 1,158, identifier@0.95 203, transliteration folds 98. Of the 83,987 strong ones: **accepted 35,995 in
19,313 groups, 35,940 rows to merge**; refused: different_reg 37,801, group_different_reg 8,754, acting_for_another_body
1,157, already_one 255, different_pic 11, natural_person 10, different_vat 2, group_different_pic 2. Everything else
(80,803 of other methods) waits for review. Same folded name with different registration numbers (never merged):
16,701 groups, 49,204 rows, 1,929 of them buy defence notices and 797 of those are in a buyer family (the family rule
keys on the exact normalised name, not the fold: extending it is the next step for the remaining 1,132).

30 sampled accepted pairs read by hand (verdict = same body): secom Drobeta-Turnu Severin x2 yes; Ravensburger
Verkehrs- und Versorgungsbetrieb x2 yes; Faxe og Hylleholt/Hylleholdt Boligforening yes; Mairie/Commune de Mimizan yes;
IP Patrimonio (same NIF both) yes; Syndicat mixte des transports du PCSM / du Petit Cul de Sac Marin yes; **Bonaire
Brandstof Terminals / Bonaire Bon Transition: unsure** (same KvK 82637490, different trade names); CA Porte de l'Isere
(typo) yes; **Agenzia del Demanio - Direzione servizi / Direzione regionale Piemonte e Valle d'Aosta: same legal entity
(06340981007), two directorates** - yes by identity, shown as one buyer afterwards; Lantik yes; CC Save et Garonne yes;
Comune di Piegaro yes; Spitalul Clinic Panait Sarbu yes; ESC (consular higher education) yes; Xestur Galicia yes;
Junta de Gobierno del / Ayuntamiento de Alberic (same NIF) yes; CC Nord Est Bearn yes; Bulgarian university hospital
x2 yes; ASFINAG x2 yes; Clisson Sevre et Maine Agglo yes; DSP Dobrich (directorate / agency through the directorate,
same BULSTAT) yes; MApN UM 02192 / Academia Navala Mircea cel Batran - UM 02192 yes; Zupanijska uprava za ceste
Koprivnicko-krizevacke yes; Prefecture de region Pays de la Loire SGAR yes; Direzione di Intendenza Marina Militare
Brindisi yes; Gournay-sur-Marne yes; CPRP SNCF x2 yes; Vodovod-Kanalizacija yes; Vallee Sud - Grand Paris yes; Ferrovie
del Sud Est x2 yes. **28 yes, 1 unsure, 1 yes-but-two-offices; 0 wrong** (the earlier sample's 2 agent pairs are now
refused). Precision on this sample is at least 29/30.

```bash
docker compose -f infra/docker-compose.yml run --rm worker python -m dgate.ops.accept_merge_candidates                    # dry run, ~40 s (office report: a full scan of organisation; --no-office-splits skips it)
docker compose -f infra/docker-compose.yml run --rm worker python -m dgate.ops.accept_merge_candidates --yes --limit 500  # first, then read 20 merged rows
docker compose -f infra/docker-compose.yml run --rm worker python -m dgate.ops.accept_merge_candidates --yes              # ~35,940 merges
docker compose -f infra/docker-compose.yml run --rm worker python -m dgate.ops.buyer_families --yes
docker compose -f infra/docker-compose.yml run --rm worker python -m dgate.ops.warm_lists --yes
```

Not done: the merge chain 88258 -> 96915 -> 78656 (audit, L) is read correctly through `organisation_merged_live`
and was left; `--yes` was not run (as briefed).

## Tests

- `tests/unit/test_wp72.py` (11): the twin rule in Python and its SQL text, one country / one-row family as `=`, the
  BT-15 link (and a `javascript:` URI refused), the merge plan (head, every refusal, a group joined through a third row,
  a body acting for another).
- `tests/integration/test_wp72.py` (8): a dual-use TED twin does not lift a national copy (ted_ref and procedure id),
  twins do not qualify each other, **SQL and Python agree on all 80 signal combinations**, the linked-defence ops module
  (dry run writes nothing, `--yes` clears two, keeps one, writes no version, second run clears nothing), `/v1/calls` by
  effective status, the de_bkms re-map writes one `source_url` version and then nothing, the merge acceptance (method
  and confidence stored, conflict and weaker methods left pending, idempotent), country and buyer-family lists.
- `tests/integration/test_wp15.py`: the TED twin fixture `put_ted(defence=True)` now also sets the legal basis, i.e. a
  twin that is relevant on its own; the four inheritance tests check what they checked. Not weakened: the dual-use
  case they did not cover is the new test above.
- `tests/integration/test_topic_details.py::test_the_conditions_are_served_on_the_single_call`: its calendar topic had
  a fixed deadline of 29 September 2026, now past, so with the effective status the call is (rightly) closed and absent
  from the default open list. The topic in this one test now has a deadline in 2100; every assertion is unchanged
  (the other tests of the file, which compare the 29th with a moved date, keep the old fixture).
- Results: see the last section.

## Hostile review of the diff

Found and fixed: (1) the first merge sample had 2 wrong pairs of the "agent acting for a principal" kind: guard added
and tested; (2) `remap_marker` is not in the truncated test tables, so the remap test failed on a re-run: it clears its
markers; (3) a control character (backspace) slipped into the ACTING_FOR regex from a shell heredoc: fixed, and the
unit test now covers the pattern; (4) the notice count used for the merge head scanned all notices: counted over the
partial `is_defence` index; (5) the linked-defence dry run first reported only totals: it now says whether the row stays
relevant or defence and whether the twin is held; (6) the full integration run found the call-list test whose fixed
deadline had passed (above). 6 found, 6 fixed.

Risks: the 581 cleared rows leave the default list (265 leave the site, the TED twin stays in `scope=all`); the
35,940 merges change buyer and organisation ids for the absorbed rows (old links resolve through `merged_into` as for
the 1,483 earlier merges); the Postgres restart is a short outage.

Scratch: `/tmp/wp72` in `dgate-worker-1` was removed (checked: no such directory). Local: container `dgate-wp72` and `D:\DEFENCEGATE TESTS\wp72` (in DELETION_CANDIDATES).

## Test results

Run locally on 21 October 2026 (Windows, Python 3.11.9, Postgres 17 in Docker), on the final tree:

- `python -m ruff check .`: All checks passed.
- `python -m pytest` (unit, the default gate): exit 0, no failure.
- `DGATE_TEST_DSN=... python -m pytest -m integration`: exit 0, no failure (before the topic-details fixture fix one
  failure, described above; baseline on `integration` before any change: green).

Not checked: GitHub CI on Linux (runs after merge); the planner's choice on production itself (the indexes do not
exist there yet: EXPLAIN after step 1 d); the `--yes` runs (not run, as briefed).
