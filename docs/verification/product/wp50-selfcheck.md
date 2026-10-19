# WP-50 self-check: the Web CI green again

Branch `wp-wp50` (from `integration` d23b5e2). CI run on d23b5e2 (Web, run 39221502289): 9 failures, 303 passed, 20 skipped.
Here, on the server in `/root/dev-w50` (Playwright 1.51.1, Chromium in a `node:22-bookworm-slim` container with the CI's env: `DG_USE_MOCK=1`, `NEXT_PUBLIC_DG_NOW=2026-10-12T08:00:00Z`, `E2E_PACE_MS=0`, one worker, `next start` of a fresh `next build`): the whole suite, desktop and 375 px, **312 passed, 20 skipped, 0 failed** (332 tests, 16.5 min). `tsc --noEmit`, `npm run check` and `next build` green (the build ran before the removal of one unused variable in `select.tsx`; `tsc` and `check` ran after it).

## The causes (one was not what the brief guessed)

| Failure | Cause | Fix |
|---|---|---|
| wp48 x4, ux U11 (`getByRole('combobox', { name })` not found) | The branded select was a `button role="combobox"` over a hidden native select, and its name came from a `sr-only` span inside it. A combobox does not take its name from its content (ARIA; Playwright follows it), so the control had no accessible name: not findable by role and name, and a screen reader got an unnamed combobox. | The button is gone, see below. |
| ux U16 (`getByLabel(...)` `toBeFocused` after a refused Next) | The wizard focuses the first `[aria-invalid]`: the hidden native select, which handed focus to the button. The label led to the native one, focus was on the button. | Same fix: one element. |
| routes `/market` desktop and mobile (`getByLabel('Buyer country')` 2 elements) | **Not the select.** The table under the filters is a scroll region labelled "Notices published by buyer country, ..." (a substring match). It failed on the phone too, where there is no combobox. | The test uses `exact: true`; the region label is a good label and stays. |
| wp45 `/regulation` at 375 px, median entry 936 px (limit 900) | See "/regulation". | Layout. |

## The select (`web/components/dg/select.tsx`)

Design change: the native `<select>` is now **the** control, not a hidden carrier. With script and a mouse (`pointer: fine`) a press on it does not open the system menu (`mousedown` default prevented, the select takes focus) but opens our listbox (the same portal, rows, keys, colours and positioning as in WP-48). The select gets `aria-haspopup`, `aria-expanded`, `aria-controls`, `aria-activedescendant` and `data-value`; its keys are handled (they never change the value by themselves; a choice sets the value and fires a bubbling `change`). The `button`, the `sr-only` hiding, the `aria-hidden`, the focus redirect, the name span and the `fit` / `controlClassName` props (the native box sizes itself to the longest option and carries the same classes) are removed; the two callers (`SortSelect`, the suppliers order) lost those props.

Why this and not "move the id and label to the button": any second element that has a name from a label, `aria-label` or `aria-labelledby` is found by `getByLabel` and by every label-based lookup as a second control; moving the label to the button would make `selectOption` / `toHaveValue` (used all over the e2e) fail on desktop. With one element: label, name (role `combobox`, name from the label), value, focus, form field and `selectOption` are the same node on desktop, on a phone and without script. The closed control is identical in all three (same classes), so there is no layout shift on hydration either (the only change at mount is attributes).
Phones keep the native picker (`pointer: coarse`), as before.

Tests: no assertion changed for the select. `e2e/wp48.spec.ts` (written for the button) passes unchanged: 'combobox' with the name finds the select, `data-value`, `aria-expanded`, focus after Escape and the 44 px box hold. U11 and U16 pass unchanged.
One test line changed (`e2e/routes.spec.ts`, `/market`): `getByLabel('Buyer country', { exact: true })`, with a comment. It selects the same control more precisely; the assertion (`toHaveValue('PL')`) is the same.

## /regulation at 375 px (`app/(public)/regulation/page.tsx`, `components/regulation/entry-list.tsx`)

What an entry is on a phone: text 301 px wide (page gutter 16 + card padding 20, each side), a summary of 13 lines (338 px) for the median entry at 16/26, a 2-column facts list in which "Source" and "On this site" were squeezed to 150 px and wrapped to 115 px rows, and a "Status" fact that repeats the status tag at the top of the same card. No text was cut; the limit stays 900.

Changes, phone only (below `sm`; from 640 px nothing changed):
- card padding 20 -> 16 px (text 309 px wide);
- the summary's line height 26 -> 24 px (16 px text, 1.5);
- the "Status" fact is not shown (the tag above says the same word; it stays in the page for larger screens);
- facts in this order: "Last checked" beside "Source" on one row, "Who is affected" and "On this site" a full row each.

Measured in the built-in browser on the mock build at 375 px (17 entries): median 936 -> **832** (entries 758-1398 before, 665-1282 after). In Playwright's Chromium the test passes. CI's numbers were within 0-26 px of mine on the same entries (CI 936 for the median, mine 936), so the margin to 900 is about 70 px.
Desktop (`/regulation` median <= 420, page <= 8000) passes: unchanged.
Not done, to avoid cutting the summary: a line clamp with "read more" (the longest entries stay 1,280 px; the median is what the test measures).

## Hostile review of my own diff

Found and fixed: (1) a first version left `shown` (the label of the selected option, only used by the button) unused: removed; (2) with a native select as the control the browser would also change its value by itself on a key (left/right on a closed select, a type-ahead that differs from ours): every key we handle, and every Arrow, Home, End, Page key, Space and Enter, is prevented, so the value only changes through `choose()`; (3) `mousedown` on a select that is `disabled` never fires, but `rest.disabled` is checked anyway; (4) the "press outside closes" handler now treats the select as inside, and a second press on the select closes the list (toggle on `mousedown`, not on `click`).
Known and left: Enter on a closed select opens the list instead of submitting the form (as before); I did not test a screen reader, Firefox or Safari (Chromium only); `aria-activedescendant` on a native `<select>` is allowed by the ARIA in HTML table but support differs between screen readers.

## Not run

- Firefox, WebKit, a real phone, a screen reader.
- `next build` after the final one-line removal of an unused variable (tsc and the checks ran after it).
- The CI itself (it runs after the push).

## Environment note

The server was loaded by other work during the run (load 8-12, two other `next build`s and integration tests); I waited for the other builds to end before the Playwright run and the load was mostly theirs, but it did exceed 8 during part of the 16 minutes. Free memory never fell below 700 MB available. Scratch: `/root/dev-w50` (about 1.9 GB with the copy of `node_modules` and the Chromium cache), the image `w50-pw`, the container `w50-site`: all deleted at the end.
