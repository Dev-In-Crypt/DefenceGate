# WP-81 self-check: contract values per supplier, and every legal-entity winner named (22 October 2026)

Branch `wp-wp81` from `integration` (a49580d, WP-80 merged). Two owner decisions of 22 October 2026, both rule changes (the old
assertions were rewritten to the new rule, none deleted or skipped):

1. "хочу показывать, это полнота, может как-то разворачиваемый блок сделать": show the **sum of contract values per supplier**, in a
   collapsed block, wherever a supplier's awards are listed. Lifts "no sum of values per supplier" (WP-37/WP-80) for sums only.
2. Scope addition ("да"): **name every legal-entity winner**, whatever its number of awards. Lifts the `K_MIN` = 3 naming and group
   rule for legal entities everywhere; natural persons and sole traders stay never named and never given a sum; suppression stays;
   the `MAX_OFFSET` paging cap stays.

Unchanged: no ranking by value (lists stay most contracts first), no share, no "sole source" label, suppression honoured. No deploy, no
push, no migration, no production read or write, no secret, no model call.

## 1. What was built

| Part | Files |
|---|---|
| `suppliers.valued()` (the profile's own per-notice value rule as SQL) and `suppliers.value_totals()` (the fold), shared by both endpoints | `backend/dgate/suppliers.py` |
| `GET /v1/suppliers/{slug}`: `values: {byCurrency: [{currency, amount, count, lotEstimates}], of, withoutValue, shared}` over every notice the profile counts (not only the 50 listed) | `suppliers.py` |
| `POST /v1/readiness/demand`: `approach.winners[].values`, same shape and rule over the answer's contracts (restores what a6c2bc3 removed, in the new form) | `backend/dgate/demand.py` (`apv` CTE) |
| `K_MIN` = 1: list filters never "withheld", summary publishes every group (`suppressedGroups` 0), demand names every legal entity in `topWinners` (still at most 10 per country) and `approach` (still 30 + every prime; `below` always empty) | `suppliers.py`, `demand.py` |
| Collapsed "Contract values" block (`Details`, native `<details>`/`<summary>`, 44 px target, prints open via the site's print rule) | `web/components/dg/value-totals.tsx`, `web/lib/value-totals.ts` |
| Block on the supplier page (header) and under each named winner of "who to approach" (report, printable report, results short list) | `web/app/(public)/suppliers/[slug]/page.tsx`, `web/components/readiness/approach.tsx` |
| Copy for the lifted rules (supplier map aggregate text, empty state, approach summary, country line, entry page) | `suppliers/page.tsx`, `approach.tsx`, `lib/demand.ts`, `readiness/spain-automotive/page.tsx` |
| Docstrings and contract | `suppliers.py`, `demand.py`, `docs/design/API_CONTRACT.md` |
| Demo data | `web/lib/mock/demand.json` (by hand, see 5), `web/lib/mock/suppliers.ts` |

## 2. The sum rules and where each is proved

| Rule | Evidence |
|---|---|
| A value only from a notice naming this one winner (`winners_in_notice` = 1); shared values attributed to none, counted in `shared` | `test_values_are_summed_only_where_a_notice_names_this_one_winner` (approach), `test_a_profile_states_the_notices_...` (profile: Rheinmetall's shared 2-2026, Indra's 5,000,000 for two winners: no sum) |
| Per currency, never converted; largest count first | `test_values_are_summed_per_currency_never_converted_and_lot_estimates_are_counted_apart`, `test_a_profile_sums_values_per_currency_beyond_the_listed_notices_and_without_removed_ones`, unit `test_wp81_values.py` |
| A sum of lots' estimated values (`value_kind` lot_sum) flagged apart from a stated total (`lotEstimates`; the block says "not a stated total") | same two tests; `wp81.check.ts` words |
| Placeholder (<= 1), the procedure's estimate (`estimated`), PLACSP / national values (no kind: the call's estimate) add nothing | `test_a_placeholder_an_estimate_and_a_national_value_are_no_value`, profile test (73-2026, 74-2026) |
| TED+PLACSP twins once | approach: `test_a_twin_pair_is_valued_once`; profile: `test_the_ted_record_stands_for_the_award_when_it_states_a_number_too` (value 1,500 once, twin listed under it) |
| "12 of 30 contracts state no value" | `withoutValue` in every test above; words in `wp81.check.ts`; e2e `wp81.spec.ts` |
| Framework ceilings: the data does not distinguish them, so the block says "Values as published by the buyer; some may be framework ceilings" | `VALUE_RULES`, `wp81.check.ts`, e2e |
| Period and sources: profile "All N notices naming it a winner, not only the ones listed below: TED result notices [and PLACSP award results] of the defence-relevant scope, from 2023"; approach "The contracts of this list: <since> to <until>, in <countries>, from TED [and PLACSP]" | e2e `wp81.spec.ts` |
| Removed on request out of the sum | profile test (75-2026 suppressed: its 4,000 is not in the sum, nor in `of`) |
| Natural persons: no name, no sum | `test_a_natural_person_is_never_named_and_never_given_a_sum` (approach); a person has no profile (410, existing tests) |
| No ranking by value, no share, no sole-source label | lists ordered by contracts as before (tests unchanged); e2e checks the words are absent; `wp81.check.ts` |
| Collapsed by default, keyboard | e2e `wp81.spec.ts`: closed on arrival (sum hidden), Enter on the focused summary opens it |

## 3. Every legal entity named (scope addition) and where it is proved

| Before (rule) | Now | Rewritten test |
|---|---|---|
| WP-39: a country/CPV filter selecting 1-2 suppliers answered `withheld: true` | listed; `withheld` always false (kept for compatibility) | `test_wp39.py::test_a_country_or_product_group_of_fewer_than_three_suppliers_is_listed`, `test_wp57.py` (Estonia by name/code) |
| Summary: groups of fewer than 3 suppliers held back | every group published, `kMin` 1, `suppressedGroups` 0, still no supplier name, the person still only counted | `test_supplier_map.py::test_the_aggregate_publishes_every_group_of_legal_entities_however_small` |
| WP-66: per-country winners named only from 3 procurements | from 1 (at most 10 per country, the rest counted as the end of the list) | `test_wp66_demand.py::test_names_every_legal_entity_and_never_a_person_or_a_removed_company` |
| WP-80: who to approach named from 3 | every legal entity (30 + primes; past them `more`) | `test_wp80_approach.py::test_every_legal_entity_winner_is_named_across_countries`, `..._twin_pair_...`, `..._prime_is_listed_past_the_end...`, `..._only_the_countries_asked` |

The copy keeps the old sentences for an answer with `kMin` above 1 (the demo answer, section 5) and says the new rule otherwise.

## 4. Budget (5 s API; the 30,000-notice cap of `/v1/readiness/demand` unchanged)

Measured locally only (no production access in this run), `D:\DEFENCEGATE TESTS\wp81\probe\perf.py`: a synthetic database at the cap
(30,000 matched TED notices, 5 countries, 8,000 winner organisations with a skewed distribution, 6,891 winners in the answer, a
third of the notices without a value, a fifth lot sums, PLN and EUR), five runs each, base = a49580d's `dgate`, new = this branch:

| Call | a49580d | wp-wp81 |
|---|---|---|
| `demand()` code 34300000, 5 countries | median 0.67 s (0.66-0.71) | median 0.83 s (0.81-0.89), +25 %: every winner now enters `ap`/`apb`/`apv` |
| `get_supplier()` largest supplier (1,490 awards) | 0.057-0.061 s | 0.071-0.097 s (one more statement) |
| `supplier_summary()` | 0.021-0.024 s | 0.022-0.030 s |

Projection, not a measurement: WP-80 measured 1.1-1.9 s on production for 22,921 matched rows and 2.3-2.6 s for 40,843 (above the cap);
+25 % puts the worst served answer near 2.4-3.2 s, under 5 s. **To confirm after deploy** (read-only, by the orchestrator): the WP-80
probe of section 4 of `wp80-selfcheck.md` with the branch's `demand.py`.

## 5. Demo answer (`web/lib/mock/demand.json`)

Not regenerated: it is production's answer and this run has no production access. Updated by hand, consistently, and only where the
data allows: each winner's `values` restored from production's own answer of 22 October 2026 that WP-80 removed them from (commit
a6c2bc3^, same winners, same rule: TED value of a notice with this one winner, once per procurement), in the new shape
(`count` = the old `contracts`; `withoutValue` = contracts minus the valued ones; `shared` and `lotEstimates` were not in that answer
and are set to 0). Its `kMin` stays 3 and its winners stay those named under the old rule: names of the winners with 1-2 awards cannot
be made up. The copy reads `kMin` and says the old rule for this answer, so the demo build stays truthful. **Open: regenerate it from
production after deploy** (then `kMin` 1, `below` empty, `shared`/`lotEstimates` real; `wp66.check.ts`/`wp80.check.ts`/e2e read it
generically and will follow).

## 6. Test runs

Local, `D:\DEFENCEGATE TESTS\wp81`, own venv (uv, Python 3.11), throwaway Postgres 17 container `dgate-wp81` on 55481 (database `dgate`
for the suites, `perf` for section 4), TZ=UTC, web mock env of `web.yml`, Playwright 4 workers:

| Check | Result |
|---|---|
| ruff | All checks passed |
| unit (`pytest`) | 3261 passed, 1208 deselected (incl. new `test_wp81_values.py`) |
| integration (`pytest -m integration`) | **1208 passed**, 0 failed (10 min 53 s) |
| `tsc --noEmit` | exit 0 |
| `npm run check` | all ok, incl. new `wp81.check.ts`, `wp80`, `wp66`, `wp68` |
| `next build` (mock) | exit 0 |
| Playwright, 4 workers, desktop + 375 px | **523 passed, 47 skipped** (the fake-API group, as in WP-80), 0 failed, incl. new `wp81.spec.ts` (2 x 2) |

A first Playwright run failed every test at browser launch (the fresh `npm ci` had no browsers); the browsers were copied from the
WP-80 scratch copy (no download) and the run repeated. A first `npm run check` failed `wp65/68/73` because the scratch copy lacked
`backend/` and `docs/`; the run script now mirrors them.

## 7. Limits and open points

- **Twin pair where the PLACSP row stands for the award** (it states the winner's number, the TED row does not): the TED notice's value
  is not added and that procurement counts under "no value" (said in the contract). Taking the TED twin's value there, as the tender
  page does (`tenders._twin_values`), is a possible follow-up.
- A TED value stated without a currency is shown on its notice row but not summed (a sum needs a currency); it counts under "no value".
- Framework ceilings cannot be told from awarded amounts in the data; the block says so instead of separating them.
- The 30-name list of "who to approach" and the 10 per country stay (list lengths, not the mosaic rule); past them winners are counted
  as "not listed". Owner may want "show all" there: **open decision**.
- `withheld` (supplier list) and `below` (approach) stay in the answers, always false/empty, for compatibility.
- Budget: measured locally on synthetic data; production confirmation after deploy (section 4).
- Demo answer: regenerate from production after deploy (section 5).
