#!/usr/bin/env bash
# One entry point for every machine check in this repository.
#
# Why this exists: one spelling of each check, so that a person, a CI job and an
# automated agent all run exactly the same command and report the same result.
# Ad-hoc shell variations drift apart and then argue about what "passing" means.
#
#   bash scripts/check.sh gate          unit tests, the gate
#   bash scripts/check.sh lint          ruff
#   bash scripts/check.sh types         mypy (informational)
#   bash scripts/check.sh integration   integration tests (needs DGATE_TEST_DSN)
#   bash scripts/check.sh unit-dir      unit tests addressed by directory
#   bash scripts/check.sh compose       docker compose config validation
#   bash scripts/check.sh all           gate + lint
#
# Always prints a final line "EXIT=<code>" and exits with that code, so a
# caller never has to guess how the check went.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 90
PY="../.venv/Scripts/python.exe"

run() {
  echo "\$ $*"
  "$@" 2>&1
  return $?
}

case "${1:-}" in
  gate)
    (cd backend && run $PY -m pytest)
    code=$?
    ;;
  lint)
    (cd backend && run $PY -m ruff check .)
    code=$?
    ;;
  types)
    (cd backend && run $PY -m mypy dgate)
    code=$?
    ;;
  integration)
    if [ -z "${DGATE_TEST_DSN:-}" ]; then
      echo "DGATE_TEST_DSN is not set; start Postgres and export it. Not a pass."
      code=91
    else
      (cd backend && run $PY -m pytest -m integration)
      code=$?
    fi
    ;;
  unit-dir)
    # Unit tests addressed by directory rather than by pytest configuration.
    run .venv/Scripts/python.exe -m pytest backend/tests/unit
    code=$?
    ;;
  compose)
    POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-check-only}" \
      run docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml config --quiet
    code=$?
    ;;
  all)
    bash "$0" gate; a=$?
    bash "$0" lint; b=$?
    code=$(( a != 0 ? a : b ))
    ;;
  *)
    echo "usage: bash scripts/check.sh {gate|lint|types|integration|unit-dir|compose|all}"
    code=64
    ;;
esac

echo "EXIT=$code"
exit $code
