# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

DefenceGate aggregates defence and dual-use procurement notices from European sources, normalises them into one schema, and versions every observed change into an append-only archive. See `README.md` for the product summary and the design rules.

Current state: Phase 1. Ingestion, classification, archive and read API implemented in `backend/`. No frontend yet. Connectors are tested against fixtures, not yet against live endpoints.

## Commands

The virtualenv is `.venv/` at the repository root. Use the explicit interpreter path rather than a bare `python`.

```bash
uv pip install --python .venv/Scripts/python.exe -e "backend[dev]"

bash scripts/check.sh gate          # unit tests, the gate; must exit 0
bash scripts/check.sh lint          # ruff; keep it clean
bash scripts/check.sh types         # mypy; informational, findings in the database layer
bash scripts/check.sh integration   # needs DGATE_TEST_DSN pointing at a Postgres
bash scripts/check.sh compose       # docker compose config validation

# one test
cd backend && ../.venv/Scripts/python.exe -m pytest tests/unit/test_pipeline.py::test_fire_extinguishers_are_not_defence
```

Integration tests carry the `integration` marker, are deselected by default, and skip themselves when `DGATE_TEST_DSN` is unset, so they never point at a real database by accident. Do not weaken the marker or `addopts` to make a run green.

Pipeline and API need `DGATE_DSN` pointing at a migrated Postgres:

```bash
cd backend
../.venv/Scripts/python.exe -m dgate.migrate            # apply migrations/*.sql
../.venv/Scripts/python.exe -m dgate.pipeline seed-buyers
../.venv/Scripts/python.exe -m dgate.pipeline ted --days 2
../.venv/Scripts/python.exe -m dgate.pipeline placsp --live
../.venv/Scripts/python.exe -m dgate.worker --list      # scheduled jobs
../.venv/Scripts/python.exe -m uvicorn dgate.api:app --reload
```

## Architecture

One ordering is enforced everywhere: **land the raw payload, normalise, classify, archive.** If normalisation breaks on an unexpected shape, the raw record survives and the run is replayable without refetching.

- `dgate/sources/ted.py`, `dgate/sources/placsp.py`: connectors. They fetch and yield payloads as the source returns them, and do nothing else. TED is an anonymous JSON search API. PLACSP is ATOM feeds wrapping CODICE XML, where the same tender reappears once per modification: that is the version history, not duplication. PLACSP has two datasets, and the second one carries the regional buyers.
- `dgate/normalise.py`: maps payloads onto the `Opportunity` dataclass, which mirrors the `opportunity` table. `strip_personal_data()` is the single boundary where contact data is removed. `normalise_org_name()` is the canonical form used by entity resolution. Deadlines are timezone-aware: the offset stated by the source wins, otherwise the source's national timezone applies.
- `dgate/classify.py`: four defence signals as separate booleans. Strong signals stand alone, weak ones need a partner, dual-use CPV alone never qualifies. A municipality buying fire extinguishers under CPV 35110000 must not reach the feed, and there is a test that says so.
- `dgate/db.py`: `upsert_opportunity()` turns a feed into an archive. An unchanged hash means no new version; a changed versioned field closes the previous row with `valid_to` and inserts a new one listing `changed_fields`.
- `dgate/rawstore.py`: filesystem or S3-compatible storage, one key shape either way. Raw payloads still contain personal data, so this store is private and never served.
- `dgate/migrate.py`, `migrations/*.sql`: plain SQL in order, recorded in `schema_migrations`. `0001` carries the trigger that makes the append-only archive a database rule rather than a convention.
- `dgate/worker.py`: scheduled jobs. `run_job()` treats a run that finished below its coverage floor as `partial` and alerts on it. A job that finished is not automatically a success.
- `dgate/config.py`: every setting, read lazily. No module reads `os.environ` directly.
- `dgate/api.py`: FastAPI. `/v1/opportunities/{id}/versions` serves the archive; `/v1/health` reports coverage, including sources that have never run or have gone stale.

## Rules

- Commercial market intelligence only. Never add fields, summaries or extractions describing technical specifications, performance or design of any system.
- Personal data is stripped at `strip_personal_data()` and nowhere else. Never persist or serve contact fields.
- `opportunity_version` rows are never updated except to set `valid_to`, and never deleted.
- Classification signals stay separate columns. Entity resolution never merges without a stored method and confidence.
- Do not delete, skip or weaken a test to make a run green.
- Identify the client honestly when calling public administration endpoints, rate limit conservatively, and never bulk-enumerate a registry.
