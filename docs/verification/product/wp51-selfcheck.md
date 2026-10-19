# WP-51 self-check: the Web CI green again

Branch `wp-wp51` (from `integration` d8c3be7). CI run on d8c3be7: 7 failures. Here, on the server in `/root/dev-w51` (Playwright 1.51.1, Chromium in a `node:22-bookworm-slim` container, CI's env: `DG_USE_MOCK=1`, `NEXT_PUBLIC_DG_NOW=2026-10-12T08:00:00Z`, `NEXT_PUBLIC_SITE_URL`, `E2E_PACE_MS=0`, one worker, `next start` of a fresh `next build`): the whole suite, desktop and 375 px, **324 passed, 18 skipped, 0 failed** (342 tests, 13.7 min). `tsc --noEmit` ok, `npm run check` exit 0, `next build` ok. The 18 skips are the viewport skips the tests declare themselves (`test.skip(isMobile ...)` and the reverse); the same ones as in WP-50 minus two.

## A. The measure tests (3 failures)

`e2e/layout.spec.ts:51`, `e2e/wp45.spec.ts:28`, `e2e/wp47.spec.ts:122` asserted "no paragraph wider than 681 px". The owner's commit 77ca9c6 set `--measure: 100%` on purpose, so the tests encoded the old rule. Not touched: the CSS.

New rule, one helper `paragraphsOutsideFrame(page, { skip?, minLength? })` in `e2e/helpers.ts`: a visible paragraph of `main` may be as wide as the content frame, but its left edge is not left of the header's left edge and its right edge is not right of the header's right edge (1 px tolerance). Same filters as before where the test had them (wp47: not in `table, nav, [role=region], article, .reading`, text over 120 characters). Kept unchanged in those tests: the frame equals the header (layout), "nothing scrolls sideways" (`visit()` checks `scrollWidth <= clientWidth` on every page), the sticky contents list, the page lists. Titles and comments updated; the wp45 title "a 680 px column" is now "the text column"; `web/README.md` no longer says 680 px for `max-w-prose`. `web/lib/tokens.check.ts`, `globals.css` and `tailwind.config.ts` were already correct (the owner's commit updated them; no 680 px claim is left in `web/`). The `docs/verification/...` older self-checks keep their 680 px text: they describe what was true when written.

## B. The currency tests (4 failures: 2 tests x 2 projects)

Reproduced on the server: the address changed (`?currency=PLN`) and the list was filtered, but the card poll never became true. Debug runs (cards printed after the choice) showed the filtering correct: 2 PLN notices, 2 SEK calls, "Topic budget SEK 60,000,000" in the card. **Cause: the test, not the code, and not the selector.** `e2e/wp49.spec.ts` lines 46, 62 and 99 contained a literal backspace character (0x08) in front of `PLN` / `EUR` / `SEK` in the regexes: an intended `\b` that was turned into a control character when the file was written (the heredoc `\b` trap from the data-quality notes). The regex could never match, so the positive assertions failed. The EUR test (line 62) was a negative assertion and passed for the same wrong reason; with `\b` it now really asserts that no card states PLN or SEK, and it passes.

Fix: the four 0x08 characters replaced by `\b`; no assertion weakened or changed otherwise. `selectOption`/the `choose` helper was already right (the select is the labelled native control, `getByRole('combobox', { name })` finds it and our listbox works on desktop; `selectOption` on a phone). No code, mock or url-state change was needed: `lib/mock/tenders.ts` and `lib/mock/calls.ts` already apply a currency alone, and `lib/wp49.check.ts` covers the parser.
A scan for other control characters (`[\x00-\x08\x0b\x0c\x0e-\x1f]`) over `e2e`, `lib`, `components`, `app`, `scripts` found nothing else.

## Not run

- Firefox, WebKit, a real device.
- The CI itself (it runs after the push; no push from here).

## Environment

Load on the server was 7 to 13 during the run (the production web container and other work; my Chromium and `next start` were part of it); available memory never fell below 1.2 GB. Scratch removed at the end: `/root/dev-w51`, image `w51-pw`, container `w51-run`.
