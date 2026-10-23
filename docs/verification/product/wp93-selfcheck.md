# WP-93 self-check: the funding eligibility answers (production check of 23 October 2026)

Branch `wp-wp93` from `integration` (f400297). Input: `D:\DEFENCEGATE TESTS\elig-check\FINDINGS.md` (two verifiers, 10 company
profiles, 60 checkable (profile, call) pairs read against the official documents: **43/60 correct, almost every error a false
"can"**), with `A\pairs.csv`, `B\pairs.csv`, the page dumps and the saved documents. Owner priority: the product must not say a
company can apply where the call document excludes it. No deploy, no push, no production write, no model call. One read of our own
public site: `GET /api/fit/facts` for the 24 fixture calls (the facts the badge received that day); the quotes come from the
verifiers' page dumps. No official document was fetched; the readings were run on the verifiers' saved copies.

## 1. Score on the regression set

The 60 pairs are `web/lib/data/wp93-pairs.json` (profile answers, call facts as served, what the document says: `can`, `can_if` a
condition, `cannot`, and a word the answer must name where the verifier found a condition missing). Pair A-7 (RAPID for a Spanish
company) was uncheckable and is left out. A pair is correct when the shown verdict is a "no" for `cannot`, a "check" naming the
condition for `can_if`, and a "yes" or a "check" for `can`.

| Code | Facts | Answers | Correct |
|---|---|---|---|
| before (integration f400297), list badge | as served on 23 Oct (no quotes) | version 3 profiles | **43/60** (the verifiers' 43/60) |
| before, call page | as served, with quotes | version 3 profiles | 43/60 |
| after | as served after the fixes and the readings below | the profiles with the WP-93 answers the verifiers' descriptions give | **60/60** |
| after | same | version 3 answers only (nobody re-answered) | 50/60, and none a false "can" or a false "cannot" (the 10 left are "check" where the new answer decides) |

Before: `D:\DEFENCEGATE TESTS\wp93\before\before.check.ts` (the integration branch's lib on the same file). After:
`web/lib/wp93.check.ts` (asserts 60/60 and the version-3 property) and `backend/tests/unit/test_wp93.py` (asserts 60/60 from the API's
verdict). The 17 pairs that changed: A 5, 11, 19, 21, 22, 26; B 28, 29, 42, 43, 44, 49, 50, 52, 56, 58, 60 (B numbered 28-61 in the file).

## 2. The fixes, finding by finding

1. **Closed country lists** (`countryStatus`, web/lib/eligibility-check.ts; the same in backend/dgate/verdict.py). A list of the call's
   own (not the general annexes') that names the Member States and the EEA or other countries one by one and says nothing that opens
   it (associated, third countries, any country) is closed: a country outside it is a "no" (Ukraine on the Digital Europe ECCC calls,
   Norway on the Ukraine Support Instrument, any country outside the Bridging topic's list). A list of the Member States alone stays a
   "check" (it may be a model's short reading of a longer one), as before. "Associated countries" are read per programme from what we
   hold (`ASSOCIATED`): Horizon Europe Iceland, Norway, Ukraine (general annexes; ukraine.py); EDIP Norway yes, Ukraine no (call
   documents; Regulation 2025/2643 Art. 9(1) and 2); EDF Norway. Any other country stays "check whether yours is associated". Norway
   on Horizon is no longer "not an EU Member State, check"; a call that names Ukraine is a yes on the country for a Ukrainian company.
2. **Size and type of applicant** (`sizeRule`, `sizeLine`): SME-only (fewer than 250) and SME-or-small-mid-cap (up to 499) calls,
   counted with the group (Recommendation 2003/361/EC Art. 3-6; EIC WP footnote 39). A university or a public body is a "no", a
   research organisation a "check". A staff count over the limit is a "no", within it a "yes", unknown (group unanswered) a "check".
   EIC Accelerator: the model's "not reserved for SMEs" is replaced by a fixed-pattern reading of the EIC work programme ("a single
   company classified as a SME", note: a small mid-cap for "investment component only" support), so 250-499 is a "check" with that
   condition and 500+ a "no". EIC STEP and STEP Defence: `investor_precommitment` ("The pre-commitment represents at least 20% of the
   total target funding round"), asked in the profile (yes / no / unanswered give yes / no / check). The EIC work programme read for a
   topic is served with scope `programme` (the scheme's own call text, WP-78), so its rules are not softened as general annexes.
3. **Controlling country**: a new question after "controlled from outside the EU" (Ukraine / an EEA EFTA state, or China / Russia or
   Belarus / another country). A China-only clause (`controlKind`: Horizon CL3 BM-01, BM-02, INFRA-03) is a "no" for a China-controlled
   company and a "yes" for others; "cannot submit guarantees" (Bridging 13) a "no" for China, the guarantee route a "check" for others.
4. **Designated-entity calls**: `designated_applicants`, read per topic from the stored call document ("only entities designated ...
   as National Cyber Hubs are allowed to apply", "This topic targets exclusively National Coordination Centres", "The targeted
   stakeholders ... are public bodies acting as National Cyber Hubs"): a "no" ("You are not eligible unless your organisation is
   one"), a "check" for a public body, and a "check" where the topic lets others join a consortium with them (NCC).
5. **One verdict**: `callFit` (web/lib/fit.ts) serves the list badge and the filter (lib/fit-store.ts `fitFor`), the call page's
   first screen ("Can I apply?" shows the saved profile's verdict, through the same store) and its readiness block; `dgate/verdict.py
   call_fit` is the same rules for the API (`POST /v1/readiness/assess` with `call` returns `call.verdict`). The list and the page had
   different inputs: `/v1/fit/facts` served no quotes and no `single_applicant_allowed` (BM-02 blocked in the list, "Possible" on the
   page); it now serves every fact the verdict reads, with its quote. Test: 24 fixture calls x 10 profiles (240) give the same fit,
   word, conditions and line verdicts and reasons from the list's facts, the page's facts and the API.
6. **Calls without rules**: "Can I apply?" says "Rules not read: check the call document", never "Possible". AID pages: RAPID's
   consolidated staff count under 2,000 and the Cyber Defense Factory's staff of French nationality are read by fixed patterns
   (`rule_readings.read_aid_page`, at ingest in `normalise.from_aid`, and by the ops command from the raw store) and served without the
   page's words (AID text is not a served source); a group of 2,000+ is a "no", unknown a "check" naming 2,000.
7. **The 35 % question**: asked as a choice (35 % or less / more / not known; the exact share optional), listed among the unanswered
   questions, in the wizard and on the supplier page; a choice is sent as 35 or 36 (the only rules compare the share with 35).
8. **Over-caution**: control from Ukraine or an EEA EFTA state is a "yes" where the controlling country is itself eligible under the
   call (the USI for Ukraine, the ECCC calls for the EEA EFTA states).
9. **Horizon border topics**: "requires the active involvement, as beneficiaries, of at least 2 Border or Coast Guard Authorities" (and
   INFRA-03's practitioner portfolios) is served as `required_partners` ("Required in the consortium", a "check"), not as who may
   apply; the general annexes' list of who may apply stays.

Profile (browser only, `dg.profile.v1`, block `version` 4; versions 1-3 read): `orgKind`, `headcount`, `inGroup`, `groupHeadcount`,
`controlCountry`, `investor`, `componentBand`. Old answers are kept; an unanswered new question gives "check", never "eligible"
(asserted on all 60 pairs with the version-3 answers). An old profile's size class is still read while the staff count is unanswered.
Wizard step 1 (kind, staff count, group), step 2 (controlling country, investor), step 3 (35 % choice); supplier page (staff count and
group in "Your company"; controlling country, investor and the 35 % choice in "If you also want EU funding").

## 3. Re-run plan on production (orchestrator)

No model call is needed (0 of the USD 5 cap): the readings re-read the text already stored. After the deploy:

```
python -m dgate.ops.rule_readings            # report: every per-topic call_eligibility row and AID call whose facts change, by name
python -m dgate.ops.rule_readings --yes      # write; a second run writes nothing
python -m dgate.ops.cascade_flags --yes      # "who may apply" / "SMEs only" badges from the new facts (the nightly job does it too)
```

The serving fixes (scope `programme`, `required_partners`, quotes in `/v1/fit/facts`) need no re-run. Expected on the report: the EIC
Accelerator row (`sme_only`), the STEP and STEP Defence rows (`investor_precommitment`), the ECCC NATCH, CBCH and NCC rows
(`designated_applicants`), the RAPID and Cyber Defense Factory calls. Not verified on production data: (a) whether the EIC calls are
served from per-topic rows (`<EIC WP>#<topic>`): a document-level row stays `general` and gets no reading, so if the report shows no EIC
row those topics need `python -m dgate.ops.extract_eligibility` per topic (a model call: estimate first); (b) whether the stored RAPID
page holds "effectif consolidé de moins de 2000 salariés" (the fixture uses the verifier's quote): if the report shows no RAPID call it
stays "Rules not read".

## 4. Tests

Local, `D:\DEFENCEGATE TESTS\wp93` (own venv, Python 3.11; Postgres 17 container `dgate-wp93` on 55493; TZ=UTC; web mock env;
E2E_PORT 3093; Playwright 4 workers), final code:

| Check | Result |
|---|---|
| ruff | All checks passed |
| unit (`pytest`) | **3429 passed** (`test_wp93.py` new: the 60 pairs from the API's verdict, the golden file is current, readers on verbatim excerpts, closed lists, association, control, size, designated bodies, the request) |
| integration (`pytest -m integration`) | **1261 passed**, 0 failed (`test_wp93.py` new: the ops tool report / `--yes` / idempotent on stored EIC and DEP texts and an AID raw page, quotes in `/v1/fit/facts`, `call.verdict` of the assessment) |
| `tsc --noEmit` | exit 0 |
| `npm run check` | all ok (`wp93.check.ts` new: 60/60, 240 list = page = API verdicts, version-3 answers never a false can or cannot) |
| `next build` (mock) | exit 0 |
| Playwright, desktop + 375 px | **692 passed, 56 skipped**, 0 failed (`wp93.spec.ts` new: the new questions saved as version 4; the call page's first screen and the list badge say "Blocked by: Country" for a Ukrainian company on an EU+EEA call) |

Tests changed because the behaviour changed on purpose, each with a WP-93 comment: the profile version (3 -> 4) and an unknown version
(4 -> 5) in profile, wp65, wp68 checks and wp65.spec; an SME-only call is "check", not "eligible", until the group is answered (fit,
fit-store checks: the test profiles now say "not part of a group"); a call that names Ukraine is a yes on the country for a Ukrainian
company (wp53); nothing held is "Rules not read", not "check" (wp91); `/v1/fit/facts` carries quotes (integration wp32); the EIC work
programme read for a topic is scope `programme` (integration wp78); BM-03 / BM-01 2027 border authorities are `required_partners`
(wp35, with a new assertion that the general list of who may apply stays); the wizard's size select is the staff-count question
(wp65.spec, ux.spec U7 answers it, fit.spec heading). None deleted, skipped or loosened; `addopts` untouched.

## 5. Privacy, limits, open decisions

- **Privacy**: the browser key is unchanged (`dg.profile.v1`); the block's version is 4 and it holds new kinds of answers: kind of
  organisation, staff-count bands of the organisation and its group, group membership, the class of the controlling country (including
  "China" and "Russia or Belarus") and an investor's pre-commitment. Once answered they go in the assessment request like the other
  answers (not stored, not logged); the size class and the SEAP-partner answer still stay in the browser. docs/DATA_PROTECTION.md
  (readiness paragraph) is updated. /privacy and /terms are untouched: their `dg.profile.v1` sentence covers answers "for example a
  company name, its country and size", not the controlling country by name: wording for the owner.
- The API's verdict reads only what the browser sends: for a version-3 profile without a staff count (its size class stays local) and
  for a SEAP-partner condition it asks ("check") where the browser may already answer. The parity test feeds both the same answers.
- Association lists hold only what a text we hold says (Horizon: IS, NO, UA; EDIP: NO, not UA; EDF: NO); other associated countries
  (UK, CH, IL, ...) stay "check" until the general annexes' Annex A list is in the repo. Open decision: add it from the stored annexes.
- A Norwegian company controlled from "an EEA EFTA state" on a call open to "an EEA member associated to Horizon Europe" keeps a
  control "check" (Liechtenstein is not known to be associated). Correct but cautious.
- Designated-entity readings depend on the call document's layout (topic headings "<code> - <title>", "3. Available budget"); a topic
  whose heading is not found reads nothing (fail closed). CBCH is a "no" for a company (the finding-4 rule); open decision whether a
  company joining a hub's consortium should be a "check" instead.

## 6. Follow-up: designated bodies per topic (production report of 23 October 2026)

The orchestrator's report run of `python -m dgate.ops.rule_readings` on production (not written: 95 rows, 16 to write) gave
`designated_applicants` to every topic of the shared ECCC documents (DEP-10, 11, 12), the open AI4SME and DUALUSE topics included.
Cause: the topic match reused `eligibility._same_topic`, which also takes the call's own code (a prefix of every topic's) and another
year's code for the topic, so a heading or a "For the topic" sentence of the whole call, or of another year, was read for each topic.
Fix: `rule_readings._same` matches only the topic's own code or its abbreviation under the same call prefix (NATCH / NCH), the "For the
topic" paragraph is cut at 600 characters, and the report prints, per row, the value and the matched sentence. Test
`test_a_designated_phrase_is_read_from_the_topics_own_section_only`: a two-topic document with a call-level heading saying "targets
exclusively National Coordination Centres", a call-level and a previous-year "For the topic" sentence and no blank lines: the open topic
reads nothing, the hub topic reads its own "Targeted stakeholders". The verifiers' DEP-11 and DEP-12 give readings for NCC, NATCH and
CBCH only, as before. Re-run: ruff clean; unit (test_wp93, test_wp35, test_eligibility) 108 passed; integration (test_wp93, wp78, wp32,
eligibility) 31 passed; lib checks all ok; next build ok; Playwright 692 passed, 56 skipped. The orchestrator should run the report
again and check each printed sentence before `--yes`.
