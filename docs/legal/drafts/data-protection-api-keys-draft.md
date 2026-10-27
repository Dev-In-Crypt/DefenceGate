# API keys (WP-153): DRAFT additions for docs/DATA_PROTECTION.md and the privacy notice (27 October 2026)

**Not published. For the owner's approval.** Nothing here changes a live text: `docs/DATA_PROTECTION.md` and
`web/app/(public)/privacy/page.tsx` stay as they are. Keys are closed (`DGATE_API_KEYS_OPEN` unset) until the owner opens
them, and these texts should be in place before that.

## What is held (migration 0145, `backend/dgate/apikeys.py`)

Rows to add to the inventory table of `docs/DATA_PROTECTION.md`, after the billing rows:

| Where | What | Why | Retention proposed |
|---|---|---|---|
| `api_key` (migration 0145, WP-153) | per key an account made: a random id, the account, the name the account gave it (up to 60 characters, free text: it may hold whatever the person types), the public prefix (12 hex characters), the SHA-256 of the key (never the key), the scopes (`tenders`, `archive`), the rate limit and daily quota, when it was made, when it expires (a year later), when it was last used (moved at most once a minute) and when it was revoked | authenticate a key-holder's requests; let the account see and revoke its keys | until the account is deleted (cascade). A revoked or expired key stays listed for the account (proposed: deleted a year after it ended; not built) |
| `api_key_usage` (migration 0145) | per key and day: the number of requests made with it. No address, no path, no query | check use against a licence; show "requests today" | until the account is deleted (cascade). Proposed: rows older than 13 months deleted (not built) |
| `api_key_event` (migration 0145) | per key: `created` or `revoked`, the account, the time. Append-only for the service role | the account's own history of its keys; evidence for a licence dispute | until the account is deleted (cascade) |
| Security log, key lines (WP-153) | `account event=api_key_created user=<account id> key=<prefix>` and `api_key_revoked`; never the key, its hash, an address or a password | as the accounts lines | as the accounts lines (90 days) |

A request made with a key is not logged by the API (only counted above). Caddy's access log holds it as it holds any
request (14 days); the key travels in the `Authorization` header, which Caddy redacts in its logs unless the server option
`log_credentials` is on (it is not in `infra/caddy/Caddyfile`). To be confirmed on one logged line by the operator.

The data export (`GET /v1/account/export`, "Download my data") now includes `apiKeys`: per key the name, prefix, scopes,
limits, dates and the requests per day for the last 400 days; never the hash. Deleting the account deletes the keys,
their usage counts and their history.

## Privacy notice: proposed addition (next version, section 5 "Accounts")

> **API keys.** If your organisation holds a data licence, you can make API keys in your account. For each key we keep
> the name you give it, a short public prefix, a one-way hash of the key (never the key itself, which is shown to you
> once), its scopes and limits, when it was made, last used, expires or was revoked, and how many requests were made
> with it each day. We use this to let your scripts in, to apply the limits of your licence and to show you your keys.
> It is kept while your account exists and is deleted with it. Requests made with a key are counted, not recorded.

Bump `PRIVACY_VERSION` in `backend/dgate/accounts.py` and keep a dated copy in `docs/legal/versions/` when this is
published (the accounts module asks accounts to accept a new version).
