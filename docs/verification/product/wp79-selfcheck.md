# WP-79 self-check: accounts with an e-mail address and a password instead of the sign-in link

Branch `wp-wp79` (from `integration` 5dcff59). Owner's decision of 22 October 2026: no sign-in by e-mail link; a
registration form with e-mail confirmation, sign-in with e-mail and password, password reset by e-mail, optional
two-step sign-in (TOTP). Builder's own check; an independent verifier checks again. Tests ran locally in
`D:\DEFENCEGATE TESTS\wp79` (own venv by uv, throwaway Postgres 17 container `dgate-wp79` on port 55479, the web with
the mock environment of `.github/workflows/web.yml` and `TZ=UTC`). Production was not touched. No model call, no
spending, nothing pushed or deployed. **Sign-in stays closed**: every account route still answers 503 `not_open`
while `mailer.can_send()` is false (no `DGATE_SMTP_HOST`/`DGATE_SMTP_FROM`), the existing switch.

## Design

| Piece | What |
|---|---|
| `backend/migrations/0105_password_accounts.sql` | `app_user` + `password_hash`, `password_changed_at`, `email_verified_at` (set to `created_at` for every existing account, once, inside the `IF NOT EXISTS` of the column: they were made by a link to their address), `totp_secret_enc`, `totp_enabled_at`, `totp_last_step`. New `app_auth_token` (SHA-256 of the token, account, purpose `verify` / `reset` / `mfa`, created, expires, used) and `app_recovery_code` (account, HMAC of the code, used). `app_login_token` emptied (kept; deletion candidate). Grants as 0027/0036/0042: `dgate_app` CRUD, `dgate_api` nothing, `dgate_worker` SELECT for `pg_dump`. Number 0105 leaves 0100-0104 to the parallel builders |
| `backend/dgate/credentials.py` (new, pure) | Argon2id via `cryptography` (already a dependency; PHC strings from 45, measured: 44 has no `derive_phc_encoded`, 45 has; `pyproject` now `cryptography>=45`), OWASP minimum m=19 MiB, t=2, p=1, 16-byte salt, NFKC before hashing; `verify_password` runs Argon2id on a dummy hash when there is no hash, so an unknown address costs the same work. Policy: 12 to 128 characters, not on `seeds/common_passwords.txt`, not a common stem with digits/symbols around it (`Password2026!`), at least 5 distinct characters, not containing "defencegate" or the address's local part (4+ characters); no composition rules. TOTP RFC 6238 with the standard library (HMAC-SHA1, 6 digits, 30 s, one step of drift, each step once). Recovery codes: 10 x `xxxxx-xxxxx` (31-letter alphabet, about 49 bits), stored as HMAC-SHA256 under the server key. TOTP key sealed with AES-GCM under HMAC(server key, label), bound to the account id as associated data |
| `backend/seeds/common_passwords.txt` (new) | 246 entries: stems (password, qwerty, iloveyou, ...) and whole passwords of 12+ characters, written down by hand from the top of the published frequency lists; nothing was downloaded. A larger list can replace it without a code change |
| `backend/dgate/accounts.py` | magic-link routes `POST /auth/request` and the binder flow of `POST /auth/verify` removed. New: `POST /auth/register` (202 always), `POST /auth/verify` (confirms, opens no session), `POST /auth/login` (session, or `{secondStep, ticket}`), `POST /auth/login/second`, `POST /auth/reset/request` (202 always), `POST /auth/reset/confirm`, `POST /me/password`, `POST /me/totp/setup`, `/enable`, `/disable`. `/me` gains `security: {hasPassword, totp}`. The mail limits of A3 moved into `_throttle_mail` unchanged and now guard registration and reset requests together. `_prune` deletes expired counters and tokens and registrations never confirmed within two days |
| Sign-in delay (A8) | failed sign-ins (wrong password, wrong current password in settings, wrong code) write `login_addr` (HMAC of the address typed, account or not) and `login_ip` rows to `app_auth_event`. Five failures of an address in an hour are free, then the next attempt waits 30 s after the last failure, doubling to an hour (12 failures: locked for the hour); a client has 30 free. Checked before the password. A complete sign-in deletes the address's rows; with two-step sign-in on, the password alone does not (otherwise a known password would buy five free guesses at the code each time), and neither does a reset |
| Mail | through the existing `ops.mailer.send_mail` (no provider yet; tests replace it with a list). Plain text: "Confirm your DefenceGate account" (link to `/auth/verify?token=`, 24 h), "You already have a DefenceGate account" (no token; points to `/signin` and `/reset`), "Set a new DefenceGate password" (`/auth/reset?token=`, 1 h), "Your DefenceGate password was changed". The proxy already drops every `token` query parameter from its logs (`infra/Caddyfile`, not changed) |
| Web | `/signin` (e-mail and password; links to `/register` and `/reset`), `/signin/code` (TOTP or recovery code, needs the `__Host-dg_mfa` ticket cookie, 5 min), `/register` (e-mail, password, terms tick with versions), `/auth/verify` (button, as before: rendering spends nothing), `/reset`, `/auth/reset?token=` (new password; `referrer: no-referrer`, noindex). Settings: change password (current one required), two-step sign-in (password, then key shown as text and `otpauth://` link, then a first code, then the 10 recovery codes shown once), turn it off (password), "Sign out everywhere" (revokes every other session, then this one). The `__Host-dg_bind` cookie is gone. All forms are server actions |
| Compatibility | accounts made by the link are confirmed and have no password: sign-in answers "wrong" for them (same answer as any wrong password), the sign-in page and Settings point them to "Forgot your password", and a reset sets the password. Tested |

Not built (YAGNI, say so if wanted): a QR code for the TOTP key (needs a library or a hand-written encoder; the key as
text and the `otpauth://` link work in every authenticator app), regenerating recovery codes without turning two-step
sign-in off and on, rehashing when the Argon2 parameters change, a "resend confirmation" button (registering again
with the same address sends a new link), password re-entry before deleting the account (it still asks for the typed
address, as before).

## Security checklist against docs/SECURITY_REQUIREMENTS.md

`docs/SECURITY_REQUIREMENTS.md` is not on the integration branch; read on `master`. Rows A1-A6 and O1-O3 as written
there; A7-A10 are the rows this package proposes for it (to be added on master by the orchestrator: the file is not
on this branch).

| # | Requirement | Met | Evidence |
|---|---|---|---|
| A1 | canonical e-mail, UNIQUE index | yes | `canonical_email` unchanged and used by every new route; `test_one_address_in_three_spellings_is_one_account` (now also: a second registration in another spelling makes no second account) |
| A2 | link single-use, short-lived, hash only, bound to the browser | changed by the owner's decision | there is no sign-in link. The confirmation link (24 h) and reset link (1 h) are single-use (spent in one `UPDATE ... RETURNING`) and stored as SHA-256; they are not bound to a browser because they open no session: the password does. `test_a_link_works_once`, `test_a_link_expires`, `test_the_link_alone_signs_nobody_in`, `test_only_hashes_are_stored`, `test_a_reset_link_works_once_for_an_hour_and_ends_every_session`, `test_an_expired_or_superseded_reset_link_is_refused` |
| A3 | per-address 5/h, per-IP 20/h, global ceiling paging the operator; identical answers; a refused request writes nothing; HMAC keys | yes (for every request that sends a mail) | `_throttle_mail` is the old code moved; the A3 tests now drive `/auth/register` (`test_the_sixth_request...`, `test_one_ip_is_limited...`, `test_a_request_that_is_not_served_writes_nothing`, `test_six_clients...`, `test_an_ipv6_client...`, `test_the_throttle_keys_are_not_a_plain_hash...`); `test_reset_requests_share_the_mail_limits`. As since audit M2 the over-limit answer is a visible 429 (the row in SECURITY_REQUIREMENTS still says 202; that change predates this package) |
| A4 | disposable domains refused, list is a table | yes | quiet refusal as before (same 202, no mail, no row) for registration and reset: `test_a_disposable_domain_gets_the_same_answer_and_no_mail` |
| A5 | 256-bit session id, `HttpOnly; Secure; SameSite=Lax`, 30 d absolute / 7 d idle, rotated on sign-in, revocable | yes | unchanged `_new_session` (a fresh id at every sign-in, cap of 10); cookie set by the site with `__Host-` prefix (`lib/account.ts`, unchanged attributes); e2e (fake API) asserts `httpOnly, secure, sameSite=Lax, path=/` on `__Host-dg_session` and on `__Host-dg_mfa`; session tests unchanged and green |
| A6 | CSRF, CORS allow-list, size limits before the first cookie route | yes, unchanged mechanism | the API takes no cookie and refuses `Origin`/`X-Forwarded-For` (tests unchanged); every new form is a Next.js server action (Origin compared with Host by Next.js before the action runs) and the session cookie is `SameSite=Lax`. Body limit: `BodyLimit` plus `Field(max_length)` on every new field; `test_a_chunked_body...` now posts to `/auth/register` |
| A7 (new) | registration: password policy (12+, common list, no composition rules), Argon2id, confirmation token single-use 24 h hashed, unconfirmed accounts cannot sign in, no enumeration (same answer, the mail differs), unconfirmed registrations replaced by a newer one and deleted after 2 days | yes | `test_an_account_signs_in_only_once_its_address_is_confirmed`, `test_registering_an_address_that_has_an_account_answers_the_same_and_changes_nothing` (same body, same Argon2id work counted, "already" mail without token, password unchanged), `test_a_newer_registration_of_an_unconfirmed_address_replaces_the_earlier_one`, `test_a_password_is_checked_against_the_policy_at_registration`, unit `test_the_password_policy_*`, `test_argon2id_hash_verifies_only_the_same_password`, prune test (`never@example.com` deleted after 2 days) |
| A8 (new) | login: constant-time verify, one answer for unknown / wrong / no password, progressive delay per address and per IP, before the password is checked; session rotation | yes | `test_an_unknown_address_a_wrong_password_and_an_account_without_one_get_one_answer` (byte-identical bodies), `test_failed_sign_ins_delay_the_address_doubling_and_a_success_clears_them`, `test_the_delay_is_the_same_for_an_address_with_no_account`, `test_one_client_is_delayed_across_addresses`, `test_wrong_current_passwords_count_as_failed_sign_ins`, unit `test_the_sign_in_delay_*`, `test_no_hash_and_a_broken_hash_are_a_no_never_an_error`. Hash comparison is inside Argon2id's verify (constant time) |
| A9 (new) | reset: no enumeration, single-use 1 h token hashed, sessions revoked, a refused password does not burn the link, mail to the stored address; change in settings needs the current password, ends other sessions, mail notice | yes | `test_a_reset_for_an_unknown_address_answers_the_same_and_sends_nothing`, `test_a_reset_link_works_once_for_an_hour_and_ends_every_session`, `test_an_expired_or_superseded_reset_link_is_refused`, `test_a_reset_confirms_an_address_that_was_not_confirmed`, `test_an_account_from_before_passwords_sets_one_through_the_reset`, `test_changing_the_password_needs_the_current_one_and_ends_the_other_sessions` |
| A10 (new) | optional TOTP (RFC 6238), set-up and switch-off need the password, a first code switches it on, 10 recovery codes hashed and shown once, each code and step once, the second step bounded by the delay, a reset does not switch it off, the key stored sealed | yes | unit `test_totp_matches_the_rfc_6238_test_vectors` (all 18 vectors, SHA1/256/512), `test_hotp_matches_the_rfc_4226_test_vectors`, `test_a_code_is_valid_one_step_either_side_and_only_once`, `test_a_sealed_key_opens_only_with_the_same_server_key_and_account`; integration `test_with_totp_on_the_password_alone_gives_no_session` (ticket once, code once), `test_a_recovery_code_works_once_instead_of_the_code`, `test_the_second_step_ticket_expires_and_wrong_codes_are_delayed`, `test_a_right_password_does_not_buy_new_free_guesses_at_the_code`, `test_the_totp_key_and_the_recovery_codes_are_not_stored_usable`, `test_turning_totp_off_needs_the_password_and_a_reset_does_not_turn_it_off` |
| O1 | owner-scoped SQL | yes | every new statement on an owned row is by `user["id"]` of the session or by the token's own `user_id`; cross-tenant test unchanged and green |
| O2 | random ids | yes | unchanged (UUID accounts); tokens 256-bit |
| O3 | export capped and logged | yes | unchanged; the export now includes `security` (booleans only, never a hash) |
| Standing: least privilege | yes | new tables: `dgate_app` CRUD, `dgate_api` none, `dgate_worker` SELECT for the dump; `test_the_public_roles_cannot_read_the_account_tables` and `test_the_accounts_role_reads_only_what_the_account_code_needs` extended with both tables; `test_the_worker_role_can_read_every_table_so_pg_dump_can` green; `test_every_account_flow_works_as_the_least_privileged_role` runs registration, confirmation and sign-in as the real `dgate_app` login |
| Standing: secrets | yes | no secret in any file; the server key stays `DGATE_INTERNAL_SECRET` (compose comment added: rotating it locks out accounts with two-step sign-in until their TOTP columns are cleared) |
| Data protection | yes | `docs/DATA_PROTECTION.md` inventory rows changed in the same commit (below) |

Residual risks, stated: (1) a stranger can slow down one address with failed sign-ins (12 in an hour lock it for up
to an hour); the owner of the address gets in again through a password reset (it clears the delay when two-step
sign-in is off). (2) A victim who clicks the confirmation link of a registration a stranger made in their name
confirms the stranger's password; the mail says "if you did not create an account, ignore this message", and a
registration by the owner replaces an unconfirmed one. (3) The common-password list is short (246 entries plus the
stem rule), not the breach corpus. (4) Rotating `DGATE_INTERNAL_SECRET` invalidates TOTP keys and recovery codes.

## Tests

All runs local, on the final code of the branch (logs in `D:\DEFENCEGATE TESTS\wp79\`).

| Check | Result |
|---|---|
| `ruff check .` | clean |
| unit gate `pytest` | **3102 passed**, 0 failed (new: `tests/unit/test_credentials.py`, 12 functions, 30 cases with the parameters: RFC 6238 appendix B, all 18 values; RFC 4226 appendix D, 10 values; policy; Argon2id; seal; recovery codes; the delay curve) |
| integration `pytest -m integration` (full) | **1214 passed**, 0 failed, 10 min 27 s (new: `tests/integration/test_accounts_passwords.py`, 23 tests; `test_accounts.py` still 60 tests: the 7 that were about the sign-in link now test the same requirement on the confirmation link or the registration request, none removed, none skipped; the privilege tests cover the two new tables) |
| web `tsc --noEmit`, `npm run check`, `next build` (CI env + `TZ=UTC`) | clean, all self-checks ok, build green (new dynamic routes `/register`, `/reset`, `/signin/code`, `/auth/reset`) |
| Playwright, full, 4 workers (CI env, no API) | two full runs: **514 passed, 1 failed, 61 skipped** each, a different test each time and neither in a file this package touches (run 1: `wp49.spec.ts` "a radio applies at once", run 2: `digest.spec.ts` "/digest.atom ... conditional requests", while the integration suite shared the machine); both specs then **87 passed with `--repeat-each 3`**, so load flakes, not regressions. The 61 skipped are the fake-API specs, as in CI. `e2e/wp79.spec.ts` (closed state): `/signin`, `/register`, `/reset` say "not open" and show no password field, are noindex; `/auth/verify`, `/auth/reset`, `/signin/code` without a token or ticket say the link is invalid; the privacy notice lists `__Host-dg_mfa`, not `__Host-dg_bind`, and says "Argon2id" |
| Playwright `wp79.spec.ts` against `e2e/support/fake-accounts.mjs` behind `e2e/support/https-proxy.mjs` (the `__Host-` cookies are refused on plain http; checked: the Set-Cookie was right and Chromium dropped it) | **14 passed** (7 x desktop and 375 px): registration (policy message, address kept, password not handed back, tick required, "check your mail"), sign-in (wrong password message; `__Host-dg_session` HttpOnly, Secure, SameSite=Lax, Path=/), two-step (ticket cookie with the same attributes and no session cookie before the code; wrong code; right code; ticket cookie cleared), reset (request, policy, done, invalid link), confirmation (nothing spent before the button), settings (wrong current password, changed, sign out everywhere shown, TOTP set-up with the key grouped, wrong code keeps the key, recovery codes shown once) |

Timings (local, TestClient against the local Postgres, median of 20): registration 87 ms (new address) and 105 ms
(an address with an account: the same Argon2id work); sign-in 94 ms (right password), 89 ms (unknown address), wrong
password 116 ms (includes one extra connection of the timing script); reset request 56 ms. Argon2id alone: 30 to 33 ms
per hash or verify, 19 MiB of memory each. No new query scans a table: every lookup is by primary key or the
existing unique index on `email_canonical` or the `(kind, key_hash, at)` index of `app_auth_event`.

Hostile review of the diff: 4 issues found and fixed. (1) A right password cleared the failure counter before the
second step, so a known password bought five free code guesses each time: now cleared only after the full sign-in
(regression test `test_a_right_password_does_not_buy_new_free_guesses_at_the_code`). (2) The same through a reset:
a reset no longer clears the delay when two-step sign-in is on. (3) The shared test helper failed for the client
fixture of another test file (`test_buyer_families`): fixed in the helper. (4) The rotation note for the server key
said two-step sign-in "has to be set up again"; in truth such accounts are locked out until their TOTP columns are
cleared: wording corrected in `accounts.py` and the compose comment.

Not checked: real mail delivery (no provider), a real authenticator app (the RFC vectors and the `otpauth://` format
stand in for it), production data (none read: accounts never opened, so the account tables are expected empty;
the two counts are listed for the orchestrator below).

## Privacy notice: every changed sentence (version 1.7, draft for the owner)

`web/app/(public)/privacy/page.tsx`; static copy `docs/legal/versions/privacy-v1.7-2026-10-22.md` (marked DRAFT);
`PRIVACY_VERSION = "1.7"` in `accounts.py` (accounts are closed, so nobody can accept it before the owner decides).
Every other sentence is as on integration 5dcff59.

| Where | Was | Now |
|---|---|---|
| Lead | "Version 1.5, published 18 October 2026." | "Version 1.7, 22 October 2026." |
| In short, 5th item | "A sign-in account, when it opens, uses a one-time e-mail link. There is no password and no tracking pixel in our mail." | "An account, when accounts open, uses your e-mail address and a password, which we keep only as a one-way hash. Two-step sign-in with an authenticator app is optional. There is no tracking pixel in our mail." |
| 4, cookie list | "`__Host-dg_bind` (cookie, first party): only while you sign in. Ties the sign-in link to the browser that asked for it. Expires after 15 minutes." | "`__Host-dg_mfa` (cookie, first party): only while you sign in to an account with two-step sign-in on, between your password and your code. Holds a single-use ticket. Expires after 5 minutes." (`__Host-dg_session` unchanged; "The two cookies are strictly necessary ..." unchanged and still true) |
| 5, opening | "An account is created when you follow a sign-in link sent to your e-mail address. We then hold:" | "You create an account with your e-mail address and a password, and confirm the address through a link we send to it. You sign in with the address and the password. We then hold:" |
| 5, list item 1 | "your e-mail address, when the account was created and when you last visited;" | "your e-mail address, when the account was created, when the address was confirmed and when you last visited;" |
| 5, new item | (none) | "your password as an Argon2id hash (a salted, one-way form from which the password cannot be read back), and when it was last changed. The password itself is never stored or logged;" |
| 5, new item | (none) | "if you turn on two-step sign-in: the key of your authenticator app, encrypted with a key that is not kept in the database, the last code period used (so that each code works once) and when you turned it on, and ten recovery codes as keyed hashes (HMAC), each marked when used. Turning it off deletes them;" |
| 5, new item | (none) | "the links we mail you, to confirm your address (valid 24 hours) or to set a new password (valid one hour), and the ticket between your password and your code (valid 5 minutes): each works once and is held only as a hash;" |
| 5, list item (counters) | "for up to a day: your e-mail address with the one-time link, and a keyed hash (HMAC) of your e-mail address and of your IP address, kept only to limit how often links can be requested;" | "for up to a day: keyed hashes (HMAC) of your e-mail address and of your IP address with the time, kept only to limit how often account mails can be requested and to slow down failed sign-ins (after five failed attempts for one address in an hour, each further attempt has to wait longer, up to an hour);" |
| 5, after the list | "We do not use passwords. We do not look at what you save ..." | "We do not look at what you save ..." (first sentence removed) |
| 5, legal basis | "... Security measures such as limiting sign-in requests rest on Art. 6(1)(f)." | "... Security measures such as limiting account mails and failed sign-ins rest on Art. 6(1)(f)." |
| 5, Mail | "sign-in links and alert digests are plain text, ..." | "the confirmation and password links, a notice when your password is changed, and alert digests are plain text, ..." |
| 5, Retention | "... Sign-in links and rate-limit counters are deleted after about a day." | "... An account whose address is not confirmed within two days is deleted. Links and tickets are deleted a day after they expire, and the rate-limit and failed sign-in counters after about a day." |
| 5, last | "Providing an e-mail address is necessary to have an account; without it we cannot offer one." | "Providing an e-mail address and a password is necessary to have an account; without them we cannot offer one." |

Other copy changed: `/signin` metadata ("... with your e-mail address and password ..." instead of "... and a one-time
link ... No password."), the new pages' texts, the mail texts (in `accounts.MAILS`).

`docs/DATA_PROTECTION.md`: rows `app_user` (new columns), `app_auth_token` and `app_recovery_code` (new),
`app_login_token` (empty, deletion candidate), `app_auth_event` (login-failure kinds; written for failures by design),
mail relay (the four mails), the log row (`token` dropped on every path), "Not held" (passwords only as a hash) and
who can read (the worker reads the hashes for `pg_dump` and does not hold the server key).

## What the owner must provide before sign-in opens

1. **A mail provider** (processor, with a data processing agreement): `DGATE_SMTP_HOST`, `DGATE_SMTP_PORT`,
   `DGATE_SMTP_USER`, `DGATE_SMTP_PASSWORD`, `DGATE_SMTP_FROM`, `DGATE_SMTP_SECURITY` in `infra/.env` (no code
   change). Setting host and from address is what opens accounts (`/v1/account/status` -> `open: true`). SPF/DKIM for
   the sender domain so the confirmation mails arrive.
2. Name the provider in the privacy notice (section 5 "Mail" and section 8), approve version 1.7 (or edit it), set
   its publication date (page lead, static copy name and first line) and have the lawyer look at it with P7/P8.
3. Deploy (orchestrator): migration 0105 (additive; it empties `app_login_token` and marks existing accounts
   confirmed), then the API and web images. Read-only checks before: `SELECT count(*) FROM app_user;
   SELECT count(*) FROM app_login_token;` (expected 0 and 0: sign-in never opened).
4. Decisions that are defaults now: the delay numbers (5 free, 30 s doubling, 1 h cap; 30 per client), the
   common-password list (246 entries; replace with a larger one if wanted), disposable domains refused quietly (as
   before), no QR code for the TOTP key.
5. Add rows A7-A10 (above) to `docs/SECURITY_REQUIREMENTS.md` on master; note there that A2 (the link) is replaced
   and that A3's over-limit answer is a 429 since audit M2.

## Navigation, scratch, how to repeat

- Navigation: none needed in the header or footer (not edited). `/signin` links to `/register` and `/reset`; the
  routes are noindex and not in the sitemap. The visit counter knows `/register` and `/reset` (API and site lists).
- Fake-API run: `node e2e/support/fake-accounts.mjs 4011`; `DG_USE_MOCK=1 DG_API_URL=http://127.0.0.1:4011 npx next
  start -p 3101`; a throwaway certificate (`openssl req -x509 ...`, see `e2e/support/https-proxy.mjs`) and
  `node e2e/support/https-proxy.mjs 3443 3101 key.pem cert.pem`; then
  `E2E_FAKE_ACCOUNTS=1 E2E_BASE_URL=https://localhost:3443 npx playwright test e2e/wp79.spec.ts`.
- Scratch left: the container `dgate-wp79` and `D:\DEFENCEGATE TESTS\wp79` (listed in `docs/DELETION_CANDIDATES.md`);
  the servers were stopped and the certificate deleted.
