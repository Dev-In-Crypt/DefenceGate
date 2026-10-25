# Terms of use, version 2.2: DRAFT for the owner's approval (WP-123, 25 October 2026)

**Not published.** The page `web/app/(public)/terms/page.tsx` keeps version 2.1 (published 24 October 2026) until the
owner approves this text. The registration form shows the version the API names (`TERMS_VERSION`, now "2.1"); bump it
to "2.2" when the page is published, together with the privacy notice 1.7 (docs/legal/drafts/privacy-v1.7-draft.md).

Built from version 2.1 as it stands on integration (445c1e5). Only term 14 changes; every other term is word for word
2.1. Term 18 (changes) asks for 30 days' notice of a material change to account holders: no account exists yet (sign-in
has never opened), so publishing 2.2 before accounts open needs no notice.

## Term 14, "Accounts"

**2.1 (in force):**
"Where accounts are offered: give accurate information, keep your credentials secret, and tell us promptly if you
suspect misuse. You are responsible for activity under your account. By signing in or creating an account you confirm
that you accept these terms and the privacy notice. You may close your account at any time. We may refuse or suspend an
account for breach of these terms or misuse."

**2.2 (draft):**
"Where accounts are offered: you create an account with your e-mail address and a password and confirm the address
through a link we send to it. Give accurate information, keep your password secret, do not use it for other services,
and tell us promptly if you suspect misuse; two-step sign-in is available and we recommend it. You are responsible for
activity under your account. By creating an account you confirm that you accept these terms and the privacy notice. You
may download the data of your account and close it at any time in Settings; closing it deletes it. We may refuse or
suspend an account for breach of these terms or misuse.

Choosing a plan on the pricing page before payment is open is not an order: no fee is due and no paid plan or paid
contract arises until you complete a checkout that states the price, the billing period and the terms of the paid plan.
Until then every account is on the free plan."

## What changes

| Sentence | Why |
|---|---|
| "you create an account with your e-mail address and a password and confirm the address ..." | says how an account is made now (no sign-in link) |
| "keep your password secret, do not use it for other services ... two-step sign-in is available and we recommend it" | "credentials" made concrete; reuse of a password elsewhere is the usual way accounts are taken over |
| "By creating an account" (was "By signing in or creating an account") | acceptance happens at registration (the tick with the versions); signing in no longer asks |
| "You may download the data of your account and close it at any time in Settings; closing it deletes it." | the self-service export and deletion exist now |
| the paragraph on choosing a plan | the pricing page's buttons lead to /signup with a plan (WP-122, WP-123); the choice is remembered, nothing is charged, and payment (WP-124) is a separate step with its own terms |

## Open items for the owner

1. Approve or edit the wording; the lawyer's review together with privacy 1.7.
2. The paid-plan terms themselves (price, billing, cancellation, refunds, the merchant of record) belong to WP-124 and are
   not in this draft.
