# DefenceGate

Aggregates defence and dual-use procurement notices from European sources into one normalised, English-language schema, and keeps an append-only archive of every change ever observed to every notice.

The archive is the point. TED removes notices from public view after ten years, national portals expire them sooner, and no source preserves what a notice looked like before it was amended. A record started today outlives its source, and history cannot be backfilled by anyone starting later.

Status: Phase 1. Ingestion, classification, versioned archive and a read API are implemented. Connectors are tested against fixtures shaped like real payloads; they have not yet been verified against the live endpoints.

## What it does

- **Ingests** TED notices published under Directive 2009/81/EC and Spanish PLACSP tenders, including the aggregated dataset that carries regional buyers.
- **Normalises** every source into one `opportunity` schema, so a single query works across all of them.
- **Classifies** defence relevance from four independent signals, kept as separate columns rather than collapsed into one verdict.
- **Archives** every observation as a version, recording which fields changed and when the previous version was superseded.
- **Serves** it over a REST API, including the full change timeline for any notice.

## Quick start

Requires Python 3.11+, Docker, and [uv](https://docs.astral.sh/uv/) (or pip).

```bash
uv venv .venv
uv pip install --python .venv/Scripts/python.exe -e "backend[dev]"

docker run -d --name dgate-db -e POSTGRES_USER=dgate -e POSTGRES_PASSWORD=dgate \
  -e POSTGRES_DB=dgate -p 15432:5432 postgres:16

export DGATE_DSN="postgresql://dgate:dgate@localhost:15432/dgate"
cd backend
../.venv/Scripts/python.exe -m dgate.migrate
../.venv/Scripts/python.exe -m dgate.pipeline seed-buyers
../.venv/Scripts/python.exe -m dgate.pipeline ted --days 2
../.venv/Scripts/python.exe -m uvicorn dgate.api:app --reload
```

Or run the whole stack:

```bash
cp infra/.env.example infra/.env      # set POSTGRES_PASSWORD
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d --build
curl http://localhost:8000/v1/health
```

## Checks

One command per check, so a person, CI and any automation all run the same thing:

```bash
bash scripts/check.sh gate          # unit tests
bash scripts/check.sh lint          # ruff
bash scripts/check.sh types         # mypy, informational
bash scripts/check.sh integration   # needs DGATE_TEST_DSN
bash scripts/check.sh compose       # docker compose config
```

## API

| Endpoint | Purpose |
|---|---|
| `GET /v1/opportunities` | Filter by country, CPV, deadline, value, subcontracting signal |
| `GET /v1/opportunities/{id}` | One notice |
| `GET /v1/opportunities/{id}/versions` | The archive: every observed state, with the fields that changed |
| `GET /v1/organisations/resolve` | Entity resolution as a service, with the method and confidence exposed |
| `GET /v1/health` | Coverage health, not liveness: reports `never_run` and `stale` sources |

## Design rules

These are enforced by tests and, where possible, by the database.

- **The archive is append-only.** A trigger rejects any `DELETE` on `opportunity_version` and any `UPDATE` that touches a column other than `valid_to`.
- **Raw payloads are stored before normalisation.** Everything downstream is reproducible from them, so a parser fix can be replayed over history without refetching.
- **Personal data is stripped at exactly one boundary.** Notices carry contact names, emails and phone numbers; `strip_personal_data()` removes them before anything is persisted or served, and no downstream code has to remember to.
- **Classification signals stay separate.** Legal basis, CPV, buyer identity and security clearance are individual booleans, because a single boolean cannot be tuned. Dual-use CPV alone never qualifies, or the feed fills with generic IT contracts.
- **Entity resolution never guesses silently.** Exact matching only, with the method and confidence stored on every alias and exposed in API responses.
- **Under-collection is loud.** A run that finishes below its coverage floor is recorded as `partial`, never `success`, and the health endpoint reports degraded.

## Scope

Commercial market intelligence only: who is buying, under which conditions, and what a supplier needs in order to qualify. No technical specifications, no performance characteristics, no design information. This is a hard boundary, not a preference.

## Sources and attribution

| Source | Licence |
|---|---|
| TED (Tenders Electronic Daily) | Commission Decision 2011/833/EU. Notices freely reusable, including commercially. © European Union |
| Plataforma de Contratación del Sector Público | Open public sector information, Ministerio de Hacienda, Spain |

Attribution is recorded per source in the database and returned with every API response.

## Licence

Not yet chosen.
