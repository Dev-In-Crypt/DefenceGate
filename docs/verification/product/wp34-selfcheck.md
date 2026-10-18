# WP-34 self-check: hardening fixes C1 to C9 (17-18 October 2026)

Branch `wp-wp34` (from `integration` fa24892). Source: `docs/verification/product/verify-abuse-new.md`.
Key `wp34`, migration 0074, test database `agent_n` (and `agent_n2` for targeted runs) on the server.
No language model call was made; no production write. Production was read (SQL with
`default_transaction_read_only` and a 30 s timeout; timings from inside the API container).

## Verdict per defect

| Id | Verdict | What was done | Test that fails without it |
|---|---|---|---|
| C1 | **fixed** | `ops/suppress.add` and `lift` delete `digest_issue` in the same transaction as the entry; the CLI then rebuilds the digest at once (`rebuild_digest`, all weeks). Meanwhile the API computes an issue on the spot, which honours the flags. The Atom feed is the site's rendering of `/v1/digest` and `/v1/digest/weeks`, so it follows. | `test_a_takedown_of_a_notice_leaves_the_stored_issues_the_api_and_the_feed_source`, `..._of_a_call_...`, `test_a_withheld_buyer_is_not_named_in_a_stored_issue`, `test_lifting_the_entry_brings_it_back_after_the_rebuild` |
| C2 | **fixed** | The same function deletes `list_snapshot`. The docstring no longer says "the API's list cache is a minute": it lists every cache with its real lifetime (API list 1 min, issue 5 min, site pages 5 min, CSV 10 min, Atom `max-age=3600`). | `test_a_takedown_drops_the_precomputed_list_pages_and_the_list_stops_showing_it`, `test_lifting_an_entry_also_drops_the_snapshots`, `test_the_docstring_...` |
| C3 | **fixed** | Health: the versions figure is the planner estimate (`pg_class.reltuples`), the oldest observation reads a new index (migration 0074), the three figures are cached 10 min with single flight (`stats.cached`), a defence count over the 5 s budget gives `null` for that figure only, a whole read over budget gives `null`s and is not retried for 60 s; `/v1/health` costs 5 tokens in `hardening.py`. Assess: the readiness connection is opened on first use, so a warm `assess` or catalogue request opens none. | `test_the_archive_versions_are_estimated_...`, `test_a_defence_count_over_budget_...`, `test_the_report_answers_without_figures_...`, `test_the_figures_are_read_once_...`, `test_the_report_is_priced_as_heavy`, `test_a_warm_assessment_opens_no_database_connection` |
| C4 | **fixed in code; the stored texts need one production command** | `eligibility.clean()` (redact e-mail addresses) runs on every text before it is stored and before it is sent, including a text stored earlier and a topic text. `redact_stored()` and `extract_eligibility --redact-stored [--yes]` clean what is already kept. DATA_PROTECTION.md now lists `call_document_text`, `call_eligibility`, `llm_usage`, `digest_issue`, `list_snapshot` and OpenAI as a processor. Privacy page source names OpenAI (**draft, owner and lawyer must approve**). | `test_no_address_is_stored_or_sent_...`, `test_a_text_kept_before_the_fix_is_cleaned_...`, `test_the_one_off_redaction_...` |
| C5 | **fixed (with one unverifiable assumption, below)** | The document is placed between `<<<DOCUMENT_BEGIN>>>` and `<<<DOCUMENT_END>>>`; the system prompt says everything between is data and never instructions; the fence characters are removed from the text so it cannot close its own fence; `maxLength` (value 1000, quote 400, note 400, list item 200) and `maxItems` 30 are in the schema, and `bound()` enforces them on the answer whatever the provider does. The quote check is unchanged. `PROMPT_VERSION` is 4 (the prompt text changed, which is the repository rule); version-3 rows are still served. | `test_the_prompt_says_the_document_is_data_...`, `test_every_string_of_the_schema_has_a_length_limit`, `test_bound_cuts_...`, `test_an_injected_quote_that_is_not_in_the_document_stays_unverified_...` |
| C6 | **fixed** | One handler for every route: `[{loc, msg, type}]`, no `input`, no `ctx`, no `url`; a `loc` name that is not a field or parameter of the API's own OpenAPI schema (an invented key, a dictionary key) becomes `*`. | `test_a_refused_query_is_not_echoed`, `test_an_unknown_key_and_a_dictionary_key_...`, `test_a_refused_get_does_not_echo_the_value`, `test_an_unknown_key_of_the_assessment_body_is_not_echoed` |
| C7 | **fixed in the repository; needs a Caddy restart on the server** | The running config was *not* stale: file in the container and on the host are identical (md5 b5db237e...), Caddy started after the file's mtime, and it has `header_down -Via`. The directive simply does not work: reproduced on a throwaway `caddy:2` (2.11.4) on the server: `header_down -Via` inside `reverse_proxy` still sends `Via: 1.0 Caddy`; a deletion in the site's `header` block (like the existing `-Server`) removes it. Moved there, tested with the real Caddyfile structure (handle blocks, POST), scratch container and files removed. | `test_the_caddyfile_removes_via_where_caddy_adds_it` |
| C8 | **fixed** | Redirects are followed by hand: https only, same registrable domain as the first address (last two labels; a ceiling noted in the code), at most 4; the first address must be https; the client no longer follows redirects. `pypdf>=6.0,<7` (installed in the worker and API images: 6.21.1). | the five `test_a_redirect_...` and `test_redirects_are_capped`, `test_pypdf_has_an_upper_bound_...` |
| C9 | **fixed** (was Info) | `repr=False` on the DSNs, the internal secret, the app password, the S3 keys, the OpenAI key, the SMTP password and the Telegram token. The public `/v1/health` disclosure is by design (documented in DATA_PROTECTION and the API contract), not changed. | `test_the_settings_repr_holds_no_secret` |

Not a defect: none. Needs the owner: the privacy wording (C4), whether to re-read the 102 documents
under prompt version 4 (about 0.66 USD at the measured 0.0065 USD a document; not needed for
correctness), and the OpenAI data processing agreement and transfer basis.

## Measurements

C3, production, read-only, from inside the API container (17-18 October 2026; the host was busy):

| Query | Before | After |
|---|---|---|
| `count(*)` of `opportunity_version` (health) | 4.84 s (parallel index-only scan, 180k heap fetches) | `reltuples` read: 0.056 s (611,039 against an exact count of the same order) |
| `min(observed_at)` | 5.22 s (parallel seq scan, 96k buffers read) | **not measurable on production (the index is created by the migration)**; on a synthetic table of 650,000 rows: 915 ms before the index, 0.10 ms after (index only scan, 14 MB) |
| defence count | 1.38 s; timed out at 5 s while the host was busy | unchanged query, now cached 10 min and allowed to be missing |
| `GET /v1/health` through Caddy | 7.6 s and 8.2 s (verifier); 5.58 s, 5.62 s and 9.53 s, all 503 (my three calls, host busy) | the cold read is one estimate, one index read and one 1.4 s count, once in 10 minutes for all callers; warm calls read a dozen small rows |

Not measured after deployment (the orchestrator measures: command below). The new `/v1/health` figure
`archive_versions` is now an estimate; nothing in the site uses it (grep of `web/`).

C4, production, read-only: `call_document_text` 102 rows, 5,829,638 characters; **29 texts hold 60
e-mail-shaped strings**; `call_eligibility` 102 rows, 0 with an address; cost 0.0065 USD a row, total 0.66 USD.
C5: the longest served value is 301 characters, quote 302, note 346: the new limits (1000/400/400) cut nothing that exists.
C1, C2 on production: `digest_issue` 119 rows (W37 to W41), `list_snapshot` 414 rows; **no suppression entry exists
yet** (0 notices, buyers, calls flagged), so nothing stale is being served today.
Unit tests of this package: 18 (`tests/unit/test_wp34.py`); integration tests: 20 (`tests/integration/test_wp34.py`).
**Run against `integration` without the fix files: 37 of the 38 new tests failed**; the one that passes
(`test_a_lift_of_nothing_drops_nothing`) guards that a lift of nothing drops nothing.

## Own review of the diff, as a hostile reviewer

Found and fixed: (1) the first draft of `suppress.add` did not call the deletion (my edit did not apply; the new
tests caught it); (2) my test helper confused notice ids with call ids (both count from 1); (3) the
defence count timing out would have taken the whole health answer down: now isolated; (4) `loc[0]`
("body", "query") would have been replaced by `*`: kept; (5) the `Via` fix first needed proof the directive
fails at all (reproduced). Five issues, five fixed.

Left, on purpose, with the ceiling:

- A worker build that read rows just before a takedown and writes just after it can put a stale digest row
  back; the daily rebuild of the last two weeks and the CLI's own rebuild close it for recent weeks, older weeks
  until the next takedown or rebuild. No lock was added.
- After a takedown the closed and all-status tender lists use the live query (about 3 s, can 503 on a busy host)
  until `python -m dgate.ops.warm_lists --yes` or the worker's next round (4 hours). The CLI prints this.
- Caches: the Atom feed may be held for an hour by a feed reader (`max-age=3600`); a removal is final in the API at once.
- C5 is a mitigation: an attacker who controls the document can still write a sentence that exists in it and
  make the model report it; the quote check only proves the quote is in the document. The blast radius is as the
  verifier described (strict schema, no tools, no secret in the prompt).
- Redirect domain is "last two labels" without a public-suffix list (`ponytail` comment): exact for europa.eu.
- Names and telephone numbers inside call documents are not redacted (only e-mail addresses), nor obfuscated
  addresses ("name [at] domain"). The EDF factsheet path (`networks.py`) has its own text and prompt and was
  **not** changed or checked in this package.
- **Unverifiable here:** OpenAI's documentation lists only `pattern` and `format` as supported string keywords in
  strict mode and says `minLength`/`maxLength` are unsupported for fine-tuned models; it does not say they are
  rejected for others. If the first live extraction answers HTTP 400 about `maxLength`/`maxItems`, remove the
  `max_length` arguments in `eligibility.py` (the `bound()` cut keeps the limits). The error costs nothing.

## Not met / could not check

- Nothing of the suite is outstanding: on the final tree, ruff is clean and the whole suite is green on `agent_n`
  (unit tests and the integration run: 3,152 passing dots, no F or E; the output was run with `-q -q`, so there is no
  summary line). Earlier attempts while the server was saturated by other packages (load above 100) had the CI Postgres
  drop connections once; that run was stopped and repeated.
- The web build (`tsc`, `npm run check`) was not run: only a TSX string list in the privacy page changed.
- Production behaviour of the Caddy change after the restart, and of the health endpoint after the index exists.

## Production commands (the orchestrator runs them; expected volume and disk)

1. Deploy the branch; the worker applies migration 0074 at start: one plain index on `opportunity_version`
   (about 14 to 20 MB, a few seconds of write lock on that table, like 0046). Disk: negligible.
2. `docker exec dgate-worker-1 python -m dgate.ops.extract_eligibility --redact-stored` (dry run: expect
   `{'documents': 29, 'eligibility_rows': 0}`), then the same with `--yes`. No model call; writes 29 rows.
3. Caddy: put the new `infra/Caddyfile` on the host and `docker restart dgate-caddy-1` (the file is a single-file
   bind mount: a restart re-reads it; there is a few seconds' gap). Check: `curl -sI https://defencegatehub.com/ | grep -i '^via'` prints nothing.
4. Timings after: `for i in 1 2 3; do curl -s -o /dev/null -w '%{time_total} %{http_code}\n' https://defencegatehub.com/v1/health; done`
   (the first is the cold read; expect under 3 s and 200).
5. Privacy 1.5: **do not deploy the web before the operator and a lawyer approve the wording**
   (`web/app/(public)/privacy/page.tsx`, section 8; copy in `docs/legal/versions/privacy-v1.5-2026-10-17.md`).
   `PRIVACY_VERSION` is 1.5 in `accounts.py` (the rule in `docs/legal/versions/README.md`: bump with the page).
   If the wording changes, change the page and the copy together; sign-in is closed, so no one is asked to accept it yet.
6. Optional: re-read the documents under prompt version 4 (`extract_eligibility --yes --force`; about 0.66 USD).

Scratch removed: `/root/dev-n2`, `/root/dev-n3`, `/root/run_n2.sh`, `/root/run_n3.sh`, databases `n_scratch` and `agent_n2` (dropped).
`/root/dev-n`, `/root/run_n.sh` and the database `agent_n` remain as the working copy and test database of this package
(delete when merged). The throwaway Caddy container and its files were removed.
