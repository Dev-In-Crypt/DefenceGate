# WP-40 self-check: rules and facts fixes, round 2 (V2-B and V2-C U2, U3)

Author: implementer wp40, 18 October 2026, branch `wp-wp40` (from `integration` at 70fa80e). Written by the author of the
change; an independent verifier is to check it again. Subject: `verify2-rules.md` (B1 to B10) and `verify2-ux.md` (U2, U3).
Test database `agent_t`, migration 0084 (0085 not needed). No language model was called, nothing was written to production.

## Primary texts read for this package

All from the Publications Office (CELLAR), one request at a time, two seconds apart, honest client name, from the server:
Regulations (EU) 2025/2643 (Articles 9, 10, 11, 13, 26, 27), 2025/2653 (Article 3), 2025/1106 (Articles 16, 17), 2021/697, 2021/821, 2018/1046,
2024/2509, Directive 2009/43, Common Position 2008/944, Council Decisions (EU) 2025/2134, 2026/444, 2026/1381 and **the agreement with Canada,
OJ L 2026/445** (Article 5 read in full). The call documents are the copies the product holds (`call_document_text`, read 17 and 18 October 2026):
the 10 EDF documents of 2026, the EDIP common procurement (2026, 2027), support-to-SEAP, project-preparation and industrial reinforcement documents,
and the Ukraine Support Instrument documents of 2026 and 2027. The UK statement HCWS1114 was read through the UK Parliament's public
written-statements API (`docs/sources/uk_parliament_statements.md`); the Council's press pages still answer with a bot check and were not read.

`python tests/verify_quotes.py seeds/requirements.json <texts> <appendix>`: **88 passages, 0 not found** (77 before, 11 new; the script now also
checks a passage quoted from a call document, `"document": <url>`). `python tests/verify_regulation.py`: **16 of 17** tracker quotes found word for
word; the 17th (`defence-procurement-directive-proposal`, COM(2025) 823, not changed here) could not be re-fetched from CELLAR under that celex.

## Defect by defect

| Id | Verdict | What was done | Test that fails before |
|---|---|---|---|
| B1 | **fixed** | New profile answer `applicant_kind` (wizard step 1, optional; unanswered is unknown, never "a company"). The kind of action of an EDIP call is read from its topic code (`regime.action_of`: `-CPA-` common procurement, `-SA-SEAP`, `-CSA-PREP`, `-IRA-`). Three rules scoped to a kind of action: `EDIP-CPA-APPLICANT` (Article 11(2) of 2025/2643 word for word, Article 11(3) beside it), `EDIP-SEAP-APPLICANT` and `EDIP-PREP-APPLICANT` (the call documents; origin `call_document`, migration 0084). They are asked only when a call is judged: `POST /v1/readiness/assess` with `call` gives a company `blocked` / `not_possible` on 108-112 and 114, 193, unchanged on 115-117 (industrial reinforcement); the rules block of a CPA call lists the rule, the other EDIP calls do not; the EDIP programme card says it in its summary; the list badge uses a mirror of the rule in `web/lib/fit.ts` (`applicantFit`, tested on the same twelve topic codes). `EDIP-CONTROL` says Article 9(9) exempts the same four kinds (said, not encoded as an exemption: an unanswered question would then count for or against a company). | `test_wp40.py` (action table, rules block, rule text), profiles p31 to p40, `integration/test_wp40.py` (company 108-112/114/193 not possible, 115-117 yes, authority yes, unanswered depends), `fit.check.ts` |
| B2 | **fixed** | `EDF-ESTABLISH` and `EDF-EXEC-MGMT`: condition is the Union and the EEA EFTA states; Ukraine is `conditional_when` with the sentence of the EDF call documents ("Participation of entities established in Ukraine is pending the signature of the association agreement to EDF", 10 of 10 EDF call documents of 2026, footnote to the list of associated countries) and the line "conditional on that agreement, not confirmed". `EDF-CONTROL`: control from Ukraine or the EEA EFTA states (one answer) is conditional. The call-timing says `depends`, not `yes`, while a condition is open. The rules block carries a `caveat`. No primary text says the agreement applies (the Commission's undated page says "has been fully associated"; no Official Journal text, Council decision or notice found), so nothing else was changed. | profiles p02, p10, p11, p15, p30; `test_readiness_roadmap.py`; `test_wp40.py`; integration `depends` for a Ukrainian company on an EDF call |
| U3 | **fixed** | The three places say the same: the EDF card of the readiness results ("Conditional", the rule's text), the tracker entry (`edf-ukraine-in-force-unconfirmed`, now quoting the call documents; legal basis entry cites Article 3(1)) and the call page ("Conditional on the association agreement, not confirmed", the flag's evidence is the call-document sentence). On the EDIP calls the page names the regime next to the programme ("filed here by the portal; the call is under ..."), so call 113 no longer reads as an EDF call that is "open to Ukraine" by chance. | `ukraine.check.ts`, `test_wp40.py::test_an_edf_call_is_unknown...`, `test_the_edf_ukraine_entry...` |
| B3 | **fixed** | `cascade._document_answer`: the sentence decides. A note limits the answer only when it limits which calls (an `only` that is not "only within / up to / subject to ..."), and never when the sentence itself says "for this topic". The topic match uses `eligibility.names_other_topic` (so `DIGITAL -ECCC-2027-...` with a stray space is this topic; call 149). | `test_wp40.py::test_every_call_whose_document_says_fstp...` over 92 stored calls (fixture `wp40_calls.json`), 20 yes / 6 no pinned |
| B4 | **fixed** | The three `*-LEGAL-ENTITY` rules: a legal person is met; a natural person or an entity without legal personality is `conditional`, with the call documents' sentence ("Natural persons are NOT eligible (with the exception of self-employed persons, i.e. sole traders, where the company does not have legal personality separate from that of the natural person)"; the same sentence is in the EDF, EDIP and USI documents, checked in 8 of them). Titles no longer say "not a natural person". The wizard question stays. | profile p06, `test_readiness_fixes.py::test_d2...` |
| B5 | **fixed in code** | The kind of action of the call decides which sentence of the general annexes is about it (`eligibility.action_kind`, passed from `type_of_action`): "Applications for 'Coordination and support' actions may be submitted by one or more legal entities" is not served for a research or innovation action (22 calls lose a wrong `single_applicant_allowed: true`: 21 RIA/IA/JU-RIA and the MSCA doctoral network 77; CSA call 155 keeps it); the general consortium sentence is not served for CSA, TMA, co-fund calls. | `test_wp40.py` (fixture calls 30-37, 59, 138, 140, 155, 43), `test_wp35_eligibility.py` |
| B6 | **fixed in code** | For research and innovation actions the general annexes' minimum of three independent entities from three countries is the floor: a topic that asks for "at least 2 Police Authorities from 2 countries" adds to it. The general sentence (word for word, in all three annexes we hold) is served with the topic's sentence in the note (calls 39, 42, 45, 55, 60, 61, 62, 64, 69 now 3/3; 23 calls that had no general fact now have it). Not applied where the topic says no consortium is needed or a single applicant may apply. The Accelerator's "70 %" is served only for the Accelerator (128-130 lose it; 131, an equity-only call, too). | `test_wp40.py`, `test_wp35_eligibility.py` (`GONE` gains `funding_rate: {131}`) |
| B7 | **fixed** (rule and tracker) | `SAFE-ESTABLISH`, `SAFE-EXEC-MGMT`, `SAFE-ORIGIN-35`: a Canadian company is `conditional` on the terms of the agreement (Article 5(2) and (8), OJ L 2026/445; provisional application from 13 April 2026 by recital (1) of Decision 2026/1381), management in the United States or elsewhere stays blocked. The tracker entry summarises Article 5 and says the entry-into-force notice was not found. **Not changed**: the headline for a US firm as `other_supplier` ("Eligible"): that is correct under Article 16(12) and the card says why; whether the headline should say more is a copy decision for the owner. | profiles p27 to p29, `test_wp40.py` |
| B8 | **fixed** | Five entries: the two stale "not yet part of the readiness check" lines; "Article 1(1)" is Article 3(1) of 2025/2653 (read); "every supplier or subcontractor" is now Article 16(12); the UK entry rests on HCWS1114 of 1 December 2025 (verbatim: "However, we have not been able to conclude these negotiations with an agreement."), status stays `unconfirmed` for what holds after that date; the EDF entry quotes the call documents. One new entry (`edip-common-procurement-applicants`). `safe-canada` summarises the agreement. | `test_wp40.py` (6 tracker tests), `verify_regulation.py` |
| B9 | **fixed in part** | EDIP: the 9 closed calls say "not for the recipient types this call names" with the reason (recipients must be established in the Union or an associated country, Ukraine is not one; Ukraine can take part as a procurement agent's designator, SEAP member, ...); call 114 (the document names Ukraine as a SEAP member) is now unknown, not false. The cyber documents list the eligible countries ("EU Member States ... EEA countries (Norway, Iceland, Liechtenstein)") without Ukraine or associated countries: 15 calls false (`call_document_closed_list`). Horizon topics limited to "legal entities established in Member States and Associated Countries" (7 calls) are true: that sentence and the general annexes' list of countries associated to Horizon Europe (Ukraine among them, wp-14 and wp-15). The evidence of call 113 is the sentence, not one word. **Not decided**: 59 Horizon calls whose held text does not say it stay unknown (by design), and 33, 151, 152 whose own list of countries does not settle it. | `test_wp40.py` (9 tests over the fixture) |
| B10 | **fixed in part** | A condition on the consortium or on a single applicant keeps the badge from "Eligible" (call 78: note on the consortium fact; call 14: "specific conditions for the consortium composition"; call 118: "no consortium is required" is followed by "but a single applicant may apply under a condition: ... Ukraine" in the form and in the badge). The profile's organisation kind feeds the form (`orgTypeOf`: authority, SEAP, EDA, international organisation are public bodies; a natural person is an individual). **Not a defect of the check**: call 16 (NCP network): the document's eligibility section admits "legal entities (public or private bodies)"; the restriction to nominated National Contact Points is in the topic description, which the extraction does not (and by the scope rule should not) read. **Not done**: the Article 11(7) allowance for USI and `USI-INVOLVES-UA` in the rules block (information rules; Low). | `fit.check.ts`, `eligibility-check.check.ts`, `fit-store.check.ts` |
| U2 | **fixed** | `covers()`: a kind of applicant that names a size class below large ("SME company", "Small mid-cap company (up to 499 employees)") does not cover a large company; the verdict is "check" with "Nothing in that list says a company like yours may" (call 131). | `eligibility-check.check.ts`, `fit.check.ts` |

## Prompt version and the live re-read

`PROMPT_VERSION` stays **4**: every B5 and B6 case was fixed in code from the action type, so no prompt text changed and no unit needs a live
re-read. The cost of a full re-read of the held rows would be USD 1.41 (83 call-document rows 1.17, 5 general 0.09, 58 topic 0.15; of the
USD 2.0 left), which a version bump would trigger for every unit. What a prompt change could still improve (B11 and the like, **not in this
package**): call 131 `sme_only`, call 118 `min_countries`, the three natural-person "false" from "limited to legal entities". The smallest set
would be the topic text of 131 (about USD 0.003) and the documents of 118 and 3 (about USD 0.03 each), but they need the bump or a forced
single-unit read stored under a version that does not describe them; that is the orchestrator's decision.

## Counts on a read-only copy of production

Copy: database `agent_t_real` (the `call`, `call_eligibility`, `call_document_text`, `programme`, `source` tables of production, 193 calls, 185 eligibility
rows), the code of this branch against it, nothing written to production.

| | before | after |
|---|---|---|
| cascade flag, yes / no / undecided | 28 / 41 / 124 | **38** / 41 / 114 (10 calls changed: 80 82 85 86 88 95 96 97 104 149) |
| open to Ukraine, yes / no / unknown | 3 / 10 / 180 | 10 / 24 / 159 (yes: 113 118 131 and 7 Horizon; no: 9 EDIP, 15 cyber; call 114 moved from no to unknown) |
| `single_applicant_allowed` true | 42 | 20 |
| calls with `min_entities` / `min_countries` served | 109 / 99 | 131 / 123 |
| `funding_rate` served | 146 | 143 |

Hand check of the changed rows (sentence read in the stored document or topic text): the 10 cascade calls (all say "For this topic, financial
support to third parties is allowed, but only within the set ceiling"), 15 of 15 cyber calls (the list in section 6 of the document names no Ukraine),
the 7 Horizon calls (the topic sentence, and Ukraine in the annex list at line 457 of wp-15), 9 of 9 floors of three, 3 of 3 Pathfinder rates.

## Verification

On the server, test database `agent_t`:

- `ruff check .`: clean.
- Unit suite: all pass (62 tests new in `test_wp40.py`; the profile regression set grew from 26 to 40 profiles, the changed verdicts carry their legal reason in `test_readiness_profiles.py`).
- Integration, the files this change touches (`test_wp40` 6 new, `test_wp36`, `test_readiness_api`, `test_wp35`, `test_wp31`, `test_eligibility`, `test_funding_api`, `test_calls_api`, `test_changes`): all pass. The rest of the suite was not run (see "Could not check").
- Web: `tsc --noEmit` clean; `npm run check` (all `lib/*.check.ts`, one new: `ukraine.check.ts`): all ok in the final run.
- Playwright specs updated (`readiness.spec.ts`: the kind-of-organisation question, "Conditional" for the Ukrainian company's EDF card) and **not run**: no browser on the server.
- The new tests fail on the code before this package: the 61 tests then written, run against the unmodified `integration` backend (with `action_of` stubbed so that the module imports), gave 57 failures; the other 4 pin behaviour that must not change (the NCC note still qualifies a yes). Without the stub the module does not import.

## Hostile review of my own diff

Found and fixed: (1) the first `append_rule` of the seed patch matched the `"rules": [` of a requirement's `extras` and put three rules in the wrong place:
caught by the seed validation, reverted from git, anchored on the top-level key; (2) `names_other_action` dropped every Coordination-and-support sentence when the
call's type was not passed (my own export script): the callers in `funding.py`, `partners.py` and `weekly_digest.py` now pass `type_of_action`; (3) the floor
would have overridden a topic that lets a single applicant apply alone: it now stands down; (4) `ukraine.run` asked for the facts without the topic, so it read the
document-level rows of prompt 3: it now passes topic and action; (5) call 114 became "true" from a SEAP-membership sentence: a participant is not a recipient, it is
now unknown; (6) the migration: the database constraint on `text_origin` rejected the new origin (caught by the integration test; migration 0084); (7) the "yes" of the
call timing for a Ukrainian company with only a PIC to obtain, now "depends"; (8) `fit-store.check.ts` expected a company to be "eligible" on a common
procurement call when the programme verdict fails: changed on purpose (the rule is Article 11(2)), with a second assertion that a company is excluded; (9) a note that
only says where a fact was read ("General rule of the work programme annexes ...") would have counted as a condition on the consortium: stripped (web);
(10) wording: "makes Ukraine an associated country" became "lists Ukraine among the associated countries"; the Canada component limits are given in the agreement's words.

Known limits: the web mirror of `action_of` and of the three applicant rules is duplicated (tested on the same topic codes on both sides); a Norwegian
contracting authority is `conditional` (associated only if Norway applies the Regulation); `third_country_control = ua_eea_only` is one answer for two
different countries, so the EDF reads it as conditional; the Canadian origin rule cannot separate Canadian components from other third-country ones.

## Production commands (for the orchestrator)

1. Deploy the branch. The worker must apply migration `0084_readiness_call_document_origin.sql` (`python -m dgate.migrate`) **before** the API restarts and
   before the worker applies the seed, because the seed has two rules with origin `call_document`. It is additive: it widens a check constraint.
2. The worker applies the readiness seed (44 rules; `reviewed` 2026-10-18) and the tracker (17 entries) on start. A few KB. The content cache turns over in 60 s.
3. Fill the two derived flags at once instead of waiting for the night:
   `cd /opt/dgate/infra && docker compose exec worker python -m dgate.ops.cascade_flags` (report: expect `yes 38`, `changed 10`), then with `--yes`;
   `docker compose exec worker python -m dgate.ops.ukraine_flags` (report: expect `yes 10`, `no 24`, `unknown 159`, `changed` about 62: the evidence of the EDF and EDIP rows is rewritten), then with `--yes`.
   A second run of each changes nothing. Rows touched: under 100 per command; no disk.
4. No model call and no live extraction are needed. Disk: nothing.

## Could not check

- The Playwright specs and a build of the site (no browser, memory).
- The full integration suite: the server was at load 10 to 100 with other packages' suites; the files that touch this change were run.
- The Council's press pages (bot check); the UK position after 1 December 2025; whether the EU-Ukraine association agreement for the EDF or the SAFE agreement with Canada has entered into force (no notice found).
- The wizard in a browser at 375 px (one more radio group, same component as the others).
- `tests/verify_regulation.py` for the COM(2025) 823 entry (unchanged).

## Scratch on the server (for `docs/DELETION_CANDIDATES.md`)

`/root/dev-t` (copy of the branch, `scratch/` with the Official Journal texts under 15 MB, the call documents' text, the fixture export), `/root/run_t.sh`, `/root/runreal_t.sh`, `/root/q_t.sh`, `/root/getdoc_t.sh`,
`/root/*_t.sql`, database `agent_t` in `dgate-ci-db`. The scratch database `agent_t_real` and `web/node_modules` were deleted at the end.
