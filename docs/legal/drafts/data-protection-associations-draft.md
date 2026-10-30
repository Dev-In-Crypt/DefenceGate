# Cluster licence and the association's digest (WP-158): DRAFT additions for docs/DATA_PROTECTION.md and the privacy notice (30 October 2026)

**Not published. For the owner's approval.** Nothing here changes a live text: `docs/DATA_PROTECTION.md` and
`web/app/(public)/privacy/page.tsx` stay as they are. Accounts are closed (`DGATE_ACCOUNTS_OPEN` unset), and no association
exists until the operator creates one (`python -m dgate.ops.association`); these texts should be in place before the first
association's members are added.

## What is held (migration 0150, `backend/dgate/associations.py`, `backend/dgate/ops/association.py`)

Rows to add to the inventory table of `docs/DATA_PROTECTION.md`, after the API key rows:

| Where | What | Why | Retention proposed |
|---|---|---|---|
| `association` (migration 0150, WP-158) | per association (a legal entity, a cluster or trade body): an operator key, the name shown in its mails, when its licence started (or that it was withdrawn), the seat cap, which account is its admin | the licence: who is entitled to what | while the licence relationship lasts; the admin link goes when that account is deleted (SET NULL) |
| `association_member` (migration 0150) | per member account: the association, since when, whether the person asked for the weekly digest, the country and CPV codes chosen for it, the last week mailed, a random stop token (it can only switch the digest off) | give the account the licence's features; send the digest the person asked for and let them stop it from the mail | until the member is removed or the account is deleted (cascade) |
| Security log, association lines (WP-158) | `account event=association_member_added user=<account id> association=<id>`, `association_member_removed`, `association_admin_set`, `association_created`, `association_licence_granted/withdrawn`, `association_digest_on/off/unsubscribed`; never an address | as the accounts lines | as the accounts lines (90 days) |

The membership is personal data of the account holder (it says which organisation's licence they use). It is set by the
operator on the association's written request, not by the member; the association learns from us how many seats are used,
never who holds them. The member is told on the account page (`/app/association`).

The digest mail is sent by us, from our address, with the association's name in the sender name ("<name> via
DefenceGate") and heading. It holds the public weekly issue only (tenders and funding calls: commercial data), nothing about
the member; the relay receives the member's address as for any account mail. No tracking, no image, no rewritten link
(`ops/mailer.py`). The stop link travels as `?token=` so the proxy drops it from its access log as it does for sign-in
links (`infra/caddy/Caddyfile`).

The data export (`GET /v1/account/export`, "Download my data") now includes `association`: the association's name, the
role, since when, the digest choice and the last week mailed; the stop token is said to exist, not given. Deleting the
account deletes the membership.

## Privacy notice: proposed addition (next version, section 5 "Accounts")

> **Association licences.** If your organisation is a member of an association (for example a cluster) that holds a
> licence with us, we add your account to that association at the association's request. We keep which association your
> account belongs to and since when; your account then has the features of the licence. The association is told how many
> of its seats are used, not who uses them. If you choose to receive the weekly digest in the association's name, we keep
> that choice, the country and product codes you chose and the last week we sent; every mail has a link that stops it.
> It is kept while you are a member and deleted when you are removed or delete your account.

Bump `PRIVACY_VERSION` in `backend/dgate/accounts.py` and keep a dated copy in `docs/legal/versions/` when this is
published (the accounts module asks accounts to accept a new version). The licence itself (between us and the
association) needs a contract text of its own: not drafted here.
