# WP-35 self-check: eligibility extraction and radar fixes (18 October 2026)

Branch `wp-wp35`, from `integration` (fa24892). Migration 0075, test database `agent_o`, key `wp35`. Scope: the backend defects of
`verify-eligibility-radar.md`; `web/lib/eligibility-check.ts` and the call page were not touched (E1, E2, F6, F7 belong to another package).
No language model was called; the orchestrator runs the live extraction.

## Acceptance criteria and evidence

| defect | what was done | test that failed before | status |
|---|---|---|---|
| E3 high-risk supplier stored as ownership control | `is_supplier_exclusion`: a quote about high-risk suppliers that does not say "controlled from / by" is not an `ownership_control_restriction` (checked when served, so rows already held are covered); prompt v4 says so | `test_a_high_risk_supplier_sentence_is_not_an_ownership_control_restriction` (calls 19, 119), `test_supplier_exclusion`, regression set | met in code; call 6 (restriction does not cover this topic) is prompt-only, see below |
| F1, F2 general annex "where the topic allows" as a firm Yes | `CONDITIONAL_ON_TOPIC`: a general-scope `cascade_funding` or `ownership_control_restriction` is never served; the digest line (`summary_line`) ignores general-scope Yes as well | `test_a_general_annex_sentence_is_never_a_yes_for_*` (8 + 4 calls), `test_the_summary_line` | met; production data: 57 general cascade Yes and 24 general ownership Yes -> 0 |
| F3 single applicant true with consortium required | `reconcile`: consortium true wins, the single-applicant fact is dropped and its note moves to the consortium fact | `test_a_consortium_action_does_not_also_allow_a_single_applicant` (138 140 59 33 36), `test_reconcile_contradictions` | met; contradictory pairs on production data 29 -> 0 |
| F4 facts of the wrong topic | the model is told the topic (code, title) and the row is stored per (document, topic) (`<url>#<topic code>`, migration 0075); `check_quotes` and the serving path refuse a quote that names another topic code and not this one; a quote that names only this topic and says "allowed" is not served as "No" (call 123) | `test_a_sentence_that_names_this_topic_is_not_turned_into_a_no`, `test_a_sentence_about_another_topic_is_not_a_fact_of_this_call` (144, 145), `test_names_other_topic` (13 cases), integration `test_the_model_is_told_the_topic_and_a_quote_naming_another_topic_is_refused`, `test_each_topic_of_the_document_gets_its_own_answer` | met for what a quote can show; see "not fixable in code" |
| F5 same sentence, opposite values (109/110) | `reconcile` rule: a single applicant allowed only under a condition and a consortium minimum of two or more means everyone else must form a consortium; no consortium + minimum of two + nobody may apply alone: the consortium fact is not served | `test_the_same_sentence_gives_the_same_answer_on_two_calls` | met; production: 110, 111, 112 now say consortium required like 108, 109 |
| C1 deadline time | see below; not a data fix | `digest.check.ts` (ics) | partly met: stated, not changed |
| C2 rolling wording | note and event word say "next cut-off" (the code stores the next one, `_closing_stamp`) | `digest.check.ts` | met |
| D1 first collection called "new" | `funding_events`: a call is `call-new` only if `COALESCE(published_at, opens_at)` is null or no earlier than the window start minus 2 days | integration `test_a_call_published_before_the_window_is_not_new_because_a_source_read_it_now` | met; production W39 75 -> 0, W41 5 -> 0, W40 5 -> 5 (checked by SQL) |
| D2 W37 "30 amended" | `_amendments` skips a change observed on the UTC day of the notice's first reading | integration `test_a_change_the_publisher_made_before_our_first_reading_is_not_an_amendment` | met |
| D3 digest and changes not public | decided: not a defect. The web server proxies them; the Caddy list is deliberately short and the uncached week computation is heavy. Recorded in `API_CONTRACT.md` | none (decision) | decided |
| D4 unknown digest country | pages say "Ignored filter: country=ZZ"; the Atom feed answers 400 | `digest.check.ts` (`unknownDigestCountry`) | met |
| F8 "consortium of at least 1 entities" | `summary_line`: a consortium from 2 entities, "from N countries" from 2 countries; one entity reads "a single applicant may apply" | `test_the_summary_line` | met |
| PROMPT_VERSION 4, held rows re-asked | version 4; the held check is per key and version | integration `test_a_row_read_with_the_old_prompt_is_asked_again` | met |

### C1: what the portal data carries

`eu_portal.closing()` receives the portal's `deadlineDates` as epoch milliseconds, which are midnight UTC for every call (the module comment
records 155 of 155 on 12 October; I did not call the portal again, so that is not re-confirmed today). The product turns that day into
23:59:59 Brussels. The stored call documents (`call_document_text`) say the cut-off in words: of 102 stored texts, 38 state a time and all 38 say
`17:00:00` (32 CET, 6 CEST); none says anything else. So the verifier is right that 17:00 Brussels is what the documents say, and the data does
not carry it.

I did **not** move the stored deadline to 17:00. It would write a `call_change` row (and a digest "amended" entry) for every EU call, it would
claim a time for Horizon calls whose documents we do not hold (the annexes we hold state none), and the portal's own value is a day. What changed:
the calendar file keeps all-day events and, for EU portal funding calls, says "No time is published; the call documents we have read set the cut-off
at 17:00 Brussels time, so the call may close earlier that day." (`web/lib/ics.ts`). Not confirmed: the time for Horizon calls (no call document), for
the EIC (its work programme was not searched for a time), and whether SEDIA's API carries the time in a field the connector does not read. Decision for
the owner: if he wants the stored deadline at 17:00, `closing()` is the single place, and the existing rows need one migration that rewrites
`deadline_at` and `call_change` must not record it.

## Regression set (the verifier's 30 calls)

`backend/tests/fixtures/wp35_verifier_calls.json`: the verified facts stored for the 30 calls on 17 October (prompt v3; quotes are the documents'
sentences; 29 documents/annexes/topic texts), read-only export from production. `tests/unit/test_wp35_eligibility.py` runs the real serving path
(`eligibility.assemble`) over it and asserts, exactly, which facts disappear (`GONE`: 10 cascade, 8 ownership, 7 single-applicant facts) and that the facts the
verifier judged correct are served unchanged. These tests fail on the code before this change (the functions do not exist; the GONE equality would fail
on the old serving path).

### Not fixable in code, expected from prompt v4 and the live run (to be checked after it)

Facts whose quote does not show the problem: call 6 ownership (the note, not the quote, names the topics), 19 `min_countries` (quote has no topic code; the note
has the right number for MDL), 126 `min_entities`/`min_countries` (4 shown, 5 needed), 144 `consortium_required` (quote says no minimum composition), 60 and 69
(topic text overrides general with its own SME/authority count), 131 (`funding_rate`, `natural_persons_allowed`, `sme_only`), 115, 118, 78. They
are listed so that the live run is checked against them: after the extraction, re-run the 30 calls against their documents.

## Verification against real data (read-only)

Production export of the 159 EU calls and all 102 `call_eligibility` rows, run through the old merge and the new `assemble` (script not kept):

- calls with facts: 149 before, 149 after (no call lost all its facts).
- facts no longer served: cascade 65 (57 general Yes; 124, 127, 144, 145, 146, 147, 148, 150 about another topic), ownership 38 (24 general Yes, 11 other general-scope facts, and the
  high-risk sentence on 18, 19, 119), single applicant 34, consortium 3 (13, 29, 192: the quote is about another topic), min entities/countries 2 each (29, 192: the quote is
  about the NCH topic, the call is the CBCH topic).
- values changed: 110, 111, 112 `consortium_required` false -> true; 123 `cascade_funding` false -> true. Nothing else changed.
- contradictory consortium/single pairs 29 -> 0.
- cascade flags (`cascade.decide`) on all 159 calls: 0 flag or reason changes (the "document allows it for other topics only" reason is kept through `other_topic`).
- Hand check of the removals above, 15 of the call-document ones: 124 yes (quote is about EHDS), 127 yes (quote is about two other topics; the verifier says
  FSTP is not allowed there), 144 145 146 147 148 150 yes (NCC only), 13 yes (quote names LEAGUE-OF-ACADEMIES), 29 192 yes (NCH, not CBCH), 18 19 119 yes (high-risk
  suppliers), 108-112 193 yes (SEAP only). One false refusal was found by this run and fixed before the final run: call 191 (the document writes NCH, the portal NATCH)
  and call 123 (the quote mentions the previous year's call): `_same_topic` now accepts a code of another year's call and an abbreviation of the last part.
  Residual risk: a document that names its own topic with a different code is refused (the facts are not served, never wrong).
- Cost of the live run: see the report; `dgate.ops.extract_eligibility` lists the units without sending anything.

## Own review of the diff (hostile reviewer)

Found and fixed: (1) `\b` in regexes written through a shell here-document became backspace characters (caught by the cascade tests); (2) the first version of the
topic check refused calls 191 and 123 on real data (above); (3) a long ICS description would have cut the link off (limit raised from 500 to 700, test asserts the link survives);
(4) the foreign key `call_eligibility.url -> call_document_text` made per-topic keys impossible (migration 0075 drops it and adds `document_url`).
Known limits left as they are: `names_other_topic` needs a code of three hyphenated parts with two words (a topic written otherwise is not checked); the `reconcile`
rule that derives "consortium required" from "single only under a condition" with a stated minimum is a reading, it carries the sentence and a note, and the form already
answers "check" for any fact with a note; `D1` also hides calls published long ago that appear first now (they show under "opened" when they open).

## Tests

Added: `tests/unit/test_wp35_eligibility.py` (regression set and pieces), `tests/integration/test_wp35.py` (9), additions to `web/lib/digest.check.ts` and
`web/lib/funding.check.ts` (calendar file, digest country); `web/e2e/digest.spec.ts` adjusted to the new event word.

Results on the server (it was at load 100 and out of memory for two hours because several packages ran suites at once, so the full integration suite could not
finish in a reasonable time):

- `ruff check .`: clean. Whole unit suite (`pytest`): green (run before the last two comment-only edits; the unit files that touch the change were re-run after: green).
- Integration, run in one session: `test_wp35`, `test_eligibility`, `test_wp31`, `test_changes`, `test_funding_api`, `test_calls_api`, `test_call_dates_api`, `test_wp19`,
  `test_security_hardening`: all green except `test_the_rate_limit_answers_429_with_a_wait_and_leaves_the_probe_alone`, which fails the same way on an unmodified
  `integration` checkout under this load (135 requests are not fast enough to empty the bucket). The rest of the integration suite (about 800 tests) was **not** run to the end;
  the orchestrator's CI run should cover it. `test_wp35` also passes alone.
- Web: `tsc --noEmit` exit 0; `lib/*.check.ts` (all of them): ok, after the funding check was adjusted to the new sentence.
