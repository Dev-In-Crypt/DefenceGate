# WP-96 self-check: entities, counts, links (persona round of 23 October 2026, A2)

Branch `wp-wp96` from `integration` (c8bf4d4, WP-94 and WP-95 in). Input: `D:\DEFENCEGATE TESTS\ux-oct23\SUMMARY.md` section A2
(items 1-7) and the evidence of p03-de-machining, p04-pl-ammo, p06-nl-logistics, p07-it-analyst, p09-be-consultant and
p10-journalist (problems.csv, page dumps, screenshots). No deploy, no push, no production read or write, no portal called from
the laptop. Not touched: the WP-88 copy rules, the WP-95 value logic.

## 1. Supplier duplicates and company groups (A2.1)

`dgate/ops/supplier_dedupe.py` (new; report by default, `--yes` writes, `--undo-batch FROM TO`). Contract winners only (an
award row), both sides, one country. Rules and stored method / confidence (`db.merge_organisations`: absorbed row keeps
`merged_into`, method, confidence; an audit row in `organisation_merge_candidate`, `detected_by ops.supplier_dedupe`; undone
by the `ops.undo_merges` logic over the run's window):

| Rule | Example of the personas | Method, confidence |
|---|---|---|
| same company number once written alike (`supplier_identity.company_number`: the Swedish VAT is SE + organisation number + 01) and names agreeing | Saab AB 556036-0793 / SAAB Aktiebolag SE556036079301 | `company_number` 0.97 |
| Italy: two valid 11-digit numbers (codice fiscale / partita IVA, check digit tested) and one written name the notices give with each number | Leonardo 00401990585 / 00881841001 | `it_tax_pair` 0.90; without a shared written name: reported, never merged |
| same name key (legal-form words left at the end dropped: "aktiebolag", "co kg") | Thales Deutschland x2, Hensoldt Optronics, KNDS Deutschland GmbH & Co. KG | `name_key` 0.95 |
| same key without spaces, keys of 12 characters or more | Landsysteme / Land Systeme, RheinmetallMAN / Rheinmetall MAN | `name_key_spaces` 0.90 |
| a letter swap is merged only when the numbers agree | KNDS Cbrn / Crbn | `company_number` |

Left alone and reported: two numbers that cannot be one company's (`awards.numbers_conflict`, kind-aware: a VAT and a register
number are two kinds): Rheinmetall Electronics GmbH x3 holds DE119356818 and DE251121155 (persona screenshots 07-428360,
07-430165), so the three stay apart, reported as `different_company_numbers`; two legal-form classes (RENK AG / RENK GmbH);
public bodies (`buyer_family.is_public_body`), persons, removed rows.

Company groups (`dgate/ops/company_groups.py`, migration 0110 `company_group_member`): a curated list, each entry with the
parent, its source and the name patterns of the companies it covers (Rheinmetall: names beginning Rheinmetall; Leonardo:
the parent in Italy and named subsidiaries; Saab: the parent in Sweden and named subsidiaries; PGZ: Mesko, HSW, Jelcz,
Rosomak, Belma, ZM Tarnów, Łucznik, Niewiadów, Maskpol, PIT-RADWAR, Nitro-Chem, Dezamet, the WZ plants, Stocznia Wojenna). A
bare parent name only in its home country ("Leonardo S.L." in Spain is not taken). Method `curated_group`, confidence 0.90,
evidence = source + pattern. Display only, never merged. Served as `group` on `/v1/suppliers/{slug}` ("Part of the PGZ group",
source line) and `/v1/suppliers?group=` (the group view); a search for the group's name ("Polska Grupa Zbrojeniowa", "PGZ")
finds its members. The worker refreshes it with the buyer families (daily, idempotent).

## 2. Buyer families (A2.2)

`dgate/buyer_family.py` (display layer, `buyer_family_member`, nothing merged):

- `nl_defensie` (0.90): Ministerie van Defensie, Ministry of Defen[cs]e (any English variant), Defensie Materieel
  Organisatie / Defence Materiel Organisation / DMO, Commando DienstenCentra / CDC, DOSCO, CLAS / CZSK / CLSK, Koninklijke
  Marine / Landmacht / Luchtmacht, Logistiek Centrum Woensdrecht, MatlogCo: one family, NL only.
- `jae_male` (0.90): Jaemale / Jae Male / JAE MALE.
- `spelling_variant` (0.90): a dash read as a space, DE "Staatl." = "Staatliches", "Beschafffungsamt" = "Beschaffungsamt"
  (a real triple f, "Schifffahrt", is untouched), PL the State Treasury prefix and the seat of a numbered base or WOG
  ("Skarb Państwa – 1 Regionalna Baza Logistyczna w Wałczu" = "1 Regionalna Baza Logistyczna").
- `twin_notice` (0.85, `ops/buyer_families.twin_groups`): a buyer row no rule placed whose notices are national copies of TED
  notices (twin linked by an identifier: stated TED number, DOUE number, procedure id; not the heuristic) joins the family of
  the TED notices' buyer (Video Downlink Track Antenna: TenderNed 146554 and TED 146213 under one buyer). A head is never moved.

## 3. Buyer counts (A2.3)

The buyer aggregate (`tenders._core_where`, the list snapshot and the live open count), the buyer profile
(`stats._buyer_scope`) and the buyer page's own lists now use the tender list's default scope, `relevant` (All defence);
`buyers_with_page` follows. `/v1/buyers/{slug}` adds `openCoreCount` (the military goods and works among the open ones,
`scope=core`, the list's own count) and `scope`. The page: "Open now 27 / 5 of them military goods and works", and the line
under the facts names the scope. So NL MoD 5 vs 27, BE MoD 4 vs 17, BAIUDBw 0 vs open, BAAINBw 15 vs search: the buyer page
counts what the list shows for the buyer's family. Global search: when the words name at most three buyers, the Tenders part
leads with the first buyer's own open count, linked to its page ("BAAINBw: 15 open tenders"), before the title matches.

## 4. Supplier countries (A2.4)

Cause: `awards.read_award` took a winner's country from TED's parallel tenderer lists; a short or reordered list gave a winner
another tenderer's (or the only stated) country. Fix: `supplier_identity.stated_country_check` checks each winner's country
against its VAT prefix (DE119356818 is DE), a country its own name names (LEONARDO Germany GmbH, Saab Finland Oy, Rheinmetall
Canada Inc., KNDS Ammo France), and its legal form (a GmbH is not Spanish: the notice's other tenderer country that has the form,
else the form's usual country, Indra Avitech GmbH -> DE; an S.A. stated as Latvian goes to the Spanish co-tenderer, otherwise it
stays). Counted per notice (`country_corrected_<basis>`). "UK" is GB in `normalise._country2`.
Backfill: `python -m dgate.ops.supplier_countries` (report) / `--yes` (organisation and its award rows, each correction in
`organisation_country_fix` with old, new, basis; `--undo FROM TO`). A row whose number another body of the new country holds is
skipped and counted.

## 5. Links and codes (A2.5)

- e-Zamówienia: `sources.ezamowienia.NOTICE_URL` is `mo-client-board/bzp/notice-details/id/<objectId>`: the stored payloads
  carry `objectId` (fixture `ezamowienia_live_notices.json`), and the persona's dumps show the Atlas rows linking that same
  object id in this form (08de131b-…: one id, both forms; the old form PAGE_NOT_FOUND). The mapper uses the one constant.
- Bekanntmachungsservice: without BT-15 (documents link) the notice links its own page,
  `oeffentlichevergabe.de/ui/de/search/details?noticeId=<eForms notice UUID>` (`sources.de_bkms.notice_page`; legacy numeric
  ids get none). The address form is the service's UI, not checked against a fetched page (no portal called from the laptop):
  one constant to change if it differs.
- Codes in words (`web/lib/taxonomy.ts`): eForms procedure codes (neg-wo-call, comp-dial …) and the German national ones (De-open,
  De-comp-wo-call, De-neg-wo-call …), legal bases de-uvgo, de-vob, de-vgv, de-vsvgv, de-sektvo, de-konzvgv, any other `de-` code
  as "German national procurement rules (X)"; the raw code stays as "As stated".
- Backfill of stored links: `remap_source --epoch 96` for pl_ezam and de_bkms (new versions annotated `remapped`).

## 6. BOAMP deadlines (A2.6)

BOAMP writes the offset of the publication day: "12:00:00+02:00" in October for 19 November (Paris +01:00); BOAMP's page says
12h00 = 11:00 UTC, the site said 10:00. `normalise._paris_wall_time`: a +01:00 / +02:00 deadline is read as Paris wall time on
its own day (zoneinfo Europe/Paris); Z and overseas offsets stay. Both the eForms and the 2015-2022 schema paths. Backfill:
`python -m dgate.ops.remap_source --source fr_boamp --epoch 96 --status open --yes`, then without `--status` for the rest.

## 7. Numbers (A2.7)

- /market names its set beside the figures ("military goods and works only, as each source published them: award notices
  and corrections included, a notice in TED and a national portal counted once per source") and links the tender list of that
  set (`scope=core&status=all`, the country and codes); the headline label says the scope.
- Market "With an amendment" uses the buyer page's rule (`amendmentsShown`, six months of watching): the API now sends
  `observedFrom` for the market too (`stats.amendments_watched`).
- /data "usual month": `stats.month_gaps` takes the median of the last 12 whole months (PLACSP said about 21 for 41,142
  notices: ten thin years outweighed the current one); the sentence says "In the last 12 months the usual month held about N".
- Methodology and home: collection "daily for tender sources and funding portals, monthly for the EU research datasets
  (CORDIS, EDF results)" instead of "every source once a day".
- Calendar and ICS: `/v1/tenders/calendar` sends `withoutDeadline` (open notices of the same filters with no deadline; 0 with a
  date range); the calendar's tender line and the file's description say "N open tenders state no deadline".
- Speed: the buyer aggregate's live open count reads the open notices of the default scope (a few thousand, as before plus the
  supply scope); `openCoreCount` is one capped list count on the buyer page; the calendar adds one capped count. The search
  is unchanged (its buyer line reads the buyer group it already has).

## 7b. Latvian Interior agency still flagged (coordinator's item)

Cause: `pipeline.SEEDS_FILE` was `Path(__file__).parents[1] / "seeds"`. The image installs the package into the venv
(`pip install .`) as well as copying it to /app; a process that imports it from the venv (uvicorn, a console script, a working
directory other than /app) looked for `site-packages/seeds`, printed "seed file ... not found; using the built-in list", and
`buyer_cleanup.rejected_names` read no derived file, so the person-rejected row of `defence_buyers_derived_LV.csv`
(nodrosinajuma valsts agentura, `rejected`) never reached `rejected_flags`. Fix: `pipeline.seeds_dir()`: `DGATE_SEEDS_DIR`
(config) when set, else the first folder holding `defence_buyers.csv` of: next to the package, `./seeds`, `/app/seeds`;
`infra/docker-compose.yml` sets `DGATE_SEEDS_DIR=/app/seeds` for the api and the worker. Narrow command:
`python -m dgate.ops.buyer_cleanup --rejected-only` (report: the seed folder used, the rejected names, the flagged rows they
match) / `--rejected-only --yes` (unflags exactly those; today only that agency), then
`python -m dgate.reprocess --reclassify-serving --yes` for `sig_buyer` / `is_defence` of its notices.

## 8. Ops commands (production, after the deploy; migration 0110 by the migrate service)

```
python -m dgate.ops.supplier_countries            # report: winners whose country their name / number / form contradicts, UK rows
python -m dgate.ops.supplier_countries --yes      # write; prints the --undo window
python -m dgate.ops.supplier_dedupe               # report: groups by rule, left alone by reason, Italian pairs waiting
python -m dgate.ops.supplier_dedupe --yes         # merge; prints the --undo-batch window
python -m dgate.ops.company_groups                # report: companies per curated group
python -m dgate.ops.company_groups --yes
python -m dgate.ops.buyer_families                # report (the worker writes it daily; --yes now)
python -m dgate.ops.buyer_families --yes
python -m dgate.ops.remap_source --source fr_boamp --epoch 96 --status open --yes   # deadlines; then without --status
python -m dgate.ops.remap_source --source pl_ezam --epoch 96 --yes                  # notice-details links
python -m dgate.ops.remap_source --source de_bkms --epoch 96 --yes                  # oeffentlichevergabe.de links
python -m dgate.ops.warm_lists                    # the buyer snapshot in the new scope (or wait for the 4-hourly run)
python -m dgate.ops.buyer_cleanup --rejected-only           # report: the Latvian Interior agency
python -m dgate.ops.buyer_cleanup --rejected-only --yes     # unflag it; then:
python -m dgate.reprocess --reclassify-serving --yes
```

Expected: supplier_countries corrects LEONARDO Germany GmbH, Saab Finland Oy, Rheinmetall Canada Inc. (name), Indra Avitech GmbH
(legal form), KNDS Ammo France (name), Rheinmetall Expal Munition S.A. only if a Spanish co-tenderer is on its notices, every UK
row to GB. supplier_dedupe merges Saab AB / SAAB Aktiebolag (`company_number`), Landsysteme / Land Systeme and RheinmetallMAN
(`name_key_spaces`), the same-name pairs with no conflicting number (Thales Deutschland, Hensoldt Optronics, KNDS Deutschland if
their numbers agree), reports Rheinmetall Electronics (two VAT numbers) and Leonardo (merged only if a notice gives one written
name with each number). buyer_families adds `nl_defensie`, `spelling_variant` (1 RBL, Staatl., Beschafffungsamt), `jae_male`
and `twin_notice` members. remap fr_boamp moves the November-onwards deadlines stated with +02:00 one hour later (269424: 10:00 ->
11:00 UTC).

## 9. Tests

Local, `D:\DEFENCEGATE TESTS\wp96` (own venv, Python 3.11; Postgres 17 container `dgate-wp96` on 55496; TZ=UTC; web mock env;
E2E_PORT 3096), final code:

| Check | Result |
|---|---|
| ruff | All checks passed |
| unit (`pytest`) | **3538 passed** |
| integration (`pytest -m integration`) | **1285 passed**, 0 failed |
| `tsc --noEmit` | exit 0 |
| `npm run check` (lib checks, wp96.check.ts included) | all ok |
| `next build` (mock) | exit 0 |
| Playwright, desktop + 375 px | **708 passed, 56 skipped**, 0 failed |

New: `backend/tests/unit/test_wp96.py`, `backend/tests/integration/test_wp96.py`, `web/lib/wp96.check.ts`, `web/e2e/wp96.spec.ts`.
Tests changed because the behaviour changed on purpose, each with a WP-96 comment: the BOAMP 26-98330 deadline (16:00 Paris on
30 November is 15:00 UTC), the German notice without BT-15 now links its notice page (test_de_bkms, test_wp72), the /data
sentence (ui.check), the buyer profile and buyer-page tests of the core-only rule (test_stats, test_wp52: a supply-only buyer now has a page and a profile; a dual-use-only buyer none), the market headline (wp89 e2e), the "Open now" cell read by its first figure (wp52b e2e). None deleted, skipped or loosened; `addopts` untouched.

## 10. Open decisions and limits

- The oeffentlichevergabe.de notice-page address form is not verified against a live page.
- Company groups are name patterns from a curated list with a source per group, not a register extract: a subsidiary under
  another name (e.g. a PGZ plant not listed) is not in the group until added; the group view lists companies, it does not sum
  values across them.
- The legal-form country default (GmbH -> DE, S.p.A. -> IT …) is the likeliest country, stored with basis `legal_form` so it
  can be found and undone; a form held by several countries (S.A., Ltd) never decides alone.
- Rheinmetall Electronics GmbH (two VAT numbers) and the Italian pairs without a shared written name wait for a person.
- The market keeps its own set (core, every notice per source); it is labelled and linked, not aligned with the list's default.
- funding.ics does not yet count calls without a deadline (the tender calendar and its file do).
- Privacy: no personal data stored; organisation_country_fix holds companies' countries only. DATA_PROTECTION inventory unchanged.
