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
| Placeholder (<= 1), the procedure's estimate (`estimated`), a PLACSP call's own estimate (`opportunity.value_amount`, no kind) add nothing; PLACSP counts through its awarded amount (section 3b) | `test_a_placeholder_an_estimate_and_a_national_value_are_no_value`, profile test (73-2026, 74-2026) |
| TED+PLACSP twins once, from whichever copy has a value (PLACSP awarded amount first, else TED), never both | approach: `test_a_twin_pair_is_valued_once` (TED 5,000, then the PLACSP twin's 4,200 preferred, switch off: TED); profile: `test_one_award_in_ted_and_placsp_...` (250,000), `test_the_ted_record_stands_...` (TED row stands, PLACSP 250,000 preferred; without it TED 1,500), `test_a_placsp_row_standing_for_the_pair_takes_the_ted_value_when_it_states_none` (7,000) |
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

## 3b. Follow-ups of 22 October (coordinator: PLACSP values, the twin case, nothing hidden)

**What PLACSP stores.** `award` had no amount column. The PLACSP award results are parsed per result (in practice per lot) by
`sources/placsp.parse_results` into the landed payload (`placsp_awards/` in the raw store, since WP-60): `value` =
`AwardedTenderedProject/LegalMonetaryTotal/TaxExclusiveAmount` (awarded amount **without VAT**), `value_with_vat` = `PayableAmount`,
`currency` = its `currencyID`, and the result's winners. So the amount was in the raw payload, not in the table.

**Smallest change.** Migration `0100_award_value.sql`: `award.value_amount NUMERIC(18,2)`, `award.value_currency TEXT` (nullable,
additive). `placsp_awards.read` gives each winner the sum of the without-VAT amounts of the results that name it alone (a result with
several winners, a blanked person among them, is attributed to none; a placeholder is none; two currencies give none), and
`awards.store_notice` writes it on every PLACSP read (a re-read updates it). TED rows leave it empty. Tests:
`tests/unit/test_placsp_awards.py` (2,000 for two lots of 1,000 net, never the 1,210 with VAT; a shared lot, a lot with a person, a
zero amount, two currencies give none), `test_placsp_award_twins.py` (250,000 stored and served).

**Production backfill (not run; the owner's/orchestrator's step after deploy and `python -m dgate.migrate`):** the amounts of the
PLACSP awards already held come from the landed payloads, nothing is downloaded:

    python -m dgate.ops.placsp_archives --from-store          # dry run: runs it and rolls back, prints the counts
    python -m dgate.ops.placsp_archives --from-store --yes    # writes

(`replay_from_store` re-reads every landed payload with `force=True` and refreshes `award_twin_set`; it is the same command WP-60/61
used to load the winners.) Until it has run, PLACSP awards held before the deploy carry no amount and count under "no value".

**Which value an award has** (`suppliers.value_of`, one LATERAL used by the profile's notices and sums and by the demand answer):
candidates are the row itself and, with the PLACSP switch on, the current rows `award_twin_set` drops in its favour; first a PLACSP
awarded amount (kind `awarded`), else a TED value (`valued`: one winner, `total` or `lot_sum`); one value, never both. A PLACSP amount
is per lot, so it counts even when the folder names other winners for other lots. The block now says: "Summed per currency, never
converted; amounts without VAT where the source states both ... PLACSP values are the awarded amounts; TED values are as the notice
states them ... where TED and PLACSP both do, PLACSP's awarded amount, else TED's value".

**Nothing hidden behind the caps.** The caps stay (30 + primes in "who to approach", 10 per country). The supplier list was **not**
used as the target: it serves the map's core scope since 2023 by the supplier's country and the notice's main CPV, while the demand
answer counts defence-scope notices of the last three years by buyer country and every CPV code of a notice, deduplicated per
procurement; most automotive-code winners (listed-buyer notices, not core) have no supplier page, so the list would have shown a
different, smaller set under the same label. Instead: `POST /v1/readiness/winners` (same body + `page`; 100 per page; the same
statement, rules, 422 and price as the demand answer, stateless) lists every winner of the answer in the order and form of "who to
approach" (with its Contract values), and the page `/readiness/supplier/winners` (built in the browser from the stored profile,
`?country=ES` for one country, not indexed) shows it with Previous/Next. Links: "All N winners for these codes" under the report's
list (and on the results page's short list) when it stops before the end, and "All N winners in <country> for these codes" under each
country list that stops at ten. Tests: `test_every_winner_a_page_at_a_time_in_the_order_of_who_to_approach` (pages concatenate to the
approach order, same entries, `total` = `total.winners`, page 0 refused, one country), e2e `wp81.spec.ts` (the link, the country link,
pages of 20 in the demo build, only codes/countries/page sent). The results page's button "Every named winner in your supplier report"
became "Who to approach in your supplier report" (the report no longer holds every winner); `wp80.spec.ts` follows.

## 4. Budget (5 s API; the 30,000-notice cap of `/v1/readiness/demand` unchanged)

Measured locally only (no production access in this run), `D:\DEFENCEGATE TESTS\wp81\probe\perf.py`: a synthetic database at the cap
(30,000 matched TED notices, 5 countries, 8,000 winner organisations with a skewed distribution, about 6,750 winners in the answer, a
third of the notices without a value, a fifth lot sums, PLN and EUR, a quarter of the award rows with an awarded amount, 1,975 twin
pairs), five runs each, base = a49580d's `dgate`, new = this branch (final):

| Call | a49580d | wp-wp81 |
|---|---|---|
| `demand()` code 34300000, 5 countries | median 0.64 s (0.59-0.67) | median 0.79 s (0.75-0.83), +23 %: every winner enters `ap`/`apb`; values are a second statement for the listed winners only |
| `winners_page()` page 5 | (new) | median 0.72 s (0.70-0.77) |
| `get_supplier()` largest supplier (1,525 awards) | 0.105-0.111 s | 0.149-0.155 s (one more statement, the value LATERAL) |
| `supplier_summary()` | 0.031-0.034 s | 0.037-0.041 s |

A first version valued every winner's award rows inside the demand statement: 0.95 s median (+48 %); moved to a statement over the
listed winners' rows (`demand.VALUES`). Projection, not a measurement: WP-80 measured 1.1-1.9 s on production for 22,921 matched rows;
+23 % gives about 1.4-2.4 s at the cap, under 5 s. **To confirm after deploy** (read-only, by the orchestrator): the WP-80 probe of
section 4 of `wp80-selfcheck.md` with the branch's `demand.py`, and one `/v1/readiness/winners` page.

## 5. Demo answer (`web/lib/mock/demand.json`)

Not regenerated: it is production's answer and this run has no production access. Updated by hand, consistently, and only where the
data allows: each winner's `values` restored from production's own answer of 22 October 2026 that WP-80 removed them from (commit
a6c2bc3^, same winners, same rule then: TED value of a notice with this one winner, once per procurement), in the new shape
(`count` = the old `contracts`; `withoutValue` = contracts minus the valued ones; `shared` and `lotEstimates` were not in that answer
and are set to 0; PLACSP awarded amounts are not in it). Its `kMin` stays 3 and its winners stay those named under the old rule: names
of the winners with 1-2 awards cannot be made up. The copy reads `kMin` and says the old rule for this answer, so the demo build stays
truthful. The demo `/api/readiness/winners` pages through the 32 named winners of the snapshot (in pages of 20), so in the demo build
the link says "All 496 winners" and the page shows 32. **Open: regenerate it from production after deploy and the backfill** (then
`kMin` 1, `below` empty, values with PLACSP amounts; the lib checks and e2e read it generically).

## 6. Test runs

Local, `D:\DEFENCEGATE TESTS\wp81`, own venv (uv, Python 3.11), throwaway Postgres 17 container `dgate-wp81` on 55481 (database `dgate`
for the suites, `perf` for section 4), TZ=UTC, web mock env of `web.yml`, Playwright 4 workers. Final runs, after the follow-ups:

| Check | Result |
|---|---|
| ruff | All checks passed |
| unit (`pytest`) | **3264 passed**, 1211 deselected |
| integration (`pytest -m integration`) | **1211 passed**, 0 failed (8 min 51 s) |
| `tsc --noEmit` | exit 0 |
| `npm run check` | all ok, incl. new `wp81.check.ts`, `wp80`, `wp66`, `wp68` |
| `next build` (mock) | exit 0 |
| Playwright, 4 workers, desktop + 375 px | **525 passed, 47 skipped** (the fake-API group, as in WP-80), 0 failed, incl. `wp81.spec.ts` (3 x 2) |

The web suite ran on the final web code; the last backend change (values as a second statement, `value_totals` merging one currency
from two groups) came after it and was covered by the full unit and integration runs above (the web build does not run the backend).
Earlier: a Playwright run failed every test at browser launch (the fresh `npm ci` had no browsers; copied from the WP-80 scratch copy,
no download); a first `npm run check` failed `wp65/68/73` (the scratch copy lacked `backend/` and `docs/`; mirrored since). The
synthetic timing found a real bug: one currency in two groups (a PLACSP lot amount in a notice of several winners) gave two EUR lines;
`value_totals` now merges them (`test_one_currency_in_two_rows_is_one_sum`).

## 7. Limits and open points

- **Production backfill of PLACSP amounts** (section 3b): migration 0100, then `python -m dgate.ops.placsp_archives --from-store`
  (dry run) and `--yes`. Not run here.
- A TED value stated without a currency is shown nowhere in the sum (a sum needs a currency); it counts under "no value".
- Framework ceilings cannot be told from awarded amounts in TED; the block says so. PLACSP amounts are awarded amounts.
- `withheld` (supplier list) and `below` (approach) stay in the answers, always false/empty, for compatibility.
- The supplier map (`/suppliers`) and the demand answer keep different scopes (core since 2023 vs defence-scope, three years); the
  "All N winners" link goes to the demand answer's own full list, not to the supplier map (section 3b). Owner may want the two aligned:
  **open decision**.
- Budget: measured locally on synthetic data; production confirmation after deploy (section 4).
- Demo answer: regenerate from production after deploy and the backfill (section 5).
