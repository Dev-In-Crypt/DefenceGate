# WP-147 self-check: our side of Cloudflare's proxy mode (26 October 2026)

Branch `wp-wp147` from `integration` 9c4295c. Requirements: WP-143 self-check, "What Cloudflare proxy mode ... would need from
our side", points 1-6. Production was only read (ssh: `docker ps`, `docker image inspect`, `ufw status`, `nft list ruleset`,
`iptables -S`, `ss -ltnp`, certificate dates); nothing restarted, executed in a container or changed. Cloudflare was called
once, for its two published lists (https://www.cloudflare.com/ips-v4 and ips-v6, 26 Oct 2026 17:13 UTC); nothing else.

Files: `infra/caddy/Caddyfile`, `infra/cloudflare-ranges.sh` (new), `infra/origin-lock.sh` (new), `infra/warm-after-deploy.sh`,
`backend/tests/unit/test_wp147.py` (new), `docs/legal/drafts/privacy-cloudflare-draft.md` (new), `docs/DATA_PROTECTION.md`
(Logs row). No file of WP-144/145/146. Lab scripts and outputs: `D:\DEFENCEGATE TESTS\wp147\lab\` (`result-*.txt`).

## 1. Real client address

**Before.** Production runs `caddy:2` = v2.11.4 (image env `CADDY_VERSION`). Caddy sends `X-Forwarded-For: <peer>`; the site
reads the first entry (web/lib/account.ts, api-proxy.ts, hits.ts, middleware.ts), the API the last one not trusted (uvicorn
`--proxy-headers`, trusted 10.250.71.2 only). Lab with the integration Caddyfile, a peer inside 173.245.48.0/20 standing in for
Cloudflare and sending `CF-Connecting-IP: 203.0.113.5`: the API and the site both get `173.245.48.10` (Cloudflare's address for
every visitor), the access log `client_ip=173.245.48.10` (`result-before.txt`).

**Change.** Global `servers { trusted_proxies static <15 IPv4 + 7 IPv6 Cloudflare ranges> ; client_ip_headers CF-Connecting-IP }`
and, in both `reverse_proxy` blocks, `header_up X-Forwarded-For {client_ip}`. The second line is needed: with only
`trusted_proxies`, Caddy appends the peer to the list Cloudflare sent, which starts with whatever the visitor put there; lab
result `"xff": "7.7.7.7, 203.0.113.5, 173.245.48.10"`: the site would read 7.7.7.7 (forged), the API 173.245.48.10
(`result-trusted-only.txt`). One list of ranges, on one line of the Caddyfile with its fetch date; `origin-lock.sh` reads it.
`infra/cloudflare-ranges.sh` fetches both lists, refuses anything that is not a list of ranges (or fewer than 5/3), prints
`+`/`-` per range and writes the line and the date only with `--yes`.

**After (lab, caddy:2.11.4, `result-after.txt`).**

| case | API sees X-Forwarded-For | site sees | access log remote_ip / client_ip |
|---|---|---|---|
| proxy OFF, direct visitor 192.0.2.10 | 192.0.2.10 | 192.0.2.10 | 192.0.2.10 / 192.0.2.10 |
| proxy OFF, direct visitor forging `CF-Connecting-IP: 6.6.6.6`, `X-Forwarded-For: 7.7.7.7` | 192.0.2.10 | 192.0.2.10 | 192.0.2.10 / 192.0.2.10 |
| proxy ON, Cloudflare 173.245.48.10 for visitor 203.0.113.5 who sent `X-Forwarded-For: 7.7.7.7` | 203.0.113.5 | 203.0.113.5 | 173.245.48.10 / 203.0.113.5 |

So the per-address rate limit (API, via the site's forwarded address too), the access log, the visit counter and the web's
render gate keep seeing visitors, and the change is a no-op while the proxy is off. A forged `CF-Connecting-IP` from a direct
client is passed on unchanged but nothing reads it (no use in backend/ or web/).

**Tests.** `test_the_client_address_is_cloudflares_header_only_from_cloudflares_ranges`,
`test_both_upstreams_get_the_resolved_address_alone`, `test_ranges_script_prints_the_change_and_writes_only_with_yes`
(a list without a final newline, as Cloudflare sends it: the first run of this test found the last IPv4 and first IPv6 range
glued together, fixed), `test_ranges_script_refuses_an_answer_that_is_not_a_list`. WP-127's test of both upstreams still passes.

## 2. Origin lock, prepared NOT applied

**Before (server, read-only).** ufw active, default deny incoming / deny routed, 22/80/443 allowed from anywhere (v4 and v6);
iptables 1.8.10 (nf_tables); Docker 29.1.3. IPv4 80/443 are Docker DNAT (`-A DOCKER ! -i br-... --dport 443 -j DNAT
--to-destination 172.18.0.6:443`), so those packets go `FORWARD -> DOCKER-USER (empty) -> DOCKER-FORWARD`, before any ufw chain:
a ufw "allow from Cloudflare" rule would not stop anything (ufw's INPUT 80/443 rules had counted 1 and 72 packets). IPv6: no
Docker NAT, docker-proxy listens on `[::]:80/443` (through ufw's INPUT); 0 packets on the v6 rules; the domain has no AAAA
record (nslookup). Default interface `eth0`; `MANAGE_BUILTINS=no` (ufw reload does not flush Docker's chains).

**Change.** `infra/origin-lock.sh`: dry run by default (prints the block and the commands). `--yes`: checks first that
`https://<domain>/` and `https://www.<domain>/` answer with a `cf-ray` header, that the running Caddy has
`client_ip_headers CF-Connecting-IP`, and that `iptables-restore --test` accepts the block; then writes a marked block into
`/etc/ufw/after.rules` (`*filter`, `:DOCKER-USER`, one `-i eth0 -p tcp --dports 80,443 -s <range> -j RETURN` per Cloudflare
IPv4 range, then `DROP`), keeps a copy `after.rules.before-origin-lock`, removes `ufw allow 80/tcp` and `443/tcp` (closes IPv6
80/443), `ufw reload`, and verifies the RETURN count and FORWARD's jump. A re-run replaces the block (after new ranges).
`--undo [--yes]`: removes the block, `iptables -F DOCKER-USER`, `ufw allow 80/tcp`, `ufw allow 443/tcp`, `ufw reload`: exactly
the state of today. SSH is never touched; the server's own requests (not on eth0) are not matched.

**Lab (`result-firewall.txt`).** Privileged ubuntu:24.04 with real ufw and iptables 1.8.10 (nf_tables), 80/443 DNAT to a
namespace and `FORWARD -> DOCKER-USER -> DOCKER-FORWARD` as on the server; clients 173.245.48.10 (Cloudflare range) and
173.245.1.10 (not): before 200/200; dry run 200/200, nothing changed; `--yes` 200/timeout, ufw shows 22 only; second `--yes`
one block; `ufw reload` keeps 15 RETURN rules and 200/timeout; `--undo --yes` 200/200, ufw back to 22/80/443 v4+v6, DOCKER-USER
empty. Not tested: a reboot (ufw loads after.rules before Docker starts; Docker leaves DOCKER-USER alone, the usual ufw+Docker
arrangement).

**Tests.** `test_origin_lock_changes_nothing_without_yes`, `test_origin_lock_refuses_while_the_site_is_not_behind_cloudflare`,
`test_origin_lock_applies_once_and_undoes` (fake ufw/iptables/curl/docker on PATH).

Also: `infra/warm-after-deploy.sh` now goes to `127.0.0.1` (`--resolve`), so it fills the origin's caches and is not met by the
bot rule's challenge on `/organisations` (`test_the_warm_up_goes_to_this_server_not_through_cloudflare`).

## 3. TLS

**Before.** Certificates for `defencegatehub.com` and `www.` from Let's Encrypt (YE1/YE2), issued 12 Oct 2026, valid until
10 Jan 2027; Caddy renews at about a third of the lifetime left (around 11 Dec 2026). Default issuer without an email: Let's
Encrypt only, challenges HTTP-01 and TLS-ALPN-01.

**Behind Cloudflare.** TLS-ALPN-01 cannot work (Cloudflare ends TLS; the `acme-tls/1` handshake never reaches us). HTTP-01
works as long as Cloudflare passes port 80 to port 80, which it does in Full (strict) for an `http://` request when "Always Use
HTTPS" is off. Lab with Let's Encrypt's test CA (pebble) and a front proxy that ends TLS itself and passes port 80
(`result-acme-default.txt`, `result-acme-http01.txt`): with the default challenges Caddy tried TLS-ALPN-01 first for `www`,
it failed ("Failed to connect to 173.245.48.10:443 for the tls-alpn-01 challenge"), then HTTP-01 succeeded; with the change
only HTTP-01 is tried and both certificates are obtained through the front. So renewal would not have broken, but each
renewal could cost a failed validation.

**Change (smallest).** Global `cert_issuer acme { disable_tlsalpn_challenge }`: same CA (Let's Encrypt), same storage
(`acme-v02.api.letsencrypt.org-directory`), so the stored certificates are kept; `localhost` still gets Caddy's internal
certificate (lab). Test: `test_lets_encrypt_is_asked_for_http_01_only`. Full (strict) needs nothing else from us: the origin
already has a publicly trusted certificate for both names, and renewals keep it so. Conditions: `www` proxied too; "Always Use
HTTPS" off (Caddy itself redirects http to https and sends HSTS); the origin lock lets Cloudflare reach port 80 (it does).

## 4. Owner steps in the Cloudflare panel (click by click)

Names as in the Cloudflare dashboard of October 2026; the newer dashboard groups some under "Security > Settings".
Do them in this order, after steps A and B of the switching order below.

1. **SSL/TLS > Overview > Configure** (encryption mode): choose **Custom SSL/TLS > Full (strict)** > Save. First, before
   any record is proxied: with "Flexible" Cloudflare talks plain http to us and Caddy's redirect to https loops.
2. **SSL/TLS > Edge Certificates**: **Always Use HTTPS: Off** (Caddy redirects; keeps Let's Encrypt's HTTP-01 on the path
   tested). **HTTP Strict Transport Security (HSTS): leave off** (our server sends it). **Minimum TLS Version: TLS 1.2**.
   **Automatic HTTPS Rewrites: Off** (it rewrites links in our HTML; a page that differs from what React renders fails to
   hydrate, WP-63).
3. **Scrape Shield** (newer dashboard: Security > Settings) > **Email Address Obfuscation: Off** (it rewrites e-mail
   addresses in our HTML, same hydration problem). **Speed > Optimization > Content Optimization > Rocket Loader: Off**.
4. **Caching > Configuration**: Caching Level **Standard**; Browser Cache TTL **Respect Existing Headers**. Do not create a
   "Cache Everything" / "Eligible for cache" rule for pages. Defaults already keep HTML out of the edge cache (HTML is not a
   cached file type) and feeds, calendars and sitemaps (`.atom`, `.ics`, `.xml`) too, so their weak ETags and 304s are
   answered by us as now. CSV exports are a cached type: Cloudflare keeps them for the 300 s our `Cache-Control: public,
   max-age=300` allows, with the ETag; they do not depend on the session.
5. **Caching > Cache Rules > Create rule**: Rule name `No cache for signed-in visitors`; "Custom filter expression";
   Field **Cookie**, Operator **contains**, Value `__Host-dg_session`; Then: **Cache eligibility: Bypass cache** > Deploy.
6. **Security > WAF > Custom rules > Create rule**: Rule name `Challenge cookieless deep pages`; **Edit expression**:
   `(starts_with(http.request.uri.path, "/tenders/") or starts_with(http.request.uri.path, "/organisations") or starts_with(http.request.uri.path, "/projects/")) and not ends_with(http.request.uri.path, ".csv") and http.cookie eq "" and not cf.client.bot`
   Choose action **Managed Challenge** > Deploy. (`cf.client.bot` is "Known Bots": verified search engines pass; the CSV
   export under `/tenders/` is machine-read and is not challenged; `/v1/*`, feeds, the webhook and the home page are not in it.)
7. **Security > Bots** (newer dashboard: Security > Settings > Bot traffic): **Bot Fight Mode: On**. Caveat: on the free plan
   Bot Fight Mode cannot be skipped by a rule; it may challenge API clients of `/v1/*`, feed readers, calendar subscriptions
   and webhooks (Creem, when billing opens). Look at **Security > Events** on the first day; if such clients are challenged,
   switch Bot Fight Mode off and keep rule 6.
8. **DNS > Records**: the `A` record `defencegatehub.com -> 2.29.42.177`: Edit > **Proxy status: Proxied** > Save; the `www`
   `CNAME`: **Proxied** too (otherwise `www` stops working once the origin lock is on, and its certificate cannot renew). Do
   **not** add an `AAAA` record for the server (over IPv6 our proxy would see one bridge address for every visitor).

## 5. Privacy

Draft `docs/legal/drafts/privacy-cloudflare-draft.md`: what Cloudflare sees (IP address, request with full address, headers,
our answer, derived country), where (nearest data centre, also the US), why (protection against automated floods, delivery),
its cookies `__cf_bm` and `cf_clearance` (they make 1.7's "sets no cookie" untrue once Bot Fight Mode is on), and the exact
sentence changes for privacy sections "In short", 2, 4, 8 and the two /data/sovereignty rows. Live texts unchanged.
`docs/DATA_PROTECTION.md` Logs row notes what the log holds once the proxy is on.

## Switching order

A. **Our deploy** of this branch (Caddyfile via `sh infra/caddy-reload.sh`; a no-op for direct visitors, lab item 1). Check:
   in `access.log`, `client_ip == remote_ip` for every line.
B. **Owner approves the privacy/sovereignty wording**; it is published (privacy 1.8, sovereignty page) and deployed.
C. **Proxy on**: owner steps 1-8. Check: `curl -sI https://defencegatehub.com/` shows `server: cloudflare` and `cf-ray`;
   `access.log` lines with `remote_ip` in Cloudflare's ranges and `client_ip` varied; no rise of 429s; `www` redirects.
D. **Origin lock** by the orchestrator: `sh infra/origin-lock.sh` (read the dry run), then `sh infra/origin-lock.sh --yes`.
   Check from outside: `curl --resolve defencegatehub.com:443:2.29.42.177 https://defencegatehub.com/` times out; the site
   answers through Cloudflare; ssh works.
Rollback: `sh infra/origin-lock.sh --undo --yes` **first**, then DNS records back to "DNS only".

## Suite

In `D:\DEFENCEGATE TESTS\wp147`: ruff clean; unit 4090 passed (9 new); integration 1562 passed, 1 failed:
`test_wp110.py::test_the_global_search_answers_every_part_at_once_within_the_budget` (a 2 s timing budget, "slow" on the shared
machine during the 19-minute run; no backend code is changed here), which passed on its own re-run (test_wp110.py 5 passed).
`caddy validate` of the Caddyfile with `DGATE_DOMAIN=defencegatehub.com` and caddy:2.11.4: valid.

## Open items

- Lawyer/owner: Cloudflare's data processing addendum and the transfer basis (draft, "Role and transfer").
- Bot Fight Mode versus API clients, feed readers and webhooks (step 7): owner's watch on day one.
- Range refresh is manual (`sh infra/cloudflare-ranges.sh`, monthly is plenty); then deploy and re-run the lock.
- A Hetzner Cloud Firewall (outside the server) was not looked at; if one exists it needs the same change or none.
- Not tested: a reboot with the lock on; Caddy answering HTTP-01 over its HTTPS port (only relevant if "Always Use HTTPS"
  were turned on).
