# WP-3 public copy changes (13 October 2026)

Source: `docs/verification/copy-factcheck.md`. Web only; no data, API or schema change.

## Versions bumped

- Terms: 1.0 (12 Oct) to **1.1 (13 Oct)**. Changed: term 1 (no longer "no programming interface"), term 3
  (English title), term 11 (CSV export and calendar feed allowed within their limits).
- Privacy: 1.1 (12 Oct) to **1.2 (13 Oct)**. Changed: summary bullets (visit counter keys, contact-field
  exception), section 3 (in-memory limiter). The 13 Oct cookie/HMAC edits were already live under 1.1.

## Where each defect went

| Id | Where |
|---|---|
| H2 | home (meta, hero, benefit, FAQ), methodology "What is versioned", tender page and evidence page, glossary, tenders intro, about |
| H3 | home benefit "Tenders and funding side by side" |
| H4 | home benefits 1 and 4, FAQ (source, complete), about, methodology limits, `/data` "Known gaps" (dated 13 Oct; update as backfills finish) |
| H5 | `lib/tender-basis.ts` `clearanceView` / `subcontractingView` (tender page, evidence page), chip, glossary (NDA, security clearance) |
| H6 | methodology, glossary "Dual-use", funding Regime filter hint |
| H7 | methodology (classification, linking, buyers) |
| H8 | funding chips and Programme filter (EDF and EDIP together), glossary, meta |
| H9 | `meta.updatedAt` (`listUpdatedAt`) on `/tenders` and `/funding`; hidden when absent; run times renamed "Last collection run" (home, footer) |
| H10 | alerts page, `AlertsLine`, dashboard and following text, cadence label "Within the hour" |
| H11 | terms 1, 3, 11; sign-in form states business use and links terms and privacy |
| M1, M2 | about, methodology, privacy summary |
| M3 | `/data` labels (kept 3 days; said plainly) |
| M4 | tenders say "Last changed in our archive" (cards, badge, evidence); tender CSV column renamed `archive_changed_at_utc` |
| M5 | market page and buyer profile (amendment share counted from first sighting; demotion stated) |
| M6 | home "Browse current tenders" |
| L1 | save-search limit message says 10 |
| L2 | privacy bullet and section 3, version |
| L3 | glossary status words |
| L4 | "Not stated" to "Not available" for procedure, value, legal basis, country, published (tender pages, amounts) |
| L5 | home audience text no longer promises following |
| L6 | methodology and terms 3 |

## Not changed (owner)

- H1: imprint fields, controller, retention period and mail provider placeholders stay; sentences that point
  to the imprint (home FAQ "How do I report an error", about, terms 1 and 17, privacy 1, 7, 9) stay.
- Privacy section 8 "server located in Finland, backup storage in the European Union": unverified; owner to
  confirm in the Hetzner console.
- Terms 10, 11, 15, 16, 20 are legal text for the lawyer.

## If the API changes

- If `source.retrievedAt` of a tender becomes the time of our last fetch, revert the "Last changed in our
  archive" labels and the CSV column name.
- If `EDF-EDIP-*` calls are mapped to programme `EDIP`, restore the EDIP chip and Programme checkbox.
- `lib/ui.check.ts`: the chip expectation changed from "Security clearance mentioned" to
  "Security-clearance field present" on purpose (H5); new checks pin `clearanceView`, `subcontractingView`
  and `listUpdatedAt`.
