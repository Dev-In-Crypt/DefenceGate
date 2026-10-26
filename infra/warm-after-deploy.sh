#!/bin/sh
# Warm the site after a deploy (WP-143). Run from the repository root, on the server, as the last step of the deploy order
# (after `web` is healthy). At the r13 deploy of 26 October 2026 a crawler's burst met a web process with an empty fetch
# cache and a just-started API: every page went to the API at once and 105 visitors' pages were 503. This asks for the pages
# most visitors and crawlers open first, one at a time, so their API answers and the site's fetch cache are filled before the
# burst, by one client instead of fifty. Read-only GETs of our own public pages.
#
#   sh infra/warm-after-deploy.sh            prints status and seconds per page; exit 1 if any answered 5xx
set -u

DOMAIN=$(sed -n 's/^DGATE_DOMAIN=//p' infra/.env | tail -n 1)
BASE="https://${DOMAIN:-localhost}"
fail=0
for path in / /tenders "/tenders?status=closed" "/tenders?status=all" /funding /buyers /suppliers /organisations /networks \
            /changes /digest /market /calendar /data /changes.atom /digest.atom /funding.atom /calendar.ics /sitemap.xml; do
    out=$(curl -s -o /dev/null -A 'DefenceGate-warm/1.0' -w '%{http_code} %{time_total}' --max-time 60 "${BASE}${path}")
    echo "warm: ${out} ${path}"
    case "$out" in 5*) fail=1 ;; esac
done
exit $fail
