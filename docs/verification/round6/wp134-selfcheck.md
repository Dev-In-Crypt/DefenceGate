# WP-134 self-check: the gated specs nobody ran, and one more generic Polish name word

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP134.md`. Branch `wp-wp134` from `integration` (e4c14a3). Test copy
`D:\DEFENCEGATE TESTS\wp134\` (`gated-run.ps1`, `backend-run.ps1`, `web-run.ps1`, `e2e-run.ps1`). No migration, no ops module, no
production write.

## 1. Gated specs that never ran

- Before: `wp79.spec.ts` "against the fake account API" (`E2E_FAKE_ACCOUNTS`), `wp123.spec.ts` "against the real account API"
  (`E2E_REAL_ACCOUNTS`, `E2E_MAIL_DIR`), `wp122.spec.ts` "billing on" (`NEXT_PUBLIC_BILLING_OPEN`) and `wp124.spec.ts` "against the
  real API, billing open" (`E2E_REAL_BILLING` and the Creem stand-in) skip themselves in `.github/workflows/web.yml` and in the
  orchestrator's run; only their builders ran them, by hand (WP-124's `e2e-all.ps1`; WP-128 listed them as open).
- How each is meant to run (the specs' headers, `e2e/support/fake-accounts.mjs`, `https-proxy.mjs`, `backend/tests/e2e_api.py`,
  `creem_mock.py`, WP-123/124 self-checks): the account sites need https (`__Host-` cookies), so they sit behind the proxy with a
  throwaway certificate; wp123/wp124 need the real API on a throwaway Postgres with the mail catcher directory; wp124 needs a
  build with `NEXT_PUBLIC_BILLING_OPEN=1` made while the API answers (the static list pages see accounts open), the site with
  `DG_E2E_CREEM_ORIGIN` at the stand-in.
- Change: new workflow `.github/workflows/web-gated.yml`, job `gated` (Postgres 17 service, Python 3.12, Node 22): starts the real
  API (`tests.e2e_api`, migrated database, catcher `/tmp/e2e-mail`, Creem stand-in on 4124, test placeholder settings) and the fake
  account API; build A (default) -> `wp79` (fake, https 3443) and `wp123` (real, https 3444); build B (billing open) -> `wp122`
  (plain http: its own 375 px and theme contexts do not ignore certificate errors; `/pricing` needs no cookie) and `wp124`
  (https 3444). Fake services only: no SMTP, no Creem, no network. Triggers on `web/**` and `backend/**` (the specs exercise the
  API). Server logs printed on failure. A note in `web.yml`'s header and `web/README.md`.
- Local: `D:\DEFENCEGATE TESTS\wp134\gated-run.ps1` (same phases, takes `web-build.lock`, its own ports and container; for another
  copy change the variables at the top). Summary in `gated.log`, one log per spec.
- Test: `backend/tests/unit/test_wp134.py::test_each_gated_spec_runs_in_ci_with_the_setting_it_waits_for` (each spec in a
  `playwright test` line with its setting, the billing-open build, the mail catcher and the stand-in, no SMTP host or Creem address).
- After (`gated-run.ps1`, three full runs; no spec or code changed):

| Spec | Against | Passed (runs 1 / 2 / 3) | Skipped (the other state's tests) |
|---|---|---|---|
| wp79 | build A, fake account API | 14 / 14 / 14 | 16 (accounts closed, run in the normal job) |
| wp123 | build A, real API + catcher | 4 / 4 / 4 | 4 (accounts closed) |
| wp122 | build B, billing open | 14 / 14 / 14 | 2 (billing off) |
| wp124 | build B, real API + catcher + Creem stand-in | 3 / **2, 1 failed** / 3 | 5 (billing closed 4; the pay flow runs on desktop only, 1) |

  Run 2's failure (`wp124.spec.ts:124`, the pay flow on desktop): after sign-in, `[data-pay-now]` ("You chose Pro, monthly. Your
  plan is Free until it is paid.") was not found within 10 s. The API logged register, confirm and sign-in for that account; the
  cached `/v1/account/status` of that minute says `open` and `billing` true, so the status was not the cause. Not reproduced in
  run 3; cause not found (a slow `/me` answer under load would render the "not available" layout, which has no such line; not
  proven). Log kept: `D:\DEFENCEGATE TESTS\wp134\e2e-wp124-run2.log`. Open item: watch the first CI runs of `gated`.
  The workflow itself has not run on GitHub (no push from builders): its first run is on the orchestrator's push.

## 2. `zakladow`, a generic Polish name word

- Before: `_UNIT_WORDS` (`backend/dgate/ops/org_repair.py`) had `zaklad zakladu zaklady` but not the genitive plural, so
  `ambiguous_name` held 'zespol zakladow opieki zdrowotnej' and 'samodzielny publiczny zaklad opieki zdrowotnej zespol zakladow'
  to be one body's names (WP-129 self-check, "Other rejoins into generic-name rows").
- Change: `zakladow` added. No other inflection was needed: both names are generic with it alone.
- Test: `tests/unit/test_wp134.py`: the two names are generic; the same names with a place ('... w wadowicach', '... w lomzy')
  stay joinable. `test_wp119`, `test_wp129` green.
- After, read-only on production (one `\copy` SELECT of the live rejoins, 30 s timeout, read-only transaction; the `namesakes`
  logic applied locally with the old and the new vocabulary). `python -m dgate.ops.org_repair --step namesakes` (report) would say:
  - old vocabulary: rejoined rows 6761; 0 groups, 0 rows; 1 row stays (329120 into 7563, number agrees);
  - **new: rejoined rows 6761; 2 groups, 5 rows; 1 row stays** (329120, as before):
    head 9206 'zespol zakladow opieki zdrowotnej' <- 314495, 314541, 314952 (cleared values were case references);
    head 10219 'samodzielny publiczny zaklad opieki zdrowotnej zespol zakladow' <- 286437, 287255 (6-digit values; head holds none).
  With `--yes`, exactly those 5 rows are undone through `ops.undo_merges` with `only`. None of the five rows' numbers agrees with
  its head, so none is kept. Not run.
- Also affected: `false-ids` (never rejoins these names again) and WP-133's `ops/accept_merge_candidates.py`, which calls
  `org_repair.ambiguous_name` for "a name that is no one body's" (no file of WP-133 edited; the behaviour widens by these names).

## Tests (batched scope)

| Check | Result |
|---|---|
| `ruff check .` | clean |
| pytest unit | 4030 passed |
| pytest integration | 1530 passed |
| web `tsc --noEmit`, `node scripts/run-checks.mjs` | 0, 0 |
| Playwright, gated specs (`gated-run.ps1`, two builds) | table above (one failure in three runs of wp124, not reproduced) |

## Ops (orchestrator)

1. `python -m dgate.ops.org_repair --step namesakes` (report): expect rejoined rows 6761, **2 groups, 5 rows**, 1 row stays.
   Stop if it differs. Then `--yes`.
2. Include `gated-run.ps1` (or its phases) in the full run.

## Files outside the package

`web/README.md` (one paragraph), `.github/workflows/web.yml` (one comment line).
