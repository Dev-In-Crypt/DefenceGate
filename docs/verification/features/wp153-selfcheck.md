# WP-153 self-check: data API product (idea 4)

Branch `wp-wp153` from `integration` a27adb8. Test copy `D:\DEFENCEGATE TESTS\wp153\` (own Postgres `dgate-wp153` on
port 56153: 55453 is in a Windows excluded port range on this machine, 55395-55494). Screenshots in
`D:\DEFENCEGATE TESTS\wp153\shots\`.

## A. Licence check

`docs/research/DATA_LICENCES_2026-10-27.md`: 15 sources, primary sources only, robots.txt respected (five pages could
not be read and are named there; nothing was bypassed). Summary of the verdicts:

| Resale | Sources |
|---|---|
| yes | BKMS (CC0, new finding; source still inactive), TenderNed (CC0), Vinnova (CC0) |
| with conditions | TED, PLACSP, BOAMP, Atlas Przetargów, BDNS (calls only), EU portal, CORDIS, EDF factsheets, AID (contradiction), NCBR |
| unclear | e-Zamówienia, MATINE |

The key allow-list stays **TED only** (`DGATE_API_KEY_SOURCES`, default `ted`), as the brief says. The research
recommends TED, TenderNed and Vinnova now, then BOAMP, PLACSP notices and BDNS calls once each record carries the
source's last-update date (not built: the API serves `attribution` but not that date). Owner decides.

Found on the way, not changed (outside this package): the `source` rows that no longer match the reading
(`se_vinnova` licence text should be CC0; `pl_ezam` and `pl_atlas` have `commercial_ok = TRUE`, more than the reading
supports; `fr_aid` and `pl_ncbr` TRUE with an open question; PLACSP attribution lacks the ministry's wording), and
BOAMP's `robots.txt` disallowing `/api/` for generic agents on the opendatasoft host the connector reads (research
file, BOAMP section and lawyer question 7).

## B. API keys

Whole feature behind `DGATE_API_KEYS_OPEN` (default off). Closed: no key can be made (403 `api_keys_closed`), a
request that presents a key is refused (401 `api_keys_closed`), the account area shows no "API keys" item, and
`/app/keys` says keys are not issued.

| Requirement | Built | Test (backend/tests/integration/test_api_keys_wp153.py unless named) |
|---|---|---|
| issued to a signed-in account, named, max 5 active | `POST /v1/account/keys` (internal, like the accounts) | `test_a_key_is_shown_once_and_only_its_hash_is_stored`, `test_at_most_five_active_keys` |
| K1 256-bit, shown once, stored hashed, prefix, scopes, expiry 1 year, `last_used_at` | key `dgk_<12 hex>_<43 url-safe>`; SHA-256 in `api_key.key_hash` | same, `test_usage_and_last_use_are_recorded`, `test_an_unknown_revoked_or_expired_key_is_refused`, unit `test_a_new_key_has_a_public_prefix_and_256_random_bits` |
| K1 out-of-scope refused | scopes `tenders` (list, one notice), `archive` (versions); GET only; any other route 403 | `test_a_key_reads_its_scopes_and_its_routes_only`, unit `test_only_the_listed_routes_have_a_scope` |
| K2 fresh sign-in to create or revoke | the account password again, under the sign-in delay (`accounts._require_password`); an account without a password is refused | `test_creating_or_revoking_a_key_needs_the_password` |
| K3 per-key limit on the same limiter | `hardening.RateLimit` hands a request with `Authorization: Bearer` to `apikeys.dispatch`: `TokenBuckets` per key (60 a minute, 10,000 a day, columns of the row), the same request costs; never charged to the address; a refused key costs its address 5 tokens | `test_a_key_over_its_rate_gets_429_with_retry_after` |
| revocable, audit log | `POST /v1/account/keys/{id}/revoke`; `api_key_event` (created, revoked; INSERT only for the service role) and the security log (`api_key_created`/`revoked`, account id and prefix, never the key) | `test_an_unknown_revoked_or_expired_key_is_refused`, `test_the_security_log_names_the_key_prefix_never_the_key` |
| O1 owner-scoped, 404 for another account's key | every statement `WHERE owner_id = %s` | `test_another_accounts_key_is_a_404_and_never_listed` |
| licence filter, config list, default TED | the key's sources are written into the request as the routes' own new `source` parameter (list, one notice, versions; `same_notice` filtered too), so the list cache keys on it; asking for another source is 403 `source_not_licensed`; answers `Cache-Control: private, no-store`, `Vary: Authorization` | `test_a_key_reads_only_the_licensed_sources`, `test_the_licence_list_is_a_setting` |
| account data | export lists `apiKeys` (no hash), deletion cascades keys, usage and history | `test_export_lists_the_keys_without_their_hash_and_deletion_removes_them` |
| key management in the account area | `/app/keys`: make a key (name, scopes, password; the key shown once and kept on that page only), list (prefix, scopes, limits, dates, last used, requests today), revoke with the password, history | e2e `wp153.spec.ts` "K" against the fake account API |
| public `/api` page | endpoints from `web/lib/data/api-endpoints.json` (curated from the OpenAPI), how a request looks, sources and credit, licence on request (no prices); `noindex`, not in the menus until keys open | e2e `wp153.spec.ts`, unit `test_the_api_page_lists_exactly_the_key_routes_with_parameters_the_api_has` (paths, scopes and every parameter exist in the OpenAPI) |

Files: `backend/dgate/apikeys.py` (new), `backend/migrations/0145_wp153_api_keys.sql` (new), `backend/dgate/hardening.py`
(the hand-over in `RateLimit`), `backend/dgate/api.py` (`source` parameter, router), `backend/dgate/accounts.py`
(`api_keys` feature in `/me`, `apiKeys` in the export), `backend/dgate/config.py` (two settings); web: `app/(public)/api`,
`app/(app)/app/keys`, `components/account/api-key-create.tsx`, `app-nav.tsx` (item only when open), `layout.tsx`,
`actions.ts`, `lib/account.ts`, `lib/types.ts`, `components/account/ui.tsx` (one notice), settings page (one deletion
line, shown only when keys are open), `e2e/support/fake-accounts.mjs` (keys, `features: ['api_keys']`).

Personal data: new rows (key name, usage counts, events) tied to the account. DRAFT for the owner:
`docs/legal/drafts/data-protection-api-keys-draft.md` (inventory rows and a privacy paragraph). Nothing published;
`docs/DATA_PROTECTION.md` and the privacy notice are unchanged.

`docs/SECURITY_REQUIREMENTS.md` is not in the repository (local only); its "Built so far" row for API keys K1-K3 should
read "built 27 Oct 2026 (WP-153), closed until DGATE_API_KEYS_OPEN=1".

### Left out (smallest version a licensee recognises)

- Only the notice list, one notice and its archive. Not: `/v1/tenders` (the site's richer shape), funding calls,
  buyers, suppliers, awards, changes feed. Each needs the source filter in its own SQL.
- No rotate endpoint (make a new key, then revoke the old one); no per-account licence grant: once open, every
  signed-in account with a password can make keys (owner question 1).
- Limits are in memory per API process (as the address limiter); the daily quota is a bucket refilled over 24 h, not
  a calendar day. Changing a key's limits is an SQL update by the operator (no admin screen).
- The source's "date of last update" that PLACSP, BOAMP and BDNS require is not in the API answer yet.
- No usage dashboard beyond "requests today"; the per-day counts are in the export.

### Enabling (owner and orchestrator; nothing done here)

`infra/docker-compose.yml` (infra, not touched) must pass `DGATE_API_KEYS_OPEN` and, when it grows,
`DGATE_API_KEY_SOURCES` to the `api` service. Then C below decides how a client reaches it.

## C. How key-holding clients reach the API (proposal; nothing changed)

Facts (Cloudflare's own documentation, read 27 Oct 2026; URLs in the research hand-over): Bot Fight Mode on the Free
plan "cannot be bypassed or skipped using WAF custom rules or Page Rules"; *Skip*, *Bypass* and *Allow* have no effect
on it; it applies to the whole domain and "may challenge API or mobile app traffic". The one documented exception is an
IP Access rule that matches first. Super Bot Fight Mode (Pro and up) can be skipped by a custom rule (for example on a
path plus a header). A DNS-only (grey-cloud) hostname is not seen by Cloudflare at all, and its origin address is public.
The origin accepts only Cloudflare's addresses (origin lock).

| Option | How | For | Against |
|---|---|---|---|
| 1. IP Access rule per licensee | Licensee gives fixed egress IPs; an IP Access "allow" rule for each | free plan, no infra change at the origin, keys still required | Cloudflare's page also says BFM "can still trigger" with IP Access rules: test with one IP first; licensees on cloud functions have no fixed IP; manual per licensee |
| 2. Pro plan, Super Bot Fight Mode | Replace BFM with SBFM; a custom Skip rule for `/v1/*` with an `Authorization: Bearer dgk_` header | the cleanest; keys alone decide; per-path | a monthly cost (owner); a forged header only skips the bot check, the API still refuses a bad key (401, and 5 tokens off that address) |
| 3. Separate DNS-only hostname | `api.` grey-cloud to the origin; Caddy answers on it only `/v1/opportunities*` and only with a key; the origin lock opened for 443 on that name | free, no Cloudflare dependency for API clients | the origin IP becomes public (it then also reaches the main site unless Caddy and the firewall split by host and port: a dedicated port is cleaner); DDoS lands on the origin |
| 4. Bot Fight Mode off | Rely on the API's own limits and Caddy | free, simplest | the site loses Cloudflare's bot screening; the reason it was turned on remains |
| 5. Bulk delivery instead of live calls | a daily signed file per licensee (JSON) the licensee downloads from the account area in a browser, or pushed to their storage | no bot problem, cheap, fits a yearly licence | not live; a second product to build |

Recommendation for the owner and the orchestrator: try option 1 with the first licensee (one rule, reversible),
and plan option 2 if more than a couple of licensees need it; option 5 as a fallback for clients without fixed IPs.

## Tests run (27 Oct 2026, in D:\DEFENCEGATE TESTS\wp153)

- ruff: clean. tsc: clean. Web lib checks (`npm run check`, with the CI environment `DG_USE_MOCK=1`,
  `NEXT_PUBLIC_DG_NOW`): 84 ok, 0 failed (wp128.check needs that environment on integration too).
- Backend unit: green (41 s), including `tests/unit/test_apikeys.py` (10).
- Backend integration, full suite: 1,584 passed, 1 failed: my own test split the key on `_`, which the URL-safe secret
  can contain (a flaky assertion, not the code). Fixed to read the regex group; `test_api_keys_wp153.py` (13) then
  green four runs in a row.
- Playwright (mock build): `wp153`, `wp122`, `wp124`: 24 passed, 8 skipped (the gated ones). Against the fake account
  API (`-g "fake account API"`: `wp153`, `wp150`, `wp79`, desktop and 375): 22 passed. The first run found a real bug:
  "Done" after a new key was a client navigation to the same page, which kept the key on screen; it now puts the key
  away (and the form comes back empty); the test checks both.
- Screenshots: `shots\api-{375,1440}-{light,dark}.png`, `keys-new-*` (the key shown once), `keys-list-*`.

## Counts that need a production read (access was denied to this builder)

- Defence notices per source (`opportunity`, `is_defence AND NOT suppressed`) and how many of them are TED: what a
  TED-only key serves.
- Of the TED notices, how many have a `same_notice` twin in another source (the twin is hidden from a key).

## Open questions for the owner

1. Who may make keys once open: every signed-in account, or only accounts the owner licenses (a per-account grant row)?
2. The allow-list beyond TED (research recommendation above).
3. Option for C.
4. Default limits (60 a minute, 10,000 a day) and the five-key cap.
5. Link `/api` from the footer and let it be indexed when keys open?
