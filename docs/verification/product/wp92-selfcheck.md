# WP-92 self-check: "What it funds" from the topic description; who may apply from the call's own facts

Branch `wp-wp92` from `wp-wp91` (eef3ba5). Owner approval 23 October 2026. Commercial information only: the summary is at
most three sentences of the topic description's **Objective** / **Expected outcome** sections that pass a fail-closed filter;
Scope, Types of activities, Functional requirements and Expected impact are never read. The full description stays in the
raw store (as before) and is in no served table. **Migration 0108** (`call_funds_summary.sql`: four nullable columns on `call`;
additive). No deploy, no push, no production read or write, no secret, no model call, no external request (no SEDIA call: the
work is on fixtures).

## 1. What the source carries

- The **reference-data snapshot** (`grantsTenders.json`, `sources/eu_portal.py fetch_snapshot`) has no description: title,
  codes, programme, division, status, dates, type of action, tags (module docstring, checked on 10,164 topics in Sept 2026).
- The **topic-details document** the connector already fetches (`fetch_topic_details`, `data/topicDetails/<code>.json`,
  `TopicDetails`) is landed whole, after `strip_personal_data`, in the raw store (`pipeline.run_topic_details`, `_store_raw`).
  Fields the code reads: `conditions` (HTML: eligibility text, document links), `budgetOverviewJSONItem.budgetTopicActionMap`
  (budget line), `topicMGAs`, `tags`, `sme`, `links`. **New: `description`** (HTML), in which the portal writes the sections
  `Expected Outcome:` / `Scope:` (Horizon, Digital) and `Objective:` / `Scope:` / `Types of activities` / `Functional
  requirements` / `Expected impact` (EDF, EDIP).
- **Production probe (orchestrator, read-only, 23 October 2026):** `description` exists (1 to 9 KB). Headings are
  `<p class="topicdescriptionkind">Scope:</p>` followed by `<p>` paragraphs. EDF 2026 topics have only "Scope:", "Targeted
  types of activities:", "Indicative budget:" (some "Management mode:", "Form of funding:"), **no Objective**; EDIP-P FNLC topics
  have short descriptions with no heading; Horizon CL3 has the long form. So: a `topicdescriptionkind` paragraph is a heading
  whatever its label (the `<strong>` form stays supported), and an EDF / EDIP topic with no Objective / Expected outcome section
  may give **only the first sentence of its Scope**, only when it opens with "The objective of this topic is", "The aim of this
  topic is" or "This topic aims to", and only through the same filter (now also: prototype, hardware, interceptor, survivability,
  integrated with, architecture). Nothing else of Scope; never Targeted types of activities.

## 2. What changed

| # | Item | Change | Test |
|---|---|---|---|
| 1 | Summary filter | `dgate/topic_summary.py`: HTML to blocks, only the blocks under an Objective / Expected outcome heading (at the start of a block, with or without a colon, on its own line or with its text); bullets become sentences, lead-ins ending in ":" dropped. A sentence is kept only if it has a purpose word (aim, support, develop, strengthen, industry, SMEs, capability, procurement...) and **no** figure (any digit except a year; %), **no** specification word (range, payload, accuracy, resolution, frequency, bandwidth, latency, performance, endurance, speed, altitude, specification, requirement, shall, calibre, armour, design, architecture, algorithm, TRL / technology readiness, ... plus WP-90's `_TECHNICAL` words), **no** named system (an acronym not on a short list of policy and programme names; Eurodrone, Leopard, Patriot, MGCS ...), no link or address, 40 to 400 characters. At most 3, in text order. Nothing kept: NULL. | `tests/unit/test_wp92.py` (16 kept, 28 dropped sentences with the reason; sections; fail-closed cases; 3-sentence cap) |
| 2 | Connector | `eu_portal.detail_fields` returns `funds_summary`; `db.CALL_DETAIL_FIELDS` writes it on every topic-details run (`update_call_details`). | unit `test_the_connector_stores...`; integration `test_the_topic_details_step_stores_the_summary` |
| 3 | Backfill | `python -m dgate.ops.funds_summary` (report) / `--yes` (write): reads the topic document each call was last built from (`raw_ingest` by `details_hash`) from the raw store; touches `funds_summary` only, only where it changes; idempotent. Counts: calls, with summary, to write, no description, no raw, failed. | integration `test_the_backfill_...` |
| 4 | API | `/v1/funding/{slug}` `fundsSummary` (detail only), under the same rule as the source's text (`SOURCE_TEXT_SOURCES` and `commercial_ok`), e-mails redacted. Not in lists. | integration `test_the_call_page_serves_...` |
| 5 | Call page | `What it funds: <summary>` and under it "From the topic description; see the full text" (official topic page, new tab). Without a summary the WP-91 line stays (title, keywords, "Read the topic description at ..."). First screen with "Can I apply?" at 375 px (asserted). | `e2e/wp92.spec.ts` |
| 6 | Badge from the call's own facts (coordinator item) | `dgate/who_apply.py`: from the verified eligibility facts of the call document or the topic's own conditions (`eligibility.read_many`; general-annex facts are programme rules and are not used): `sme_only` true -> companies + `sme_only`; an entity type naming a company / private / any legal entity -> companies; every entity type a public body (procurement agencies, ministries, contracting authorities, public authorities) -> public; otherwise nothing stored. Stored in `call.who_may_apply_doc`, `sme_only`, `who_may_apply_evidence` by the nightly cascade-flags job and `python -m dgate.ops.cascade_flags --yes`. `funding.WHO_MAY_APPLY` = `COALESCE(c.who_may_apply_doc, <programme rules>)`, so the badge and the `who` filter read the same answer. Wording unchanged ("Companies can take part" / "Public buyers only"); an SME-only call adds the tag "SMEs only" (`smeOnly`) on the card and the call page. A mandatory consortium and its country composition stay in "Can I apply?" (unchanged, WP-91 `applySummary`). | unit (16 cases of `decide`); integration `test_the_badge_follows_the_call_document_...`; `e2e/wp92.spec.ts` SME card |

Demo data (`lib/mock/calls.json`): call 4 (EDF SSA) and call 11 (Digital AI) carry a summary; call 3 (EDF SME open call) is
SME-only by its document. Call 6 (USI) keeps no summary, so WP-91's test of the fallback line stands.

## 3. Sentences from the fixtures

Kept (15 of 21; `topic_summary.sentences` over `eu_topic_descriptions.json`):

| Topic | Sentence |
|---|---|
| EDF-2026-RA-SENS-MSDT | The aim is to strengthen the European defence technological and industrial base in the field of passive surveillance. |
| EDF-2026-RA-SENS-MSDT | Proposals are expected to foster cooperation between industry, research organisations and SMEs across Member States. |
| EDF-2026-RA-SENS-MSDT | The topic contributes to the CARD focus area on enhanced military mobility. |
| EDF-2026-DA-GROUND-FCV | The objective is to develop the next generation of ground combat capabilities in a cooperative way between Member States. |
| EDF-2026-DA-GROUND-FCV | Proposals should enable European industry to deliver interoperable solutions to the armed forces of several Member States. |
| EDF-2026-DA-GROUND-FCV | Participating SMEs are expected to gain access to new supply chains. |
| EDF-EDIP-USI-2026-SCS | The objective of this topic is to increase the production capacity of the Ukrainian defence industry and its integration into the European defence technological and industrial base. |
| EDF-EDIP-USI-2026-SCS | Actions should support cooperation between Ukrainian and EU companies in ramping up manufacturing of defence products. |
| EDF-EDIP-USI-2026-SCS | The topic also aims to secure supply chains for critical raw materials used by the defence industry. |
| EDIP-2026-CPA-AIRDEF | This topic will support the common procurement of air defence products by consortia of Member States. |
| EDIP-2026-CPA-AIRDEF | It aims to reduce fragmentation of demand and to improve the security of supply of the European defence industry. |
| HORIZON-CL3-2026-01-DRS-01 | Improved preparedness of first responders and civil protection authorities for large-scale disasters. |
| HORIZON-CL3-2026-01-DRS-01 | New market opportunities for European SMEs in the civil security sector. |
| HORIZON-CL3-2026-01-BM-02 | The project is expected to strengthen the competitiveness of the EU security industry. |
| DIGITAL-2026-AI-01 | The objective is to deploy trusted artificial intelligence testing facilities that support SMEs and start-ups in bringing products to market. |

Dropped (15 of 24, with the reason):

| Topic | Sentence | Reason |
|---|---|---|
| EDF-2026-RA-SENS-MSDT | The objective of this topic is to support research on multi-static detection techniques for European armed forces. | specification |
| EDF-2026-RA-SENS-MSDT | The detection range should exceed 150 km against small targets. | figure |
| EDF-2026-RA-SENS-MSDT | The resulting solutions should reach TRL 4 at the end of the project. | figure |
| EDF-2026-RA-SENS-MSDT | Sensor accuracy and latency must be improved over current systems. | specification |
| EDF-2026-DA-GROUND-FCV | The vehicle should reach a top speed of 90 km/h. | figure |
| EDF-2026-DA-GROUND-FCV | The armour level must be compatible with STANAG 4569 level 4. | figure |
| EDF-2026-DA-GROUND-FCV | The design of the turret should allow modular integration. | specification |
| EDF-2026-DA-GROUND-FCV | The project builds on the work of MGCS and Leopard upgrade programmes. | named system |
| EDF-EDIP-USI-2026-SCS | Applicants should increase output by 30% within 24 months. | figure |
| EDIP-2026-CPA-AIRDEF | Patriot and IRIS-T SLM batteries are eligible products. | named system |
| HORIZON-CL3-2026-01-DRS-01 | Projects' results are expected to contribute to some or all of the following outcomes: | fragment |
| HORIZON-CL3-2026-01-DRS-01 | An operational resolution of 10 cm per pixel. | figure |
| HORIZON-CL3-2026-01-BM-02 | Contact the helpdesk at info@example.eu. | link |
| DIGITAL-2026-AI-01 | The facilities should be open to companies from every Member State on fair terms. | unclassified |
| EDF-2026-RA-NAVAL | The project should aim for a payload capacity of at least one tonne. | specification |

Real first Scope sentences of 2026 EDF topics (production probe; `REAL-` fixtures, markup `topicdescriptionkind`):

| Sentence | Verdict |
|---|---|
| The objective of this topic is to follow up and complement previous activities in the field of smart technologies for next generation fighter systems. | **kept** (the call's whole summary; the second Scope sentence is not read) |
| The aim of this topic is to follow up and complement previous activities in the field of the next generation self-protection systems in order to increase the survivability of fixed wing and rotary wing, combat or non-combat aircraft in hostile environment. | dropped: specification (survivability) |
| This topic aims to follow up and complement previous activities for the development of an endo-atmospheric interceptor by maturing key technologies required to successfully counter hypersonic and ballistic threats up to TRL 6. | dropped: figure (TRL 6) |
| This topic aims to develop a prototype of a semi-autonomous remote management system, integrated with adaptive hardware that continuously learns. | dropped: specification (prototype, integrated with, hardware) |
| Military operations require higher flexibility and mobility to gain and maintain the initiative. | dropped: not an aim sentence (and an aim sentence after it in Scope is not read) |

Never read at all (Scope beyond an EDF / EDIP aim opening, Functional requirements, Types of activities, Expected impact): e.g. "The system shall operate in the
2-4 GHz band.", "the system should be able to track at least 50 objects simultaneously", "Procurement of systems with an
engagement range of 40 km or more." Two fixtures give no summary: a description with no heading, and an objective written under
"Functional requirements".

## 4. Tests

Local, `D:\DEFENCEGATE TESTS\wp92` (own venv, Python 3.11; Postgres 17 container `dgate-wp92` on 55492; TZ=UTC; web mock
env; E2E_PORT 3092; Playwright 4 workers), final code:

| Check | Result | Time |
|---|---|---|
| ruff | All checks passed | |
| unit (`pytest`) | **3384 passed** (78 new in `test_wp92.py`, after the real-markup change) | 20 s |
| integration (`pytest -m integration`) | **1258 passed**, 0 failed (5 new in `test_wp92.py`), full run before the real-markup change; after it `test_wp92`, `test_wp19`, `test_wp31`, `test_wp91`: 64 passed | 11 min 47 s |
| `tsc --noEmit` | exit 0 | 11 s |
| `npm run check` | all ok | 118 s |
| `next build` (mock) | exit 0 | 52 s |
| Playwright, desktop + 375 px | **688 passed, 56 skipped**, 0 failed (3 new tests x 2); after the real-markup change (backend only) `wp92` + `wp91` specs: 34 passed | 3 min 30 s |

The first Playwright run failed the new call-page test on its own assertion (the link's screen-reader text "at EU Funding &
Tenders Portal (opens in new tab)" sits before the final full stop); the assertion was corrected, the page was not changed, and
the full suite was run again with the result above. No test deleted, skipped or weakened; `addopts` untouched.

Screenshots, `docs/verification/product/wp92/` (demo data, 1280 and 375 px, from `wp92.spec.ts` with WP92_SHOTS):
`call-what-it-funds` (the summary and "Can I apply?" on the phone's first screen), `funding-sme-only`.

## 5. Limits and open points

- The filter is deliberately strict: a purpose sentence with a number word plus a unit word ("one tonne") is caught only by the
  specification word next to it; a sentence with an unlisted acronym is dropped even when harmless. Fewer summaries, never a
  technical one. Ceiling: word lists, not a model; widen `ACRONYMS_OK` / `PURPOSE_WORDS` from the backfill report if too few pass.
- On production most EDF 2026 topics will have no summary: their only candidate is the first Scope sentence, and real ones
  often name a technology (interceptor, prototype) or a TRL. The backfill report gives the count before anything is written.
- `who_may_apply_doc` is only as good as the extracted `entity_types`; an entity list the rules cannot place (universities only,
  "Member States") stores nothing and the programme rules decide.
