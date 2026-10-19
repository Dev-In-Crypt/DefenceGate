# WP-58 self-check: accessibility and interaction (key `wp58`)

Branch `wp-wp58`, from `integration` 161b689. Web only. No wording changed except accessible names and one new link text that only shows when it has keyboard focus ("Skip to results"). Nothing deployed, no model call, no secret, production not touched.

## How it was measured

On the owner's instruction of 19 October (server rescale), everything ran **on the laptop** in `D:\DEFENCEGATE TESTS\wp58`: two production builds of the mock site (`DG_USE_MOCK=1`, `NEXT_PUBLIC_DG_NOW=2026-10-12T08:00:00Z`, `NEXT_PUBLIC_SITE_URL=https://ci.example.test`, the CI's settings), "before" = `integration` 161b689 on port 3157, "after" = this branch on 3158, both `next start`, Node 24, Playwright 1.51.1 (Chromium 134). axe-core 4.14.0 from a local copy (`crawl/axe-core`). The script `crawl/axe.js` runs the audit's rule set (wcag2a, wcag2aa, wcag21a, wcag21aa, best-practice) on the audit's **31 page types x {1333, 375 px} x {light, dark} = 124 runs**, then counts prefetch requests per load and Tab presses from the top of `/funding` to the first call link, and reads list-view titles. The mock has 22 calls and 11 tenders, so production pages are longer; the rules are the same.

## Before / after

| Measure | Before (161b689) | After (wp-wp58) |
|---|---|---|
| axe runs / errors | 124 / 0 | 124 / 0 |
| axe violations (nodes) | `landmark-unique` (moderate) 8, on `/suppliers` in all 4 width/theme runs | **0** |
| `link-in-text-block` (production audit L5) | 0 in the mock (WP-55's underline rule already covers `li > a`) | 0 |
| Prefetch requests per load, desktop: tenders / funding / buyers / organisations / suppliers / home | 16 / 16 / 16 / 16 / 16 / 18 | **9 / 8 / 8 / 8 / 10 / 11** |
| Tab presses to the first result on `/funding`, 1333 / 375 px | 59 / 23 | **21 / 11** ("Skip to results" is stop 16 / 6) |
| Titles: `/tenders?page=2`, `?country=DE`, `/funding?page=2`, `/buyers?country=PL`, `/organisations?country=DE`, `/suppliers?country=DE` | all the same as page 1 of their list | "Tenders, page 2", "Tenders in Germany", "Funding calls, page 2", "Buyers in Poland", "Organisations in Germany", "Supplier map in Germany" |
| Tender page links under 32 px outside a sentence (3 tender pages x 2 widths) | 6 (the buyer link after "Buyer:", 22 px) | **0** |

## What changed, per task

1. **Branded select** (`components/dg/select.tsx`). Measured first (`crawl/axprobe.js`, Chromium 134): a `<select>` reports `expanded=false` whatever the markup says, plain, with `role="combobox"` or `size=1`, because Chromium reads its own system popup, which never opens here. So `aria-expanded=true` on the select cannot reach the accessibility tree. The fix follows the system menu instead: **while the list is open, focus is on the listbox** (`tabindex=-1`, `aria-activedescendant` = the active option, name = the label). A screen reader then reads a focused listbox and its active option; Escape, a choice and Tab put focus back on the select (Tab and Shift+Tab move on from the select, tested); a blur to anything but the select closes the list. The select keeps `aria-haspopup`, `aria-expanded` (DOM, true while open, used by the e2e) and `aria-controls` (only while the list exists, so never dangling). The native select is still the one labelled control, so `getByLabel`, `selectOption`, `toHaveValue` and the helpers of wp48/wp49 are unchanged and pass.
2. **Focus.** Escape on a link of a header menu returns focus to the menu's button (`header-bar.tsx`, 3 lines; the brief reserves this file for navigation wiring, the change is local to the Escape handler). New `components/dg/route-focus.tsx` in the public layout: after a client-side change of the **path**, focus goes to `#main h1` (`tabindex=-1` added), or to `main` if there is none; not on the first load (the skip link stays the first stop), not when only the query changes (filters keep focus on their control), not when the page already put focus inside `main`. "Mark as done" (WP-53): checked only; `readiness.spec` "focus to the next step heading" passes.
3. **Radio-group error**: `Fieldset` takes `id`, `hint`, `error`; hint and error are inside the fieldset and named by its `aria-describedby`; the wizard's radios get `aria-invalid` while the error stands. The legal-form error was a loose `role=alert` paragraph after the group. The other radio groups (filters, calendar, account profile) have defaults and no error state. **Landmarks**: the two tables of `/suppliers` had the same name as their cards ("By CPV division" region inside the "By CPV division" section): table regions renamed "Suppliers and wins per ...". `Callout` (`aside`) is named by its title (home, `/readiness` and 10 other uses).
4. **Titles**: `listViewTitle()` in `lib/seo.ts`, used by the five list pages through `buildMetadata` (WP-56's trim kept; the short part comes first so a long search is cut, not the page number). **`lang`**: the breadcrumb takes `lang` (tender, tender evidence and call pages); the title links of "What changed" entries (tenders and calls) carry it. Cards and page h1 already had it. Digest and supplier-page notice titles: the API gives no language there, left. **"View original"**: the inline source line takes `subject`; list cards pass their title, so each link is "View original: <title>, at <source> (opens in new tab)" (hidden text, with `lang`).
5. **"Failed to fetch"**: `assess()` turns a request that gets no answer into `AssessError` with the existing sentence; the three hooks show only our messages; the call-page readiness block and the partner suggestions use the standard `ErrorState` (heading level set to fit the block: h5 / h3). **Prefetch**: the 8 links of the closed header menus are not prefetched (16 -> 8-10 per list page). **Skip to results**: a visually hidden link, visible on focus, before the chips of the call lists and first in the filter column of the tender and buyer lists; the results region is its target (`id=results`, `tabindex=-1`). DOM order and layout unchanged.
6. **WP-55 leftovers**: the `/digest` empty-state link is underlined (`.run-text` on the empty/error state text, added to WP-55's rule); the tender page buyer link has the 8 px padding (38 px).

## Tests

- `lib/wp58.check.ts` (in `npm run check`): `listViewTitle` for 9 views, through the real filter parser and `buildMetadata`'s trim; `assess()` on a rejected fetch, an abort and a 502.
- `e2e/wp58.spec.ts`, 12 tests x desktop and 375 px (3 desktop-only skips on the phone): the select's focused listbox and its active descendant in the CDP accessibility tree, Escape returns focus; Tab / Shift+Tab from the open list; header-menu Escape; focus on the h1 after a route change and not on first load; the legal-form group; 8 list titles; `lang` on the h1 and the breadcrumb; distinct "View original" names; Skip to results; the failed check; the `.run-text` underline; the buyer link height. **Against the before build 20 of the 21 run tests fail** (the Tab test passes there too: it guards the new focus move). No existing assertion changed.
- Laptop run (16 CPUs): `tsc --noEmit` exit 0; all 28 `lib/*.check.ts` pass (run with `D:\DEFENCEGATE TESTS\wp58\run-checks-win.mjs`, a copy of `scripts/run-checks.mjs` that calls `tsc.cmd` through a shell: the repo script spawns `npx` without a shell, which fails on Windows for every check); `next build` exit 0; **full Playwright suite, 4 workers: 432 passed, 37 skipped, 3 failed**:
  - `wp55` "first visit: the system scheme decides ..." desktop and 375: **fails on the before build too** (4 of 4 runs on each build, `--repeat-each=2`): the theme-color meta is the dark colour under a light system in this laptop Chromium. Not caused here; worth a look on CI.
  - `wp49` "a radio applies at once" (desktop): passed 6 of 6 on a re-run with 1 worker (a timing test, also seen flaky under load in WP-55).

## Hostile review of my own diff: 5 issues found, 5 fixed

1. My first select fix (`role="combobox"` on the select) did nothing in the tree (probe): replaced by the focused listbox.
2. The short title "Suppliers" broke the supplier pages' title rule (`/supplier map/i`, 18 failures): the short form is "Supplier map".
3. "Skip to results" first in the filter column still left 28 stops on `/funding` (header, breadcrumb, 12 chips): moved before the chips (21 in all).
4. The accessibility-tree helper of the new spec took the document (also "focused") for the focused node: it skips `RootWebArea`.
5. The title of `ErrorState` is an `h2`; inside the call page's readiness block (under an h4) that broke the heading order: `level` prop added.

## Left, with reasons

- The select's own `expanded` state stays false in Chromium's tree (a browser rule, measured). Firefox and Safari were not tested, nor any real screen reader (NVDA, JAWS, VoiceOver): the pattern is the system menu's, but unverified with AT.
- Prefetch on home is 11 (not a list page): the 8 visible header links and the page's own links.
- Mixed-language strings inside an English title (TED's "Country – CPV text – original" form, audit L4) cannot be split without guessing; `lang` is set where the API states the title's language.
- Digest items and supplier-page notice rows carry no title language in the API.
- Not run: the axe run against production (production read-only; the mock covers the same page types), Edge, Firefox, Safari.

## Scratch

Laptop: `D:\DEFENCEGATE TESTS\wp58` (`crawl/` scripts and the axe-core copy, `out/` results: `before.json`, `after.json`, `pw-full2.log`); `node_modules` and `.next` of both builds deleted after the run. No Docker container was created. Server: `/root/dev-w58` (the source copy uploaded before the switch) deleted.
