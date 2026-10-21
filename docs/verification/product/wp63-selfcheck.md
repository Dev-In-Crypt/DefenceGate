# WP-63 self-check: technical tails and placeholder copy

Branch `wp-wp63` from `integration` at `edffcde`, 21 October 2026. Web and `infra/Caddyfile` only; no backend, no migration, no
design token, `globals.css`, type scale or card component touched (WP-62's area). Nothing deployed or pushed; production was not
contacted at all (no SSH, no GET). No model calls, no spending. Everything below ran on the laptop in `D:\DEFENCEGATE TESTS\wp63`
(own `npm ci`, CI env: `DG_USE_MOCK=1`, `NEXT_PUBLIC_DG_NOW=2026-10-12T08:00:00Z`, `NEXT_PUBLIC_SITE_URL=https://ci.example.test`,
`TZ=UTC`). Lab scripts: `D:\DEFENCEGATE TESTS\wp63\lab\` (`slicer.js`, `hydr.js`, `titles.js`, `weight.js`, `Caddyfile.before`,
`Caddyfile.after`, result files `*-100*.txt`, `titles-after.txt`).

## 1. React error #418: buffer the page at Caddy, smaller calendar pages

**Change.** `infra/Caddyfile`, in the `reverse_proxy web:3000` block: `response_buffers 1MiB`.

- Caddy reads the upstream answer into memory up to the bound, then sends it; a longer body has its first MiB buffered and the rest
  streamed (Caddy source, `bufferedBody`: `io.CopyN(buf, body, limit)` then `io.MultiReader(buf, body)`). So the bound is per
  response and cannot grow: at most 1 MiB per response in flight. Pages are 0.2 to 0.4 MB (WP-54; 0.19 to 0.28 MB in the lab
  after the calendar change), so every page is sent whole; a feed over 1 MiB still works (streamed after its first MiB).
- Cost: the first byte waits until the page is complete (lab: `/calendar` TTFB 3.35 s = total 3.35 s, against TTFB 0.2 s without).
  The pages have no Suspense streaming left on the lists (WP-43, WP-54), so nothing a visitor saw early is lost, except the
  skeleton of any `loading.tsx` still in the tree.
- Memory: the server had 170 MB to 1.7 GB free during WP-54. At the measured 1.4 requests a second and about 4 s a page, a few pages
  are in flight (a few MB). A slow client holds its page in Caddy instead of in Node; the total is the same order as before.

**Validation.** `caddy validate --adapter caddyfile` in `caddy:2` (v2.11.6, local image): `Valid configuration`; `caddy fmt` gives
no diff. The deployed Caddy is 2.11.4 (WP-54 validated `response_buffers` there); `handle_response`, `copy_response` and the `>`
(deferred) form of `header` were not run on 2.11.4 here. The rollout step below validates on the server's own image before the restart.

**Lab (reproduced locally).** Chain: Playwright Chromium 134, fresh context per load, dark theme stored → local `caddy:2` with the
real Caddyfile (`DGATE_DOMAIN=localhost`, `web` and `api` mapped to the host) → `slicer.js` as `web:3000` (reads the page whole,
sends the shell at once and the rest in 100 slices over 3 s, as WP-54 did; assets pass through) → the production server artifact
(`.next/standalone/server.js`, the image's `CMD`) with demo data from the fake API (`e2e/support/fake-api.mjs`: 1,449 deadlines,
1,522 open tenders). The image itself was not built (no `node:22-alpine` image on the laptop; I did not pull one).

| Caddyfile | build | page | loads | #418 | theme lost |
|---|---|---|---|---|---|
| integration (no buffer) | integration | `/calendar` | 100 | **13** | 0 |
| integration (no buffer) | integration | `/tenders` | 100 | **23** | 0 |
| with `response_buffers 1MiB` | integration | `/calendar` | 100 | **0** | 0 |
| with `response_buffers 1MiB` | integration | `/tenders` | 100 | **0** | 0 |
| integration (no buffer) | this branch (50 a page) | `/calendar` | 100 | **4** | 0 |
| this branch (final file) | this branch | `/calendar` | 100 | **0** | 0 |
| this branch (final file) | this branch | `/tenders` | 100 | **0** | 0 |

Controls: the same chain with built-in mock data (small pages) and 20 slices gave 0/30 on `/calendar`, `/tenders`, `/about`, as
in WP-54; the failure needs large inline data that trickles. The lab rate without the buffer (13 %) is the live rate of the
re-audit (13/100 on `/calendar`). The theme was kept on every hit (WP-54's fix holds). Through the buffered proxy `/calendar.ics`,
`/changes.atom`, `/sitemap.xml` and a JS chunk answer 200 with their types.

**Page weight.** `/calendar` lists 50 entries a page instead of 100 (`LIST_PAGE`, list and month view). Fake-API data:

| page | before | after |
|---|---|---|
| `/calendar` | 306,305 B (inline RSC 179,257) | 194,028 B (114,530) |
| `/calendar?view=month&month=2026-11` | 390,181 B (228,741) | 276,404 B (163,114) |

Without the buffer the smaller page alone took `/calendar` from 13 to 4 in 100 (the slicer spreads any page over the same 3 s, so
this is the effect of less data, not of an earlier end). Not done: the per-row class strings (about a third of the bytes) live in
components and `globals.css` of WP-62's area.

### Rollout (orchestrator; after `integration` is merged and `main` carries it)

The Caddyfile is a single-file bind mount: `git pull` replaces the file, so `caddy reload` inside the running container would read
the old one. Restart the container (TLS state is in the `caddydata` volume; a few seconds without the site). Any time; it does not
touch the PLACSP load (worker).

```sh
cd /opt/dgate
git rev-parse HEAD > /root/caddy-before-wp63.rev            # for the rollback
git pull --ff-only
# validate the new file with the deployed image, without touching the running proxy (no ports published by `run`)
docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose -f infra/docker-compose.yml --env-file infra/.env restart caddy
# checks: TTFB now equals the total; a page is 200; the log has no new error
curl -s -o /dev/null -w 'ttfb %{time_starttransfer} total %{time_total} code %{http_code}\n' https://defencegatehub.com/calendar
curl -s -o /dev/null -w '%{http_code}\n' https://defencegatehub.com/calendar.ics
docker compose -f infra/docker-compose.yml --env-file infra/.env logs --since 5m caddy | grep -ci error
```

The web image must also be rebuilt for the page changes (calendar size, error states, copy): the usual
`infra/build-web.sh` and `docker compose ... up -d web`. Re-measure #418 on the live site after both (the WP-54 / re-audit script,
100 clean loads of `/calendar` and `/tenders`, 1 a second).

### Rollback

```sh
cd /opt/dgate
git checkout "$(cat /root/caddy-before-wp63.rev)" -- infra/Caddyfile
docker compose -f infra/docker-compose.yml --env-file infra/.env restart caddy
# later, to return to the tracked file:  git checkout HEAD -- infra/Caddyfile
```

## 2. A failed list answers 5xx, not 200

**What Next 15.5 does (measured, `next start` against the fake API with a list that answers 503).** A page that throws is
answered **500** (`/tenders?q=unavailable`: 500, `<meta name="robots" content="noindex"/>`, the error boundary drawn on the client).
WP-59's "200" came from the pages that drew their own error state instead of throwing (`/organisations` in the re-audit, N2). A
page cannot set any other status: Next only maps `notFound()` 404, `forbidden()` 403, `unauthorized()` 401 and redirects; there is
no response object in a server page, and middleware runs before the render.

**Changes.**

- Pages that drew an error state with 200 now throw, so they answer 500 like the others: `/organisations` (a 422 past the cap stays
  a 404), `/calendar` when neither tenders nor funding answered (new `calendar/error.tsx`; one of the two down still renders the
  other with its line), `/networks/ukraine-partners` and `/networks/consortium-gaps` (new `networks/error.tsx`; a 4xx refusal of
  a too-broad topic stays the in-page message, it is an answer to the form).
- `/requirements` (ISR, 1 h): at run time a failed refresh is thrown, so ISR keeps the last good catalogue instead of storing the
  error state for an hour; only `next build`, which has nothing older, still renders the error state (`NEXT_PHASE`).
- Edge: `infra/Caddyfile` `handle_response` on upstream status 500 from the web: `copy_response 503`, `Retry-After: 120`,
  `Cache-Control: no-store` (set after the upstream headers are copied, so it replaces `public, max-age=0, must-revalidate`).
  Lab: `/tenders?q=unavailable` and `/organisations` through Caddy: `HTTP/1.1 503`, `Cache-Control: no-store` (once),
  `Retry-After: 120`, the error page as body. A route handler's own 502 (`/tenders/export.csv` with no API) is left as it is.
- Caveat: a real bug (any web 500) is now also sent as 503 with Retry-After; the web log still has the error and its digest.

Not cached: lists are dynamic (no ISR entry), and the 503 carries `no-store`; ISR pages keep their last good version on a thrown
refresh (Next's documented behaviour; not reproduced here, it needs an hour or a forced revalidation).

## 3. Titles and descriptions cut mid-phrase

Crawl of the demo build (`titles.js`: the sitemap plus 16 pages it leaves out, 84 pages): **21 pages** with a title or description
ending in "…" before, **8 after**. The 8 left are notice and call titles (data: a tender or call name longer than 46 characters,
cut at a word), not our copy. Fixed by shorter source titles, per route:

| page | before | after |
|---|---|---|
| `/glossary` title | Glossary of defence procurement and funding… | Defence procurement and funding glossary |
| `/calendar` title | Deadline calendar for defence tenders and… | Deadline calendar: defence tenders and calls |
| `/requirements/aqap2310` title | AQAP 2310 quality management for aviation… | AQAP 2310: who issues it, cost and time |
| `/requirements/edip-elig` title | EDIP eligibility and origin rules, including… | EDIP eligibility: what the rule says |
| `/requirements/export` title | Export authorisation for dual-use or military… | Export authorisation |
| `/data/sovereignty` description | … and the one language-model service… | What DefenceGate runs where: server, archive and backups, DNS, certificate, code and the one language-model service. What is in the EU and what is not. |
| `/readiness` description | … what blocks it and… | Answer a few questions about your company and see, rule by rule, whether EDF, EDIP and SAFE let it take part, what blocks it and what to obtain first. |
| `/requirements/edf-elig` description | … and not controlled by a… | Who may receive EDF funding: an entity established in the Union or an associated country, managed from there, not controlled by a non-associated third country. |
| `/requirements/safe-35` description | … 35 % of the estimated cost of the… | In a SAFE-supported procurement, components from outside the Union, the EEA EFTA states and Ukraine may be at most 35 % of the estimated component cost. |
| `/digest` title, description | Weekly digest of defence notices and funding…; … calls with cascade… | Weekly digest of defence tenders and calls; Each week: new and amended defence notices, funding calls that are new, opening or closing, and calls with cascade funding. Free, with an Atom feed. |
| `/networks/consortium-gaps` title, description | Repeat participants of a capability area with…; … with the projects… | Repeat participants lacking a partner country; Organisations funded at least twice in one European Defence Fund capability area that never had a partner from a chosen country, with the projects as evidence. |
| `/networks/ukraine-partners` title, description | Who partners with Ukrainian organisations in…; … and the projects as… | Who partners with Ukrainian organisations; Coordinators of EU-funded defence and research projects with a participant established in Ukraine, with the Ukrainian organisations and projects as evidence. |
| `/organisations` title | Organisations in EU-funded defence and… | Organisations in EU-funded projects |

The requirement pages keep their full name and summary on the page; only the tab and snippet use the short words
(`SHORT_META` in `requirements/[code]/page.tsx`, keyed by code). The two rule descriptions are paraphrases of the summaries for the
owner to read: EDF "executive management there" is "managed from there"; SAFE leaves out the second rule (the categorical
exclusion), which the page states.

## 4. Placeholder copy: every string, for the owner

Facts kept: free to browse; no billing; accounts and alerts built, sign-in closed until a mail provider is chosen; Atom feeds,
calendar feed, CSV export and the readiness check work now; no contact, price or date invented. Footer "Alerts (not open yet)" is
in `footer.tsx` (not mine to edit) and is unchanged.

**/pricing**

- Description: "DefenceGate is free to use and there is no paid plan. What it offers today: the lists, CSV export, Atom feeds, a calendar feed and the readiness check."
- Lead: "DefenceGate is free to use. There is no paid plan and no billing, and we ask for no payment details. If a paid service is ever offered, its price and terms will be on this page before anything is charged."
- Table "What is offered and what it costs", columns What / Price / Status / Note:
  - Browsing · Free · Open · "Tenders, funding calls, buyers, organisations and the source status, with no account."
  - CSV export · Free · Open · "The public fields of a tender or funding list, with the source, licence and attribution on every row."
  - Atom feeds · Free · Open · "What changed, the weekly digest and the regulatory tracker, for any feed reader."
  - Calendar feed · Free · Open · "Tender and funding deadlines in your own calendar app."
  - Readiness check · Free · Open · "Your answers stay in your browser."
  - Account and e-mail alerts · No price set · Not open yet · "Built. Sign-in opens once a provider to send the e-mails is chosen."
- Removed: the rows "Alerts / Opportunity pack / Pro archive · Not announced · Not available yet", "Planned. Scope is not defined.", "Pricing is not announced."

**/pack**

- Description: "A ready-made pack for one company is not offered. Put the same list together yourself, free: filters, CSV export, the readiness check and the calendar feed."
- Lead: "A pack of the open tenders and funding calls that fit one company, assembled for you, is not offered. You can put the same list together yourself today, free and without an account."
- Section "Put it together yourself":
  - "Filter the tenders by country, product code (CPV) or keyword, and the funding calls by programme, funder country or keyword. The filters are in the address, so a bookmark keeps the search."
  - "Download each result as CSV: the public fields, with the source, licence and attribution on every row."
  - "Run the readiness check to see which EDF, EDIP and SAFE rules your company meets. Your answers stay in your browser."
  - "Subscribe to the calendar feed for the deadlines, and to the Atom feed of what changed."
- "What it is not": "Not a guarantee of fit, eligibility or success, and not legal or bidding advice. Check every item against its original notice."
- Buttons: "Tenders", "Funding calls", "Readiness check".
- Removed: "Coming soon", "The pack is planned. It cannot be ordered today and we do not give a date or a price.", "What it is meant to contain" (3 items), "The contents may change before it is offered.", the button "What is planned for alerts" (weak link text, m-13).

**/alerts** (sign-in closed; the open-state strings are unchanged)

- Description: "Saved searches and e-mail alerts are built; sign-in is not open yet. Without an account: filters in the address, CSV, a calendar feed and Atom feeds."
- Lead: "Saved searches and e-mail alerts are built, but sign-in is not open yet: it opens once we have chosen a provider to send the e-mails. What works today needs no account, and it is listed first."
- Card "A calendar feed": "Subscribe to the deadline calendar in your own calendar app: open tenders and funding calls with a deadline." (was "A calendar file": "The deadline calendar is a file you can subscribe to …")
- Section title "What an account adds, once sign-in opens" (was "What is planned").
- Last line, closed state: "… Sign-in will be by a one-time link sent to your e-mail, with no password." (was the present tense, m-14).
- Removed: "E-mail alerts and saved searches are being prepared and are not open yet. There is no date."

**/privacy**, section 5 "Mail", the one visible placeholder only:

- Was: "They are sent through a mail provider acting as our processor: [mail provider to be named when sign-in opens]"
- Now: "They will be sent through a mail provider acting as our processor. None has been chosen yet, which is why sign-in is not open; the provider will be named here before it opens."
- Section 8 ("The mail provider named in section 5, once sign-in opens.") and every other privacy sentence: unchanged.

## Tests

- New `e2e/wp63.spec.ts`: the 16 pages above have no "…" in title or description and fit 60/160 (description at least 40);
  `/pricing` table rows and no "Not announced"; `/pack` copy and its three links; `/alerts` and `/privacy` without the
  placeholders. Against the fake API only (skipped in CI like `wp52b-api.spec.ts`): `/tenders?q=unavailable`, `/organisations`,
  `/networks/ukraine-partners` answer 5xx with `noindex`.
- `e2e/support/fake-api.mjs`: `q=unavailable` on `/v1/tenders` answers 503.
- Changed for the new copy or paging (not weakened): `wp46.spec.ts` pricing/pack (table of 6 rows, "Free", new headings);
  `wp52b-api.spec.ts` T9 (50 a page, twelve pages, the size bound tightened from 600 KB to 300 KB); a comment in `wp52b.spec.ts`.

Runs (laptop, CI env, final tree):

- `npx tsc --noEmit`: exit 0. `npm run check`: exit 0, **30 of 30** `lib/*.check.ts` ok.
- `next build`: exit 0.
- Full Playwright, `--workers=4`, `E2E_PACE_MS=0`, both projects: **455 passed, 47 skipped, 0 failed** (1.5 min). The skips are the
  declared viewport skips and the fake-API specs.
- Fake-API specs (`E2E_FAKE_API=1`, site started with `DG_API_URL` at the fake): `wp63.spec.ts` and `wp52b-api.spec.ts`, both
  projects: **25 passed, 1 skipped** (the desktop-only metadata test on the phone project).
- `caddy validate` and `caddy fmt` on the final `infra/Caddyfile`: valid, no diff. Lab results in the tables of section 1.

## Hostile review of the diff

Six issues found and fixed before the final runs:

1. The first 503 mapping sent `Cache-Control` twice (`no-store` and the framework's `public, max-age=0`): a plain `header` adds
   before the upstream headers are copied. Now `header >Cache-Control`, measured once.
2. `copy_response_headers` duplicated `Content-Type` and others (the upstream headers are copied anyway): removed.
3. The new `/alerts` and `/pack` descriptions were over 160 and lost their second sentence: shortened, both whole now.
4. Two new titles dropped words the existing tests rely on (`/calendar/i`, `/Repeat participants/`): rewritten to keep them rather
   than editing those tests.
5. `/pack` said the funding calls filter "the same way" as tenders (they have no CPV filter): now names their real filters.
6. The account row of `/pricing` said "Free", which is a price nobody set: now "No price set".

## Not done or not checked

- The image was not built and the live site was not measured; the #418 rate after rollout must be re-measured there.
- Caddy 2.11.4 (deployed) was not run locally; the rollout validates on it first.
- ISR keeping the last good `/requirements` after a thrown refresh is Next's documented behaviour, not reproduced here.
- No-JS visitors of a failed list see an empty 503 page (the error boundary is drawn by script); before, three pages drew the
  message in HTML with a 200.
- The calendar's per-row markup (about a third of its bytes) was not slimmed: it lives in WP-62's components and styles.
- Backend not touched, so no backend tests were run.
