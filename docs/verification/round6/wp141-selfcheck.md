# WP-141 self-check: one answer on who may apply for a saved profile (SEAP 114 and its siblings, 26 October 2026)

Branch `wp-wp141` from `integration` (55092e5). Evidence: `D:\DEFENCEGATE TESTS\verify-oct25\r8-site\text\call114-profile.txt` (lines
308-333), `r8-site\problems.csv` (the 114 row), `wp137-selfcheck.md` (open items, third). Production was read only: one `SELECT` of the
EDIP calls (`call`: id, topic code, status, deadline) through the postgres container with a 30 s statement timeout and a read-only
transaction. No ops module, no migration, no app container entered, no portal called.

## Item

| Before (evidence) | Change | Test | After |
|---|---|---|---|
| 114 (SEAP support) with a saved company profile: the verdict "Blocked by: an established SEAP", while the rows under it said "Who may apply: Check. The call names who may apply: Established SEAP; ... Check the document before you go on." and then "Rule of the programme or the action: Not allowed. an established SEAP." (a lower-case fragment), in the "Check your company" box and in "Your readiness for this call"; the first screen listed "Who may apply: an established SEAP." beside the "Check" row. Cause: `callFit` (web/lib/fit.ts) and its twin `call_fit` (backend/dgate/verdict.py) added the action's blocker (`applicantFit`) to `blockedBy` but kept the document's `entity` row; `verdictLines` printed the blocker as the text after its last ": ". `answersFit` (no profile) had replaced the row since WP-121; the profile path had not. | `callFit` / `call_fit`: where the action's rule on who may apply blocks (`applicantFit` = no), the document's `entity` row is replaced in place by one row `who`, label "Who may apply", verdict no, reason a sentence: "Only an established SEAP may apply to this call." / "Only contracting authorities, international organisations, SEAPs and the EDA may apply to this call." / "Only a SEAP or a group of Member States may apply to this call.", then "Your profile names another kind of organisation."; the document's quote stays with it. A call with no `entity` row (193) or no rules read gets the row first. `blockedBy`, `conditions`, fit and the badge word are unchanged ("Blocked by: an established SEAP"). The boxes list a blocker once: `isLine(b, lines)` (a row of that name, or a row saying no to the rule the blocker names) in `verdictLines` and the first screen (`apply-summary.tsx`). `verdictLines`: a programme blocker whose last part is a lower-case fragment keeps its subject ("Legal entity: a legal person, or ..."). | `lib/wp141.check.ts` (114 as production served it, a company and a SEAP; all 50 profile x call pairs of the verified sets where the rule blocks: one "Who may apply" row, a no, the sentence, no `entity` row, no lower-case reason, the rule not repeated, the badge unchanged; an unread 193; the fragment rule); `tests/unit/test_wp141.py` (the same 50 pairs, the first row on 193, a SEAP on 114 untouched, an unread call); e2e `wp141.spec.ts` (new: first screen, form and readiness box on a saved company profile); `wp102.spec.ts` line 44 now expects the fixed row instead of "Rule of the programme or the action: Not allowed." (the old fragment), and asserts no "Not allowed. <lower case>". | 114 with a company profile: "Who may apply: Not allowed. Only an established SEAP may apply to this call. Your profile names another kind of organisation." in place of the "Check" row, no "Rule of the programme or the action" row for it; the summary still "1 of N lines is a no". |

## Calls where a programme or action blocker meets a document "Check" row

Production's EDIP calls (12): the action rule applies to common procurement (CPA), SEAP support (SA-SEAP) and EDPCI preparation
(CSA-PREP); industrial reinforcement (IRA: 113, 115-118) is open to companies and is not affected.

| Call | Topic | Status | Document row before | Now |
|---|---|---|---|---|
| 108 | EDF-EDIP-P-2026-FNLC-CPA-AMEW | closed | no verdict on a closed call | same rule if shown |
| 109 | EDF-EDIP-P-2026-FNLC-CPA-CDS | closed | no verdict on a closed call | same rule if shown |
| 110 | EDF-EDIP-P-2027-FNLC-CPA-AMDS | open | "Who may apply: Check" | row replaced |
| 111 | EDF-EDIP-P-2027-FNLC-CPA-C5ISRS | open | "Who may apply: Check" | row replaced |
| 112 | EDF-EDIP-P-2027-FNLC-CPA-GNPS | open | "Who may apply: Check" | row replaced |
| 114 | EDF-EDIP-P-2026-2027-FNLC-SA-SEAP | open | "Who may apply: Check" | row replaced |
| 193 | EDF-EDIP-P-2026-FNLC-CSA-PREP | open | no `entity` row; the blocker printed as "Not allowed. a SEAP or a group of Member States." | row added first |

Profiles affected: a company, university or research body (or a profile that names one without the applicant-kind answer), and on SEAP
support any kind but a SEAP. A contracting authority outside the EU on CPA, or on PREP, is a "check" (not a blocker) and keeps the document's
row. Programme blockers of the readiness rules (EDF/EDIP/USI, e.g. a Ukrainian company and EDIP) stay rows of their own ("Rule of the
programme or the action"); their reasons were already capitalised, except the legal-entity rule, which now keeps its subject.

## Tests run (batched scope)

- Regression sets: only `expected` recomputed (scratch script calling `tests.wp93_golden.expected` / `tests.wp102_golden.expected`;
  pairs, facts, assessments and requests untouched): wp93 40 of 240 entries (10 profiles x 110, 112, 114, 193), wp102 10 of 350 (10
  profiles x 111); in each only `lines` changed (`entity` check -> `who` no); fit, shown, word and conditions identical.
  wp93 60/60 correct, 240 call x profile verdicts equal to the API's; wp102 58/58 checkable correct, 350 equal to the API's.
- Web: `tsc --noEmit` clean; every `lib/*.check.ts` passes (new `wp141.check.ts`); one production build; Playwright `wp141.spec.ts`,
  `wp102.spec.ts`, `wp121.spec.ts`, `wp93.spec.ts`, `wp91.spec.ts`, `wp53.spec.ts`, `wp109.spec.ts`, `fit.spec.ts`: 123 passed, 5 skipped by
  their own conditions, 2 failed (the first `wp141.spec.ts`, on demo call 21, which has no form); the spec moved to demo call 1 (as
  `wp102.spec.ts`), then `wp141.spec.ts` + `wp102.spec.ts` 6/6 on the same build.
- Backend (own copy, Postgres 17): ruff clean; unit 4,063 passed (new `tests/unit/test_wp141.py`; `test_wp93.py`, `test_wp102.py` check
  the recomputed `expected`); integration 1,556 passed.

## Files outside this package's area

- `web/components/funding/apply-summary.tsx`: one filter (`isLine`) so the first screen lists the blocker once.
- `web/lib/data/wp93-pairs.json`, `web/lib/data/wp102-pairs.json`: derived `expected` lines only (above).
- `web/e2e/wp102.spec.ts`: the expected text of the row (above).
- Not touched: WP-140's privacy and terms pages and the sign-in switch.

## Open items

- None for this package. The readiness section's own programme block ("European Defence Industry Programme (EDIP): the Programme:
  Blocked ... Who may apply: an established SEAP") is the call-specific assessment and already agrees.
