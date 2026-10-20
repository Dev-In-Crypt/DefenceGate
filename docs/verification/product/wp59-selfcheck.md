# WP-59 self-check: fixes from the re-audits of 20 October 2026

Branch `wp-wp59` from `integration` at `ac6268d`. Sources: `reaudit-content-brand.md` (NEW-1..14, STILL OPEN),
`reaudit-data-pages.md` (section 6, and F-05), `reaudit-system-a11y.md` (N1, N2), and the coordinator's two follow-up
messages. Nothing deployed or pushed. No model calls, no spending. Production was read only: a few SELECTs
(`statement_timeout` 30 s), `docker logs`, and GET requests to the API inside `dgate-api-1` and to the public site.

## What was done

| Item | Fix | Where |
|---|---|---|
| Content NEW-9 / a11y N1 (footer at 1024-1279 px) | Groups are as wide as their longest label (`auto` columns, one line per link from lg); the brand takes the rest. The long groups are one column from lg to xl and two from xl. | `components/dg/footer.tsx` |
| Content NEW-1 (calendar feed) | Checked /alerts, /about, /terms, /data against the restored `/calendar.ics`: all true again. /alerts now links to the feed (`/calendar#feed-heading`); /calendar says "calendar feed" where it said "calendar file". | `alerts/page.tsx`, `calendar/page.tsx` |
| Content NEW-8 (plurals) | One helper `plural(n, one, many?)` in `lib/format.ts`. Used in 18 count phrases found by grep (list below). The API reason "1 factsheets could not be read" is now "1 factsheet ..." (`funding.run_reason`, old stored messages included). | web, `backend/dgate/funding.py` |
| Content NEW-2 (rule ids) | The two tracker entries name the rule by its title, in the seed and in the mock. A unit test now checks the title is there and that no tracker title, text or "affected" line carries a `XX-YY-NN` id. No other rule id is shown as text (grep of web; the call identifiers on the home page are data). | `seeds/regulation_tracker.json`, `lib/mock/regulation.json`, `tests/unit/test_wp40.py` |
| Content NEW-5 (titles and descriptions cut mid-phrase) | `trimAtPhrase` in `lib/seo-trim.ts`, used by `buildMetadata`: the last whole sentence that fits, else the part before the last colon, semicolon or dash, else before a bracket, else the old cut at a word with "…". A quoted search ("Tenders, page 2: “drone ...”") is never dropped. Requirement pages no longer pre-cut their description at 197 characters. | `lib/seo-trim.ts`, `lib/seo.ts` |
| Content NEW-6 (quotes) | `publicPassage`: a quote that starts in lower case after its label was removed opens with "…"; a quoted table row shows " · " instead of pipes. | `lib/readiness.ts` |
| Content NEW-7 (PIC "same body" plus "not collected") | A row for every country next to country rows is "Every other country"; when one exists the "not collected" sentence is left out (Q&A and the page note). | `lib/readiness.ts`, `requirements/[code]/page.tsx` |
| Content NEW-10 | The cost texts read "USD 17,000 to 48,000", "USD 17,000 to 25,000", "about EUR 15,700 to 44,200", as the card does (seed, mock, e2e fixtures). Verbatim quotes unchanged. | `seeds/requirements.json` |
| Content NEW-12 | Non-breaking space in "(7 September 2026)". | `lib/readiness.ts` |
| Content NEW-13 | Home stamp "Counts as of 20 Oct 2026, 18:25 UTC." (`countsNote`; the tenders list keeps the time only). | `lib/list-count.ts` |
| Content NEW-14 | Header and footer link "Data sovereignty" is now "Where the data runs", the page's own title. | `header-bar.tsx`, `footer.tsx` |
| Data NEW-1 (major: history hides versions) | Cause: WP-52's T12 folded every `remapped` version into the line it corrected, so a correction vanished (notice 6) or rewrote an earlier entry under that entry's date (notice 235: "Open → Cancelled" dated 30 Sep, the Awarded state gone). Now `timeline(rows, corrections=True)` for `/v1/tenders/{slug}/versions` lists a remapped version as its own entry, dated when we re-read it, flagged `correction`; the counts (`versionCount`, `amended`, /changes, the pulse) keep the fold, so a correction is still never an amendment. The site shows "Corrected by DefenceGate on <date>" and one sentence. | `backend/dgate/tenders.py`, `components/dg/version-timeline.tsx`, `lib/types.ts` |
| Data NEW-2 (capped total below a subset) | Cause: in `all`, the open part is collapsed against closed twins (112) and the rest ran out of its time box. A capped `all` total is now at least the Open list's count; an open part whose count timed out no longer counts as 0. | `backend/dgate/tenders.py` |
| Data NEW-3 (TED + German copy side by side in Closed) | Cause: the de_bkms row's `ted_ref` names the newest TED stage (deadline 2 Nov, open); the stage it copies (20 Oct) is closed. A row linked by procedure identifier now gives way to any TED notice of its procedure with its status in the result. Other link methods keep the old rule. | `collapse_clauses` |
| Data NEW-4 | "Your profile does not say whether you already have consortium partners, so that one is yours to answer." | `components/funding/eligibility-check.tsx` |
| Data NEW-5 | "This call falls under a national programme." | `components/funding/rules-apply.tsx` |
| Data NEW-6 | A country code with no name is not put in a title ("Supplier map (filtered)"). | `lib/seo.ts` `listViewTitle` |
| Data F-05 (`/funding?view=calendar` 26 px sideways at 375) | Call titles in the calendar view wrap anywhere (the title of call 153 has U+202F spaces). On production, adding the same rule in the browser took the document from 401 to 375 px. | `components/funding/call-calendar.tsx` |
| a11y N2 (list pages fail under light load) | Buyers, suppliers and organisations now use the WP-49 last-good fallback (`withLastGood`) like tenders and funding, with the same "did not answer in time" note. See the investigation below. | `lib/api.ts`, `lib/networks-api.ts`, three list pages |
| Windows check runner | `scripts/run-checks.mjs` spawns `npx` through a shell on Windows (paths quoted); it checks the same files the same way. | `web/scripts/run-checks.mjs` |

### N2: what the server shows (read only)

- `dgate-web-1` was restarted at **18:58:54 UTC on 20 Oct**, inside the crawl window (the deploy of the restored calendar feed). That explains the 502s on `/calendar` and loses the web log before it; the API (`uvicorn`) and Caddy keep no access log, so the 500s cannot be matched request by request.
- Postgres logged 11 statement timeouts between 18:21 and 19:32: 8 are the time-boxed tender counts (designed, answered "at least"), 3 are long SELECTs of the other audits running at the same time. No "too many connections".
- Now, unloaded: `/v1/buyers?country=DE` 0.77 s cold and 0.03 s warm, `/v1/suppliers?page=2` 0.28 s, `/v1/organisations?page=2` 0.04 s, `?programme=all&sort=defence` 0.12 s, all 200.
- Verdict: load and a deploy during the crawl (infra), plus three list pages that had no last-good fallback (code, fixed). Not fixed in code: an error state still answers HTTP 200. Next.js App Router cannot set a status from a server component (only `notFound()` 404 or a thrown error, which is a 500); a 503 with Retry-After needs a framework workaround (for example a route handler in front of the page) and is an owner or architecture decision. Those pages already send `noindex` when their own metadata fetch fails.

## Strings changed (every one)

- Footer and header link: "Data sovereignty" is now "Where the data runs".
- /alerts: new link "Calendar feed" beside "Atom feed".
- /calendar: "...; the calendar file has the opening days ..." is now "...; the calendar feed has the opening days ...".
- /regulation (seed and mock): "(rule EDIP-ORIGIN-35)" is now "(rule “Components from outside the Union and associated countries: at most 35 % of component cost”)"; "(rule USI-ORIGIN-35)" is now "(rule “Components from outside the Union and Ukraine: at most 35 % of component cost”)".
- /data (API sentence): "1 <things> could not be read; the rest of the run is kept." uses the singular for 1.
- Count nouns now singular for 1 (number formatting unchanged): matches (dashboard, saved searches), deadlines (/calendar), changes (/changes), days / notices (/market, 3 places), participants / countries / months / pages (/projects, 5 places), suppliers / wins / notices (/suppliers), calls (funding list and calendar view), days left (call readiness), organisations / projects (partner suggestions), notices / years (buyer profile, 2 places), entries (/regulation), countries (requirement issuer groups), days (readiness spans), legal entities / countries (eligibility and fit sentences).
- /suppliers: for 1, "1 winner that is a natural person (a sole trader under their own name) is left out." and "(1 group is held back)".
- Requirement Q&A "Who issues ...?": next to country rows, a row for every country reads "Every other country: <body>." and the sentence "The body has not been collected for the countries not listed." is left out when such a row exists; alone it still reads "<body> (the same body for every country)." The page label of that row is "Every other country" next to country rows; the note "For a country that is not listed, the issuing body has not been collected. We list none rather than guess." is hidden when a row for every country exists.
- Cost texts: "USD 17,000-48,000 for ..." is now "USD 17,000 to 48,000 for ...", "USD 17,000-25,000 for ..." is now "USD 17,000 to 25,000 for ...", "about EUR 15,700-44,200, ..." is now "about EUR 15,700 to 44,200, ...".
- "(7 September 2026)": the space is now non-breaking.
- Home: "Counts as of 18:25 UTC." is now "Counts as of 20 Oct 2026, 18:25 UTC.".
- Quotes on requirement pages: a quote that starts in lower case gets a leading "…"; " | " in a quoted table row is now " · ".
- Titles and descriptions: cut at a phrase end, as described above (for example "Requirements for EU defence programmes · DefenceGate", "Readiness check · DefenceGate", "ISO 9001 quality management certificate · DefenceGate"; description of /alerts "E-mail alerts and saved searches are being prepared and are not open yet.").
- Call page "Can you apply?": "Your profile has no question about partners, so that one is yours to answer." is now "Your profile does not say whether you already have consortium partners, so that one is yours to answer."
- National call pages: "This call falls under National programme." is now "This call falls under a national programme."
- Version history: a correction entry reads "Version N · Corrected by DefenceGate on <date>" with "We read the notice we already held again with a corrected reading: the publisher did not change it on this date, and it is not counted as a change."
- Buyers, organisations, suppliers: the existing sentence "The data service did not answer in time. This is its last answer, as of ...; reload in a minute for the current one." can now appear there.
- List titles: an unknown country code gives "<List> (filtered)" instead of "<List> in XX".

## Evidence (laptop, `D:\DEFENCEGATE TESTS\wp59`)

- `npx tsc --noEmit`: exit 0.
- `npm run check` (the repo runner, now working on Windows): **29 of 29** `lib/*.check.ts` pass, the new `wp59.check.ts` among them.
- `next build` with the CI env (DG_USE_MOCK=1, NEXT_PUBLIC_DG_NOW=2026-10-12T08:00:00Z, NEXT_PUBLIC_SITE_URL=https://ci.example.test, TZ=UTC): exit 0.
- Full Playwright suite, 4 workers, E2E_PACE_MS=0: first run (before the data-page fixes) **446 passed, 40 skipped, 0 failed**; final run **447 passed, 40 skipped, 1 failed**. The failure was `digest.spec.ts:67` (the conditional request to `/digest.atom` got 200, not 304), a file this package does not touch; re-run alone with `--repeat-each=5` on both projects: 10 of 10 passed (flaky under 4 workers). New spec `e2e/wp59.spec.ts`: footer at 1024/1180/1279/1280/1440 (no wrapped label, no overlap, no sideways scroll), the tracker rule title, the PIC page, the alerts link to the feed and `/calendar.ics`, the national call sentence.
- Footer measured on the build (light, /terms): 0 wrapped labels and 0 overlaps at 375, 768, 1024, 1100, 1180, 1279, 1280, 1333, 1440, 1920 (before: 13 wrapped labels and the logo on "Funding calls" at 1024). Height 299 px from xl, 427-447 px from lg to xl (taller, because the long groups are one column there; the 360 px test of WP-46 runs at 1280 and passes).
- Backend, own venv and a local Postgres 17 container: `ruff check .` clean; unit **2,906 passed**; integration **1,121 of 1,122 passed** on the full run, the one failure being the new collapse test, which read a cached answer for its second query (the test now asks with another page size); after that change `test_tenders_collapse.py`, `test_wp52.py` and `test_archive_timeline.py` pass.
- Version history against production data (read only): the new timeline run on the version rows of 80 notices that have a `remapped` version (6 and 235 among them): **0 notices** with a stored change a reader can see that the history leaves out. Notice 235 now shows v1, v3 "Open → Awarded" dated 30 Sep, v4 (correction, procedure) and v5 (correction, "Awarded → Cancelled", value, legal basis) dated 15 Oct; notice 6 shows v1 and v2 (correction: deadline 19 Oct 21:59 to 11:00 UTC). v2 of 235 (publication date only) stays hidden by the existing rule.
- Bundeswehr on production (API, read only): `all` 112 capped, `open` 116, `closed` 11 capped. With the fix the capped `all` total is at least 116.

## Not done, or needs a decision

- Content NEW-3 (two NCAGE groups with the same label) and NEW-4 (the 7/5 conversion note): need a wording choice.
- Content NEW-11 (`/regulation` notice at full width): the paragraph already has `max-w-prose`, which is 100 % by the owner's measure decision (M-14).
- Titles still cut at a word because they have no phrase end within 46 characters: /glossary, /calendar, /requirements/aqap2310, edip-elig, export. Descriptions still cut: /data/sovereignty, /readiness, edf-elig, safe-35. Shorter source titles would fix them (wording).
- `/terms` s.13 names "the calendar feed" but not the Atom feeds among the allowed automated uses: owner wording, true as it stands.
- An error state answering HTTP 200 (N2): see above; needs an architecture decision.
- Data NEW-7 (scope labels that add up higher than the first): explained by the overlap note; no change. NEW-8 (de_bkms run failed), NEW-9 (`changes.atom` near its 2,400 cap), NEW-10 (one transient error): ops or watch items.
- The changed collapse rule (NEW-3) adds an OR branch to the republication sub-query; it is driven by the `procedure_identifier` equality. It was not timed on production (no deploy); the orchestrator should check the Closed list timing after deploy.
- Seeds: the regulation and requirements seeds are applied on worker start, so the new tracker and cost wording reaches production on the next deploy of the worker.
