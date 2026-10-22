# WP-78: eligibility facts for the funding calls that have none (22 October 2026)

Builder/operator report. Branch `wp-wp78` (on top of `integration` f606b51). Not deployed;
the orchestrator deploys and runs the one production command below.

## 1. The audit's numbers were a measuring artefact

The database audit (`qa-full-database.md`, finding 4) gave "facts for 18 of 51 open calls and 0 of 32
forthcoming". It matched `call_eligibility.url` against the topic code, which only works for call-document
rows (`<pdf>#<topic>`). Calls without a call document are read from the general annexes (key = annex URL)
and their own topic text (key = `call-text:<hash>`), so the audit missed them.

Measured with the code the site uses (`eligibility.read_many`, the same call as `/v1/funding/{id}`),
read-only on production, 22 Oct 2026:

| | calls | with served facts before | without |
|---|---|---|---|
| open | 51 | **46** | 5 |
| forthcoming | 32 | **31** | 1 |

Every unit (document, annex or topic text) that serves an open or forthcoming call was already read with
prompt v4. Nothing was "never queued". The only units not held were 2 closed Chips JU calls (a zip
behind the link).

## 2. The 6 calls without facts, and why

| id | status, deadline | call | why no facts |
|---|---|---|---|
| 24 | open, 2026-11-04 | HORIZON-EIC-2026-ACCELERATOR-01 | No call document. Its source is the EIC Work Programme 2026 (209 pages), read once for all EIC schemes and without the topic: that row (download URL) states 0 facts. The topic text states 0. |
| 25 | open, deadline 2026-10-08 already past (status lag) | HORIZON-EIC-2026-STEP | Same EIC row, 0 facts. |
| 132 | open, 2026-12-01 | DIGITAL-JU-CHIPS-2026-AI1-SG | The portal lists "Guide for applicants", not "Call document", so it was never a source. The link is a viewer page (JavaScript) holding the PDF address. Topic text: 0 facts. |
| 134 | open, 2026-12-01 | DIGITAL-JU-CHIPS-2026-AI-GFP | Same as 132. |
| 133 | open, 2026-12-08 | DIGITAL-JU-CHIPS-2026-SG-JAPAN | No guide. The rules are in "Appendix 8 of the Chips JU Work Programme" (viewer page, 167 pages, names the topic). Never a source. |
| 141 | forthcoming, deadline 2026-08-27 already past (status lag) | DIGITAL-JU-EUROHPC-2026-HPCQC-01-IBA | The portal lists only standard forms and regulations: no document with the call's rules. Its topic text states 0 facts. Not fixable from our data. |

No call is blocked by a licence gate. The Chips JU site serves its files at public `/File/download.aspx`
addresses (probed 22 Oct, 1 request per 1.5 s, our User-Agent; its `robots.txt` path returns an HTML page,
so there are no rules to obey). One quality problem behind the EIC rows: the EIC work programme mixes
Pathfinder, Accelerator and STEP rules. Read without the topic, it gives Pathfinder sentences ("can support
projects from consortia or from single legal entities"). Those sentences would be wrong for the Accelerator.
So simply forcing a re-read was not the fix.

## 3. Code change (branch `wp-wp78`)

`backend/dgate/eligibility.py`, `backend/dgate/ops/extract_eligibility.py`:

- `sources_of`: when there is no "Call document", the source is a "Guide for applicants". Without a guide,
  it is a Chips JU "Appendix N of ... Work programme". Either is read per topic, like a call document. A
  "Call document" still wins. An appendix of any other work programme is not taken.
- `_get_pdf`: a viewer page whose script holds `fileUrl = '/File/download.aspx?...'` is followed to the
  file. The path is joined to the page's own site, so the existing same-site and https rules apply.
- The EIC work programme is read once **per topic** (key `<url>#<topic code>`). The model is told which
  topic it reads, and quotes that name another topic are refused (the existing check). Until a topic is
  read, the row already held for the whole document keeps being served, so no call loses facts. The
  Horizon general annexes are unchanged (one row for all topics).
- `extraction_units` ranks forthcoming calls before closed ones (they were ranked together before). The
  CLI list shows the forthcoming count.

Tests: `tests/unit/test_wp78_sources.py` (7) and `tests/integration/test_wp78.py` (2). They cover the
viewer page being followed, a file on another site not being followed, guide over appendix, call document
over guide, non-Chips appendices refused, EIC keys per topic with fallback to the old row, Horizon annexes
unchanged, forthcoming before closed, the per-topic EIC read telling the model the topic and refusing
another topic's quote, and a second run being held. Run locally in `D:\DEFENCEGATE TESTS\wp78` (own uv
venv, throwaway Postgres `dgate-wp78` on port 55478): ruff clean, the whole unit suite green, the whole
integration suite green.

## 4. Production runs and budget

**No model call was made in WP-78. Spent: USD 0.00.** Month spend is still USD 2.943 of the 5.00 cap
(`llm_usage`: 0.434 edf_factsheet + 1.102 + 1.407 call_eligibility), so USD 2.057 remain.

Why nothing was run: with the deployed code every unit of every open and forthcoming call is already held
at prompt v4, so a run would not spend anything and would not add a fact. Reading the 6 calls needs the
code above. Running branch code inside the production worker was refused as a production deploy, which
is the orchestrator's step.

**After the deploy, one command** (in the worker; it skips everything already held, stops at the cap):

    docker compose exec worker python -m dgate.ops.extract_eligibility            # dry run: list + month spend
    docker compose exec worker python -m dgate.ops.extract_eligibility --yes

It reads exactly 14 units. I computed this offline with the branch code over the exported call rows; the
export has since been deleted.

| units | calls | estimated cost (USD) |
|---|---|---|
| EIC WP 2026 per topic, open | 24, 131, 25 | 3 × ~0.026 |
| Chips guides, open | 132, 134 | 2 × ~0.006 |
| Chips Appendix 8 for SG-JAPAN, open | 133 | ~0.03 |
| EIC WP 2026 per topic, forthcoming | 128, 129, 130 | 3 × ~0.026 |
| Chips guides, closed (they keep their coverage) | 135, 136, 137 | 3 × ~0.006 |
| old Chips zips, closed (will fail again, no spend) | 26, 27 | 0 |

The total is about **USD 0.22-0.30**. That leaves about USD 1.75, well above the 0.20 floor. Prices are
derived from `llm_usage`: 0.30 per M input tokens and 1.50 per M output tokens (the configured high side).
The cap check in `llm.py` runs before each call (worst case per EIC call is about 0.05). For a stricter
order, run the keys one at a time with `--yes --url '<key>'`, open calls first. The key shape is
`<document url>#<topic code>`, for example
`https://eic.ec.europa.eu/document/download/52598755-1351-4b54-b46b-e2682d0a3aec_en?filename=EIC-Work-Programme-2026.pdf#HORIZON-EIC-2026-ACCELERATOR-01`.

Expected coverage after the run: open 49-51 of 51 (24, 132, 133, 134 should get facts; 25 only if the
STEP chapter states them), forthcoming 31 of 32 (141 has no source). 131 and 128-130 already have facts;
they get topic-specific ones.

## 5. Checks on what is served (read-only, production)

- Quote check: a fact is served only if `verified` is true, meaning its quote was found in the stored
  document text (`_served_fact`). The 83 served facts of the sample below all carry such a quote.
- E-mail addresses: `--redact-stored` dry run finds 4 document texts with an `@`. A regex check shows 0
  e-mail addresses in them: they are the programme name "HealthData@EU". There are 0 `call_eligibility`
  rows with an `@`, and 0 addresses in served facts. Nothing personal is stored. The schema has no
  contact fields and `clean()` redacts addresses before storing and before sending.

## 6. Spot-check: 10 served calls (not newly extracted)

No call was newly extracted, so I checked the 10 open calls closing soonest that have facts instead:
EDF 4, DIGITAL 3, HORIZON 3. For each served fact I compared the value with its verbatim quote and its
note, and asked whether it is a rule of this call. Calls: 131 EIC Defence, 56 SSRI-02 (PCP), 57 FCT-06
(RIA), 118 EDIP LS-IRA-MAB, 114 EDIP FNLC-SA-SEAP, 193 EDIP CSA-PREP, 144 ECCC REGCABH, 148 ECCC AI4SME,
147 ECCC EULEG, 112 EDIP CPA-GNPS.

| field | served | correct | wrong | error rate |
|---|---|---|---|---|
| eligible_countries | 10 | 9 | 1 | 10 % |
| consortium_required | 10 | 8 | 2 | 20 % |
| funding_rate | 9 | 9 | 0 | 0 % |
| natural_persons_allowed | 9 | 9 | 0 | 0 % |
| sme_only | 8 | 8 | 0 | 0 % |
| entity_types | 8 | 8 | 0 | 0 % |
| ownership_control_restriction | 7 | 7 | 0 | 0 % |
| min_entities | 6 | 5 | 1 | 17 % |
| min_countries | 6 | 6 | 0 | 0 % |
| cascade_funding | 5 | 5 | 0 | 0 % |
| single_applicant_allowed | 5 | 5 | 0 | 0 % |
| **all** | **83** | **79** | **4** | **4.8 %** |

The 4 errors:

1. **114** (SEAP functioning): `consortium_required = True` on the quote "Only single applications by a SEAP
   are allowed". It should be false. `reconcile` adds "check the call document", but the value stays
   wrong.
2. **114**: `min_entities = 3`. That is the minimum number of SEAP members, not of applicants. The note
   says so, but the value misleads a filter.
3. **193** (CSA-PREP): `consortium_required = False` on "Single applicants may apply only if they are a SEAP".
   The general rule is a 4-country consortium, so it should be true, with the SEAP exception in the note.
   The prompt asks for exactly that.
4. **56** (PCP): `eligible_countries = "EU Member States or Associated Countries"` comes from the
   procurer-composition sentence. Under the general annexes, applicants from other countries may take part.

Also weak but not counted as errors: the general-annex `funding_rate` of Horizon calls lists every
action-type ceiling, not this call's rate.

Suggested follow-up (not built; outside this package): a code rule in `reconcile` for "only single
applications by a SEAP / only if they are a SEAP" (consortium = not required for a SEAP, required
otherwise), the same way the V-B rules were added.

## 7. Open items

- The orchestrator deploys `wp-wp78` and runs the command in section 4. Then re-run the read-only
  coverage measurement and spot-check the 6 new calls (24, 25, 131, 132, 133, 134) against their documents.
- 25 and 141 are past their deadline but not closed (status lag, audit finding 4). They are a status
  problem, not an eligibility one.
- Scratch: files on the server's `/tmp` and in the worker container are deleted. The test container
  `dgate-wp78` and `D:\DEFENCEGATE TESTS\wp78` are local and can be removed.
