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
# The result is NOT started: `docker compose -f infra/docker-compose.yml --env-file
# infra/.env --profile web up -d web` does that, when the domain is live.
set -eu

: "${DGATE_DOMAIN:?set DGATE_DOMAIN to the public host name, without https://}"

docker run --rm --network dgate_default \
    -v "$PWD/web:/app" -w /app \
    -e DG_API_URL=http://api:8000 \
    -e NEXT_PUBLIC_SITE_URL="https://${DGATE_DOMAIN}" \
    -e NEXT_TELEMETRY_DISABLED=1 \
    node:22-alpine sh -c 'npm ci && npm run build'

docker compose -f infra/docker-compose.yml --env-file infra/.env --profile web build web
