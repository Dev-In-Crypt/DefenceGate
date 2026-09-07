# dgate

Phase 1 ingestion pipeline for the EU Defence Access Portal.

Aggregates defence and dual-use procurement notices from TED and Spanish PLACSP,
classifies them, and archives every observed version.

## What is here

```
migrations/             Postgres schema, applied in order. opportunity_version is append-only.
src/sources/ted.py      TED Search API connector (anonymous, no key)
src/sources/placsp.py   Spanish PLACSP ATOM/CODICE connector
src/normalise.py        Source payloads to unified schema; personal data stripped here
src/classify.py         Four-signal defence classification
src/db.py               Archive upsert, entity resolution, run tracking
src/pipeline.py         Orchestration CLI
src/api.py              FastAPI serving layer
tests/                  28 unit tests, 21 integration checks
```

## Setup

```bash
createdb dgate
python -m dgate.migrate
pip install -r requirements.txt

export DGATE_DSN="postgresql://localhost/dgate"
export DGATE_RAW_DIR="./raw"

python -m dgate.pipeline seed-buyers        # defence buyer list, run once
python -m dgate.pipeline ted --days 2       # daily incremental
python -m dgate.pipeline placsp --live      # daily incremental
python -m dgate.pipeline placsp --backfill 2012 2025   # historical, run once

uvicorn dgate.api:app --reload
```

Suggested cron:

```
15 6 * * *  python -m dgate.pipeline ted --days 2
30 6 * * *  python -m dgate.pipeline placsp --live
```

Both windows overlap deliberately, so a missed run heals itself on the next one.

## Design decisions worth knowing before changing anything

**The archive is append-only.** `opportunity_version` is never updated or
deleted. A changed notice closes the previous row with `valid_to` and inserts a
new version listing `changed_fields`. This is the asset: TED itself removes
notices from public view after ten years, so an archive started today
eventually holds material the source no longer serves.

**Raw payloads are stored before normalisation.** If normalisation crashes on
an unexpected shape, the raw record survives and the run can be replayed after a
fix without refetching. Everything downstream is reproducible from `raw_ingest`.

**Personal data is stripped at exactly one boundary.** TED notices carry contact
names, emails and phone numbers, and award notices can name natural persons.
`strip_personal_data()` in `normalise.py` removes them before anything is
persisted or served. No downstream code has to remember to. Verified by test.

**Defence classification keeps four signals separately.** Legal basis, CPV,
buyer identity and security clearance are stored as individual booleans, not
collapsed into one verdict, because this logic needs tuning and a single boolean
cannot be tuned. Dual-use CPV alone never qualifies, or the feed fills with
generic IT contracts. Municipal fire extinguisher purchases in CPV 35110000 are
excluded, and there is a test that says so.

**Entity resolution stops at exact matching in Phase 1.** Alias lookup, then
exact normalised name. Fuzzy, embedding and LLM stages belong behind the same
interface later, once there is a labelled set to measure precision against. A
poisoned alias table is worse than none, and merges are hard to unpick.

**Ingest runs have coverage floors.** A run that finishes below its floor is
marked `partial`, not `success`, and `/v1/health` reports degraded. Silent
under-collection is the failure that quietly destroys a coverage promise, so it
must not look like a green tick.

## Verification status

Run on 7 September 2026 in a container without network access to europa.eu.

**Passing**
- 28 unit tests: classification, normalisation, personal data stripping, name
  canonicalisation, hash stability, query construction
- 21 integration checks against a real Postgres 16: version creation, no-op on
  unchanged input, `changed_fields` accuracy, `valid_to` closure, serving-row
  currency, personal data absence in both serving rows and archive payloads,
  buyer resolution, alias creation, coverage floor behaviour
- PLACSP CODICE parser against a realistic ATOM fixture including a malformed
  entry, which is skipped rather than killing the batch
- All five API endpoints exercised in-process

**Not yet exercised, and why**

Live calls to `api.ted.europa.eu` and `contrataciondelsectorpublico.gob.es` were
not possible: the build container's egress allowlist does not include
europa.eu or gob.es. Everything is tested against fixtures shaped like the real
payloads.

**First thing to do on your machine**, in this order:

1. `python -m dgate.pipeline ted --days 7` and read the raw JSON in `./raw/ted/`
   before trusting any parsed output.
2. Compare 20 parsed records field by field against their TED notice pages. The
   field names in `TED_FIELDS` come from the official field list, but response
   nesting is the part fixtures cannot fully predict.
3. Confirm the response envelope key. The connector accepts `notices` or
   `results`; if the API uses something else, that is a one-line fix in
   `ted.search()`.
4. Check `defence_query()` against the TED expert query syntax. If the
   `classification-cpv=35*` wildcard is not supported, drop that clause and
   filter downstream in `classify.py`, which already handles it correctly.

## What is deliberately not here

- LLM enrichment (translation, summarisation, capability tagging). The
  `enrichment` table and its cache-by-content-hash design exist in the schema;
  the worker does not. Add it after the ingestion is proven, not before.
- Consortium and EDF data. That is Phase 2, and it is PDF parsing rather than
  API work: EDF project data is not in CORDIS.
- The requirements and readiness layer. Phase 3.
- Auth, rate limiting, billing. Nothing here is exposed to the public yet.

## Bug found during testing

`buyer_org_id` was resolved but never persisted, so every API response returned
a null buyer organisation while the resolution was silently discarded. Caught by
the integration test, fixed, re-verified. Noted here because it is the kind of
failure that looks fine in logs and is invisible until someone queries by buyer.
