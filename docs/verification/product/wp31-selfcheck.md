# WP-31 self-check: funding radar completeness and the weekly digest (17 October 2026)

Branch `wp-wp31` (from `integration`), migrations 0066 and 0067, test database `agent_j`, scratch `/root/dev-j`.
Written by the implementer; an independent verifier checks it again. Where a criterion is not met, it says so.

## What was measured, and how

- Production was read with read-only SQL (`statement_timeout` 30 s) and by fetching our own public pages. Nothing was
  written there. No language model was called (fake clients only).
- The digest and the cascade tool were run against **production-shaped data**: a subset of production copied into the
  scratch database `agent_j` (1,686 notices seen in the week 5 to 11 October with their twins, 5,473 versions, 2,269
  version notes, 239 organisations, all 193 calls, all 38 eligibility documents). `agent_j` was emptied and recreated
  for the final test run.

## Acceptance criteria

### A1. The cascade flag matches a hand check of at least 25 calls: MET (35 calls, 35 right)

How: the 23 calls the brief names (the ones whose stored document list mentions it) were checked against an
independent query (every sentence of `eligibility_text` that holds "third parties" or "FSTP", minus the two annex
titles), and 12 more were checked by reading the quote the flag rests on.

The 23: ids 25, 39 to 59, 140. **Of them 22 mention FSTP only as the title of an annex the portal lists with every
Horizon call ("Information on financial support to third parties (HE)"): not a statement, flag stays undecided
(`not_stated`), which is right.** Only id 56 (HORIZON-CL3-2026-01-SSRI-02) says it in a sentence: "Beneficiaries may
provide financial support to third parties." (flag true, `call_text`). The same query finds three more calls that state
it: 61 and 72 ("must provide", forthcoming) and 63 ("may provide", forthcoming), all flagged true. The other 70 calls
whose `eligibility_text` matches the old pattern (73 in all) mention only the EDF guide title "Guidelines on FSTP
implementation".

| id | topic | flag | reason | evidence | verdict |
|---|---|---|---|---|---|
| 25, 39 to 55, 57 to 59, 140 (22 calls) | Horizon CL3, EIC STEP, EuroHPC | undecided | not_stated | annex title only | right |
| 56 | HORIZON-CL3-2026-01-SSRI-02 | true | call_text | "Beneficiaries may provide financial support to third parties." | right |
| 61 | HORIZON-CL3-2027-01-BM-03 | true | call_text | "Beneficiaries must provide ..." | right |
| 63 | HORIZON-CL3-2027-01-SSRI-03 | true | call_text | "Beneficiaries may provide ..." | right |
| 72 | HORIZON-CL3-2027-01-FCT-03 | true | call_text | "Beneficiaries must provide ..." | right |
| 84 | EDF-2026-RA-MCBRN-DST | true | call_document | "allowed in all topics under this call ... Annex 4" | right |
| 107 | EDF-2026-LS-DIS-NT | true | call_document | "(FSTP) may be included as part of any proposal." | right |
| 117 | EDF-EDIP-P-2027-LS-IRA-PE (open) | false | call_document | "(FSTP) is not allowed." | right |
| 121 | DIGITAL-2026-BESTUSE-RSF-10-AWARENESS | true | call_document | "at least 60% of their proposed budget to the financial support to third parties" | right |
| 122 | DIGITAL-2026-BESTUSE-MCP-10-HUB | true | call_document | "Financial support to third parties is allowed." | right |
| 123 | DIGITAL-2026-BESTUSE-10-EHDS | true | call_document | allowed in DIGITAL-2026-BESTUSE-10-EHDS (topic code in the quote is this call's) | right |
| 124 | DIGITAL-2026-BESTUSE-10-NETWORKSICs | undecided | call_document_other_topic | the quote names EHDS only | right (the document says nothing for this topic) |
| 126 | DIGITAL-2026-SKILLS-10-NATIONAL-COALITIONS | true | call_document | allowed in this topic and EDTECH | right |
| 148 | DIGITAL-ECCC-2027-DEPLOY-CYBER-11-AI4SME (open) | undecided | call_document_other_topic | allowed in the NCC topic only | right |
| 149 | DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC (open) | true | call_document | allowed in this topic | right |
| 191 | DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NATCH (open) | false | call_document | "is not allowed." | right |

Whole production data (read with the real code): 193 calls, **38 true, 38 false, 117 undecided** (34 true and 38 false
from a document fact, 4 true from a sentence of the text, 8 undecided because the document names other topics, 109 with
no statement). A second run changes nothing (`changed 0`). **Among the calls open today only 2 are true** (56 and 149);
3 more are forthcoming (61, 63, 72). That is what the data says, not a bug: most open EDF calls are EDIP calls where
FSTP is not allowed.

Not checked: a call whose text says it in other words than the regular expressions know ("subgranting", a
translated text). Those stay undecided; the flag is never a "no" without a sentence or a fact.

### A2. The digest of a past week reproduces the counts of /changes for that window: MET on the subset; by construction on the full archive

The digest calls `changes.build_events` over exactly Monday to Monday. On the production subset, for the week
2026-W41 (5 to 12 October): the 14-day list as `/v1/changes` computes it, cut to the events inside the week, gives
**598 new and 66 amended**; the digest gives **598 and 66**. The funding half: 5 calls new in the week in both.
`calls closing within 14 days`: 1 in the digest, 1 by a direct count on production (call 173, deadline 20 October).
Integration test `test_the_digest_of_a_week_has_the_counts_of_the_change_list_for_that_window` pins the same equality
and that notices seen before or after the week are not in it.

Limit of the check: the subset holds the week 5 to 12 October only, so earlier weeks (37 to 40) were not compared with
a full /changes window. The three EXPLAIN runs below cover their cost.

Hand check, 12 tender rows of the issue (random, seed 31) against production: 8 "new" notices (ids 146529, 146532,
146539, 146542, 146550, 146551, 147012, 147015): each first observed 10 or 11 October, published 7 to 10 October,
buyer a defence ministry or a military unit: **8 of 8 right**. 4 "amended" (2666 status Open to Awarded, 3410 status
Open to Awarded, 146289 deadline 22 to 26 October, 146296 status Open to Awarded): each has a version in the week
whose changed fields are the ones shown: **4 of 4 right**. Calls: ids 174, 179, 187, 188 (French AID pages) and 173
(Vinnova) were first seen on 10 October: right.

Another thing the check turned up: 34 calls were first seen in that week and only 5 are listed as new. The other 29
are closed today, and `/v1/changes` already says "a call already closed is not news"; the digest follows that rule, so
a digest rebuilt later can list fewer new calls than one built on the Monday. The worker stores each week for two
more days after it ends and then keeps it as it was.

### A3. The Atom feed validates: PARTLY (checked structurally, no online validator run)

`/digest.atom` builds one entry per week (the last four). Checked: well-formed XML (ElementTree), the elements RFC 4287
requires (feed `id`, `title`, `updated`, `author`; entry `id`, `title`, `updated`, `link`, `summary`), ids unique and
stable (`tag:` URIs by week and country), `updated` in RFC 3339 with `Z`, markup in titles escaped, no control
characters, conditional requests (ETag, Last-Modified, 304). The same checks run in `lib/digest.check.ts` (npm run
check) and in `e2e/digest.spec.ts`. **Not run: the W3C feed validator** (an external service; not called from here).

### A4. Calls without a call document show facts or an honest "not read" state: MET

Production has 75 EU calls with no "Call document". By the deterministic mapping (`eligibility.sources_of`):
67 list the general annexes (3 Horizon PDFs) or the EIC work programme (2 URLs), and 70 have their own conditions text
(sections 3 and 6) that says more than a pointer. 5 calls have only the annexes, 8 only their own text, 62 both; none
has no source (checked: the probe prints no "NO SOURCE" line). The API serves, per call, `eligibilityState`:
`read` (82 of 159 now), `not_read` (77 of 159: the 75 plus 2 call documents not read) and `no_source` for national calls.
The page says "have not been read yet" with links to the sources, never an empty panel. When read, each fact says in
its note that it is the work programme's general rule or this topic's own, and a general rule is never a "no" in the
check form (`lib/eligibility-check.check.ts`).

**Not done: the live extraction** (orchestrator, below). So no fact from these sources exists on production yet, and
no accuracy figure for them can be given. Tested with a fake model: unit mapping tests, and
`test_a_call_without_a_document_gets_facts_from_the_annexes_and_its_own_text` end to end (extraction, quote check,
topic wins over general, the unverified fact is not served, second run reads nothing).

### A5. Every new endpoint timed

Timed on the scratch database holding the production subset (TestClient, cold memory cache, one connection), and
the candidate queries by `EXPLAIN ANALYZE` on **production** (read-only, under the present load):

| Request | Time |
|---|---|
| GET /v1/digest (latest, stored row) | 129 ms (first call), 55 ms |
| GET /v1/digest?week=...&country=FR (stored) | 35 ms |
| GET /v1/digest for a week with no stored row (live build, 598 + 66 events) | `build_all` 0.71 s for all 24 countries |
| GET /v1/digest/weeks | 50 ms |
| GET /v1/funding?status=all (with `cascadeTotal`) | 155 ms for 100 items; 47 ms with `cascade=true` |
| GET /v1/funding/{id} (cascade and eligibility) | 30 and 43 ms |
| production `EXPLAIN ANALYZE`, new-notice candidates, W41 / W38 (history-heavy) / W37 | 171 / 190 / 123 ms |
| production `EXPLAIN ANALYZE`, amended candidates, W41 / W38 / W37 | 281 / 420 / 473 ms |

Budget: the API role has 5 s, the brief asks under 1.5 s cold. Both hold. The full-archive build of an old week was
not run end to end (only its two big queries, above); the worker stores the weeks, so a visitor reads one row. The
funding list's added `count(*)` over 193 rows costs nothing visible.

Web pages (next build, mock data): `/digest`, `/digest/[week]`, `/digest.atom`, `/funding?cascade=true` render and
answer; page timings against the real API were not measured (the web was not deployed).

## The five items

1. **Cascade funding.** `call.cascade` with `cascade_reason`, `cascade_evidence` (migration 0066); `dgate/cascade.py`;
   `python -m dgate.ops.cascade_flags` (report, or `--yes`), nightly in the worker (`cascade-flags`); filter
   `cascade=true` and `cascadeTotal` on `/v1/funding`; badge on cards and on the call page with the sentence; filter in
   the filter bar with its count; glossary entry. Investigation of cascade-call sources: `docs/sources/cascade_calls.md`;
   **no connector built** (no clean, licensed, machine-readable source found; reasons there).
2. **Calls without a call document.** `eligibility.sources_of`, `extraction_units`, scope on `call_eligibility`
   (migration 0067), `extract_eligibility --scope general|topic`, serving by `read_many`. `PROMPT_VERSION` not bumped:
   the system prompt is unchanged; only the line before the text differs for the two new kinds of source.
3. **Weekly digest without e-mail.** `dgate/weekly_digest.py`, `/v1/digest`, `/v1/digest/weeks`, worker job `digest`,
   `digest_issue` table; site `/digest`, `/digest/[week]`, `/digest.atom`; sitemap; documented on `/data`.
4. **Calendar.** Checked `/calendar.ics?kind=funding` on production against the call rows: expected 82 deadline events
   and 25 opening events, got 82 and 25, none missing or extra; every date equals the stored one (81 all-day, 1 timed;
   call 155 has a 00:00 UTC deadline with no precision and is served as a day, which is the portal's date-only stamp).
   **One fault fixed:** a call that takes submissions continuously or in several cut-offs (calls 24 and 114 today) was
   written as "Deadline"; it is now "Latest cut-off" with a note saying so, in the file and on the page. A rolling call
   past its last cut-off is still left out (call 25).
5. **Tests.** See below.

## Tests added

Unit: `tests/unit/test_wp31_cascade.py`, `test_wp31_sources.py`, `test_wp31_weeks.py`. Integration:
`tests/integration/test_wp31.py` (migrations, cascade tool and idempotence, list filter/count/badge, detail basis,
saved-search path, extraction units, extraction with a fake model for general and topic text, precedence, the
call-document call unchanged, the digest: counts equal the change list, calls new/moved/opened/closing, cascade,
country filter, stored equals live, second run no change, 404 and 422 cases, limit, no contact data, timing,
`/v1/changes` unchanged). Worker job list test extended (`cascade-flags`, `digest`). Web: `lib/digest.check.ts`,
`lib/eligibility-check.check.ts` (general rules), `e2e/digest.spec.ts` (digest, atom, cascade filter, calendar file).

Count: 31 unit and 26 integration test functions (several parametrised).

Result of the whole suite on the server (ruff, unit, integration; two full runs): ruff clean, every unit test green,
every integration test green **except one that is not mine and fails on the unchanged code too**:
`test_security_hardening.py::test_the_rate_limit_answers_429_with_a_wait_and_leaves_the_probe_alone` sends 135 requests
and expects a 429 within the minute; with the server at a load average of 7 to 8 (other implementers testing at the
same time) the 135 requests take 12 to 15 s and the limiter's refill lets them through. It passed in my first isolated
run when the load was lower, and fails the same way in `/root/dev-int` (the integration code, without my branch).
Not weakened, not skipped; it needs a quiet server or a faster limiter window to be green, which is the owner's call.

Web: `tsc --noEmit` and `npm run check` (all 11 self-check files) pass in a `node:22-alpine` container; `next build`
passes; `next start` with the mock data answers the new routes. **The Playwright specs were not run** (no browser image
fits the disk: 4 GB free); they are written against the markup by role and label and are run by CI.

## Self-review

Reviewing my own diff as a hostile reader I found and fixed 8 problems:
the EIC calls listed old Horizon annexes as well and were mapped to them (now the EIC work programme wins, and its
two URL shapes are recognised); a negative word list that included "excluded" could turn a yes into a no; the stale
rows of a country that had nothing any more would have kept being served; a topic text could carry an e-mail address
into the model prompt and `call_document_text` (now redacted); a general rule of the annexes could produce a firm "no"
in the check form (now "check"); the calendar called a cut-off a deadline; a stray copy of an owner document had been
created in the worktree (removed); and the digest's own wording
"read from the rules" (now "read automatically"). Six of these have a test that fails without the fix.

## Not met, not checked, risks

- The live extraction for the 75 calls has not run, so the "can you apply" lines for them do not exist yet.
- The Atom feed was not run through the W3C validator; Playwright specs not run here.
- Past weeks 37 to 40 were not compared with a full /changes window; only W41 was (see A2).
- The digest follows `/v1/changes`' default scope, "defence-relevant", which includes supplies to defence buyers
  (office supplies bought by a ministry of defence appear in the sample). That is the existing site rule, not a new one.
- The country filter slices the week's one event list; the rule that shows a national notice once may differ at the
  edges from `/v1/changes?country=`.
- For a week with no stored row, each new country code costs a live build (about a second); the worker stores every
  week once a day, so this only happens before the first run after deploy. The API rate limit applies.
- `eligibility.call_documents()` is no longer used (kept; in `docs/DELETION_CANDIDATES.md`).
