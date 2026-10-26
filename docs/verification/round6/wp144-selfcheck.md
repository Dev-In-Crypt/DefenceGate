# WP-144 self-check: one buyer, several units (the Unit choice), and pages for buyers outside the default scope

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP144.md` (general rules: `D:\DEFENCEGATE TESTS\ux-oct24\BUILDER.md`), plus item 5
added by the coordinator on 26 October 2026 (owner-approved). Branch `wp-wp144` from `integration` (d3d6132), with `integration`
merged in at 9c4295c (WP-143) for item 5. Test copy `D:\DEFENCEGATE TESTS\wp144\` (own venv, Postgres `dgate-wp144` on 55544, removed
at the end). Production was only read: SELECT/EXPLAIN through psql in the postgres container, `statement_timeout=30s` and
`default_transaction_read_only=on` (scripts and outputs in `D:\DEFENCEGATE TESTS\wp144\prod\`). No migration, no ops module, no
production write.

## 1. What a unit is (data)

**How the data already works.** A legal body on the site is a *family*: its head row, the rows merged into it
(`organisation.merged_into`; a merge re-points the notices, `db.merge_organisations`) and its display members
(`buyer_family_member`, migration 0055: named rules, French ministry names, spellings, shared tax id). Each notice keeps the buyer
name it states (`opportunity.buyer_name_raw`); the aliases (`organisation_alias`) are every name a row was resolved from, including
names of notices we do not hold.

**Definition (no new merging rule, nothing fuzzy).** A unit is the buyer name as the notice states it, folded by the database's
existing `dg_fold` (case, accents, the Polish ł, punctuation and runs of spaces; migration 0054), among the family's notices
(`tenders.UNIT_KEY`). Two spellings of one name ("POLITECHNIKA WARSZAWSKA", "Politechnika Warszawska") are one unit; nothing else is
grouped. A unit's label is its commonest spelling. A notice whose buyer is withheld names no unit. A buyer has a choice only with
two units or more.

**Measured on production (26 Oct, `prod/measure.out`, `prod/heads.out`; default scope, uncollapsed).** 3,464 buyers (families)
with notices, 4,842 units. **506 buyers get a dropdown** (two units or more): 448 with 2 to 5, 51 with 6 to 20, 7 with 21 to 100,
none above; 287 of the 506 are buyer families; 455 of their units have one notice. Largest: BAAINBw 67 units (9,735 notices),
Ministerstvo obrany 57 (10,476), Ministerie van Defensie 55 (5,023), MINDEF Air SIAé 37, DALO 28, DGA DO S2A 27, Direzione Armamenti
Terrestri 22, Estado-Maior da Força Aérea 16. (Collapsing a notice and its copy can only make a unit smaller; a unit left with
none disappears from the choice.)

## 2. API

- `GET /v1/buyers/{slug}` returns `units`: `[{key, name, tenderCount, coreCount}]`, most tenders first. `key` is the value of
  `unit=`; `name` the unit's name as stated; `tenderCount` its notices as the tender list counts them with `unit=` (status all,
  the default scope); `coreCount` the military goods and works among them (the brief's "notice count, defence count": every
  notice here is a defence notice, so the two figures are the default scope and its core part). Empty below two units.
- `unit=` (at most 400 characters, compared folded) on `/v1/tenders`, `/v1/tenders/scope-counts` and `/v1/tenders/export`: one
  more condition in `_tender_filters`, the one WHERE every list, count and export reads (`NOT o.buyer_withheld AND
  dg_fold(o.buyer_name_raw) = dg_fold(%s)`). Only with `buyer=` (422 otherwise: it is read on a buyer's notices, by index).
- **Lists and counts agree.** A unit's count is the list's own collapse with the twin required in the same unit
  (`collapse_clauses(same_unit=True)`: the TED twin, the rectificatif, the re-publication and the Polish bulletin/mirror pair,
  `mirror_clause(extra=)`), which is what `unit=` in the list's WHERE says; so the dropdown's number is the total its list shows
  (test below, with a TED copy and a bulletin/mirror pair whose copies state two different units).
- **Same snapshot as now.** The collapse costs 2.3 s for Ministerstvo obrany and 4.7 s for BAAINBw on production (`units268.out`,
  `units196.out`); every family in one statement ran past 30 s (`unitsall.out`; the buyer aggregate itself took 17 s). So the
  worker computes the units of the 506 buyers that state two names or more, one buyer per statement, with the other snapshots
  (`ops/warm_lists`, `list_snapshot` key `buyer-units`, `tenders.compute_buyer_units`; head selection 1.2 s, the 506 buyers hold
  236,251 notices: about 1 to 2 minutes per run by the per-notice cost measured), and the API reads it as it reads the buyer counts
  (`buyer_base`), kept in memory 5 minutes. With no stored result (a fresh deploy, a test) one buyer's units are counted live in a
  1.5 s time box; past it the buyer shows no choice until the worker's next run. A buyer that gains its second unit after a run
  shows the choice from the next run (at most 4 hours).

## 3. Web

`app/(public)/buyers/[slug]/page.tsx`, `lib/buyer-units.ts`:

- A "Unit" choice (the site's branded `Select`, WP-58: the native select is the control, labelled "Unit"; with a mouse its own
  listbox, on a phone and without script the system picker) in a GET form of its own, only when the buyer has two units or more:
  "All units (N)" first (N: the buyer's tenders), then each unit with its tenders. Button "Show unit". The CPV form carries the
  chosen unit and the unit form carries the CPV filter (the CPV form's address stays `?cpv=445`, e2e/wp90).
- The choice travels in the URL (`?unit=<key>`); pagination and "Show all" keep it. An unknown or empty unit shows all units.
- A unit's view: the header says it (`Unit: <name>` under the title), the status line says "Showing the tenders of <unit>: N open
  and M earlier" with a "Show all units" link; the open, planned and earlier lists are the unit's; the figures above and the
  profile stay the whole buyer's (as under a CPV filter).
- `noindex` whenever `unit` is given; the canonical stays the plain page.
- Phone 375 px and both themes: the e2e runs desktop and mobile-375 (the page's horizontal overflow is checked by `visit`) and a
  dark-theme case (the select reads on the dark surface). Card hover: no card was added or changed (the tender cards are the
  shared `TenderCard`).

## 4. Politechnika Warszawska

**Production now (`prod/pw.out`, `pw2.out`, `pw3.out`, `pw4.out`).** Three live rows, all the university: 60 "politechnika
warszawska" (2 notices, pl_atlas), 29844 "politechnika warszawska szkola biznesu" (5 notices, pl_ezam; NIP 5250005834, PIC
999884052; its 16 aliases are the university, its faculties and the business school), 283751 "politechnika warszawska" (no notice;
REGON 000001554; 8 rows merged into it). 29844 is shown under 283751 (family `shared_tax_id`); 60 is a buyer of its own. Every one of
the 7 notices states "Politechnika Warszawska" (two spellings): the faculty and business-school names are aliases from notices we
do not hold.

**After merging 29844 and 283751 into 60.** One buyer, head 60, "Politechnika Warszawska", 7 notices of which 5 are listed (the two
2025 notices are each held from the bulletin and its mirror and shown once). **The dropdown would not appear: one unit**
("Politechnika Warszawska", 5). It would appear the day a notice stating a faculty is held. Head 60 is the university's own name;
without a head the plan picks 29844 (most notices: the business school's name), so the ids file names the head.

**Ops step for the orchestrator (not run).** File `docs/verification/round6/wp144-pw-accept-ids.csv` (2 lines, both ACCEPT, head 60):

```
cd /opt/dgate && docker compose run --rm -T worker python -m dgate.ops.accept_merge_candidates --ids-file - < wp144-pw-accept-ids.csv
# then, if the report matches, the same with --yes
```

Expected report (checked offline with `plan_reviewed` on the production rows, `prod/pw_plan.py`, and the candidate rows of
`pw4.out`): `reviewed {'ACCEPT': 2, 'REJECT': 0, 'UNSURE': 0}: 2 accepted in 1 groups (2 rows to merge); refused {}; the review
decided where the rules said {'public_body': 1, 'different_reg': 1}; other pending candidates of those pairs to merged 19; to reject
0; unsure left pending 0`, and `head 60 'politechnika warszawska' <- 29844 'politechnika warszawska szkola biznesu', 283751
'politechnika warszawska' (candidates [2508832, 2509709])`. With `--yes`: `merged 2 rows in 1 groups`; 21 candidates set to
`merged` (the 2 and 19 other pending pairs between the rows); 60 takes NIP 5250005834, the VAT number and PIC 999884052; 283751
keeps REGON 000001554 (merged with `allow_identifier_conflict`: a NIP and a REGON are one body's two registers); the 8 rows merged
into 283751 point at 60; the family 29844 -> 283751 is dropped by the family run. Undo: the `--undo-batch` line it prints.
Afterwards `/buyers/60-...`: 5 tenders; `/buyers/283751-...` and `/buyers/29844-...` redirect to it.

## 5. Buyers whose notices are all outside the default scope (added item)

**Before.** WP-143 item 8: 9421 "Dyrektor Urzędu Morskiego w Gdyni" (283618 merged into it) holds one defence notice, 40319 (TED
122655-2017: a military code, `dual_use`, buyer class "other"), in neither the core nor the supply scope; a buyer with no notice in
the default scope had no page (404), and the notice's buyer line had no link (`buyerSlug` null).

**Measured on production (`prod/outside.out`).** **2,084 buyers gain a page** (live heads, 8,594 notices between them), beside
the 3,464 with a page now.

**Change.**
- `get_buyer`: a buyer the stored aggregate does not hold is counted live (`_live_buyer`): in the default scope when it has a
  notice there (a buyer newer than the worker's last run, which was a 404 until the next run), else under `all`. Such a page has
  `scope: "all"`, its counts are its notices under All notices (collapsed, as the list counts them), `openCoreCount` null, no
  units. A merged row answers its head; a suppressed one keeps its 410.
- `buyers_with_page`: any defence notice we show (any scope), so the notice's buyer line links to the page.
- Page: a note in the site's scope words: "None of this buyer's notices is in the default scope, All defence (military goods and
  works and other purchases by armed forces). The notices listed here are under All notices: everything, also dual-use purchases
  of civil buyers, for example a military product code bought by a civil buyer. ..."; its lists ask `scope=all`; the profile
  (default-scope figures) is not shown.
- **Sitemap and indexing, as dual-use notices are treated now:** a notice page is indexed only in the core scope and the tender
  sitemap lists core notices only, so these buyer pages are `noindex`, are not in the buyer sitemap (`/v1/buyers/slugs` reads the
  default-scope aggregate) and not on the buyer list (`/v1/buyers`, default scope).

## Tests

- Backend unit `tests/unit/test_wp144.py` (3): spellings of one unit add up and the commonest is its name; one name gives no
  choice; the same-unit collapse reaches all four rules; `unit=` without `buyer=` is a 422.
- Backend integration `tests/integration/test_wp144.py` (7): Politechnika Warszawska after a merge (two units, a TED copy, a
  bulletin/mirror pair stating two units, a withheld notice): each unit's count equals its list's total, open counts per unit, the
  name as stated finds its unit; scope counts and export with `unit=` equal the list; 422 cases; one name, no units; the worker's
  stored units equal the live ones and the API reads them until the next run; item 5: a dual-use-only buyer (with a merged row)
  has a page with `scope: "all"` and counts equal to its `scope=all` list, the notice's `buyerSlug` is its slug, it is neither on
  the buyer list nor in the slugs; a buyer with default-scope notices keeps `scope: "relevant"`; an unknown buyer is a 404.
- Web lib check `lib/buyer-units.check.ts`: folding, choosing a unit by key or stated name, unknown/one-unit cases, option labels.
- e2e `e2e/wp144.spec.ts` (desktop, mobile-375): the choice narrows the lists, travels in the URL, header and status line, noindex
  and canonical; with the CPV filter; unknown unit; no choice for a one-name buyer; the branded select by keyboard (desktop);
  without script (GET form); dark theme. `e2e/wp144-api.spec.ts` (fake API, desktop and mobile): the outside-scope page's note,
  its listed notice, noindex, its lists asked with `scope=all`; the notice page links its buyer line to it.

**Results (test copy, 26 October 2026; logs in `D:\DEFENCEGATE TESTS\wp144\`).** ruff clean; unit suite green; integration
1,565 passed, 5 failed (`test_network_api` and `test_tender_export`: "server closed the connection" from the test Postgres, which
was in recovery after the laptop's restart; two `test_search` group time boxes and one `test_wp98` order on the loaded machine);
those 5 and `test_wp144.py` run again on their own: 12 passed. tsc clean; lib checks 83 ok, 0 failed. Production build 0. e2e
batch (wp144, wp144-api, wp143-api, wp100, wp105, wp111, wp121, wp47, wp87, wp88, wp90, wp96, wp120, wp58, layout, routes; every
project): 297 passed, 22 skipped, 1 failed (wp144-api on fake-api-mobile-375: its check of the fake API's request log read the
other test's notice-page request; the check now looks at the earlier list's request), then wp144 + wp144-api + wp143-api on the
same build: 21 passed, 1 skipped (the keyboard test on the phone). Before the fix of the unit form, e2e/wp90 caught the CPV form
submitting an empty `unit=`; the unit choice then got its own form.

## Files

Backend: `dgate/tenders.py`, `dgate/ops/warm_lists.py`, the two test files. Web: `app/(public)/buyers/[slug]/page.tsx`,
`lib/buyer-units.ts` (+ check), `lib/types.ts`, `lib/filters.ts` (`unit` in `toTenderQuery`), `lib/mock/tenders.ts` (one demo
notice states its unit; demo units), `e2e/wp144.spec.ts`, `e2e/wp144-api.spec.ts`, `e2e/support/fake-api.mjs` (buyer 779003,
notice 779004), `playwright.config.ts` (the new fake-API spec). Docs: this file and `wp144-pw-accept-ids.csv`.

Overlaps with WP-143 (merged into integration before item 5): `tenders.py` (WP-143 added the person wording in `to_tender`,
`_present` and `get_buyer`; my changes sit beside them), `ops/warm_lists.py` (one view and one branch), `fake-api.mjs` and
`playwright.config.ts` (my lines after WP-143's). No conflict at the merge.

## Open items

- After deploy, run the worker's `warm_lists` once (or wait for its 4-hourly run): the tender list's snapshot keys now name `unit`
  (`unit=None`), so the stored list snapshots are read again only after the next run, and the `buyer-units` snapshot does not exist
  before it (until then, a large buyer's units are counted live in the 1.5 s box and may be missing).
- The worker's run grows by about 1 to 2 minutes (the 506 buyers' collapsed unit counts).
- A unit is a stated name: "Česká republika - Ministerstvo obrany" and "Ministerstvo obrany" are two units of the Czech ministry
  (57 in all). Grouping such forms is a naming rule, outside this package (no new merging rule, as the brief says).
- `api.row_scope` still says "supply" for a dual-use notice (WP-143 item 8); not changed here.
