# WP-36 self-check: rules that apply, open to Ukraine, regulatory tracker, data sovereignty

Author: implementer wp36, 18 October 2026, branch `wp-wp36` (from `integration` at 26898fc). Written by the author of
the change: an independent verifier is to check it again. A criterion that was not met is listed as not met.

## What was built

- `dgate/regime.py`: the regime of a funding call from its programme and topic code (`EDF`, `EDIP`, `EDIP-USI`,
  `HORIZON`, `DIGITAL`, `CEF`, `NATIONAL`). `dgate/rules_apply.py`: the "Rules that apply" block (headline rules of the
  regime from the readiness seed, each with its verbatim source). Served as `rulesApply` on `GET /v1/funding/{slug}`.
- `dgate/ukraine.py` + migration `0076_call_open_to_ukraine.sql` + `python -m dgate.ops.ukraine_flags`: the derived flag
  `call.open_to_ukraine` (true / false / null) with reason and evidence, filled in the nightly cascade job (no new job:
  the pinned job list is untouched). API: `ukraine=true` filter, `openToUkraine`, `ukraineTotal`, `ukraineBasis`.
- `dgate/regulation.py` + migration `0077_regulation_tracker.sql` + `seeds/regulation_tracker.json` (16 entries) +
  `GET /v1/regulation`; the worker applies the seed on start (`ensure_regulation`). `tests/verify_regulation.py` checks
  every quote against the source text.
- Web: panels "Rules that apply" and "Ukrainian participants" on `/funding/{slug}`, filter and badge on `/funding`,
  glossary entry `open-to-ukraine`, `/regulation`, `/regulation.atom`, `/data/sovereignty`, sitemap entries, mock data.
- Tests: 51 unit test cases (`tests/unit/test_wp36.py`, 35 functions), 14 integration tests (`tests/integration/test_wp36.py`), a web
  self-check (`lib/regulation.check.ts`), 6 Playwright tests (`web/e2e/wp36.spec.ts`).
- Touched files of other packages, additively: `funding.py` (fields, one filter, the two counts), `accounts.py` (one
  keyword), `api.py` (one router), `worker.py` (one call in the cascade job, `ensure_regulation`), `infra/Caddyfile` (one
  path), the call page, `filters.ts`, `types.ts`, `filter-bar.tsx`, `cards.tsx`, `glossary.ts`. The readiness seed
  (`requirements.json`) and the eligibility code are not touched.

## Test results (on the server, test database `agent_p`)

- Web: `tsc --noEmit` clean; `npm run check` ok (13 self-checks, 1 new).
- `ruff check .`: clean.
- Unit suite: **2279 passed, 0 failed** (51 of them new), run on the branch; the tracker seed and its mock were regenerated afterwards (one source reference) and `test_wp36.py` re-run: 51 passed.
- Integration, new file: **14 passed**. A targeted run of the new file and the files that touch the same code (`test_wp31`,
  `test_funding_api`, `test_accounts`, `test_readiness_api`, `test_security_hardening`, `test_calls_api`,
  `test_list_cache_and_scope`, `test_health`): **228 passed, 1 failed**. The failure is
  `test_security_hardening.py::test_the_rate_limit_answers_429_with_a_wait_and_leaves_the_probe_alone`, the load-sensitive test
  that WP-29 recorded as failing the same way on unmodified `integration` (it sends 135 requests and expects the bucket to run dry;
  the server's load average was 11 to 50). The backup test (`test_the_worker_role_can_read_every_table_so_pg_dump_can`) passes
  with the new table. The full integration suite did not finish (below).
- Quotes of the tracker: `python tests/verify_regulation.py regulation_tracker.json <dir>`: **16 of 16 found** word for
  word in the Official Journal texts (CELLAR), the Legislative Observatory page and the two Commission pages.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Every tracker entry confirmed or excluded with the evidence | Met | the two tables below |
| Ukraine verdicts hand-checked | Met, 30 rows | the table below |
| Regime mapped on all 193 calls, the unmapped listed with the reason | Met | below |
| Sovereignty page matches what was measured | Met | below |
| Page timings under 1.5 s cold | **Partly** | API timings measured; the new pages were not built on the server (see below) |
| Tests: unit and integration for every item, e2e for the filter, `/regulation` and the call block | Written; e2e **not run** | `web/e2e/wp36.spec.ts` was not run (no browser on the server: memory) |

### The regime of the 193 calls (production, 18 October 2026)

`tests/unit/test_wp36.py::test_every_one_of_the_193_calls_has_a_regime_and_the_counts_are_these` reads the programme and
topic code of every non-suppressed call (`tests/fixtures/calls_programme_topic.json`, taken from production).

| Regime | Calls | Rules in the block |
|---|---|---|
| EDF | 28 | EDF-ESTABLISH, EDF-EXEC-MGMT, EDF-CONTROL |
| EDIP (topic `EDF-EDIP-P-`, filed under the EDF by the portal) | 10 | EDIP-ESTABLISH, EDIP-EXEC-MGMT, EDIP-CONTROL, and the 35 % component rule of Article 10(3) as "also read" |
| EDIP Ukraine Support Instrument (`EDF-EDIP-USI-`) | 2 | USI-ESTABLISH, USI-EXEC-MGMT, USI-TERRITORY, USI-CONTROL, and the 35 % rule of Article 27(3) as "also read" |
| Horizon Europe | 67 | none: named, "no rules of this regime are encoded" |
| Digital Europe | 51 | none |
| National (FR-AID 15, PL-NCBR 7, SE-VINNOVA 7, ES-BDNS 4, FI-MATINE 1) | 34 | none |
| CEF | 1 | none |

No call maps to no regime at all (0 of 193). The 153 calls of Horizon, Digital Europe, CEF and the national programmes name a
regime but list no rules, because the readiness seed holds none for them (the seed has EDF, EDIP, USI, SAFE, NATO supply and
general rules) and this package does not invent any. SAFE has no funding calls (a loan instrument for Member States), so
no call is under it. The `EDF-EDIP-P-` and `EDF-EDIP-USI-` mapping was checked against the call documents of calls 93, 108,
113 and 118: the EDIP document lists "EU Member States and EDIP associated countries", the USI documents list Ukraine.
The existing readiness `call` assessment maps a call by `programme.code` only, so an EDIP or USI call is assessed against the
EDF rules there; that is not changed here and is reported as a finding.

"Design authority": the seed has no such rule, and nothing is shown for it. The origin share (35 %) of EDIP and USI is not in
the seed either (verifier finding D1 of `verify-readiness.md`): it is shown from `regime.ALSO_READ`, with the sentence of
Regulation (EU) 2025/2643 Article 10(3) / 27(3) copied from the Official Journal text, and only while the seed has no rule of kind
`threshold` for the regime (a test pins that).

### The Ukraine flag on real data (a scratch copy of production in `agent_p_real`)

All 193 calls decided: **3 yes, 10 no, 180 unknown**; a second run changes 0 rows.

| Result | Calls | Reason |
|---|---|---|
| yes | 113 | `call_document`: the verified fact lists "non-EU countries: − Ukraine" |
| yes | 118 | `programme_rule`: Article 26(1) of Regulation (EU) 2025/2643 (the document also lists Ukraine, with the territorial exclusion; that sentence is skipped on purpose) |
| yes | 131 (HORIZON-EIC-2026-DEFENCE-01) | `topic_text`: "established in the Union, in Ukraine or in an EEA member associated to Horizon Europe" |
| no | 10 EDIP calls (108-112, 114-117, 193) | `programme_rule`: Article 2 defines associated countries as EEA EFTA states |
| unknown | 28 EDF calls | `edf_association_unconfirmed` |
| unknown | 152 others | `not_stated` |

Hand check of 30 calls (evidence read by me; "agrees" = my reading of the stored evidence gives the same answer):

| Calls | Stored answer | Agrees | Note |
|---|---|---|---|
| 113, 118 | yes | yes, yes | |
| 131 | yes | yes | the only Horizon call whose held text names Ukraine |
| 108, 109, 110, 111, 112, 114, 115, 116 | no | yes x8 | the documents list "EDIP associated countries (i.e. Norway)" and never Ukraine. The Commission's page on support to Ukraine says Ukraine "has been fully associated ... to the European Defence Industry Programme"; the Regulation's definition of associated countries and Article 26 do not, so the sentence on the page says only that the regulation does not list Ukraine and that the Ukraine Support Instrument serves Ukrainian entities |
| 79, 80, 81, 82, 83, 84, 85, 86 | unknown | yes x8 | "countries associated to the EDF Programme" without naming any |
| 32, 41, 50, 59, 128 | unknown | yes x5 | Horizon texts say "Associated Countries" without a list; Ukraine is in reality an associated country to Horizon Europe, but no text we hold says so, so it is not marked |
| 4, 5, 6, 18 | unknown | yes x4 | Digital Europe: no fact, or "countries associated to the Digital Europe Programme" |
| 156, 157 | unknown | yes x2 | national (ES-BDNS): nothing stated |

30 of 30 agree. What this does not show: unknown is the answer for 180 calls, many of which are probably open in fact
(Horizon: Ukraine is an associated country, topic restrictions aside). That is the price of "only what we hold says so".
Under-detection that I found and left: call 32 limits participation to Member States and associated countries without naming
Ukraine, which could be read as "no"; it stays unknown.

### The tracker: every claim of the analysis, confirmed or excluded

| Claim of `EUROPEAN_AUTONOMY_ANALYSIS_2026-10-18.md` | Result | Evidence |
|---|---|---|
| SAFE, Regulation (EU) 2025/1106, in force 29 May 2025 | Published | OJ L 28.5.2025, final Article: "the day following that of its publication" |
| SAFE: at most 35 % of component cost from outside the Union, EEA EFTA and Ukraine; categorical exclusion | Published | Article 16(10), verbatim; two rules |
| SAFE Canada: agreement signed February 2026 | Published | Decision (EU) 2026/1381, recital 1: signed 14 February 2026, provisionally applied from 13 April 2026 |
| SAFE Canada: "Council approved 19 December 2025" | **Not published** | the 15 June 2026 decision is the Council's conclusion (OEIL 2025/0413(NLE): Parliament consent 20 May 2026, Council 15 June 2026, OJ 18 June 2026). A Council press release of 19 December 2025 is headed "member states endorse"; that page and the 2026 releases refuse automated access (Cloudflare challenge), so I did not read them and did not circumvent it |
| SAFE UK: "talks broke down in November 2025" | **Not published** (entry `safe-uk-unconfirmed`, status unconfirmed) | only the authorisation of 18 September 2025 is in a primary text; no agreement, signature or statement on the talks found |
| SAFE: Japan applied, Korea and Turkey pending | **Excluded** | no primary text found |
| SAFE: 19 national plans submitted by 30 November 2025 | **Excluded** | the deadline of 30 November 2025 is in Decision 2025/2134; the number of plans is not in a primary text I read |
| EDIP, Regulation (EU) 2025/2643; EUR 1.5 bn, of which EUR 300 m for the USI | Published, corrected | Article 3: EUR 1 200 000 000 for the Programme and EUR 300 000 000 for the Ukraine Support Instrument (1.5 bn in all, not 1.5 bn with 0.3 bn inside it) |
| EDIP: at least 65 % of components from the EU or associated countries | Published as 35 % | Article 10(3) and (4); for the USI Article 27(3) and (4) |
| EDIP: control Article 9(5)/(6) | Not repeated | already a rule of the readiness seed, verified by the independent verifier |
| USI: Ukraine counts as EU | Published | Article 26(1); Article 27(8) |
| EDF, Regulation (EU) 2021/697, control rules Article 9(4) | Not repeated | already a rule of the readiness seed |
| EDF: Ukraine's association agreement signed July 2026, ratified by the Rada on 16 September | **Not published as facts** | only press and law-firm pages; stated in the entry as "reported", with no date |
| EDF: entry into force not confirmed | Published (`edf-ukraine-in-force-unconfirmed`, unconfirmed) | the Commission's undated page says "has been fully associated"; no Official Journal text, Council decision or notice of entry into force found |
| EDF: Ukraine can be an associated country | Published | Regulation (EU) 2025/2653 Article 1(1), replacing Article 5 |
| Omnibus: proposal 17 June 2025, thresholds EUR 443 000 to 900 000 and EUR 5 538 000 to 7 000 000, framework agreements 7 to 10 years | Published as the proposal's figures | COM(2025) 823 final, operative text (Article 8 of the Directive) and the explanatory memorandum |
| Omnibus: provisional agreement 10 June 2026 | **Not published** | the Observatory dates the agreed text 17 June 2026 (Coreper letter); the 10 June date is only in press |
| Omnibus: plenary vote September 2026; adoption unconfirmed | Published, updated | Parliament 16 September 2026, Council 9 October 2026, "Awaiting signature of act" (Observatory); not in the Official Journal yet |
| Omnibus: "European preference" not included | **Excluded** | the adopted text was not compared with the proposal |
| A full revision is announced; applicability around 2028 and 2029-2030 | Announcement published, dates excluded | DEFIS page of 25 November 2025: "the Defence Readiness Roadmap of October 2025 announced the upcoming revision of the legal framework" |
| TED covers about 10 % of defence spending (ECIPE); 80 % direct awards (Kubilius); BT-7220 codelist; licences; competitors; EUDIS | **Not tracker material** | not a regulatory change; not checked against a primary text |
| Export control rules already in the requirements seed | Published | Regulation (EU) 2021/821 Article 3(1); in force 9 September 2021 (ninetieth day after 11 June 2021) |

### The sovereignty page against what was measured (18 October 2026)

| Statement on the page | Measured |
|---|---|
| Server at Hetzner, Helsinki, Finland | the server's address (omitted here, WP-39): RIPE netname CLOUD-HEL1, AS24940 Hetzner Online GmbH, FI, Helsinki; reverse name `your-server.de`; the privacy notice says the same |
| Storage Box in Germany | the box's host name (omitted here, WP-39: the box is shared with another project) resolves to an address in RIPE DE-HETZNER, Gunzenhausen DE (an address range, not a statement from Hetzner about the data centre; the page says so) |
| Production writes the archive to the Storage Box only | `DGATE_RAW_BACKEND=sftp`, `DGATE_S3_ENDPOINT` empty in the worker container |
| Cloudflare is registrar and DNS, not a proxy | RDAP of the domain: registrar Cloudflare, Inc.; NS lola/ram.ns.cloudflare.com; the A record is the Hetzner address itself (not a Cloudflare range); no MX, TXT or AAAA record |
| Let's Encrypt issues the certificate | `openssl s_client` on the server: issuer Let's Encrypt (CN=YE1), valid 12 October 2026 to 10 January 2027 |
| The code is in a public GitHub repository; the server's copy has it as origin | `api.github.com` anonymous: `private: false`; `git remote -v` on the server |
| OpenAI reads public call documents; store off; capped | `dgate/llm.py`: `store: False`, URL `api.openai.com/v1/responses`, monthly cap; the worker has the key set (value not read); model `gpt-6-luna` |
| Telegram receives operator alerts | worker has `DGATE_TELEGRAM_TOKEN` and chat id set (values not read); no healthchecks.io base, no SMTP host set |
| No third-party request from the browser | browser trace of the home page (17 resources) and of `/funding/118-...` (20 resources): the only host is `defencegatehub.com`, 0 cookies; the HTML names no resource from another host; the content security policy allows own-origin only |
| Fonts are copied into the build | `next/font/google` in `app/layout.tsx` downloads them at build time on the server |

Findings for the owner that the page does not decide: the privacy notice (section 8) says no personal data leaves the
EEA "apart from the domain name service", and does not name OpenAI or Telegram; what OpenAI receives is public call
documents, but the lawyer should see it (`docs/legal/OPEN_ITEMS_FOR_LAWYER.md`). The code repository is public and holds the
internal documents under `docs/`. Whether the earlier raw archive in Cloudflare R2 (the code still supports it) was deleted is
not known to me.

### Timings

On a scratch database holding a copy of production's 193 calls, 102 eligibility readings and the seeds (the server's load
average was 30 to 50 during the runs, other implementers' suites running; figures include the test client):

| Endpoint | Median | p95 | Size |
|---|---|---|---|
| `GET /v1/funding?status=all&pageSize=10` | 661 ms | 796 ms | 16 KB |
| `GET /v1/funding?status=all&ukraine=true` | 522 ms | 787 ms | 4 KB |
| `GET /v1/funding?status=open` | 405 ms | 445 ms | 16 KB |
| `GET /v1/funding/113` (USI, with the block) | 240 ms | 316 ms | 14 KB |
| `GET /v1/funding/79` (EDF) | 212 ms | 283 ms | 14 KB |
| `GET /v1/funding/1` (Horizon, no rules) | 244 ms | 331 ms | 17 KB |
| `GET /v1/regulation` | 257 ms | 344 ms | 21 KB |
| first detail request after the rules cache was cleared | 331 ms | | |

`EXPLAIN (ANALYZE)` of the added count (`open_to_ukraine IS TRUE`): index scan on `call_open_to_ukraine`, execution 0.2 ms;
the existing cascade count 2.3 ms. The API role's budget is 5 s. The list now runs four count/row queries instead of three.
Pages: the new pages were not built on the server. For reference, the deployed call page `/funding/118-...` reached
`responseEnd` in 1.35 s in the browser on 18 October (cold, loaded server); the new panels add about 3 KB of HTML to it.

## Hostile review of my own diff

12 issues found and fixed:

1. The Ukraine reading ignored a bare list item ("− Ukraine") because the sentence had no eligibility word: a unit test caught
   it; a fact that is already about eligible countries now counts its list items.
2. `cascadeTotal` did not follow the new filter (and `ukraineTotal` would not have followed the cascade filter): both counts are
   now computed with the other filter applied (a test pins it).
3. The sentence for an EDIP call said "Ukrainian entities may not take part", more than the evidence shows (the regulation does
   not list Ukraine; the Commission's page speaks of association to EDIP): it now says that, and that the USI serves Ukraine.
4. The tracker entry on the EDF said "reports in the press describe ratification": a press claim in a tracker that excludes
   press claims; reworded to say that steps taken in Ukraine do not settle the EU side.
5. The tracker's directive entry had a sentence about the Parliament's resolution I had not read; removed.
6. `linkHref` sent a programme link to `/readiness?programme=...`, a parameter the wizard does not read: now `/readiness`.
7. My quote check dropped punctuation (a replacement string lost its escape) and then failed on "Union ." of the Official
   Journal text: fixed and re-run, 16 of 16.
8. A call text that mentions Ukraine without being about participation ("support the reconstruction of Ukraine") would have
   flagged a call: an eligibility-word test and a unit test.
9. A document that names topics (several topics in one PDF) could set the flag for a topic it does not name: the topic code decides.
10. The first draft of the sovereignty page said "the server takes its code from GitHub"; I only know the server's copy has
    GitHub as origin: reworded.
11. The sovereignty page did not mention that OpenAI also receives a topic's published conditions text, not only PDFs: added.
12. The mock data first reformatted the whole `calls.json`; reverted and edited in place (4 lines).

## Could not check, and not met

- **The Playwright specs were not run** and `next build` was not run (a browser and a build need about 1 GB; the server had 100 MB free
  with five suites running). `tsc --noEmit` is clean and `npm run check` passes (13 self-checks, the new `regulation.check.ts`
  among them), run in a container with 1.1 GB. I read the markup against the locators; expect to adjust one in CI.
- **The full integration suite did not finish on this server** (five other implementers' full suites were running against the same
  database server; 36 tests in 40 minutes, so I stopped it and ran the 9 files above). The other 58 files were not run here;
  CI runs them.
- The 35 % component rule of EDIP and USI is shown but not part of the readiness check (the seed holds no rule for it).
- No Official Journal text of the EU-Ukraine EDF agreement, no notice of entry into force of the SAFE-Canada agreement and no text
  on the UK talks were found; the Council's press pages cannot be read by a program. The three points are in the tracker as unconfirmed or as
  "we have not found".
- The browser's network trace was done with the performance entries of the page (all resources of the load), not with a recording of
  every request including those blocked by the policy; the policy itself and the HTML were read as well.
- Nothing was written to production. Scratch removed at the end: database `agent_p_real` (a copy of production's `programme`,
  `source`, `call`, `call_eligibility`, `call_document_text`; 7 MB dump), the downloaded Official Journal texts and pages
  (about 15 MB). Kept for the verifier: `/root/dev-p` (16 MB: the branch's backend and web, the scripts, the extracted texts of the sources and
  `/root/run_p.sh`) and database `agent_p`; both are in `docs/DELETION_CANDIDATES.md`.
