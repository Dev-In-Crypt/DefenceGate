# WP-109 self-check: funding call verdicts and funding lists (round 4, 24 October 2026)

Branch `wp-wp109` (from `integration` e0d73b7). Test copy `D:\DEFENCEGATE TESTS\wp109\`, Postgres `dgate-wp109` on 55509 (removed at the end).
Evidence of "before": `D:\DEFENCEGATE TESTS\ux-oct24b\NOTES.md` (p09, p08, p05) and the persona folders; the facts production served on
24 October for the calls named (read-only GETs, kept as `web/lib/data/wp109-calls.json`).

## Regression sets

| Set | After |
|---|---|
| WP-93 (60 pairs) | **60/60** (Python `test_wp93`, TS `wp93.check.ts`). `expected` re-derived (`python -m tests.wp93_golden derive`): the only verdict change is the word of 179 for every profile ("Only if your staff are French nationals", item 2); one stored assessment outcome (ES-NSFCC) moved with the engine already on `integration`. Pairs and document answers unchanged. |
| WP-102 (58 checkable) | **58/58** (Python `test_wp102`, TS `wp102.check.ts`); fixture unchanged by the derive. |

Python and TS agree: the new verdict rules (nationality word, size-line sentence) are in both `verdict.py` and `fit.ts`/`eligibility-check.ts`, and
both fixtures compare every call x profile line by line.

## Items

1. **One verdict per call page in every state (SEAP 114, USI 118, EIC 131).** Before: the bare "Can I apply?" box judged the country alone
   (`applySummary`), the "Check your company" form the document alone (`check`): 114 "cannot apply" above "none is a no", 118 form without the
   Ukrainian-partner rule, 131 university "no" below "Possible, with a condition", a 2,000-staff group only "check".
   Change: one verdict function for the page without a profile, `answersFit` (lib/fit.ts): the document's facts (`check`), who may apply to the
   action (`rulesApply.forCompany`) and the programme's rules for the country's group (`rulesApply.byCountry`, the Ukrainian partner among them).
   The first screen and the form share one case (`usePageCase`, components/funding/apply-summary.tsx): untouched with a saved profile both show the
   profile's `callFit`; any changed answer, at the top or in the form, is one case judged by `answersFit` in both. The top asks the country, the
   kind of organisation and, where the rules need it, the Ukrainian partner; the form adds only the questions a call needs: the staff count
   counted with the group (a size rule or a group limit), who controls the company (a restriction and "yes"), the Ukrainian partner. With a
   profile, the country-alone lines carry no second verdict word. Tests: `wp109.check.ts` (114 SME/large/university "no", public body "check";
   118 PL "check" with the partner line, "no partner" -> "Not without a Ukrainian partner", US "no"; 131 university and 2,000+ "no", 250-499 "check";
   a university profile: `callFit` = `answersFit` = "no"), Playwright `wp109.spec.ts` (three cases). After: one word, one icon, top and form.
2. **Cyber Defense Factory (179).** Owner decision: stays in Fits. Its word now names the condition: "Only if your staff are French nationals"
   (`nationalityWord` / `verdict.nationality_word`), not "Nothing known blocks you"; `fitOrder` ranks it with the partner-only calls: after every
   topic match and after the calls without such a condition. **Why the order "did not change" (p05, p08):** the WP-102 sort was CSS `order` only;
   the testers read the page text (`innerText`), which follows the DOM, as a screen reader does. Now `FitList` (fit-badge.tsx) re-orders the
   list itself (stable sort by `fitOrder`, the dual-use heading left out while sorting). Tests: `wp109.check.ts` (word, order), `wp109.spec.ts`
   (first list item in DOM order names the topic), `wp91.spec.ts` (its CSS-order assertion now asserts the DOM order; the reported fault).
3. **Call 39 (CL3).** US-controlled: the restriction names China only; the form asked no controlling country, so "check". Now the form asks
   "From which country is it controlled?" when the answer is "yes": another country -> "yes", China -> "no". The size line drops a sentence
   that is not about size ("Any legal entity, regardless of its place of establishment ..."), both engines (`SIZE_WORDS`). Tests:
   `test_wp109` (control, quote), `wp109.check.ts`.
4. **EIC STEP (25).** The badge, the card and the key facts say "That cut-off has passed; the source publishes no next one yet" for an open call
   past its last cut-off. An equity-only action (type of action HORIZON-EIC-EQU) reads "Expected number of investments" / "Investment per company"
   (funding.eligibility_rows). Test: `test_an_equity_only_action_names_investments_not_grants`.
5. **Funding list and exports.** Status "Open and forthcoming" (`status=open-forthcoming`, API and site); "Universities and research
   organisations" in Who may apply (`who=research`: the call's own facts, `who_apply.research_of` -> `research_may_apply_doc`, migration 0121;
   else EDF and Horizon calls not reserved to public or designated bodies); CSV columns `who_may_apply`, `research_may_apply`, `regime`,
   `open_to_ukraine`, `min_consortium`; EDIP and USI calls under their instrument in the CSV and the Atom feed (`programmeNameOf`); the Atom
   summary names the programme once and gives the budget; call cards show the topic id. Tests: integration `test_wp109` (status, research),
   `wp109.check.ts` (feed), `wp109.spec.ts` (filter, CSV).
6. **Dual-use tag on civil Horizon topics.** The division rule took whole programme parts. `eu_portal.civil_subject`: topic families NEB,
   NATURE, RAISE, EUROHPC, MISS and civil title subjects (healthy ageing, soil, wildlife, biodiversity) are not collected; the STEP defence seal
   still wins. Rows already held are never deleted: `call.out_of_scope` (migration 0121), set by `python -m dgate.ops.wp109_scope --yes`, keeps
   them out of the funding list, `/v1/calls`, the change feed and the digest; their pages still open. Tests: `test_wp109` (5 civil, 4 kept, seal),
   integration (report then write, idempotent, list).
7. **Print of a call page.** The rule texts, the eligibility form and readiness, the source's conditions and the document list are
   `print:hidden`; a printed line gives the page address for them. Test: `wp109.spec.ts` (<= 2 A4 pages; WP-106's own <= 2 test still runs).
8. **Call 113 / Ukraine partners.** CUXS (and CDS) compared with their EDF categories (AIR, GROUND, NAVAL, AIRDEF; AIRDEF) by title, like AMDS
   (`partners.EDIP_RELATED`); a country with 0 organisations is no choice ("Ukraine (0)"); Ukraine partners: the missing space before "Show all
   programmes", an empty keyword result offers "projects since 2014, all programmes" and the open EDF calls' partner lists; "dual-use" in the
   order is narrowed to Cluster 3, Cluster 4's Digital and Space topics and the EIC Accelerator/STEP/defence calls (timber and geochemistry
   projects of CL4 RESILIENCE were ranked as dual-use). Tests: `test_wp41_partners`, `test_wp32_areas` (rows that asserted "names no category"
   for CDS and CUXS now assert the categories: the reported fault), `test_wp109` (relevance).

Additional items (p05):

- **Fits order** - see item 2 (cause: CSS order vs DOM order; tested end to end on the list's DOM).
- **AID calls (179, 188):** "What it funds" shows the agency's own summary held by the connector (`conditions_raw.summary`, Licence Ouverte 2.0,
  marked as the agency's text in its language); budget stays "No total stated by the agency"; the key facts deadline says "Not stated by the
  source". **Slowest call of the CDF page** (production, read-only, 24 Oct ~18:30 UTC): `/v1/funding/179` 0.10 s, related list 0.07 s, fit facts
  0.03 s, partners 0.05 s: the 60 s once was not reproduced at the API (the auditors' load on the web renderer); nothing to fix here.
- Related calls: ranked by the subject words of the topic code and keywords first (CYBER, ECCC ...), then programme and country.
- NATCH vs NCH: the key facts say "The call document writes it ...-NCH" when the document's sentences name the topic with another last part.
- AID name: issuer with its accent (`aid.ISSUER`), programme renamed "AID calls for projects and RAPID" (migration 0121), so the funder line
  says the agency once; RAPID is dual-use in the agency's own words (`aid.regime_of`). Stored rows: ops `wp109_scope`.
- Finnish source in the Funding header: the header gives the time of the latest run, no longer one source's name.
- Next EDF calls: no work programme of future EDF calls is stored, so nothing is said (as the item allows).

## Not done / open

- The "Who may apply" line for a university on 131 stays "check" (the size line is the "no"; the verdict is "no"). Making it "no" too would
  double the blocker in the badge ("and 1 more").
- Ukraine partners "first load empty list once" (p08): not reproduced; the fallback to all programmes is server-side already.
- Funding search synonyms ("cybersécurité" in funding search, p05) belong to the search package.

## Files outside my list

`web/lib/api.ts` (related calls), `web/lib/export.ts` (call CSV), `web/lib/filters.ts`, `web/lib/types.ts`, `web/lib/mock/calls.ts`,
`web/lib/mock/networks.ts`, `web/components/funding/filter-bar.tsx`, `web/components/dg/cards.tsx`, `web/components/dg/deadline-badge.tsx`, `backend/dgate/api.py`, `changes.py`,
`weekly_digest.py` (one `out_of_scope` clause each), `normalise.py` (AID regime and issuer), `sources/aid.py`, `sources/eu_portal.py`,
`network_api.py`. Tests changed where they asserted the reported faults: `e2e/wp91.spec.ts` (CSS order), `tests/unit/test_wp32_areas.py`,
`tests/unit/test_wp41_partners.py`, `tests/integration/test_wp32.py` (CDS/CUXS), `e2e/wp91.spec.ts` ("Ukraine (0)" option), `tests/integration/test_aid_pipeline.py` (issuer without accent); `web/lib/data/wp93-pairs.json`
`expected` re-derived.

## Runs (test copy)

ruff 0; unit 3789 passed; integration 1364 passed; tsc 0; lib checks 59/59 (wp93, wp102 and the new wp109 among them); Playwright full
suite 820 passed, 62 skipped (as before), the new `wp109.spec.ts` included.

Notes: the status radios are laid out in two columns so the folded funding filter form stays within WP-47's 1,700 px with the sixth status;
`who_apply.run` counts a change of the research answer alone as `research_changed` (`changed` keeps its meaning for the WP-92 test);
`tests/integration/test_wp32.py` uses the energetic-components topic for "no category named" (CDS now names one).

## Production

Migration 0121 (additive). After deploy: `python -m dgate.ops.wp109_scope` (report), then `--yes` (out-of-scope flags for the civil topics,
RAPID dual-use, AID issuer accent, `research_may_apply_doc` through `who_apply`). The worker's who-may-apply refresh keeps the research column.
