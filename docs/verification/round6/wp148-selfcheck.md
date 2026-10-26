# WP-148 self-check: privacy 1.8 published (Cloudflare as processor), 26 October 2026

Branch `wp-wp148` from `integration` 1a1e7c4 ("Cloudflare privacy draft approved"). Feature freeze: only this package.
No production access, no external call. Wording source: `docs/legal/drafts/privacy-cloudflare-draft.md` (owner's approval and
instruction of 26 Oct 2026), its proposed sentences used verbatim; everything else in both pages unchanged.

Files: `web/app/(public)/privacy/page.tsx`, `web/app/(public)/data/sovereignty/page.tsx`, `backend/dgate/accounts.py`,
`docs/legal/versions/privacy-v1.8-2026-10-26.md` (new), `docs/legal/versions/README.md`, `docs/DATA_PROTECTION.md`,
`web/e2e/wp79.spec.ts`, `web/e2e/wp148.spec.ts` (new), `backend/tests/unit/test_wp148.py` (new).

## 1. Privacy page

**Before.** 1.7: "Browsing needs no account and sets no cookie"; section 2 "the server and the reverse proxy in front of it";
section 4 "the site sets no cookies"; section 8 "Cloudflare, Inc. (USA), as the provider of the domain name service only ...
Traffic to the site does not pass through Cloudflare."

**Change.** Lead: "Version 1.8, published 26 October 2026 (Cloudflare as processor for network security and content
delivery)." plus the unchanged rest of the lead. In short: first bullet replaced, new bullet after the access-log bullet.
Section 2: first sentence replaced (rest of the paragraph unchanged), new Cloudflare paragraph after the retention paragraph.
Section 4: first and last sentences replaced (cookie names in the page's `font-mono` span, as the other item names). Section 8:
the Cloudflare item replaced by the approved sentence with the DPF basis, exactly as written. No "(USA)" and no "United
States" in any Cloudflare sentence (the OpenAI item, unchanged, still names the United States). The source comment on the
e-Zamowienia date now also names the 1.8 copy.

**Test.** `test_wp148.py::test_privacy_18_names_cloudflare_as_processor_without_the_united_states` (version, lead, DPF item
verbatim, no USA/United States on any Cloudflare line, old sentences gone); `wp148.spec.ts` first test (rendered text);
`wp79.spec.ts` pins moved 1.7 -> 1.8 and a new `not 'Version 1.7'`.

## 2. Sovereignty page

**Change.** Server row note: "One virtual server. Visitors reach it through Cloudflare's proxy (below)." Cloudflare row: title
"Domain registration, name service (DNS) and the proxy in front of the server", note as drafted; who/where/eu unchanged (the
"where" column still reads "United States company; ...", as the brief says: columns unchanged). Lead and the rest unchanged.
The optional origin-lock sentence is not added (the owner adds it once the lock is on).

**Test.** `test_wp148.py::test_sovereignty_says_visitors_pass_through_cloudflare`; `wp148.spec.ts` second test.

## 3. accounts.py

`PRIVACY_VERSION = "1.8"` (comment: WP-148). `PASSWORD_PRIVACY_VERSION` stays "1.7": `accounts_problem()` only closes accounts
when `PRIVACY_VERSION < PASSWORD_PRIVACY_VERSION`, so it is a lower bound ("the first notice that describes password
accounts"), and 1.8 keeps that text; 1.8 >= 1.7, accounts' gate unchanged. Moving it to 1.8 would change nothing today and
would misstate which version introduced passwords.

Pins: `test_wp140` and `test_accounts*.py` read `accounts.PRIVACY_VERSION`, so they follow; `test_accounts_wp123` sets
1.6/1.7 itself as a scenario (not the published value), unchanged. `web/e2e/support/fake-accounts.mjs` answers
privacyVersion '1.7' with termsVersion '2.0' (already not the published terms 2.2): a self-contained fake whose forms post back
what it served, not a pin of the published text; unchanged. `web/lib/*.check.ts`: only `wp142.check.ts` says "privacy 1.7" in
messages about the archive figures, which 1.8 keeps word for word; unchanged.

## 4. Static copy and README

`privacy-v1.8-2026-10-26.md` made from the 1.7 copy with exactly the page's changes (header says so); README line added.

## 5. DATA_PROTECTION.md

Logs row (WP-147 text kept): the "draft, to be published" reference now points to privacy 1.8 and the new row. New row
"Cloudflare (Cloudflare, Inc.; processor for network security and content delivery ...)" after the mail relay row: what it
sees, its two cookies, purpose, retention its own, DPF basis named in the notice, processing addendum the owner's.

## Tests (copy `D:\DEFENCEGATE TESTS\wp148\`, Postgres `dgate-wp148` on 55548, removed afterwards)

- ruff: clean. Unit: 4099 passed (incl. `test_wp148`, `test_wp140`).
- Integration (own container): `test_accounts.py`, `test_accounts_passwords.py`, `test_accounts_wp123.py`,
  `test_billing_wp124.py`: 143 passed.
- tsc 0; lib checks 0.
- Build 0 (50 s, under `web-build.lock`). e2e `wp148, wp79, wp36, wp45, wp56, wp63, wp131, wp143, layout` (every spec that
  opens /privacy or /data/sovereignty), desktop + mobile-375 + fake-api projects: 123 passed, 21 skipped, 0 failed. The skips
  are the existing `E2E_FAKE_ACCOUNTS` block of wp79 (needs a hand-started https fake-accounts site); its `'Version 1.8'` pin
  (line 57) therefore did not run here.
