# WP-157 self-check: team workspace and Consultant client profiles

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-FEATURES-2.md`, section WP-157 (owner, 30 Oct 2026). Branch `wp-wp157` from
`integration` 53dc50d. Test copy `D:\DEFENCEGATE TESTS\wp157\` (own Postgres `dgate-wp157` on port 56157). Screenshots in
`D:\DEFENCEGATE TESTS\wp157\shots\`. Migration **0149**. No price anywhere.

## What a customer gets

- **Team (and Consultant, "Everything in Team")**: `/app/team`. Make a workspace, invite colleagues by e-mail (5 people in
  all, the owner included), withdraw an invitation, remove a member, leave, end the workspace. Members have the owner's plan
  and see one another's saved searches, shortlist (status and note: the one entry per item is shared, a teammate's change is
  everyone's) and follows. A teammate's saved search is shown with a tag and without its controls (alerts stay its author's).
  The invitation link lands on `/app/team/join?token=...`: sign-in first (the layout returns there), and only the button joins.
- **Consultant**: `/app/clients`. Up to 15 client profiles (company name, country, CPV codes, note; commercial data only, the
  form says so). A client switcher ("Working on") on Clients, Searches and Shortlist (a `__Host-` cookie of the site; the API
  checks the id at every use); searches and shortlist entries can be given to a client and the lists narrow to it. The company
  report shows "Prepared for <client>" on screen and in the printed head, next to the name on reports.
- Nav: "Team" when `me.features` has `team_workspace` or the account is in a workspace (so a member whose sharing stopped can
  still leave); "Clients" with `client_profiles` (pattern of `KEYS` in `app-nav.tsx`).

## How each gate is enforced

| Gate | Where | Not on sale (WP-124: nobody refused) | On sale |
|---|---|---|---|
| `team_workspace` (Team, Consultant) | `billing.FEATURES`, `MESSAGES`; `billing.require` in `workspace.create_workspace`, `workspace.invite`; owner's plan in `workspace.join`; `accounts.shared_scope` (sharing stops when the plan in force lacks it) | every account | Team, Consultant; Free/Pro/Founding 402 `plan_required` |
| seats | `billing.SEATS`, `billing.seat_limit`; `workspace.invite` (members + open invitations), `workspace.join` (members, owner's plan) | 5 | Team 5, Consultant 5, others 0 |
| `client_profiles` (Consultant) | `billing.require` in `workspace.create_client`, `patch_client`, `workspace.client_id` (every use of a client id: search, shortlist, list filter, report) | every account | Consultant only |
| client count | `billing.CLIENTS`, `billing.client_limit`; `workspace.create_client` | 15 | Consultant 15 |
| members share the owner's plan | `accounts.current` joins `workspace_member` and the owner's `billing_subscription` (`ws_*`, `accounts.PLAN_KEYS`); `billing.plan_of` takes the owner's plan when it has the workspace and ranks above the member's own; `ops/digest.DUE_SQL` reads the same for alerts | - | as stated |
| accounts closed | `accounts._open` in `workspace.invite` (no mail without the relay and the switch); everything else needs a session, which needs open accounts | - | - |

Security (docs/SECURITY_REQUIREMENTS.md):
- O1: every query of the workspace tables is scoped by the authenticated account's workspace in SQL; rows of
  `app_saved_search` / `app_shortlist` / `app_follow` through one helper `accounts.shared_scope` (`owner_id = me OR
  workspace_id = my workspace while the plan has it`). Another workspace's member, invitation or client is a 404.
- O2: workspace, invitation and client ids are UUIDs.
- O3: the account export now includes the membership, and for the owner the invitations and client profiles (capped at 100).
- Invitation (as A2 for account links): 256-bit random token, only its SHA-256 stored, single use (spent when the account
  joins), 7 days, bound to the invited address (another account gets 403 `wrong_account` and the token stays usable for the
  right one); the answer is the same whether or not the address has an account; at most 20 a day per workspace and one mail an
  hour to one address (429 with `Retry-After`); the owner cannot invite itself. The mail names no inviter address. Opening the
  join page joins nothing (a mail scanner opens links): the form does. "Signed link" of the brief: a stored-hash random token,
  as every account link here, rather than an HMAC signature (revocable by deleting the row).
- Security log lines `workspace_created|invite|joined|left|removed|dissolved` with account and workspace ids, never an address.
- New tables: grants in the migration (accounts role writes, API role nothing, worker reads).

## Tests

- Backend unit `tests/unit/test_wp157.py` (4): the member's plan (owner's when it has the workspace and is higher), seats and
  clients per plan, both states, the sharing scope.
- Backend integration `tests/integration/test_wp157_workspace.py` (12): sharing of shortlist/follows/searches incl. dashboard
  and state; outsider sees nothing (404, 403 for non-owner); invitation hashed, one-time, address-bound, expiring; seats and
  the hourly limit; closed accounts send no invitation; members have the owner's plan once on sale, Free/Pro/Founding refused,
  the owner's downgrade stops the plan and the sharing (rows stay), an invitation is refused while the owner's plan lacks it;
  the alert digest reads the owner's plan; leave, remove, dissolve; export; client profiles (cleaning, validation, labels, list
  filter, cross-workspace 404, removal keeps rows); Consultant-only and the cap of 15 in both states; the report carries the
  client's name.
- Full backend run in the test copy: ruff clean, unit green, integration 1616 passed + 1 pinned assertion moved (below), then
  the touched files re-run green.
- Web: `tsc` clean, `node scripts/run-checks.mjs` green (new `lib/client-profile.check.ts`), `next build` green.
- Playwright `e2e/wp157.spec.ts`: public (Team, Clients, Join behind sign-in) and against the fake account API (an address
  starting with `team` is a Consultant in a workspace, `e2e/support/fake-accounts.mjs`): make/invite/withdraw/refused invite/
  end needs the tick; the join page joins only on its button; a client added, picked, invalid CPV refused; switcher on searches
  and shortlist, "seen by your team" note; a teammate's search without controls; no horizontal scroll at 320 px in both
  themes; screenshots at 375, 1280 and 1440 px, light and dark. Runs: account specs (wp150, wp79, wp153, wp157) 33 passed,
  1 skipped (the 1440 screenshot test runs on the desktop project only); public wp157, wp152, wp153, wp155-api: 29 passed and
  one wp155-api desktop test hit React #418 once on `/suppliers/.../competitors` (the known intermittent, backlog); wp155-api
  re-run three times: 30 of 30 passed.

Assertions moved on purpose (they pin the feature set, which WP-157 extends by two):
- `backend/tests/unit/test_wp155.py` TABLE (+ `team_workspace`, `client_profiles`)
- `backend/tests/unit/test_wp124.py` the set of FEATURES and `features(free)` while not on sale
- `backend/tests/integration/test_billing_wp124.py` `/me` features while billing is closed
- `web/lib/wp155.check.ts` PAID_FEATURES list

## Shared files touched (small)

`backend/dgate/billing.py` (FEATURES, MESSAGES, SEATS, CLIENTS, `plan_of`, `seat_limit`, `client_limit`),
`backend/dgate/accounts.py` (`current` join, `PLAN_KEYS`, `shared_scope` on the shortlist/follow/search queries, `clientId` on
searches and shortlist, `?client=` filters, `/me.workspace`, export), `backend/dgate/api.py` (router),
`backend/dgate/competition.py` (`open_report` `?client=` -> `clientName`), `backend/dgate/ops/digest.py` (DUE_SQL),
`web/components/account/app-nav.tsx`, `web/app/(app)/app/layout.tsx`, `web/components/account/ui.tsx` (notice texts),
`web/lib/account.ts` (`call` exported, client params, `clientName`, `workspace`), `web/lib/types.ts`,
`web/app/(app)/app/searches/page.tsx`, `shortlist/page.tsx`, `web/app/(public)/suppliers/[slug]/report/page.tsx`,
`web/e2e/support/fake-accounts.mjs`. Not touched: `web/lib/pricing.ts`, config.py, docker-compose (no new setting).

Own files: `backend/dgate/workspace.py`, `backend/migrations/0149_wp157_workspace.sql`, the two test files,
`web/lib/workspace.ts`, `web/lib/client-profile.ts` (+ check), `web/app/(app)/app/team/{page,actions}.tsx|ts`,
`team/join/page.tsx`, `web/app/(app)/app/clients/page.tsx`, `web/components/account/client-switcher.tsx`, `web/e2e/wp157.spec.ts`,
`docs/legal/drafts/data-protection-workspace-draft.md` (DRAFT, not published).

## Ops to run

Migration 0149 at deploy (additive, idempotent). Nothing else: no backfill, no setting. Accounts stay closed by
DGATE_ACCOUNTS_OPEN as today; with plans not on sale every account may use both features (WP-124 rule).

## Left out (smallest version)

- Saving a search or shortlisting from the public pages does not attach the picked client (assign it on the Searches or
  Shortlist page); the dashboard shows the team's shortlist and follows but only the account's own saved searches.
- Company report quotas stay per account (not pooled per workspace).
- No per-member permissions beyond owner/member; no transfer of ownership; no re-send button (invite again after an hour).
- Two members who both had the same item shortlisted before joining keep two entries (new ones are one shared entry).

## Open questions for the owner

1. Seats: Consultant "Everything in Team" read as 5 users too. More?
2. Members see one another's e-mail addresses on the Team page; a count only instead?
3. Pooled report quota per workspace, or per account as now?
4. Lawful basis for the invitation mail to a person who is not yet a user (draft, open item).
5. Should joining share the member's existing rows (built: yes, the join page says so) or only new ones?
