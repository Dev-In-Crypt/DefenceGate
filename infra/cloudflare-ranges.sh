#!/bin/sh
# Refresh Cloudflare's published address ranges in infra/caddy/Caddyfile (WP-147). Run from the repository root.
#
#   sh infra/cloudflare-ranges.sh          fetch, print what changed, write nothing
#   sh infra/cloudflare-ranges.sh --yes    also rewrite the `trusted_proxies static` line and its date in the Caddyfile
#
# It calls https://www.cloudflare.com/ips-v4 and https://www.cloudflare.com/ips-v6 and nothing else. The ranges change
# rarely; a change is a normal commit, then the deploy's `sh infra/caddy-reload.sh`, and, once the origin lock is in force,
# `sh infra/origin-lock.sh --yes` again so the firewall allows the same ranges Caddy trusts.
set -eu

CADDYFILE=${CADDYFILE:-infra/caddy/Caddyfile}
BASE=${CF_IPS_BASE:-https://www.cloudflare.com}
YES=
[ "${1:-}" = --yes ] && YES=1

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

{ curl -fsS --max-time 20 "$BASE/ips-v4"; echo; } | tr -d '\r' | sed '/^$/d' > "$tmp/v4"
{ curl -fsS --max-time 20 "$BASE/ips-v6"; echo; } | tr -d '\r' | sed '/^$/d' > "$tmp/v6"

# Every line a range of its family, and a plausible count: an error page or a cut answer stops here, nothing is written.
if grep -qvE '^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$' "$tmp/v4" || grep -qvE '^[0-9a-fA-F:]+/[0-9]{1,3}$' "$tmp/v6" \
   || [ "$(wc -l < "$tmp/v4")" -lt 5 ] || [ "$(wc -l < "$tmp/v6")" -lt 3 ]; then
    echo "cloudflare-ranges: FAILED, the answer is not a list of ranges; nothing written" >&2
    exit 1
fi

new=$(cat "$tmp/v4" "$tmp/v6" | tr '\n' ' ' | sed 's/ $//')
grep -m1 'trusted_proxies static ' "$CADDYFILE" | sed 's/.*trusted_proxies static //' | tr ' ' '\n' | sed '/^$/d' | sort > "$tmp/old"
printf '%s\n' $new | sort > "$tmp/newsorted"

if cmp -s "$tmp/old" "$tmp/newsorted"; then
    echo "cloudflare-ranges: unchanged ($(wc -l < "$tmp/newsorted") ranges)"
    exit 0
fi
echo "cloudflare-ranges: changed"
comm -13 "$tmp/old" "$tmp/newsorted" | sed 's/^/  + /'
comm -23 "$tmp/old" "$tmp/newsorted" | sed 's/^/  - /'

if [ -z "$YES" ]; then
    echo "cloudflare-ranges: dry run, nothing written (--yes writes $CADDYFILE)"
    exit 0
fi
today=$(date -u +%Y-%m-%d)
sed -i -e "s#^\([[:space:]]*trusted_proxies static \).*#\1$new#" \
       -e "s#cloudflare-ranges fetched [0-9-]*#cloudflare-ranges fetched $today#" "$CADDYFILE"
echo "cloudflare-ranges: written to $CADDYFILE; commit it, deploy (sh infra/caddy-reload.sh), and if the origin lock is on:" \
     "sh infra/origin-lock.sh --yes"
