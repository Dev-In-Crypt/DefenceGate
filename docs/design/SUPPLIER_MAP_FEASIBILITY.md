# Supplier map from award notices: feasibility (WP-37, 18 October 2026)

The question: **which European companies have already won defence-relevant contracts, where and for how much,
with honest coverage.** The rule the orchestrator set: at least 2,000 unique European suppliers after
de-duplication, or narrow the scope and say so. Every number below was measured on 18 October 2026 (method in
the last section); nothing is quoted from the owner-supplied analysis
(`docs/research/EUROPEAN_AUTONOMY_ANALYSIS_2026-10-18.md`) unless it says "the analysis states".

## Verdict

| | |
|---|---|
| **M2, supplier map** | **GO.** 4,807 unique suppliers (4,666 European) in the core scope for 2023 to 18 October 2026; 2,525 (2,427 European) under the narrowest definition (military CPV only). The rule (2,000) holds under every definition measured |
| What the map really is | the open segment: winners named in TED result notices, effectively from November 2023 (before eForms the API states no winner as data). It is **not** the European defence supply base |
| **M3, US-dependency signals** | **NO-GO.** The wording is too rare to measure (about 40 notices in 3.8 years carry it in fields we could store), precision of the commonest term is 50 %, and German, French and Polish origin wording returns zero hits in all of TED. Details below |
| GLEIF as the identity source | **no, as enrichment only.** 22 of 100 random winners have a LEI by name, 10 by registration number. The 481 MB golden copy was not downloaded |

## 1. What award data do we hold

**Notice types we collect.** The TED queries (`defence_query`, `day_query`, `defence_history_query` in
`dgate/sources/ted.py`) carry no notice-type filter: result notices are collected. In the database, TED rows of
2023 or later whose subtype is a result notice: 31,539 (29: 23,904; 31: 6,855; 33: 339; E4: 166; 30: 78; E6: 75;
E1: 49; 36: 30; 35: 24; E5: 7; E3: 5; E2: 5; 34: 2). TED `notice-type` of those subtypes: 29, 30, 31 and E4 are
`can-standard`; 33, 34, 35 `can-social`; 36, 37 `can-desg` (38 and 39 are `can-modif`, contract modifications: not
used).

**But the winners are not in what we hold.** `TED_FIELDS` asks for no winner field, so neither the `opportunity`
table nor the raw store has a winner name, country, identifier or value per winner. The 22 keys of a raw record read from
the store, and `TED_FIELDS`, show no winner field. Winners have to be asked for from the TED search API by publication number
(`publication-number IN (...)`, 100 per request, anonymous, one request a second).

**What the API states for a result notice** (fields `winner-name`, `organisation-name-tenderer`,
`organisation-country-tenderer`, `organisation-identifier-tenderer`; the others tried are listed under "Traps"):

- name: always, where a winner is stated (30,632 of 30,632 notices that state a winner name);
- country: one entry per organisation in the tenderer block for all 30,632;
- registration number: aligned for 29,069 notices (94.9 %); in the core scope **18.6 % of winner rows have none**
  (2,160 of 11,608);
- value: a notice-level or lot-level value for 28,028 of 30,632 notices (91.5 %), but the API gives flat lists:
  **which winner got which lot or value cannot be read from them.** Where one organisation won the notice (6,487 of
  11,608 core rows, 55.9 %) the notice value is that supplier's; otherwise it is shared and the map states none.
  The exact lot-to-winner mapping is only in the notice XML (about 100 KB each; not fetched);
- lot: lot identifiers exist as lists, not attached to a winner: **an award here is a (notice, organisation) pair.**

**Presence by year** (result notices returned by the defence history query, `can-standard`, `can-social`, `can-desg`
and `veat`; 46,007 notices, 25,385 of them in our database as defence):

| Year of publication | Notices | Naming a winner |
|---|---|---|
| 2023 | 10,894 | 637 (5.8 %) |
| 2024 | 11,795 | 9,468 (80.3 %) |
| 2025 | 12,841 | 11,273 (87.8 %) |
| 2026 to 18 Oct | 10,477 | 9,254 (88.3 %) |

Before eForms became mandatory (25 October 2023) the API gives no winner as data. The map therefore starts in
practice in late 2023, and says so on its page. The notices that name no winner are cancelled or unawarded
procedures, or notices whose result is published elsewhere.

**The trap that nearly cost a quarter of the suppliers' countries.** `winner-name` and `winner-country` are **not**
in the same order in notices with several winners. A legal form against a country (GmbH with DE/AT/CH, Sp. z o.o. with
PL, S.L. with ES, and so on; 1,226 pairs) agrees for 99.0 % of the pairs of `organisation-name-tenderer` ×
`organisation-country-tenderer`, but for only 81 % of `winner-name` × `winner-country` (control, the country list
rotated by one: 63 %). The loader therefore reads the tenderer block and uses `winner-name` only to say which
tenderers won (every winner name is among the tenderers: 30,632 of 30,632; 782 notices, 2.5 %, also list tenderers
that did not win). A first run that zipped the winner fields would have given the wrong country to several hundred
suppliers.

## 2. How many unique suppliers

Method: every result notice of the TED defence history query (2023-01-01 to 2026-10-18) was fetched with the winner
fields (46 monthly windows, about 200 requests, one a second); each winner organisation was read as the loader reads it;
its name was normalised with `dgate.resolution.names.key_of` (the key of WP-26: accents, legal forms, Cyrillic) and
counted once per (country, key); names that state the same national registration number in one country were counted
once ("after id merge"). "European" is the EU 27, EEA, Switzerland, the United Kingdom, Ukraine, Turkey and the
Western Balkans, Moldova. "Core scope" is the site's definition (`classify.CORE_SQL`): defence-qualified and either
the 2009/81/EC legal basis or a military CPV that is not dual-use; the figures below approximate it from the stored
flags (7,747 notices against 7,596 candidates by the exact predicate on production: 2 % more).

| Definition | Winner rows | Unique (country, name) | After id merge | European | EU 27 |
|---|---|---|---|---|---|
| **Core scope, 2023 to 18 Oct 2026** | 11,608 | 5,205 | **4,807** | 4,666 | 4,471 |
| Military CPV only (not dual-use) | 6,391 | 2,710 | 2,525 | 2,427 | 2,309 |
| 2009/81/EC legal basis only | 7,829 | 3,738 | 3,456 | 3,331 | 3,183 |
| Everything the defence query returns, in our database | 41,364 | 14,965 | 13,799 | 13,627 | 13,180 |
| Everything the defence query returns | 65,431 | 19,849 | 18,177 | 17,993 | 17,470 |

By year of publication (core scope, after id merge): 2023: 222 (eForms transition); 2024: 1,761; 2025: 2,266;
2026 to 18 October: 2,228. A single year is at the rule's border; the map is a three-year view.

**The last two rows are not the supplier base.** They include the military hospitals, canteens and clothing that
buyers with "defence" in their name publish. The top suppliers of the unfiltered set are Romanian pharmaceutical
wholesalers. The map uses the core scope only, as the rest of the site does. Even in the core scope the largest
suppliers by number of notices are Romanian suppliers of uniforms, footwear and similar (military CPV, small lots),
then KNDS, Rheinmetall, Tatra Trucks, FFG, Indra: the notice count is a measure of how a buyer slices its lots, not of
size, and the map shows no ranking.

**De-duplication.** Exact normalised name within a country, then the national registration number, took 5,205
(country, name) pairs to 4,807 (−7.6 %). What it does not do, by design: merge a parent with a subsidiary (Thales SA,
Thales Belgium), and spellings of one company that share no number. Those stay as separate organisations, as the
resolution cascade of WP-26 requires; the share of such duplicates was not measured. The loader resolves through that
cascade (`dgate.resolution.resolve`); no second method was written.

**Countries** (core scope, unique (country, name)): DE 908, PL 675, ES 615, FR 506, EE 226, CZ 223, RO 164, SE 146,
HR 136, FI 126, NL 124, IT 115, LV 112, SI 103, BG 94, DK 91, HU 87, GB 84, US 84, BE 81, PT 80, NO 75. US 84 and
IL 29 and CA 16 are winners of European buyers.

## 3. Natural persons (GDPR)

A winner can be a sole trader under their own name, and so can a firm called after its owner. The notice does not say.
The loader (`dgate/awards.py: person_reason`) skips what looks like a person and **never writes it**: not to an
organisation, an alias, an award or the raw store (the landed record is the API's, with those entries blanked in place).
It is a rule on names, because there is nothing else to read, and it is imperfect in both directions. Measured on the
5,997 distinct (name, country) pairs of the core scope:

- skipped: 184 (3.1 %). Of 45 skipped names read by hand, 30 (67 %) were persons or sole proprietorships (Polish
  trading names that end in the owner's name, "Radek Nečas", "Zimmerei Jörg Hoffmann", "e.K." firms) and 15 were
  companies (for example "Sopra Steria", "Northrop Grumman", "FN Herstal"): about 60 legal entities (1 %) are lost for it;
- kept without any legal-form or business word: 667. Of 45 read by hand, 3 were persons or a person's firm
  ("Hanna Dobies" at the end of a Polish trading name, a Polish "JANUSZ KANIA ..." and a French organisation named
  after its owner): about 45 names (0.8 % of the suppliers) are probably still a person. The two fixes that followed the
  reading (Polish given names, a person at the start of a name) were not re-measured on a fresh sample;
- what no rule on names can catch: a sole trader whose name has a company-like word, an all-capital name of one or two
  words, a person registered with a business number.

So the rule is "best effort, measured", not a guarantee; the page links the removal route (`suppression`, kind
organisation) and a person who finds themselves can ask for the removal. See `docs/DATA_PROTECTION.md`.

## 4. The other award sources we hold

| Source | Award rows (defence) | Winners in what we hold | Verdict |
|---|---|---|---|
| `ted` | 31,539 result rows since 2023 | not stored; available from the API (above) | **used** |
| `es_placsp` | 16,802 `award` + 12,941 `formalisation` | **no**: the raw store holds our normalised record (checked on 6 records); the connector reads the feed's entries and keeps no `WinningParty` | would need a connector change and a re-read of the feeds; **not in this step** |
| `fr_boamp` | 11,181 (kind not stored) | yes, `titulaire` as a list of names, **without a number or a country**; 30 of the 56 award notices in a sample of 300 records (54 %) | candidate for the next step: cheap (in the raw store), but names only |
| `pl_ezam` | 43,198 | `contractors` with name, NIP, city, country on 1,409 of 3,160 sampled records (45 %), many entries empty | candidate; has a national number |
| `de_bkms` | 12,667 | in the eForms XML (`Tenderer` ids and organisation blocks); 54 of 213 sampled records are result notices | candidate; needs an XML reader |
| `nl_tenderned` | 474 | no: the listing-level record | no |
| `pl_atlas` | 36,182 | **removed on purpose** by `strip_personal_data` (`contractor_name`, `contractor_national_id`) | no |

## 5. GLEIF as an identity source

`https://goldencopy.gleif.org/api/v2/golden-copies/publishes/lei2/latest` (read 18 October 2026): the Level 1
golden copy holds 3,465,841 records; CSV zip 481.58 MB (JSON 881.68 MB). **Above the 300 MB limit: not downloaded.**
Level 2 relationship records (`rr`): 491,462 records, CSV zip 23.36 MB (not downloaded either: parents are useless
without the LEIs to attach them to).

The LEI search API (`api.gleif.org/api/v1/lei-records`, one request a second) for 100 random core-scope suppliers
(seed 11), by name and country, and by registration number where the notice gave one (78 of 100):

- 35 returned some LEI record; **22 returned one whose normalised name equals ours** (22 %). One of the 22 matched a
  look-alike (a "Dassault Aviation" matched the first hit "MUTUELLE DASSAULT AVIATION BIARRITZ"; the real one was
  among the 8 hits): name matching alone is not safe;
- by registration number (`filter[entity.registeredAs]`): 10 of 78 returned a record, 9 with an agreeing name (13 %).

The companies with a LEI are the larger ones (Rheinmetall, KNDS, Explosia, Esri, Bechtle); small and medium
suppliers, which are most of the map, mostly have none. GLEIF is therefore an **optional enrichment** (parent group of
the big names, through Level 2) and not a way to identify suppliers. Its licence is CC0 according to the analysis and
GLEIF's own pages; we did not re-read the terms, as nothing is built on it.

## 6. M3, "US dependency signals" from tender text

Question: what would the raw store let a text detector do, and how precise is it for FMS, ITAR and "US-origin"?

- **What is stored.** `opportunity.summary_en` is empty for every row; titles are stored. The raw store keeps
  `description-lot` and `description-proc` for the records fetched since the field was added: in the sample of 40,256
  records, 62.6 % have a description, and 85.5 % of the 1,903 defence-like ones (legal basis 2009/81 or CPV 35).
- **What the scan finds.** 3 records match any of ITAR, FMS or an origin phrase in English, German, French or Polish:
  2 FMS, 1 ITAR (0.007 %).
- **What TED itself finds** (full-text search, publications since 1 January 2023, counted 18 October 2026):

| Wording | Notices in all TED | In the defence query | Wording inside title / description fields |
|---|---|---|---|
| "ITAR" | 114 | 56 | 20 of 114 |
| "Foreign Military Sales" | 23 | 23 | 11 of 23 |
| "FMS" | 841 | 101 | 8 of the first 60 read |
| "US origin" / "US-origin" | 11 | 0 | 0 of 11 |
| "American origin" | 2 | 0 | not read |
| DE: "US-Herkunft", "amerikanischer Herkunft", "Herkunft USA" | 0 | 0 | |
| FR: "origine américaine" | 0 | 0 | |
| FR: "origine US" | 11 (the same notices as the English "US origin") | 0 | 0 |
| PL: "pochodzenia USA", "pochodzenia amerykańskiego" | 0 | 0 | |

- **Precision, read by hand** (a hit counts when the notice states a US-origin, ITAR-controlled or FMS-route
  dependency): "ITAR" 10 of 20 (50 %): nine of the other ten are one German export-compliance sentence that lists
  AWV, the EU dual-use regulation, ITAR and EAR in every tender of a federal buyer, and one is a list of types of
  export-controlled goods; "Foreign Military Sales" 11 of 11, but they are about eight procurements (the Danish
  Defence Acquisition and Logistics Organisation, Dutch and Swiss buyers) because a notice and its award notice both
  hit; "FMS" the acronym 1 of 8 (a Swiss air-freight notice "ventes militaires étrangères (FMS)"; the others are
  financial management systems, flight management systems, farm management software, a fire-service radio status,
  a company called Smart FMS).
- **The hand sample of 50 hits per language could not be drawn.** German, French and Polish origin wording has zero
  hits in TED; English origin wording has 11 notices and none in fields we would store. The kill criterion
  (precision below 80 % on 200 hits means no country trends) cannot be tested for lack of hits, and the one term with
  enough hits, ITAR, is at 50 %.
- **Conclusion.** About 40 notices in 3.8 years contain the wording in a field we could store. A country trend from
  that is noise, and the share of US purchases is out of reach anyway: FMS and government-to-government purchases
  mostly bypass TED, as the analysis states. **Not built.** What it would take for a list of "notices that mention ITAR
  or FMS" (not a trend): descriptions stored in the database (a reprocess of the raw store, or TED's full-text search
  at query time), a filter for the German export-compliance sentence, and the long phrase "Foreign Military Sales" in
  place of the acronym. That list would be about 40 notices and would say what each states, not that Europe depends on
  anything.

## 7. Size and cost of building the map

- Candidates on production (TED, core scope, result subtypes, from 2023-01-01, not suppressed): **7,596** notices
  (7,394 since 2024), 550 buyers. At 100 numbers a request that is **76 requests**, about two minutes at one a second.
- Measured by loading those 7,596 notices (a read-only export of production) into a scratch database and running the
  real loader against the live API: **76 requests, 196 s, 9,826 awards, 4,187 supplier organisations (4,178 of them
  new; production has 425,330 organisations: +1.0 %), 223 winners left out as natural persons**. Added size about
  10 MB (the limit given was 500 MB); the raw store gets 76 bundles of person-blanked records, a few megabytes.
  Details: `docs/verification/product/wp37-selfcheck.md`.
- Licence: TED notices are reusable, commercially too, with attribution (Commission Decision 2011/833/EU); the
  attribution line is stored on the source and returned by the API.

## Method, and what was not checked

- All API reads: the TED search API (anonymous, the project's `User-Agent`, one request a second, about 200
  requests in total for the study: about 200 for the winners, about 50 for the full-text counts and samples), the GLEIF
  golden-copy index (2 requests) and the LEI search (about 180 requests). No other site was contacted. No language
  model was called.
- The raw store was read for 40,256 records (12 bundles) and for the source probes; the production database was read
  with `statement_timeout`, nothing written.
- Scratch on the server: `/root/wp37_scratch` (15 MB of fetched notices, the study scripts, the output), removed at the
  end of the work.
- Not checked: the licence texts of the national portals; how many exact-name duplicates remain (spellings without a
  number); the lot-to-winner mapping (needs the XML); that all result notices of the period are in our database (6,154
  of the database's result rows were not returned by the API's defence query, 20,622 returned rows are not in the
  database as defence; the loader works from the database).
- The figures of the database are as of 18 October 2026, while the historical load of TED was still running; rerunning
  the study later will change the counts.
