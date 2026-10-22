# WP-68 self-check: entry page "Spain automotive" and the supplier profile gaps (22 October 2026)

Branch `wp-wp68` from `integration` (f606b51). Plan row: WP-68 of `docs/plans/MVP_SPAIN_AUTOMOTIVE_2026-10-21.md`. No model call, no
spending, no deploy, no push, no migration, no change to the engine, the seed or the API. Production was used once, read-only: one
`POST /v1/readiness/demand` (stateless, stores nothing) from inside `dgate-api-1` for the sample codes, to check what the entry page will
show (section 3). Not touched: WP-76 (organisation merges) and WP-78 (eligibility-facts extraction) files.

## 1. What was built

| Part | Files |
|---|---|
| Entry page `/readiness/spain-automotive` (static, revalidated hourly) | `web/app/(public)/readiness/spain-automotive/page.tsx` |
| Live sample of the demand map (server side, POST to the API, hourly) | `web/lib/readiness-api.ts` `getDemandSample`, `web/lib/demand.ts` `SAMPLE_CPV`, `isDemand` |
| Navigation: Readiness menu (header and footer, same label and address), link on `/readiness`, sitemap | `components/dg/header-bar.tsx`, `components/dg/footer.tsx`, `app/(public)/readiness/page.tsx`, `app/sitemap.ts` |
| German questions, dual-use question, export block, export authorisation | `web/lib/profile.ts` (`DE_QUESTIONS`, `DUAL_USE_QUESTION`, `EXPORT_HOLDING`, `Answer`), `components/readiness/supplier.tsx` |
| Step 5's export options shared with the supplier page | `components/readiness/wizard.tsx` (`EXPORT_OPTIONS`, same words) |
| Report lists the new answers and the export answer | `components/readiness/report.tsx` |
| Fix: radio questions had no id, so every results link `/readiness/supplier#q-<field>` (WP-65/73) led nowhere | `components/dg/form.tsx` (`Fieldset` renders its `id`) |
| Sample German supplier (generated request and answer) | `backend/dgate/readiness/export.py` (`de-sup`), `web/e2e/fixtures/{request,assess}-de-sup.json` |

The header and footer were edited (the task asked for the menu entry); the groups stay identical (the WP-56 test C5 passes).

## 2. Acceptance criteria

| Criterion | Met | Evidence |
|---|---|---|
| Entry page: who it is for, what they get, what it is not, a clear start button | yes | `e2e/wp68.spec.ts` test 1 (headings, bullets, both "not" statements, the button leads to `/readiness/supplier`) |
| "What they get in 15 minutes" | **not as worded** | The page says "The profile is one page." No time is stated: nobody has timed it, and the brief forbids unmeasured claims. If the owner times a few users, the figure can be added |
| Readiness check against Spanish MoD, NATO and EU rules with sources; roadmap; demand map ES/DE/FR/PL/NL; printable report | yes | page copy, each item matches what WP-64..67 built (roadmap prints cost/time only from primary sources; demand map names winners only from 3 awards) |
| Not legal advice, no guarantee of contracts, no primes' sub-tier needs | yes | "What it is not" section and the callout "Indicative, sources linked, not legal advice" (the plan's disclaimer) |
| Sample numbers only if pulled live | yes | `getDemandSample` returns null without `DG_API_URL` and on any failure or malformed body (`isDemand`, `wp68.check.ts`); the demo build shows no figure (`e2e` asserts `[data-demand-sample]` absent); the live answer is section 3 |
| Metadata / OG, sitemap, link from /readiness and the Readiness menu, header = footer | yes | e2e tests 1 and 2 (title <= 60, description 50..160, canonical, `og:url`, `og:title`, robots index; sitemap `<loc>`; footer and desktop header link); WP-56 C5 green |
| Short Spanish summary, strictly facts | yes | `lang="es"` block, a translation of the English facts on the page plus "La herramienta está en inglés" |
| German questions (Geheimschutzbetreuung need, VS-NfD, Ü1-Ü3) only for DE companies or when targeting German buyers | **partly, by design** | Asked only of a company established in Germany (`country` DE). Every German rule applies only when `country` is DE, so for a company elsewhere "targets German buyers" would change no outcome; the profile has no target-country field either. Ü1-Ü3 (DE-SUE) is an information rule that reads no answer of its own: nothing to ask; the German block says the results show it once classified access is "Yes" |
| Dual-use question (Annex I of Reg. 2021/821), "not sure" -> consultant flag | yes | `DUAL_USE_QUESTION`; "not sure" gives EU-DUALUSE-EXPERT `conditional` and its consultant flag (`test_wp68_questions.py`, e2e test 3 checks `[data-consultant-flag="EU-DUALUSE-EXPERT"]`) |
| HSES for Spanish companies with classified work | already present | WP-73 (`ES_CLEARANCES`, REQ-HSES-ES when information is stored on the premises); unchanged |
| Outcomes change from "unknown with question" to met / not met / check | yes | table below; `test_wp68_questions.py` (5 tests) |
| Versioned storage stays compatible | yes | still version 3, no new top-level key; new answers live in `supplier.answers`, each read only from its own choices (`wp68.check.ts`); older blocks read as before (`wp65.check.ts`, `profile.check.ts` unchanged and green) |

### The German and dual-use rules for the sample German supplier (`de-sup`)

A German supplier, supplier page only, classified work (VS-VERTRAULICH and VS-NfD), exports outside the EU, not sure about either
export list, no export authorisation. "Before" = the same body without the page's German and dual-use answers and with the export
authorisation unknown (the WP-65 page could not ask them).

| Rule | before | after | why |
|---|---|---|---|
| DE-GHB-ADMISSION | unknown | **conditional** | VS-VERTRAULICH, not yet under the Geheimschutzbetreuung: only the VS-Auftraggeber can apply |
| DE-GHB-COST | unknown | info | applies now (no fee) |
| DE-SIBE | unknown | **met** | security officer appointed |
| DE-VSNFD | unknown | **not_met** | declaration signed, the contract does not incorporate the Merkblatt |
| DE-EXPORT-BAFA | unknown | **conditional** + specialist | not sure about Ausfuhrliste Part I |
| EU-DUALUSE-EXPERT | unknown | **conditional** + specialist | not sure about Annex I |
| open questions of the general block | 9 (the 8 fields and REQ-EXPORT, as `missing`) | **0** | |

Also tested: "no"/"neither" make all six `not_applicable` and drop both specialist flags; admitted + Merkblatt + Section B + licence held
give met; the same answers for a Spanish company leave every German rule `not_applicable` while the dual-use check still applies.

To decide the two export rules the page also had to ask the **export answer** (step 5's question, the same stored answer) and, once an item
is or may be listed, **"Do you hold an export authorisation for this item (dual-use or military)?"** (the wizard's step 4 status
REQ-EXPORT; "I am not sure" leaves it unknown, as the clearances do). Without them both rules stay "unknown" whatever the classification
answer.

When each question is shown (hidden answers are kept and not sent, as in WP-65):
- German security questions: country DE and classified access "Yes"; GHB and SiBe after VS-VERTRAULICH "Yes"; declaration and Merkblatt
  after VS-NfD "Yes".
- Ausfuhrliste: country DE and the export answer is not "No".
- Dual-use: product regime not "military" or "neither" (step 3), and the export answer not "No" or "to other EU countries" (the rule
  reads only exports outside the EU, or "not sure").
- Export authorisation: dual-use "yes"/"not sure", or (DE) Ausfuhrliste Section A/B/"not sure".

Results links: German questions go to `#sp-germany`, the dual-use and Ausfuhrliste questions to `#sp-export`; REQ-EXPORT stays linked to
step 4 (where every company is asked).

## 3. The live sample (production, 22 October 2026, read-only)

One call of `POST /v1/readiness/demand` from inside `dgate-api-1` with the sample codes (34300000, 34100000, 35421000, 42600000, 44300000)
and the five countries: 2023-10-22 to 2026-10-22, 4,311 procurements, 160 core / 183 other buyers, 178 under 2009/81; ES 1,515 (33),
DE 306 (39), FR 87 (37), PL 2,313 (50), NL 90 (19); per code 1,725 / 1,308 / 110 / 474 / 836. These equal the WP-66 self-check's table
for the same profile. The page shows these counts (procurements, buyers core/other, the 2009/81 share, per code and per country) and the
API's coverage line; it shows no winners and no names. Not checked: the page rendered against the live API (the local build has no API;
after deploy, open `/readiness/spain-automotive` and compare with the numbers above).

## 4. Every new copy string

Entry page (`/readiness/spain-automotive`):
- Title: "Spain automotive suppliers: defence readiness"
- Description: "For civilian manufacturers in Spain, such as automotive suppliers: the Spanish MoD, NATO and EU rules with their sources, and who buys your CPV codes."
- Crumb and menu label: "Spain automotive"
- H1: "Supplier readiness: Spain automotive"
- Lead: "For civilian manufacturers in Spain, such as automotive component suppliers, that are considering supplying defence buyers. You fill in one supplier profile; the check reads it against the published rules and shows every source."
- Buttons: "Start the supplier profile" (twice), "The readiness check for EU funding"
- Callout "Indicative, sources linked, not legal advice": "Each result names the rule it comes from, quotes its source and links to it, with the date the rule was last reviewed. Read the source before you act on a result."
- "Who it is for": "Manufacturers established in Spain that make civilian products today, such as automotive components, castings, machined parts or electronics, and want to supply defence buyers: the Ministry of Defence, the NATO Support and Procurement Agency (NSPA), and the prime contractors that build for them. A company established elsewhere can use the profile too; the Spanish rules then do not apply to it."
- "What you get":
  - "A readiness check. Your answers against the rules of the Spanish Ministry of Defence supplier route, NATO supply and the EU defence programmes. Each rule shows its outcome, the reason, and the text of its source with a link."
  - "A roadmap. What you already hold, what you need now on your answers, and what usually comes with a first contract, such as the PECAL quality certificate, with each prerequisite first. A cost or a time is printed only where a primary source states it."
  - "A demand map. Who bought under the CPV codes you choose in defence-scope notices of Spain, Germany, France, Poland and the Netherlands over the last three years: the buyers (core defence buyers and others), how many procurements, how many under Directive 2009/81/EC, and who won where a winner is published (a company is named only from three awards up; the others are counted)."
  - "A printable report of all three, which you can print or save as a PDF."
  - "The profile is one page. Where an answer needs a classification or a legal reading (export control, US-origin components, a foreign investor, a security clearance), the result says so and that a specialist is needed; it gives no answer of its own."
- "What it is not":
  - "It is not legal advice and does not replace the tender documents: each buyer sets its own conditions there."
  - "It does not find contracts or guarantee one. Meeting these requirements does not win a contract."
  - "It does not show what prime contractors need from their suppliers: those needs are not published in the sources we read. The demand map shows who buys directly and who won, not what primes need."
  - "It does not ask about the technical detail of any product, and never will." (as on `/readiness`)
- "Live from the demand map" (only with a live answer; numbers and dates from the API): "Five CPV codes an automotive parts maker might choose, counted by the demand map on {until} for the three years from {since}:", per code "{code} {official title}: {n} procurements", "In the five countries together: {n} procurements by {buyerLine}; under Directive 2009/81/EC: {share}.", per country "{Country}: {n} procurements by {buyerLine}; under Directive 2009/81/EC: {share}.", the API's coverage line, "Your own map is computed from the codes you choose on the supplier profile, and is part of your report."
- Callout "Your answers stay in this browser": "There is no account and no copy on our server. Two requests leave your browser: the one that computes the verdict, with the answers the rules read, and the one for the demand map, with your CPV codes and nothing else. The server does not store or log them."
- "Resumen en español": "Para fabricantes civiles establecidos en España, por ejemplo proveedores de componentes de automoción, que estudian suministrar a compradores de defensa. El perfil de proveedor contrasta sus respuestas con las reglas de la ruta de proveedor del Ministerio de Defensa, del suministro OTAN y de los programas de defensa de la UE, cada una con su fuente; ordena lo que falta; muestra quién compra sus códigos CPV en España, Alemania, Francia, Polonia y los Países Bajos; y genera un informe imprimible. Es orientativo, no es asesoramiento jurídico y no garantiza ningún contrato. La herramienta está en inglés."

`/readiness`: link "A civilian manufacturer in Spain, such as an automotive supplier: what the check gives you".

Supplier page:
- Block "Exports and export control"; export question "Do you export, or plan to export, your product?" (step 5's words and options) with hint "The same answer as step 5 of the readiness check. The export rules read it."
- Dual-use question (engine's words) "Is your item listed in Annex I of Regulation (EU) 2021/821 (dual-use items)?", hint "The EU rule on dual-use exports reads this answer when you export, or may export, outside the EU. If you are not sure, your results say that a classification settles it and that a specialist is needed; this check does not classify items."; when hidden: "The question on the EU dual-use list (Annex I of Regulation (EU) 2021/821) is asked when you export, or may export, outside the EU, unless you said in step 3 of the readiness check that your main product is military or in neither regime."
- Ausfuhrliste (engine's words) with choices "Yes, Part I Section A (arms)", "Yes, Part I Section B (national dual-use list)", "Neither", "I am not sure"; hint "The German rule on BAFA licences reads this answer. If you are not sure, your results say that a classification settles it."
- "Do you hold an export authorisation for this item (dual-use or military)?", hint "The same answer as step 4 of the readiness check. If you are not sure, your results keep the question open."
- Block "Questions of the German rules on classified contracts (optional)": "The German rules on the Geheimschutzbetreuung, the security officer and VS-NfD material read these answers; they apply to companies established in Germany. Leave a question empty, or answer “I am not sure”, and the rule stays open with its question on your results. The personnel security checks (Ü1 to Ü3) need no answer here: your results show that rule, with its source, once you say you need access to classified information."; before classified "Yes": "These questions appear once you answer “Yes” to access to classified information above."
- The six German questions in the engine's words (`engine.SUPPLIER_FIELDS`; `wp68.check.ts` fails on a difference): de_vs_vertraulich, ghb_admitted, sibe_appointed, de_vs_nfd, vsnfd_declaration_signed, vsnfd_merkblatt.

Report: row "Exports" (step 5's option words, or "Not answered"); answered German and dual-use questions with their choice's words.

## 5. Tests

New: `web/lib/wp68.check.ts`, `web/e2e/wp68.spec.ts` (4 tests x desktop and 375 px), `backend/tests/unit/test_wp68_questions.py` (5),
fixture `de-sup` (generated). Changed, and why (nothing loosened):
- `lib/wp65.check.ts`: asserted that the page does not ask `de_vs_nfd` and `dualuse_annex_i`; it now does (asserted in `wp68.check.ts`).
  The PIC and legal-form negatives stay.
- `lib/wp73.check.ts`: `askedAt('de_vs_nfd')` was null; now `#sp-germany`. The "no page asks it" case stays, with a field nothing asks.
- `dgate/readiness/export.py`: one profile added; every existing fixture regenerated byte-identical.

## 6. Results and hostile review

Local, `D:\DEFENCEGATE TESTS\wp68`, own venv (uv), throwaway Postgres 17 container `dgate-wp68` on 55468, TZ=UTC, web mock env of
`.github/workflows/web.yml`. Final tree:

| Check | Result |
|---|---|
| ruff | All checks passed |
| unit (`pytest`) | 3080 passed, 1191 deselected (+5 new, +2 parametrised cases for `de-sup`) |
| integration (`-m integration`) | 1191 passed (9 min 36 s) |
| `dgate.readiness.export --check` (in the unit run) | up to date; existing fixtures byte-identical |
| `tsc --noEmit` | exit 0 |
| `npm run check` | 36 checks ok, incl. `wp68.check.ts`, `wp65`, `wp73` |
| `next build` (mock) | exit 0; `/readiness/spain-automotive` static, revalidate 1 h (the known Windows-only standalone trace warning) |
| Playwright, 4 workers, desktop + 375 px | **509 passed, 47 skipped (the fake-API group, as before), 0 failed** |

The first full run had 4 failures, all in my new spec: a Callout title is not a heading (locator changed to the `complementary` landmark), and
the question anchors did not exist, which uncovered the dead-link bug fixed in `Fieldset`.

Hostile review, found and fixed 5: (1) the two export rules stayed "unknown" with only the classification answered, so the export answer
and the export authorisation are asked too; (2) the dual-use question was first shown for exports within the EU, where its rule never
applies; (3) results links to radio questions were dead anchors (`Fieldset` without `id`, pre-existing since WP-65); (4) the stored
`answers` would have accepted "yes" for the Ausfuhrliste and "part_i_a" for the dual-use question (each now only its own choices);
(5) the entry copy first said "defence buyers" for the demand map, which counts all defence-scope buyers (now "core defence buyers and
others"). Checked and kept: German answers never sent for a company outside Germany; no German question asked for Ü1-Ü3; the demo build
shows no figure.

## 7. Limits and open points

- No time claim ("15 minutes"); see section 2.
- German questions only for German companies (the rules' own scope); a profile field "target countries" does not exist and was not added.
- The live sample is fetched at most hourly by the site's server; if the API fails at that moment the block is absent until the next
  regeneration. Rate limit: one call (cost 5) per regeneration, from the site's own address.
- `Fieldset` now renders its `id`: the WP-65/73 links to radio questions (`#q-foreign_capital`, `#q-REQ-FSC-ES`, ...) were dead anchors
  before; no page had two fieldsets with one id (checked by grep).
- Navigation added (header and footer "Readiness" group: "Spain automotive", after "Supplier profile"). Deletion candidates: none.
- Scratch: `D:\DEFENCEGATE TESTS\wp68` (kept, as the earlier packages), container `dgate-wp68` (removed at the end), scratchpad scripts.
- Production commands: none (no migration, no seed change). After deploy: open `/readiness/spain-automotive` and compare with section 3.
