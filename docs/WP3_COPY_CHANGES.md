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

## Site QA follow-up (`docs/verification/site-qa.md`, web side)

| QA # | Change |
|---|---|
| 2 | Date-only deadlines read "13 Oct 2026 (date only)" (and "(time not stated)"); no dangling "UTC". `lib/format.ts`. |
| 3 | `lib/cpv.ts` `cpvName`: the code's own title from the CPV finder data first; else the group or division, shown as "Within: ...". Market and buyer tables use `cpvGroupName` (group, else "Construction work (division)"). The dataset holds 366 of 9,454 codes, so codes outside it (79710000) still show their group; no title is invented. |
| 8 | Funding topic tags wrap (`Tag wrap`, `break-words`). |
| 9 | `callStatusKind` takes the opening date: forthcoming with a passed deadline is "Closed", with a passed opening day "Opening date passed" (new `pending` pill). Cards, detail page, calendar. |
| 10 | Call-level budget: card label "Call budget" / "Topic budget"; the amount is shown once per list (`repeatedCallBudgets`), later topics say it is shared. Funding CSV gets a `budget_scope` column (new column, after `currency`). |
| 12 | `displayName` keeps any token with a digit, slash or underscore as published. |
| 13 | Legal basis shown as its name ("other" says so; the code sits beneath); procedures in FR/ES/NL words get an English name with "As stated" beneath (`procedureLabel`, a short table; unknown names are shown as stated). |
| 14 | Amounts of 0, 0.01 and 1 (`isPlaceholderAmount`) read "Not available" on cards and pages, are blank in the CSVs, and a value filter on `/tenders` sends `min` of at least 1.01 so they never match (web side only; the API is not changed). |

Not web, not done here: QA 1, 5, 6 (WP-4), 4 (owner), 11, 15 (done), 16.
`lib/ui.check.ts`: two expectations changed on purpose (date-only text); new checks for items 3, 9, 10, 12, 13, 14.
It runs green under Node 24: `node --experimental-transform-types --import <register-with-ts-resolver> lib/ui.check.ts`.
