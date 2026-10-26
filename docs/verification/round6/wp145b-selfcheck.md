# WP-145b self-check: the "No funding for Ukrainian entities" filter only where it can find a call

## Before

The orchestrator's full run (`D:\DEFENCEGATE TESTS\wp106\e2e.log`, about line 1435): `[desktop] e2e/wp47.spec.ts:116` "the funding
filters fold too, and the cascade and Ukraine filters stay in reach" failed, the folded funding filter form measured 1766 px against
1700. Cause: WP-145 added the choice "Only calls whose document says Ukrainian entities cannot receive funding" to the "Ukrainian
participants" group for every visitor, though no call carries that label (0 on production, 26 Oct 2026; WP-145 self-check §1).

## Change

- API (`backend/dgate/funding.py`): `/v1/funding` has `uaNoFundingTotal`, the calls with reason `call_document_no_funding` among those
  that match every filter but this one (the `cascade` and `ukraine` choices applied), counted before the `uaNoFunding` filter, the same
  rule as `cascadeTotal` / `ukraineTotal`. One `count(*)` more per list request. `docs/design/API_CONTRACT.md` says it.
- Demo twin (`web/lib/mock/calls.ts`) and type (`web/lib/types.ts`): the same count.
- Site (`web/components/funding/filter-bar.tsx`, `call-list-template.tsx`): the choice shows only when `uaNoFundingTotal > 0`, or when
  the URL already chose it (`uaNoFunding=true` typed in), so it can be unticked; its label carries the count like its two siblings. A
  typed-in filter with no labelled call gives the honest empty list ("No calls match ... no funding for Ukrainian entities") with the
  existing "N calls match without the Ukrainian-funding filter" way out. An older API without the field: hidden.
- Fake API (`web/e2e/support/fake-api.mjs`): `uaNoFundingTotal` 1 for the WP-145 search (9006), 0 for the WP-132 search, whose
  answer now also honours `uaNoFunding=true` as the API does.

## Tests (new; none changed or weakened)

- `backend/tests/integration/test_wp145.py::test_the_list_counts_the_labelled_calls_so_the_filter_bar_offers_the_choice_only_then`:
  0 with no labelled call and an empty list when typed in; 1 with one, also under its own filter; follows `status` and `ukraine`.
- `web/lib/wp145.check.ts`: the demo count is 0 (no labelled demo call), counted before its own filter; funding.py sends the key.
- `web/e2e/wp145-api.spec.ts`: "the filter is offered, with its count, only when a call carries the label" (shown with "(1)" for
  9006, absent for 9002-9005, the Ukraine choice stays); "typed into the URL where no call carries the label, the filter stays ticked
  and the list is honestly empty".

## Runs (`D:\DEFENCEGATE TESTS\wp145b\`)

- ruff: clean. Unit: 4097 passed, 0 failed. Integration (Postgres on 55546) of the funding list files `test_wp145`, `test_wp36`,
  `test_wp31`, `test_wp32`: 72 passed, 0 failed.
- tsc: clean. Lib checks (`node scripts/run-checks.mjs`): all green (`wp145 checks passed`). `next build`: 0.
- Playwright, under `web-build.lock`, `wp47.spec.ts wp145-api.spec.ts funding.spec.ts` on desktop, mobile-375 and the two fake-API
  projects: **51 passed, 5 skipped** (the viewport-bound skips of wp47 and funding.spec, as before), 0 failed. `[desktop]
  wp47.spec.ts:116` passes again: the folded form is back under 1700 px.
