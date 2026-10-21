# WP-73 self-check: fixes from the frontend QA audit (21 October 2026)

Branch `wp-wp73` from `integration` (2ad1862). Audit: `docs/verification/product/qa-full-frontend.md` (main checkout). No model call, no
spending, no production access, no deploy, no push, no migration. Not touched: the files of WP-71 (strip_personal_data, /v1/calls texts,
health, pool, trigger, rate limiter) and WP-72 (indexes, classification, call status, de_bkms, PLACSP dates, organisation resolution),
`header-bar.tsx`, `footer.tsx`, `/privacy` (MJ-6 is the owner's).

## 1. MJ-4: the route verdict follows the rules (engine and TS mirror)

**Where the bug was: the engine.** `assess()` built the verdict from rules of obligation `mandatory` only. Every ES-MOD rule except the
RID is `conditional` (binding where its `applies_when` holds), so HSEM "not met", NSFCC "not met" and three missing answers left the card
"Eligible". The TS mirror (`lib/supplier-roadmap.ts`, the red "needed now") had the same `obligation === 'mandatory'` test.

Fix (`backend/dgate/readiness/engine.py`, `counts()` / `blocks()`): every rule but a `recommended` one counts. Not met: a block, except a
`conditional` rule of kind `contract` (PECAL, EN 9100 for PECAL 2310: what a contract may name), which is a condition. Unknown: conditional.
`roadmap.blockingFor` uses the same `blocks()` (general rules excluded, as before). Mirror: `supplier-roadmap.ts` reads
`obligation !== 'recommended'`. Only ES-MOD and GENERAL are affected: every non-mandatory rule of EDF, EDIP, USI, SAFE and NATO-SUPPLY is
an `info` rule with no condition (checked in the seed).

Tests: `tests/unit/test_wp73_verdict.py` with the audit's profile B (Spanish electronics firm, classified work, supplier page only):
NSFCC not met gives `blocked` (blocking `ES-NSFCC`), the HSEM not asked gives `unknown` with its question; the old request (HSEM sent as
"not held") gives `blocked` by both clearances; missing answers give `conditional`; everything answered and held gives `eligible`; a
contract-kind rule not met is a condition; a recommendation never decides; and a check over every `assess-*.json` fixture that no card
is `eligible` beside a binding rule that is not met or unknown. Changed expectations (behaviour change, documented in each test):
`test_verdicts`, `test_what_beats_what...` (a conditional obligation now counts), `test_readiness_export` and the integration test
(the wizard's ES profile: classified work and "We do not hold it" for the HSEM in step 4: `blocked` by ES-HSEM, previously `conditional`),
`test_wp65_supplier` (the three sample firms' ES-MOD verdict `conditional`; the defence firm has 1 open question, the HSEM).
Lib check `wp73.check.ts` (mirror: a conditional registration that applies is red, a recommended one amber).

Also on the card: the "eligible" meaning of a **route** no longer speaks of the Financial Regulation (m-1, `verdictMeaning()`), and a route
with no programme-wide legal basis says "each rule above names its own source" instead of "No legal basis is stated" (m-2).

## 2. MJ-3: unasked is unknown, never "not held"

- API: `statuses` accepts `unknown` (`AssessIn`); a rule reading it is `unknown` and asks "Do you hold: <requirement name>?" (or the
  requirement's own question). The roadmap reads it as before (a step, "not held" until marked). Documented in `API_CONTRACT.md`.
  A request that does not mention a requirement still reads "not held" (test).
- Web `toRequest`: a requirement of the wizard's step 4 is sent as `not_held` when empty only once step 4 was passed (`step > 4`); before,
  `unknown`. The supplier page's save marks "not held" only what it shows (ISO 9001, EN 9100, AQAP 2110/2310, NCAGE; RID and PECAL for
  Spain). PIC, export authorisation, REOCE and the HSEM are `unknown` for a supplier-page-only firm.
- The HSEM (and the HSES when classified information is stored) is now asked on the supplier page of a Spanish firm with classified work
  (yes = held, no = not held, "I am not sure" = unknown, also after the wizard was finished). Results link the question there.
- Fixtures regenerated (`dgate.readiness.export`): `request-es-sup-*.json` now carry `unknown` for PIC, EXPORT, REOCE, FSC-ES. Stored
  profiles `profile-es-sup-*.json` updated to what the new save writes. wp67: the defence firm's HSEM is amber "Needs an answer" (was red).

## 3. MJ-1: the full CPV vocabulary

- Source: Publications Office, EU Vocabularies, CPV dataset release `20260520-0`, genericode distribution (`Cpv.gc`), retrieved 21 October
  2026. robots.txt of op.europa.eu / publications.europa.eu allows the paths (`Allow: /`); SIMAP answered 429 and data.europa.eu's search
  is disallowed, neither used. Four requests in all, about a second apart, honest User-Agent. Licence CC BY 4.0 (OP copyright notice) /
  Decision 2011/833/EU. `docs/sources/cpv_vocabulary.md` has the twelve questions. Download deleted after conversion.
- `web/lib/data/cpv-full.json`: 9,454 codes, English titles verbatim, 371 KB (94 KB gzip), with `_source`, `_licence`, `_retrieved`,
  `_robots`. The 366 titles of the old selection and every curated product-word title equal the new file (checked).
- Loaded only by `useCpvVocabulary()` (dynamic `import('@/lib/cpv-full')`, a chunk of its own, 371 KB); a lib check proves only
  `lib/cpv-full.ts` imports the JSON and only `use-readiness.ts` imports the module; an e2e proves /tenders does not load the chunk.
  First load of /readiness/supplier 148 → 149 kB, report 160 → 161 kB; other pages unchanged.
- `cpvSearch(query, max, dictionary)`: code prefix; else the curated product words' codes, then every code whose title holds each query
  word as a whole word (either form: "castings" finds "Casting machines"), titles beginning with the word first, broader codes first; at
  most 50 shown with "Add a word or more digits". Results on the full list: casting(s) 2, steel 10, aluminium 10, forging 1, machining 5,
  prefix 4452 18 codes, "gun" no Gunmetal.

## 4. MJ-2: CPV optional

`cpvProblem` refuses only more than 15. Legend "CPV codes of what you make (optional, up to 15)", hint "5 to 15 recommended for the demand
map; no rule of the check reads them". wp65 spec and check updated (an empty or 4-code profile saves).

## 5. MJ-5: wizard-only users

- Results always show a supplier-page button ("Answer the supplier questions" before it was used, "Change my supplier profile" after).
- `askedAt()` links every missing answer to where it is asked: a wizard field to its step, a supplier field or requirement to its
  question, a follow-up ES question to the Spanish questions block (`#sp-spain`, the parent is asked there), a step-4 requirement to step 4.
  Only German questions and similar that no page asks keep a plain line, now "(this check does not ask it; see the rule and its source)".
- The RID rule's text no longer says the questionnaire does not ask: "Say on the supplier profile page (Readiness, Supplier profile)
  whether you hold a current RID certificate ...". (Follow-up questions of an unanswered parent are still listed by the engine: a unit
  test of WP-29 requires the condition's questions with an unknown `applies_when`; they now link to the block where the parent is asked.)

## 6. Minors and nits

| Item | Fix | Test |
|---|---|---|
| m-1, m-2 | route meaning, legal-basis line | wp73 e2e |
| m-3 | ES-PECAL-CERT not-met text: "both ... on your answers at least one of the two is missing" (no claim the user lacks ISO) | seed text |
| m-4 | foreign-owner hint only for Spain; the EEA question asked of every EU firm and sent (EU-CERTIFIED-RECIPIENT reads it) | wp73 check |
| m-5 | roadmap "Undo" after Mark as done/started | build, e2e suite |
| m-6 | `rulesReviewed` = latest review of any rule (2026-10-20) | unit + integration |
| m-7 | /pricing at 375: note under the name, no sideways scroll, row headers top-aligned | wp73 e2e |
| m-8 | /changes past page 100 or past the end: "There is no page N of this list" + "Go to page 1" | wp73 e2e |
| m-9 | /organisations and /suppliers past the API cap redirect to the last page (404 only if page 1 is refused too) | wp73 e2e (mock) |
| m-10 | "Ignored filter" on /changes (week, kind, country, scope), /organisations (country, sort), /suppliers (cpv, sort), /calendar (month in the list view), every list `page=0` | wp73 e2e |
| m-14 | detail 404 pages have an `h1` (`EmptyState level="h1"`) | wp73 e2e |
| m-16 | funding print: `details::details-content` visible in print and a `beforeprint` listener opening closed disclosures; LongText head hidden in print; partner button hidden in print | wp73 e2e |
| n-2 | country checkbox names "DE Germany" (sr-only space) | build |
| n-3 | search placeholder "Title, buyer or number" | build |
| n-5 | general section no longer repeats the card's summary | build |
| n-7 | homologation "does not apply" text no longer speaks of automotive parts | seed text |
| n-8 | a refused import clears the "cleared"/"loaded" status | build |
| n-9 | /pack names the EU programmes, NATO supply and the Spanish route | build |
| n-10 | /alerts and dashboard: "the What changed page lists new calls and moved dates" | build |

Not done (reason): m-11 (count "at least" with scope all: API count semantics), m-12 (/regulation filter in the URL: a client-state change
of its own), m-13 (intermittent hydration error, no reproduction), m-15 (focus return: `header-bar.tsx` is the orchestrator's), m-17
(performance), m-18 (data), n-1 (title casing of buyer names: display-name rules), n-4 (counter timing), n-6 (the API does not know an
"unsure" answer; it is sent as absent), n-11 (feed order), n-12 (merged-buyer links), MJ-6 (owner decision).

Open point for the owner: the wizard's step 4 pre-selects "We do not hold it". A Spanish firm with classified work that passes step 4
without changing the HSEM line is therefore "not held" and its route is **Blocked** by ES-HSEM (the fixture `assess-es.json`). That is
the answer the page shows, so it is not an unasked default; the supplier page now asks it with "I am not sure". Making step 4 start
empty is a UX change across all programmes and is left to the owner.

## 7. Self-review (hostile)

Found and fixed 6: a dangling `else` that dropped the EEA question for non-Spanish firms (caught by the new check); `clearanceAnswer`
preferring a stale page answer over a later step-4 status; "I am not sure" turning into "not held" once the wizard was finished; the
first and later CPV ranking hiding "Parts and accessories for vehicles" (rank by code level, 50 shown); the org/supplier redirect turning a
refused page 1 into a 500 (now 404 as before); a doc comment that tripped the dynamic-import check. No new endpoint, query or grant.

## 8. Results (local, `D:\DEFENCEGATE TESTS\wp73`, own venv, Postgres 17 container `dgate-wp73` on 55473, TZ=UTC, mock env of `web.yml`)

- ruff: clean. Unit: 2,999 passed. `dgate.readiness.export --check`: up to date.
- Integration (`-m integration`): 1,146 passed, 3 failed on the first run (expected-value changes of §1 and m-6), fixed;
  `tests/integration/test_readiness_api.py` then 51 passed.
- `tsc --noEmit` clean; `npm run check` 34 checks ok (new `wp73.check.ts`); `next build` ok.
- Playwright, full, 4 workers, desktop and 375: 493 passed, 47 skipped (the fake-API group, as on integration), 0 failed. New spec
  `e2e/wp73.spec.ts` (8 tests × 2 viewports).
- Not checked: production data (no production access was needed; the engine was run on the generated fixtures and the audit's
  profile); the fake-API group (it has no organisations or suppliers endpoint).

Production commands: no migration. After deploy, reload the readiness seed (`python -m dgate.readiness.seed`, as after WP-64) so that the
three rewritten rule texts (ES-RID unknown, ES-PECAL-CERT not met, ES-HOMOLOG not applicable) reach the database; the verdict logic is code. Scratch: container `dgate-wp73` (removed at the end), `D:\DEFENCEGATE TESTS\wp73`.
