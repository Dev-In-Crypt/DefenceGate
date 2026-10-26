# WP-146 self-check: a filter radio clicked before hydration is lost (wp49:86 on phones)

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP146.md`. Branch `wp-wp146` from `integration` (9c4295c). Test copy
`D:\DEFENCEGATE TESTS\wp146\` (web only; no backend change, no migration, no ops module, no Postgres). Production not touched.
Files: `web/components/funding/filter-panel.tsx` (the fix), `web/e2e/wp146.spec.ts` (new), this file. Nothing of WP-144 or WP-145.

## Before

`D:\DEFENCEGATE TESTS\wp106\e2e.log` and `e2e-repeat.log` (26 Oct): `[mobile-375] e2e/wp49.spec.ts:86 "a radio applies at once"`
failed in two full runs and once in 4 repeats; the URL's `status` stayed null for the 3 s of the poll.

## 1. Cause (proved)

Every live filter form (tenders, funding, buyers, suppliers, calendar, organisations) goes through one hook, `useLiveForm` in
`filter-panel.tsx`. It listens for the form's native `change` with `addEventListener` inside a `useEffect`, so the listener exists
only once the form's subtree has hydrated and its effects ran. A tap before that checks the radio (a plain GET form, the DOM
works) but its `change` event fires with nobody listening; when the listener arrives the form already shows the new value, it
equals nothing it compares against, and no request is made. The radio stays checked over a list that ignores it.

Evidence, on the unfixed build (`D:\DEFENCEGATE TESTS\wp146\before-wp146.log`):
- New `e2e/wp146.spec.ts` holds the page's script chunks back (`page.route`), makes one change, checks React had not reached the
  control yet (no `__reactFiber` key: true in every case), lets the scripts run and waits until the form is hydrated: the change
  is never applied. **12 of 12 failed** (6 controls x desktop and mobile-375: tenders radio, checkbox, select; funding radio;
  buyers checkbox; suppliers text box), `Received: null` each time.
- CPU throttling alone does not reproduce it (`probe.log`, a scratch spec outside the repo running the wp49:86 steps with
  `Emulation.setCPUThrottlingRate`): 4x 20/20 and 10x 20/20 passed, although React had not hydrated the radio at the click in all
  40 runs. Once React's root is running, a discrete event on a not-yet-hydrated part makes React hydrate it synchronously and run
  its effects before the `change` fires, which rescues the click. So the click is lost only while the form's code is not there
  yet (its chunk still loading, or the scripts not run): what a busy run (4 workers, a full suite) and a slow phone network give,
  hence a flake on mobile-375 and not a constant failure. The same unfixed build passed wp49:86 20/20 on an idle machine
  (`before-wp49.log`).

## 2. Fix (product, shared hook)

`useLiveForm`, right after it attaches its listeners, looks for controls the visitor changed since the server's HTML
(`changedSinceLoad`: a checkbox or radio whose `checked` differs from `defaultChecked`, a select whose default option is no longer
selected, a text or date box whose value differs from its `defaultValue` and that does not have focus). React's hydration leaves
both the user's state and the defaults alone (react-dom 19 `initInput` with `isHydrating`; selects are not touched), so the
difference is exactly the early change. It is applied as its own event would have been: a checkbox waits the usual 400 ms for
the next tick, anything else goes at once; `go()` still sends nothing when the form equals the address.
Left alone: a search box (it applies on Enter, which submits the plain GET form natively before hydration), a box still being
typed in (it applies when left, as before). No-JS behaviour unchanged (still the GET form and its button). wp49:86 and its 3 s
timeout and assertion are unchanged.

## 3. The other instant-apply filters

All of them use the same hook (`FilterPanel` for tenders, buyers, funding, calendar, organisations; `LiveForm` for suppliers), so
the one change covers them; the new spec checks tenders, funding, buyers and suppliers. `SortSelect` (outside the form) and the
CPV/deadline preset pills are links or apply on their own event; the pills are plain links and work before hydration.

## Tests

`e2e/wp146.spec.ts`: the 6 early changes are applied after hydration (each within 3 s); with nothing changed, hydrating the four
pages makes no request and no history entry (guards against a false "changed" from a select without a default); a text box still
being typed in is not applied by hydration, only when it is left.

## After

Fixed build, `D:\DEFENCEGATE TESTS\wp146\` (`final.log`; web-build.lock held for every build and browser run):
- `tsc --noEmit` 0; `scripts/run-checks.mjs` 0 (all lib checks); `next build` 0.
- `e2e/wp146.spec.ts e2e/wp49.spec.ts e2e/funding.spec.ts e2e/suppliers.spec.ts e2e/networks.spec.ts`, both projects, 4 workers:
  95 passed, 1 skipped (funding.spec.ts:72 skips itself off desktop, as before) (`after-specs.log`).
- `--repeat-each=20 --workers=4`, `e2e/wp146.spec.ts` + `e2e/wp49.spec.ts:86`: mobile-375 **180/180 passed** (`rep-mobile.log`),
  desktop **180/180 passed** (`rep-desktop.log`): wp49:86 20/20 on each, every wp146 case 20/20 on each.
