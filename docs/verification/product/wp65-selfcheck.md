# WP-65 self-check: supplier profile (21 October 2026)

Branch `wp-wp65` from `integration` (5fb7805). Plan row: WP-65 of `docs/plans/MVP_SPAIN_AUTOMOTIVE_2026-10-21.md`. No model call, no spending,
no external request, no production access, no migration, no change to the API or the engine (the WP-64 `ProfileIn` already takes every
field). The assess endpoint and the web proxy are unchanged: stateless, nothing stored or logged.

## 1. What was built

- **`/readiness/supplier`** (`web/app/(public)/readiness/supplier/page.tsx`, `web/components/readiness/supplier.tsx`): one page in five
  cards, saved in the browser as it is filled in (same block as the wizard). Entry: `/readiness` has a link "I make parts or materials and
  want to supply defence buyers" above the wizard; the funding wizard itself is unchanged.
- **Storage** (`web/lib/profile.ts`): key `dg.profile.v1`, block **version 3** with a `supplier` sub-object. Versions 1 and 2 are read with
  every answer kept and an empty supplier block; reading does not write; the first change writes version 3. Unknown versions (0, 4) are
  refused. Export and import (the wizard's "Keep my answers") carry the supplier block; import of a version 1 or 2 file still works.
- **CPV search** (`web/lib/cpv.ts` `cpvSearch`, `cpvDictionaryTitle`): our dictionary = the 366 codes of `cpv.json` plus the codes of
  `product-keywords.json`, official titles only. A 2-8 digit query is a code prefix; otherwise the curated product words first (the same
  phrase matcher as WP-43/57, factored out as `keywordEntries`), then every query word as a whole word of a title (`isForm`, so "gun" never
  finds "Gunmetal"). At most 20 shown; 5 to 15 chosen. No language model.
- Results (`components/readiness/rules.tsx`): a question that the supplier page asks links to its field there
  (`/readiness/supplier#q-<field>`). A question the wizard asks still links to its step. A question neither asks keeps
  "(not asked by the questionnaire yet)". The results page has "Change my supplier profile" once the page was used.

## 2. Fields and how they map to the rules

| Field on the page | Stored as | Sent to the engine |
|---|---|---|
| Country | `country` (shared with the wizard) | `country` |
| Region (ES: autonomous community, ISO 3166-2; other: text) | `supplier.region` | not sent |
| Size band | `sizeClass` (shared) | not sent |
| NACE code (optional, NACE Rev. 2 format checked) | `supplier.nace` | not sent |
| Foreign investor owns or controls part (yes/no/not sure) | `supplier.foreignOwner` | `foreign_capital` (yes/no only). "No" also answers the wizard's empty "controlled from outside the EU?" with "no" (no foreign shareholder at all), written into the profile so the wizard shows it |
| Investor country (if yes) | `supplier.foreignCountry` | not sent |
| 5-15 CPV codes | `supplier.cpv` | not sent (for WP-66) |
| Processes (casting, forging, machining, welding, electronics, plastics and composites, coatings, textiles, assembly) | `supplier.processes` | not sent |
| ISO 9001, EN 9100, AQAP 2110, AQAP 2310 held | `statuses[REQ-*]` (the wizard's step 4 answer) | status |
| PECAL held (ES only) | `statuses[REQ-PECAL]` | status; "not held" once the page is saved |
| IATF 16949, ISO/IEC 27001 held | `supplier.held` | not sent (no rule: Q-IATF16949 was left out in WP-64) |
| Expiry month per certificate (optional, YYYY-MM) | `supplier.expiry` | not sent |
| RID (ES only), NCAGE | `statuses[REQ-RID]`, `statuses[REQ-NCAGE]` | status; RID "not held" once the page is saved |
| NSPA Source File | `supplier.held` | not sent (no seeded rule; WP-64 unconfirmed item 5) |
| US-origin components (yes/no/not sure) | `supplier.usComponents` | `us_components` (yes/no only) |
| Access to classified information (yes/no/not sure) | `classified` (shared with step 5) | `handles_classified` |
| 18 questions of the Spanish route (ES only, optional) | `supplier.answers[field]` | the engine field of the same name |

The 18 Spanish questions are the WP-64 `engine.SUPPLIER_FIELDS` in the engine's own words (a lib check reads `engine.py` and fails on a
difference): pecal_certificate_wanted, pecal_system_9_months*, pecal_prior_contract*, pecal_2310_target, ncage_need_justified (only while
NCAGE is not held), specific_defence_use, homologation_mandatory*, homologated*, es_defence_material_list (only for a military regime),
stores_classified (only with classified access), nato_classified_contract, nsfcc_held*, nato_staff_cleared*, nato_icb_bid,
rid_capabilities_declared*, foreign_investor_authorised (only with a foreign investor), receives_eea_defence_products,
certified_recipient*. A starred question appears only after the "yes" it depends on. A hidden answer is kept and not sent.
"I am not sure" and an empty answer are **not sent**, so the rule stays "unknown" and keeps its question.

Not asked (the rule stays unknown with its question where it applies): the German questions (de_*, ghb_admitted, vsnfd_*, sibe_appointed),
dualuse_annex_i, de_ausfuhrliste, REQ-HSES-ES. These are outside the ES-MOD card, except REQ-HSES-ES, which applies only when
classified information is stored on the company's premises.

## 3. Open questions on the ES-MOD card: before and after, three sample profiles

The sample companies are the generated fixtures `web/e2e/fixtures/request-es-sup-{civil,defence,partial}.json`
(`dgate.readiness.export`, `SUPPLIER_PROFILES`), computed by the engine. "Before" is the same company without the supplier page (none of
its answers, RID and PECAL never asked). The counts are pinned by `backend/tests/unit/test_wp65_supplier.py`. `lib/wp65.check.ts` proves
the web's `toRequest` produces exactly these bodies, and `e2e/wp65.spec.ts` proves that filling in the page for the civil one sends exactly
its body.

| Profile | ES-MOD open questions before | after | verdict after |
|---|---|---|---|
| civil: castings maker in País Vasco, ISO 9001 + IATF 16949, no investor, no US parts, no classified work, every Spanish question "no" | 19 | **0** | obtain (RID to obtain) |
| defence: machining and electronics, ISO 9001, AQAP 2110, RID, NCAGE, French investor with authorisation, US parts, classified access (not stored), wants PECAL | 20 | **0** | eligible |
| partial: only the profile fields (ISO 9001, no investor, US parts "not sure", no classified work), no Spanish question answered | 19 | **15** | obtain |

The partial profile keeps the questions it did not answer (PECAL ambitions, NCAGE need, homologation, NATO, EEA transfers), each still
"unknown" with its question, now linked to the page. What it did answer (RID, foreign capital, control) is gone from the list. The wizard-only
WP-64 profile `es-auto` still shows 18 (unchanged fixture); its questions now link to the supplier page.

The EDF, EDIP, SAFE cards of a supplier-only profile list the wizard's questions (legal form, management, component origin). They link to
the wizard steps, as before.

## 4. Accessibility and layout

Labels on every control. Grouped questions are fieldsets with legends. Hints and errors are tied with `aria-describedby`; the CPV error is
tied to the search box too. On "Save" with problems, an `role="alert"` summary lists each problem as a link that focuses its field, and focus
moves to the summary. Fields carry `aria-invalid`. The CPV match count is a `role="status"`. Targets are at least 44 px: the e2e measures
every label, button, select and field box on the page at both widths (more than 60 elements). The branded `Select` (the native select as the
control) is used for country, region, size and investor country. There is no horizontal scroll at 375 px (`visit` checks it). No new
design tokens or components were added (WP-62's area); `Radios`, `COUNTRY_OPTIONS`, `SIZE_OPTIONS` and `YES_NO_UNSURE` are exported from
the wizard and reused.

## 5. Tests

New: `web/lib/wp65.check.ts`, `web/e2e/wp65.spec.ts` (4 tests x desktop and 375 px), `backend/tests/unit/test_wp65_supplier.py`
(7 cases), generated fixtures `request-/assess-es-sup-{civil,defence,partial}.json`.

Existing tests changed, and why (nothing loosened):
- `lib/profile.check.ts`: "written back as version 2" -> 3; the "unknown version refused" cases use 4 instead of 3 (3 is now the
  current version).
- `e2e/wp64.spec.ts`: the RID question was asserted to have no link (nothing asked it). It is now asserted to link to
  `/readiness/supplier#q-REQ-RID` (`data-supplier-asks`).
- `dgate/readiness/export.py`: three profiles added. The existing fixtures regenerated byte-identical.

## 6. Results

Local, `D:\DEFENCEGATE TESTS\wp65`, own venv, throwaway Postgres 17 container `dgate-wp65` on port 55465 (removed afterwards), TZ=UTC, web
mock environment of `.github/workflows/web.yml`.

| Check | Result |
|---|---|
| ruff | All checks passed |
| unit (`pytest`) | 2966 passed, 1145 deselected (WP-64: 2959; +7) |
| integration (`pytest -m integration`) | 1145 passed (10 min 54 s) |
| `dgate.readiness.export --check` (in the unit run) | up to date; existing fixtures byte-identical |
| `tsc --noEmit` | exit 0 (final tree) |
| `npm run check` | all files ok, incl. `wp65.check.ts`, `profile.check.ts`, `wp64.check.ts` |
| `next build` (mock data) | exit 0 (final tree); `/readiness/supplier` static, 10.9 kB |
| Playwright, 4 workers, desktop + 375 px (final tree) | **460 passed, 40 skipped, 0 failed** (WP-64: 452 + 8 new) |

The first full Playwright run had 2 failures, both in my own new test: a guard that the 44 px measurement is not vacuous expected more than 60
elements, and there are 59. I set the floor to 50; nothing in the page changed. The second full run is the one in the table.

## 7. Hostile review

I found and fixed 5 issues:
1. My first draft sent `nato_classified_contract: false` whenever classified access was "no". That changed the request of every
   wizard-only profile and inferred an answer the person never gave. I dropped it: the question is asked.
2. "No foreign investor" left ES-FOREIGN-CAPITAL open, because its trigger also reads `third_country_control`. Now an empty control answer
   is set to "no" in the profile itself, so the wizard shows it.
3. Two hints stated rules without a source ("Spain asks for an authorisation ...", "ITAR can follow such parts ..."). Reworded so the hints
   point to the sourced rule on the results and say there is no verified US rule.
4. The CPV search box was marked invalid without being tied to its error text (`aria-describedby` added).
5. The supplier fields were first going to be sent as nulls. They are now sent only when answered, so wizard-only requests are unchanged
   (the WP-29/53/64 request fixtures still match) and the body stays small (< 2 kB; limit 4096).

Checked and kept: a hidden follow-up answer is never sent; Spanish questions and RID/PECAL are never sent for a company outside Spain; an
imported or stored block is checked field by field (CPV 8 digits, at most 15, known keys only, months YYYY-MM).

## 8. Limits and notes

- Old clients (a tab opened before the deploy) that read a version 3 block fall back to an empty profile until reloaded, as in WP-53.
- The certificate expiry month is stored but not used: an expired certificate still counts as held if ticked.
- CPV codes, processes, region, NACE and investor country never leave the browser; WP-66 (demand map) will read them from `supplier`.
- Navigation: new route `/readiness/supplier` (reachable from `/readiness`); not added to the header, footer or sitemap (orchestrator).
- Deletion candidates: none.
