# Open items for a lawyer and for engineering (Terms v2.0, Privacy v1.3)

Written 14 October 2026 when Terms v2.0 and Privacy v1.3 were applied to the site
(`web/app/(public)/terms/page.tsx`, `privacy/page.tsx`). The source draft is
`docs/legal/TERMS_PROPOSAL_2026-10-14.md` (clause Basis lines) and the analysis
`docs/verification/round2/legal-benchmark.md`. Both pages are `noindex` and out of the sitemap
until the Imprint is filled in. Nothing here is legal advice.

## For a lawyer (clause numbers are Terms v2.0 unless marked P = Privacy v1.3)

| Clause | Item |
|---|---|
| 1, 14 | Acceptance by use ("browse-wrap") and by signing in: is it enough evidence in the seat's law? |
| 2 | B2B-only statement and refusal of consumers: workable for an open site? |
| 3 | Describing the service as an information service and compilation, with no hosting or conduit safe-harbour claim (DSA / e-Commerce Directive). |
| 5, 12 | Source data / DefenceGate data split and the database-right claim limited to our compilation (Directive 96/9/EC; consistency with CC BY 4.0 and Directive 2019/1024 Art. 1(6)). |
| 9 | Export control, sanctions and technical-data wording. |
| 11 | Per-source licence and attribution statements on `/data` are the operator's to verify (report O10). |
| 13 | AI/ML-use term and the automated-access term; whether a contractual penalty is wanted (not included). |
| 17 | EUR 100 cap, the 90-day notification period and the 12-month long stop (were `[LAWYER]` markers); validity of the cap and of the periods in the seat's law. |
| 18 | Business-user indemnity: enforceability. |
| 19 | Time limits given: "without undue delay" and one month for data protection requests; no fixed working-day figures were promised. |
| 23 | Governing law and courts: arbitration is a choice not taken. Depends on the seat in the Imprint. |
| P1 | Representative in the Union (GDPR Art. 27) and DPO: needed or not, once the seat is known. |
| P2 (section 2) | Maximum log retention. 14 days implemented 15 Oct 2026 and stated in Privacy 1.4; confirm the figure is acceptable. |
| P3 (section 7) | Legitimate-interest assessment (Art. 6(1)(f)) is not written down; the page states the interest but does not say an assessment is on file. Art. 14(5)(b) reliance. Period for older records in the archive and raw store (the page gives criteria, no number). |
| P4 (section 8) | Transfer mechanism for Cloudflare DNS (adequacy or SCCs) is not stated on the page. Mail provider still to be named. |
| P5 (section 9) | Refusal grounds, one-month rule and up to two months extension as written. |
| P6 | Records of processing (Art. 30): the draft's sentence was left out because no record beyond `docs/DATA_PROTECTION.md` is claimed; add once one exists. Supervisory authority of the seat: named in the Imprint once it exists. |
| Imprint | Whole provider block (name, form, address, register, VAT, contact, privacy contact). The site says "the operator identified in the imprint" everywhere; the imprint page is unchanged and empty. |
| 22 | "Earlier versions kept and available on request": v1.0 to v1.2 texts are in git history; confirm the owner will keep them. |

## Engineering follow-up (promised by neither page as a technical fact; listed so the text can later be tightened)

**Status 15 October 2026 (branch wp-wp11, owner approval of the same day).** Items 1, 2, 3, 5 (as the
request log, not the public count) and 6 are built; 4 is not. Details: `docs/DATA_PROTECTION.md`.

- 1 done: table `suppression`, owner CLI `python -m dgate.ops.suppress`, every public read honours it,
  410 "removed on request" at the detail address, a re-ingest cannot clear it. Terms 19 and
  Privacy 7/9 may now say "at once" once the lawyer agrees; the page texts were not changed.
- 2 done: tick on the sign-in form, `terms_version`, `privacy_version`, `accepted_at` on `app_user`,
  asked again when the constants in `accounts.py` change (sign-in stays closed until a mail relay).
- 3 done: 14 days for the proxy's request log (`logprune`), API access line off; Privacy 1.4 states it.
- 4 not done: no ticketing; the request log `data_request` records dates only.
- 6 done: `docs/legal/versions/` (Terms 2.0, Privacy 1.3 and 1.4; earlier ones only in git history).

1. **Suppression of a notice, label or link from the public site and public endpoints.** None
   exists. A serving-column edit is overwritten by the next collection and `opportunity_version`
   is append-only (break-glass redaction in `docs/RUNBOOK.md`, "Data subject requests", is by
   hand). Terms 19 and Privacy 7/9 therefore say "remove or correct without undue delay after
   verifying the request". A durable `suppressed` flag honoured by `/v1` and the site, plus a
   worker rule that does not re-publish it, would allow the draft's "at once".
2. **Record of acceptance.** Draft term 14 said a tick and a stored version and time. Neither
   exists (`web/components/account/signin-form.tsx` shows a sentence). The page says "by signing
   in you confirm that you accept"; adding a tick and `terms_version` / `accepted_at` on
   `app_user` would match the draft.
3. **Log retention.** Implement a 14-day (or the decided) limit for proxy and API access logs;
   then put the figure into Privacy section 2.
4. **Acknowledgement and answer deadlines.** No ticketing exists; the mailbox is the Imprint
   contact. Working-day commitments from the draft were not published.
5. **Public count of archive records still holding contact details** (inventory in
   `docs/DATA_PROTECTION.md`): the draft proposed a figure on the page; the page says "a small
   number" to avoid a number that goes stale.
6. **Terms texts in the repository.** Keep a dated copy of each published version outside git
   history if "available on request" is to be met without engineering.

## German notice service (oeffentlichevergabe.de), source `de_bkms` (added 15 October 2026)

The connector is built and the source is held back (`active = FALSE`, `commercial_ok` NULL):
nothing it collects is served until these are answered. Measurements: `docs/sources/de_national.md`.

1. Under what licence may the notice exports (`/api/notice-exports`: eForms, OCDS, CSV) be reused
   commercially? Datennutzungsgesetz open-data rules, Datenlizenz Deutschland, CC BY, or other? Ask the
   Beschaffungsamt des BMI in writing; the licence text could not be read on the site.
2. Is automated daily download of the day files without registration permitted, and is a historical
   load of every day since 25 October 2023 (about 1,000 requests, one a second) within the terms?
3. Attribution: what wording, and does it apply to derived, unified records and to the API?
4. Personal data in the files (contact names, telephone numbers, e-mail addresses, beneficial owners,
   jury members, natural-person winners): is stripping at ingestion, before the file is landed, enough
   under the GDPR, and may the stripped file be kept in the private raw store?
5. Does the statutory duty to publish put these notices outside database rights (sui generis)?
6. Notices a buyer sent only to a state platform and not to the BKMS: is anything we may use covering
   them? (A coverage question, but it decides what the product may claim.)
