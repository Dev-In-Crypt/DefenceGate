# WP-125 self-check: readiness check, supplier report copy, search relevance (verification round 6, 25 October 2026)

Branch `wp-wp125` from `integration` (9244638). Evidence: `D:\DEFENCEGATE TESTS\verify-oct25\personas\` (problems.csv, recheck.csv,
dump/p2-wiz-1440.txt, rc/s-castings.txt, rc/f-csv.txt). No migration. No production access was used.

## Items

| # | Before (evidence) | Change | Test | After |
|---|---|---|---|---|
| 1 | After all five steps the Spanish MoD card said "13 answers are missing" and listed the RID, PECAL, NATO bidding and foreign-investor questions; "Where you need a specialist" said "To answer: Does your product contain components ... of US origin?" (p2-wiz-1440). None of them is asked by the steps: they are the supplier page's. | `lib/profile.ts` `stepAsking` / `askedInSteps`: the step of the five that asks a field (the wizard's fields, the step-4 requirements of the company's country). `components/readiness/rules.tsx` `ProgrammeCard`: on the readiness check's results (not the supplier path) only those count as missing and link to their step; the others are a block of their own, "N more questions for this route are on the supplier page (optional):", one line why ("The readiness check does not ask them. Until you answer them there, the rules that read them stay open."), each question a link to the supplier page (a hidden follow-up to its parent there), and "Go to the supplier page". `results.tsx` `SpecialistAsk`: a specialist's question is a link to where it is asked, "(on the supplier page, optional)" after the five steps alone. The supplier path is unchanged. A scan of the engine over 2,304 completed-wizard profiles (8 countries x regime x classified x export x control x applicant kind, `api.assess_payload` on the seed) found no missing field outside the steps and the supplier page, so no result names a question no page asks. | e2e `wp125.spec.ts` 1 (walks the five steps answering every question shown; ES-MOD has no `[data-missing]`, every missing link on the page is `/readiness?step=N`, the supplier block's links are `/readiness/supplier#q-...`, RID and US-origin linked, the wizard shows no unanswered question); `lib/wp125.check.ts` §1. | A completed wizard never ends with "answers are missing" for questions it did not show. |
| 2 | Step 1 asked "What kind of organisation are you? (optional)" (company or research body / contracting authority / IO / SEAP / EDA) and then "Which of these is your organisation?" (company / university / research organisation) (p2-ready-1440). | One question, "What kind of organisation are you?", seven answers: a company, a university, a research organisation, a contracting authority, an international organisation, a SEAP, the EDA. `lib/profile.ts` `kindOf` / `withKind`: the three company kinds set `applicantKind: company_or_research` and their `orgKind`; a public body sets its `applicantKind` and clears `orgKind`. The engine's inputs and the stored profile (version 5) are unchanged; a profile saved before reads as before (`applicant_kind` alone is still asked its kind; a SEAP is answered). The supplier page keeps its own question (it has no applicant-kind question). Unanswered list: "What kind of organisation you are". | `lib/wp125.check.ts` §2 (mapping, requests, unanswered, old profiles); e2e `wp125.spec.ts` 2 (one group of 7, no "Which of these", stored inputs). | One question; step 1 has 7 questions (8 with the group's staff count). |
| 3 | Tile, /check, /readiness and the call page's readiness note said "25 to 35" (WP-121 took it from the lead, it was not counted). | Counted on the page with WP-121's counter: see below. Texts now "24 to 35" (home tile and its figure, /check, /readiness lead, call-readiness note). | e2e `wp125.spec.ts` 1 and 3 (walks, counts per step, the four texts). | True on every route. |
| 4 | Supplier report of a cable-harness maker (31611000, 31612000, 35422000, no automotive preset) said "Automotive suppliers usually enter defence as subcontractors" and linked the elDiario car-parts article (p3-supres; recheck p03 PARTLY). | Root cause `lib/cpv.ts` `codeKind`: wiring sets (in the automotive set) and military-vehicle parts (3542) counted as automotive on their own. Now a profile is automotive only with a code of motor vehicles or their parts (341, 342, 343) among its codes; the harness profile reads "goods" (the generic sentence) and gets no Indra/elDiario line (`spanishAutomotive` follows `codeKind`). | `lib/wp125.check.ts` §4 (harness = goods; the automotive set, the civil Spanish fixture and wiring sets with vehicle parts stay automotive; `wp97.check.ts` unchanged and green); e2e `wp125.spec.ts` 4 (report: explainer `goods`, no automotive sentence, no Indra, no eldiario link). | Sector copy only for the matching codes. The report's prime list also cited the elDiario automotive article as Indra's source (p3-supres line 218) for any profile: `backend/dgate/demand.py` PRIMES now gives Indra the SIPRI Top 100 source as the other primes (the demo's `lib/mock/demand.json` the same); the article stays in the automotive explainer only. |
| 5 | `/search?q=castings`: two Horizon climate-security calls and a Swiss water-pipe tender (rc/s-castings.txt). Causes: the funding search reads a word of 5+ letters inside any word, and the castings group's word "casting" is inside "forecasting" (the calls' topic tags); the tender search reads the group's term "foundry" as a word start, and TED titles the Swiss notice by its main code's title "Foundry moulds" (CPV 43415000). | Funding (`backend/dgate/textsearch.py`): a word of a product group (the tender search's map) and its alternatives match the start of a word, as the tender search reads them (`_starts`); the funding search's own synonym rows (drone, cyber, logistics, ...) keep their rules. Map (`search-terms.json`, both copies identical): "foundry", "Gießerei", "fonderie", "odlewnia" (the place, not the product; every one begins a code title of foundry equipment) moved to the new `typed_only`: typed, they search the whole group as before; no other word of the group searches them. `search_terms.py` and the demo's `lib/search-terms.ts` read it. | `tests/unit/test_wp125.py` (no place word under "castings"; each place word typed still finds the group; the two calls' texts are not matched by castings/casting/foundry/Gussteile; real casting calls still are; cyber, logistic, drone keep their rules); `tests/integration/test_wp125.py` (Postgres: "castings" finds the aluminium, German and French casting notices and not "Foundry moulds"; "foundry" finds all four; "Gussteile" the three); `lib/wp125.check.ts` §5 (the demo search). test_wp98, wp101 ("fonderie" -> castings), wp110 unchanged and green. | Neither false match; no casting notice lost. |
| 6 | recheck.csv, the PARTLY / NOT FIXED rows on readiness and funding fit. | See the table below. | | |

## Questions per route (item 3)

Counted on the page as `e2e/wp121.spec.ts` counts: each group (fieldset) once, each field outside a group, with every follow-up a route
shows answered.

| Route | Count | How |
|---|---|---|
| EU funding (readiness check), most | 35 = 8 + 7 + 7 + 10 + 3 | Spain, products, run from another country, controlled from outside the EU, in a group, classified work (`wp125.spec.ts` 1) |
| EU funding (readiness check), fewest | 24 = 7 + 5 + 2 + 8 + 2 | a company outside the EU making software or services (`wp125.spec.ts` 3) |
| Supplier profile (products) | 19 outside Spain, 23 in Spain, 35 in Spain with EU funding | unchanged by this package (`wp121.spec.ts` 3) |
| Supplier profile (services, `?offer=services`) | 18 outside Spain, 23 in Spain | `wp125.spec.ts` 3. 18 is below the tile's "19 to 35": the tile now says "one page of 18 to 35 questions" (`SUPPLIER_QUESTIONS`) |

Before the merge step 1 asked 7 to 9 (a public body 7), so the check asked 24 to 36; "25 to 35" was the lead's estimate.

## recheck.csv rows (readiness and funding fit)

| Row | Status there | Here |
|---|---|---|
| p03 supplier report: automotive sentence and elDiario for a harness profile | PARTLY | Fixed (item 4). |
| p05 / p09 EIC 131: "Large company" gets "Nothing known blocks you, 3 conditions to check"; a 2,000+ group "not expressible in the top box" | PARTLY (blocker in round 4) | No change, by evidence: "Large company" without a staff count covers small mid-caps (250 to 499), which may apply on the investor condition, so "check" is the true answer. The staff count is asked by "Check your company" on the same page, which shares one case with "Can I apply?" (WP-109), and a 2,000+ group is a no there: `lib/wp109.check.ts` asserts 131 large + 2000plus = no, large + 250_499 = check, university = no; wp93 pair 42 (P8, 2,000+, 131) = cannot = no. |
| p08 Cyber Defense Factory (French-nationality staff) in "Fits my profile" for a Ukrainian company | PARTLY, UA not tested | No change: the profile does not hold the staff's nationality, so the line is a "check" naming the condition, and WP-109 ranks such calls after the topic matches (`fitOrder`). |
| p05 "Fits my profile" ordering by topic | PARTLY, not tested | Implemented by WP-109 (`FitList` re-orders the list itself; `e2e/wp109.spec.ts`); the persona had no topics saved. No change. |
| p09 three eligibility tools on one call page | PARTLY | Not in this package (page design): open item for the owner. The top box already says it uses the answers of "Check your company". |
| p09 "Who may apply" filter has no research bodies | PARTLY, filter not opened | Present: `who=research`, "Universities and research organisations" (`lib/filters.ts` WHO_WORDS, `filter-bar.tsx`). No change. |
| p06 country texts (export authority, NCAGE) | PARTLY, not checked | Covered by WP-105 (`lib/country-routes.ts`). No change. |
| p09 call 39 "broader country eligibility rules are not stated", p09 non-defence Horizon topics, p01 Ley 24/2011 share, p02/p06/p07 supplier data, p10 heading | | Data or other pages, not readiness or funding fit: not here. |

## Files outside this package's area

- `backend/dgate/demand.py` (PRIMES: Indra's source) and `web/lib/mock/demand.json` (the demo's two Indra rows): item 4.
- `web/app/(public)/page.tsx`, `web/app/(public)/check/page.tsx`, `web/app/(public)/readiness/page.tsx`, `web/components/funding/call-readiness.tsx`: "25 to 35" -> "24 to 35" only (item 3, the brief asks it).
- `backend/dgate/readiness/export.py`: the wizard profiles of the e2e fixtures (ua, ua-pic, ua-pic-na, es) carry `org_kind: company` (step 1's one question sends it); the engine and the roadmap context read them as the API does. Only `request-*.json` changed; every `assess-*.json` is byte-identical.

## Tests moved (old -> new, why)

None deleted, skipped or loosened.

| Test | Old | New | Why |
|---|---|---|---|
| `e2e/readiness.spec.ts` (Ukraine, Spain) | "What kind of organisation are you" -> "A company or a research body" | same group -> "A company" | item 2: the answers of the one question |
| `e2e/readiness.spec.ts` request fixtures | `request-ua.json`, `request-es.json` without `org_kind` | regenerated by `python -m dgate.readiness.export`, with `org_kind: company` | item 2: "A company" sends it |
| `e2e/wp93.spec.ts` | "Which of these is your organisation" -> "A company" | "What kind of organisation are you" -> "A company" | item 2 |
| `e2e/wp117.spec.ts`, `e2e/wp121.spec.ts` | "25 to 35" | "24 to 35" | item 3: counted |
| `e2e/wp121.spec.ts` tile | "one page of 19 to 35 questions" | "one page of 18 to 35 questions" | item 3: the services route asks 18 |

## Runs (D:\DEFENCEGATE TESTS\wp125)

- Backend: `ruff check .` clean. Unit: test_wp125, wp98, wp101, wp110, textsearch, readiness_export, wp93, wp102, wp66, wp80, wp89, wp97,
  wp105 all green. Integration (Postgres 17, port 55525, container deleted after): test_wp125, wp98, wp101, wp110, wp93, wp102,
  readiness_api, search, and the demand / supplier-map / wp66 / wp80 / wp89 / wp97 / wp105 sets all green.
- Web: `tsc --noEmit` 0; `node scripts/run-checks.mjs` 0 (every lib check; wp93 60/60 pairs and 240 verdicts equal to the API's, wp102
  58/58 and 350; wp125 new). The wp93 / wp102 golden files and pairs were not touched.
- `next build` 0 and Playwright (holding web-build.lock) wp125, readiness, wp93, wp117, wp121, wp80, wp97: 114 passed, desktop and 375 px.
