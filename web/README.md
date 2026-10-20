# DefenceGate web

Next.js 15 (App Router) · TypeScript strict · Tailwind CSS 3.4 · shadcn/ui conventions · lucide-react.

```bash
cp .env.example .env.local   # leave DG_API_URL empty to use mock data (development only: a production build refuses to start without it)
npm install && npm run dev
```

Status: **styleguide, landing, /funding, /funding/[slug], /tenders, /tenders/[slug], /buyers, /buyers/[slug], /data (source status) and the text pages (/alerts, /pack, /pricing, /privacy, /terms, /imprint, /about) are built.** The text pages are skeletons: `robots: noindex` and a visible "Draft — text pending" notice until the text exists. `(app)` and `(admin)` are scaffolds (P3, P4).

## Folder structure

```
app/
  layout.tsx              fonts (next/font Manrope + DM Mono), theme pre-paint script, base metadata
  globals.css             DefenceGate tokens as CSS variables (light :root, dark [data-theme="dark"])
  icon.svg                favicon (from brand/favicon.svg)
  robots.ts / sitemap.ts  sitemap lists the indexable static pages and the real call, tender and buyer slugs
  (public)/               server-rendered, indexable
    layout.tsx            HeaderBar + Footer, skip link
    actions.ts            server action: waitlist intake is closed; validates, stores and sends nothing
    page.tsx              /  landing
    funding/(list)/       /funding hub: page.tsx, loading.tsx, error.tsx (own route group so its loading boundary does not wrap [slug])
    funding/[slug]/       call detail  (+ error.tsx, not-found.tsx; no loading.tsx on purpose: it would stream a 200 before notFound()/permanentRedirect run)
    tenders/(list)/       /tenders list; tenders/[slug]/ tender detail with version history (same structure as funding)
    buyers/(list)/        /buyers directory; buyers/[slug]/ buyer with its open and earlier tenders
    data/                 /data source status (getHealth)
    alerts pack pricing privacy terms imprint about   text-page skeletons on components/dg/content-page.tsx
    styleguide/page.tsx   /styleguide (noindex; 404 in production)
  (app)/app/layout.tsx    P3, robots noindex
  (admin)/admin/layout.tsx P4, robots noindex
components/
  dg/                     shared design-system components (see list)
  funding/                FilterBar, FilterPanel, SortSelect, CallCalendar, CallListTemplate
  tenders/                TenderFilterBar, BuyerFilterBar (reuse FilterPanel and SortSelect)
  landing/                WaitlistForm
lib/
  types.ts                all domain types; funding types follow docs/design/API_CONTRACT.md
  api.ts                  the ONLY data-access module
  mock/                   calls.json, sources.json (+ typed adapters), tenders.ts (tenders, versions and buyers; all names invented)
  deadline.ts             days left, state (normal/soon/urgent/closed/none), UTC string, countdown; null deadline = "No fixed deadline"
  format.ts               UTC dates, ISO-coded amounts
  filters.ts              URL ⇄ CallFilters (parse, serialise, active count)
  seo.ts                  buildMetadata, meetsMinimumContent, JSON-LD builders
  taxonomy.ts             countries, programmes, regimes, languages, tender scopes, legal bases, CPV names
public/brand/             mark.svg, mark-reversed.svg, mark-small.svg, favicon.svg, app-icon.svg
```

## How tokens map to the design system

- `app/globals.css` copies every token from the DS `tokens/*.css` with **identical names** (`--bg`, `--surface`, `--surface-inset`, `--ink`, `--primary`, `--accent`, `--accent-text`, `--urgent`, `--open-bg`, `--soon-bg`, `--closed-bg`, `--alert`, `--edge`, `--input-edge` (border of a form field, 3:1), `--logo-*` (the logo follows the theme), `--radius-*`, `--measure`, `--content-max`, `--gutter`, `--transition`…). Light on `:root`, dark on `[data-theme="dark"]`.
- `tailwind.config.ts` maps each token to a utility: `bg-surface`, `text-ink`, `text-accent-text`, `bg-soon-bg`, `rounded-lg` (= `--radius-lg`, 20px), `rounded-md` (14px), `rounded-pill`, `p-6` (24px), `gap-8` (32px), `gap-12` (48px) (spacing is Tailwind's own scale, 4/8/12/16/24/32/48/64/96: there is no override), `text-h1` (36/44), `text-h4` (18/26), `text-lead`, `max-w-prose` (the one reading measure: the whole content box, `--measure: 100%`; it was 680px until 19 Oct 2026), `border-edge`, `text-mono-strong`, `text-figure`, `duration-dg`. Never use raw hex in components.
- DS type classes (`.display .h1 … .figure`) also exist in `globals.css` for parity.
- **shadcn/ui:** role variables (`--background`, `--card`, `--muted`, `--border`, `--ring`, `--destructive`, `--primary-foreground`…) point at DG tokens. shadcn's `accent` role (hover fill) is deliberately **not** mapped, because DG `--accent` is copper and reserved for the logo and time pressure. When adding a shadcn component, replace `bg-accent text-accent-foreground` with `bg-surface-inset text-ink`.
- Logo colours are fixed and do not follow the theme (`components/dg/logo.tsx`).

## Swapping mock data for the real API

All reads go through `lib/api.ts`. Set `DG_API_URL=https://api.defencegate.eu` and every function calls `/v1/*` instead of `lib/mock`. Funding responses are defined by `docs/design/API_CONTRACT.md` and match `lib/types.ts`. Remove `NEXT_PUBLIC_DG_NOW` in production (it pins "now" so mock countdowns stay stable).

| Function | Endpoint |
|---|---|
| `getCalls(filters)` | `GET /v1/funding` (query keys as the site URL, plus `pageSize` and `currency`) |
| `getCall(slug)` | `GET /v1/funding/{slug}` (leading id looked up; the page redirects to the canonical slug) |
| `getAllCallSlugs()` | `GET /v1/funding/slugs` |
| `getTenders(filters)` | `GET /v1/tenders` (cached only for the unfiltered default list) |
| `getTender(slug)` | `GET /v1/tenders/{slug}` (the page redirects to the canonical slug) |
| `getTenderVersions(slug)` | `GET /v1/tenders/{slug}/versions` |
| `getAllTenderSlugs()` | `GET /v1/tenders/slugs` |
| `getBuyers(filters)` | `GET /v1/buyers` |
| `getBuyer(slug)` | `GET /v1/buyers/{slug}` |
| `getAllBuyerSlugs()` | `GET /v1/buyers/slugs` |
| `getHealth()` | `GET /v1/sources` |
| `getSiteStats()`, `getRelatedCalls()` | composed from the above |

## SEO

- Public pages are Server Components with `generateMetadata` (`lib/seo.ts → buildMetadata`): canonical, Open Graph, Twitter, robots.
- Filtered/paginated `/funding?…` URLs are shareable but `noindex,follow` with canonical `/funding`.
- `meetsMinimumContent(entity)` returns false for thin calls (no source URL or title, or none of structured eligibility, a deadline, an opening date) and lists with fewer than 3 items; pages then render `noindex`.
- JSON-LD: Organization + FAQPage (landing), MonetaryGrant (call detail), BreadcrumbList (every Breadcrumbs).
- `robots.ts` disallows `/app`, `/admin`, `/v1`; `(app)` and `(admin)` layouts set `robots: noindex`. `/styleguide` is noindex and returns 404 in production.

## Components

Design system: `HeaderBar`, `Button` (primary, secondary, text), `Tag` (programme, neutral), `StatusPill` (open, soon, closed, amended), `DeadlineBadge` (md, lg), `CallCard`, `SourceBadge` (inline, full), `VersionTimeline`, `Logo` / `LogoMark` / `Wordmark`, `Icon`, `TextInput`, `Select`, `Textarea`, `Choice` (checkbox/radio), `Fieldset`.

Added with the same tokens: `Footer`, `TenderCard`, `BuyerCard`, `TenderStatusPills`, `RunStatusPill`, `ListPage`, `ContentPage`, `ContentSection`, `PendingSections`, `Placeholder`, `DraftNotice`, `AmountDisplay`, `CountryLabel`, `FactCell`, `FilterBar` (GET form, URL-synced, works without JS), `FilterPanel`, `SortSelect`, `CallCalendar`, `CallListTemplate`, `Pagination`, `EmptyState`, `ErrorState`, `Skeleton`, `CallCardSkeleton`, `LockedFeature`, `ComingSoon`, `Breadcrumbs`, `JsonLd`, `ThemeToggle`, `WaitlistForm`.

## Tools and reference pages

- `/calendar` (month and list) and `/calendar.ics`: open tenders and funding calls with a deadline, built in `lib/calendar.ts`; the feed is `lib/ics.ts` (RFC 5545, at most 500 events, UID `<kind>-<id>@defencegatehub.com`, cached an hour). The feed was withdrawn on 2026-10-19 and restored on 2026-10-20.
- `/tenders/export.csv`, `/funding/export.csv`: the public fields of the current list result (same query keys as the pages), at most 2,000 rows, formula-safe cells (`lib/csv.ts`, `lib/export.ts`).
- `/tenders/<slug>/evidence`: printable record with source, licence, retrieval time, version shown and the full version timeline; `noindex`. Print CSS hides the header and footer (`print:hidden`).
- `/cpv`: selection of the official CPV 2008 vocabulary in `lib/data/cpv.json` (source and licence in the file's `_source` and `_licence`). `/glossary`: entries in `lib/glossary.ts`.
- Tender status words come from `lib/tender-status.ts`: only an effective `open` reads "Open"; `expired` is "Closed"; `awarded`, `cancelled`, `forthcoming` ("Planned") and `unknown` ("Status unknown") have their own pills.
- `lib/export.check.ts` is a self-check of the CSV and calendar-file helpers; the command to run it is in its header.
- `/changes` and `/changes.atom`: what changed in the last 14 days (`GET /v1/changes`, contract in `docs/design/API_CONTRACT.md`). New notices and amendments to a deadline, value, status or procedure, one entry per notice per day; the feed (`lib/atom.ts`, Atom 1.0, tag-URI ids, `ETag`/`Last-Modified`) is what an alert would be while sign-in is closed. Without `DG_API_URL` the demo data answers (`lib/mock/tenders.ts` `queryChanges`).
- `lib/atom.check.ts` checks the feed's validity and the change filters. `npm run check` runs every `lib/*.check.ts` (`scripts/run-checks.mjs`).

## Tests

- `npm run typecheck` and `npm run check`: types and the self-checks.
- `npm run e2e` (Playwright, `e2e/`): the main routes at 1280 px and at 375 px, checking status, title, headline, key text, no console error, no horizontal scroll and no e-mail address in the page; the feed is validated with the browser's XML parser. It only reads, one worker, with a pause after each page (`E2E_PACE_MS`, 700 ms). Against a site: `E2E_BASE_URL=https://defencegatehub.com npm run e2e`. Against a build: `npm run build && npm run e2e` (starts `next start` itself). The browser comes from `npx playwright install chromium` (add `--with-deps` on a bare machine; the `mcr.microsoft.com/playwright:*-jammy` images carry the system libraries).
- `e2e/wp52b-api.spec.ts` needs numbers the demo data cannot show (593 deadlines in a month, a list that stops at position 10,000, a feed of 2,311 changes). It is skipped unless `E2E_FAKE_API=1`: start `node e2e/support/fake-api.mjs` (port 4010, shaped as the API contract says), start the build with `DG_API_URL=http://127.0.0.1:4010 NEXT_PUBLIC_DG_NOW=2026-10-12T08:00:00Z npx next start -p 3100`, then `E2E_FAKE_API=1 E2E_BASE_URL=http://127.0.0.1:3100 npx playwright test e2e/wp52b-api.spec.ts`. `/data` is a static page built with the demo data: the spec waits for its refresh (up to 150 s). The site keeps the API's answers in `.next/cache/fetch-cache`: after changing the fake's data, delete that folder before starting the site again, or the first request is served from the old answer.
- CI (`.github/workflows/web.yml`) builds with the demo data (`DG_USE_MOCK=1`, `NEXT_PUBLIC_DG_NOW` pinned) and runs the same tests: no secret, no API, no production.

## States

Each list route has loaded (page), loading (`loading.tsx` skeletons), empty (`EmptyState` in the template) and error (`error.tsx` → `ErrorState` with retry). The call detail route has no `loading.tsx` so unknown slugs return a real 404 and non-canonical slugs a real permanent redirect; it keeps `not-found.tsx` and `error.tsx`.

## Rules enforced in code

UTC everywhere (`lib/format.ts` appends "UTC"); amounts always `CUR 1,234` (`formatMoney`) and never converted or compared across currencies; a null deadline is "No fixed deadline", never "Closed"; a forthcoming call is "Opens soon", never "Open"; every card and detail shows `SourceBadge` with retrieved time and licence; a non-English heading carries `lang` and a "Original language, X" label, and the other-language title sits beneath it with its own `lang`; deadline colours only from `lib/deadline.ts` states; `--alert` only in `ErrorState` and field errors; no personal contact data in types or mocks.

## Security headers and production build

- `next.config.ts` sets CSP, Referrer-Policy, X-Content-Type-Options, Permissions-Policy, X-Frame-Options and HSTS on every route. `script-src` has `'unsafe-inline'` (nonces do not work with ISR pages); the reasoning is in the comment there.
- A production build fails unless `NEXT_PUBLIC_SITE_URL` starts with `https://`. `DG_ALLOW_INSECURE_SITE_URL=1` allows it to be unset (local previews only).
- Source-supplied URLs only become links through `lib/safe-url.ts` (`http:` / `https:` only).
- Every header and footer link points to a page that exists. A link to a page that does not exist yet must not be added.

## Layout foundation (WP-44)

Components in `components/dg` (API and measurements: `docs/verification/product/wp44-selfcheck.md`): `PageHeader` (breadcrumbs, h1, lead, actions: use it for every page head), `Card` / `TextCard` (the one white box: 1px edge, 20/24px padding, titled variant with a 56px header row), `FactsGrid` / `Fact` and the `facts-grid` class (label-above-value hairline grid, at most 3 columns), `AutoGrid` (cards fill the row, a lone card takes it), `Prose` (the reading measure and rhythm), `Details` (a long line behind a 44px summary), `DataTable` (keeps its width, scrolls inside its box at 375px), `ContentPage` / `ContentSection` / `PageSection` (reading pages are one centred column with the title of each card in its own column from lg; `wide` is the data page). Never write a `max-w-[..ch]`, an `h1` class string or a white-card class string by hand: use `max-w-prose`, `PageHeader` and `Card`.
