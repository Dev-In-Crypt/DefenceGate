# WP-43 self-check: the five findings left open by the third verification

Builder: WP-43, 18 October 2026. Branch `wp-wp43` (worktree `C:\Users\DEV\PROJECTS\milgrants-wp43`), from `integration` a8c5365.
Findings: `verify3-fixes.md` (N4, N1/R2) and `verify3-live.md` (4, 5, 9 and the product-search row of 3.9).
Read-only on production: SQL with `statement_timeout` 30 s and `default_transaction_read_only`, and the public CORDIS SPARQL
service (robots.txt read first, one request a second, the project's User-Agent). No write, no deploy, no restart, no model call,
no secret read. Nothing is pushed or merged. Tests run on the server in `/root/dev-w43` with database `agent_wp43` (not
`/root/dev-int`, so that WP-42 and this package cannot overwrite each other's copy).

## 1. N4: the country of a body (CSIC under Italy)

**Cause.** The first CORDIS load took the address of the PIC record. CSIC's record is contradictory (address "Trento, IT", site
name "... Madrid ES", VAT ESQ2818002D). WP-41 wrote the rule (`cordis.seat_country`) but its only path to the stored rows is the
next CORDIS load or `pipeline cordis-countries --yes`, and that has not been run. And `organisation.country_basis` was NULL on all
429,129 organisations, which a reader cannot tell from "never looked at".

**The rule (deterministic, no model, nothing merged).** For an organisation that holds a PIC, from its CORDIS record:

| basis | when | country |
|---|---|---|
| `address` | one address country, nothing in the record contradicts it | that country (new value, migration 0090) |
| `vote` | the site name's country and the VAT prefix agree against the address | that country (CSIC: ES) |
| `several` | sites in several countries, nothing decides | the first alphabetically; all in `country_sites` |
| NULL | not looked at | unchanged |

One voice against the address is not enough (CrowdHelix; EurOcean's Dutch site with a Portuguese VAT number): the address stays.
An undisputed address never overrules a stored country that has no basis (it may have come from the buyer side); that case is
counted (`address_differs_kept`). The profile API now serves `countryBasis` and `countrySites` and the page says so for `vote` and
`several`; the sentence "CSIC appears under Italy" on the site is replaced by the rule in words.

**Before and after, measured offline on production data (read-only).** I read the 72,534 organisation records from the service (15
requests, 18 MB, kept in scratch) and ran the rule against the 72,199 organisations that hold a PIC:

| | before | after `org_countries --yes` |
|---|---|---|
| `address` | 0 | 72,197 |
| `vote` | 0 | 1 (CSIC: IT -> ES; its 2,054 projects move from Italy to Spain) |
| `several` | 0 | 1 (EurOcean: NL, sites NL and PT) |
| NULL ("not looked at") | 429,129 (every organisation) | 356,930 (no PIC, or merged away) |
| stored country differs from an undisputed address | | 0 found |

Not in the table: 315 CORDIS records without a PIC or a name, and 20 records whose PIC the table does not hold. The command prints
`basis before` and `basis after` itself.

**Contradictions I looked for besides the CORDIS record, and left alone.** A rule from the name alone is not safe: 107
organisations have a name ending in a two-letter code that differs from their country (mostly the legal form "SE"), and the 21
groups whose name holds another country's word (about 35 organisations) are local subsidiaries and branches named after the
parent's country ("TUV AUSTRIA ROMANIA SRL" in RO, "Saab Finland Oy" in SE). Seven organisations carry a VAT prefix other than
their country: CSIC (fixed by the vote), Centre Scientifique de Monaco (Monaco uses French VAT numbers), EurOcean (`several`), two
Mexican tax numbers that only look like a prefix, McKinsey Belgium (US stored, BE VAT, "BELGIUM" in the name) and the European
Institute for Health Records (BE VAT, FR stored). The last two have one voice in the record and stay for a person to judge; the
WP-41 doctrine (one signal is not enough) is kept. I read the 70 biggest organisations of the directory by eye: no other
contradiction.

**Why not "the country its projects state most":** the participation table holds no country per participation (CORDIS gives it per
organisation; EDF factsheet countries are only used to resolve), so there is nothing to vote with.

**Command (not run):** `python -m dgate.ops.org_countries` (dry run, prints `basis before/after`), then `--yes`.

## 2. N1: the amounts that differ from CORDIS

**Cause found.** `SUM(?amt)` of the roles query is taken over the rows the other patterns multiply. A role node that points to
**two organisation nodes** (`isRoleOf` twice; usually the real organisation and a bare reference with no description) is read
twice, so its payment came out doubled. On 18 October 207 of 398,584 roles are such (found with `HAVING COUNT(DISTINCT ?o) > 1`;
in 168 of them one node is bare, in 33 both are described). Evidence on the service: the role of CEA (PIC 888898201) in ENEN2plus
(project 242772) has `isRoleOf` the CEA organisation and `isRoleOf` a node that has no triple at all, one payment of 46,017.5; the
old query returned `amount 92035`, the new one `amount 92035, orgs 2`, read as 46,017.5. NATURE-ETN (227112): Warsaw 454,957.20 ->
227,478.60 and a second row 549,604.08 -> 274,802.04. Other multipliers I measured and ruled out: a payment with two values (0
payments), a role with two labels (0), a project with two `rcn` (0). A role with two payments (35) is legitimate and summed. A role
with two projects (3 roles) is handled by the same division.

**Fix.** `cordis._query("roles")` also returns `COUNT(DISTINCT ?o)`, `COUNT(DISTINCT ?p)` and the node that has a description
(`real_org`); `role_record` divides the sum by the product and takes the real node. (Before, `MIN(?o)` could pick the bare node,
the role was "unlinked" and the participant was lost: 48 of the 173 roles that carry a PIC are not stored at all.) The roles query
costs 8.7 s a page instead of 5.9 s (live, 5,000-row page, host load 5 to 9).

**Repair of the stored rows.** `python -m dgate.ops.repair_role_multiples [--yes]` (one request, dry run by default) finds the stored
participation by project and PIC (through the live organisation) or, for an organisation without a PIC, by the doubled figure in
that project and role (only when exactly one participation holds it), takes the surplus out, and settles the project again with the
rules of `repair_contributions` (a project that stops exceeding its total gets its amounts back). A figure that does not hold the
doubled amount is left alone and counted. Simulated read-only on production with the 207 roles:

| | roles |
|---|---|
| read from the service | 207 |
| with a PIC | 173: 125 participations stored, 124 hold the doubled figure, 1 has no amount; 48 are **not stored** (their bare node sorted first) |
| without a PIC | 34: 17 found by amount (exactly one holder), 8 none stored, 9 ambiguous (left; a full load corrects them) |
| EUR taken out of stored amounts (PIC rows) | 117.8 million, mostly CEA: project 242744, CEA 118,350,935.20 (withheld as "exceeds project total") -> 59,175,467.60 |

Of the 6 of 70 rows the verifier found: ENEN2plus (CEA) and NATURE-ETN (Warsaw) are this cause: fixed. MedMaD (172,750.08), RECOMBINE
(41,400) and E-TANDEM (240,750) are what the service states today (I read the roles of those three projects on the service); the
CORDIS page was amended later. SLAFNET: the service states IRD as coordinator at 441,000, equal to ours; the verifier's INRAE row is
not in the project's data (one participant of 121,500 is a bare node, see below). ZAHYR (8,500) and ILLINVESTMENTS (171,791.76): the
page shows EUR 0 because the participation ended; the open data holds a role with the project's end date and no end of
participation (all triples of the ZAHYR role read), so **this part is not fixable from the open data**.

**Found on the way, not fixed:** 16,012 roles (4.0 per cent) point only to a bare node with no description, so the participant
cannot be named or stored (SLAFNET has one at 121,500). They are the `roles_unlinked` of the load report and are written up in
`docs/sources/cordis.md`.

**Commands (not run):** `python -m dgate.ops.repair_role_multiples` (dry run), then `--yes`; later, a full
`python -m dgate.pipeline cordis` (the monthly job: about 80 role pages at 8.7 s, 15 organisation pages, the projects), which
corrects the 9 ambiguous rows and stores the 56 lost roles.

## 3. The organisation directory counts defence projects

**Change.** `organisation_network.defence_projects` (migration 0090, filled by the migration and by every rebuild): projects of
EDF, EDIDP, PADR with the same live-organisation and family rules as `projects`. API `GET /v1/organisations`: `defenceProjects` in
each item, `sort=defence`, and when `sort` is not given the order is `defence` if the `programme` filter holds only defence
programmes, else `projects`; `meta` carries `sort`, `defenceProgrammes`, `countsNote`. Page: in the defence scope (the default) the
first figure of a card is "Defence projects", the others are labelled "Projects, all programmes", "Coordinated, all programmes",
"EU contribution, all programmes"; over all programmes it reads "Projects" and "Of which defence". The sort menu has "Most defence
projects first". The profile header gets a "Defence projects" cell next to "Projects, all programmes".

**Before and after (production, read-only, the same counts the migration writes).**

| rank | now (all-programme total) | after (defence projects) |
|---|---|---|
| 1 | CNRS 4,336 | Leonardo 74 (of 74) |
| 2 | Fraunhofer 2,739 | Indra 64 (of 229) |
| 3 | KU Leuven 1,616 | Fraunhofer 59 (of 2,739) |
| 4 | Copenhagen 1,363 | TNO 46 (of 942) |
| 5 | Delft 1,240 | AIT 43 (of 455) |
| 6-10 | DLR, INSERM, Milano, TNO, KTH | Thales SIX GTS 33, Safran Electronics & Defense 33, Airbus D&S 31, Saab 31, Elettronica 31 |

CNRS: 10 defence projects of 4,336 (what the verifier found). 1,689 organisations in the defence scope, 825 of them with only defence
projects. The migration's `UPDATE` ran as a SELECT in 1.2 s on production; the list query is the existing one with another ORDER BY
on 1,689 rows (the existing plan: index scan, 0.5 ms; the sort of 1,689 rows is below that of the planning time).

## 4. The funding list is in the first HTML

**Cause.** `app/(public)/funding/(list)/loading.tsx` wraps the page in a Suspense boundary. The server sent the skeleton in place and
the list as a hidden block (`<div hidden id="S:n">`) that a script swaps in. The call titles were in the response (4 times on the
live `/funding?status=open`) but not in the visible markup: no scripts, no list. `/tenders` and `/buyers` have the same shape
(0 visible tender links before the first hidden block); not touched, outside this finding.

**Fix.** The file is removed (the layout keeps the 308 for a page past the end). Measured on a production build with the demo data
(what CI builds): `/funding?status=all` has 10 call links before the first hidden block and no "Loading funding calls" anywhere.
Cost: while a slow answer loads, a client navigation keeps the page it is on instead of showing a skeleton. New e2e tests: the raw
response holds a call link before any hidden block; with scripts off the list, the count and the filters are there. They were not
run here (Playwright and a browser do not fit the server's memory next to the test runs); the build and the checks that CI runs
before them were.

## 5. The supplier product search

**Change.** `web/lib/data/product-keywords.json` (9 entries, 41 phrases, codes and English titles from the OP-TED codelist the
finder already cites, retrieved 18 October) is read first by `cpvForWords`: the whole query must be listed phrases, otherwise the
finder's titles are searched as before. Mapped: drone/UAV/unmanned aircraft -> 35613000 Unmanned aerial vehicles + 34711200
Non-piloted aircraft; explosives -> 24600000; pyrotechnics/flares -> 24613000; detonators/fuses -> 24615000; propellant ->
24611000; body armour/armor/bulletproof/ballistic vest -> 35815000 Garments for anti-ballistic protection; tank -> 35411000 Battle
tanks (with a note on how to reach heating tanks); armoured vehicle -> 35410000; ammo -> 35330000. The status line reads "“drone” is
read as 35613000 Unmanned aerial vehicles; 34711200 Non-piloted aircraft ... Filtering by the prefixes 35613, 347112." Awards in the
archive carry these codes as main CPV: 24600000 (24), 24613000 (18), 24615000 (10), 24610000 (3), 35613000 (55), 34711200 (11),
35815100 (109), 35815000 (15), 35411000 (3), 35412000 (16). Checked on the demo build (rendered page): drone, explosives, body armour
and tank give the status line above; "drone zzzz" (not a listed phrase) and "ammunition" behave as before. A test checks that every
code is 8 digits and, where the finder holds the code, that the title is the finder's.

**"Nammo Palencia" repeated wins: the duplicates are real, in part.** Org 429464, 12 awards (notices):

| procedure identifier | notices | published | value | lots |
|---|---|---|---|---|
| 629ec203-... | 7 (343515, 344320, 344925, 345357, 345482, 346174 on 28 May 2025; 361305 on 4 June) | same title (equal md5), same buyer | 1,984,400 each | 2 |
| ae232934-... | 2 (765260 on 18 November, 772945 on 21 November 2025) | same title | 572,500 each | 1 |
| three others | 1 each | | 1,730,000 / 3,492,700 / 814,000 | |

So "12 notices" are 5 procedures: the same procedure, supplier, value, lot count and title published up to 7 times (TED result
notices re-sent or amended; `related_native_id` and `twin_method` are empty, so nothing links them). Across the map, of 9,687
awards: **219 groups of identical content (same supplier, procedure, value, lots, main CPV and title) hold 466 rows, 247 of them
repeats (2.5 per cent), in 189 suppliers; the largest group has 7**. In all, 732 (supplier, procedure) pairs have more than one
notice; the others differ in value, lots or title (several contracts of one procedure) and are separate awards. Nothing was changed:
the "wins" count stays a count of notices, as the page says. An exact fix (count distinct procedure and content) changes
`awardCount` and the order by wins; I did not make it.

## Tests

Added: `tests/unit/test_wp43_money.py` (7), `tests/integration/test_wp43_money.py` (7), `tests/integration/test_wp43_directory.py`
(9); in `web`: `lib/cpv.check.ts` (the curated words and the list's integrity), `lib/networks.check.ts` (the directory's default
sort and its URLs), e2e `funding.spec.ts` (2), `networks.spec.ts` (2), `suppliers.spec.ts` (4). Changed on purpose, none weakened:
`tests/unit/test_wp41_money.py` and `tests/integration/test_wp41_money_country.py` (an undisputed address now has the basis
`address`, not NULL; a new test for the country that is kept), `e2e/ux.spec.ts` (the CSIC sentence), `tests/fakecordis.py` (the
stand-in recognises the roles query by its subject, now that the query contains `COUNT(DISTINCT`), `lib/networks.check.ts` (the
default sort of the directory is `defence`, so `none.sort` and `orgApiQuery(none)` changed). `addopts` untouched.

## Results (on the server, `/root/dev-w43`, database `agent_wp43`)

- `ruff check .`: clean.
- `pytest` (unit): 2,822 passed. `pytest -m integration`: 1,075 passed (the whole suite, 3,897 tests; the integration run took 30
  minutes with the host under load; the files I changed after it started were run again, all tests of `test_wp43_money.py`, `test_wp43_directory.py`, `test_wp41_money_country.py` and `test_network_api.py` passed).
- Web, in a `node:22-alpine` container with the CI's dependencies: `npx tsc --noEmit` clean (it also type-checks the e2e files);
  `npm run check`: all 20 `lib/*.check.ts` ok; `next build` with the demo data (`DG_USE_MOCK=1`, the CI's environment) ok, and the
  built site served: `/funding` 10 call links before the first hidden block; `/organisations` card labels as above;
  `/suppliers?product=` drone, explosives, body armour, tank, "drone zzzz", ammunition as in section 5.
- Playwright (the e2e specs): not run, see section 4. A spec I could not run is a risk: the selectors follow the existing ones
  (`getByText(..., { exact: true })` inside `getByRole('article')`, `getByLabel('Sort')`, `getByRole('status')`).

## Hostile review of my own diff

I read every changed file again. 11 issues found, 11 fixed or documented:

1. The repair skipped a role whose organisation has no PIC, which is exactly NATURE-ETN's Warsaw row (found by looking up the
   verifier's example in the 207 rows): it now finds the participation by the doubled figure, only when exactly one holds it.
2. `tests/fakecordis.py` took any query holding `COUNT(DISTINCT` for a count and any holding `e:Organisation .` for the
   organisation list; the new roles query holds both strings. The stand-in now reads the subject of the query.
3. The partial index on `defence_projects` could never be used by the planner (the list filters on `programmes`): removed from the
   migration.
4. The new web sends `sort=defence`, which the old API answers with 422: the deploy order is in the commands.
5. Running the repair before the new loader is live would be undone by the next old load: in the commands.
6. The profile header said "Projects 4,336" beside no defence figure: it now has "Defence projects" and "Projects, all programmes".
7. The site's own `CountryNote` still said CSIC appears under Italy: rewritten, and the e2e that quoted it.
8. A regex with raw combining characters in `lib/cpv.ts` (invisible in review): `\p{M}`.
9. ruff F811 on fixtures imported from another test file: the fixtures are bound by assignment.
10. A float compared with `numeric` in the by-amount lookup: a 0.006 tolerance.
11. My first write of `cordis.py` converted its line endings to CRLF on Windows (git would have shown the whole file as changed): converted
    back; the diff is 49 lines.

Left on purpose, and said above: the 56 lost roles and 9 ambiguous rows need a full load; `/tenders` and `/buyers` keep their loading
file; the wins count counts repeated notices; the unmatched VAT-prefix and name contradictions are for a person. N+1: the
repair does one lookup per role (207), the list query is one statement, the profile query count is unchanged. Grants: no new table;
the new column is read through the existing grants on `organisation_network`.

## Production commands (the orchestrator runs them; none was run)

1. Deploy the backend first, then the web (the new web sends `sort=defence`, which the old API refuses with 422), and do not run
   the repair before the new loader is live (the old monthly load would double the amounts again). Migration `0090` runs with
   `migrate`: a constraint is dropped and re-added `NOT VALID` then validated (about 1 s on 429,000 rows), a column is added and
   `defence_projects` is filled (1.2 s).
2. `... run --rm --no-deps worker python -m dgate.ops.repair_role_multiples`, then again with `--yes`. Expected dry-run counters:
   `roles 207`, `matched 142`, `corrected 141`, `not_stored 56`, `ambiguous 9`, `by_amount 17`, `no_pic_unmatched 17`. Writes about
   140 participation rows and rebuilds the directory table (seconds).
3. `... python -m dgate.ops.org_countries`, then `--yes`. Expected: `countries_changed 1`, `bases_set` about 72,198,
   `organisations_country_by_vote 1`, `organisations_several_countries 1`. 15 requests, one a second.
4. Later: `python -m dgate.pipeline cordis` (the monthly job) corrects the 9 ambiguous rows and stores the 56 lost roles.
5. Check: `GET /v1/organisations?programme=EDF,EDIDP,PADR` starts with Leonardo, `defenceProjects 74`; the CSIC profile says
   `country ES`, `countryBasis vote`; `/funding?status=open` shows call links without scripts.

Disk: no new table, one 4-byte column on 72,000 rows. Scratch to delete: `docs/DELETION_CANDIDATES.md` (WP-43).

## Not met / not checked

- ZAHYR and ILLINVESTMENTS (EUR 0 on the page where a participation ended): not fixable from the open data.
- MedMaD, RECOMBINE, E-TANDEM: the service itself states our figures; the page differs.
- The 9 ambiguous no-PIC roles and the 56 roles never stored are corrected only by a full CORDIS load.
- `/tenders` and `/buyers` still use a loading file (the same hidden-block behaviour).
- Playwright was not run (see 4). `tsc`, all 20 `lib/*.check.ts` and a production build with the demo data were.
- The "wins" count still counts repeated notices of one award (5).
- Navigation: no new route, no change to the header or footer.
