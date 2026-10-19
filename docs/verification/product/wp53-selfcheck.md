# WP-53 self-check: readiness correctness (19 October 2026)

Branch `wp-wp53` (worktree `C:\Users\DEV\PROJECTS\milgrants\.claude\worktrees\agent-af3091875fba96dc0`), from `integration` 4fbdc87. Inputs: the readiness
findings of `ux-audit-networks.md` (M1 to M5, plan names T4 to T7), `wp42-selfcheck.md` (the USI 118/113 verdict and its open point: the wizard had no
partner question) and the approved plan (section WP-53). Production was read only: one `SELECT id, topic_code FROM call WHERE id IN (...)` and a `\d` of `call_eligibility` through `docker exec dgate-postgres-1 psql`
with `default_transaction_read_only=on` and a 30 s statement timeout, and the stored eligibility facts of the nine open EDF/EDIP calls through the API container's own loopback
(`GET /v1/funding/{id}`, a public endpoint). No write, no deploy, no language-model call, no secret read. The facts are saved as `web/lib/data/wp53-edip-calls.json` (facts, notes, quotes shortened to 60 characters; no personal data).

Where it ran: `/root/dev-w53` (backend, `bash /root/run_w53.sh`, database `agent_wp53` in `dgate-ci-db`) and `/root/dev-w53-web` (web, `node:22-alpine` for
`tsc`, `npm run check` and `next build`; Playwright in a throw-away `node:22-bookworm-slim` container against `next start` of that build on 127.0.0.1:3153).
Never `dev-int` or `agent_int`. Server load was 8 to 17 the whole time (other builders); the web jobs started only when it was below 8 with more than
1 GB available, one worker.

## What was built, per task

### T4: "Not applicable to us" is not "Met" (audit M1)

Cause: the seed wrote the condition of every rule about a requirement as `{"status": "REQ-PIC", "in": ["held", "not_applicable"]}`, so the answer
"Not applicable to us" was `met` with the text of a held certificate ("You have a PIC.") in the EDF, EDIP and EDIP Ukraine cards (3 of 3), and the PIC step was
absent from the roadmap because the roadmap treats it as done.

Change (`backend/dgate/readiness/engine.py`, `backend/seeds/requirements.json`):
- `declared_not_applicable(rule, statuses)`: the rule's `requirement` has the status `not_applicable` and its condition reads that status. The outcome is
  `not_applicable` (a third state: left out of the verdict, the summary `met`, and the roadmap), with its own reason: "You answered “Not applicable to us” for this
  requirement, so this rule is left out of your result. It is not counted as met. If it does apply to you, change the answer." A rule that does not apply for its
  own reason (`applies_when`) keeps its own words (checked first).
- The eight seed conditions on a status (`EDF/EDIP/USI-PIC`, `NATO-NCAGE`, `G-EXPORT`, `G-REOCE`, `G-HSEM`, `G-EXPORT-MIL`) now read `{"status": ..., "is": "held"}`:
  the data says what the engine does. Three `met` texts that said "or have said none is needed" lost that clause.
- Web: the sentence under step 4 says what "Not applicable to us" does; the card lists the rule under "N rules that do not apply to you" with the reason.

Before / after, profile of audit M1 (Ukrainian company, PIC answered "Not applicable to us"): EDF, EDIP and USI rule `*-PIC`: `met` / "You have a PIC." (3 of 3)
-> `not_applicable` / the reason above (3 of 3); verdicts and roadmap unchanged (no PIC step, no `to_obtain`).

Tests that fail without it: `tests/unit/test_wp53_readiness.py` (six T4 tests: the three programmes, summary counts, roadmap for the four statuses, NCAGE and export,
the rule that does not apply for its own reason, no `not_applicable` left in any seed expression), `tests/integration/test_wp53.py::test_not_applicable_is_not_a_pic_the_company_holds`,
`tests/unit/test_readiness_export.py` (the new e2e scenario `ua-pic-na`), `e2e/wp53.spec.ts` (T4).

### T5: no pre-selected executive-management answer (M2)

Cause: `managementSameCountry: true` in the empty profile ticked the radio and was sent as the company's country.

Change (`web/lib/profile.ts`, `web/components/readiness/wizard.tsx`): `management: 'same' | 'other' | ''`, empty from the start; the request sends `null` for an empty
answer, the rule reads unknown, the card says "Needs an answer" with the question and the link to step 2, and `unanswered()` lists it, so "Change my answers" opens there.

**Storage version.** The profile block is now `version: 2` under the same key `dg.profile.v1`. A version 1 block is still read and imported: its `managementSameCountry: false`
becomes `management: 'other'` (with its country), but `true` becomes unanswered, because a stored "same country" cannot be told from the radio that was ticked for the visitor.
Consequence for people who finished the wizard before: one question is open again (the card says which). A block with an unknown version (3, 0) is still rejected. The block is written
back as version 2 at the first change; reading does not write. Fixtures of `e2e/fit.spec.ts`, `e2e/ux.spec.ts` and `lib/fit-store.check.ts` were moved to version 2 with `management: 'same'`
(they stand for "answered"); nothing else in them changed. Old clients that read a version 2 block fall back to an empty profile until their page is reloaded (they reject unknown versions).

Tests: `lib/profile.check.ts` (empty is null, `unanswered`, version 1 migration, version 3 refused, legacy file import), `e2e/wp53.spec.ts` (no radio ticked at step 2; empty and
legacy blocks send `executive_management_country: null`).

### T6: a share outside 0 to 100 (M3)

Cause: `Next` was not blocked, "-5" was turned into "5" and "12345678" cut to six characters by the input filter, an invalid value was dropped in `toRequest`, and the page then said
"3 answers are missing" without a reason.

Change: `pctProblem(value)` (one rule, `parsePct`: digits with an optional decimal part, 0 to 100, comma or point; "1e2", "0x10", "1 000", "-5", "." are invalid) shown inline
as before ("Enter a number from 0 to 100."), now also **blocking Next** and focusing the field; the input keeps what was typed (up to 12 characters) so the error is visible; the
stored value is no longer dropped silently on load. The same for "executive management in another country" with no country chosen (blocks Next, error on the select).
`answerProblems(profile)` lists every stored answer that cannot be used, with its step; the results page and the roadmap print "One of your answers is not used" with the
sentence ("The share of component cost you entered (“150”) is not a number from 0 to 100, so it is treated as not given.") and a link "Change it" to the step.
Not changed: "I am not sure" is reported as missing by the engine (audit m2, a different finding).

Tests: `lib/profile.check.ts` (ten invalid and seven valid values, each: the message, not sent, one problem on step 3, the entered text quoted), `e2e/wp53.spec.ts` (150, -5, abc, 100.5 refused; 20 goes on; the callout on results and roadmap;
no callout for a valid share).

### T7: the roadmap headline (M4)

Cause: `Totals` printed "Free" when the money list was empty and some step was free, ignoring the steps with no stated cost.

Change (`lib/readiness.ts` `costHeadline`, `timeHeadline`, used by `components/readiness/roadmap.tsx`): "Free" only if every step states free; otherwise
"2 steps free, 1 with no stated cost" (money first if some steps state a price: "USD 17,000 to 48,000, 2 steps free, 2 with no stated cost"); the time reads "5 to 20 days, 1 with no stated time",
and "2 steps with no stated time" when none states one (never "no time needed"). Both boxes use their own list (`unknownCost`, `unknownCostWithOptional`).

Before / after on the e2e fixture `assess-ua.json` (3 required steps): "Free" -> "2 steps free, 1 with no stated cost"; time "5 to 20 days" -> "5 to 20 days, 1 with no stated time";
the second box "Free / 5 to 20 days" (the audit's second finding) -> "USD 17,000 to 48,000, 2 steps free, 2 with no stated cost".

Tests: `lib/wp53.check.ts` (15 cases of cost and time), `e2e/readiness.spec.ts` (the three headlines above, exact text).

### T21: the partner question (USI 118/113, EDIP 116/117)

Design. Two profile fields, both optional, unanswered = unknown, both in step 2 ("Ownership and control"):
- `uaPartner` (not asked of a Ukrainian company): "Does your planned consortium include a legal entity established in Ukraine, with its executive management structure there?"
- `seapPartner`: "Does a SEAP (structure for European armament programmes) take part in your planned consortium?"

Engine (Python): field `ua_partner` (`ProfileIn`, `engine.FIELDS`, the request fixtures, `API_CONTRACT.md`). `USI-INVOLVES-UA` is `met` if the country is Ukraine **or** `ua_partner` is true; with `false` it is
`conditional` (text: you can take part only with such a partner); with no answer it is `unknown` and the programme's `missing` names the question (it was a `conditional` that said "this check does not know" before).
The SEAP condition is not an engine rule: it is a sentence of the call documents ("a single applicant cannot apply unless a SEAP participates", for actions within Article 12(1)(d) of the EDIP Regulation), and no regulation text with a verbatim quote was added.

Mirror (TypeScript, `lib/eligibility-check.ts`, `lib/fit.ts`): `partnerLine(facts, profile)` reads the notes of `single_applicant_allowed`, `consortium_required`, `min_entities` and `min_countries`, sentence by sentence.
A sentence is a Ukrainian-entity condition, a SEAP condition, harmless ("This is the minimum for the topic"), or other. The line is "yes" only if there is at least one condition of the first two kinds, none of "other"
(in the single-applicant and consortium notes), and the saved answers meet each. Otherwise it is the same "check" as before, with the sentence "Your answers do not say whether ..." or "You said no ... takes part ...". A partner answer never gives "no".
A Ukrainian company meets the first condition only with its executive management in Ukraine.
Two more notes kept calls 116 to 118 and 113 and 117 from ever being "yes", and are now set aside when the saved profile answers what they are about (`entityNote`, `countryNote`): sentences that are exceptions for kinds of
applicant the profile is not (natural persons and entities without legal personality when the legal form is "a legal person"; international organisations and SEAPs as applicants when the kind is "a company or research body"), the
non-government-controlled areas of Ukraine (a company established elsewhere, or a Ukrainian one that said it is not in one), and "executive management established in an eligible country" (when the call names the country of the answer).
Each applies only if its answer was given. The "Can you apply?" form of the call page does not carry any of these (its `more` is dropped as soon as the visitor edits a field).

**Result: how many of the 9 open EDF/EDIP calls can reach "yes" for a fully matching profile** (Polish small company, legal person, company or research body, executive management in Poland, not controlled from outside,
PIC held, Ukrainian entity in the consortium, SEAP in the consortium; document side plus the rule on who may apply; run with the old and the new `lib/` on the same nine stored fact sets):

| Call | Topic | What decides | Before | After |
|---|---|---|---|---|
| 118 | EDF-EDIP-USI-2026-LS-IRA-MAB | Ukrainian entity and SEAP (or three entities) | check (entity, country, partners) | yes, with both answers |
| 113 | EDF-EDIP-USI-2027-LS-IRA-CUXS | Ukrainian entity | check (country, partners) | yes, with the Ukrainian partner |
| 116 | EDF-EDIP-P-2027-LS-IRA-KEC | SEAP (or three entities) | check (entity, partners) | yes, with the SEAP |
| 117 | EDF-EDIP-P-2027-LS-IRA-PE | SEAP (or three entities), executive management in an eligible country | check (entity, country, partners) | yes, with the SEAP and executive management in a named country |
| 114, 193, 110, 111, 112 | SEAP support, project preparation, common procurement | applicant kind | no | no (open to SEAPs and contracting authorities, not to a company) |

**Before: 0 of 9. After: 4 of 9** (all the calls open to a company). Without the partner answers it stays 0 of 9 (each line is "check" and says which question is open). For the programme side (the API, not the document):
`tests/integration/test_wp53.py::test_the_four_calls_open_to_a_company_can_say_you_can_apply_now_once_the_partner_is_named` posts the same company with each call: the USI calls are `eligible` / `realistic: yes` with the Ukrainian partner and `depends` without or with "no";
the two EDIP calls are `yes`. A "yes" for 118 needs the SEAP answer too, on purpose: its note says that without a SEAP three independent entities are needed for such activities, and the profile does not know the number of entities.

Tests: `lib/wp53.check.ts` (the sentence classes on the real notes; the needs of each of the nine calls; the count above; each answer on each call; "no" and "unsure" stay check; the notes that stay when an answer is missing; a Ukrainian company with management elsewhere stays check;
the old behaviour without `more`), `lib/profile.check.ts` (request field, UA company not sent, no SEAP in the request), `lib/fit.check.ts`, `backend/tests/unit/test_wp53_readiness.py` (4 T21 tests), integration (3 tests), `e2e/wp53.spec.ts` (the questions at step 2, stored, `ua_partner: true` in the request, no SEAP in the request, none for a Ukrainian company).

### Focus after "Mark as done" (M5)

`components/readiness/roadmap.tsx`: after a mark, the plan is asked again; when the re-scored plan arrives, focus moves to the heading of the step that follows the one marked (the previous one if it was last, the link
"Back to my results" if none is left; the headings have `tabIndex=-1`), and a `role="status"` region (always in the page) says "PIC (Participant Identification Code) is marked as done. 4 steps are left. Your results are re-scored."
"Mark as started" keeps the card, so focus goes to its "Mark as done" button (the pressed button is gone). If the assessment fails, nothing is moved. Test: `e2e/readiness.spec.ts` (roadmap of the Ukrainian company: heading `REQ-NCAGE` focused, exact status text).

## Hostile review of my own diff

Issues found and fixed (9):
1. The first draft of the "declared not applicable" check ran before `applies_when`: a rule that does not apply for its own reason would have shown "You answered ..." (fixed: the flag is returned only after `applies_when`; test).
2. Three `met` texts kept "or have said none is needed" after "Not applicable" stopped counting as held (reworded).
3. The percentage input removed characters as typed ("-5" became "5", digits were cut), and `Number()` accepted "1e2" and "0x10" (one regex now; tests).
4. A version 1 block with `managementSameCountry: true` would have been migrated to "answered": the very bug (kept unanswered, documented above).
5. The call page's form is seeded from the saved profile; with the new `more` it would have applied the saved legal form and partners to a case the visitor edited: `more` is dropped on the first edit.
6. The sentence splitter kept the ";" and my "harmless" pattern missed "This is the minimum for the topic;" (found by the new check).
7. A Ukrainian company met "an entity established in Ukraine with its executive management there" by country alone: it now needs the management answer too.
8. `parseProfile` dropped an invalid share without a word on load: it is kept (12 characters) so that the problem can be shown.
9. The seed note on `USI-INVOLVES-UA` ("met") said "Your company is established in Ukraine" for every case, wrong for the partner: reworded for both.

Found and not fixed:
- The audit's m2 (an "I am not sure" is reported as "1 answer is missing") and m1 (Conditional text on USI does not mention the registration still to obtain) are other findings and were not in this package.
- The SEAP and Ukrainian-entity conditions are recognised by the wording of the notes the model extracted (five patterns, checked on all nine stored sets). A new call whose note is phrased differently stays a "check": the safe side. The fact store is not corrected for call 131 (`sme_only`), as in WP-42.
- The "Can you apply?" form on the call page has no partner question of its own beyond "Do you already have consortium partners?"; the badge of the list and the saved profile carry the new answers, the form does not.
- I did not measure the effect on the other open calls (Horizon, Digital Europe, national): the new code reads only the notes of the four partner kinds and the exceptions listed above, and only for a profile that answered the matching question.
- A profile finished before this change has one open question (executive management) and its Ukraine Support Instrument card asks for the partner: expected, not a defect.

## Tests

Server, `bash /root/run_w53.sh` on the final tree (ruff, then `pytest`, then `pytest -m integration`, each `-q -p no:warnings`, which prints no summary line): ruff "All checks passed!"; 2,849 unit and 1,091 integration tests collected; both runs ended at 100 % with no `F`, no `E` and no skip in the output (the integration run starts only if the unit run exits 0). A first full run of the tree before the last test edits had one failure, `test_wp40.py::test_wp42_r1_...` (it pinned `openConditions == ["The action involves Ukraine"]` for a company with no answer about a partner; updated to the three cases and re-run with `test_wp53.py`, green). The existing expectations that changed on purpose, all about "no answer about a Ukrainian partner" being `unknown` and no longer `conditional`: `test_readiness_fixes.py` (R1 rule), `test_readiness_roadmap.py` (two), `test_wp40.py` (one); the 40 profile fixtures and their verdicts are unchanged. Tests added: unit `test_wp53_readiness.py` (10 functions, 12 collected cases), integration `test_wp53.py` (4).

Web, final tree: `tsc --noEmit` exit 0 (before the last two logic edits; `next build` type-checks the whole project and passed after them); `npm run check` 23 files: 22 passed at the first run, the 23rd (`wp53.check.ts`) failed on the "harmless" pattern (issue 6, fixed) and passed on its own run together with `profile`, `fit`, `eligibility-check` after the fix (I did not repeat the 12-minute full `npm run check` after the last two edits); `next build` ok (the `/readiness`, `/readiness/results`, `/readiness/roadmap` routes build).
Playwright, `--workers=1`, desktop (1280) and mobile-375, against `next start` of the final build: `e2e/wp53.spec.ts`, `e2e/readiness.spec.ts`, `e2e/ux.spec.ts`, `e2e/fit.spec.ts`: **100 passed, 2 skipped** (the two skips are the menu tests that run only at the other width, `ux.spec.ts:336` and `:322`), 0 failed. A first run of the new spec (desktop) had 2 failures in my own test script (a legacy block is not rewritten on read; the init script re-saved the profile on navigation), fixed in the script; a second run at both widths failed 102 of 102 because the throw-away container lacked the system libraries of Chromium (not a test result), fixed by installing them in each run.

## What I could not run

- The full `npm run check` after the last two logic edits (a partial run of the four affected checks passed). Everything else of the web ran on the final tree.
- The other e2e specs of the site (layout, routes, wp45, wp46, wp48...) were not run, by the request (readiness specs) and the load of the server; they do not touch the files changed here except `e2e/fit.spec.ts` and `e2e/ux.spec.ts`, which ran.
- No check against production data beyond the nine stored fact sets: no live call of the API with the new field (nothing is deployed; the production API still rejects `ua_partner` with a 422 until the new image runs). **Order of deploy: API image first (it accepts the field), then the web.** The worker applies the changed readiness seed (the new condition of `USI-INVOLVES-UA`, the `is held` conditions and the reworded texts) on start, as in WP-42; until it has, the engine still gives the T4 behaviour (it does not depend on the seed) and `ua_partner` is accepted but the old seed condition ignores it.

## Production commands for the orchestrator (I ran none)

None are needed for data. After the deploy: restart the worker (it applies the seed), then `GET /v1/readiness/programmes` should list `ua_partner` in `fields`, and `POST /v1/readiness/assess` with a Polish company and `"ua_partner": true`, `"REQ-PIC": "held"` should give `EDIP-USI` `eligible`.

## Scratch

On the server: `/root/dev-w53`, `/root/dev-w53-web` (with `.next`), `/root/dev-w53-pw` (Chromium for Playwright, 877 MB), `/root/run_w53.sh`, `/root/w53_*.sh`, `/root/one_w53.sh`, `/root/q_w53.sh`, `/root/waitload_w53.sh`, the database `agent_wp53` in `dgate-ci-db`, the container `w53-site`: deleted at the end: the container `w53-site`, `/root/dev-w53-pw` (877 MB), `/root/dev-w53-web/.next` (283 MB), `/root/dev-w53-old` (the previous `lib/` for the before/after count). Left for a re-run, to delete when the package is merged: `/root/dev-w53` (22 MB), `/root/dev-w53-web` (source; `node_modules` is hard-linked to `/root/dev-w48/web/node_modules`, so it costs no disk), the scripts above, and the database `agent_wp53`. Disk free at the end: 5.4 GB.
