# WP-118 self-check: card hover (owner, 25 Oct 2026)

Branch `wp-wp118` from `integration` (4b7255c). Web only; no backend, no migration, no ops module. Only hover and focus states changed:
no copy, layout or colour token changed.

## The bug and its root cause

Owner's screenshot (homepage, dark): hovering the "Can I take part?" tile underlined every line in it. Two causes:

1. `web/app/globals.css`: `a:hover { text-decoration: underline; }` has specificity (0,1,1). Tailwind 3 layers are source order, not
   CSS cascade layers, so it beat every link's own `no-underline` utility (0,1,0). The tile said `no-underline` and was still underlined,
   and an underline on a block link reaches every line inside it. The same rule underlined the stretched title of every list card
   (the title's `::after` covers the card, so hovering anywhere in the card is hovering the title link). Components worked around it
   with `hover:no-underline` (buttons, pills, pagination, logo, account menu).
2. `group-hover:underline` on the title of whole-card links (home tile, list cards, organisation cards, calendar entries).

## Change

| Where | Change |
|---|---|
| `web/app/globals.css` | `a:hover` became `a:where(:hover:not([class~="block"], [class~="flex"], [class~="grid"], :has(div, p, h2, h3, h4, ul, ol, dl)))`: specificity (0,0,1), placed after the preflight's `a`, so a link's own `no-underline` wins; a block, flex or grid link, or one holding a heading, paragraph or box (a card), never gets the hover underline. Inline and inline-flex text links still underline on their own hover. The WCAG 1.4.1 running-text rule is unchanged. |
| `web/components/dg/card.tsx` | New `ROW_HOVER`: for a list row that is one link, the row gets the inset tint on hover and on keyboard focus (`has-[:focus-visible]`). An 8 px spread shadow in the same tint carries it past the text, so nothing moves. Existing token only (`--surface-inset`), both themes. |
| `web/app/(public)/page.tsx` | Home tiles: `group-hover:underline` taken off the title; `focus-visible:border-ink-muted` added (the tile gets the same edge on keyboard focus as on hover, plus the site's focus ring). |
| `web/components/dg/cards.tsx` | TenderCard, CallCard, BuyerCard: `group-hover:underline` taken off the stretched title link; `has-[:focus-visible]:border-ink-muted` on the card (keyboard focus draws the card edge too). Comment made true. |
| `web/components/networks/parts.tsx` | OrgCard: the same two changes (same card constants). |
| `web/components/calendar/calendar-views.tsx` | Calendar entry (stretched title over the row): title underline removed, `ROW_HOVER` on the row. |
| `web/components/funding/call-calendar.tsx` | Funding calendar row (stretched title): the same. |
| `web/app/(public)/search/page.tsx` | Search result row (one link holding the title and its line): `hover:underline` removed, `ROW_HOVER` on the row. |
| `web/components/cpv/cpv-browser.tsx` | CPV code row (one link: code and title): `hover:underline` removed, `ROW_HOVER` on the link (both lists: the selection and the full vocabulary). |

## What was checked (every page and component with card-like links)

Method: a hover audit on the demo build (`DG_USE_MOCK=1`, 1280 px): on each page every visible link was scrolled into view and
hovered, and a link was reported if it is card-like (stretched, holds block boxes, or is a block/flex/grid link with more than one text
part) and either underlines on hover or shows no change on its box. Pages (41): `/`, `/tenders`, `/funding`, `/funding?view=calendar`,
`/buyers`, `/companies`, `/suppliers`, `/organisations`, `/networks/ukraine-partners`, `/networks/consortium-gaps`, `/market`,
`/digest`, a digest week, `/changes`, `/calendar`, `/search`, `/check`, `/readiness`, `/readiness/supplier`,
`/readiness/supplier/winners`, `/readiness/spain-automotive`, `/readiness/roadmap`, `/readiness/results`, `/about`, `/data`,
`/data/sovereignty`, `/methodology`, `/glossary`, `/cpv`, `/requirements`, a requirement, `/regulation`, `/pricing`, `/pack`, `/alerts`,
and the records: a tender, a funding call, a buyer, an organisation, a supplier, a project. Also `a a` (a link inside a link) on each.

- Before the change (the red run of the new spec below, and the classes in the code): home tiles, every TenderCard / CallCard /
  BuyerCard / OrgCard, calendar entries, funding calendar rows, search rows and CPV rows underlined their text on hover; the rows showed
  no change on their box. An audit run during the work (with the first, too weak version of the rule) also found the CPV rows.
- After (final build): no card-like link underlines; every whole-card link and row changes its box on hover. What the audit still lists are text links,
  which keep their underline on their own hover by the rule: "View original" (source badge), "Primary source" (/regulation), "NSPA:
  request an NCAGE code" (/requirements/ncage), the country links in the /market tables, the text-style `Button` ("Open EU Funding &
  Tenders Portal", /data), and the logo (its own `hover:no-underline`, not a card). Links inside links: 0 on every page.

| Kind | Pages | Result |
|---|---|---|
| Home tiles | `/` | fixed (above) |
| Home closing-soon rows | `/` | unchanged, already by the rule: only the title is the link (meta and deadline are not), and it underlines on its own hover like any text link. |
| TenderCard | `/tenders`, buyer record (its tenders) | fixed; the buyer link and "View original" inside it underline on their own hover only. |
| CallCard | `/funding`, funding record ("related") | fixed |
| BuyerCard | `/buyers` | fixed |
| OrgCard | `/organisations`, networks pages (same constants; the demo data shows no cards there) | fixed |
| Calendar entries | `/calendar` | fixed (row tint) |
| Funding calendar rows | `/funding?view=calendar` | fixed (row tint) |
| Search results | `/search` | fixed (row tint) |
| CPV code rows | `/cpv` | fixed (row tint) |
| Cards that contain links but are not links | `/data` source cards, `/about`, `/check`, `/readiness*` entry cards, `/changes`, `/digest`, `/market`, `/companies` and `/suppliers` lists (tables), record pages (facts, related blocks), footer | unchanged: hovering the card changes no text; each text link underlines on its own hover; buttons and pills keep their own hover. |
| Menus | header (own `hover:underline`, kept), account menu, pagination, pills (own `hover:no-underline`), companies tabs | unchanged, except the companies tabs (`/companies`, `/suppliers`, ...): they say `no-underline` and now really have none; their hover stays the colour change to `--ink` they declare. |

Keyboard: the site's `:focus-visible` outline is unchanged on every link; in addition the home tile and the list cards draw their hover
edge on keyboard focus, and the link rows their tint.

## Tests

- New `web/e2e/wp118.spec.ts` (desktop project; hover is a pointer state, so the 375 px touch project skips it): home tiles in the light
  and the dark theme (hover: border changes, no element in or around the tile underlined; keyboard focus: `:focus-visible`, the edge,
  the outline), a tender card (card hover; then the buyer link and "View original" each underline alone; focus on the title draws the
  card edge), a funding card, a buyer card, an organisation card, a search result row, a calendar entry, a funding calendar row, a CPV row,
  a /data source card (not a link: hovering it changes no text; its link underlines alone), a running-text link still underlined at rest
  and on hover, no link inside a link on five pages. The underline check reads each element's own `text-decoration-line` and those of the
  card's ancestors (a decoration propagates, it is not inherited into the computed style).
- Red before the fix: the same spec on a build of the integration versions of the changed files: 7 failed (tiles light and dark, tender,
  funding, buyer, organisation cards: 3 to 4 underlined elements each; rows: no change on the box), 2 passed (the guard tests).
- No existing test changed.

Batched scope (owner rule), demo build: `npx tsc --noEmit`, `node scripts/run-checks.mjs`, `npx next build`, and Playwright
`e2e/wp118.spec.ts`, `layout.spec.ts` (card edge on hover), `wp55.spec.ts` and `wp58.spec.ts` (running-text underline), `wp117.spec.ts`
(home tiles), `wp110.spec.ts`, `wp86.spec.ts` (search, CPV), `wp87.spec.ts` (calendar), `wp99.spec.ts` (funding calendar view).
Results: tsc 0, lib checks 0, build 0; Playwright 133 passed, 16 skipped (the touch project for wp118, and existing skips), 1 failed:
`wp86.spec.ts` "the header search and the home search" at 375 px timed out waiting for the menu's search field (a page this package did
not touch); alone it passed, and the whole of `wp86.spec.ts` again with 4 workers passed (13 passed, 3 skipped). Timing under load,
not a hover change.

## Open items

- Signed-in pages (`/app/*`) were not audited (sign-in is closed); they use the same card components.
- Funding calendar rows: a date block in the neutral tone uses the same inset tint as the hovered row, so on hover it merges with the
  row (its text stays). A different tint would be a colour change, outside this package.
