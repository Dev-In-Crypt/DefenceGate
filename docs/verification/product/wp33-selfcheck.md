# WP-33 self-check: readiness fixes (D1 to D12)

Author: implementer wp33, 18 October 2026, branch `wp-wp33` (from `integration` at fa24892). Written by the author of the
change; an independent verifier is to check it again. Subject: the defects of `verify-readiness.md`.

## Primary texts re-read

All rules were re-read in the Official Journal text from the Publications Office (CELLAR, `publications.europa.eu/resource/celex/...`,
one request at a time, honest client name, from the server): Regulations (EU) 2021/697, 2025/2643, 2025/1106, 2025/2653, 2021/821,
2018/1046 and 2024/2509 (Financial Regulation, Article 197 and 200), Directive 2009/43/EC and Common Position 2008/944/CFSP.
`python tests/verify_quotes.py seeds/requirements.json <texts> <appendix>`: **77 passages, 0 not found** (the 53 of WP-29 plus 24 new).
The checker was made tolerant of one thing only: the Journal prints a footnote mark as "( 39 ) ," and a quote has "(39),".

## Defect by defect

| Id | Verdict | What was done | Test that fails before |
|---|---|---|---|
| D1 | fixed | EDIP and USI origin rules (`EDIP-ORIGIN-35`, `USI-ORIGIN-35`, Art 10(3)-(4) and 27(3)-(4)), restricted-component bans (`EDIP-NO-RESTRICTED`, `USI-NO-RESTRICTED`), the EDIP subcontractor allowance as an information line (`EDIP-SUBCONTRACT-RELIEF`, **Article 11(7)**: the verifier cited 10(7), which does not exist, the Article has six paragraphs), the Ukraine involvement (`USI-INVOLVES-UA`, Art 27(7)). The three Articles count different things as "foreign" (EDIP: outside the Union and associated countries, so Ukraine counts; USI: outside the Union and Ukraine, so EEA EFTA counts; SAFE: neither). A new yes/no answer (`components_from_ua_or_eea_efta`) settles it: a share within 35 % with such components is **conditional**, never eligible | `test_readiness_fixes.py::test_d1_*`, profiles p12 to p16, p19, p20 |
| D2 | fixed | `legal_form` question and `EDF/EDIP/USI-LEGAL-ENTITY`. The definition (2021/697 Art 2, 2025/2643 Art 2) names a legal person or an entity without legal personality as in point (c) of the Financial Regulation; natural persons are point (b) of that Article, which the definition does not cite. Natural person: not met; no legal personality: conditional. SAFE has no such definition for contractors, so no SAFE rule | `test_d2_*`, p06, p18 |
| D3 | fixed | New outcome `to_obtain` (a mandatory rule of kind `registration` not met) and verdict `obtain` ("Obtain first"); `blocked` only for real blocks. Conditional beats obtain; the to-do stays listed (`toObtain`) and in the roadmap. Wording of "Eligible" now says it does not cover the Financial Regulation's exclusion and capacity checks or a call's own conditions | engine tests, `test_a_missing_pic_alone_is_obtain_and_never_blocked`, p02, p03, p24, p25 |
| D4 | fixed | NCAGE issuer rows for all 32 NATO members and the 19 Tier 2 countries of the appendix (name of the bureau not collected, status U); NSPA only for the rest | `test_d4_*`, integration issuers test |
| D5 | fixed | `safe_role` question; `SAFE-ESTABLISH/EXEC-MGMT/CONTROL` apply to the contractor and to a "subcontractor involved" (Art 16(12) quoted); "other supplier": not applicable, its components still count in the 35 % | `test_d5_*`, p21 to p23 |
| D6 | fixed | `G-EXPORT` now dual-use outside the Union (Art 3(1)); `G-EXPORT-INTRA-DU` information line (Art 11(1)-(2), Annex IV); `G-EXPORT-MIL` for military goods (Directive 2009/43 Art 4(1); Common Position 2008/944 Art 1(2): national law says when a licence is required); REOCE follows the licence. Not verified: which authority issues military licences in Germany and Poland (marked UNVERIFIED in the rule and the Polish issuer row) | `test_d6_*`, p04 |
| D7 | fixed | every rule with a condition has `texts.requires` (loader refuses its absence); the requirement page prints it | `test_d7_*`, `readiness.check.ts` |
| D8 | fixed | `statusWords(status, origin)`: a line from the notes reads "Marked verified in the DefenceGate research notes ...; not checked again on this site" | `readiness.check.ts`, `test_d8_*` |
| D9 | fixed | REQ-EXPORT description says what the service does (asks the regime, names the authority for ES, DE, PL; does not decide categories) | `test_d9_*` |
| D10 | fixed | issuer flag `state_route` (migration 0072; ES PECAL, DE Bundeswehr): no vendor price for that country, with a note; `unknownCostWithOptional`, `unknownDurationWithOptional` list ISO 9001; `notAdded` shows the "+30-40 %, 1-2 months" sentence without adding it. Countries with no AQAP row (e.g. FR) still show the vendor range, labelled | roadmap tests |
| D11 | fixed | country must be ISO 3166-1 alpha-2 or `XX`; `EL` is read as `GR`, `UK` as `GB`; the 422 no longer repeats an unknown key's name (`(unknown field)`) | `test_d11_*`, two integration tests |
| D12 | fixed | "a subcontractor", both conditions named, and the dates (published 28 May 2025, in force the next day) | `test_d12_*` |

Not changed, with reason: the wizard's default "executive management in the same country" is a visible, pre-selected radio, not a hidden assumption. A
rule for the Financial Regulation exclusion criteria is **not added** (no verified rule text was read for it); the "Eligible" wording now says so.

## Regression set

`backend/tests/fixtures/readiness_profiles.json`: 26 profiles, the 17 runs itemised in the verifier's section 3 (its report names 14 profiles; the JSON of its
"25 runs" was not handed over, so those are rebuilt from the table) and 9 added for the new rules. `test_readiness_profiles.py` states the legal reason of
every verdict and fails if one is missing. Against the unmodified `integration` code all of them fail or error (the old API refuses the new fields, and the
verdicts of p06 and p16 are the wrong "Eligible" the verifier found).

## Verification

On the server (test database `agent_m`), commit 840acf3 plus this file:

- `ruff check .`: clean.
- Unit suite: all pass (no failure in the run; includes the 26-profile regression set, `test_readiness_fixes.py`, the updated engine, roadmap, seed and export tests).
- Integration suite: all pass except `test_security_hardening.py::test_the_rate_limit_answers_429_with_a_wait_and_leaves_the_probe_alone`, the timing-sensitive test that WP-29 already recorded as failing on the unmodified `integration` code when the server is loaded (load average 40 to 100 during this run). Not caused by this branch; not weakened. The readiness integration file (`test_readiness_api.py`, 51 tests with 3 new) passed on its own.
- Web: `tsc --noEmit` clean; `node scripts/run-checks.mjs` exit 0 (all self-checks, including the extended `profile.check.ts` and `readiness.check.ts`). The Playwright spec `readiness.spec.ts` was updated (legal form, role and component questions, "Obtain first", no vendor price for Spain) and **not run**: no browser on the server. Expect CI to find a locator to adjust.
- Fixtures regenerated with `python -m dgate.readiness.export`; the drift test passes.
- New tests fail on the old code: the profile set and the defect tests error or fail against the unmodified `integration` backend.

## Hostile review of my own diff

Issues found and fixed: (1) the first draft of the SAFE rules asked only for the role when the role was unknown and hid the other questions: `missing` now includes the condition's fields too; (2) the state-route AQAP step still said "you hold ISO 9001, so the range ... is used" with no range: variant and branch note are dropped for it; (3) the `EDIP-CONTROL` quote failed the checker only because of a footnote mark spacing: the checker is tolerant of exactly that; (4) the legal-entity rule would have asked nothing of an old stored profile: the wizard now needs the legal form to go on, and an old stored profile gets "needs an answer" (conditional) until answered, never "eligible"; (5) the USI "foreign" base would have passed a company with EEA EFTA components: the new component question makes that conditional.

Known limits: the ISO 3166 list is typed in once in `readiness/api.py` (checked by a test: 250 entries with XX); a country with no AQAP issuer row still gets the labelled vendor range; the single `components_from_ua_or_eea_efta` answer is conservative for USI when the components are only Ukrainian (conditional instead of eligible); the 35 % rules are not scoped by action type (the note says which Articles); Financial Regulation exclusion criteria are not encoded.

## Production commands (for the orchestrator)

1. Deploy the branch; the worker applies migration `0072_issuer_state_route.sql` (`python -m dgate.migrate`) **before** the API restarts, because the API reads the new column.
2. The worker applies the seed on start (`python -m dgate.readiness.seed`): about 41 rules, 53 + 3 issuer rows changed; the content cache turns over within 60 s. Rows: a few KB.
3. No disk beyond a few KB; no model call.
