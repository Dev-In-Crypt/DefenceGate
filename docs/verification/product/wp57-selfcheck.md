# WP-57 self-check: suppliers and organisations (19 October 2026)

Branch `wp-wp57` (from `integration` d9f1d2b). Findings addressed: UX audit M6, M7, M8, M9 (`ux-audit-networks.md`). No wording of existing copy was
changed; the only new strings are the two empty-state/line texts quoted below. No migration, no production write, no model call.

## What was built

| # | Finding | Change | Where |
|---|---|---|---|
| 1 | M6 `?country=Germany` and `?country=DEU` were a 404 page | A country is read as a two-letter code, a three-letter code or an English name (case, accents and `&`/`and` ignored) and normalised to the alpha-2 code. API: `country` values go through `to_iso2`; a value that is none of the forms answers **422** `country: '<value>' is not a country; ...`. Web: the field keeps what was typed, the API is asked with the codes; an unknown part gives the empty state "Not a country" (no 404, never the unfiltered list, a good and a bad part together are not silently narrowed). A two-letter value is a code as written, so `ZZ` stays an empty group (existing test `test_a_country_or_product_group...` unchanged). | `backend/dgate/countries.py` (new), `backend/dgate/suppliers.py`, `web/lib/country-input.ts` (new), `web/app/(public)/suppliers/page.tsx`, `docs/design/API_CONTRACT.md` |
| 2 | M7 product words matched pieces of words | Title matching is by whole word (`isForm`: the word, `+s`, `+es`, `+ed`, `y`->`ies`), and the headword rule uses the first word of the title. "gun" no longer reads "Gunmetal pipe fittings" (35341100), "fuel" no longer reads the "nuclear/diesel fuelled" submarines (35512100-300). The curated map reads the **longest** phrase ("body armour" is not "body" + "armour"; "land mines" is not "mines"). Curated entries added (codes and titles are the finder's own): radar (35722000, 35723000; not the radar detectors), armour/armor (35410000 + 35815000, with a note), pistol/handgun (35321100), helmet (35813000), land mine, sea mine, mine (with a note); German "Drohne(n)" added to the drone entry. 9 -> 16 entries. | `web/lib/cpv.ts`, `web/lib/data/product-keywords.json` |
| 3 | M8 display casing of names | `displayName(name, 'title')` (the shared helper behind `nameOf`, buyers, cards, profiles) now: keeps the acronyms and legal forms of a list (`NAME_KNOWN`: CNRS, TNO, VTT, INRIA, EDF, CEA, DLR, AIT, GTS, ... SAS, SARL, SRO, DOO, UAB, GmbH, ApS, Kft, mbH, ...) in their form wherever they stand and in whatever case the source used; writes the ambiguous forms (AS, AB, SA, AG, KG, SL, OY, SpA, OÜ, e.V.) as forms **only as the last word** ("As Good As Gold Ltd" keeps its words); gives a name with no capital at all name case ("ministere des armees" -> "Ministere des Armees", "inria" -> "INRIA"), unless a letter would change on the way (Turkish dotless i). Only the case of letters changes, never the letters; the stored name is untouched; titles (kind `sentence`) are unchanged. Supplier list, supplier profile (heading, title, breadcrumb, captions) and the withheld-name span of `OrgLink` now use the helper too. Name-variant strings ("Also published as", "Name variants") stay raw on purpose: they show what the sources wrote. | `web/lib/display-name.ts`, `web/components/networks/parts.tsx`, `web/app/(public)/suppliers/**` |
| 4 | M9 project without coordinator | The line under the facts reads "Coordinator not stated." when the API returns no coordinator (it stays "Coordinated by ..." otherwise). | `web/app/(public)/projects/[slug]/page.tsx`, demo project `299-delta` in `web/lib/mock/networks.ts` (outside `PROJECTS`, no count changes) |

No organisation is merged or renamed by any of this.

## Measured on production data (read-only SQL, `statement_timeout` 30 s, 19 October 2026)

**Names.** The 1,689 organisations of the default directory (`organisation_network.defence_projects > 0`) through the old and the new helper:

| Display | before | after |
|---|---|---|
| ending ` Sas` | 41 | 0 |
| ending ` As` | 39 | 0 |
| ending ` Ou` / ` Ev` / ` Srl` | 8 / 3 / 2 | 0 / 0 / 0 |
| `Cnrs`, `Tno`, `Vtt`, `Ait` | 1 each | 0 |
| `Gts` | 2 | 0 |
| names all lower case in the source that still start lower case | 36 | 0 |
| names whose display changed | | 280 of 1,689 |

The before counts equal the audit's (41, 39, 8, 3, 36): the audit's numbers are reproduced and removed. Samples of the change: `Nammo Raufoss As -> AS`, `Alcatel Submarine Networks Sas -> SAS`, `Talgen Cybersecurity Ou -> OÜ`, `Deutsches Zentrum Fur Luft - Und Raumfahrt Ev -> Deutsches Zentrum fur Luft - Und Raumfahrt e.V.`, `inria -> INRIA`, `Isd Aerospace Limited -> ISD ...`, `Thyssenkurpp marine Systems GMBH -> ... GmbH`.

Not changed (stated limits): a mixed-case name with a shouted word ("MEYER WERFT GmbH") stays as the source wrote it, because a rule that lowers 5-letter capitals would also lower acronyms (PIDSO, INEGI); the source's own misspellings ("Thyssenkurpp", "Defenceof") are data, not display; "Aalborg University" (lower case) and "Aalborg Universitet" remain two rows (no merging, as the brief says).

**Sample of 220 names** (`web/lib/fixtures/org-names-sample.json`, chosen by `md5(name)` from `organisation_network`, 141 capitals / 39 lower case / 40 mixed; legal entities only; I read the list: some company names carry a founder's name, as legal entities do, and no name is a natural person on its face): 181 change in display; for all 220 the letters are identical after removing case and accents, a second pass changes nothing (except an all-capitals result such as `NHP SRL`, which reads as shouting again, as every all-capitals string always did), no name ends in a wrong-case legal form, and every lower-case name starts with a capital.

**Projects without a coordinator.** 7,432 of 80,491 projects (9.2%) have no active participation with role `coordinator`: H2020 2,092 of 37,137; FP7 1,494 of 23,914; Horizon Europe 2,896 of 18,211; EDF 4 of 283; 946 projects with no programme (all with no member at all). 3,382 of the 7,432 have no active member either. Project 55762 (RAMSSES) has 21 active members, roles `participant` and `third_party` only, so it is a data fact and the page now says so. The audit's "every other project has exactly one coordinator" holds for 90.8% of the projects, not all: the page statement is now correct for the other 9.2% too. (The API's `coordinator` is the first member with role `coordinator`; nothing was inferred.)

**Product words.** 64 words against the 366-code finder, whole word versus substring. The vocabulary holds these pieces-of-words that a substring rule can offer (listed by script): `gun` in 35341100 Gunmetal pipe fittings; `fuel` in the three "fuelled" submarines 35512100-35512300; `tank` in 35513400 "...tanker; ro-ro vessel" and 35611700 Tanker aircrafts; `bomb` in 35611200 Fighter-bomber and 35611300 Bomber aircrafts; `ship`/`ships` in the seven "warships" codes; `engine` in 71000000 and 71300000 (engineering); `air` in 22 codes (aircraft, repair). None of them is offered any more (the test fails on any of them). Results for 40 of the words now (via, prefixes): gun title 35312, 353211, 353213; fuel title 09; ammunition title 3533; armour keyword 3541, 35815; radar keyword 35722, 35723; drone keyword 35613, 347112; explosive keyword 246; tank keyword 35411; missile title 3562; rifle title 353212; bomb title 353331; rocket title 353332; torpedo title 353321; grenade title 353313; mortar title 353224; artillery title 35322; firearm title 3532; mine keyword 35513, 353314, 353322; helmet keyword 35813; pistol keyword 353211; truck, boots, sonar, parachute, shotgun, sniper: no code (the finder holds none, and no filter is made up). The page still prints the codes it used.

## Tests added (all fail without the change)

* `backend/tests/unit/test_countries.py`: 27 positive and 10 negative cases (codes, ISO3, names, `UK`, accents, `&`, garbage, injection-shaped text) and every ISO3 of the TED table.
* `backend/tests/integration/test_wp57.py`: `Germany`/`germany`/`DEU`/`deu`/`de`/`Deutschland`/`Germany,DEU` list exactly what `DE` lists; the k rule holds under a name (Estonia withheld); `Atlantis`, `Germ`, `XYZ`, `DE,Atlantis` answer 422 with the message; `ZZ` still 200.
* `web/lib/wp57.check.ts` (run by `npm run check`): country forms (30 positive, 9 negative, lists); `isForm`; gun/fuel/bomb/pistol/radar/helmet/armour/mine cases; 64 defence words against the whole vocabulary (no code offered for a piece of a word, no made-up filter); 42 name cases (the audit's examples in capitals and in the source's mixed case, all-lower names, words that must stay: "As Good As Gold Ltd", "MEYER WERFT GmbH", "iXblue", CJK, Turkish, Cyrillic) and the 220-name sample properties.
* `web/e2e/wp57.spec.ts` (desktop + 375 px): Germany/germany/DEU/Deutschland give the same heading as DE and keep the typed value in the field; Atlantis and `DE,Atlantis` give "Not a country"; gun/fuel/radar status text; `Bravo Ingénierie SAS` in the directory; `Coordinator not stated.` on `/projects/299-delta` and `Coordinated by` on `/projects/201-alpha`.

## Runs on the server (own dirs `/root/dev-w57`, `/root/dev-w57-web`, database `agent_wp57`; load and memory watched, runs waited for load < 8)

* Backend: `/root/run_w57.sh` (ruff, unit, integration): exit 0.
* Web: `tsc --noEmit` clean; `npm run check` all files ok (including the new `wp57.check`); `next build` ok.
* Playwright, `--workers=1`, desktop and 375 px, against `next build` + `next start` with the demo data (`DG_USE_MOCK=1`): `wp57`, `networks`, `suppliers`, `routes`, `layout`, `ux`, `wp36` specs: **167 passed, 0 failed** (the first run of `wp57`/`networks`/`suppliers` alone: 56 passed). The other specs were not run. They render buyer names, which pass through the same helper; the demo buyer names are in mixed case and hold none of the new forms, so no change is expected, but the helper is shared and the orchestrator's full Playwright run is the real check.

## Hostile review of my own diff

Found and fixed: (1) a variable name clash in `keywordMatch` (tsc); (2) the first idea for `UK`/`ZZ` handling turned `ZZ` into a 422 and would have broken an existing test, now two letters are a code as written; (3) Turkish dotless i and German sharp s would have changed letters when a lower-case name was upper-cased, now guarded; (4) `EPE` (a Dutch town as well as a Greek legal form) and `ELI` (a given name) removed from the acronym list; (5) a radar note that claimed what the CPV code 35121900 is; removed; (6) the first sample test expected `SH DEFENCE - SH Group A/S` to be left alone, but the old rules already lower-case it (two of four words in capitals): a pre-existing limit, left, test changed. 6 found, 6 fixed.

## Not met or not checked

* Mixed-case names with a shouted word (see above) are left as they are.
* "Aalborg University" / "Aalborg Universitet" and the 7 duplicate supplier groups (m37) are entity resolution, outside this package.
* The 404 page for `?page=26` (m41) and the label "Country code, for example DE" (n7) are not touched (wording).
* The API is not reachable on the public host for organisations and projects, so the project page was checked against the demo data only; the production figures above are from SQL.
* Names of countries: 130 are known by English name (Europe, NATO, major trading partners); a rare country is reachable by its code or three-letter code only.
