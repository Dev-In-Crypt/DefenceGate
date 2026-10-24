# WP-110 self-check: search precision and stability (round 4, re-check of 24 October 2026)

Branch `wp-wp110` (from `integration` e0d73b7). Package: `search.py`, `search_terms.py` (+ `data/search-terms.json`, both copies),
`textsearch.py`, the q-handling and subject of `tenders.py`, the web search page, the `/cpv` finder, `lib/search-terms.ts`,
`lib/cpv.ts` (code sets), the tender list's presets. Findings: `D:\DEFENCEGATE TESTS\ux-oct24b\NOTES.md` (p01, p03, p04, p05, p06, p07,
p08, p10) and the coordinator's additions (SSI, cyber buyer names, funding cybersécurité, Ersatzteile DE, Zerspanung ranking, list subject).

Production was read only (SELECT through the postgres container with `default_transaction_read_only`, and the list functions inside
`dgate-api-1` with the API role in READ ONLY transactions), a few queries spaced, after the coordinator said the auditors had finished.
The branch's code was run there from `/tmp/wp110` (PYTHONPATH) with `ts.main_heads` computed inline, as migration 0122 is not applied
there; nothing was written.

## Root causes

| finding | cause (evidence) |
|---|---|
| q="wiring harness": 8 unrelated tenders (canteen in Łomża, concrete foundation, network cables, battery room) | All 8 found by a **secondary** CPV code: 45311000 "Electrical wiring and fitting work" / 45311100 among the codes of construction notices main-coded 45000000 (e.g. 267759 `{45000000,45315300,45311100,...}`), which `codes_for_word("wiring")` named; the network cables by the Spanish term "cableado" (any cabling). |
| q=drone 1,374 incl. a Croatian pollution-control vessel | 298380 `{34513600,34512000,34113200,34711200,35512400}`: secondary 35512400 "Unmanned underwater vehicles" (the title of the group term "unmanned") and 34711200. |
| q=cyber 3,390 | the typed product word also read the buyer's name: every notice of the Polish cyberspace centre matched. |
| FR cyber: fire alarms, cold rooms, firefighter clothing | the term "SSI" (French: Système de Sécurité Incendie). |
| Zerspanung/CNC: general spare parts first | machining and spare parts were one group: "Zerspanung" was any spare-parts word (38 open, 2 of them machining). |
| /cpv: harness, wiring, stamping "0 codes match" | the finder searched its 366-code selection only, in the browser. |
| header search "not available" ~1 load in 3; RBLog 11.5 s, 3 of 5 parts "took too long" | (a) the parts ran one after the other on the request's one connection; `SET LOCAL statement_timeout` bounds each **statement**, not the part, so the tender part's three statements of ~1.2 s each (measured on production, idle: RBLog 4.2 s, funding and buyers "slow") took the budget, and under load each statement took longer (11.5 s); (b) the request's own connection was taken before the search started: a full pool (`PoolBusy`, 3 s wait) was a 503 for the whole search; (c) **429**: the ten auditors shared one address (BRIEF.md) and `/v1/search` costs 15 of the bucket's 120 tokens: `dgate-web-1` logs show 429s from 16:16 to 16:20 UTC, and the page said "not available" for any failure. |
| "warehousing" (no country, status all) "service busy" 2/2 | not the query: 1.1 s on production now (164 notices). The web log shows `GET /v1/tenders?q=warehousing&status=all&pageSize=10 failed ... status: 429` at 16:17:06 UTC: the shared address's rate limit. |
| "Leonardo": Megmar second, unexplained | Megmar's award name as stated: "Konsorcjum: MEGMAR Logistics & Consulting Sp. z o.o. Leonardo Poland Sp. z o.o." (the supplier search reads published names). |
| Dutch MoD as a Swedish company that won 1 contract | supplier 429647 "Het Ministerie van Defensie", `supplier_country` SE, from notice 624641-2025 (NL) whose buyer is the Ministerie van Defensie itself: the source lists the buyer as its own winner. Award reading, not search (see open items). |
| subject cut at "kal." (7.62 mm ammunition) | `commercial_subject` split at any ". " before a capital or digit: "kal. 7,62". |
| Volvo Penta engines tender shows vacuum-toilet parts | the buyer's own text: 144661 (TED 666676-2026) and 147002 (TenderNed 441590) carry the same description "De levering reserveonderdelen vacuü(mtoilet)..." in every version; the engines notices 120105/127841 have their own. Not a version or lot mix-up of ours: nothing to fix in code (open items). |
| BAAINBw subjects "...FAHRZE", "100 EA", "Versorgungsnummer", an address | BAAINBw's item-name field is 40 characters (cut by the source), item numbers with their labels, quantity-only texts, letter heads with addresses (274926, 284020, 286899). |
| landing spain-automotive: 34322000 without label | the site's code dictionary (finder selection + product words) lacked 13 codes of the one-click sets. |
| vehicle-repair preset catches a gate repair | the preset filter reads every code; works notices list services as secondary codes. |

## Items

### 1. Precision of the product groups

- Change: `search-terms.json` (both copies): groups get `anchors` (codes whose **main-code** notices are the product itself); "wiring"
  alone and the generic cabling words (cableado, câblage, okablowanie, cablaggio, cablaggi) left the harness group, "wiring harness(es)",
  "wire harness(es)", "cable harnesses", "wiring looms", "Kabelsätze", "faisceaux électriques" added; "SSI" removed from cyber; machining
  (Drehteile, Frästeile, Zerspanung, CNC, Präzisionsteile, mecanizado, usinage ...) is a group of its own; "Ersatzteil", "Ersatzteilen" added.
  Migration `0122_wp110_search_main_code.sql`: `opportunity_search.main_heads` (heads of the main code), the trigger writes it, backfill,
  GIN index. `tenders._tender_filters`: a group slot is (typed words, all, any order, **in a title**) or (a term of the group as a phrase in
  a title) or (main code under an anchor) -- never the buyer's name, never a secondary code, never the titles of codes its words begin; a
  word of no group reads titles and the buyer as before, and the codes its word begins **by the main code only**.
- "Did you mean CPV 31611000 Wiring sets?": `tenders.cpv_hints` (`cpvHints` on `/v1/tenders` and `/v1/search`): a group's suggested codes,
  or for a one-word search of no group the codes whose title's first word is that word; shown beside the results whatever they are
  (`CpvHints`, tender list and search page), each a link to the list by code.
- Ersatzteile + DE: the open BAAINBw part orders (Gelenkwelle, Getriebe) are titled by order number ("6003121709-BAAINBw E2.3Y_E23Y003367")
  and main-coded 35400000, which on production is also the code of vehicle purchases (Slovenian lorries, Polish police vehicles, six
  Portuguese vehicles among the 1,344 notices of that main code). Reading 35400000 as "spare parts" would make every vehicle purchase a
  spare part, so the hint names it instead: "Did you mean CPV 35420000 Parts of military vehicles, CPV 35400000 Military vehicles and
  associated parts ...". Item 4 of the subject shows "GELENKWELLE MIT AUSGLEICHSGELENK" on those cards.
- Precision before/after, production, open notices (all listed open results read and judged by title):

  | search | before: open (judged relevant) | after: open (judged relevant) | notes |
  |---|---|---|---|
  | wiring harness | 8 (0) | 0 (0) | no open wiring-harness tender exists; hint CPV 31611000 |
  | cyber | 4 (1: the BE training; cold rooms = SSI, two by the cyberspace centre's name) | 5 (5: firewall PT, malware lab RO, vulnerability management RO, data security RO, BE training) | |
  | drone | 12 (10: the Croatian vessel and the Swedish target-shooting DPS by codes) | 11 (11, a Lithuanian fixed-wing UAV added by main code 34711200) | |
  | spare parts | 38 (about 31: grinding machines, valves, a fibre laser, welding equipment, lifting gear, mecanizado and Tatra support among them) | 32 (the first 25 read: all spare parts) | |
  | Zerspanung | 38 (2: everything else general spare parts) | 2 (2: CNC grinding machines FR, SDA mecanizado ES) | |
  | Ersatzteile, DE | 3 (3) | 4 (4: + "Kappmesser inkl. Ersatzteil") | BAAINBw orders by the hint |
  | castings | 1 (1) | 1 (1) | |
  | stampings | 0 | 0 | |

  Counts over every status on production cannot be had with the inline expression (its count ran out of its time box, "at least");
  with the column of migration 0122 they are index-backed. The synthetic archive's runs are in "Runs" below.
- Tests: `tests/unit/test_wp110.py` (groups, SQL: no `ts.buyer_name` and `ts.main_heads` only for a product word, hints),
  `tests/integration/test_wp110.py` (trigger keeps `main_heads`; canteen, foundation, network cables and the vessel not found, a main-coded
  31611000 notice and a "Wiring harnesses" title found; the cyberspace centre's notices not "cyber" and found by its name; machining vs
  spare parts; the hint). Spec changes in older tests, each with a comment: `test_wp98.py` (Drehteile/Frästeile are machining; a typed
  product word no longer reads the buyer; `search_info` has `cpvHints`), `test_wp101.py` unit and integration (machining group: "Drehteile
  Frästeile" and "CNC" no longer list "Ersatzteile Leopard 2"; "wiring" alone and "SSI" no group term), `lib/wp98.check.ts`,
  `lib/wp101.check.ts` (same). What those tests asserted about one slot per run of terms, the stored texts and the alternatives cap is unchanged.

### 2. /cpv finder over the full vocabulary

- Change: `components/cpv/cpv-browser.tsx`: the first keystroke loads `lib/cpv-full` (a chunk of its own, as the supplier picker) and the
  search reads all 9,454 codes with the curated product words (`cpvSearch`, curated words first, whole words); until it has loaded the
  selection is searched as before. The page's footnote says the search reads all codes. `lib/wp73.check.ts`: the dynamic import is allowed
  in the finder too (the full list is still never imported statically).
- Test: `e2e/wp110.spec.ts` (harness -> 31611000, wiring -> 31612000, stamping -> 34320000, never "0 codes match"), `lib/wp110.check.ts`.

### 3. Header search reliability

- Change: `search.py`: the five parts run at the same time, each on its own connection inside the API's bound (same gate as every request)
  and the search's own (`PART_CONNECTIONS` = 10 of the API's 24), each with the budget as its statement limit and a wall-clock deadline;
  a part not done at the deadline is cancelled (`Connection.cancel`) and is "slow", one without a free connection in time is "busy"
  (new, said as "This part of the search is busy right now"), any other failure of one part is that part's ("busy", logged). The search
  takes no connection itself: a full pool is never a 503 of the whole search. The page says a 429 as "Too many searches from your
  network just now" (an office behind one address shares the limit), not "not available". `hardening.py`: no change -- the 15 tokens
  are the database time of five lists; a shared office address meets the limit by design, and the page now says so.
- Production (read only, spaced 3 s, load 0.8-1.0), the branch's search against the deployed one:

  | q | before (deployed, sequential) | after (branch, parts at once) |
  |---|---|---|
  | Regionalna Baza Logistyczna | 4,230 ms, funding and buyers "slow" | 2,348 ms, every part answered (tenders 27, buyers 4) |
  | Ministerie van Defensie | 3,909 ms | 1,329 ms |
  | DMO | 1,425 ms | 930 ms |
  | NAVARM | 779 ms | 423 ms |
  | Ersatzteile / Drehteile / BAAINBw | -- | 1,566 / 1,376 / 940 ms |
  | warehousing (search) / `/v1/tenders?q=warehousing&status=all` | 1,095 ms (list) | 738 ms (search) |

- Tests: `tests/unit/test_wp110.py` (all parts started at once; a full pool makes each part "busy", never the search; a part past the
  deadline is cancelled and "slow" while the others answer), `tests/integration/test_wp110.py` (two parts of 1.2 s each in a 2 s budget
  both answer), `tests/integration/test_search.py` unchanged and green (a part of 3 s in 2.4 s is "slow", the others answer, under 2.4 s).

### 4. Ranking and labels

- "Leonardo": `search.named_first`: the companies whose own name holds the words first, then those found by a published name, each with
  that name (`matchedAs`); the page says "named in an award as “Konsorcjum: MEGMAR ... Leonardo Poland Sp. z o.o.”". Production: Leonardo
  S.p.A., LEONARDO Germany, Leonardo UK, Leonardo PZL-Świdnik, then Megmar with that line. Test: `test_wp110.py`.
- Dutch MoD as a Swedish company: explained above; not changed here (award reading). See open items.

### 5. Subject

- Change: `tenders.first_sentence`: a full stop after an abbreviation (kal., nr, ok., tj., np., ca., z.B., bzw., aprox., réf., e.g.
  and others, `_ABBREVIATIONS`), a single letter or a dotted abbreviation does not end the sentence. `commercial_subject` (list and page):
  a letter head's address block and labels are taken out (only when the text has a postcode-and-town line), supply item numbers with
  their labels ("Vers.Art. 2520-...", "Versorgungs-Artikel-Nummer ..."), an internal reference at the start of a line ("Q/I2BQ/PA103/MA447");
  a name of exactly BAAINBw's 40-character field before an item number loses its cut last word ("GELENKWELLE MIT AUSGLEICHSGELENK,
  FAHRZE" -> "GELENKWELLE MIT AUSGLEICHSGELENK"); a text without a word ("100 EA", "3.564.000 EA") is no subject (the title is shown).
  The 7.62 mm ammunition description itself then reads as calibre with a unit and is left out by the existing technical rule (the title
  shows), never cut in the middle.
- Tests: `test_wp110.py` (eight abbreviation cases; the production BAAINBw texts; an ordinary description unchanged).
- Volvo Penta: the buyer's own description (above), nothing to fix in code.

### 6. Profiles, landing, presets

- Profiles saved with an earlier set: `lib/cpv.ts` `PREVIOUS_SETS` (the automotive set with 35420000 and 35421000 of WP-89/97, the WP-97
  machining set, from the file's history) and `setUpdate`: when the codes hold an earlier version whole and lack some current codes, the
  CPV picker offers "Update to the current set" saying what it adds and drops; only the old version's own dropped codes are removed (a
  code another set chosen whole holds stays), the visitor's other codes stay, never past 15. `lib/wp110.check.ts`.
- 34322000 without label: `lib/cpv.ts` `SET_TITLES`, the official titles of the 13 set codes neither the selection nor the product words
  held (verbatim; `lib/wp110.check.ts` holds each to `cpv-full.json` and asserts every set code has its title). The finder's selection
  (`cpv.json`) is unchanged: adding them there changed its title search (`lib/wp57.check.ts`).
- Presets: `lib/analyst.ts` `presetMainOnly`: the services presets (transport, fuel, facility, catering, vehicle repair, training, IT)
  set "Main product code only"; a goods preset reads every code (a part is often a secondary code of a vehicle or ship notice), said in
  the CPV field's hint. `e2e/wp98b.spec.ts`: the Transport preset's URL now ends `&cpvMain=true` (spec change, commented).

### Funding search ("cybersécurité" found no ECCC call)

- Change: `textsearch.parse(..., products=True)` adds the product groups of the tender search to the funding synonyms; `funding.py` (WP-109's
  file, one line) passes it. The organisations' and partners' searches keep their own synonyms. Test: `test_wp110.py`.

## Runs (D:\DEFENCEGATE TESTS\wp110, Postgres 17 on 55510, fresh database)

- ruff clean. Full unit suite: 3,792 passed, 1 failed (`test_wp106` expected the source-cut "..., FAHRZE": spec change of item 5, now
  "GELENKWELLE MIT AUSGLEICHSGELENK", unit and integration, commented); rerun of the changed files green.
- Full integration suite: 1,364 passed, 1 failed (the same `test_wp106` case); rerun green. A first run also failed
  `test_wp19` (the funding search's "also searched" for "counter drone" grew by the drone group's words): the product groups are
  now added only for a funding word the funding synonyms do not know, and `test_wp19` passes unchanged.
- tsc clean; every lib check ok (`node scripts/run-checks.mjs`, with `wp110.check.ts`); `next build` ok; Playwright wp110, wp98, wp98b,
  wp101, wp86, wp47, wp65, wp96, wp90, wp105, suppliers, ux: all passed, desktop and 375 px.

## Files outside the package

- `backend/dgate/funding.py`: one line (`products=True`) for the funding search's product words.
- `web/components/readiness/supplier.tsx`: the "Update to the current set" offer in the CPV picker (profile preset migration).
- `web/components/tenders/filter-bars.tsx`, `web/lib/analyst.ts`: services presets read the main code.
- `web/lib/types.ts`: `CpvHint`, `cpvHints`, `matchedAs`.

## Ops on production

- Migration `0122_wp110_search_main_code.sql` (the migrate service): one UPDATE of `opportunity_search` (~394,000 rows, a minute or two),
  then a GIN index. The trigger is replaced in the same transaction; run it when no load is writing notices, as 0113.
- No data ops module.

## Open items

- Dutch MoD as winner (429647, notice 624641-2025): the source names the buyer as its own winner; the award reading should skip a winner
  whose name is the notice's buyer (awards package, not search).
- Volvo Penta sterndrives (666676-2026 / TenderNed 441590): the buyer published the vacuum-toilet description; nothing to correct.
- BAAINBw part orders titled by order number: the word search cannot tell them from vehicle purchases by code; the hint leads to
  35400000. Searching the subject (descriptions) would need it in `opportunity_search` (a later package).
- The tender list's error page says "busy or slow" for a 429 too (Next.js hides the status from the error boundary).
