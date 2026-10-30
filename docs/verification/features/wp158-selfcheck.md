# WP-158 self-check: cluster licence and the co-branded weekly digest

Branch `wp-wp158` from `integration` 53dc50d. Test copy `D:\DEFENCEGATE TESTS\wp158\` (own Postgres `dgate-wp158` on port
56158, removed at the end). Screenshots in `D:\DEFENCEGATE TESTS\wp158\shots\`. Built dark: no association exists until
the operator creates one, accounts stay closed by `DGATE_ACCOUNTS_OPEN`, and while no plan is on sale nobody is refused
anything (WP-124), members included.

## What a customer gets

- **The licence.** An association (a cluster, a trade body) gets a licence agreed outside the plans, with an end date and a
  reason (the agreement's reference). The operator adds its members' existing accounts, at most 50 seats (the admin
  counted). While the licence runs, a member's account has the **Pro** features and the admin's account the **Team**
  features; it ends by itself after its last day, or when the operator withdraws it or removes the member.
- **The account page `/app/association`** (nav item "Association" only for a member): the association's name, the plan it
  gives and until when; for the admin the seats used ("12 of 50", counted, never named); the digest choice.
- **The co-branded weekly digest.** A member who opts in gets the public weekly issue of the last complete week
  (`weekly_digest.get_digest`) for the country and CPV codes they chose, by e-mail: sender "<association> via
  DefenceGate" from our address, the association's name in the subject and the heading, plain text plus the existing
  `mailer.to_html()` form, links to each tender and call and to the whole issue, a change link and a stop link
  (`List-Unsubscribe` header too). Once a week; sent only while accounts are open and the relay is ready.
- **The stop link** `/unsubscribe?token=...`: a page with one button (a POST, so a mail scanner opening the link stops
  nothing); the token switches that member's digest off and can do nothing else.

## How each gate is enforced

| Gate | Where | Test |
|---|---|---|
| member = Pro set, admin = Team set, the larger of subscription and licence wins | `billing.plan_in_force(..., association=)` via `billing.plan_of` (the one function every gate goes through); the plan comes with the session: `accounts.ASSOC_PLAN_SQL` in `accounts.current` and in the alert digest's `ops/digest.DUE_SQL` | unit `test_the_larger_of_the_subscription_and_the_association_is_in_force`, `test_on_sale_a_member_has_the_pro_set_and_the_admin_the_team_set`; integration `test_on_sale_the_member_has_pro_the_admin_team_and_others_free` (a saved search: member 201, other account 402) |
| plans not on sale: nobody refused | `billing.may` (unchanged rule) | unit `test_while_no_plan_is_on_sale_nobody_is_refused`; integration `test_while_no_plan_is_on_sale_the_member_is_refused_nothing_either` |
| licence withdrawn, member removed, licence past its end date: Free, page 404 | `licensed_at IS NOT NULL AND licensed_until > now()` in `ASSOC_PLAN_SQL`, `associations._MINE`, `associations.DUE_SQL` | `test_withdrawing_the_licence_or_the_member_ends_the_plan`, `test_the_licence_ends_by_itself_on_its_last_day` |
| D3: a grant by hand is dated, reasoned, expiring | migration CHECK (`licensed_until > licensed_at AND licence_reason IS NOT NULL` when licensed); `ops.association` refuses `--create`/`--license` without `--until` (today or later) and `--reason` | `test_the_module_reports_by_default_and_writes_only_with_yes` |
| seat cap 50, one association per account | CHECK `seat_cap BETWEEN 1 AND 50`; `ops.association.add_member` counts under `SELECT ... FOR UPDATE` of the association row; `association_member.account_id` is the primary key | `test_the_seat_cap_holds_and_an_account_is_in_one_association` |
| report by default, logged | `ops/association.main` prints a dry run without `--yes`; every change `_audit(...)` (account and association ids, never an address) | `test_the_module_reports_by_default_and_writes_only_with_yes` |
| O1 the membership is the account's own, 404 for others | `WHERE m.account_id = %s` in `_mine`; the digest UPDATE `WHERE account_id = %s` | `test_the_association_is_the_member_s_own_and_seats_are_counted_for_the_admin` |
| natural persons counted, never named | `_out` gives the admin `seats.used`/`cap` only; the module prints ids | same, and the `capsys` check |
| digest choice validated | pydantic (`country` two letters, at most 20 CPV); `tenders.cpv_prefixes` (the list's own rule) → 422 `invalid_cpv` | `test_the_digest_choice_is_validated_and_stored` |
| stop token: random, one action, no oracle | 64 hex from two random UUIDs (244 random bits, migration default); `POST /v1/account/association/unsubscribe` answers `{"done": true}` for any well-formed token; `?token=` is dropped from the proxy's access log by the existing filter (`infra/caddy/Caddyfile`); the page sets `referrer: no-referrer` | `test_the_stop_link_switches_off_that_member_only` |
| digest only while accounts are open, relay ready, issue stored | `associations.run_digests`: `settings().accounts_open`, `mailer.ready()`, the week's `digest_issue` row | `test_the_digest_is_sent_only_while_accounts_are_open`, `test_no_digest_without_a_licence_or_before_the_issue_is_stored_and_a_failed_send_is_retried` |
| once a week, a failed send retried | `digest_last_week` moved only after the relay accepted; worker job `association-digest` hourly at :40 (`worker.job_association_digest`) | `test_the_digest_goes_once_a_week_to_members_who_opted_in_under_the_association_s_name`, the retry test |
| sender name per mail, no header injection | `mailer.build_message/send_mail(sender_name=, headers=)`; CR/LF in any header value refused; display name cleaned on create (`accounts.clean_report_name`: control and direction characters out, 80 characters) | unit `test_a_mail_goes_out_under_the_association_s_name_from_our_address`; integration create with U+202E and a newline |
| account data | export has `association` (the token said to exist, not given); deletion cascades the membership and clears the admin mark | `test_the_digest_choice_is_validated_and_stored`, `test_deleting_an_account_removes_its_membership_and_the_admin_mark` |
| least privilege | migration 0150: `dgate_app` writes, `dgate_worker` reads and may UPDATE `digest_last_week` only, `dgate_api` nothing | `test_the_public_roles_cannot_read_the_account_tables` (existing) and the job tests under the test role |

## Files

New: `backend/dgate/associations.py`, `backend/dgate/ops/association.py`, `backend/migrations/0150_wp158_associations.sql`,
`backend/tests/unit/test_associations.py`, `backend/tests/integration/test_associations_wp158.py`,
`web/app/(app)/app/association/page.tsx`, `web/app/(public)/unsubscribe/page.tsx` and `actions.ts`, `web/e2e/wp158.spec.ts`,
`docs/legal/drafts/data-protection-associations-draft.md` (DRAFT inventory rows and privacy wording; nothing published).

Small shared edits (listed for the merge):
- `backend/dgate/billing.py`: `_RANK`, `plan_in_force(association=)`, `plan_of` passes `assoc_plan`, `features()` adds
  `association` for a member. FEATURES and MESSAGES unchanged: the licence is no plan's feature (as the API licence).
- `backend/dgate/accounts.py`: `ASSOC_PLAN_SQL` and its use in `current`; `patch_me` keeps `assoc_plan`; export
  `association`.
- `backend/dgate/ops/digest.py`: `ASSOC_PLAN_SQL` in `DUE_SQL` (alert digests decide on the same plan as the API).
- `backend/dgate/ops/mailer.py`: optional `sender_name` and `headers` on `build_message`/`send_mail`.
- `backend/dgate/api.py`: router include. `backend/dgate/worker.py`: job `association-digest`, hourly at :40.
- `infra/docker-compose.yml`: worker gets `DGATE_ACCOUNTS_OPEN: ${DGATE_ACCOUNTS_OPEN:-0}`.
- web: `lib/types.ts` (`Me.association`, `AssociationView`), `lib/account.ts` (three calls, `toMe`), `app/(app)/app/actions.ts`
  (`saveAssociationDigest`), `components/account/app-nav.tsx` (`association` prop), `app/(app)/app/layout.tsx` (passes it),
  `app/(app)/app/billing/page.tsx` (a plan without a subscription is said to come from the association, not "Free"),
  `e2e/support/fake-accounts.mjs` (an association admin, the digest routes).

Assertions changed on purpose: `tests/unit/test_worker.py::test_every_job_is_reachable_from_the_cli` (the new job in the
set); `tests/unit/test_wp140.py::test_the_api_gets_the_switch_closed_by_default_and_nobody_else_does` (the worker now gets
`DGATE_ACCOUNTS_OPEN` closed by default, asserted; web and caddy still must not).

## Tests run (test copy)

All on the final code, 30 October 2026:

| Check | Result |
|---|---|
| ruff | clean |
| backend unit (whole suite) | 4138 passed (new: `test_associations.py`, 5) |
| backend integration (whole suite, fresh Postgres 17) | 1618 passed (new: `test_associations_wp158.py`, 13) |
| tsc | clean |
| web lib checks (`scripts/run-checks.mjs`) | pass |
| `next build` | pass |
| Playwright desktop + mobile-375, `wp158.spec.ts` and `wp153.spec.ts` (public parts) | 12 passed |
| Playwright against the fake account API (https), desktop + mobile-375: `wp150`, `wp79`, `wp153`, `wp158` | 26 passed |

Screenshots: `association-{desktop,mobile-375}-{light,dark}.png`, `unsubscribe-{desktop,mobile-375}.png`. No horizontal
scroll at 320 px (`/unsubscribe`, both themes) or on the association page (asserted in the spec). No card with a hover
was added.

## Ops (owner / orchestrator, after merge and deploy; nothing here was run on production)

1. Migration 0150 runs with the deploy (`python -m dgate.migrate`).
2. Recreate the worker so it gets `DGATE_ACCOUNTS_OPEN` (still 0: nothing is sent).
3. For a signed agreement: `python -m dgate.ops.association --create <key> --display-name "<Name>" --until YYYY-MM-DD
   --reason "<agreement ref>"` (report), then again with `--yes`; members (their accounts must exist):
   `--association <key> --add-member <email> [--admin] --yes`. Withdraw: `--association <key> --revoke --yes`; renew or
   move the end: `--license --until ... --reason ... --yes`.
4. Before the first member is added: publish the data-protection rows and privacy wording of the draft (owner).

## Left out (smallest version)

- No self-service: the admin cannot invite or remove members in the account area (the operator does it on request); no
  invitation of addresses that have no account (the module stores no address of its own).
- No association logo or colours in the mail (name only); the HTML is the existing plain `to_html()`.
- A member cannot also buy a plan of their own while the licence gives one (`create_checkout` refuses any account whose
  plan is not Free, as before); a licence never lowers a bought plan (the larger wins).
- No one-click `List-Unsubscribe-Post` (the header points at the page with the button); no per-association digest
  statistics.
- The licence contract text itself is not drafted.

## Open questions for the owner

- Should the admin seat count against the 50 (built: yes)?
- Is "Pro for members, Team for the admin" right for every association, or per agreement (a column would do it)?
- The sender "<Name> via DefenceGate" from our address: acceptable to the first association?
