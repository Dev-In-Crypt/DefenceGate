#!/bin/sh
# WP-147: the web ports 80/443 open to Cloudflare's ranges only, so traffic cannot go around the proxy to the server's own
# address. PREPARED, NOT APPLIED: run it only once the proxy is on and the site answers through Cloudflare (with --yes the
# script checks both names for Cloudflare's `cf-ray` header and the running Caddy for CF-Connecting-IP, and stops otherwise).
# As root on the server, from the repository root (/opt/dgate). SSH (22) is never touched.
#
#   sh infra/origin-lock.sh                 dry run (default): print the rules and commands, change nothing
#   sh infra/origin-lock.sh --yes           apply; run again after infra/cloudflare-ranges.sh changed the ranges
#   sh infra/origin-lock.sh --undo          dry run of the undo
#   sh infra/origin-lock.sh --undo --yes    undo: 80/443 open to anyone again, exactly as before
#
# Where the rules go (the firewall as read on the server on 26 Oct 2026, read-only): ufw is active, default deny incoming,
# 22/80/443 allowed from anywhere for IPv4 and IPv6, iptables 1.8.10 (nf_tables), Docker 29.
#   IPv4: Docker publishes 80/443 by DNAT to the caddy container, so those packets go through FORWARD, where Docker jumps to
#     DOCKER-USER before any ufw chain: a ufw "allow from" rule would not stop them (its INPUT rules saw 1 and 72 packets
#     against hundreds of thousands served). The lock is a DOCKER-USER block in /etc/ufw/after.rules: ufw loads it at boot and
#     on reload, and Docker never changes DOCKER-USER. Only packets arriving on the outside interface are matched, so the
#     server's own requests (infra/warm-after-deploy.sh goes to 127.0.0.1) and the containers' traffic are not.
#   IPv6: no Docker NAT; docker-proxy listens on [::]:80/443 and the packets meet ufw's INPUT. The site has no AAAA record
#     (0 packets on the v6 rules) and Cloudflare reaches the origin over IPv4, so the "80/443 from anywhere" rules are
#     removed. (Over IPv6 every visitor would look like the bridge address 172.18.0.1: do not add an AAAA record.)
set -eu

CADDYFILE=${CADDYFILE:-infra/caddy/Caddyfile}
UFW_DIR=${UFW_DIR:-/etc/ufw}
AFTER="$UFW_DIR/after.rules"
BEGIN="# BEGIN dgate-origin-lock"
END="# END dgate-origin-lock"
YES=
UNDO=
for a in "$@"; do
    case $a in
        --yes) YES=1 ;;
        --undo) UNDO=1 ;;
        --dry-run) ;;
        *) echo "usage: sh infra/origin-lock.sh [--undo] [--yes]" >&2; exit 2 ;;
    esac
done

fail() { echo "origin-lock: FAILED, $*" >&2; exit 1; }
run() { if [ -n "$YES" ]; then echo "+ $*"; "$@"; else echo "would run: $*"; fi; }
without_block() { awk -v b="$BEGIN" -v e="$END" '$0 == b {skip = 1} !skip {print} $0 == e {skip = 0}' "$AFTER"; }

[ -f "$AFTER" ] || fail "$AFTER not found (is ufw installed?)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

if [ -n "$UNDO" ]; then
    without_block > "$tmp/after.rules"
    if [ -n "$YES" ]; then cat "$tmp/after.rules" > "$AFTER"; echo "+ removed the origin-lock block from $AFTER"
    else echo "would remove the origin-lock block from $AFTER"; fi
    run iptables -F DOCKER-USER          # live: ufw reload no longer declares the chain, so it would keep the old rules
    run ufw allow 80/tcp
    run ufw allow 443/tcp
    run ufw reload
    [ -n "$YES" ] && echo "origin-lock: undone, 80/443 open to anyone (IPv4 and IPv6) as before"
    exit 0
fi

# The ranges are the ones Caddy trusts for CF-Connecting-IP: one list, refreshed by infra/cloudflare-ranges.sh.
v4=$(grep -m1 'trusted_proxies static ' "$CADDYFILE" | sed 's/.*trusted_proxies static //' | tr ' ' '\n' \
     | grep -E '^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$' || true)
[ "$(printf '%s\n' "$v4" | grep -c .)" -ge 5 ] || fail "fewer than 5 IPv4 ranges on the trusted_proxies line of $CADDYFILE"
IF=${WAN_IF:-$(ip -4 route show default | awk '{print $5; exit}')}
[ -n "$IF" ] || fail "no default route interface"

{
    echo "$BEGIN"
    echo "# WP-147, written by infra/origin-lock.sh: IPv4 80/443 on $IF from Cloudflare's ranges only (Docker's DNAT path)."
    echo "*filter"
    echo ":DOCKER-USER - [0:0]"
    for r in $v4; do echo "-A DOCKER-USER -i $IF -p tcp -m multiport --dports 80,443 -s $r -j RETURN"; done
    echo "-A DOCKER-USER -i $IF -p tcp -m multiport --dports 80,443 -j DROP"
    echo "COMMIT"
    echo "$END"
} > "$tmp/block"
{ without_block; cat "$tmp/block"; } > "$tmp/after.rules"

if [ -z "$YES" ]; then
    echo "origin-lock: dry run, nothing changed. Would write to $AFTER:"
    cat "$tmp/block"
    echo "would run: ufw delete allow 80/tcp; ufw delete allow 443/tcp   (IPv6 80/443 closed; IPv4 is the block above)"
    echo "would run: ufw reload"
    exit 0
fi

# Only behind the proxy: locking a site that is still reached directly takes it off the net.
DOMAIN=${DGATE_DOMAIN:-$(sed -n 's/^DGATE_DOMAIN=//p' infra/.env | tail -n 1)}
[ -n "$DOMAIN" ] || fail "DGATE_DOMAIN not found in infra/.env"
for host in "$DOMAIN" "www.$DOMAIN"; do
    curl -sS -o /dev/null -D "$tmp/h" --max-time 20 "https://$host/" || fail "https://$host/ did not answer"
    grep -qi '^cf-ray:' "$tmp/h" || fail "https://$host/ is not answered through Cloudflare (no cf-ray header): proxy it first"
done
docker exec dgate-caddy-1 grep -q '^[[:space:]]*client_ip_headers CF-Connecting-IP' /etc/caddy/Caddyfile \
    || fail "the running Caddy does not take CF-Connecting-IP: deploy the Caddyfile first (sh infra/caddy-reload.sh)"
iptables-restore --test --noflush < "$tmp/block" || fail "iptables-restore rejects the block; nothing changed"

[ -f "$AFTER.before-origin-lock" ] || cp "$AFTER" "$AFTER.before-origin-lock"
cat "$tmp/after.rules" > "$AFTER"
echo "+ wrote the origin-lock block to $AFTER ($(printf '%s\n' "$v4" | grep -c .) IPv4 ranges)"
echo "+ ufw delete allow 80/tcp; ufw delete allow 443/tcp"
ufw delete allow 80/tcp >/dev/null 2>&1 || true     # absent on a re-run: fine
ufw delete allow 443/tcp >/dev/null 2>&1 || true
run ufw reload

n=$(iptables -S DOCKER-USER | grep -c -- '-j RETURN' || true)
[ "$n" -eq "$(printf '%s\n' "$v4" | grep -c .)" ] || fail "DOCKER-USER holds $n RETURN rules after the reload; undo with --undo --yes"
iptables -S FORWARD | grep -q -- '-A FORWARD -j DOCKER-USER' || fail "FORWARD does not jump to DOCKER-USER"
echo "origin-lock: on, 80/443 from Cloudflare only ($n IPv4 ranges on $IF, IPv6 80/443 closed). Undo: sh infra/origin-lock.sh --undo --yes"
