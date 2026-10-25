# WP-122 self-check: pricing page with plans and prices (owner, 25 Oct 2026)

Branch `wp-wp122` from `integration` 397162a. Web only; no backend, no migration, no ops module.

## Owner's change during the package (orchestrator, 25 Oct)

The brief's call to action (a mailto link to `NEXT_PUBLIC_SALES_EMAIL`) was replaced before anything was committed: **no mailto and no
sales e-mail setting at all.** Each paid plan gets a "Choose <plan>" button to `/signup?plan=<id>&billing=<monthly|yearly>`, shown only
when `NEXT_PUBLIC_BILLING_OPEN` is on (default off; accounts with e-mail + password and payment through a merchant-of-record provider
are a later package, which also builds `/signup`). Off: "Opens soon" in place of the buttons. On-request items: "On request, opens soon".
Plan ids: free, pro, team, consultant, founding.

## What changed

| Item | Change |
|---|---|
| Data | `web/lib/pricing.ts`: the five plans (id, name, audience, monthly / yearly price, features with `coming`), the three on-request items, `BILLING_OPEN` (`NEXT_PUBLIC_BILLING_OPEN` is `1` or `true`, read like `SITE.url` in `lib/seo.ts`, at build time) and `signupHref(plan, billing)`. |
| Page | `web/app/(public)/pricing/page.tsx`: one lead sentence ("Browsing stays free, and no paid plan is on sale yet: nothing is charged until a feature works and its terms are published."), "Plans" (five cards, "Prices in euros, excluding VAT."), "On request" (three cards), "Questions" (four: Is anything charged now? What stays free? Do the prices include VAT? How do I get access?). Reuses ContentPage, PageSection, AutoGrid, Card, Tag, Faq, buttonVariants; no new component. The "Choose" buttons are plain `<a>` (not a prefetched Link), since `/signup` does not exist yet. |
| Buttons | Pro, Team, Consultant: "Choose Pro, monthly" (primary) and "Choose Pro, yearly" (secondary); Founding customer: "Choose Founding customer" (yearly only). Free: none. |
| SEO | Title "Pricing: Free, Pro, Team and Consultant plans", description "Browsing stays free. Pro, Team, Consultant and Founding customer plans in euros, excluding VAT; none is on sale yet and nothing is charged." Still `noindex` and not in the sitemap: nothing is on sale (the sitemap's comment, "pricing is not announced", stays true). |
| Setting | `web/.env.example`: `NEXT_PUBLIC_BILLING_OPEN=` (empty) with a note. |
| Menu / footer | Unchanged: /pricing stays in the footer's About group and is not in the header (`lib/wp86.check.ts`, `e2e/wp86.spec.ts` still assert it). |

## What is live today, and the "coming" labels

Checked in the code: the account, saved searches and e-mail alerts are built (`app/(app)`, `/alerts`), but sign-in is closed until an
e-mail provider exists (`/alerts`: "Saved searches and e-mail alerts are built; sign-in is not open yet"). So everything that needs an
account is "coming". Live without an account: the lists (tenders, funding, buyers, companies), /changes (last 14 days), the Atom feeds
(changes, digest, funding, regulation), the calendar feeds (`/calendar.ics`, `/funding.ics`), the CSV export of the lists, the readiness
check (answers in the browser). That is exactly the Free card; it has no "coming" label.

"Coming": Saved searches, E-mail alerts, Export of the eligibility check, Shared workspace, Consortium gap analysis (the paid feature;
the public /networks/consortium-gaps page stays free and is not listed as a plan feature), Supplier-map export, Up to 15 client profiles,
Branded PDF reports, Access for members (up to 50 companies), A co-branded digest, White-label, API (offered only here).
Not labelled: seat counts ("1 user", "Up to 5 users": limits of a plan, not features), "Everything in Pro", "A direct line to the
founder", the Call & Consortium Brief (a one-off piece of work, not a software feature) and "Data licence" (a contract).

## Tests

New:
- `web/lib/wp122.check.ts`: ids, names and exact prices of the five plans; the three on-request items and prices; Free has nothing coming;
  the exact list of "coming" features; `signupHref`; `BILLING_OPEN` follows the setting.
- `web/e2e/wp122.spec.ts`: lead; five plans with exact monthly and yearly prices; on-request items with "On request, opens soon" and no
  link; "Coming" only on the list above, none on Free (and Free lists exactly its five items); billing off: no `/signup` or `mailto:`
  link, "Opens soon" on each paid plan, FAQ answer; billing on: each paid plan's buttons link to `/signup?plan=<id>&billing=<period>`
  with the right names, none on Free; 375 px: no sideways scroll, one column, no card wider than itself; light and dark theme: page and
  card colours, card hover rule (a plan card is not a link: hover changes neither surface nor edge and underlines nothing; with billing on
  the button does not underline on its own hover and shows its focus ring). The off and on tests each skip themselves on a build of the
  other setting.

Moved to the new contract (never weakened; each still checks what its test name promises):

| Spec | Old assertion | New assertion | Why |
|---|---|---|---|
| `e2e/wp46.spec.ts` "/pricing is one table ..." -> "/pricing is one list of the five plans, and /pack one block" | table "What is offered and what it costs" has 7 rows; the Browsing row says Free | the Plans list has 5 cards; the first is Free at €0 | the owner replaced the table with plans |
| `e2e/wp63.spec.ts` "/pricing says the site is free and lists only what exists ..." -> "... browsing stays free and the Free plan lists only what exists ..." | lead "DefenceGate is free to use."; five Free rows; "Account and e-mail alerts" row "Not open yet"; no placeholder words | lead "Browsing stays free, and no paid plan is on sale yet"; the Free card holds the same five things and no "coming"; E-mail alerts carries "Coming"; same placeholder check | "no paid plan" is no longer the owner's text; the honest-status check moved from "Not open yet" to "Coming" |
| `e2e/wp73.spec.ts` "/pricing fits a phone without scrolling sideways" | the table's scroll region fits; alerts row "Not open yet" | each of the five cards fits (scrollWidth <= clientWidth) on top of the page check of `visit`; E-mail alerts "Coming" | there is no table region any more; stricter (every card instead of one box) |

## Runs (D:\DEFENCEGATE TESTS\wp122, CI env: DG_USE_MOCK=1, NEXT_PUBLIC_DG_NOW, NEXT_PUBLIC_SITE_URL=https://ci.example.test, TZ=UTC)

- `tsc --noEmit`: exit 0. `node scripts/run-checks.mjs` (every lib check, `wp122.check.ts` included): exit 0.
- Billing off (default; holding `web-build.lock`): `next build` exit 0 (54 s); Playwright `wp122`, `wp46`, `wp63`, `wp73`, `wp86`
  (desktop and mobile-375): **69 passed, 13 skipped, 0 failed**. Skips: the two billing-on tests of wp122 and the viewport skips the
  other specs declare themselves.
- Billing on (`NEXT_PUBLIC_BILLING_OPEN=1`, test copy only): `next build` exit 0 (48 s); Playwright `wp122`: **14 passed, 2 skipped**
  (the billing-off test at both widths), 0 failed.

## Terms and privacy sentences that the page now touches (not edited; for the owner)

Terms of use (`web/app/(public)/terms/page.tsx`):
1. Term on changes: "Paid features, if introduced, will be announced with their own terms before they are offered." The page now
   announces paid plans and their prices without their terms. It does not offer them (nothing can be chosen while billing is off), so this
   holds today, but the plan terms must exist before `NEXT_PUBLIC_BILLING_OPEN` is turned on.
2. Liability term: "The service is provided free of charge unless we state otherwise." The pricing page now states otherwise for the paid
   plans; consistent in law-of-the-text, but the owner may want the terms to point to /pricing.
3. Same term: "our total liability to you ... is limited to EUR 100 for free use and, if a paid tier is ever offered, for paid use to the
   fees you paid ..." "if a paid tier is ever offered" reads as if none is planned; the page lists four.

Privacy notice (`web/app/(public)/privacy/page.tsx`, version 1.6): nothing in it contradicts the page today (no payment data is collected).
Before billing opens it needs: the merchant-of-record provider as a recipient, what it processes (name, e-mail, billing address, payment
data, VAT ID), legal basis (contract, Art. 6(1)(b); tax records, Art. 6(1)(c)) and retention of invoices; and sign-up by password (version
1.6 describes only the one-time sign-in link: "your e-mail address with the one-time link", section on accounts).

Product copy outside this package (not edited, other packages' files):
- `/pack` lead: "A pack of the open tenders and funding calls that fit one company, assembled for you, is not offered." The new "Call &
  Consortium Brief" (on request) is a different, one-off product for one call; no contradiction, but the owner may want the two linked.
- `/alerts` and the FAQ "Do I need an account?" still describe sign-in by one-time link; the accounts package changes that.

## Open items

- `infra/build-web.sh` passes only `NEXT_PUBLIC_SITE_URL` into the build container; turning billing on needs
  `-e NEXT_PUBLIC_BILLING_OPEN=1` there (the setting is read at build time). Not changed (web-only package; nothing to turn on yet).
- `/signup` does not exist (accounts package). Until it does, billing must stay off or the buttons lead to a 404.
- When billing opens, the lead and "Is anything charged now?" (both say nothing is on sale) must change with it; and the "coming" labels
  of account features must go as each feature goes live (`web/lib/pricing.ts`, one flag per feature).
- /pricing stays `noindex`; remove it (and add /pricing to `app/sitemaps/[name]/route.ts`) when the owner wants the prices found.
