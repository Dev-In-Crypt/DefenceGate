# WP-66 self-check: the demand map, "Who buys what you make" (22 October 2026)

Branch `wp-wp66` from `integration` (9db8daf). Plan row: WP-66 of `docs/plans/MVP_SPAIN_AUTOMOTIVE_2026-10-21.md`. No model call, no
spending, no deploy, no push. Production was only read: short `SELECT`s and `EXPLAIN ANALYZE` in read-only transactions with
`statement_timeout` 30 s through `psql` in `dgate-postgres-1`, and one read-only `\copy` of `(id, cpv_codes)` of the defence-scope rows
(no names) to time the new index on the laptop. The suppliers router (`suppliers.py`) is not edited; its constants are imported.

## 1. What was built

| File | What |
|---|---|
| `backend/dgate/demand.py` | `POST /v1/readiness/demand`: one statement over the matched notices, then one read of the linked notices (and, with the PLACSP switch on, the PLACSP attribution of `suppliers.placsp_note`) |
| `backend/migrations/0099_cpv_heads_index.sql` | function `dgate_cpv_heads(text[])` (every 2-8 digit leading part of every code) and GIN index `opp_cpv_heads` on it, partial on `is_defence AND NOT suppressed`. 0098 is taken by WP-75 (`award_twin_set`) |
| `backend/dgate/api.py`, `hardening.py` | router included; rate-limit cost 5; the body limit of `/v1/readiness` (16 KiB) applies |
| `web/lib/demand.ts`, `components/readiness/demand.tsx`, `use-readiness.ts` (`useDemand`) | request (CPV codes and the five countries, nothing else), the full map (`DemandMap`) and the short table (`DemandSummary`) |
| `web/app/api/readiness/demand/route.ts`, `lib/api-proxy.ts` | the site's pass-through route; `forwardPost` shared with the assess route (same behaviour, now one function). A demo build (`DG_USE_MOCK=1`) answers `lib/mock/demand.json` |
| `web/components/readiness/report.tsx` | the hidden section of WP-67 is shown when the supplier page holds CPV codes; the "what left this browser" line names the second request |
| `web/components/readiness/results.tsx` | the short version on `/readiness/results` when the supplier page was used |
| copy | `/readiness`, `/readiness/supplier` and the supplier form now say the CPV codes alone are sent for the map (they said the codes never leave the browser) |
| `docs/design/API_CONTRACT.md` | the endpoint |

**Rules of the answer.** Window: 1,096 days to today, by `published_at`, else `notice_date`. Scope: `is_defence AND NOT suppressed` in
ES, DE, FR, PL, NL (the scope of `ANGLE1_DATA_CHECK`). A code matches by its level (the code without trailing zeros: 34300000 is group
`343`, 44470000 class `4447`, 35000000 the division). **Procurements**: a procurement published several times counts once (eForms
procedure identifier of the notice or of the TED notice a national notice names; else the TED number; else country + national number,
which the two Polish sources share). **Directive**: `sig_legal_basis`. **Buyers**: families (`buyer_family_member`, as `dgate_buyer_head`);
core = `sig_buyer OR buyer_class = 'defence'`; a withheld buyer is counted, never named; two families with one name are one line of the
top list. **Winners**: award rows on the matched notices that the supplier map would serve less its core-scope test (a defence body's
commodity purchase under the civil directive is demand too): not excluded, not superseded, not suppressed, not a natural person
(`individual_reason`); PLACSP rows only with `DGATE_PLACSP_AWARDS_PUBLIC=true`. Mosaic rule: a winner is named only with at least 3
procurements (`suppliers.K_MIN`) in that country, at most 10 per country; the rest is one count `{winners, awards}`. Links: 5 newest
procurements per country and 3 notices per named winner, each with its page here and its source URL. Coverage line on every answer.
Nothing stored, cached or logged; a refused body is not echoed (the app's validation handler).

## 2. Acceptance criteria

| Criterion | Met | Evidence |
|---|---|---|
| Stateless POST, CPV codes and countries in the body, nothing stored or logged | yes | `test_nothing_is_stored_or_logged` (row counts of 5 tables unchanged, codes not in any log record); no cache decorator; site route keeps nothing |
| Strict validation, max 15 codes, max 5 countries | yes | 8-digit codes only, unknown keys refused, countries from the five only, no repeats; unit + integration (7 refused bodies, none echoed) |
| Prefix match by the code's level | yes | `test_a_code_stands_for_its_level_in_the_tree`, `test_a_code_matches_by_its_level`; production candidate sets equal with the inline function and with the index (2,791 / 20,195 / 260,987 rows) |
| Last 3 years, 5 countries, core vs other buyers, notices, number under 2009/81, awards, top winners as legal entities, mosaic aggregate | yes | `test_counts_one_procurement_...`, `test_names_only_legal_entities_...` (natural person with 3 awards never counted or named, removed company never named, a 1-award winner only counted) |
| Links to the notices | yes | `latest` and winner `notices` (site slug + source URL); e2e checks the links |
| PLACSP winners only with the switch, TED always | yes | integration test both ways; production numbers both ways below |
| Honest coverage line | yes | `coverage` (and `winnersFrom`, `notice`) in the answer, shown in both views; e2e checks it |
| Under 1 s cold on production volume | **realistic profiles yes, measured warm; the extreme 15-division case no (about 3 s)** | section 4 |
| Index via migration after 0097 | yes | 0099 (0098 is WP-75's) |
| Web: report section filled, short version on results, per country, coverage line, print as WP-67 | yes | e2e `wp66.spec.ts` (8 tests), `wp67.spec.ts` updated; print: own page, outside links print their address |

## 3. The demand map on production (22 October 2026, switch off as in production)

Measured with the endpoint's own Python on production data: every statement rendered with its parameters and run through `psql`
read-only (the function of 0099 inlined, since it is not on production). Three sample companies, 5 codes each:

- **castings**: 44470000 cast-iron products, 34312000 engine parts, 34322000 brakes, 42140000 gears, 44210000 structures;
- **electronics**: 31711100 electronic components, 31712300 printed circuits, 31610000 electrical equipment for engines and vehicles,
  31612000 wiring looms, 31400000 batteries;
- **vehicle parts**: the WP-65 sample profile (34300000, 34100000, 35421000, 42600000, 44300000).

Columns: procurements | under 2009/81 | buyers core/other | with a winner | winners (TED only).

| Profile / country | ES | DE | FR | PL | NL | All five |
|---|---|---|---|---|---|---|
| castings | 123 \| 2 \| 25/15 \| 2 \| 2 | 55 \| 16 \| 16/3 \| 11 \| 15 | 28 \| 14 \| 13/2 \| 2 \| 2 | 364 \| 3 \| 34/41 \| 0 \| 0 | 11 \| 3 \| 2/0 \| 2 \| 3 | 581 \| 38 \| 90/61 \| 17 \| 22 |
| electronics | 112 \| 2 \| 26/7 \| 3 \| 8 | 13 \| 7 \| 2/1 \| 7 \| 4 | 12 \| 8 \| 8/2 \| 3 \| 3 | 876 \| 5 \| 46/23 \| 4 \| 8 | 7 \| 1 \| 1/0 \| 1 \| 1 | 1,020 \| 23 \| 83/33 \| 18 \| 24 |
| vehicle parts | 1,515 \| 33 \| 46/33 \| 23 \| 24 | 306 \| 39 \| 17/45 \| 25 \| 21 | 87 \| 37 \| 30/21 \| 7 \| 17 | 2,313 \| 50 \| 64/81 \| 34 \| 26 | 90 \| 19 \| 3/3 \| 15 \| 17 | 4,311 \| 178 \| 160/183 \| 104 \| 104 |

Per code (all five countries): castings 4447: 6, 34312: 64, 34322: 30, 4214: 31, 4421: 463; electronics 317111: 95, 317123: 3, 3161: 14,
31612: 4, 314: 940; vehicle parts 343: 1,725, 341: 1,308, 35421: 110, 426: 474, 443: 836.

Top buyers in Spain: castings: JAE Mando de Apoyo Logístico (17), JAE Fuerza Terrestre (10), Intendente de Ferrol (7); electronics:
DGE Jefatura de Apoyo Logístico de la Armada (13), Intendente de San Fernando (13), Intendente de Rota (11); vehicle parts: JAE Mando de
Apoyo Logístico (259), Jefatura de Intendencia de Asuntos Económicos Este (199), JAE Fuerza Terrestre (95).

Named winners, switch off (TED only, at least 3 procurements): castings none; electronics EXIDE Technologies GmbH (DE, 3), ANKOL Sp. z o.o.
(PL, 4), Borimex Sp. z o.o. (PL, 3); vehicle parts MADZEAL, S.L. (ES, 3), BMW AG (DE, 3), Esser GmbH (DE, 3), AUTO PODLASIE (PL, 5), BIWAR
(PL, 4), ZDUNEK PREMIUM (PL, 4), AUTOCOMP MANAGEMENT (PL, 3), CENZIN (PL, 3), CLAYMORE GROBLEWSCY sp. j. (PL, 3). Every other winner is a
count (ES vehicle parts: 23 winners, 25 awards).

**With `DGATE_PLACSP_AWARDS_PUBLIC=true`** (the switch the owner has not turned on), Spain changes completely: castings 92 procurements
with a winner and 82 winners (named: Suyfa Defence 9, ALFARIVER DEFENSE 6, five with 3); electronics 91 and 64 (Suyfa Defence 15, MADZEAL 10,
AEG Power Solutions Ibérica 9, Sánchez Sur 8, ...); vehicle parts 1,229 and 416 (Ferretería Ferayu 73, Suministros Mera 56, URO Vehículos
Especiales 49, Suyfa Defence 40, Iturri 38, Iveco España 36, ...; 406 more winners as a count). The incumbent side the data check called
"nearly empty" is there once the switch is on.

What the numbers say, as `ANGLE1_DATA_CHECK` found: mostly MoD contracting units buying commodities under the civil directive
(2009/81 share 2 % in Spain, 13 to 43 % in DE, FR, NL); Poland is the largest by count. The procurement key removes the double counting
of that check: vehicle parts 1,810 notice rows in ES become 1,515 procurements, DE 834 -> 306, FR 148 -> 87, NL 178 -> 90, PL 5,160 -> 2,313.

Sample of 15 Spanish notices of the vehicle-parts map (random by `md5(id)`), checked by hand: does a code fall under a chosen code, is the
row in the window and scope? 15 of 15 yes (firefighting vehicles and buses under 341 "motor vehicles"; spare parts under 343 and 35421;
workshop machinery under 426; hardware under 443). One of them is a city council (Ayuntamiento de Cox, counted as "other" buyer): in the
defence scope by the classifier, not by this endpoint; it is what "other defence-scope buyer" means.

## 4. Timing (production, read-only)

Without the index (today's production, the function inlined): the whole statement 3.7 to 4.6 s per profile (the prefix test unnests every
candidate row's codes: 177,070 rows for six prefixes, 1.47 s for the match alone).

With what 0099 gives (the matched ids handed in, `o.id = ANY(ids)`, the rest of the statement unchanged), `EXPLAIN ANALYZE`, two runs:

| Profile | candidate rows | statement |
|---|---|---|
| castings | 2,791 | 164 / 276 ms |
| electronics | 3,558 | 193 / 213 ms |
| vehicle parts | 20,195 | 362 / 290 ms |
| 15 whole divisions (34, 31, 35, 44, 42, 39, 19, 30, 32, 33, 38, 09, 45, 50, 15) | 260,987 | 2,916 / 3,476 ms |

The index itself, built on the laptop over the 388,802 production `(id, cpv_codes)` rows: 18 MB (the codes table 33 MB), built in 11 s,
the bitmap lookup 0.3 ms (castings), 2.4 ms (vehicle parts), 40 ms (15 divisions), returning exactly the candidate sets above.

Not met as written: "under 1 s cold" holds for realistic profiles as measured, but these runs are warm (the buffers were in cache; a cold
cache cannot be produced read-only), and the extreme 15-division request takes about 3 s, under the API role's 5 s budget but not 1 s.
Three changes took it from 11 s: the per-row array of heads dropped from the statement, the procurement key hashed to `bigint` before
the `count(DISTINCT)`s, and the buyer family read as a join instead of the per-row function.

Production commands for the orchestrator (in this order):

```
-- no write lock on opportunity while a load runs; then the migration's own statement is a no-op
CREATE OR REPLACE FUNCTION dgate_cpv_heads(codes text[]) RETURNS text[] LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $f$
  SELECT COALESCE(array_agg(DISTINCT left(c, n)), '{}') FROM unnest(codes) AS c, generate_series(2, 8) AS n WHERE length(c) >= n $f$;
CREATE INDEX CONCURRENTLY IF NOT EXISTS opp_cpv_heads ON opportunity USING gin (dgate_cpv_heads(cpv_codes)) WHERE is_defence AND NOT suppressed;
```

Expected: about 18-20 MB of disk, under a minute. Then re-time with the real index:
`EXPLAIN ANALYZE` of `demand.QUERY` (vehicle parts) and one `POST /v1/readiness/demand` from inside `dgate-api-1`.

## 5. Tests and results

New: `backend/tests/unit/test_wp66_demand.py` (12: level of a code, request bounds, price, coverage line, the demo JSON is the
response model's shape), `backend/tests/integration/test_wp66_demand.py` (11: counts and twins, buyer split, withheld buyer, mosaic rule
and persons, the switch both ways, level match, index used, 7 refused bodies, nothing stored or logged), `web/lib/wp66.check.ts`,
`web/e2e/wp66.spec.ts` (4 tests x desktop and 375 px). Changed: `web/e2e/wp67.spec.ts`: the report section is now shown for the sample
profiles (they hold CPV codes) and the demand POST is the one other non-GET request allowed; nothing loosened (its body is checked in
`wp66.spec.ts`).

Local, `D:\DEFENCEGATE TESTS\wp66`, own venv, Postgres 17 container `dgate-wp66` on 55466, TZ=UTC, web mock environment of `web.yml`:

| Check | Result |
|---|---|
| ruff | All checks passed |
| unit | 3073 passed, 1186 deselected |
| integration (`-m integration`) | 1186 passed (10 min 20 s) |
| `tsc --noEmit` | exit 0 |
| `npm run check` | all ok, incl. `wp66.check.ts` |
| `next build` (mock) | exit 0 (the known Windows-only standalone trace warning, as WP-65/67) |
| Playwright, 4 workers, desktop + 375 px | **501 passed, 47 skipped, 0 failed** (after the last web change, a React key, re-run: tsc, build, wp66/wp67/wp73 specs 34 passed; first full run: 2 failures in `wp73.spec.ts`, which asserts the CPV hint text I had reworded; the wording "recommended for the demand map" is kept and extended instead) |

## 6. Hostile review

Found and fixed 6:
1. The copy of `/readiness`, `/readiness/supplier` and the supplier form said the CPV codes never leave the browser: now they say the
   codes alone are sent for the map. The report's "what left this browser" line names both requests.
2. A buyer was shown twice under one name (two organisation rows of one German federal office in two families): one line now.
3. The first statement took 11 s for 15 divisions (above the 5 s budget): rewritten (section 4).
4. A mis-encoded "e-Zamówienia" in the coverage line (edited through a shell with the wrong code page): fixed in code and demo JSON.
5. React key of a named winner was its name (two companies can share one): index-qualified.
6. My integration world set `suppressed` / `buyer_withheld` on insert, which the insert trigger re-derives: the test passed for the
   wrong reason until set afterwards; the withheld-buyer check now really proves a withheld buyer is not named.

## 7. Limits and open points

- With the switch on, a TED and a PLACSP award of one procedure count once when the winner resolves to one organisation (distinct
  organisation and procurement key); two unmerged organisation rows of one company with one tax id count as two winners. The supplier
  map handles that with `award_twin`, which costs 5 s a read; WP-75's `award_twin_set` (migration 0098, not on `integration` yet) would
  allow `a.id NOT IN (SELECT award_id FROM award_twin_set)` here. Not done: it depends on uncommitted work.
- Polish partnerships named after their partners ("CLAYMORE GROBLEWSCY sp. j.") are legal entities to the directory and are named once
  they have 3 awards. The demo JSON leaves that one out; the owner may want the directory to treat `sp. j.` / `s.c.` names as persons.
- Counts of notices, not money (values not shown: budgets and framework ceilings as often as contract values).
- `/v1/readiness/demand` is not added to Caddy's public allow-list (the site calls it over the internal network); add it if the API
  should offer it to outside callers as it does `/assess`.
- Navigation: no new page. Deletion candidates: none. Scratch: container `dgate-wp66` (with the database `measure` holding the copied
  `(id, cpv_codes)`), `D:\DEFENCEGATE TESTS\wp66`, the scratchpad files; removed at the end except the test folder.
