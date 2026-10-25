# WP-123 self-check: accounts with e-mail and password, ready for a mail provider

Branch `wp-wp123` from `integration` 445c1e5, with the unmerged `wp-wp79` (cede846) brought over as one cherry-pick.
Builder's own check; an independent verifier checks again. Tests ran in `D:\DEFENCEGATE TESTS\wp123` (own venv, throwaway
Postgres 17 `dgate-wp123` on 55523, removed at the end). Production not touched, nothing pushed, merged or deployed, no
external network call in any test. The WP-79 design and its own checklist stay in `docs/verification/product/wp79-selfcheck.md`;
this file lists what changed on top of it.

## Bringing WP-79 onto today's integration

| Conflict / stale item | Resolution |
|---|---|
| migration 0105 | renumbered `0131_wp123_password_accounts.sql`, header rewritten; plan columns added (below) |
| `tests/conftest.py` TABLES | both sides: WP-79's `app_recovery_code, app_auth_token` and WP-114's `job_run` |
| `docs/DELETION_CANDIDATES.md` | both sides; WP-79 rows rewritten for WP-123 |
| WP-116 return page (`next`) | carried by the password form instead of the bind cookie: `/signin?next=` -> hidden field -> `finish()` redirects to `safeReturnPath(next)`; with two-step sign-in via `/signin/code?next=`. `bindValue`/`readBind` stay in `lib/safe-url.ts` (their WP-116 check still runs) and are listed as deletion candidates |
| privacy page | integration's 1.6 kept (WP-79 had put its 1.7 draft on the page): the draft moved to `docs/legal/drafts/` and rebuilt from 1.6 |
| `TERMS_VERSION` / `PRIVACY_VERSION` | were "2.0" / "1.5" on integration while the pages say 2.1 / 1.6 (stale): now "2.1" / "1.6" |
| WP-117 homepage, WP-86 menu | no conflict; `lib/site-copy.ts` FAQ answer and `/alerts` said "one-time link, no password": made true ("e-mail address and a password") |
| `/register` | now `/signup` (pricing buttons land there); `/register` is a permanent redirect keeping `plan`/`billing` |
| "Had an account before passwords were introduced?" on /signin | removed: sign-in never opened, so no such account exists |

## Security review against SECURITY_REQUIREMENTS.md (as if new): findings fixed

| # | Finding | Fix | Test |
|---|---|---|---|
| F1 | The TOTP seal key, recovery-code HMAC key and counter key was `DGATE_INTERNAL_SECRET`, which the site's server also holds: a compromised web container plus a dump opens every TOTP key | `DGATE_ACCOUNT_KEY`, API only (compose gives it to `api`, not `web`); production keeps accounts closed without it | `test_the_totp_key_is_sealed_with_the_account_key_not_the_shared_secret`, `test_in_production_accounts_need_the_apis_own_key`, `test_the_account_key_is_given_to_the_api_and_not_to_the_site`, `test_the_account_key_is_not_in_the_settings_repr` |
| F2 | Accounts would open with a password while the published privacy notice says "There is no password" | `accounts_problem()`: closed while `PRIVACY_VERSION` < `PASSWORD_PRIVACY_VERSION` (1.7) | `test_accounts_stay_closed_until_the_privacy_notice_for_passwords_is_published`, `test_the_shipped_versions_keep_accounts_closed` |
| F3 | "Open" meant only "host and from set": a wrong password or dead relay opened registration whose mails never arrive | `mailer.ready()`: health check (connect, TLS, log in, NOOP; nothing sent), kept 10 min when passed, retried after 1 min when failed, re-run at once when the settings change; digests use it too | `test_the_health_check_passes_against_a_working_relay_and_sends_nothing`, `test_a_relay_that_does_not_answer_keeps_mail_closed_and_the_answer_is_kept`, `test_a_relay_that_fails_its_health_check_keeps_accounts_closed` |
| F4 | `DGATE_SMTP_SECURITY=none` allowed plain SMTP to any host: reset links in clear text | plain SMTP only to a loopback relay | `test_plain_smtp_is_refused_for_a_relay_that_is_not_on_this_host` |
| F5 | Deleting the account needed only the session and the typed address | the password too (same delay as a sign-in) | `test_deleting_needs_the_password_and_removes_every_owned_row`, e2e |
| F6 | A password reset sent no notice | "Your DefenceGate password was changed" after a reset as after a change | e2e (mail read from the catcher); `test_audit_lines_hold_no_secret` |
| F7 | No security log; and the O3 export line (INFO) was dropped under uvicorn (root logger WARNING) | `_audit()` lines (event + account id only) and an INFO handler on the `accounts` logger | `test_audit_lines_hold_no_secret` (passwords, tokens, codes, session, address absent; events present); seen in the e2e API log |
| F8 | Export missed sessions, confirmation/password/TOTP dates | added (no hash, key, code or token) | `test_the_export_holds_everything_about_the_account_and_no_secret` |

Reviewed and kept as built by WP-79 (tests from WP-79, all green here): Argon2id m=19 MiB t=2 p=1 (OWASP minimum),
dummy hash for unknown addresses; identical 202 for register/reset whatever the address; A3 mail limits per address,
address+IP, IP and global; A8 delay per address and per IP before the password check; tokens single use in one UPDATE,
24 h / 1 h / 5 min, SHA-256 only; TOTP each step once, recovery codes HMAC; session 256-bit, rotated, 30 d / 7 d,
`__Host-` cookies HttpOnly Secure SameSite=Lax; CSRF by Next.js server-action Origin check (now also tested end to end)
and the API refusing `Origin`/`X-Forwarded-For`.

Residual (stated, not fixed): a stranger can delay one address for up to an hour with failed sign-ins (a reset clears
it when TOTP is off); a stranger's unconfirmed registration of someone's address can be confirmed by its owner clicking
the link; the common-password list is short; rotating `DGATE_ACCOUNT_KEY` locks TOTP accounts out; no "new device" mail
(optional in the brief: needs a device record, not built).

## Package items

| Item | Done |
|---|---|
| /signup with `?plan=&billing=` | shown before and after registering and after the confirmation link ("You chose Pro, monthly. Payment opens soon."), stored as `plan_choice`/`billing_choice`, `/me.plan = {current: 'free', chosen, billing}`, Settings "Plan" block; unknown plan ignored on the page, 422 at the API; free has no period; re-registering a confirmed address changes nothing. `app_user.plan` (default `free`, CHECK) is the clean place for WP-124 |
| Mail | `DGATE_SMTP_*` unchanged; sender "DefenceGate"; every mail text + HTML from the same text (escaped, links unchanged, no image/pixel/redirect); confirm, reset, changed (change and reset), "already", digests |
| Opens automatically | when `accounts_problem()` is None: relay passed its check, privacy 1.7 published, `DGATE_ACCOUNT_KEY` in production. Until then every account page: "Sign-in is not open yet. Sign-in opens soon. ..." |
| Dev mail catcher | `DGATE_MAIL_CATCHER_DIR` writes `.eml` files; refused in production; tests use `tests/mailcatcher.py` (local SMTP on 127.0.0.1) and the catcher dir |
| Deletion | Settings lists what goes (4 items), needs address + password |
| Export | Settings "Download my data", complete as above |

## Tests (batched scope)

| Check | Result |
|---|---|
| `ruff check .` | clean |
| pytest, unit + integration of the touched area: `unit/test_wp123.py` (new, 3), `unit/test_mailer.py` (new, 10), `unit/test_credentials.py`, `unit/test_accounts.py`, `unit/test_compose_env.py`, `unit/test_wp34.py`, `unit/test_wp71.py`, `unit/test_migrate.py`, `integration/test_accounts.py`, `test_accounts_passwords.py`, `test_accounts_wp123.py` (new, 12), `test_buyer_families.py`, `test_repair_ted.py`, `test_readiness_api.py`, `test_security_hardening.py` | all passed (253 in the main batch, the rest in a second run) |
| web `tsc --noEmit`, `npm run check` (incl. new `lib/wp123.check.ts`), `next build` | clean |
| Playwright (mock env, no API): wp79, wp123, routes, wp116, wp46, wp56, wp59, wp63, wp86, wp117 | 163 passed, 6 failed on the first run (wp79 "no form" counted the header's search form, see below); after the fix wp79 + wp123: 20 passed |
| Playwright `wp123.spec.ts` against the real API (`tests/e2e_api.py`, Postgres, catcher dir, https proxy) | 4 passed (desktop and 375 px): register with plan -> confirm -> sign in (cookie flags) -> reset -> change -> delete; cross-site sign-in post refused (>= 400, no cookie) |
| Playwright `wp79.spec.ts` against the fake API (WP-79's harness) | 14 passed |

Tests changed (none deleted, skipped or weakened):
- `integration/test_accounts.py`: fixture `sent` uses a local SMTP catcher instead of `relay.invalid` (the health check
  runs for real) and opens the privacy gate as publication will; two DELETE `/me` calls now send the password (F5).
- `e2e/wp79.spec.ts`: the privacy test moved to the new contract (was: page says 1.7, lists `__Host-dg_mfa`, Argon2id;
  now: page stays 1.6 until approved, no 1.7 text); "no form" scoped to `main`; `/signup` added to the closed pages.

## Owner

Settings to set on the server (names only): `DGATE_SMTP_HOST`, `DGATE_SMTP_PORT`, `DGATE_SMTP_USER`,
`DGATE_SMTP_PASSWORD`, `DGATE_SMTP_FROM`, `DGATE_SMTP_SECURITY` (starttls or ssl), `DGATE_ACCOUNT_KEY` (new, api only).
Then approve and publish privacy 1.7 (and terms 2.2): `docs/legal/drafts/`.

Deploy (orchestrator): migration 0131 (additive; empties `app_login_token`, marks existing accounts confirmed; expected
0 accounts), then api and web.

Proposed rows for `docs/SECURITY_REQUIREMENTS.md` (on master; not in this checkout): A7-A10 as in the WP-79 self-check,
plus A11 "account secrets keyed by an API-only key", A12 "accounts open only with a relay that passed its check and the
published notice", A13 "deletion needs the password; export complete and secret-free; security log without secrets".
