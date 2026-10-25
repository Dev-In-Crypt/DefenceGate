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
   not in this draft. WP-124 added them below as a draft of a new term.
3. [WP-131] Term 20 together with the archive item of privacy 1.7, section 7 (re-count the figures before publishing).

## WP-124 (25 October 2026): a new term "Paid plans", DRAFT

Payment is built (Creem, merchant of record, test mode, switched off): `backend/dgate/billing.py`,
`docs/verification/accounts/wp124-selfcheck.md`. It stays off until the owner has the Creem account and products, sets
the settings on the server and publishes this term with the privacy notice 1.7. Where the term goes (after term 14, as
14a, or renumbered) is the owner's choice; the text refers to "these terms" and to term 14 only.

**Draft text:**

"Paid plans. The free plan stays free. The paid plans (Pro, Team, Consultant and Founding customer) and their prices are
those shown on the pricing page when you buy; prices are in euros and exclude VAT.

Paid plans are sold by our reseller and merchant of record, Creem [legal entity and address to be
completed], which takes the payment, charges the VAT that applies, issues the invoice and handles refunds and payment
disputes. When you buy, you enter into the purchase with Creem on its own terms, shown at checkout; these terms govern
your use of DefenceGate. We never see or store your card details.

A plan is billed in advance for its period (a month or a year) and renews at the end of each period until it is
cancelled. You can cancel at any time in Billing, Manage subscription (Creem's customer portal); a cancellation there
takes effect at once and the paid features stop then. [Refunds: to be decided by the owner with Creem's refund policy,
e.g. no refund for a part of a period, except where the law requires one.] If a payment fails, Creem tries again for a
time and the plan stays available meanwhile; if the payment is not made, the plan ends.

When a plan ends or is cancelled, your account returns to the free plan: your saved searches and other data stay, but
the paid features (saved searches and their e-mail alerts) stop until you have a paid plan again.

The Founding customer plan is offered to the first 20 customers at a fixed yearly price for as long as the subscription
continues without interruption [owner to confirm: 'price fixed' means for the life of the subscription].

An account with a running subscription cannot be deleted: cancel the subscription first, then delete the account (term 14).

Paid plans are offered only to customers who act for their trade, business or profession."

### Why each part

| Part | Why |
|---|---|
| merchant of record, Creem's own terms at checkout | Creem is the seller: it charges VAT and issues invoices (owner's choice, 25 Oct 2026); its checkout shows its terms |
| renewal, cancellation "at once" | Creem's customer portal cancels immediately (docs.creem.io, customer portal); the code closes the plan on Creem's `subscription.canceled` event |
| failed payments | Creem's `subscription.past_due` (Creem retries; the plan stays open) and `unpaid` / `expired` (the plan ends): `billing.plan_in_force` |
| downgrade keeps the data | the owner's brief: "Downgrade keeps the user's data but stops the paid feature" |
| deletion needs cancellation first | the safe option: deleting would leave Creem charging an account nobody can manage |
| business customers only | the registration tick already says "I act for a trade, business or profession"; no consumer withdrawal right is offered in this draft (lawyer to confirm) |

### Open items (WP-124)

1. Creem's legal entity name and address as it appears on its invoices.
2. The refund rule (bracket above) and whether a cancellation should instead run to the end of the paid period (Creem's
   API also has a scheduled cancellation, `subscription.scheduled_cancel`, which the code already honours to the end of the
   period; the portal's cancel is immediate).
3. "Price fixed" for Founding customer: for how long.
4. The lawyer's review: merchant-of-record wording, consumer exclusion, the reference to Creem's terms.
