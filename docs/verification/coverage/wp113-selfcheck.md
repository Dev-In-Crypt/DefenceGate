# WP-113 self-check: source field mappings (coverage audit of 24 October 2026)

Branch `wp-wp113` (from `integration` ea00dca). Findings: `D:\DEFENCEGATE TESTS\coverage-oct24\NOTES.md` (accuracy) and
`accuracy\problems.csv` (ids 1-15). Evidence below was read on production read-only (short SELECTs through the postgres
container; raw payloads of 17 notices read once; the who-may-apply facts of three calls through one `run --rm` worker
one-off). No migration was needed (0125 unused). No data was written anywhere but the local test database.

Note on method: the first raw payloads (two reads, 13 notices) were read with `docker exec` inside the running worker
container, before the rule against running tools inside production containers reached me; the helper file left in its
`/tmp` was removed. Every later read used the postgres container or a `run --rm` one-off.

## Items

### 1. BOAMP deadlines (problems 1, 2): fixed

Before: 26-98956 (/tenders/246424) body `FNSimple.initial.procedure.dateReceptionOffres = 2026-10-29T16:00:00`, column
`datelimitereponse = 2026-10-29T16:00:00+00:00`, stored `2026-10-29 16:00 UTC` (one hour late). 26-100516 (/tenders/329978,
buyer cp 97400 Saint-Denis de La Reunion) stored 09:00 UTC for 09:00 Reunion (4 h late); 26-103716 (/tenders/397583, cp 97300
Cayenne) stored 16:00 UTC for 16:00 Cayenne (3 h early). eForms 26-98817 (/tenders/269424, DID Saint-Denis, ORG-0001 postcode
97476) `EndTime 12:00:00.000+02:00` read as Paris 11:00 UTC for 12:00 Reunion (08:00 UTC).

Change (`normalise.py`): `_fr_zone` picks the buyer's zone from its postcode (national form `organisme.cp`; eForms: the
organisation the contracting party names) or, without one, the first department listed (`code_departement`); 971-978 and
986-988 map to their own zones, everything else is Europe/Paris. `_fr_national_deadline` reads `dateReceptionOffres` as wall
time in that zone and, where the body has none, the column's printed time (its "+00:00" is false). The eForms and legacy
readers take the zone too (a Paris offset on an overseas buyer's notice is the converter's, the wall time is local).
The page's local clock line still names the country's zone (Paris) for an overseas buyer: the instant is right, the second
line is the Paris time of it (web `localDeadline`, by country; a buyer zone would need an API field: open item).

Test: `tests/unit/test_wp113.py` Paris winter/summer and both DST edges of 2026 (28/29 March, 24/25 October), the false-UTC
column, Reunion, Guyane, Martinique, Guadeloupe, Mayotte, Tahiti, Noumea, Saint-Pierre summer and winter, Corsica, the
department fallback, eForms overseas vs metropolitan vs a non-Paris offset. Integration `test_wp113.py` re-derives a stored
26-98956-like row from its raw payload to 15:00 UTC.

### 2. TenderNed (problems 3, 4): fixed

Before: 428231 (/tenders/146809) list row `sluitingsDatum 2026-08-19T12:00`, detail `2026-11-16T12:00`
(`publicatieIDLaatsteRectificatie 442733`), stored 19 Aug. 422883 (/tenders/146747) detail `cpvCodes`: 34900000 listed first
(`isHoofdOpdracht false`), 42400000 flagged; stored main 34900000.

Change: deadline from `detail.sluitingsDatum`, the list row as fallback; `_nl_cpv` puts the flagged code first. The CPV
order is not a version (`db.same_value` treats the list as a set), so the re-derive updates the serving row's order as an
attribute (`remap_source.plan`), reported as `cpv_codes (attribute)`.

Test: unit (both), integration (version 2 with `changed_fields = [deadline_at]` and note `remapped`, version 1 closed and its
payload untouched; the order alone: attribute update, no version; second run examines 0).

### 3. Procedure codes (problems 5, 6): fixed

Production counts (24 Oct): TED `4` 11,724, `V` 5,896, `9` 4,053, `Z` 194, `6` 178, `E` 54, `F` 3; pl_ezam `T` 76, `V` 38;
PLACSP `7` 8,185 (+1 agg), 3,048 of them titled as a call-off of a framework ("acuerdo marco", "basado en", "derivado").

Change: `tenders.TED_LEGACY_PROCEDURES` spells out TED's pre-eForms codes 1, 2, 3, 4, 6, 9, C, T, V, Z in the serving layer
(E, F, B stay codes: meaning not certain); the stored code stays as the source gave it. `placsp.PROCEDURE_NAMES["7"] =
"Derivado de acuerdo marco"` (stored as the name, as for the other verified codes; web says "Contract based on a framework
agreement"). Web `legalBasisLabel("CODE_OTHERS")` = the "other" label. "De-open" / "de-uvgo": already translated on
production (WP-96: "Open procedure (German national rules)", "UVgO (...)"; the "As stated: De-open" line is the source's
code shown beside it), no change.

Tests: `test_procedure_label.py` ("V" and "4" moved from the not-shown list to the shown list: the reversal this item asks
for; "E", "F", "B" added to the not-shown list), `test_placsp_quality.py` and `test_wp1_placsp.py` (7 named, 5 and 8 still
codes), `web/lib/wp113.check.ts`.

### 4. German links (problem 7): fixed

Before: 7,752 of 12,743 de_bkms rows link a buyer platform page (BT-15), e.g. /tenders/284683 `https://www.meinauftrag.rib.de`.

Change: `from_de_bkms` links the notice's own page on oeffentlichevergabe.de (built from its eForms notice id) and keeps BT-15
as `documents_url` (a new payload-only Opportunity attribute, left out of the payload while empty so no hash moves), unless
BT-15 is a bare home page (no path, no query). The API's `documentsUrl` for a German notice, and for a TED notice through its
German twin, reads it from the latest version (`tenders.get_tender`); a row not yet re-derived keeps its link as before.

Tests: unit (platform page kept as documents, bare home page dropped), `test_wp72.py` unit and integration updated to the new
link (the documents link asserted instead), integration: API serves the notice page as the original and BT-15 as documents.

### 5. BOAMP legal basis (problem 8): fixed; award values (problem 9): not changed

Before: 3,906 DIRECTIVE-24, 33 DIRECTIVE-25, 13 DIRECTIVE-23 rows without legal basis (24-21716 states
`cbc:RegulatoryDomain 32014L0024`).

Change: `_fr_legal_basis`: the defence perimeters as before, else an eForms `cbc:RegulatoryDomain` that is a known CELEX, else
DIRECTIVE-24/25/23. Not a defence signal (only 2009/81 is).

Award values: 19-182081 (/tenders/143614) states five decisions of EUR 2,500,000 each. The mapper reads a single decision's
amount and never sums (several decisions of one notice can be holders of one framework, so a sum would be wrong). Winners
are the award tables' (awards.py, another package). Left as it is: open item.

### 6. PLACSP publication dates and TED links (problem db 5): the control fixed; no data was wrong

Production: of the 17,757 PLACSP rows without a publication date, 17,741 carry the entry's own date (`notice_date`: award
9,023 + 611, formalisation 7,420, update 548, cancellation 148), which the page shows as "Notice date"; 16 aggregated rows have
neither. The award entry's date is not the call's publication and is not stored as one (remap_source, WP-12). Of the 833
"unlinked" Spanish TED notices, 764 share the eForms procedure identifier with a PLACSP row that is linked to the procedure's
first TED publication: a row holds one `ted_ref`, so the procedure's later TED notices (award, subtypes 29, 38) never matched.

Change (`ops/controls.py`): a TED notice whose procedure identifier a national row shares is linked; a missing date is a row
with neither a publication nor a notice date. The `placsp_links` alarm then measures what it was meant to.

Test: integration (call and award TED notice of one procedure, one PLACSP award entry: unlinked 0, missing dates 0, ok);
`test_wp15.py` unchanged and green.

### 7. Funding (problems 10, 11, 12)

- Who may apply: fixed in `who_apply.py`. 188 RAPID: no document source (`no_source`); its page rule `max_group_headcount`
  (< 2000 staff, consolidated) is now "Companies". 170 Vinnova: `no_source`; the call text "aimed at Swedish small and
  medium-sized enterprises (SMEs)" (and the Swedish "riktar sig till ... små och medelstora företag") is now "Companies, SMEs
  only" with that sentence as evidence. 125 DIGITAL-2026-SKILLS-10: the entity list read from the call document is unverified
  (confidence 0.3, not served); the verified sme fact quotes "be legal entities (public or private bodies)", which is now
  "Companies" with that quote. Only calls with no served facts use the text rules.
- Rolling call /funding/25: already handled on `integration` by WP-109 (key date "8 Oct 2026 (passed; the source publishes no
  next cut-off yet)", badge "Open: rolling submission"); production shows the WP-109 badge text. No change.
- EU deadline time: the portal's record has no time; 41 of the 109 stored call documents state one ("Deadline for submission:
  1 October 2026 – 17:00:00 CEST"). `eu_portal.document_closing` reads it, only for the portal's own closing day (never another
  topic's or stage's), and `with_document_time` applies it in the nightly EU run (`pipeline.py`, one line) and in the ops
  module; the deadline is then an instant (17:00 Brussels), no longer "date only". Nothing is invented: a call whose document
  states no time stays date only.

Tests: unit (RAPID, Vinnova English and Swedish, the legal-entities quote and a public-bodies one that stays undecided, the
document time for its day / another day / none), integration (who may apply written, the time written, the nightly upsert
keeps it).

### 8. TenderNed value from the TED twin (problem 13): fixed

Change: the tender page says under the value "Not stated in this notice; as given in the TED notice of the same procurement"
when `valueFrom = ted_twin` (the same words as the procedure's). Test: `web/e2e/wp113.spec.ts` (mock: the Polish demo notice
carries `valueFrom: ted_twin`; a TED notice has no such line).

## Re-derive (ops)

`python -m dgate.ops.wp113_rederive` (report) then `--yes`. It runs `ops.remap_source` at epoch 113 for nl_tenderned,
fr_boamp, de_bkms and es_placsp / es_placsp_agg (code 7 rows only), from the current version's stored payload: a changed
versioned field is a new version with `changed_fields` and the note `remapped` (a DefenceGate correction, not an amendment);
the old version gets `valid_to` only. Then the calls (who may apply, EU closing time; not versioned). Idempotent.

Expected counts (from the production counts above; the report prints the exact ones per source and field):

| source | field | expected |
|---|---|---|
| nl_tenderned | deadline_at | **14 versions** (measured, report mode on production) |
| nl_tenderned | cpv_codes (attribute) | **150** (measured; 145 attribute-only rows, 5 with the deadline version) |
| fr_boamp | legal_basis | about 3,950 versions (DIRECTIVE-24/25/23, plus eForms RegulatoryDomain) |
| fr_boamp | deadline_at | some hundreds (124 metropolitan national forms since 2025 plus older ones, about 75 overseas) |
| de_bkms | source_url | about 7,750 versions (minus the rows with no eForms notice id, which keep BT-15) |
| es_placsp (+agg) | procedure_type | 8,185 + 1 versions |
| calls | who may apply | **11** decided by a WP-113 rule (measured): 170, 188 (text, page rule), 125 and 11, 14, 16, 18 (DIGITAL), 80, 92, 97, 107 (EDF, already "companies" by the programme rule) by the legal-entities quote; plus 72 research answers of WP-109's rule that production has not written yet |
| calls | EU deadline time | **79** of 158 date-only calls (measured; one call document serves several topics) |

Rows examined: fr_boamp 11,217, de_bkms 12,743, nl_tenderned 481, PLACSP 8,186. Suggested order on the server: one source at a
time, `--source nl_tenderned` first, outside the busy hours (11 and 16 UTC).

## Files outside the package

- `backend/dgate/tenders.py`: the legacy procedure labels; the documents link read from the version payload.
- `backend/dgate/db.py`: `documents_url` left out of the payload while empty (one word).
- `backend/dgate/ops/controls.py`: the `placsp_links` measures.
- `backend/dgate/ops/remap_source.py`: epoch 113 docs, `documents_url`, CPV order as an attribute, a `procedure` filter;
  `backend/dgate/ops/repair_ted.py`: attribute fields counted in the report (one line).
- `backend/dgate/pipeline.py`: one line (the EU closing time).
- `web/lib/taxonomy.ts`, `web/app/(public)/tenders/[slug]/page.tsx`, `web/lib/mock/tenders.ts`.

## Checks

- Backend (local copy `D:\DEFENCEGATE TESTS\wp113`, Postgres 17 on 55513): ruff clean; unit 3,865 passed; integration 1,389
  passed (0 failed).
- Web: `tsc` clean; lib checks all ok (`wp113.check.ts` included); `next build` ok; Playwright 846 passed (`wp113.spec.ts` 2 tests
  x projects).
- Production, read-only: `wp113_rederive --source nl_tenderned` in report mode through a `run --rm` worker one-off with this
  branch's package mounted read-only (481 payloads, nothing written), the numbers above.

## Open items

- The page's local clock line for an overseas French buyer names Paris (by country); the instant is right. A buyer zone needs an
  API field (`deadlineZone`) and the web's `localDeadline` to use it.
- BOAMP award amounts of notices with several decisions and BOAMP winners (awards package).
- 69 Spanish TED notices stay unlinked after the control's fix: the true remainder for `link_twins`.
- TED date-only deadlines at local midnight (problem 14) were not in this package.
- The NCP-network DIGITAL call (16) is now "Companies can take part" from the call's verified sentence; the topic may restrict it
  to nominated NCPs (not in a verified fact). Worth a look by the verifier.
