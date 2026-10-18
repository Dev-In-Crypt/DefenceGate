# WP-42 self-check: the verdicts of the readiness check after verify3 (18 October 2026)

Branch `wp-wp42` (worktree `C:\Users\DEV\PROJECTS\milgrants-wp42`), from `integration` a8c5365. Inputs: `verify3-fixes.md` (R1, B9, B11) and
`verify3-live.md` (U4, finding 6). Production was read only: public GET of our own site (about 90 requests, at most 1.7 a second), short read-only
SELECTs through `docker exec dgate-postgres-1` with `default_transaction_read_only=on`, and one `pg_dump` of the tables `call`, `call_eligibility`,
`programme` (1.5 MB) restored into the scratch database `agent_wp42_real`. No write, no deploy, no language-model call, no secret read.

Where the work ran: `/root/dev-wp42` and the test database `agent_wp42`, not `/root/dev-int` and `agent_int`, because the WP-43 builder uses those at the
same time and the integration tests truncate tables. The script is `/root/run_wp42.sh`, a copy of `/root/run_int.sh` with the other directory and database.

## 1. R1: "you can apply now" for a company outside Ukraine on the Ukraine Support Instrument

**Cause.** `USI-INVOLVES-UA` (Regulation (EU) 2025/2643, Article 27(7): "carried out by, or with the involvement of, at a minimum, Ukraine or one legal
entity established and having its executive management structure in Ukraine") was an information rule, so a Polish company with every answer given
had the verdict `eligible` for `EDIP-USI`, and `call_timing` printed "No blocking rule is open: you can apply now." The call documents of calls 118 and
113 say the same in their own words (stored facts: `single_applicant_allowed` true with the note "A single applicant must be a legal entity
established and having its executive management structure in Ukraine"; call 118 `min_countries` note "consortia must include at least one legal entity
established ... in Ukraine").

**Change.**
- `backend/seeds/requirements.json`: the rule is `mandatory`, kind `establishment`, `condition` = country is UA, `conditional_when` = country is not UA,
  with `requires / met / conditional / not_met / unknown` texts. A Ukrainian company: `met`. Any other company: `conditional` ("you can take part only with
  such a partner; this check does not know whether you have a Ukrainian partner"). The engine is unchanged: still three-valued and pure. The rule now also
  shows in the "Rules that apply" block of a USI call page, with the verbatim Article (kind `establishment` is a headline kind).
- `backend/dgate/readiness/roadmap.py` `call_timing`: new field `openConditions` (titles of the mandatory rules that are open, not failed). With one open,
  `realistic` is never `yes` and the text names it: "No certificate is missing, but a condition is still open: The action involves Ukraine." (or, when steps are
  also missing, "... A condition or an answer is also still open in the rules (The action involves Ukraine), so this is not a plain yes.").
- Web, same decision: `lib/readiness-types.ts` (`openConditions?`), `lib/call-readiness.ts` (the sentence names the open condition, never "No rule of the
  programme blocks you"). `lib/fit.ts` needed no change: a `conditional` programme is already `check`, and the facts of calls 118 and 113 already gave `check` through
  `singleApplicantCondition`; the two now agree, and a new check proves a USI `conditional` keeps the badge at `check` even when the document facts carry no note.
  `web/lib/mock/requirements.json` and `web/e2e/fixtures/assess-*.json` were regenerated with `python -m dgate.readiness.export` (the existing test
  `test_the_e2e_fixtures_state_the_verdicts_of_the_two_test_profiles` and `--check` keep them in step). `docs/design/API_CONTRACT.md` names the field.

**Before / after (rule engine, every answer given, PIC held):**

| Profile | USI verdict before | after | `call_timing` before | after |
|---|---|---|---|---|
| PL, DE, ES company | eligible | conditional | yes, "you can apply now" | depends, "a condition is still open: The action involves Ukraine." |
| UA company | eligible | eligible | yes | yes (unchanged) |

Fifteen of the 40 profiles in `tests/fixtures/readiness_profiles.json` changed their expected `EDIP-USI` verdict: all non-Ukrainian, only `EDIP-USI`, only
`eligible`/`obtain` to `conditional` (the regeneration script asserted exactly that before it wrote anything). The pinned expectations in
`test_readiness_roadmap.py`, `test_readiness_export.py`, `test_readiness_seed.py` (AQAP never blocks: the assertion now also demands `blocking == ()` and
`to_obtain == ()`) and `tests/integration/test_readiness_api.py` follow the same line. Nothing was removed or loosened; the old "information line" test became a test of the new rule.

**Tests that fail without the change:** `test_wp42_r1_the_ukraine_involvement_is_a_mandatory_rule...` and `test_wp42_r1_a_company_outside_ukraine_is_never_told...`
(unit), `test_wp42_r1_the_ukraine_support_instrument_calls_do_not_say_you_can_apply_now...` (integration, through `POST /v1/readiness/assess` with a call id, and the call
detail), and the checks in `call-readiness.check.ts` and `fit.check.ts`.

**Not done:** the profile has no question "do you have a Ukrainian partner", so a company that has one is also `conditional`. That needs a wizard question (a new profile
field and a rule input): a decision for the orchestrator, not a defect of the verdict.

## 2. The personalised check never says "yes" on the open EDF/EDIP calls

The nine open calls (118, 114, 193, 110, 111, 112, 113, 116, 117) are all EDIP Programme or Ukraine Support Instrument calls that the portal files under the EDF;
no call of the EDF Programme itself is open today. Method: the stored facts of the nine calls (public `GET /v1/funding/{id}`), the programme assessment of a profile that
meets every stated condition (country PL or DE, legal person, company or research body, small or large, not controlled from outside, 0 % outside components, every
certificate held), run through the real `fit.ts` / `eligibility-check.ts` (compiled with tsc in a `node:22-alpine` container; scratch scripts only).

**Result for a company, before and after this package, identical tally: 0 yes, 4 check, 5 no.**

| Group | Calls | What decides | Defect or missing fact |
|---|---|---|---|
| Not open to a company | 114 (SEAP support), 193 (project preparation), 110, 111, 112 (common procurement) | `no`, from the applicant kinds the documents name (SEAP; contracting authorities, international organisations, SEAPs, EDA) | none: `no` is the right answer, a yes is impossible for a company |
| Open to a company | 118, 113 (USI), 116, 117 (EDIP industrial reinforcement) | one `consortium` line each: the document attaches a condition to who applies with whom (single applicant must be Ukrainian, or the consortium needs a Ukrainian entity, on 118 and 113; "a single applicant cannot apply unless a SEAP participates" for Article 12(1)(d) actions on 116 and 117) | **missing fact**: the saved profile has no answer about partners, and the second condition is specific to the topic's activities |

Lines that were not "yes" on those four calls: 14 before, 10 after. The 10 are 4 consortium lines (genuine, above), 3 `entity` lines (118, 116, 117: a note about exceptions for sole
traders or entities without legal personality sits on the "who may apply" fact; irrelevant to a legal person, but I cannot tell it from a real condition without reading the sentence,
so it stays a `check`) and 3 `country` lines (118 and 113: the note excludes the non-government-controlled areas of Ukraine, irrelevant to a Polish company; 117: executive management
must also be in an eligible country, which the profile answers but the line does not use). Removing all six would still leave the consortium line on each of the four, so I did not touch
them: a rule written to drop them would be a guess that manufactures a yes.

For a contracting authority (ES): 110, 111 and 112 are open to it; tally 8 check / 1 no (114: SEAP only), before and after. What is left is the `consortium` line (a single applicant is
allowed only if it is a SEAP) and the condition "A consortium is required: at least 3 legal entities from at least 3 countries. Your profile does not say whether you have partners."
Missing fact again.

**Defects found and fixed in `web/lib/eligibility-check.ts`** (both inflated the "conditions to check"; neither changes today's yes count):
1. The "Ownership control" line for a company that answers "not controlled from outside" took any note on the fact as a condition. The note is a way round the restriction (a guarantee,
   an exemption, a screening) for entities that ARE controlled. It is now ignored for a company that says it is not, and still shown to one that is, or does not know (it uses the existing
   `EXCEPTION` words; a note that is not a way round still counts). It removed 4 lines on the four company calls and 3 on 110, 111, 112 for the authority.
2. `withNote` counted the words the API puts before the note of every fact read from a topic's own text ("Stated in this topic's own conditions.") as a condition, so no topic-scope
   fact could ever be a "yes" (59 of the 185 stored readings are topic scope). `ownNote`, which already stripped the words for the consortium condition, is now used there too. Call 131:
   "Country ... A condition applies: Stated in this topic's own conditions." is gone for both a large company and an SME.

Over all 62 open calls (facts read for 52): PL small company 3 yes / 44 check / 5 no / 10 unknown, DE large company the same, before and after. The three yes are Digital Europe calls 146,
148, 150 (verify3 already noted 146, 148 and 150 read "Eligible" for a large company; I did not read their topic text and did not change them).

## 3. Large company on the SME-only call 131

Call 131 has no call document; its facts come from the topic's own text (stored `call.eligibility_text`, read by me): "The following entities are eligible to apply: A single company
classified as a SME or small mid-cap (up to 499 employees) established in the Union, in Ukraine or in an EEA member associated to Horizon Europe". **The stored fact `sme_only = false` is
wrong against that sentence** (the call is limited to SMEs and small mid-caps). I did not correct it: the fact lives in `call_eligibility.fields` (key `call-text:...`), the code has no
override path, a rewrite is a production write and a re-read is a model call. For the orchestrator: set `sme_only` to true with the note "Small mid-caps (up to 499 employees) are also
eligible" at the next live extraction or by hand. The lines agree now without it.

Fix (`smallKindsOnly` in `eligibility-check.ts`): when the fact says "not reserved for SMEs" but the call's own list of applicant kinds names only size classes below large, a large company
gets the same `check` on the size line as on "Who may apply", in words that do not contradict it. Real facts of call 131, ES large company:

| Line | before | after |
|---|---|---|
| Who may apply | Check, "Nothing in that list says a company like yours may." | unchanged |
| Organisation size | Check, "The call is not reserved for SMEs." | Check, "The call names only these kinds of applicant: SME company; Small mid-cap company (up to 499 employees). It does not name a large company, so check your size class against the document before you go on." |
| Country | Check, "A condition applies: Stated in this topic's own conditions." | Yes, "An EU Member State is eligible under this call." |
| Ownership control | Check (guarantee note) | Yes |

Result for the large company: still `check` (two lines, "Who may apply" and "Organisation size", now saying the same thing), no contradictory line and no empty "condition" line. For an SME: `check` only
because of two real notes (an investor may apply for an SME; small mid-caps are also eligible), before: four lines.

An SME and a call without a small-only list are unchanged (tests). A large company gets `check`, not `no`, on purpose: a company of 250 to 499 staff is a small mid-cap and the profile calls it large.

## 4. Ukraine flag of the EDIP Programme calls

Production today: 9 calls with `open_to_ukraine = false, reason = programme_rule` (108, 109, 115 closed; 110, 111, 112, 116, 117, 193 open); call 114 is already unknown. The task said seven;
the database holds nine. I read the stored call documents (`call_document_text`) behind all ten: the six PDFs (`call-fiche_edf-edip-p-2026-fnlc-cpa`, `2027-fnlc-cpa`, `2026-ls-ira`, `2027-ls-ira`,
`2026-fnlc-csa`, `2026-2027-fnlc-sa`) name Ukraine in other roles ("Associated countries and Ukraine can normally be also part of the SEAP"; "EDA and international organisations ... designated
as 'procurement agent' ... by the EU Member States, EDIP associated countries, Ukraine or a SEAP"; "Ukraine or Moldova are one of the recipients of additional quantities"; "a SEAP that includes
Ukraine as an observer ... will be eligible"), and none of the nine says that a Ukrainian entity may not apply. The "closed" came from Regulation Articles 9(1) and 2 alone, which the document does not say.

Change (`backend/dgate/ukraine.py`): an EDIP Programme call is `NULL / programme_rule` unless the document itself says Ukraine is (not) eligible (that path is unchanged: a negative sentence still gives
`false / call_document`, tested). The evidence keeps the Regulation's sentence and adds "No sentence we hold says whether entities established in Ukraine may apply to this call: its document names
Ukraine only in other roles, if at all." Web sentence (`lib/ukraine.ts`): "Not decided. Recipients of EDIP funding must be established in the Union or in an EEA EFTA associated country, which Ukraine is
not. No sentence we hold says ...". The readiness engine still blocks a Ukrainian company for the EDIP Programme (Article 9(1) is a rule there, with the Article shown); that is a statement about
recipients, the flag is about what the call documents say.

Dry run on the scratch copy of production data (`ukraine.run(write=False)`, 193 calls): before 10 yes / 24 no / 159 unknown; after **10 yes / 15 no / 168 unknown, 9 changed**, all nine
`(false, programme_rule) -> (null, programme_rule)`, nothing else. The cascade flag needed no change: all 12 EDIP/USI calls have `cascade = false` from "Financial support to third parties (FSTP) is not allowed."

Production commands for the orchestrator (I ran none): after the deploy, `python -m dgate.ops.ukraine_flags` in the worker container (report, expect `changed: 9`), then `--yes` (the worker also runs it
nightly). The worker applies the changed readiness seed on start; `GET /v1/readiness/programmes` then shows `USI-INVOLVES-UA` with `obligation: mandatory`.

## Hostile review of my own diff

Found and fixed: (1) the first draft of the control-line fix would have dropped the downgrade for every note; limited to notes with the `EXCEPTION` words (a test keeps a plain note as `check`);
(2) the Ukraine evidence said "the call document does not say", where the code only knows that no sentence it holds says so (not every call has its document read): reworded in code, tests and web;
(3) a stray `or country == "NO"` in my own first test (removed; NO is blocked for the USI by another rule). Found and not fixed, named above: the six irrelevant-note lines on the company calls, the
wrong `sme_only` fact of call 131, the missing partner question.

## Tests

Server, `bash /root/run_wp42.sh` on the final tree (ruff, then `pytest`, then `pytest -m integration`, each with `-q -p no:warnings`): ruff "All checks passed!"; 2,818 unit tests and 1,059 integration tests
passed, 0 failed, 0 skipped, exit 0 (a first full run of the tree before the last wording and `withNote` changes also exited 0; an earlier run found 19 unit and 1 integration expectation that pinned the old "USI eligible for a non-Ukrainian company" verdict, listed in section 1, updated on purpose).
Tests added or changed for this package: unit `test_readiness_fixes` (R1 rule), `test_readiness_roadmap` (call_timing, plus four pinned verdicts), `test_wp36` and `test_wp40` (Ukraine flag, and a case
where the document itself says Ukraine is not eligible), `test_readiness_export`/`_seed`/`_profiles` (pinned verdicts, 15 fixture profiles); integration `test_wp40` (R1 through the API), `test_wp36`
(flag counts), `test_readiness_api` (ES verdicts); web `call-readiness`, `fit`, `eligibility-check`, `ukraine` checks.

Web: `node scripts/run-checks.mjs` in `node:22-alpine` with typescript only: every `lib/*.check.ts` passes except `digest`, `export` and `funding`, which cannot compile without the `next` package in that
light container (TS2307 on `lib/api.ts` and `lib/seo.ts`); they fail the same way on the untouched `integration` tree, and CI (full `node_modules`) runs them. No full `tsc --noEmit` and no Playwright run
(no `next`, no browser on the server).

Scratch: deleted at the end, `agent_wp42_real` (the copy of three production tables) and `/tmp/wp42` (typescript install, JSON of production call facts, logs). Left for a re-run, to delete when the
package is merged: `/root/dev-wp42`, `/root/run_wp42.sh`, database `agent_wp42` in `dgate-ci-db`.
