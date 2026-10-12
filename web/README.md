# DefenceGate web

Next.js 15 (App Router) · TypeScript strict · Tailwind CSS 3.4 · shadcn/ui conventions · lucide-react.

```bash
cp .env.example .env.local   # leave DG_API_URL empty to use mock data
npm install && npm run dev
```

Status: **styleguide, landing, /funding hub and /funding/[slug] are built.** Everything else is scaffolded (types, API functions, route-group layouts, sitemap/robots) and lands in later passes (P1 rest → P2 → P3 → P4).

## Folder structure

```
app/
  layout.tsx              fonts (next/font Manrope + DM Mono), theme pre-paint script, base metadata
  globals.css             DefenceGate tokens as CSS variables (light :root, dark [data-theme="dark"])
  icon.svg                favicon (from brand/favicon.svg)
  robots.ts / sitemap.ts  sitemap lists /, /funding and real call slugs only
  (public)/               server-rendered, indexable
    layout.tsx            HeaderBar + Footer, skip link
    actions.ts            server action: waitlist intake is closed; validates, stores and sends nothing
    page.tsx              /  landing
    funding/(list)/       /funding hub: page.tsx, loading.tsx, error.tsx (own route group so its loading boundary does not wrap [slug])
    funding/[slug]/       call detail  (+ error.tsx, not-found.tsx; no loading.tsx on purpose: it would stream a 200 before notFound()/permanentRedirect run)
    styleguide/page.tsx   /styleguide (noindex; 404 in production)
  (app)/app/layout.tsx    P3, robots noindex
  (admin)/admin/layout.tsx P4, robots noindex
components/
  dg/                     shared design-system components (see list)
  funding/                FilterBar, FilterPanel, SortSelect, CallCalendar, CallListTemplate
  landing/                WaitlistForm
lib/
  types.ts                all domain types; funding types follow docs/design/API_CONTRACT.md
  api.ts                  the ONLY data-access module
  mock/                   calls.json, sources.json (+ typed adapters), opportunities.ts (P2)
  deadline.ts             days left, state (normal/soon/urgent/closed/none), UTC string, countdown; null deadline = "No fixed deadline"
  format.ts               UTC dates, ISO-coded amounts
  filters.ts              URL ⇄ CallFilters (parse, serialise, active count)
  seo.ts                  buildMetadata, meetsMinimumContent, JSON-LD builders
  taxonomy.ts             countries, programmes, regimes, languages
public/brand/             mark.svg, mark-reversed.svg, mark-small.svg, favicon.svg, app-icon.svg
```

## How tokens map to the design system

- `app/globals.css` copies every token from the DS `tokens/*.css` with **identical names** (`--bg`, `--surface`, `--surface-inset`, `--ink`, `--primary`, `--accent`, `--accent-text`, `--urgent`, `--open-bg`, `--soon-bg`, `--closed-bg`, `--alert`, `--space-*`, `--radius-*`, `--transition`…). Light on `:root`, dark on `[data-theme="dark"]`.
- `tailwind.config.ts` maps each token to a utility: `bg-surface`, `text-ink`, `text-accent-text`, `bg-soon-bg`, `rounded-lg` (= `--radius-lg`, 20px), `rounded-md` (14px), `rounded-pill`, `p-6` (= `--space-6`, 28px), `gap-8` (48px), `text-h1`, `text-mono-strong`, `text-figure`, `duration-dg`. Never use raw hex in components.
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
| `getOpportunities(filters)` | `GET /v1/opportunities` |
| `getOpportunity(id)` | `GET /v1/opportunities/{id}` |
| `getOpportunityVersions(id)` | `GET /v1/opportunities/{id}/versions` |
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

Added with the same tokens: `Footer`, `TenderCard`, `AmountDisplay`, `CountryLabel`, `FactCell`, `FilterBar` (GET form, URL-synced, works without JS), `FilterPanel`, `SortSelect`, `CallCalendar`, `CallListTemplate`, `Pagination`, `EmptyState`, `ErrorState`, `Skeleton`, `CallCardSkeleton`, `LockedFeature`, `ComingSoon`, `Breadcrumbs`, `JsonLd`, `ThemeToggle`, `WaitlistForm`.

## States

Each list route has loaded (page), loading (`loading.tsx` skeletons), empty (`EmptyState` in the template) and error (`error.tsx` → `ErrorState` with retry). The call detail route has no `loading.tsx` so unknown slugs return a real 404 and non-canonical slugs a real permanent redirect; it keeps `not-found.tsx` and `error.tsx`.

## Rules enforced in code

UTC everywhere (`lib/format.ts` appends "UTC"); amounts always `CUR 1,234` (`formatMoney`) and never converted or compared across currencies; a null deadline is "No fixed deadline", never "Closed"; a forthcoming call is "Opens soon", never "Open"; every card and detail shows `SourceBadge` with retrieved time and licence; a non-English heading carries `lang` and a "Original language, X" label, and the other-language title sits beneath it with its own `lang`; deadline colours only from `lib/deadline.ts` states; `--alert` only in `ErrorState` and field errors; no personal contact data in types or mocks.

## Security headers and production build

- `next.config.ts` sets CSP, Referrer-Policy, X-Content-Type-Options, Permissions-Policy, X-Frame-Options and HSTS on every route. `script-src` has `'unsafe-inline'` (nonces do not work with ISR pages); the reasoning is in the comment there.
- A production build fails unless `NEXT_PUBLIC_SITE_URL` starts with `https://`. `DG_ALLOW_INSECURE_SITE_URL=1` allows it to be unset (local previews only).
- Source-supplied URLs only become links through `lib/safe-url.ts` (`http:` / `https:` only).
- Pages that do not exist yet (tenders, buyers, data, pricing, alerts, pack, legal) are not linked; the footer marks them "Coming soon".
