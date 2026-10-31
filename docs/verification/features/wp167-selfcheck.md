# WP-167 self-check: Ukraine's EDF association in force since 16 October 2026; the call document's budget total

Owner decisions of 31 October 2026 on the WP-166 USI check (docs/verification/features/wp166-usi-check.md, rows 4, 7 and 9). Branch
`wp-wp167` from `integration` 849ced5. Test copy `D:\DEFENCEGATE TESTS\wp167\`, Postgres `dgate-wp167` on 56168 (removed at the end).

## Sources read (once, robots.txt respected)

- DG DEFIS news of 16 October 2026 (last updated 18 October 2026),
  `https://defence-industry-space.ec.europa.eu/ukraines-association-european-defence-fund-and-european-defence-industry-porgramme-funding-entered-2026-10-16_en`.
  `robots.txt` disallows only `/core/`, `/profiles/` and a few files. The sentence quoted everywhere, word for word: "The Ukrainian
  association with the European Defence Fund (EDF) and financing under the European Defence Industry Programme (EDIP) agreements have
  come into force." The page's own title spells "Porgramme" (kept as published in the tracker's `source_ref`). Checked with
  `tests/verify_regulation.norm` against the saved page: the quote, the title, "signed on 13 July 2026", "ratification by Verkhovna Rada"
  and "Last updated on: 18 October 2026" are all on it.
- The two USI call documents were not fetched again: their text is stored on production (`call_document_text`), and the budget sentences
  were read from there (read-only SELECT): `call-fiche_edf-edip-usi-2026-ls-ira_en.pdf` "The estimated available call budget is EUR
  184 500 0008" (the footnote number 8 glued to the amount) and footnote "8 including EUR 180 000 000 from voted EU budget";
  `call-fiche_edf-edip-usi-2027-ls-ira_en.pdf` "EUR 82 000 0008" and "including EUR 80 000 000 from voted EU budget".

## 1. The rule and every text

| Place | Before | After |
|---|---|---|
| `backend/dgate/ukraine.py` (the flag) | EDF call: `null`, `edf_association_unconfirmed`, "no text we could read says that agreement is in force" | EDF call open on or after 16 Oct 2026 (Brussels) or without a deadline: `true`, `edf_association`, evidence = the DG DEFIS sentence + Reg. 2025/2653 Art. 3(1). Closed before: `null`, `edf_closed_before_association`, evidence "This call closed before 16 October 2026 ... The EDF call documents of 2026 said: “...pending the signature...”". The call document's reason still comes first (unchanged order). |
| `backend/dgate/verdict.py`, `web/lib/eligibility-check.ts` (the eligibility check) | `ASSOCIATED.EDF.yes = ['NO']` | `['NO', 'UA']`; for UA the reason is `EDF_UA_YES` (with the quote); a call carrying `ukraineBeforeAssociation` (served by `/v1/fit/facts`, set on the call page from `ukraineBasis.reason`) keeps "check" with `EDF_UA_BEFORE`. EDIP untouched (Ukraine is not an associated country of the Programme; the "EDIP financing" of the news is the USI). |
| `backend/seeds/requirements.json` (readiness EDF card) | EDF-ESTABLISH, EDF-EXEC-MGMT: UA conditional; EDF-CONTROL: control from UA/EEA conditional | UA counts as an associated country (`in: [EU, EEA_EFTA, UA]`, no `conditional_when`); EDF-CONTROL met for control from Ukraine or an EEA EFTA state, conditional only for other countries (Art. 9(4) guarantees). Texts say "in force since 16 October 2026", the caveat and note quote the Commission; `last_reviewed` 2026-10-31. |
| `backend/seeds/regulation_tracker.json` | `edf-ukraine-in-force-unconfirmed` (status unconfirmed) | `edf-ukraine-association-in-force` (in_force, event 2026-10-16, source the DG DEFIS page, quote above); `edf-ukraine-legal-basis` links to it |
| `web/lib/ukraine.ts` `ukraineSentence` | "Conditional on the association agreement, not confirmed..." | `edf_association`: "Ukrainian entities may take part in this call: Ukraine is an associated country of the European Defence Fund since 16 October 2026, ..."; closed before (and the old reason name until the re-flag): "This call closed before 16 October 2026, when Ukraine’s association ... entered into force. Its call document said ... pending ...". The call page links the DG DEFIS page next to the evidence. |
| `web/lib/glossary.ts` (open to Ukraine), `web/components/funding/rules-apply.tsx` (basis labels), `web/lib/mock/calls.ts`, generated `web/lib/mock/regulation.json`, `requirements.json`, `web/e2e/fixtures/assess-*.json`, `web/lib/data/wp93-pairs.json`, `wp102-pairs.json` | old wording / old verdicts | regenerated (`dgate.readiness.export`, `dgate.regulation --export`, `tests.wp93_golden derive`, `tests.wp102_golden derive`: the pairs stay 58/58 correct; only the programme verdicts of the Ukrainian profiles moved from conditional to obtain/eligible); the *97 fixtures (not written by the export) got the three rules' new texts |

Decision taken here, consistent with the project's earlier reading (profile p11: "The texts of EDF and SAFE do not mention the area:
SAFE eligible on its rules"): no condition is invented for the non-government controlled areas of Ukraine under the EDF; with the
association in force the EDF is "eligible" for that profile as SAFE is. Tried and reverted: an EDF territory condition (no text says it).

Tests: `tests/unit/test_wp167.py` (open EDF call -> true with the quote, also on the boundary 16 Oct 00:00 Brussels; closed 29 Sep and
15 Oct 23:59 Brussels -> unchanged with "closed before"; the document first; the verdict yes / check-before / EDIP no; web words equal);
`tests/integration/test_wp167.py` (report then write, the old reason re-flagged, a second run writes nothing, `/v1/fit/facts` flag);
updated: `test_wp36`, `test_wp40` (the real EDF calls of the WP-40 export: closed before -> unchanged, read open -> true),
`test_readiness_profiles` (p02 obtain, p10/p11/p30 eligible), `test_readiness_roadmap`, `test_readiness_api`, `test_wp32`, `test_wp91`,
`test_wp73_verdict`, `test_readiness_export`; `web/lib/wp167.check.ts`, `ukraine.check.ts`, `regulation.check.ts`;
`e2e/readiness.spec.ts`, `e2e/wp131.spec.ts`, new `e2e/wp167.spec.ts`.

## 2. The call document's budget total

- Read: `eu_portal.document_budget(text)` -> `{total, voted}` ("estimated available call budget is EUR X", "including EUR Y from voted EU
  budget"; amounts read in groups of three so a glued footnote number is not read). Stored: `call.document_budget` JSONB
  `{total, voted, url}` (migration `0158_wp167_document_budget.sql`, not versioned, derived). Filled by `dgate.ops.call_budgets` from the
  stored call documents only (no request), and nightly in the worker's cascade-flags job.
- Served: `documentBudget {amount, votedEu, currency, documentUrl}` on `/v1/funding` items and `/v1/funding/{slug}`, only where the two
  figures measure the same thing and differ: the document's voted part equals the portal's figure, or the portal's figure is the call's
  (`budgetScope: call`). A topic's budget is never set against a call total. The portal's figure stays `budget`.
- Shown: on the call page under the budget, small type, "Call document total: EUR 184.5 million, including EUR 180 million from the voted
  EU budget." with a link to the call document. Not on the funding list card (WP-88 keeps the card to one budget line; the list API
  item carries the field if the owner wants it there).

Simulated on the production export of 31 October (38 documents with a total, 193 calls, the same parser and serving rule): 82 calls get a
`document_budget`, 2 with a voted part; 4 calls show the line: 118 (EUR 184.5 million, incl. EUR 180 million), 113 (EUR 82 million, incl.
EUR 80 million), and 116 and 117 (`EDF-EDIP-P-2027-LS-IRA-KEC`, `-PE`: the portal's call figure 282,150,000 against the document's
"EUR 275 000 000"; shown as "Call document total: EUR 275 million.").

## Ops for the orchestrator (production; not run by me)

After the deploy (migration 0158 runs with `migrate`):

1. `python -m dgate.ops.ukraine_flags` (report): expected `changed 28`: every call now `edf_association_unconfirmed` (28, all closed
   between 28 Apr and 29 Sep 2026) -> `edf_closed_before_association`, flag stays null; `yes` stays 47 (no open EDF call today); each
   change is logged. Then `--yes`; a second report says `changed 0`. The nightly cascade-flags job would do the same write on its own.
2. `python -m dgate.ops.call_budgets` (report): expected `{'calls': 193, 'with_total': 82, 'with_voted': 2, 'changed': 82}` (counts move
   with new calls). Then `--yes`; a second report `changed 0`. No external call: it reads `call_document_text` only.
3. Check: `/v1/funding/118-...` has `documentBudget.amount` 184500000 and `votedEu` 180000000; 113: 82000000 / 80000000.

## Results

Runs in `D:\DEFENCEGATE TESTS\wp167\` (31 October 2026):

- ruff clean; unit suite green (37 s); integration suite: first full run 1659 passed, 5 failed (expectations of the old rule: reviewed /
  checked dates 2026-10-20 and 2026-10-18, the Ukrainian EDF timing "depends", the "not confirmed" caveats); fixed, and the five files
  that held them (`test_readiness_api`, `test_wp36`, `test_wp40`, `test_wp32`, `test_wp167`) rerun green.
- web: `tsc` 0, lib checks 0 (93 files, `wp167.check.ts` new), `next build` 0, Playwright 319 passed, 7 skipped (readiness, wp131, wp53,
  fit, wp93, wp91, wp92, wp99, wp107, wp125, ux, wp105, wp106, wp112, wp97, wp73, wp64, wp65, wp145-api, wp132-api, routes, wp167; desktop,
  375 px and the fake-API projects), under `web-build.lock`.
- Screenshots: `D:\DEFENCEGATE TESTS\wp167\shots\` (call-document-budget and tracker-edf-ukraine at 1280 and 375 px).

Files outside the brief's list, touched for consistency: `backend/dgate/partners.py` and `readiness/api.py` (the closed-before flag for the
verdict), `web/lib/fit.ts`, `eligibility-pack.ts`, `format.ts`, `types.ts`, `mock/calls.ts`, `mock/calls.json` (a demo document total on
the demo USI call), `web/lib/regulation.check.ts` (its Atom `updated` now reads the newest entry's own check day instead of a literal),
`docs/design/API_CONTRACT.md`. Not changed: privacy and terms texts, migration 0076's historical comment.
