# WP-145 self-check: EDIP calls and Ukrainian applicants, stated precisely

Owner decision of 26 October 2026: mark the EDIP calls where Ukrainian entities cannot take the funding, saying only what the call's
documents say, never on the Ukraine Support Instrument (EDIP-USI). Context: WP-143 self-check item 11.

## 1. What the stored call documents say (production, read-only, 26 Oct 2026)

Production has 12 calls with an `EDF-EDIP-` topic code: 10 EDIP (`EDF-EDIP-P-`) and 2 EDIP-USI (113, 118, left out by rule). Each EDIP
call lists one stored "Call document" (`call.conditions_raw.documents` joined to `call_document_text`, 6 distinct documents); no other
document of these calls is stored, and their portal conditions text (`call.eligibility_text`) names Ukraine nowhere. Every sentence of
the 6 documents that names Ukraine or Ukrainian was read (`grep -i ukrain`, 53 lines), and the eligibility sections in full.
Evidence: `D:\DEFENCEGATE TESTS\wp145\prod\q2.out`, `q4.out`, `docs.txt` (the 6 texts); the relevant passages are committed as
`backend/tests/fixtures/wp145_edip_documents.json`.

**Outcome: no EDIP call document states that entities established in Ukraine (or controlled from it) cannot receive funding or are
not eligible. All 10 are silent; 0 calls are marked.** Ukraine appears only in other roles, and the one sentence that withholds
funding does not name Ukraine.

| Calls | Document (version) | Who may apply (the document) | Where it names Ukraine |
| --- | --- | --- | --- |
| 108, 109 (2026-FNLC-CPA-AMEW, -CDS) | call-fiche_edf-edip-p-2026-fnlc-cpa (V1.1, 20.05.2026) | "be contracting authorities, international organisations, SEAPs or EDA within the meaning of Articles 11, 27(1) and 42 of the EDIP Regulation." | the EDA or an international organisation may be a beneficiary "if designated as ‘procurement agent’ ... by the EU Member States, EDIP associated countries, Ukraine or a SEAP"; "Associated countries and Ukraine can normally be also part of the SEAP"; the procurement agent informs "EDIP associated countries and Ukraine" of the chance to buy additional quantities; a bonus where "Ukraine or Moldova are one of the recipients of additional quantities" |
| 110, 111, 112 (2027-FNLC-CPA-AMDS, -C5ISRS, -GNPS) | call-fiche_edf-edip-p-2027-fnlc-cpa (V1.0, 20.05.2026) | the same sentence | the same four roles |
| 114 (2026-2027-FNLC-SA-SEAP) | call-fiche_edf-edip-p-2026-2027-fnlc-sa (V1.0, 13.10.2026) | "be an established SEAP ... with at least 3 members from EU Member States, EDIP associated countries or Ukraine, of which at least 2 must be EU Member States" | a SEAP member (the grant is EUR 200 000 per Member State, associated country "or Ukraine" member); "a SEAP that includes Ukraine as a member would not be eligible" in EDPCI CSA or Deployment actions (other calls; a SEAP, not a Ukrainian entity) |
| 115 (2026-LS-IRA-EC) | call-fiche_edf-edip-p-2026-ls-ira (V1.2, 10.06.2026) | "be established in one of the eligible countries, i.e.: EU Member States (including overseas countries and territories (OCTs)) − non-EU countries: listed EEA countries and countries associated to the EDIP Programme (‘EDIP associated countries’; list of participating countries)" | only "Associated countries and Ukraine can normally be also part of the SEAP" |
| 116, 117 (2027-LS-IRA-KEC, -PE) | call-fiche_edf-edip-p-2027-ls-ira (V1.1, 08.06.2026) | the same list | only the SEAP sentence |
| 193 (2026-FNLC-CSA-PREP) | call-fiche_edf-edip-p-2026-fnlc-csa (V1.0, 13.10.2026) | "be a SEAP or a group of at least 4 EU Member States and EDIP associated countries and which have submitted a proposal for an EDPCI ..." | the SEAP sentence; the grant may be reduced "if (one or more) EU Member States or EDIP associated countries or Ukraine is not involved or consulted in the preparation of the roadmap" |

The nearest sentence, in all six: "Associated partners which are not established in one of the eligible countries (or which are subject
to control by a non-associated third country or non-associated third-country entity) may however participate exceptionally if certain
conditions are fulfilled ... subject to agreement by the granting authority and without any funding under the grant." It does not
name Ukraine; that Ukraine is not an eligible (associated) country comes from the Regulation (EU) 2025/2643, Articles 9(1) and 2, not
from the document. So the label would say more than the document, and it is not shown. What the call pages already say since WP-132
(reason `programme_rule`: "Entities established in Ukraine cannot receive EDIP funding under this call ... (Regulation (EU) 2025/2643,
Articles 9(1) and 2)") is unchanged, and the readiness check keeps blocking a Ukrainian company under the EDIP Programme rules.

## 2. Built so a document that says it is marked (and only then)

- `ukraine.no_funding_sentence(text)`: a sentence whose subject is entities established in Ukraine, Ukrainian entities or entities
  controlled from Ukraine, with a refusal (not eligible, cannot, may not, without/no funding) about funding or eligibility; a
  territorial exclusion (non-government controlled areas) and Ukraine's roles (SEAP member, designating state, recipient of
  quantities) are not it. PDF line breaks are joined first.
- `ukraine.decide`: for an EDIP call (never EDIP-USI, never EDF), checked first: flag stays `null` (taking part without funding is
  another question), reason `call_document_no_funding`, evidence = the sentence. `ukraine.run` reads the stored "Call document" texts
  of the `EDF-EDIP-P-` calls only. Runs nightly (worker, with the cascade flags) and as the ops step below.
- API: `ukraineNoFunding` (bool) on every call of `/v1/funding` and its detail; filter `uaNoFunding=true` (before the counts);
  `/v1/fit/facts` items of such calls carry the sentence (absent otherwise, so older answers are unchanged); `verdict.check` adds the line "No funding for Ukrainian entities" (no) for a country UA
  applicant with the sentence as quote (`readiness/api.call_verdict` passes it). No migration (the reason is a text column).
- Site: the badge "No funding for Ukrainian entities" on the list card and the call page header (`data-ua-no-funding`); the
  "Ukrainian participants" panel line "Ukrainian entities cannot receive funding under this call: the call document says so." with the
  sentence quoted under it ("From the call document"); the filter "Only calls whose document says Ukrainian entities cannot receive
  funding" in the Ukrainian participants group (`uaNoFunding`, also accepted by the feed, ICS and CSV routes); `lib/eligibility-check.ts
  check` the same line as the API (`lib/fit.ts callFit` and the call page pass the sentence). `docs/design/API_CONTRACT.md` updated.
- Silent document: nothing new anywhere (all of production today).

## 3. Ops step (the orchestrator, after the deploy)

`docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps worker python -m dgate.ops.ukraine_flags`
(report), then the same with `--yes` only if the report differs. **Expected today: `no_funding: 0`, `changed: 0`** (the 10 EDIP calls
keep `programme_rule`, the 2 USI calls `call_document`). The nightly job writes it by itself when a new or changed EDIP call document
says it. Outcome list: marked: none; silent: 108, 109, 110, 111, 112, 114, 115, 116, 117, 193; not considered (USI): 113, 118.

## Tests

- `backend/tests/unit/test_wp145.py`: the 6 stored documents (fixture) give no sentence and the 10 calls stay `programme_rule`;
  positive and negative sentences; USI and EDF never get the reason; the verdict blocks P5 (UA, wp93 set) with the sentence on call 117
  and not P1 (ES), and nothing changes without it.
- `backend/tests/integration/test_wp145.py`: `ukraine.run` report writes nothing, `--yes` marks only the EDIP call whose call
  document says it (not the silent one, not a USI call, not a document labelled otherwise), second run changes nothing; list field and
  filter (422 for another value), detail basis, `/v1/fit/facts` sentence, `call_verdict` blocked for UA.
- `web/lib/wp145.check.ts`: `callFit` the same as the API's twin, the API's words word for word, the page line, the filter's URL key.
- `web/e2e/wp145-api.spec.ts` (fake API, calls 9005/9006; `playwright.config.ts` fake testMatch): card badge only on 9006, the
  filter, the page header badge and panel line with the quote; 9005 shows nothing new.

## Runs (`D:\DEFENCEGATE TESTS\wp145\`)

- ruff: clean. Unit: **4085 passed** (after the last change). Integration (Postgres on 55545, one run on the final tree): **1564
  passed** (`int3.log`). An earlier run had stopped with the laptop's restart; the run after it found one real failure, fixed:
  `test_wp32` compares a `/v1/fit/facts` item exactly, so the new key is now sent only for a marked call (absent otherwise).
- tsc: clean. Lib checks (`node scripts/run-checks.mjs`): all green; **wp93 60/60** pairs and **wp102 58/58** checkable pairs, Python
  and TS equal (240 and 350 call x profile verdicts); the truth pairs are unchanged.
- Build: ok. Playwright (lock held): wp145-api, wp132-api, wp91, wp109, wp141: 56 passed, 1 skipped, 3 failed in wp145-api on the
  spec's own selectors (the panel heading, the folded filter on a phone); after the fix wp145-api **6 passed** (desktop and 375).

## Files outside the funding/eligibility area

`web/playwright.config.ts` (one spec name in the fake-API list), `web/e2e/support/fake-api.mjs` (call 9006 and a `q=wp145` list),
`web/lib/filters.ts` (the `uaNoFunding` key; WP-144 works in tender/buyer parts of it: different lines).
