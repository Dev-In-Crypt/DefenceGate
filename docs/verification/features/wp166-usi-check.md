# WP-166 item 3: the Ukraine Support Instrument (USI) calls in our data, checked against the official sources

Read-only check, 31 October 2026 (15:15 to 15:35 UTC). Our data: production `call` and `call_change` rows, read with
`SET default_transaction_read_only = on; SET statement_timeout = '30s'` through the postgres container (four SELECTs). Official
sources: the Funding & Tenders Portal topic records (`/opportunities/data/topicDetails/<topic>.json`, the JSON behind the public
topic page; `ec.europa.eu/robots.txt` does not disallow the path; no login), the two call documents (PDF) the topics link, and the
DG DEFIS news page of 16 October 2026. No code or data was changed for this item: no flag or quote is wrong because of our reader.

## The two USI calls

| # | Claim | Our data (production) | Official source | Match |
|---|---|---|---|---|
| 1 | The first USI call is in our data | Call 118, topic `EDF-EDIP-USI-2026-LS-IRA-MAB`, call `EDF-EDIP-USI-2026-LS-IRA`, title "Missiles, ammunition and bombs", source `eu_portal`, first seen 24 Sep 2026, last seen 31 Oct 2026 | Portal topic record: same identifier and title; call title "1st call for proposals for industrial reinforcement actions under the Ukraine Support Instrument" | yes |
| 2 | Owner's research: the first USI call **closed on 13 October 2026** | Deadline `2026-11-10 22:59:59+00` (the end of 10 November in Brussels: the portal states the day, no hour), status `open` | Call document V1.0 of 18 May 2026, section 4: deadline 13 October 2026, 17:00 CET. Portal topic record, latest information of 30 Sep 2026: "The deadline for this call has been extended from 13 October to 10 November"; the record's deadline is 10 November 2026 | **our data yes, the research no**: the call is open until 10 November 2026. (Two EDIP procurement calls, `EDF-EDIP-P-2026-FNLC-CPA-AMEW` and `-CDS`, did close on 13 October 2026 15:00 UTC; the research may have taken that date.) |
| 3 | The hour of the first call's deadline | Stored as the end of the day in Brussels, the reader's rule for a day without an hour (`eu_portal.closing`) | The extension notice names no hour; the document's 17:00 CET is for 13 October. `eu_portal.document_closing` adds a document time only for the same day, so it rightly adds none | yes (no hour claimed) |
| 4 | The first call's budget | `budget` 180,000,000 (EUR) | Portal `budgetYearMap` 2026: 180,000,000. Call document section 3: "estimated available call budget is EUR 184 500 000", footnote "including EUR 180 000 000 from voted EU budget" | **partial**: we show the portal's figure, the voted EU budget, not the document's total of EUR 184.5 million. Not a reader error (the portal states 180,000,000); a data or copy decision for the owner |
| 5 | The first call is open to Ukrainian participants | `open_to_ukraine` true, reason `call_document`, quote: "be established in one of the eligible countries, i.e.: − EU Member States (including overseas countries and territories (OCTs)) − non-EU countries: − Ukraine" | Call document section 6, word for word; it goes on: "Legal entities established in the non-government controlled areas of Ukraine are not eligible for funding" (our eligibility check applies that rule, WP-99) and "Consortia must have at least one legal entity which is established and has its executive management structures in Ukraine" | yes |
| 6 | The second USI call is in our data, deadline **16 February 2027** | Call 113, topic `EDF-EDIP-USI-2027-LS-IRA-CUXS`, title "Unmanned systems and counter-unmanned systems", deadline `2027-02-16 16:00:00+00` (17:00 CET), status `open`; no deadline change recorded (`call_change` empty for 113 and 118) | Portal record: deadline 16 February 2027, call title "2nd call for proposals ... under the Ukraine Support Instrument". Call document section 4: "16 February 2027 - 17:00:00 CET (Brussels)" | yes |
| 7 | The second call's budget | `budget` 80,000,000 (EUR) | Portal `budgetYearMap` 2027: 80,000,000. Call document: "EUR 82 000 000", "including EUR 80 000 000 from voted EU budget", and "subject to the final adoption of the budget 2027" | **partial**, as row 4 |
| 8 | The second call is open to Ukrainian participants | `open_to_ukraine` true, reason `call_document`, the same quote as row 5 | Call document section 6: the same list (Member States, Ukraine) | yes |

## Other claims of the research we might show

| # | Claim | Our data / site | Official source | Match |
|---|---|---|---|---|
| 9 | Ukraine's association with the EDF is **in force since 16 October 2026** | 28 EDF calls (all closed) carry `open_to_ukraine_reason = edf_association_unconfirmed`. The site says the EDF answer for Ukraine is "conditional on the association agreement, not confirmed" and "we have found no official text that says it is in force": `web/lib/ukraine.ts` (`ukraineSentence`), `web/lib/glossary.ts` (open to Ukraine), the readiness EDF card and the regulation tracker entry (backend seeds; mock copies in `web/lib/mock/regulation.json`, `requirements.json`) | DG DEFIS news, 16 October 2026 (updated 18 October): "The Ukrainian association with the European Defence Fund (EDF) and financing under the European Defence Industry Programme (EDIP) agreements have come into force." Signed 13 July 2026, ratified by the Verkhovna Rada (16 September 2026, per the same source) | **no: our wording is out of date.** Not a reader error, so not changed here (the rule and its copy live in the backend seeds, the readiness rules and four web files; another package). No open EDF call is affected today (open EDF/EDIP calls: 2 USI calls flagged open to Ukraine, 7 EDIP calls under the programme rule) |
| 10 | USI budget figures | Not shown anywhere on the site (no instrument total in code, seeds or copy); only each call's budget (rows 4 and 7) | DG DEFIS news, 16 October 2026: the USI is "around €300 million", of which "€260 million" for expanding and modernising production and "€35.3 million" for innovation | nothing to correct; if the owner wants the instrument total on the site, quote this page |

## What follows

- Row 9 needs a follow-up package (owner decision): update the EDF Ukraine rule and its sentence (`edf_association_unconfirmed`) to the
  Commission's statement of 16 October 2026, in the regulation tracker, the readiness EDF card, `lib/ukraine.ts`, the glossary and the
  requirement seeds, and decide how the 28 closed EDF calls are flagged (their call documents said participation was pending).
- Rows 4 and 7: decide whether a call's budget is the portal's figure (voted EU budget, today) or the call document's total.
- No ops module is needed: no data fix follows from this check.

Sources: Funding & Tenders Portal topic records `EDF-EDIP-USI-2026-LS-IRA-MAB` and `EDF-EDIP-USI-2027-LS-IRA-CUXS`; call documents
`call-fiche_edf-edip-usi-2026-ls-ira_en.pdf` (V1.0, 18.05.2026) and `call-fiche_edf-edip-usi-2027-ls-ira_en.pdf`; DG DEFIS,
"Ukraine's association with the European Defence Fund and European Defence Industry Programme funding entered into force",
16 October 2026, defence-industry-space.ec.europa.eu.
