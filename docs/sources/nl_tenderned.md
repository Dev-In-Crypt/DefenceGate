# TenderNed (Netherlands, national procurement platform)

The platform on which Dutch contracting authorities publish procurement notices,
operated by PIANOo for the Ministry of Economic Affairs. Discovered and measured on
10 October 2026. It is a **tender** source: it feeds `opportunity`, not `call`.

| # | Question | Answer |
|---|---|---|
| 1 | Endpoint | `GET https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties` (list) and `.../publicaties/<id>` (detail) |
| 2 | Authentication | None. The portal's own backend, the one its public pages call. |
| 3 | Format | JSON. |
| 4 | Volume | 146,311 publications in total; **22,016 in 2026** to 10 October; 78 a day on average, 2 to 190. |
| 5 | History | From 2012 (335 by the end of that year), 98,498 by the end of 2024 -- the count jumps in 2022 with eForms. |
| 6 | Update frequency | Continuous; fetched daily at 05:55 UTC, the two days before it. |
| 7 | Paging | `page`, `size`. **`size` above 100 is HTTP 400, and page 100 is HTTP 400**: 10,000 rows per query. |
| 8 | Filtering | `publicatieDatumVanaf`, `publicatieDatumTot` (both inclusive), `sluitingsDatumVanaf`, `typeOpdracht`. Free text and buyer name are silently ignored, so the whole day is fetched and filtered locally. |
| 9 | Identifier | `publicatieId`. Each rectification, award and modification is its own publication with its own id. |
| 10 | Defence signal | `publicatiecode` names the form; "defensierichtlijn" is Directive 2009/81/EC (EF06, EF18, EF27, EF31). The detail page's `juridischKaderCode` is `DEF` for the same notices. CPV codes are on the detail page only. |
| 11 | Personal data | Descriptions can carry addresses; swept by `strip_personal_data()` before landing. No contact fields were seen. |
| 12 | Licence | The dataset "Aankondigingen van overheidsopdrachten - TenderNed" is listed on data.overheid.nl under **CC0 1.0**. See the caveat below. |

## What is in it, for a defence supplier

Measured over the 22,016 publications of 2026:

- **Ministerie van Defensie: 435 publications** (430 under that name, 5 under the
  Commando Materieel en IT procurement desk). Supplies 271, services 160, works 4.
- **162 under the defence directive**, of which 144 are Defensie's, 9 the police's, and
  the rest are single notices from the central bank, the tax administration, a water
  company and others. A buyer list alone would have missed 18 of them.
- **23 of Defensie's 435 are national-only** (`europees: false`), so not in TED. The
  other 412 are also published there; TenderNed adds the national detail and the
  below-threshold work, not a second copy of the market.
- Four "Challenge" notices from Defensie (Battle Damage Repair, Universele Trailer,
  Counter-UAS CLASS II, Inkoop Challenge Rantsoenen). They are innovation procurements
  that small suppliers answer, and the nearest thing to a grant on this platform. They
  are procurement and are stored as such.

## What is not in it

**SBIR Defensie.** An earlier note in `national_grants.md` said its calls are published
here. In 2026 one publication mentions SBIR and it is Gemeente Amsterdam's. Dutch defence
innovation schemes are published by RVO and Holland High Tech on their own pages; the
Holland High Tech MKB-Defensie call (EUR 5 million, phase 1 closed 9 January 2026) is one.
They are a page-level collector, not built.

## The four properties that decided the design

**1. The directive is in the list.** One request per day finds every defence-directive
notice; the detail page is needed only for CPV codes.

**2. 10,000 rows is the ceiling and a year is more than twice that,** so a publication day
is the window. A day whose distinct rows are fewer than the count the API states is an
error, not a smaller day. All 283 days of 2026 reconciled exactly.

**3. The list carries no CPV codes,** and a below-threshold supply of military electronics
under the general directive is exactly what a buyer list misses. So the detail page is read
for every publication: about 100 requests a day. A publication seen for the first time
whose detail could not be read is landed anyway, marked `detailError`, and makes the run
`partial`. One already archived is **left as it is**: a thin copy would append a version
with its CPV codes emptied, and when the page came back the full record's hash would match
the older version and be skipped, so the loss would have been permanent. (Found by an
independent review, with a test that fails against the earlier code.)

**4. Two counters move without the notice changing:** `aantalDagenTotSluitingsDatum` and
`numberOfDaysBeforeAanmeldenInschrijven` are days to the deadline. Hashed, they would land
every notice again each night and record a change that is not one. They are dropped.

## Status mapping

| Type | Meaning | Status |
|---|---|---|
| AAO | contract notice | open |
| VAK | prior information notice | open |
| MAC | market consultation | open |
| REC | rectification | open |
| AGO | award notice | awarded |
| AAW | modification of a contract | awarded |
| VBE | early termination | cancelled |
| anything else | | unknown |

Deadlines are Amsterdam time with no zone, converted to UTC.

## Caveats the owner should read

**The endpoint is the portal's own, not the documented API.** The documented XML API needs
a user name and password requested from TenderNed's functional management, and it is
`functioneelbeheer@tenderned.nl` that grants them. The JSON used here is what the public
pages call, and it answered anonymously. The *data* is CC0 as listed on data.overheid.nl;
what is not written down anywhere found is a statement that this *endpoint* may be used
for automated collection. If that matters, the owner can ask TenderNed, and the source can
move to the documented API with the same mapping. An assistant must not request those
credentials.

**The same notice is stored twice.** 412 of Defensie's 435 publications in 2026 are also
in TED, and each becomes its own `opportunity` row, because no source is linked to
another. The same is true of France and Spain against TED. The eForms notice UUID
(`referentieNummer` on the detail page) may be the key that joins them; that is a guess
and has not been checked against a TED payload. Until a cross-source link exists, counts
across sources double-count the above-threshold notices.

**Not measured.** Whether `publicatieDatum` can be earlier than the day a notice appears
in the list (a publication lag would leave a gap outside the three-day window), and
whether the seven publication types seen in 2026 are all the types there are (an unmapped
one is stored as `unknown`). Free text in descriptions is swept for e-mail addresses and not
for telephone numbers; no contact field was found in 120 detail pages sampled.

**The value of a contract is not mapped.** Neither level carries a value field; the
description sometimes says "circa EUR ..." in prose. `value_amount` is empty rather than
parsed from a sentence.

## Not done

- A 2026 backfill. The loader is registered (`history --source nl_tenderned`) and is
  resumable; it costs about 22,000 list rows and 22,000 detail requests, and has not been
  run.
- The Dutch grant schemes: Holland High Tech MKB-Defensie, SBIR via RVO.
- Other buyers than Defensie in the curated list (police, Rijkswaterstaat, Kustwacht):
  the directive notices from them are caught by the legal basis, the others are not.

## Correction of 12 October 2026 (data-quality audit, findings F13 and F14)

Measured on the 22,092 publications landed up to 12 October 2026. Seven publication
types are all there are (AGO 9,403, AAO 6,569, REC 2,593, MAC 1,326, VAK 922, VBE 741,
AAW 538). **The status table above is superseded** (kept above so the error stays
visible): VAK and MAC were mapped `open`, which made 62 of the 107 effective-open Dutch
rows prior-information notices and consultations, not tenders.

| Type | Meaning | Status now |
|---|---|---|
| AAO | contract notice | open |
| VAK | prior information, alone (EF04-EF08, EFE2) or as a call for competition (EF10-EF14) | forthcoming |
| MAC | voluntary preliminary market consultation (EFE1); no `sluitingsDatum` on any of 1,326 | forthcoming |
| REC | rectification; inherits `detail.formType` of what it corrects: competition open, planning and consultation forthcoming, result, dir-awa-pre and cont-modif awarded | by formType; `unknown` without it |
| AGO | award notice (voluntary ex-ante transparency, formType `dir-awa-pre`, included) | awarded |
| AAW | contract modification | awarded |
| VBE | early termination | cancelled |
| anything else | | unknown |

**Legal basis.** `detail.juridischKaderCode` names a Dutch instrument, not a directive:
DEF (162) is the defence act, 2009/81/EC. NAW (19,175), the Aanbestedingswet 2012,
carries the general, utilities and concessions directives and the national
below-threshold regime, so it says nothing alone. With a European publication
(`detail.nationaalOfEuropeesCode` EU, or the list's `europees`) and a form written for
one directive (`publicatiecode.omschrijving`: "algemene richtlijn" 2014/24/EU,
"sectorale richtlijn" 2014/25/EU, "concessierichtlijn" 2014/23/EU) it does, and is
mapped to that CELEX act. ARW2012 (2,325, the works regulation) and AND2012 (429,
"Anders") name no directive and stay empty, as does every national-only publication.
