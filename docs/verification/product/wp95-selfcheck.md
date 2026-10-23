# WP-95 self-check: data correctness, values, winners, classification (persona round of 23 October 2026, A1)

Branch `wp-wp95` from `integration` (a7ae02d). Input: `D:\DEFENCEGATE TESTS\ux-oct23\SUMMARY.md` section A1 (items 1-5) and the
evidence of p01-es-auto, p07-it-analyst, p10-journalist, p04-pl-ammo (problems.csv, dumps, TED answers `ted1-4.json`,
`ted-fincantieri.json`, the tender CSV exports). Owner priorities: correctness, completeness, usability. No deploy, no push, no
production read or write, no external source called from the laptop (the TED field names used are the ones the persona's own TED
queries answered with). Not touched: `awards.person_reason` / `clean_supplier_name` (parallel WP-94), the WP-88 copy rules.

## 1. Value kinds (A1.1)

`dgate/award_value.py` (new): every award value is `contract` (the contract awarded; a call-off is a contract), `framework` (the
ceiling of a framework agreement or dynamic purchasing system) or `estimate` (the buyer's estimate where the award states no value).

- **TED.** The search API's `total-value` is not one field: on the persona's notices it is BT-161 (808800-2025), the framework
  maximum BT-118 (390572-2026, EUR 11,930,000 against tenders of 318,900; 854350-2025, DKK 97,000,000) and the procedure estimate
  BT-27 (712069-2026, award values -1). The award loader now asks `BT-161-NoticeResult`, `BT-118-NoticeResult`, `BT-709-LotResult`,
  `BT-720-Tender` and the currencies with the winners (`awards.AWARD_FETCH_FIELDS`), and `ted_value` decides: a framework maximum is
  a ceiling, a notice value or winning-tender values a contract value, an award stating only placeholders has the estimate. With no
  eForms value field at all (older format, or TED omits them) the stored value is read as the mapper chose it: a total is a contract
  value unless the title says framework, a sum of lot estimates an estimate.
- **PLACSP.** The awarded amount is a ceiling for a folder that establishes an acuerdo marco or a dynamic purchasing system:
  `cbc:ContractingSystemCode` (now landed in the award payload, codes 1-4 per the syndication specification; not yet seen in a held
  payload, the backfill reports it) else the title (`kind_of_title`: acuerdo marco / contrato basado, CB en AM, CBAM, framework,
  Rahmenvertrag, accordo quadro, DPS ...). A call-off whose title quotes its framework's file number ("1º CB AM
  (2025/AR43U/00001894)") is linked to that notice (`award_notice.framework_id`).
- **Storage** (migration `0109_award_value_kind.sql`): `award.value_kind`; `award_notice.value_amount/value_currency/value_kind`
  (a TED notice's own value), `award_notice.framework_id`; `opportunity.other_buyers` (item 4). TED rows now carry their notice's
  value where the notice names one winner. A row without a kind is read as before WP-95 (`suppliers.value_of`), so the site is
  right before the backfill too, except for the frameworks only the backfill can find.
- **Sums** (`suppliers.value_totals`, one per procurement via `suppliers.best`): contract values only in `byCurrency`; `frameworks`
  and `estimates` listed apart, never added, so a framework and its call-offs are never counted twice; a twin pair takes a contract
  value before a ceiling before an estimate, PLACSP's amount before TED's. `largest`: the ten largest contract values with links
  (supplier page and every "who to approach" / winners card, in the collapsed Contract values block). Rows show the kind
  ("framework ceiling, not in the sum", "estimate, not in the sum") and "Call-off under the framework agreement <link>".
- Effect on the persona's examples (from their dumps; the TED re-read itself runs on the server): Rheinmetall Landsysteme
  EUR 41,753,450 over 18 → at most EUR 28,663,450 over 16 (390572 ceiling, 712069 estimate out, listed apart); MADZEAL EUR
  52,142,508 over 91 → EUR 49,380,008 over 89 by the title rule alone (TED 389204 IVECO and 401420 PIRAÑA frameworks out), its
  call-off 2026/AR43U/00002206E linked to 2025/AR43U/00001894E. Indra's EUR 4.93 bn: its Acuerdo Marco folders become ceilings by
  the title rule; the size of the drop needs production data.

## 2. Award notice page (A1.2)

`GET /v1/tenders/{slug}` adds `awardedTo` (legal-entity winners of the notice and of its other publications, `award_set.WINNERS`;
a supplier link where the supplier map lists them, none outside its window), `awardedPersons` (counted, never named),
`awardValue` (notice value with its kind, else the one winner's) and `otherBuyers`. The page: "Awarded to: INDRA SISTEMAS S.A.
(ES)" with the link, "and a natural person, not named"; the value cell is "Awarded value" (contract), "Framework ceiling" or
"Estimated value" with a one-line note.

## 3. TED winners of older-format notices (A1.3)

Cause: `awards.candidates` asked `notice_subtype = ANY(AWARD_SUBTYPES)`; an older-format (pre-eForms) notice has no subtype (NULL),
so TED 40783-2024 (Italian Navy, warship repair, defence directive, published January 2024, the site's /tenders/102720) was never a
candidate, and the search API states no winner for that format anyway. Fix, core scope and window unchanged: such notices are
candidates by notice type (`LEGACY_AWARD_TYPES`), and when the search record names no winner the notice document
(`ted.europa.eu/en/notice/<n>/xml`, the notice's own XML link) is read (`awards.legacy_award_record`: name, country, national
number of each contractor of the TED_EXPORT R2.0.8 / R2.0.9 forms, then the same `read_award` rules, persons blanked). A document
naming nobody leaves the notice without winner, counted (`legacy_documents`, `legacy_with_winners`). /methodology says so
("Contract values and winners"). The element names are the documented TED_EXPORT ones, not checked against a fetched document
(no external call from the laptop): the run's counts show at once whether they hold.

## 4. Classification honesty (A1.4)

- Levels by signal (`confidence.label`, served as `confidence.label`; the web uses it, an older API gets signal words too):
  "Clearly defence"; "Defence buyer, ordinary purchase"; "Defence buyer, some military codes"; "Defence directive, unlisted buyer";
  "Weak defence signal". No "Probably/Possibly defence" anywhere.
- High needs the military code as the MAIN (first) code with a listed buyer or the directive (from a body not of a civil or
  security class), or the directive used by a listed buyer (the Bulgarian MoD pyrotechnics). The gatehouse /tenders/396812 is
  medium. `CONFIDENCE_SQL` is the twin (`o.cpv_codes[1]`), levels still partition every row.
- Catch-all rule (`classify.CATCH_ALL_CODES` = 20): a military code that is not the main code of a notice with more than 20
  distinct codes, from a buyer that is neither listed nor named a defence body (class known), without directive or defence twin, is
  no defence signal: `is_defence` false (Bétera, Cetursa, Molina de Segura). `sig_cpv_military` keeps saying the code is there.
- Latvia: Nodrošinājuma valsts aģentūra (Interior's provision agency) leaves the defence vocabulary, is class `security`, its
  derived-list row is `rejected`, and `ops.buyer_cleanup` now unflags a name a person rejected whatever its notices' legal basis.
  Joint procurements: `otherBuyers` from TED's buyer-name list (mapper; `ops.co_buyers` for the held notices), shown "Buyers: A;
  B (joint procurement)".
- Effect on the local dataset (the two CSV exports of production downloaded by the personas, signals read back from `why_listed`
  and `confidence`; script in the scratchpad, `local_counts.py`):

| Export | Before | After |
|---|---|---|
| p10 default list, 1,549 | Probably 1,298 · Possibly 143 · Clearly 108 | Defence buyer, ordinary purchase 1,187 · Clearly 211 · Weak signal 142 · Defence buyer, some military codes 9 |
| p07 Italy, 1,000 | Probably 464 · Clearly 389 · Possibly 147 | Clearly 834 · Weak signal 147 · Defence buyer, some military codes 19 |

Level moves: p10 medium→high 112 (directive used by a listed buyer), high→medium 9 (military code not main), low→medium 1; p07
medium→high 464, high→medium 19. Catch-all rule: 1 row of p10 leaves the list (Donegal Education and Training Board, 46 codes);
the Spanish catch-alls were in the ES "all" scope the export does not hold.

## 5. /changes (A1.5)

New kind `award` (a new notice whose status is awarded or whose notice kind is award/formalisation), filter "New award notices",
counts `awards`, legend "New award"; each entry shows "Published <date>"; the lots of one notice and one notice from two sources
are one row (`changes.group_events`: same buyer, title without its lot number, main code, publication date, deadline, kind, day,
changes; `repeats`), the digest uses the same rule (its tenders stay new | amended).

## 6. Ops commands for production (orchestrator, after the deploy; migration 0109 is applied by the migrate service)

```
python -m dgate.ops.award_values            # report: TED value fields re-asked by number (100 a request, 1/s), kinds by source
python -m dgate.ops.award_values --yes      # write; a second run writes nothing (only rows without a kind are read)
python -m dgate.pipeline awards             # older-format core-scope TED result notices are candidates now: winners from the documents
python -m dgate.ops.co_buyers               # report: joint procurements in the landed TED payloads
python -m dgate.ops.co_buyers --yes
python -m dgate.ops.buyer_cleanup --yes     # unflags Nodrosinajuma valsts agentura (rejected)
python -m dgate.reprocess --reclassify-serving --yes   # sig_buyer / is_defence for the agency and the catch-all rule
```
Expected: `award_values` reports 390572-2026 and 854350-2025 as `framework`, 712069-2026 as `estimate`, the PLACSP Acuerdo Marco
folders as `framework`, `placsp_call_offs_linked` > 0 (MADZEAL 2206E), and the contracting-system codes met (none in held payloads);
`awards` reports `legacy_documents` / `legacy_with_winners` (Fincantieri on 40783-2024 if the document names it); reclassify
reports `defence_to_not` for the catch-all notices; the confidence labels need no re-run (read time).

## 7. Tests

Local, `D:\DEFENCEGATE TESTS\wp95` (own venv, Python 3.11; Postgres 17 container `dgate-wp95` on 55495; TZ=UTC; web mock env;
E2E_PORT 3095), final code:

| Check | Result |
|---|---|
| ruff | All checks passed |
| unit (`pytest`) | **3468 passed** |
| integration (`pytest -m integration`) | **1275 passed**, 0 failed |
| `tsc --noEmit` | exit 0 |
| `npm run check` (lib checks) | all ok |
| `next build` (mock) | exit 0 |
| Playwright, desktop + 375 px | **700 passed, 56 skipped**, 0 failed |

New: `backend/tests/unit/test_wp95.py` (value kinds on the persona's TED records, title rule, PLACSP codes, framework refs, older-
format documents and persons, catch-all rule, Latvian agency, co-buyers, lot titles and grouping), `backend/tests/integration/test_wp95.py`
(supplier page and report by kind, twin by kind, award notice page, legacy loader with a stand-in TED, framework maximum stored,
both backfills report / write / idempotent, reclassify, cleanup, /changes awards and lots), `web/e2e/wp95.spec.ts`. Tests changed
because the behaviour changed on purpose, each with a WP-95 comment: confidence levels (directive + listed buyer and directive +
main military code are high; labels in the API object), a sum of lot estimates is an estimate (wp80, supplier map, wp81 unit and
lib checks), the PLACSP fixture folder is an "Acuerdo marco" so its amount is a ceiling (award twins), /changes counts carry
`awards` and identical-looking fixtures got distinct titles (changes, wp52), the derived-list check accepts a `rejected` row only
if no rule names it a defence body, the WP-87 PLACSP-amount step turns the PLACSP winners on, the VALUE_RULES words. None deleted,
skipped or loosened; `addopts` untouched.

## 8. Open decisions and limits

- TED call-offs are not linked to their framework (eForms OPT-100 not asked: field name unverified); PLACSP links only where the
  title quotes the file number.
- `ContractingSystemCode` codes are from the specification, unseen in held payloads; the title rule decides until they appear.
- Largest contracts are ordered within the supplier's currencies (most contracts first), never converted.
- The confidence sample of 16 October was measured under the old high rule; not re-read (methodology says so).
- The digest counts a new award as a new notice of the week, while /changes?kind=new now excludes awards: the digest's
  "has the rest" link for new notices omits the awards.
- Grouping in /changes is by look-alike fields; e-Zamówienia parts with different part titles stay separate rows (no shared
  procedure identifier is stored for that source).
- Privacy: no new personal data stored (contractor names of older-format notices pass the same person rule; other buyers are
  public bodies); DATA_PROTECTION inventory unchanged.
