# WP-91 self-check: the funding path (UX audit of 22 October 2026, section 6)

Branch `wp-wp91` from `wp-wp90` (2795f32, integration plus WP-90). Persona Piotr: founder of a 15-person Polish drone-software
start-up (audit dumps and screenshots in `D:\DEFENCEGATE TESTS\ux-oct22\funding\`). Owner priorities: usability, completeness,
correctness. Not changed: WP-87's numbers logic (the list, its counts and its order go through `list_funding` as before; the new
filter is one more clause), WP-88's copy rules (one sentence before content, method collapsed, attribution on screen), /privacy,
/terms. Commercial information only: "What it funds" is the title and the source's topic keywords, no description or
specification is stored or served. **Migration 0107** (`project_topic_search.sql`: a stored generated column and a trigram
index on `project`; additive). No deploy, no push, no production read or write, no secret, no model call, no external request.

## 1. What changed, item by item

| # | Audit finding | Change | Test |
|---|---|---|---|
| 1 | /funding?country=PL "No calls match" (dead end) | An empty Open or Closing-soon list reads the same filters with status Opens soon and Closed (3 each) and shows them under one sentence: "No open calls in Poland now; next expected: "...", opens 3 Nov 2026." or "...; the latest that closed is ..." (`lib/funding-path.ts emptyLine`), with links to all of each. Chips: every entry chip (two added: "EDIP USI (Ukraine)", "Open to companies") lands on calls or on that block. | `wp91.check.ts` §1; `wp91.spec.ts` empty list, every chip |
| 2 | Call page first screen: what it funds; "Can I apply?" for my country; never "Consortium required: No" when a partner country is required; Ukraine territory note only for UA; phone above the fold | **What it funds**: SEDIA's topic description (ExpectedOutcome/Objective) is **not stored** (the connector keeps conditions, budget line, tags, documents; `sources/eu_portal.py detail_fields`), so the header says the title and the source's topic keywords and links "Read the topic description at <source>" (the topic page). **Can I apply?** (`components/funding/apply-summary.tsx`, `applySummary`): the API's rules block now carries `byCountry`, the engine's own outcome of each establishment rule for one country of each group (EU, EEA EFTA, UA, other) with only the country and the kind of action known (`rules_apply.by_country`), and `forCompany` (the EDIP who-may-apply rules for a company). Country from the saved profile or a select in the box, nothing sent. From Poland on a USI call: "only together with a partner established in Ukraine, with its executive management there" (USI-INVOLVES-UA, unknown on `ua_partner`, never a yes); from the US: "you cannot apply"; a CPA call: "Companies cannot apply to this call. Who may apply: ..."; no encoded rules and no facts: "check the official call text". The call document's consortium fact `false` with a single-applicant condition or a Ukrainian-partner condition prints "Not for every applicant. ..." (`factDisplay`), never a bare "No". The NGCA sentence: in the summary for UA only (the rule applies only there), in the Ukrainian participants panel only for a saved UA profile (`UkraineOnly`), and cut from the eligible-countries note of the facts list for any other country. The box is in the page header: above the fold at 375 px (asserted). | `test_wp91.py` (unit) country groups; `test_wp91.py` (integration) rules block; `wp91.check.ts` §2; `wp91.spec.ts` call page (PL, UA, US, CPA) |
| 3 | List says EDF for EDIP USI calls; /regulation vs /funding | `programme_of(code, topic)` reads `regime.regime_of`: EDF-EDIP-USI- topics are `EDIP-USI` (label "EDIP USI"), EDF-EDIP-P- topics `EDIP`, in lists, badges, cards, calendar and follows (`accounts._programmes`). Filter: `programme=EDIP-USI` (its own checkbox), `EDIP` = EDIP topics incl. USI, `EDF` unchanged (every call the portal files under it, the chip "EDF and EDIP"). Regulation seed (and its mock copy): the EDF entry adds that USI calls are another instrument, labelled EDIP USI and marked open to Ukraine; the USI entry links `/funding?status=all&programme=EDIP-USI`. Glossary USI entry updated. | integration labels + filter + follows; `wp91.check.ts` §3; `wp91.spec.ts` USI label |
| 4 | "software", "autonomy", "SME", "EUDIS" give 0 | The search reads the source's topic keywords too (EU portal tags, NCBR thematic areas, BDNS sectors) and the word SME where the portal flags the topic (`funding.SEARCH_TEXT`). New synonym rows (same table in Python and TS, held equal by `wp91.check.ts`): software/algorithms/computing/data fusion/simulation; autonomy/autonomous/uncrewed/robotic/robotics/swarm; ai + machine learning; cyber/cybersecurity/cyber security/cyber defence; sme/smes/small and medium/pme/pyme/msp. EUDIS: no source in the repository names it, so the empty result says it is not a programme we collect, without a link. "Open to SMEs/companies": see 5. | unit synonyms; integration search; `wp91.spec.ts` search |
| 5 | Who may apply on cards; filter | `whoMayApply` (one SQL expression, `funding.WHO_MAY_APPLY`, read by the card and the filter): `public` for the EDIP actions of common procurement, SEAP support and project preparation (rules EDIP-CPA/SEAP/PREP-APPLICANT, tokens of `regime.action_of`); `companies` for any other EDF/EDIP call (recipients are legal entities: *-LEGAL-ENTITY rules), a topic the portal flags for SMEs, an NCBR call whose applicant types name SME/micro/large enterprise, a BDNS call whose beneficiaries name companies/SMEs; null otherwise (no badge, never a guess). Badges "Public buyers only" / "Companies can take part"; filter `who=companies|public` ("Who may apply", folded), in saved searches too. | integration who + saved search; `wp91.spec.ts` who |
| 6 | Partners not by topic; Ukraine for USI; organisation search by topic; Ukraine partners default civil | Partners: the organisations whose area projects share a topic word of the call's title (or a synonym; generic words dropped) rank first, then as before; the answer names the words (`area.topicWords`, `topicAlso`, `topicalProjects`, partner `topical`) and the page says so; evidence lists topical projects first. USI calls always offer Ukraine in the country choice (0 when none). /organisations: `topic=` (acronym, title, EDF category of projects; every word in one project; synonyms; ≤3-letter words whole). Ukraine partners: coordinators with defence-programme projects first, then dual-use calls (Horizon CL3/CL4/EIC, H2020 Secure Societies/Digital Security, FP7 Security), then the rest; the order is said on the page. | integration partners, organisations, Ukraine partners, index; unit topic words, relevance; `wp91.spec.ts` |
| 7 | Readiness assumes hardware; "Fits my profile" by topics | Step 1 "What do you offer?"; "software or services" hides the three component questions in step 3 with the reason. **Not "not applicable"**: no rule text supports it (EDIP/USI-ORIGIN-35 and NO-RESTRICTED concern the end product of the action), so those answers are sent as unknown and the rules stay open ("check"); the results say "left open: you make software or services ..." instead of linking a hidden question (`skippedFields`). Topics: "Your topics" under "Fits my profile", kept in the profile (`dg.profile.v1`, additive field, version stays 3), never sent; with the filter on, calls holding more topics come first (CSS order, the rest keeps the server's order) and say "Matches N of your topics". Editing topics does not re-ask the programme verdict. | `wp91.check.ts` §7; `wp91.spec.ts` wizard, results, topics |
| 8 | .ics per call; feed with the list's filters | `/funding.ics?call=<slug>` (deadline, or opening day and planned deadline; closed: 404) and `/funding.ics?<filters of /funding>` (Open/Closing soon: deadlines; Opens soon: openings and planned deadlines; All: both; Closed: 422; an unknown parameter or bad value: 422). One rule for all calendars, `lib/calendar-calls.ts callEntries` (the deadline calendar reads it too). Links: "Add to my calendar (.ics)" on the call page, "Calendar file of this search (.ics)" in the list tools. The file is `/funding.ics`, not under `/funding/`, so no call link is shadowed. | `wp91.check.ts` §8; `wp91.spec.ts` calendar files |
| 9 | /requirements Poland NCAGE unverified | /requirements has "Who issues them in your country" (`?country=`): each document card says "Issued in X by ..." for a verified row, or "Not verified in our sources: we have not confirmed which body issues NCAGE codes in Poland. ..." with "NSPA: request an NCAGE code" (the seed's own `*` row URL), or "not collected". The roadmap shows an unverified issuer the same way instead of "UNVERIFIED: ..."; the NCAGE requirement page links NSPA beside the unverified bureau group. No issuer invented. | `wp91.check.ts` §9; `wp91.spec.ts` requirements |

## 2. The 5 s budget

Measured on synthetic data (database `perf91` in the WP-91 container: 80,000 projects, 400,000 participations, 173,063 directory
rows; API through TestClient, warm, list cache off; word frequencies far above real ones, "drone" or a synonym in ~25 % of titles):

| Request | Before the stored column | Final |
|---|---|---|
| `/v1/organisations?topic=drone` (5 alternatives) | 3.01 s | 0.43 s |
| `topic=drone&page=50` | 2.97 s | 0.44 s |
| `topic=sensor network` | 0.17 s | 0.15 s |
| `topic=resilient&sort=name` | 0.66 s | 0.27 s |
| `/v1/analytics/ukraine-partners?since=2008` (3,970 projects) | | 0.15 s |
| `/v1/funding?q=software&status=all` | | 0.03 s |

The first version folded the text inside the index expression and refolded every candidate row once per alternative in the
recheck (1.35 s of the 1.6 s); 0107 stores the folded text as a generated column. Partners rank at most 600 area projects in
Python (unchanged ceiling).

## 3. Tests

Local, `D:\DEFENCEGATE TESTS\wp91` (own venv, Python 3.11; Postgres 17 container `dgate-wp91` on 55491, recreated after 0107
changed; TZ=UTC; web mock env; E2E_PORT 3091; Playwright 4 workers), final code:

| Check | Result | Time |
|---|---|---|
| ruff | All checks passed | |
| unit (`pytest`) | **3306 passed** (8 new in `test_wp91.py`) | 25 s |
| integration (`pytest -m integration`) | **1253 passed**, 0 failed (11 new in `test_wp91.py`) | 10 min 3 s |
| `tsc --noEmit` | exit 0 | 10 s |
| `npm run check` (43 files with `wp91.check.ts`) | all ok | 102 s |
| `next build` (mock) | exit 0 | 44 s |
| Playwright, desktop + 375 px | **682 passed, 56 skipped**, 0 failed (14 new tests x 2) | 2 min 11 s |

Rewritten (no test deleted or skipped): `test_wp32.py` `PARTNER_KEYS` adds `topical` (a new organisation-level field; the
no-contact assertion stays). Demo data: call 6 is now a Ukraine Support Instrument topic (EDF-EDIP-USI-2026-SCS), call 21 an EDIP
common-procurement topic, two calls carry the SME flag. Earlier runs failed on: call links picked by `a[href^="/funding/"]` (the
first ics route was under /funding/: moved to /funding.ics), `LS-IRA` in a demo call ID (WP-88's term list), the folded funding
filter form 58 px over its 1,700 px limit (the new group folds, the search hint is shorter), the org filter object shape
(`topic` only when set). Two environment failures (ERR_NETWORK_CHANGED, ECONNRESET) did not recur.

Screenshots, `docs/verification/product/wp91/` (demo data, 1280 and 375 px, from `wp91.spec.ts` with WP91_SHOTS):
`funding-empty-country`, `funding-usi-label`, `funding-who`, `call-can-i-apply`, `organisations-topic`, `readiness-software`,
`requirements-poland`.

## 4. Open decisions for the owner

- **Topic description (ExpectedOutcome/Objective)**: not stored. Storing it needs the connector to keep `description` from the topic
  details (the same request it makes) and a filter like WP-90's commercial subject, since the text mixes outcomes and technical scope.
  Until then the page links the topic text.
- **"Companies can take part" for every EDF/EDIP call** other than the three public-only actions rests on the regulations' legal-entity
  rules, not on each call document; a USI call from Poland still needs a Ukrainian partner (the summary says so).
- **Software branch**: the component rules stay "check" for a software company; the owner may decide a stated rule that they do not
  apply to a pure software or services supplier, with a source.
- **Synonyms and the dual-use call prefixes** (Ukraine partners order) are our lists; say if a row should change.
- **Programme follows**: an EDIP or USI call's Follow button now follows `EDIP` / `EDIP-USI`; follows of `EDF` made before keep the
  EDF count, which no longer includes those calls.
- **0107** adds a generated column to `project` (a table rewrite on apply; the table is about a hundred thousand rows).
