# Terms of use, version 2.2: DRAFT for the owner's approval (WP-123, 25 October 2026)

**Not published.** The page `web/app/(public)/terms/page.tsx` keeps version 2.1 (published 24 October 2026) until the
owner approves this text. The registration form shows the version the API names (`TERMS_VERSION`, now "2.1"); bump it
to "2.2" when the page is published, together with the privacy notice 1.7 (docs/legal/drafts/privacy-v1.7-draft.md).

Built from version 2.1 as it stands on integration (445c1e5). Terms 14 and (WP-131) 20 change; every other term is word
for word 2.1. Term 18 (changes) asks for 30 days' notice of a material change to account holders: no account exists yet (sign-in
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

## [WP-131] Term 20, "Personal data and people named in notices"

**2.1 (in force), first two sentences:**
"Public notices sometimes name a contact person. We do not collect the contact fields a source publishes and we remove
e-mail addresses from free text; a name or number typed into a description by the publisher is not removed."

**2.2 (draft), first two sentences:**
"Public notices sometimes name a contact person. Our collection drops the contact fields a source publishes and removes
e-mail addresses from free text; a name or number typed into a description by the publisher is not removed, older
records in our private archive still contain some contact details, and some buyer names contain a telephone, fax or
e-mail block as the source wrote it. None of it is shown on the site (privacy notice, section 7)."

The rest of term 20 is word for word 2.1.

**Why (round-7 legal-content audit of 25 October 2026):** "We do not collect" is absolute, while the privacy notice
(1.6, section 7, and the 1.7 draft) says the archive still holds contact details, and `docs/DATA_PROTECTION.md` counts
them: about 100 TED payloads of 14-19 September, the Spanish payloads landed before 12 October (not counted), 221 archive
versions with an e-mail address, about 960 organisation names with a contact block (kept by the owner's decision of
24 October 2026, not served). The two texts now say the same.

## What changes

| Sentence | Why |
|---|---|
| "you create an account with your e-mail address and a password and confirm the address ..." | says how an account is made now (no sign-in link) |
| "keep your password secret, do not use it for other services ... two-step sign-in is available and we recommend it" | "credentials" made concrete; reuse of a password elsewhere is the usual way accounts are taken over |
| "By creating an account" (was "By signing in or creating an account") | acceptance happens at registration (the tick with the versions); signing in no longer asks |
| "You may download the data of your account and close it at any time in Settings; closing it deletes it." | the self-service export and deletion exist now |
| [WP-131] term 20: "Our collection drops ... older records in our private archive still contain some contact details ..." | "We do not collect" contradicted the privacy notice and the inventory (see above) |
| the paragraph on choosing a plan | the pricing page's buttons lead to /signup with a plan (WP-122, WP-123); the choice is remembered, nothing is charged, and payment (WP-124) is a separate step with its own terms |

## Open items for the owner

1. Approve or edit the wording; the lawyer's review together with privacy 1.7.
2. The paid-plan terms themselves (price, billing, cancellation, refunds, the merchant of record) belong to WP-124 and are
   not in this draft.
3. [WP-131] Term 20 together with the archive item of privacy 1.7, section 7 (re-count the figures before publishing).
