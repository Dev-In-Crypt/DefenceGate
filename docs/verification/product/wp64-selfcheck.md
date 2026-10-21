# WP-64 self-check: Spain, Germany and NATO/EU readiness rules (21 October 2026)

Branch `wp-wp64` from `integration` (edffcde). Source of every rule: `docs/research/ANGLE1_RULES_ES_DE_2026-10-20.md`
(copied into this branch read-only, so that a test can check the quotes against it). Plan row: WP-64 of
`docs/plans/MVP_SPAIN_AUTOMOTIVE_2026-10-21.md`. No model call, no spending, no external request, no production access, no
migration (the new data fits the existing JSONB columns `texts` and `extras`).

## 1. Rules added (seed `backend/seeds/requirements.json`)

The research table has 33 rows. 32 are in the seed; 31 as new rules, 1 as an upgrade of an existing rule. Every new passage is
copied from the research table by the generator and checked verbatim against it by `tests/unit/test_wp64_rules.py`
(`test_every_new_quote_is_verbatim_from_the_research_table_with_source_and_date`). `text_origin` primary,
`last_reviewed` 2026-10-20 (EU-DUALUSE-EXPERT: 2026-10-17, as the research says), source URL and reference on each.

New programme **`ES-MOD` "Spanish defence supplier (MoD)"** (kind `route`, 21 rules, all apply only to companies established in Spain):
ES-RID (mandatory registration), ES-PECAL-CONTRACT, ES-AOC-CLAUSE, ES-PECAL-CERT, ES-PECAL-ISO, Q-ISO9001-FILTER, Q-EN9100-FILTER,
ES-NCAGE, ES-CATALOG-CLAUSE, ES-HOMOLOG, ES-HSEM, ES-HSES, ES-HSEM-ISSUER, ES-ONS-ROLE, ES-NSFCC, ES-NATO-DOE, ES-EXPORT-MIL,
ES-LGTC, ES-FOREIGN-CAPITAL (S, as the research rates it), ES-CERTIFIED-RECIPIENT, ES-MOD-EXPORT-ROLE.

**`GENERAL`** (usable by any profile): DE-GHB-ADMISSION, DE-GHB-COST, DE-GHB-BID, DE-VSNFD, DE-SIBE, DE-SUE, DE-EXPORT-BAFA,
EU-CERTIFIED-RECIPIENT, EU-DUALUSE-EXPERT. **`NATO-SUPPLY`**: NATO-AQAP-ED.

**ES-REOCE** is the upgrade of G-REOCE (correction 2), not a second rule.

New requirements: **REQ-RID**, **REQ-PECAL** (prerequisites REQ-RID and REQ-ISO9001, "before"), **REQ-HSES-ES** (prerequisite
REQ-FSC-ES), with issuers (DIGEID; DGAM state route; DGAM/ONS) and no cost or duration (none is published). New issuer
REQ-AQAP2310 / ES (PECAL 2310 state route).

## 2. Corrections applied (the six of the research file)

1. REQ-FSC-ES / G-HSEM: the issuer depends on who owns the information. REQ-FSC-ES has two Spanish issuers (DGAM for MoD classified
   contracts, Resolución 320/14546/2013; ONS for NATO, EU, ESA), primary passages from the MoD SEGINFOEMP page and cni.es; G-HSEM texts
   name both. The appendix FSCIS sentence was dropped (not re-read in a primary source).
2. REQ-REOCE / G-REOCE: upgraded to Ley 53/2007 art. 12 (BOE), `primary`, V, 2026-10-20. The residence condition (RD 679/2014 art. 13)
   has no verbatim primary passage in the research, so the description says it rests on the 7 September notes.
3. NATO-AQAP: note that for Spain it is stated in a primary source (ES-PECAL-CONTRACT, V); the general statement stays S.
4. ISO 9001 / EN 9100: `mandatory_for` says they are a formal precondition on the PECAL route (PA 4302); REQ-PECAL has ISO 9001 as a
   formal prerequisite; the ES issuer of REQ-AQAP2110 says so.
5. NCAGE issuer ES: "requires an existing supply contract" replaced by the MoD wording (justified need: a product bought by the MoD,
   or SAM registration; SICAD or the NSPA tool); URL of the catalogación page.
6. AQAP editions: REQ-AQAP2310 says Spain lists PECAL 2310 Ed. B V1 = AQAP-2310 Ed. B V1 (the appendix said V2); legal basis
   "Edition B"; AQAP-2131 Ed. C V1 is in NATO-AQAP-ED. No REQ-AQAP2131 requirement was added (no cost, time or issuer is sourced).

Also changed because it would otherwise be false: G-CLASSIFIED-OTHER said only Spain was collected; it now excludes Germany too.

## 3. Left out

- **Q-IATF16949**: the research says "do not build" (no primary source). IATF appears only in an UNVERIFIED note.
- **The 11 UNCONFIRMED items**, none seeded as a fact (test `test_nothing_unconfirmed_is_seeded_as_a_fact`):
  1. RID legal basis, fee (EUR 181.50), processing time, validity: not seeded; REQ-RID says UNVERIFIED.
  2. PECAL fee, processing time, validity (3-year renewal): not seeded; "the DGAM issues a quote" only.
  3. HSEM/HSES cost and duration, and whether a company can apply without a contracting body's need: not seeded.
  4. NCAGE Spain cost and time on a Spanish page: not seeded (ES-NCAGE note).
  5. NSPA Source File registration: not seeded.
  6. Duration of the German Geheimschutzbetreuung admission; who requires/certifies AQAP in Germany: not seeded (note says it depends on the case).
  7. AQAP 2110/2310 certification outside Spain per country; AQAP 2120: unchanged, not re-checked.
  8. Directive 2009/43/EC amendments after 2009; CERTIDER register: EU-CERTIFIED-RECIPIENT note says UNVERIFIED.
  9. ISO 9001 / IATF 16949 as general buyer filters: Q-ISO9001-FILTER says no primary source, and makes no such claim.
  10. Ranking of Spanish MoD buying units: not seeded (WP-66 data).
  11. Domestic sale of Annex I material needs no licence: not stated; ES-EXPORT-MIL's text speaks only of goods that leave Spain, and its note says UNVERIFIED.

## 4. Engine and pages

- Three-valued outcomes unchanged. **Unasked requirements** (REQ-RID, REQ-PECAL, REQ-HSES-ES carry `extras.question`): a status the
  browser does not send reads as unknown (`engine.with_unasked`, sentinel `unknown`), so the rule is "unknown" and asks the question;
  a sent status (roadmap "Mark as done") is read as before. **28 new profile fields** (`engine.SUPPLIER_FIELDS`), optional in the API,
  not asked by the wizard: a rule that needs one is "unknown" with its question; the results page shows such a question with
  "(not asked by the questionnaire yet)" instead of a link to a wizard step. No wizard question was added.
- **Consultant needed**: `texts.consultant` on ES-EXPORT-MIL and EU-DUALUSE-EXPERT and DE-EXPORT-BAFA (export classification:
  RD 679/2014 Annex I, Reg. 2021/821, Ausfuhrliste), ES-HSES (HSES path), ES-PECAL-CONTRACT (prime qualification), ES-FOREIGN-CAPITAL
  (RD 664/1999). Shown per rule while it is open or not met, and listed in a "Where you need a specialist" section. **ITAR**: there is
  no verified rule; the `US-COMPONENTS` flag only says a specialist is needed and states no rule (shown unless `us_components` is false).
- **PECAL chicken-and-egg**: ES-PECAL-CERT is `conditional` obligation; RID + ISO/EN 9100 held but no nine months / no prior PECAL
  contract gives `conditional` with the explanation, never a block of the route. REQ-PECAL is a roadmap step (optional "when a contract
  names it", after RID and ISO 9001) with `note` explaining the chicken-and-egg.
- **RD 679/2014 art. 13.3**: ES-FOREIGN-CAPITAL applies when the company is controlled from abroad (existing answer) or says it has
  foreign capital; the authorisation is the check; S.
- A route none of whose rules applies (ES-MOD for a non-Spanish company) is left out of the answer (`engine.concerns`), not "eligible".
- Web: types (`consultant`, `consultants`, `note`), `profile.ts` (roadmap-only status codes sent only once marked, `wizardAsks`),
  results/roadmap/requirement pages; a national primary source is no longer called "the Official Journal" (`isOfficialJournal`).

## 5. Tests

New: `backend/tests/unit/test_wp64_rules.py` (13 test functions, 19 cases), `backend/tests/integration/test_wp64.py` (2), `web/lib/wp64.check.ts`,
`web/e2e/wp64.spec.ts` (2 tests x desktop and 375 px), generated fixture `web/e2e/fixtures/{request,assess}-es-auto.json`.

Existing tests changed, and why (no assertion removed or loosened):
- `test_readiness_seed.py`: requirement count 12 → 15 and the exact set +3; `seed ok` line 6/12 → 7/15; the Spanish HSEM issuer is
  now two (correction 1), both still asserted UNVERIFIED on processing times.
- `test_readiness_roadmap.py`: `run()` uses `api.assess_all` (what the API answers); UA general outcomes list the 9 new rules; ES steps
  add REQ-RID and REQ-PECAL; HSEM issuer order DGAM, ONS (correction 1, MoD SEGINFOEMP page); unknown cost adds REQ-RID.
- `test_readiness_profiles.py` + fixture: verdicts computed as the API does; the 5 Spanish profiles add `ES-MOD: conditional` with
  the stated reason (RID not asked).
- `test_readiness_export.py`: the ES fixture adds `ES-MOD: conditional`; the request check covers `es-auto`.
- `web/lib/readiness.check.ts`: the "primary is the Official Journal" assertion now uses an EUR-Lex URL (it used example.test);
  a national source is checked in `wp64.check.ts`.
- `tests/verify_quotes.py`: skips passages with a national `url` (they are checked against the research file by the unit test).

Runs (local, `D:\DEFENCEGATE TESTS\wp64`, Postgres 17 container `dgate-wp64` on port 55464, own venv, TZ=UTC, web mock env of
`.github/workflows/web.yml`): see section 6.

## 6. Results

| Check | Result |
|---|---|
| ruff | All checks passed |
| unit (`pytest`) | 2959 passed, 1145 deselected |
| integration (`pytest -m integration`, Postgres 17) | 1145 passed (10 min 10 s) |
| `tsc --noEmit` | exit 0 |
| `npm run check` (lib checks, incl. `wp64.check.ts`) | all ok |
| `next build` (mock data) | exit 0 |
| Playwright, 4 workers, desktop + 375 px | 452 passed, 40 skipped (the specs' own `test.skip` cases), 0 failed |
| `python -m dgate.readiness.seed --check` | 7 programmes, 15 requirements, 75 rules |

Hostile review of the diff: 6 issues found and fixed before the final runs: ES-MOD shown as "eligible" to non-Spanish companies
(route filter `engine.concerns`); NATO-AQAP-ED made the Spanish route apply to everyone (moved to NATO-SUPPLY only); an unknown
REQ-PECAL status kept ES-PECAL-CERT "unknown" for a company that answered everything (condition simplified to the PA 4302 conditions);
"Quoted from the Official Journal" on BOE and ministry pages (`isOfficialJournal`); the appendix passage of REQ-REOCE would have shown
as an official quote (removed, said in the description); prerequisite order of REQ-PECAL differed between file and database.

## 7. Not checked / limits

- The quotes are checked against the research file, not re-fetched from the sources (no external requests from this run).
- Issuer rows on the requirement pages still say "marked verified in the research notes" (issuers carry no origin); for the new
  Spanish issuers that undersells a 2026-10-20 primary read.
- For a Spanish company the ES-MOD card lists about 19 unanswered questions until WP-65 adds them to the profile.
- `missing` lists the condition's questions even while the applicability question is open (existing engine behaviour, kept).
- Navigation: no new route; nothing to wire. Deletion candidates: none.
