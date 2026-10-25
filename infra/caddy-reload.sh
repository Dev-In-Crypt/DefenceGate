#!/bin/sh
# Load infra/caddy/Caddyfile into the running proxy, or stop with an error. Run from the repository root, on the server,
# after the checkout and before api and web are replaced (deploy order, step 2, in infra/docker-compose.yml).
#
#   sh infra/caddy-reload.sh               reload in place, connections kept (every deploy)
#   RECREATE=1 sh infra/caddy-reload.sh    recreate the container instead (once, for WP-136's directory mount)
#
# WP-136: up to 25 Oct 2026 the file was bind-mounted on its own, git replaced it with a new one, and the container kept
# reading the version of 21 Oct: every reload said "config is unchanged" and WP-127's hold never ran (10 x 502 at r10).
set -eu

C="docker compose -f infra/docker-compose.yml --env-file infra/.env"
DOMAIN=$(sed -n 's/^DGATE_DOMAIN=//p' infra/.env | tail -n 1)
IMAGE=$(docker inspect -f '{{.Config.Image}}' dgate-caddy-1)

# 1. The checked-out file, validated by the proxy's own image before the running proxy is touched.
docker run --rm --network none -e DGATE_DOMAIN="${DOMAIN:-localhost}" -v "$PWD/infra/caddy:/etc/caddy:ro" "$IMAGE" \
    caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

# 2. Load it.
if [ "${RECREATE:-}" = 1 ]; then
    $C up -d --no-build --no-deps --force-recreate caddy
else
    docker exec dgate-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
fi

# 3. The proxy reads the file that was checked out.
host=$(sha256sum infra/caddy/Caddyfile | cut -d' ' -f1)
seen=$(docker exec dgate-caddy-1 sha256sum /etc/caddy/Caddyfile | cut -d' ' -f1)
if [ "$host" != "$seen" ]; then
    echo "caddy-reload: FAILED, the proxy reads another Caddyfile (host $host, container $seen)" >&2
    exit 1
fi
echo "caddy-reload: ok, the proxy runs infra/caddy/Caddyfile $host"
