# WP-133 self-check: links of merged organisations, a possible duplicate, a buyer's count

Branch `wp-wp133` from `integration` (e4c14a3). Evidence: `D:\DEFENCEGATE TESTS\verify-oct25\ops-r9\` (04-spotcheck-*.txt,
04-buyer-api.txt, 04-heads-tenders-psql.log). Production was read only: SELECTs through the postgres container (statement_timeout
30 s, read-only transaction) and three API reads with curl; the SQL and logs are in `D:\DEFENCEGATE TESTS\wp133\prod\`. Nothing was
merged and nothing was written on production. No migration.

## Items

| # | Before (evidence) | Change | Test | After |
|---|---|---|---|---|
| 1 | `/v1/buyers/7504`, `/323780`, `/286425` (rows merged into 29523, 7310, 195698 on 25 Oct) answered 404 "no such buyer", and so did `/buyers/<id>-...`: `get_buyer` followed buyer families (`dgate_buyer_head`) but not `merged_into`. The supplier resolver followed one merge step only; `/v1/organisations/<id>` already followed the chain (`dgate_live_org`). | One shared resolver, `tenders.live_id_of(conn, slug, what)`: the slug's id followed through `merged_into` to the end of the chain (`dgate_live_org`, migration 0068). Used by `/v1/buyers/{slug}`, `/v1/buyers/{slug}/profile`, `/v1/buyers/{slug}/suppliers`; `suppliers._resolve` (supplier page, its contracts and CSV) now reads `dgate_live_org` instead of one step; a followed buyer (`accounts._buyers_by_id`) too. The API answers the head under the head's slug, and the three web pages already `permanentRedirect` (308) when the slug they were asked under is not the one the API gives (unchanged). The buyer sitemap (`/v1/buyers/slugs`) leaves out a row that is merged (heads only); the supplier sitemap groups by the head already, the organisation sitemap reads `organisation_network` (live rows). `dgate_buyer_head` itself is unchanged: it runs per notice in the list's collapse rules, where a recursive lookup would cost every list. | `tests/integration/test_wp133.py`: buyer (a row merged into the head, a two-step chain, a row not merged unchanged, an unknown id 404), buyer profile and suppliers, sitemap heads only (also a family head merged away), supplier (one step, two-step chain, unmerged unchanged), organisation (two-step chain, unmerged unchanged). e2e `wp133.spec.ts`: buyer, supplier and organisation pages under an old slug answer 308 to the current one; the current one is 200. | `/buyers/7504-...` 308 to `/buyers/29523-amw-sinevia-...`, `/buyers/323780-...` to 7310, `/buyers/286425-...` to 195698 (after deploy). |
| 2 | Buyer search "zaklad karny we wronkach": 8840 "Zakład Karny we Wronkach" (5 notices) and 195698 (head of a reviewed merge, 286425 absorbed) with the same name and 5 defence notices. | Read both (`prod\a.log`): the same five notices, 2025/BZP 00224230, 00279322, 00308384, 00308393, 00308399: 8840 holds the copies of the bulletin's mirror (`pl_atlas`), 195698 the bulletin's own (`pl_ezam`), the buyer stated as "Zakład Karny we Wronkach" in all ten. 8840 has no number, 195698 REGON 000320302. One body. Candidate, not a merge: new ops module `python -m dgate.ops.shared_notice_candidates` (report by default, `--yes` writes) finds every pair of live rows of one country, not of one buyer family, holding the same notice number in `pl_ezam` and `pl_atlas` with the same stated name, and writes it through `db.add_merge_candidate`: method `same_notice_number`, confidence 0.95, evidence the numbers and the stated name, status pending, for the review queue. On production (report query, 0.44 s, `prod\g.log`): 17 pairs, 8840 ~ 195698 among them; two (7063 ~ 173425, 15819 ~ 64371) already have a pending `identifier` candidate and gain this one as a second method. | `tests/integration/test_wp133.py::test_two_rows_holding_the_same_notice_become_a_candidate_never_a_merge` (one pair written; different stated names and one buyer family left out; report writes nothing; a second run leaves the pair as it is; nothing merged). | 17 pending candidates after the ops run. |
| 2b | Other live rows sharing a name and country with a reviewed-merge head. | Scan (`prod\c.sql`, `c.log`): of the heads of the 64 `person_review` and 3 `curated_source_review` merges, 18 have a live row (not merged, not removed) whose stated name (an alias) folds to the head's display name: 23 rows. With notices: 8840 (5, the pair above), 7370 "gmina miasta gdyni" ~ head 283613 (4 defence notices; 3 pending candidates: identifier, identifier_name_mismatch, same_name_different_identifier), 7283 "powiat nowotarski" ~ head 325185 (2 defence notices; 2 pending candidates). The other 20 hold no notice and no award (an alias only); 11 of them already have pending candidates (7872 ~ 11921, 13075; 24703 ~ 287529; 293948 ~ 8036; 294379 ~ 6950; 294460 ~ 7240; 294470 ~ 10510; 303097 ~ 17432; 305194 ~ 10142; 306561 ~ 14249; 309310 ~ 10551); 9 have none (8670 ~ 22630, 30256; 13117 ~ 18775; 24703 ~ 80671; 293948 ~ 27284, 31617; 294442 ~ 15521; 334391 ~ 14052; 334712 ~ 27632). No candidate added for those: a public body with a generic name is never joined by name alone, and the merge queue skips rows nothing references (WP-115). Also 325059 "zaklad karny we wronkach" (NIP 7631081000, no notice) has a pending identifier candidate with 286425, the row now merged into 195698. | Read-only SQL. | Reported, no write. |
| 3 | Buyer 7310 page "604" against 630 defence notices (`04-heads-tenders-psql.log`). | Explained (`prod\f.log`, API `t-*.json`): 630 = 553 e-Zamówienia + 74 TED + 3 mirror notices, none removed or withheld, all in the default scope (`/v1/tenders?buyer=7310&status=all` = 604 under `scope=relevant` and under `scope=all`; 25 under `core`). 26 of the e-Zamówienia notices are national copies of TED notices of this buyer, and the list (and the page's count) shows each such notice once, as its TED notice: 630 - 26 = 604. The page said which notices it counts (the list's All defence scope) but not that a copy is counted once: it now does, `data-count-basis` "A national notice that is a copy of a TED notice is counted once, so the count can be lower than the notices we hold." Copy changed only to say what is true. | e2e `wp133.spec.ts` (the sentence); `wp96.spec.ts` (the sentence's start, unchanged). | The page says which count it shows. |

## Open items

- The 3 mirror (`pl_atlas`) notices of 7310 are also in e-Zamówienia under the same number and buyer, and the collapse rules do not
  treat a mirror copy as a copy: 7310's 604 counts them twice (601 distinct). Across the archive this is every notice held in both
  Polish sources under one buyer family; a collapse rule on (`native_id`, the two sources) would fix every count at once. Not done
  here (it changes the list's counts and their cached aggregate; its own package).
- A merge chain (A <- B <- C) is followed to its end by the pages now; the award and participation reads of a supplier or organisation
  still read one step (`COALESCE(merged_into, id)`). WP-115 re-points chains at merge time, so production has none (25 Oct).

## Ops on production (orchestrator)

1. Deploy (no migration).
2. `python -m dgate.ops.shared_notice_candidates` (report): `pairs: 17`, 8840 ~ 195698 among them; then `--yes`: 17 pending
   `same_notice_number` candidates. They are candidates only; the review queue (`ops.accept_merge_candidates`) decides.

## Tests run (batched scope)

- Backend: ruff clean; unit 4,027 passed; integration 1,536 passed (Postgres 17, own container); new
  `tests/integration/test_wp133.py` (6 tests).
- Web: tsc clean; lib checks green; `next build` green; Playwright `e2e/wp133.spec.ts` and `e2e/wp96.spec.ts`: 16 passed
  (desktop and mobile).

## Files

`backend/dgate/tenders.py`, `stats.py`, `suppliers.py`, `accounts.py` (one line: a followed buyer that was merged shows its head),
`backend/dgate/ops/shared_notice_candidates.py` (new), `backend/tests/integration/test_wp133.py` (new),
`web/app/(public)/buyers/[slug]/page.tsx`, `web/e2e/wp133.spec.ts` (new), this file.
