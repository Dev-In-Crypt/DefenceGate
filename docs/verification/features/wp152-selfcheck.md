# WP-152 self-check: competitor intelligence for a company (idea 3)

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-FEATURES-1.md`, section WP-152 (owner request of 27 Oct 2026). Branch `wp-wp152` on
`integration`. Nothing merged, pushed or deployed. Screenshots: `D:\DEFENCEGATE TESTS\wp152\shots\`.

## What was built

On every supplier page (`/suppliers/{slug}`), right under the head facts, three new blocks, all from one new endpoint
`GET /v1/suppliers/{slug}/competition` (`backend/dgate/competition.py`):

1. **Competitors.** The other legal entities that won a contract of the same buyer (buyer family, `dgate_buyer_head`) under the same CPV
   class (first four digits of any code of the notice) in the same window. A "market" is one buyer and one class. Ranked by overlap: the
   other company's contracts in the shared markets, then the number of shared markets. Columns: its contracts there, shared markets (and
   buyers), this company's own contracts in those markets. First 20 listed, the total said. Each row links to the competitor's page.
2. **Where it wins.** Contracts per buyer country and per CPV class (a contract under codes of two classes is in both), next to the
   page's existing per-year, per-division and buyers tables; and the typical stated contract value: the median of its contract values in
   its commonest currency, with how many of its contracts state none and how many are in another currency.
3. **Its share.** For its five top CPV classes and five top buyer countries: its contracts out of every contract of the set there
   (a contract of several winners counted once), and its contract value out of all stated contract values there, in that slice's
   commonest currency, never converted, with the number of valued contracts behind the total.
4. **Company report** (paid, behind the flag): `/suppliers/{slug}/report`, print-ready (the browser's print dialog saves the PDF; a sample
   is `shots\report.pdf`): head facts, contract values, the three blocks above, main buyers and the company's **EU project partners**
   (the existing `/v1/organisations/{slug}/partners`), the logo and date on paper, the site's header, footer and the print button left out.

### One definition, reused

No second definition of an award, a contract, a value or a defence buyer. Every number is read from the rows the market overview already
stores and sums (`money.compute`, list_snapshot `contract-values`, renewed after every award load, every 4 hours and at the worker's
start): one row per contract (`award_set.KEY`) and winner of `award_set.scope()`, valued by `suppliers.value_of`/`best`/`is_suspect`
(contract values only). The only change there: each row now carries its contract key (`k`, `award_set.KEY_HASH`), so a slice counts a
contract of several winners once. Checked by the integration test against the same database:

- the competition's `contracts` equals the supplier page's `noticeCount`;
- its count in a CPV class equals its `awardCount` on `/v1/suppliers?cpv=<class>` (the list's product-code filter);
- its value in the class equals its page's contract-value sum.

A snapshot stored before this change (no `k`) is not read: the blocks are then left out ("available": false) until the worker's next
round, never guessed.

## The known defect: one company under several organisation rows

Nothing is merged. A row under the **same name in the same country** (the WP-111 namesakes: e.g. Rheinmetall Electronics GmbH as
426698 / 428360 / 430165, kept apart by their registration numbers) shows up as a *competitor* of itself, because it wins at the same
buyers under the same classes. Such a row is marked "Same name and country: possibly this company under another record", and a company of
the same curated group (`ops.company_groups`) "Same group: ...". The effect on the numbers:

- **Competitors:** the namesake rows appear in the list (marked), usually near the top, since they win the same markets.
- **Where it wins / typical size:** each row counts only its own contracts, so the company's true totals are the sum of its rows.
- **Share:** each row's share is too small by the other rows' part; the totals (denominators) are right, since every contract is in the
  set once whatever row won it.

How much it distorts the result needs a production read, which this run was not allowed to do (see below).

## Flags

| Flag | Default | Effect |
|---|---|---|
| `DGATE_COMPANY_REPORT_OPEN` (API, `config.company_report_open`; passed by `infra/docker-compose.yml` to `api`) | `0` | Off: `billing.may(user, "company_report")` is false for every account, `features` never lists it, the API's `reportOpen` is false, the supplier page shows no report link and `/suppliers/{slug}/report` is a 404. On: the link shows; the report asks for sign-in, then opens for an account whose `features` include `company_report`. |

The plan gate is the existing one (WP-124, `billing.FEATURES`): `company_report` is set to the Consultant plan as a placeholder; which plans
carry it is the owner's decision (one line in `backend/dgate/billing.py`). While no plan is on sale, `billing.may` withholds nothing (the
WP-124 rule), so with the flag on and billing closed every signed-in account gets the report. Competitors, where it wins and its share stay
free on the supplier page (the brief marks only the report as paid).

## Tests

- Backend unit `tests/unit/test_wp152.py` (5): ranking by overlap, a withheld buyer in no market, a co-won contract once in a slice, the
  median and the "state none" count, one currency per share, index rebuilt per snapshot; the switch of `company_report`.
  `tests/unit/test_wp124.py`: the pinned set of gated features now includes `company_report` (moved on purpose; free still has none).
- Backend integration `tests/integration/test_wp152.py` (3): the equalities above on a real Postgres, namesake marked, no snapshot / an
  old snapshot gives `available: false`, a removed company is 410, the switch is said.
- Area runs: ruff clean; unit suite 4,104 passed; integration of the area (test_wp152, test_supplier_map, test_wp105, test_wp98c,
  test_billing_wp124, test_wp111, test_network_api) 121 passed. The full integration suite was not run (batch rule).
- Web: tsc clean; lib checks all ok, new `lib/wp152.check.ts` (share percent never 0% for a small share, value share only where a value
  is stated, the size line, class labels never take a group's title as the class's).
- Playwright: `e2e/wp152.spec.ts` (demo build: blocks, links, same-name mark, words the map must not carry, no report link and a 404
  while the switch is off, hover of a competitor link, no horizontal scroll at 320 px light and dark) and `e2e/wp152-api.spec.ts`
  (@fake-api: report link, sign-in gate, paid-plan gate, the report with partners, print media hides the tools). Run on a fresh build
  with every spec that opens a supplier page (suppliers, wp47, wp79, wp80, wp81, wp85-90, wp95, wp96, wp100, wp105, wp116, wp124): 295
  passed, 33 skipped (gated account specs), 0 failed, desktop and 375 px.
- Screenshots (`shots\`): supplier page 1440 and 375, light and dark (first screen and full), 320 px (scrollWidth 320 = clientWidth),
  the report at 1440 and 375 in both themes, in print media, and `report.pdf` (A4, Chromium's print).

## Production reads needed (access was denied to this builder)

Read-only, with `SET statement_timeout = '30s'`, outside 10:50-11:30 and 15:50-16:30 UTC:

1. Size of the stored rows: `SELECT jsonb_array_length(body->'org') FROM list_snapshot WHERE key = 'contract-values';` (the index is built
   once per snapshot per API process: about 1.2 s for 250,000 rows on the laptop, `analyse` 0.1 s for a 400-contract company).
2. How many winners share a name and country with another winner row (the distortion above):
   ```sql
   WITH w AS (SELECT DISTINCT COALESCE(r.merged_into, r.id) AS id FROM award a JOIN organisation r ON r.id = a.organisation_id
               WHERE a.superseded_at IS NULL AND a.excluded_reason IS NULL)
   SELECT count(*) AS names, sum(n) AS rows FROM (
     SELECT lower(o.canonical_name), o.country, count(*) AS n FROM organisation o JOIN w ON w.id = o.id
      WHERE NOT o.suppressed AND o.individual_reason IS NULL GROUP BY 1, 2 HAVING count(*) > 1) g;
   ```
3. After the deploy and one worker round: `/v1/suppliers/426698/competition` from the server host (`curl --resolve`), to see the
   Rheinmetall Electronics rows marked among its competitors, and the response time of a cold and a warm call.

## Left out (smallest version a paying customer would recognise)

- No merge or "show all records of this company together" view (the owner's standing rule; a family view like the buyer families would
  need its own evidence rule).
- No head-to-head (same contract, both winners) or lost-bid data: notices name winners only.
- No filters on the competitor list (country, class, years); no CSV of competitors; no trend over time.
- The report is DefenceGate-branded (logo and date). "Branded" for a consultant may mean the consultant's own logo: not built.
- No server-made PDF: the browser's print dialog makes it (no new dependency).
- The share is per class and country only, not per buyer.

## Open questions for the owner

1. Which plans carry the company report (now Consultant as a placeholder) and when to switch `DGATE_COMPANY_REPORT_OPEN` on.
2. Should competitors and shares stay free on the supplier page, or only the first rows (as WP-154 does for its list)?
3. The supplier map's old rule "no share" (WP-37, mosaic effect) is lifted for this feature by the brief; the page's About text now says
   what the shares are. Confirm.
4. "Branded" report: our brand, or the customer's logo?
