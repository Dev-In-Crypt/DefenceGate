# WP-135 self-check: a Polish notice held from the bulletin and from its mirror is one notice

Branch `wp-wp135` from `integration` (3d2a649). Evidence: `docs/verification/round6/wp133-selfcheck.md` (open item 1) and
`D:\DEFENCEGATE TESTS\wp133\prod\`. Production was read only: SELECT through the postgres container (statement_timeout 30 s,
`default_transaction_read_only`), SQL and logs in `D:\DEFENCEGATE TESTS\wp135\prod\` (the list's own statements, old and new
rules, generated from the code by `D:\DEFENCEGATE TESTS\wp135\gen_sql*.py`). Nothing was written on production. No migration,
no stored flag, no ops module.

## Items

| # | Before (evidence) | Change | Test | After |
|---|---|---|---|---|
| 1 | The collapse rules (`tenders.collapse_clauses`: TED copy, rectificatif, re-publication) did not know that `pl_ezam` (the bulletin) and `pl_atlas` (its mirror) publish the same notice under the same BZP number. Production (`prod\b.log`): 27,886 pairs, 27,730 of them of one buyer family and both shown; each listed as two cards and counted twice. Buyer 7310: 604 where it holds 601 notices. | A fourth rule in the shared function, `mirror_clause(where)` over `mirror_hidden_by(o, p)`: a Polish notice is not shown when its other copy (same number, the other of the two sources, same buyer family: `dgate_buyer_head`) passes the same filters and is the kept copy. **Kept copy:** the bulletin's (`pl_ezam`), except where only the mirror states a value (a value over the placeholder 1): the mirror's. Measured (`prod\b.log`): the mirror holds a value the bulletin lacks in 19,621 of the pairs; no other field (deadline, CPV, TED reference, English title, procedure) is held by the mirror alone, and the bulletin never holds a value the mirror lacks. Exactly one copy of a pair is the kept one, independent of the filters; a filter only the other copy meets lists that copy (nothing vanishes). Every reader of `collapse_clauses` follows: the list, its total and capped counts, the scope counts, the CSV export, the buyer aggregate (`openCount`, `tenderCount` from the worker's exact base), the buyer directory, the buyer profile and its per-source split, the counts under codes, `/v1/changes` and its Atom feed. The parameters now repeat `COLLAPSE_REPEATS` (5) times: every caller uses the constant (`tenders`, `stats.buyer_profile`, `changes`). `/v1/opportunities` (its own inline TED rule) gets the same rule. The kept copy lists the other in `sameNotice` (`api._twins`, by BZP number). The hidden copy's page is still served (200, its own archive) and carries `copyOf`, the kept copy's slug; the page uses it as its canonical address (`web/lib/seo.ts` `tenderCanonicalPath`). The sitemap (`/v1/tenders/sitemap`) and the recent slugs (`/v1/tenders/slugs`) leave the hidden copy out. | `tests/integration/test_wp135.py` (8 tests): a pair is one card, total 1, export 1, scope counts 1, the kept copy names the other, the hidden page is 200 with `copyOf`, sitemap and slugs once, `/v1/opportunities` once; the mirror is kept when only it states a value (a placeholder 1 is no value; both valued: the bulletin's); a search or value range only the mirror meets lists the mirror; a bulletin notice without a mirror, two different numbers and two unrelated buyers stay; the TED rule unchanged (a national copy and its mirror both under the TED notice); a 7310-shaped buyer (10 bulletin, 4 TED, 3 mirror, 2 national copies of TED) counts 12 in the list, the buyer's list, `tenderCount`, `openCount`, the profile and its sources, the export and the directory; every status list; the filters' parameters repeat `COLLAPSE_REPEATS` times. Mutation check: with the rule switched off (`FALSE AND` in `mirror_hidden_by`) the five collapsing tests fail. `test_wp98b`: its slow stand-in for the collapse now carries one placeholder per rule (`COLLAPSE_REPEATS - 1`), same assertions. `web/lib/wp135.check.ts`: the canonical path (kept copy, none, older API, a value that is no slug). | See item 2. |
| 2 | Measure on production. | Read-only SQL (`prod\c.log`, `d.log`, `e.log`). | | **7310: 604 -> 601** (status all, the list's default scope; open 2 -> 2). Buyer families whose count falls: **111**, notices counted once more: **26,872** (the exact buyer aggregate: 315,525 -> 288,653, the same difference). Pairs of one family: 27,730 (348 families when every scope is counted; 111 hold such pairs in the default scope and not already collapsed under a TED notice). Largest five (`d.log`): 7065 31 Wojskowy Oddział Gospodarczy -1,310 (profile 4,469 -> 3,159), 26 15 WOG -964, 7396 43 WOG -949, 9020 4 WOG -938, 11870 2 WOG -938. Default list (open): 1,555 -> 1,554. Under CPV 35: 30,722 -> 29,771. Timings, old -> new: default list count 136 -> 92 ms, first page 45 -> 90 ms, closed count (capped) 385 -> 222 ms, closed page 32 -> 24 ms, 7310 count 250 -> 96 ms, counts under 35 1.88 -> 1.88 s (budget 2.5 s), profile 7065 78 -> 187 ms, live open counts of the directory 1.35 -> 1.02 s, `sameNotice` of 50 paired notices 0.63 -> 0.29 s. The worker's exact buyer aggregate 11.1 -> 17.7 s (the worker, not a request; no statement timeout there). No stored flag or table needed: nothing to write. |
| 3 | Tests. | As item 1. | | List/count agreement holds (same WHERE, same rules, `COLLAPSE_REPEATS` in every caller; the 7310-shaped test checks list total, `len(items)`, buyer counts and export together). |

## Ops on production (orchestrator)

1. Deploy (no migration, no ops module).
2. The counts that are stored follow on the worker's next `warm_lists` run (the buyer base, list snapshots, scope counts):
   expect buyer 7310 at 601, the default open list 1,554 (as of 25 October 18:00 UTC; it moves with the day's notices).

## Open items

- 237 families hold pairs only outside the default scope (or already under a TED notice); they collapse as well when the
  list is asked for `scope=all`.
- 17 pairs of two different buyer rows (WP-133's `same_notice_number` candidates) stay two notices until the review queue
  merges the buyers: the rule asks for one buyer family, as the brief says.
- The buyer page's sentence (WP-133) names the TED copy as the reason a count can be lower than the notices held; it stays
  true, it does not name the mirror. Not changed (copy only to make it true).
- Market statistics outside the list rules (CPV group shares, notices per month of the market) count rows, as they did for
  TED copies; not changed.
- Checked and nothing to do: no award is held on a mirror notice (`prod\h.log`), so supplier values are not doubled; no kept
  mirror copy has a bulletin update notice (0).

## Tests run (batched scope)

- Backend: ruff clean; unit 4,027 passed; integration 1,544 passed (Postgres 17, own container), `test_wp135.py` (8) among them.
- Web: tsc clean; lib checks green (`wp135.check.ts` included); `next build` green; Playwright `e2e/wp113.spec.ts` (a Polish
  notice's page with its TED twin): 4 passed (desktop and mobile).

## Files

`backend/dgate/tenders.py`, `api.py`, `stats.py` and `changes.py` (one line each: `COLLAPSE_REPEATS`),
`backend/tests/integration/test_wp135.py` (new), `backend/tests/integration/test_wp98b.py` (the stand-in's placeholders),
`docs/design/API_CONTRACT.md`, `web/lib/seo.ts`, `web/lib/types.ts`, `web/app/(public)/tenders/[slug]/page.tsx`,
`web/lib/wp135.check.ts` (new), this file.
