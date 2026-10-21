# Germany: Datenservice Oeffentlicher Einkauf (oeffentlichevergabe.de)

Discovery on 15 October 2026 by direct observation (about 20 requests, one a second, small
samples only). Operator: Beschaffungsamt des BMI (BeschA), national Bekanntmachungsservice
(BKMS) inside the Datenservice Oeffentlicher Einkauf. It receives the notices that German
buyers (Bund, Laender, municipalities) must publish, EU-threshold and below.

| # | Question | Answer |
|---|---|---|
| 1 | Endpoint | `GET https://oeffentlichevergabe.de/api/notice-exports?pubDay=YYYY-MM-DD&format=eforms.zip` (one publication day per file). Swagger UI at `/documentation/swagger-ui/opendata/index.html` (JavaScript, not readable without a browser). |
| 2 | Authentication | None. Anonymous GET, HTTP 200. |
| 3 | Formats | `eforms.zip` (one eForms UBL XML per notice), `ocds.zip`, `ocds2.zip`, `csv.zip` (notice.csv, lot.csv, organisation.csv...). The `format` value is also the `Accept` media type (`application/vnd.bekanntmachungsservice.eforms.zip+zip`); `ocds.json` returns 406. |
| 4 | Volume | 14 Oct 2026 (Wednesday): 732 XML files, 4.2 MB zip (27 MB unpacked). Sunday 11 Oct: 506 files, 3.2 MB. 12 Mar 2025: 1,355 files, 4.8 MB. A day is one request. |
| 5 | History | Day files answer back to at least 3 April 2023 (402 files, 4.6 MB) and 25-26 Oct 2023 (499 and 663). Before 25 Oct 2023 the content is not eForms (not examined). Full depth not measured. |
| 6 | Update | Day files are regenerated: the file for 14 Oct held notices dated 11-14 Oct (late arrivals, new versions); `Cache-Control: max-age=120`. Fetch the last three days nightly. |
| 7 | Rate limit | None stated, none observed at one request a second. |
| 8 | Identifier | `cbc:ID schemeName="notice-id"` (UUID) plus `cbc:VersionID` (`01`, `02`...); file name is `<uuid>-<version>.xml`. `cbc:ContractFolderID` is the procedure id. |
| 9 | Licence | **Not found stated.** Open-data interface confirmed; the licence text could not be read (single-page app, no static terms found, no `robots.txt`: HTTP 404). See legal questions. |
| 10 | Personal data | Yes: `cac:Contact` has a name, e-mail, telephone. Strip at `strip_personal_data()` before landing. |

## Sample (trimmed, contacts removed)

```xml
<ContractNotice xmlns="urn:oasis:names:specification:ubl:schema:xsd:ContractNotice-2" ...>
  <efac:NoticeSubType><cbc:SubTypeCode listName="notice-subtype">18</cbc:SubTypeCode>...
  <cac:PartyName><cbc:Name languageID="DEU">Bundesamt fuer Ausruestung, Informationstechnik
     und Nutzung der Bundeswehr</cbc:Name></cac:PartyName>
  <cbc:ID schemeName="notice-id">129f4d26-440e-4017-91b5-df3a10cf3f30</cbc:ID>
  <cbc:ContractFolderID>d8e98b07-ad6e-4f35-92c6-0760efbc6039</cbc:ContractFolderID>
  <cbc:IssueDate>2026-10-13+02:00</cbc:IssueDate>
  <cbc:VersionID>01</cbc:VersionID>
  <cbc:RegulatoryDomain>32009L0081</cbc:RegulatoryDomain>
  <cbc:NoticeTypeCode listName="competition">cn-standard</cbc:NoticeTypeCode>
  <cbc:ActivityTypeCode listName="authority-activity">defence</cbc:ActivityTypeCode>
  <cbc:ProcedureCode listName="procurement-procedure-type">restricted</cbc:ProcedureCode>
  <cbc:ItemClassificationCode listName="cpv">80000000</cbc:ItemClassificationCode>
  <cbc:EndDate>2026-10-26+01:00</cbc:EndDate>   <!-- tender deadline -->
```

## Mapping to `Opportunity`

This is standard eForms, the same schema as TED, so the TED mapper's field paths apply.

| Our field | eForms |
|---|---|
| source id | `notice-id` + `-` + VersionID (identity: notice-id; version: suffix, as `pl_ezam`) |
| title / description | `cbc:Title`, `cbc:Description` of the procedure/lot |
| buyer | `efac:Organization` -> `cac:PartyName` of the buyer referenced by `ContractingParty` |
| legal basis | `cbc:RegulatoryDomain`: 32014L0024 (571 of 732), 32014L0025 (89), **32009L0081 (12 here)**, 32014L0023, and national `de-vob`, `de-uvgo` (46 below-threshold) |
| notice type / status | `NoticeTypeCode`: cn-* open, pin-* forthcoming, can-*/veat awarded, can-modif awarded (modification) |
| CPV | `ItemClassificationCode listName="cpv"` |
| deadline | `cac:TenderSubmissionDeadlinePeriod/cbc:EndDate` (+EndTime) |
| authority activity | `ActivityTypeCode authority-activity` (`defence`) |

Types seen on 14 Oct: cn-standard 385, can-standard 259, can-modif 61, veat 5, cn-social 5,
pin-only 4, pin-tran 3, can-social 2, qu-sy 2, others 1 each.

## Defence on the sample day (732 notices)

- 16 (2.2 %) carry directive 2009/81/EC (12) or a CPV 35* code; 14 have authority activity
  `defence`. Expect about 15 to 20 a weekday, roughly 4,000 a year.
- Buyer names seen: BAAINBw (6, one with a "L2.1" desk), BAIUDBw (5), BWI GmbH,
  Bundeswehr-Dienstleistungszentrum Hamburg and Rostock, Bundesministerium der
  Verteidigung, BBR acting for the BMVg. 17 notices name Bundeswehr entities.
- Only the 12 directive notices are strong signals; the rest are services and works
  (the sample notice is CPV 80000000, training). CPV 35 alone: 11 notices, mostly civil
  35110000 fire equipment (the known false positive).

## Duplicates against TED

Above-threshold notices are forwarded to TED, so they exist twice. Link is exact:
TED `notice-identifier` equals the `notice-id` UUID without suffix, and TED
`procedure-identifier` equals `ContractFolderID`. Checked on one notice: TED search
by `procedure-identifier` returned publication 710974-2026 with the same notice id
(search by `uuid-01` returned nothing; use the bare UUID). 188 of 732 files carry
related-notice or procedure references. Below-threshold (`de-vob`, `de-uvgo`, 46 of 732)
are German-only and not in TED. The TED publication number itself is not in the file.

## Not available

- Contract value on many notices (only where the form carries it).
- Platform-only items published on the buyer's own pages: tender documents, Vergabeunterlagen.
- Notices under national thresholds that buyers never send to the BKMS (some Laender
  keep Verwaltungsvorschrift-based "Beschraenkte Ausschreibung" lists on their own platforms).
  Coverage of below-threshold is the open question: only 46 of 732 here.
- Pre-eForms history (before 25 Oct 2023) in a comparable schema; not examined.

## Other channels (not fetched, search and the portal only)

State platforms (vergabe.NRW, Bavaria, Lower Saxony, Berlin), evergabe-online.de, DTVP and
Bund.de feed the same BKMS (that is the purpose of the Datenservice); no separate open
API was verified for any of them. TED's DE slice is already ingested.

## Recommendation

Use **oeffentlichevergabe.de day files, eForms**, as the single German channel. One anonymous
request per day, same schema as TED, below-threshold included, stable version suffix, exact
TED link.

Plan:
1. Connector `de_bkms`: per `pubDay`, download zip (max 20 MB), land each XML raw after
   `strip_personal_data()` (contact block), normalise with the TED eForms mapper plus
   notice-id/version identity.
2. Daily: fetch the last three days (late arrivals); a day with fewer files than 40 % of
   the weekday median is `partial`.
3. History: `history --source de_bkms`, day markers like `pl_ezam`, one request a second,
   from 2023-10-25 (about 1,000 days, 1-5 MB each, under 3 GB total, resumable).
4. Twin linking: store `notice-id` and `ContractFolderID` as external ids; link to TED rows by
   `notice-identifier` and `procedure-identifier`; mark the DE row the national observation.
5. Tests: mapper fixtures for cn-standard, can-modif, de-vob; contact stripping; day with
   duplicate versions; twin link; fire-extinguisher case.

Risks: licence unstated; day-file regeneration changes counts (hash on content);
unmeasured below-threshold completeness; old format before October 2023; the Swagger
documentation was not readable, so undocumented parameters (month export) are untested.

## Questions for the owner's lawyer

1. Under what licence may the notice exports be reused commercially? (Datennutzungsgesetz
   open-data rules, or Datenlizenz Deutschland, or CC BY: ask BeschA in writing.)
2. Is automated daily download of the day files permitted without registration?
3. Attribution wording and whether publishing derived (unified) records needs it.
4. Personal contacts in notices: our stripping at ingestion is sufficient under GDPR?
5. Whether a statutory publication duty makes the data free of database rights (sui generis).

If BeschA declines or the licence is restrictive, the least bad fallback is TED's German
slice (already held, above-threshold only) plus manual entry of below-threshold
Bundeswehr notices from the BAAINBw platform.

## Implementation (branch wp-wp14, 15 October 2026)

Connector `de_bkms` (`backend/dgate/sources/de_bkms.py`), source row seeded by migration
`0050_source_de_bkms.sql`: kind tender, country DE, **`active = FALSE`, `commercial_ok = NULL`**.

What was measured on the day file of 13 October 2026 (1 request, 3.6 MB, 1,035 entries; not
732 as on the 14th):

- Not every entry is current eForms: legacy national forms (`CustomizationID eforms-sdk-0.1`)
  have a numeric id (`25920552-1.xml`), an empty `ContractFolderID`, no organisation block
  (buyer is `ContractingParty/Party/PartyName`) and an unpadded version (`-1`). The mapper
  handles both. 15 buyers in the file carried the defence directive, a CPV 35 code or a
  Bundeswehr name.
- The buyer is in `EformsExtension/Organizations/Organization/Company`, matched to
  `ContractingParty/Party/PartyIdentification/ID`. `cac:Contact` appears on 1,377
  organisations (telephone 1,335, e-mail 1,368, telefax 650), on `ServiceProviderParty`
  and on `UltimateBeneficialOwner` (26 files); `TechnicalCommitteePerson` (6) holds family names.
- 20 files carry `efac:Publication` with `NoticePublicationID schemeName="ojs-notice-id"`. In
  the ones read the value was the placeholder `00000000-1900`, which is not a TED number and is
  ignored (`canonical_ted_ref` accepts only `<n>-20YY`). Where it is a real number it fills `ted_ref`.
- The zip order is not name order; the connector sorts, so versions of a notice arrive in order.
- Largest entry 0.69 MB; unpacked day about 27 MB.

### Pipeline

| Step | Rule |
|---|---|
| Fetch | `open_day`: stream to a temporary file (ceiling 64 MiB), entries read one at a time (ceiling 8 MiB each, 400 MiB unpacked, 20,000 entries), a document type declaration refuses the entry. Not `new_client`: its body hook buffers whole bodies in memory. |
| Land | the record `{file, notice_id, version, xml}` after `strip_personal_data`, which for this shape calls `strip_eforms_xml`: drops `Contact`, `ElectronicMail`, `Telephone`, `Telefax`, `UltimateBeneficialOwner`, `TechnicalCommitteePerson`, person-name elements, `ResidenceAddress`; an organisation with `NaturalPersonIndicator` true keeps only its identifier; e-mail addresses in prose are replaced; a file that cannot be scrubbed is landed with `xml` null. |
| Map | the XML is read into TED's field names and `from_ted` is the mapper (status, value rules, deadline, lots). Own: identity `native_id` = notice id (so version `02` is a new version of the same row), `notice_version` from `VersionID`, `procedure_identifier` = `ContractFolderID` lower-cased, `ted_ref` from `ojs-notice-id` when real, `source_url` = the notice's procurement-documents address (BT-15, `CallForTendersDocumentReference/Attachment/ExternalReference/URI`): the notice on the buyer's own platform (evergabe-online.de, vergabe.niedersachsen.de, vergabeplattform.bwi.de, meinauftrag.rib.de ...), about 68 % of stored notices (272 of 400 read on 21 Oct 2026, WP-72); empty where the notice states none. The day files name no page on oeffentlichevergabe.de itself, so no URL is built from the notice id (an unverified scheme would be a guess). |
| Classify | the existing classifier. German buyers in the sample (BAAINBw, BAIUDBw, BWI GmbH, BwDLZ, Bw Bekleidungsmanagement, HIL, Marinearsenal) were already recognised by `buyer_vocab`; one pattern added (`Branddirektion`, fire department). Authority activity `defence` is not a signal (the classifier has no input for it). |
| Twin | `procedure_identifier` equals TED's `procedure-identifier`: the existing nightly `link_twins` sets `ted_ref`, `twin_method = procedure_id`, confidence 0.98. Exact, not a heuristic. Below-threshold notices (`de-vob`, `de-uvgo`) have no TED twin. |
| Daily | `pipeline de-bkms`, worker job `de_bkms_daily` 06:05 UTC: the last three publication days, oldest first, idempotent (hash). Nothing is done while the source is inactive; `--force` for a manual run. |
| Count check | per day: files in the zip vs payloads landed; unreadable files; a past day under 290 files (40% of the weekday median). Any of them makes the run `partial` with the days named. The run-level floor (400) is `DGATE_FLOOR_DE_BKMS`. |
| History | `pipeline history --source de_bkms --from 2023-10-25 --to D --force`, day markers as pl_ezam; an earlier date is refused (not eForms). |

### Holding it back until the licence is clear

`source.active = FALSE` has three effects, all tested: the scheduled job does nothing; a
manual run or history needs `--force`; and every row written for the source has
`opportunity.suppressed = TRUE`, computed by the database trigger (so the worker, replays
and ops tools are covered), which every public read already honours. `/v1/sources` and the
coverage figures list only active sources. Setting `active = TRUE` re-evaluates the source's
rows in the same statement (and `FALSE` withholds them again). A takedown lifted with
`ops/suppress` does not release a row of an inactive source.

To switch on after the lawyer's answer, as the database owner:

```sql
UPDATE source SET active = TRUE, commercial_ok = TRUE,
       licence = '<the licence the lawyer named>', attribution = '<the wording required>'
 WHERE code = 'de_bkms';
```

`link_twins` then runs on its own that night. Volume: about 4,000 defence notices a year in
`opportunity`; the raw store receives every notice (about 730 a weekday, 27 MB unpacked a
day, gzipped bundles).

### Operations (lines for docs/RUNBOOK.md)

| What | Command |
|---|---|
| Manual run while inactive | `python -m dgate.pipeline de-bkms --days 2 --force` |
| History | `python -m dgate.pipeline history --source de_bkms --from 2023-10-25 --to <yesterday> --force` (about 1,000 requests at one a second, 1 to 5 MB each; resumable; exit 75 if the source rate-limits) |
| Is it held back? | `SELECT active, commercial_ok FROM source WHERE code = 'de_bkms'` and `SELECT count(*) FROM opportunity o JOIN source s ON s.id = o.source_id WHERE s.code = 'de_bkms' AND NOT o.suppressed` (0 while inactive) |
| Count check result | `SELECT status, error_message FROM ingest_run r JOIN source s ON s.id = r.source_id WHERE s.code = 'de_bkms' ORDER BY r.id DESC LIMIT 5` |

### Limits

The count check compares what the zip held with what was landed in the same run; it cannot
see a notice the service left out of a regenerated file. Authority activity and BT-801
(non-disclosure agreement) are not read, so `nda_required` stays false. Below-threshold
completeness is unmeasured. The TED publication number is only present on some files.
