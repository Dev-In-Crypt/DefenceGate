#!/bin/sh
# Build the frontend and its runtime image. Run from the repository root, on the server.
#
# `next build` prerenders pages from the API, so the API must be reachable while it
# runs, and it is only reachable on the compose network. A throwaway node container on
# that network does the build (npm ci from the lockfile, nothing else is installed on
# the host); web/Dockerfile then packages the output.
#
#   DGATE_DOMAIN=example.org sh infra/build-web.sh
#
# NEXT_PUBLIC_BILLING_OPEN (WP-122, read at build time; `1` or `true` lets visitors choose a
# paid plan) comes from the environment, else from infra/.env, else empty (off). WP-126.
#
# The result is NOT started: `docker compose -f infra/docker-compose.yml --env-file
# infra/.env --profile web up -d web` does that, when the domain is live.
set -eu

: "${DGATE_DOMAIN:?set DGATE_DOMAIN to the public host name, without https://}"
NEXT_PUBLIC_BILLING_OPEN="${NEXT_PUBLIC_BILLING_OPEN-$(sed -n 's/^NEXT_PUBLIC_BILLING_OPEN=//p' infra/.env 2>/dev/null | tail -n 1)}"

docker run --rm --network dgate_default \
    -v "$PWD/web:/app" -w /app \
    -e DG_API_URL=http://api:8000 \
    -e NEXT_PUBLIC_SITE_URL="https://${DGATE_DOMAIN}" \
    -e NEXT_PUBLIC_BILLING_OPEN="${NEXT_PUBLIC_BILLING_OPEN}" \
    -e NEXT_TELEMETRY_DISABLED=1 \
    node:22-alpine sh -c 'npm ci && npm run build'

docker compose -f infra/docker-compose.yml --env-file infra/.env --profile web build web
