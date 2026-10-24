# WP-102 self-check: eligibility verdicts (round 3, 24 October 2026)

Branch `wp-wp102` (from `integration` 24e5295). Test copy `D:\DEFENCEGATE TESTS\wp102\`, Postgres `dgate-wp102` on 55502 (removed at the end).

## Scores

| Set | Before WP-102 | After |
|---|---|---|
| WP-93 regression set (60 pairs, `web/lib/data/wp93-pairs.json`) | 60/60 | **60/60** (Python `test_wp93`, TS `wp93.check.ts`, 240 call x profile verdicts equal API = browser) |
| New pairs of 24 October (`elig-fresh\A`, `B` pairs.csv), second fixture `web/lib/data/wp102-pairs.json` | **49/58** checkable (code of `integration` on the facts production served on 24 October; the verifiers counted 48, their 49th error was the list/page disagreement of 69, a page fault, item 6) | **58/58** checkable (Python `test_wp102`, TS `wp102.check.ts`, 350 call x profile verdicts equal API = browser) |

The two uncheckable pairs (A22 Chips Japan 133, B24 AID IDEA3 187) stay neither "yes" nor "no" (asserted). A27 (ASTRID 174, no rules held) is "Rules not read" (asserted as `not_held`).
The fixture holds each pair's document answer (`can`, `can_if` with the word the answer must name, `cannot`), the facts served on 24 October
(`/v1/fit/facts`, read-only GET on production), the readings WP-102 adds with their sentences and sources, and the "before" words.
Rebuild: `python -m tests.wp102_golden build derive before <old backend>` (sources: `D:\DEFENCEGATE TESTS\wp102\src`, the stored texts
read with SELECTs on production: `call.eligibility_text`, `call_document_text` of the EIC work programme, the DEP-11 call document, the
Horizon Europe general annexes).

Before -> after on the nine errors: 11 RAISE (consortium of the MSCA DN rule), 14 CS-ECCC-02 (US-controlled: now Blocked), 17 EuroHPC
(guarantee route and own countries), 30 SSRI-01 (15 % cap), 34/39 FCT-05 (police and CSO beneficiaries), 36 PPI (conflict of interest),
42 Pathfinder 130 (no single large beneficiary), 43 research institute 300 on the Accelerator (now Blocked).

## Items (SUMMARY.md WP-102)

1. **Non-company / headcount over the limit on SME and small-mid-cap calls (EIC 24, 131).** Before: a 300-staff research institute got
   "Nothing known blocks you" on the Accelerator (B13); the form's "University or research organisation" and an SME got "The call is not
   reserved for SMEs" on 131. Change (`verdict.check` = `eligibility-check.ts check`): a research organisation of 250+ staff is "no" (not an
   SME, the small mid-cap route is for companies); the form's university is "no"; without a staff count the size line uses the size rule
   (an SME: "The call is for SMEs and small mid-caps (up to 499 staff), and you are an SME"); "Reserved for SMEs" is never a bare "No" on such a
   call (`factDisplay`). Tests: `test_a_research_organisation_of_300_staff...`, `test_the_form_without_a_staff_count...`, wp102.check 5/6,
   `eligibility-check.check.ts` (an assertion that expected the old wording "The call is not reserved for SMEs." for an SME on 131 now expects
   the new one: the old text was the reported fault). After: B13 Blocked by: Organisation size.
2. **Controlled from a non-eligible country with no guarantee route (CS-ECCC 34-37).** Before: "the document allows a way round" because the
   exception pattern matched the verb in "In order to guarantee the protection of the strategic interests". Change: the pattern matches
   "guarantees" (the route) only, in both engines; the topic's Article 22(5) sentence is also read from the portal text with a note "no way round".
   Test: `test_an_article_22_5_clause_without_guarantees...`, integration `test_the_conditions_text...` (assessment API: Blocked by: Ownership
   control). After: A14 Blocked.
3. **Never "Eligible" when a rule is not read (RAPID 188).** Change: `fit_of`/`fitOf` add a "Country: check" line when the call's facts hold no
   rule on where applicants must be established. Tests: `test_a_call_whose_establishment_rule_was_not_read_is_never_eligible`, wp102.check 5;
   `wp53.check.ts` expected call 116 (whose stored facts hold no country rule) to be "Eligible": it is now a check, asserted with its line, and
   the "Ukrainian entity does not matter" assertion moved to 117.
4. **French-nationality staff rule (CDF 179): not changed to a block.** The WP-93 regression pair 60 (an Estonian company on 179) has the
   document answer `can_if` "French" (the rule is about the nationality of the staff, not where the company is established); a block would be a
   false "cannot" there. The line stays "check" and names the rule. Owner decision needed if the badge should hide it from "Fits my profile".
5. **Designated-only NCC (149), public-buyers-only EDIP calls.** NCC: the WP-93 pair 57 has the document answer `can_if` (others join an NCC as
   partners), so it stays a check, but the badge now says **"Only as a partner of the bodies the call names"** instead of "Nothing known
   blocks you" (`PARTNER_ONLY_WORD`), and such calls sort last in "Fits my profile". COORDPREP (145) is read as designated bodies with a partner
   route (`rule_readings.designated`, stored document; ops). EDIP public-buyer calls: a profile that answered "A company" (org kind) without the
   applicant-kind question was "say what kind of organisation you are" (p01, 112); `applicant_fit`/`applicantFit` now read the org kind, so the
   call is Blocked for it in the list and in "Fits my profile". Tests: `test_a_designated_body_call_with_a_partner_route...`,
   `test_coordprep_is_for_designated...`, `test_a_company_profile_without_the_applicant_kind_answer...`, wp102.check 5.
6. **One verdict per call page (SEAP 114, USI 118, NCH 191, BM-01 69).** Before: the "Check your company" box computed its own verdict from the
   document alone ("none is a no") under a first screen that said "cannot apply"; the NCH lines said "your organisation is covered" beside
   "Blocked"; a failed `/api/fit/facts` look-up (a 429) was shown as "Rules not read". Change: untouched, the box shows the saved profile's one
   verdict (`callFit`, through the store) with the programme's lines (`verdictLines`: blocking rules of the programme or the action, and the
   conditions such as "Not without a Ukrainian partner"); changed by the visitor it is another case, as before. A designated-bodies line
   replaces the entity-types line. A failed look-up is `lookupFailed` (asked once more after 4 s), shown as "could not be compared ... reload",
   never hidden by the filter. Tests: Playwright `wp102.spec.ts` (both cases), `fit-store.check.ts`, wp102.check 6.
7. **UA single applicant -> Partners allowed (113).** With the saved profile the box now shows the one verdict, whose partner line is "yes" for a
   company established in Ukraine with its management there (it already was in the list). The bare form without a profile cannot know the
   management country, so it still says "check".
8. **Consortium composition and limits into the verdict.** Read by fixed patterns, each with its sentence (`rule_readings.read_conditions`,
   from the portal's conditions text when the call is served; nothing stored): FCT-05 44 police and civil society beneficiaries
   (`required_partners`, footnote removed), SSRI-01 60 15 % cap (`non_sme_budget_cap`; "non-SME industries" now covers a large company), the
   Article 22(5) clauses, EuroHPC 140 own country list and guarantee route, RAISE 77 -> the MSCA Doctoral Networks rule (consortium of 3/3, the
   MSCA work programme's clause kept in the note with its section). From stored documents (ops): Pathfinder single-beneficiary rule for every
   Challenge topic (128/130, `single_beneficiary_excludes`), PPI Annex H conflict of interest (`procurement_conflict`, served for PCP/PPI
   actions only), COORDPREP. DRS-01 64: kinds the note says are required beneficiaries move to `required_partners` with the involvement
   sentence. Tests: the reading tests of `test_wp102.py` (verbatim excerpts of the stored texts), integration `test_wp102.py`.
9. **Switzerland and Norway associated to Horizon.** `ASSOCIATED.HORIZON` from the Commission's list of participating countries V4.2
   (7 October 2026): the countries associated to the entire programme (Switzerland, Egypt, Türkiye, the Western Balkans ... and Norway,
   Iceland, Ukraine as before), Liechtenstein "does not intend to associate"; the clauses are stored with the list (`ASSOCIATION_SOURCES`,
   both engines). Control from "an EEA EFTA state" is now a check where only some of them are eligible. `test_wp93` expected Switzerland to be
   "check": that row now expects "yes", with LI "no" and GB "check" rows added.
10. **20 % investor in the short block (131).** `applySummary` lists the size limit and the investor pre-commitment (a check). Test wp102.check 6.
11. **Fits sort and "Matches 1 of your topic".** `fitOrder`: with the filter on, topic matches first and the eligible ones first among them;
    calls that need a partner the profile lacks or are partner-only go last. "Matches your topic" for one topic (`topicsLine`); the wp91
    Playwright assertion changed accordingly. Note: CSS `order` changes the visual order, not the reading order of a screen reader (open item).

## Files outside my list

`backend/dgate/partners.py` (`FIT_FACTS`: the three new fact names, so `/v1/fit/facts` serves them); `web/lib/fit-hooks.ts` (no mount for an
empty id); `web/lib/fit-store.ts` (failed look-ups); `web/components/funding/fit-badge.tsx`; tests of other packages updated where they
asserted the reported faults: `web/lib/eligibility-check.check.ts`, `web/lib/wp53.check.ts`, `web/e2e/wp91.spec.ts`,
`backend/tests/unit/test_wp93.py` (one parametrize row), `web/lib/data/wp93-pairs.json` (`expected` re-derived by `tests/wp93_golden.py
derive`; pairs and documents unchanged, 60/60).

## Runs (test copy)

ruff 0; unit 3673 passed; integration 1323 passed; tsc 0; lib checks 0 (all); Playwright full suite 765 passed, 57 skipped (as before).

## Production

No migration. After deploy: `python -m dgate.ops.rule_readings` (report), then `--yes`: writes the Pathfinder, COORDPREP and Annex H readings
into the stored rows (the conditions-text readings need no write). The worker's refresh of `who_apply` and `ukraine` picks up the changed facts.

## Open

CDF and NCC as blocks (owner decision; the WP-93 regression truth says "can only if"); "Fits" reading order (CSS order); the bare form without
a profile for 113; SEAP 114 consortium wording beside "only single applications by a SEAP"; Chips JU Japan appendix not held (A22).
