# WP-48 self-check: branded select, record pages centred, deadline block, home hero, CI e2e

Branch `wp-wp48` (from `integration` da8e0ae). Layout and components only; no wording changed (the CPV finder link and the home links moved, their words are the same).
`tsc --noEmit`, `npm run check` (all `lib/*.check.ts`) and `next build` ran on the server in `/root/dev-w48` (node:22-alpine): all green on the final commit. Playwright cannot run on the server and was not run anywhere; see "Not run" below.

## 1. Branded Select (every select in the app)

`components/dg/select.tsx` (new, client): `ListboxSelect`, a WAI-ARIA select-only combobox over the native `<select>`. `components/dg/field.tsx` (new): `Field`, `boxCls`, `CONTROL` moved out of `form.tsx` so both files share them. `Select` in `form.tsx` renders `ListboxSelect`; `SortSelect` (`components/funding/filter-panel.tsx`) and the `/suppliers` order select, which were bare `<select>`s, use it too. `grep "<select\|<option" app components` finds only `select.tsx`.

Uses covered (all through `Select`/`ListboxSelect`): tenders, funding, organisation and market filters (currency, minimum, maximum, programme, country, year), sort on lists, home finder, `/changes`, `/digest`, readiness wizard (size, country, management country, one status select per requirement), eligibility check, partner suggestions, networks filters, consortium gaps, account profile, saved searches, shortlist, suppliers order.

How it works
- The native select stays in the form, first in the DOM. The label points at it; GET forms, server actions, `FormData` and the filter panel's `change` listener keep working. The custom control writes `select.value` and dispatches a bubbling `change` (so controlled `value`/`onChange` callers work unchanged).
- No script: the native select is the control (it now has option colours: `bg-surface text-ink`).
- With script and a mouse (`pointer: fine`): the native select becomes `sr-only` (not focusable, `aria-hidden`; a focus on it moves to the button), and a `button role="combobox"` shows the value. Its name is the hidden label text plus the value (`data-value` holds the value). The list is a fixed-position portal on `document.body`: not clipped by the sticky, scrolling filter column; it flips above the button when there is less room below; it follows the button on resize and on scroll of any parent.
- Keys: Down, Up, Enter, Space open; Home, End; letters search (labels that start with them, then labels with a word that starts with them; a repeated letter steps through the matches; a space inside a search is a letter); open: Up, Down, Home, End, PageUp, PageDown, Enter or Space choose, Escape closes, Tab chooses and moves on. Focus never leaves the button (`aria-activedescendant`), so focus "returns" after a choice or Escape by construction.
- Look: Manrope (inherited), `--surface` background, `--ink` text, `--edge` border, `--shadow-menu` (new token, light and dark), rows 44 px, hover/active `--surface-inset`, selected: bold plus a check in `--accent-text`; maximum height 352 px (8 rows), scrolls; `fit` sizes a non-full-width select to its longest option so the box does not change width with the choice.
- Phones: `(pointer: coarse)` keeps the native select. Reason: the system picker (wheel or full-screen list with search) is better than a second picker in a 375 px window, is read correctly by VoiceOver and TalkBack, and is never clipped. Its options carry our colours and the page sets `color-scheme`, so the opened system list is dark in the dark theme. The closed control is the same branded box.

Measured (built-in browser, build served from the server through an SSH tunnel, mock data)
- `/changes` at 1333: click opens 32 rows (31 countries and the placeholder), row height 44, menu 352 high (max), page scroll height and width unchanged; click on an option sets value DE and the native select to DE, focus stays on the button; `ArrowDown`, `p o l` jumps to "Poland (PL)", `Tab` commits PL and moves to the next field (native PL); `End` then `Escape` closes without changing the value.
- Dark theme (data-theme=dark, computed styles): menu background rgb(29, 52, 40) = `--surface`, text rgb(238, 241, 234) = `--ink`, font Manrope = body font. (A screenshot of the dark list was not taken: the capture of the pane lagged the theme change.)
- `/tenders` sort select in the sticky filter column: menu is a child of `body`, at x 1088 to 1325 in a 1333 window (clamped), 3 options, selected one marked.
- Mobile preset (375): `pointer: coarse` is true, no `role="combobox"` button, the native select is the control, no horizontal scroll.
- Observation: on `/tenders` (it has `loading.tsx`, so the list streams in a Suspense boundary) the built-in browser pane hydrated the boundary only after a click; that is the pane throttling idle hydration, not the select (a click opened the list at once).

## 2. Call and tender pages (`DetailLayout`, `SectionNav`)

Cause found: the index was bare text in a 200 px column, flush with the container edge, while the main and side parts are cards. The visible block therefore started at the first card (x 560 at 1920) and ended at the container edge: left margin to the first box about twice the right one. Not a container error (the grid fills the 1296 px box).

Change: the index is a card like the others (`border-edge`, 20/24 px padding), column 224 px (was 200). From xl: index card, text, side card fill the container; below xl the index card sits in the side column under the facts. `d-top` card padding 12/16 → 16/20.

Measured on the built mock site, call `1-edf-2026-additive-manufacturing-spare-parts`, in an iframe with a 15 px scrollbar (so equal margins differ by up to 1 px): left margin of the index card / right margin of the side card: 1280: 32 / 32; 1333: 32 / 32; 1440: 64 / 65; 1920: 304 / 305. Cards start and end where the header bar starts and ends (32-1233, 32-1286, 64-1360, 304-1600). Index link inset from its card: 17 px. Deadline block 24 px from the top of its card (side), 17 px of card around it on a phone (call and tender, 375): 17 / 17 / 17 / 17. No horizontal scroll on any of these at 375.

The "deadline block on the divider": the tinted (closing soon) fact of a list card (`ListFact`) and of `FactCell` had the next fact's hairline directly under it (2 px at xl, 0 when stacked). Now `mb-4` (and `mt-4` when not first; side by side from sm there is no line). Measured on `/funding` (6 closing-soon cards): gap tint → next divider 16 px at 375, 1280 and 1920 (side by side at 800: no divider). List cards at 1280: 187 / 189 / 229 (min / median / max; before 187 / 187 / 223-227); at 375: 429 / 499 / 541 (before 429 / 463-483 / 497-525, the tinted cards grew by 16).
Facts grid cells: `Fact` and `FactCell` already share `py-3` and the hairline above; only the tinted cell differed, and it now has its space.

Organisation, project and buyer pages: they are cards and facts inside `main`, with margins equal by construction (checked at 1333, 375); they do not use `DetailLayout` and have no deadline block. Left unchanged.

## 3. Home hero

The four links (All current tenders, Funding calls, What changed, "Free to browse. No account needed.") are now in the left column under the lead; the finder is one row (three fields and the button) and "Not sure of the code? CPV finder" moved into the row under it, with the "Open now" examples. Same words. Measured at 1280 / 1333 / 1440 / 1920: left column 265 px, figures 265 px, same top and bottom (balanced; before, the left column ended at 345 with the figures going down to 437). Hero 497 px (limit 760 in wp46). Three parts list top 785 px (before 835; the U15 limit is the window height, 800); 375: hero 1221, list top 1529 (limit 2 x 812). Hero keeps the card padding (24) and a 20 px row gap.

## 4. CI e2e (run 39155688480, five failures, three causes)

| Test | Cause | Fix |
|---|---|---|
| networks.spec.ts:84 desktop, the H2020 table | WP-47's `DataTable` named the table by its region label ("Funding by year, Horizon 2020"); the caption "Horizon 2020: projects and EU contribution per year" was lost | `DataTable` takes an optional `caption`; `FundingChart` passes the old caption. Code fix, test unchanged. |
| networks.spec.ts:84 mobile, 396 px scroll | The sr-only header of the bar column is absolutely positioned inside a scroll box that was not `relative`, so it was not clipped and sat at x 395 | `ScrollBox` is `relative` now (all tables that scroll sideways). Checked: scroll width 360 of 360 (was 395) on `?tab=funding`; no scroll on 4 other pages at 375. |
| ux.spec.ts:237 U10, desktop and mobile | WP-46 changed the default on purpose: with no defence-programme project the page opens on all programmes and says so | Test rewritten, not weakened: the default URL asserts "Showing all programmes", the sentence about EDF/EDIDP/PADR and the link back; `?programme=EDF` asserts the old sentence ("All programmes together hold 1 more project") and the "Show all programmes" link and table |
| ux.spec.ts:296 U15 desktop | Three parts list at 895 px (limit 800) | Layout, see 3: list top 785. The assertion is unchanged. |

New `e2e/wp48.spec.ts` (9 tests, not run): listbox look and no shift, dark theme colours, keyboard search and the value reaching the form (Apply, URL `country=PL`), mouse choice (native on the phone project), call page margins at 1280/1333/1440/1920, deadline 16 px, phone deadline card padding, tinted fact gap, profile funding no sideways scroll, hero links. Existing tests that use `getByLabel(...).selectOption(...)`, `toHaveValue` and `getByRole('combobox', ...)` still resolve to the native select / the combobox button; the `sr-only` native select is skipped by the 24/32 px target scans (they skip `.sr-only`) and the combobox button is 44 px.

## Hostile review of my own diff

Found and fixed: (1) the menu's own scroll re-placed it and snapped the active row back into view (scroll listener now ignores events from the menu, in-view effect depends on open/active only); (2) a space opened the list on keydown and the button's click on keyup would close it again in Firefox (keyup default prevented); (3) the home hero change first cost more than it saved (the CPV link row came back as a row of its own in the mock) and U15 stayed at 803, found by measuring, fixed with padding; (4) a first baseline build was contaminated because I synced files while it ran: discarded. Known and left: controlled selects that reject a change show the new value until the next render (the per-render sync corrects it); a custom listbox is not announced identically by every screen reader (not tested); the e2e `getByLabel` of a `SortSelect` depends on the native select being the first labelable element in its label (comment in the code).

## Not run

- Playwright, any spec (the 292 existing and the 9 new): CI runs them after the push. If a check of mine fails in CI the likely candidates are the 1 px tolerance in the margin test and `pointer: coarse` on the mobile project (true in the built-in browser's mobile preset).
- Firefox, Safari, a real phone, a screen reader.
- A screenshot of the dark list (computed colours only).
- 2000 px exactly (1920 measured; the margins are equal by the same rule).
- The owner's numbers (77 / 213 px at 2000) could not be reproduced on this build: the grid fills the container and the margins are equal. The visible asymmetry was the unframed index, fixed as above.

Scratch on the server: `/root/dev-w48` (955 MB, mostly a copy of `node_modules`; delete when done). No container left running.
