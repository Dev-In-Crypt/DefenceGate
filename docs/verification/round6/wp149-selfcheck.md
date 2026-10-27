# WP-149 self-check: design pass, phase 1 (home, /tenders, /readiness)

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP149.md` (owner-approved 27 Oct 2026). Branch `wp-wp149` on `integration`.
Nothing is merged or deployed until the owner approves the screenshots in `D:\DEFENCEGATE TESTS\wp149\shots\`.

## What the owner saw

1. Home: the search box stopped at 768 px (`max-w-3xl`) inside a 1200 px column, with its 12 px label 4 px above it. The box looked accidental.
2. /readiness: before the first question, a framed "Your answers are not stored on our server" box with its disclosure, then a framed
   scope box with two long links. At 1440x900 the first field sat at y = 845; at 375x812 the first step was off the first screen.
3. /tenders (same pattern): a 9-line search explanation under the search field in the filter column; on a phone a CSV card with a
   sentence of explanation stood between the sort and the first result, which started below the first screen.

## Rules applied

- **First-screen rule.** At 1440x900 and 375x812 the first screen holds the title, at most one line on what the visitor gets, and the
  service (search, list, first question). Explanations, scope, privacy reassurance and method go one click away, in one small line
  beside the action. Nothing legally required is removed; the privacy statement stays on the page with its full text behind the link.
- **Callout policy.** A framed `Callout` is kept for what changes what the visitor must do (a warning, a blocker). A reassurance, scope or
  method note is a `NoteLine`: a 16 px icon, one small sentence (14/20, muted), optionally a disclosure or link on the same line; an
  opened disclosure takes the full width under it.
- **Spacing scale.** Unchanged, the brand book's (4, 8, 12, 16, 20, 28, 48, 64 on Tailwind's scale). A label sits 8 px above its field
  (the page search; form fields elsewhere stay 4 px in phase 1, see phase 2). Sections 48 px apart (`main` gap-12), header to body 48 px.
- **Type scale.** Unchanged (brand book: display 56/60, h1 40/48, h3 20/28, body 16/24, small 14/20, label 12/16). Notes use small;
  the page-search label is small/600 instead of label 12/700, so it reads as a caption of a large control, not a form field.
- **Content widths.** 1200 px content box. The page search fills it (owner's WP-83 rule: text and controls take the full width of their
  block; no measure cap). A form stays at `--form-max` 560 px.
- **Controls.** The page search is the large size: 56 px field and button (the brand book's 44 px stays for form fields and the header).
- **Restraint (reference reading).** Stotles and Tussell home pages, read once each, read-only, robots.txt allowed both (Tussell
  disallows only preview paths): one headline, one sentence, one or two actions on the first screen; generous space; no caveat or
  method text above the action; one accent colour. Their cookie banners were not touched. Nothing copied.

## Token and component changes

No CSS token or Tailwind config change was needed: the brand-book tokens were right, the drift was in layout and in boxes of text.

| File | Change |
|---|---|
| `web/components/dg/site-search.tsx` | Page search (non-compact): label 8 px above a 56 px pill field that fills its column; Search button 56 px beside it, full width under it on a phone. Header search unchanged. Also applies to /search. |
| `web/components/dg/blocks.tsx` | New `NoteLine` (the callout policy above). `Callout` unchanged. |
| `web/components/dg/download-link.tsx` | `ResultTools compact`: one row of links (Download CSV, What the file holds, calendar), no card; a cut result is still said in full. |
| `web/components/dg/list-page.tsx` | The phone instance of the result tools (above the results) is `compact`. Applies to every ListPage list (tenders, buyers). The desktop card under the filters is unchanged. |
| `web/components/tenders/filter-bars.tsx` | The search hint is one line; the rest is a closed "What is searched" disclosure (`AboutData`). |
| `web/components/readiness/wizard.tsx` | Steps not reached yet are drawn in `--line` (they were `--surface-inset`, which equals the light page colour: invisible in the light theme). |
| `web/app/(public)/page.tsx` | Search without the 768 px cap, 32 px under the lead (40 from md; it was 20). |
| `web/app/(public)/readiness/page.tsx` | Privacy box and scope box replaced by two `NoteLine`s directly above the first step; shorter lead. |
| `web/app/(public)/tenders/(list)/page.tsx` | Shorter lead. |

Card hover rule untouched (no card markup changed). Both themes checked in the shots. No horizontal scroll at 320 px (new e2e check).

## Every text change (before -> after)

| Where | Before | After |
|---|---|---|
| /readiness lead | Answer five sets of questions (24 to 35 in all, depending on your answers) to see, programme by programme, whether your company can take part in EU defence funding and what to obtain first. | See whether your company can take part in EU defence funding and what to obtain first: five sets of questions, 24 to 35 in all. |
| /readiness privacy | Box heading "Your answers are not stored on our server" with the disclosure "What is kept and what is sent" | Line "Your answers are not stored on our server." with the same disclosure; the disclosure's two paragraphs are word for word unchanged (meaning unchanged) |
| /readiness scope | The questions below are for EU defence funding (the European Defence Fund, EDIP and SAFE). Something else? | For EU defence funding (EDF, EDIP and SAFE). Something else? |
| /readiness link 1 | I make parts or materials and want to supply defence buyers (one page, 17 to 53 questions) | unchanged words, now a link in the scope line |
| /readiness link 2 | A civilian manufacturer in Spain, such as an automotive supplier: what the check gives you | A civilian manufacturer in Spain |
| /tenders lead | Procurement notices from defence buyers in one list, each linked to its source with its changes kept: filter, then open a notice. | Procurement notices from defence buyers in one list, each linked to its source with its changes kept. |
| /tenders search hint | Searches titles in the original language and in English where TED gives one, buyer names, and the English names of the notice's product codes. Every word must match, in any order; the main product words (...) are also searched in other European languages. | Hint: "Every word must match, in any order." Disclosure "What is searched": "Titles in the original language and in English where TED gives one, buyer names, and the English names of the notice's product codes. The main product words (uniforms, spare parts, drones, fuel, ammunition and a few more) are also searched in other European languages." |
| Phone result tools (tenders, buyers) | The CSV sentence shown under the button | The same sentence behind "What the file holds" (new summary text) |
| Home | none | none (the owner's headline and lead are kept word for word; see open question 1) |

The question counts still come from `lib/question-counts.ts` (`rangeWords`), as `lib/wp131.check.ts` requires.

## Tests

- New `web/e2e/wp149.spec.ts` (both projects): home search spans the hero, 8 px label gap, 56 px controls, on the first screen; /readiness
  first step on the first screen, no `aside`, privacy line with its closed disclosure holding `data-what-is-sent`, scope line with both
  routes, one-line lead at 1440; /tenders first result on the first screen, phone tools without the card sentence, desktop search hint
  one line with the rest behind "What is searched"; no horizontal scroll at 320 px for the three pages.
- One existing assertion changed, on purpose: `e2e/wp90.spec.ts:71` pinned the 9-line search hint as visible text in the tenders filter
  form. It now checks the one-line hint is visible, opens "What is searched" and checks the same words ("English names of the notice's
  product codes") are visible there. Not loosened: the same text must still be on the form and reachable by one click.
- Every other pinned text holds unchanged ("Your answers are not stored on our server", "24 to 35 in all", "(one page, 17 to 53
  questions)", the supplier link name, /civilian manufacturer in Spain/, "Download CSV" before the first result, the owner's home lead).
- Results: see the final message of the builder (tsc, lib checks, build, the 53 specs that touch home, /tenders, /readiness, /buyers and
  /search at desktop and mobile-375).

## Phase 2 (proposal)

Same rule and components, page by page:

| Pages | What changes |
|---|---|
| /funding, /funding/closing-soon and the programme lists (call-list-template) | Search hint to one line plus disclosure; phone ResultTools `compact`; lead to one line. |
| Every form (`Field` in form.tsx) | Label gap 4 -> 8 px. Held back here: the folded funding form has a 1,700 px budget (wp47) and needs re-measuring with it. |
| /readiness/supplier, /readiness/spain-automotive, results, roadmap | Privacy and scope Callouts to `NoteLine` (wizard keeps the storage warning as a callout: it changes what the visitor must do). |
| /check, /organisations, /suppliers, /buyers, /calendar | Lead to one line; order and method notes to `NoteLine` or disclosure. |
| /search | Drop its `max-w-2xl` so the large search fills the column, as on home. |
| Tender, call, buyer and organisation pages | Title, status and deadline, value, buyer on the first screen; source and method lines under the facts. |
| /about, /methodology, /cpv, /privacy, the cabinet (`app/(app)`) and accounts-closed | Callout audit by the policy above; legal text untouched. |
| /market, /data, /digest, /changes, /pricing | First-screen check; intro paragraphs to one line plus "details". |

Estimate: phase 2 about 3 builder days (1 day lists and forms with the funding height budget, 1 day readiness family and detail pages,
1 day content pages, e2e and screenshots), plus one owner review round.
