# WP-39 self-check: data protection fixes (18 October 2026)

Package `wp39`, branch `wp-wp39` (from `integration` at 70fa80e), test database letter `r`, migrations 0080-0081.
Source of the defects: `docs/verification/product/verify2-abuse.md` (N1-N10 and the list of statements that are no
longer true). No language model was called. Production was only read (short `SELECT`s over the container's `psql`
with `default_transaction_read_only`, the API container's read-only role for timings); a scratch copy of five tables
and the `award` table (about 250 MB, database `scratch_r` in `dgate-ci-db`) was used for the measurements that need an
index or the new code. Person names are not written in this file: rows are cited by organisation id.

## Result per defect

| Id | Criterion | Met | Evidence |
|---|---|---|---|
| N1 | no e-mail address or telephone number in a supplier's `identifiers`; stripped at the loader; stored values cleaned | yes | `normalise_identifier` refuses `@`, a leading `+` and a `tel`/`fax` label, `awards.read_award` drops them and blanks them in the landed record, `awards.stated_number` stores only number-shaped values, `get_supplier` filters on output whatever the table holds. `ops/clean_suppliers.py` (dry run on the copy: 6 award rows with contact data on the 4 known organisations 430736, 420406, 427232, 430154; 420 stored values that are no number; 2 organisations lose a registration number made from a telephone number: 427232 and 430154). Tests: `test_wp39.py` (unit and integration), idempotent second run asserted |
| N2 | persons in the organisation directory: rule, hidden from directory, sitemap and pages, count on production, removal path | yes, with the limits below | `dgate/individuals.py`; column `organisation.individual_reason` (0080); `refresh_organisation_network` marks and leaves them out; profile 410, name "Name not shown" and no amount inside projects, partner lists (now read from the directory table), call partner suggestions (`partners.py`), analytics, `/v1/organisations/resolve`, supplier list and profile. Removal sentence on `/organisations/<slug>` and in the directory footnote; the page `RemovedOnRequest` has its own words for it. Count: **710 of 73,347 (0.97 %)** on the copy of production; the verifier's 1.0 % (3 of 300) agrees |
| N3 | a suppression clears `organisation_network` and what is derived | yes | trigger `organisation_network_drop` on `organisation.suppressed` (0080) deletes the merge family's rows in the same transaction, whoever sets the flag; `suppress lift` rebuilds the table. Tests: add, merge family, lift, hand-set flag |
| N5 | the group rule holds through list filters and sort; the list is capped | yes | `list_suppliers`: a `country`/`cpv` filter that selects fewer than 3 suppliers answers `withheld: true` with no items, whatever `sort`; the group is judged without the search word; `MAX_OFFSET = 500` (page beyond: 422, the last page is cut at the cap). Cap chosen because the table is 4,186 suppliers (42 requests of 100) and nobody reads past a few pages; narrowing reaches every supplier that is not in a small group, so it is a price, not a barrier (said in `DATA_PROTECTION.md`). The "no ranking" sentence on `/suppliers` is reworded to what is true |
| N7 | a page past the cap answers 404, not "Could not load" with 200 | yes in code; not run in a browser | `organisations/page.tsx` and `suppliers/page.tsx` catch the API's 422 and call `notFound()`; `tsc --noEmit` and `npm run check` pass; the Playwright specs were not run (CI only) |
| N8 | placeholders, consortium strings and mojibake do not become supplier rows; stored rows cleaned by an idempotent tool | yes | `awards.clean_supplier_name`; counters `skipped_placeholder`, `skipped_consortium_string`, `skipped_garbled`, `skipped_contact_in_name`; a role note after one company ("- Lider") is stripped and the company kept. `ops/clean_suppliers.py` marks `award.excluded_reason` (rows kept; every supplier query skips them): on the copy **139 award rows in 106 organisations** (35 consortium strings, 98 role notes, 5 placeholders, 1 garbled), 76 notices that name a consortium or carry a role note could be read again (owner decision, below) |
| N4 | partner tab, supplier list with q on deep pages, `/changes.atom` under 1.5 s cold; expensive ones priced | partly | see the timings; the unfiltered `/v1/changes` window is **not** under 1.5 s cold (2.1 s) |
| N9 | Storage Box host and real-looking person data out of tracked files; history not rewritten | yes in the tree; history needs the owner | below |
| N10 | HEAD on `/v1/*` | yes | `hardening.HeadAsGet`, tested in unit tests and with real `uvicorn` on both HTTP implementations (httptools, h11): `curl -I` answers 200 with the GET's headers, no body, no protocol error |
| EDF | e-mail addresses out of the factsheet text before it is stored, landed or sent | yes in code | `edf_factsheets.read_pdf` redacts `layout` and `plain`; a name such as `SYSTEM@TIC PARIS REGION` survives (tested). Stored data: `project_factsheet.facts` has no address (0 of 283; the 2 rows with "@" are that brand name), so nothing to clean in the database. The landed text in the raw store (`edf_factsheets/`) is unredacted for the 283 files already read: not touched (owner) |
| Texts | `DATA_PROTECTION.md` corrected; privacy page 1.6 as a draft | yes | below |

## Measurements on real data (read-only)

* **Persons in the directory.** 73,347 organisations in `organisation_network`. The rule marks 710 (0.97 %): 705 by name, 4
  by a sole-proprietor form, 1 by an owner in parentheses. They hold about 960 participations in about 880 projects and about EUR 122 million of
  EU contribution (counted on 699 before the last five names were added); **none** is also a buyer of a notice or a supplier with an award; all 699 have a PIC.
  Countries (699): DE 167, NL 78, PL 58, AT 55, IT 51, GB 45, FR 42, ES 35.
* **Hand check of 15 flagged rows (organisation ids, verdict person = yes/no):** 370650 yes, 390375 yes, 407859 yes,
  408514 yes, 422141 yes, 369245 yes, 380487 yes, 417744 yes, 419766 **no** (the Hellenic Red Cross, "Stavros" is a given
  name; the word is now a marker), 413922 yes, 401412 yes, 415473 yes, 412608 yes, 406662 yes, 416774 yes. **15 unflagged
  candidates:** 409665, 380211, 5426, 167389, 361177, 386628, 253500, 410800, 32870, 416764, 390620, 375197, 402888, 381989,
  395491: all organisations (correctly left alone).
* **Rates on fresh samples** (taken before the last five names were added to the list): of 100 flagged names 3 were
  organisations and 7 businesses named for their owner (hidden on purpose); of 150 unflagged candidate names (two to four
  plain words, no organisational word) 5 were persons the list does not know (Arabic, Albanian, Chinese, Indian and a few
  western names). So about four persons in five are found among Latin-script names and about one organisation in thirty is hidden by mistake.
  Not measured: names in other scripts (the sources transliterate most).
* **Suppliers** (copy of `award`, 9,826 rows): `clean_suppliers` dry run in 2.6 s: 6 rows with contact data, 420 values that are no number,
  139 rows excluded; `mark_individuals` dry run over 73,347 names in 4-6 s.

### Timings and plans

| Path | Before (production, idle host unless stated) | After |
|---|---|---|
| Partner tab, biggest organisation (CNRS, 4,336 projects, 9,663 partners) | 0.41 s warm; 1.3-5.0 s cold under load (verifier) | pages read from disk for the same query on the copy: **9,835 -> 4,058** (join the narrow `organisation_network` instead of `organisation`) **-> 1,446** (two partial covering indexes, 0081, 12 MB each); warm 656/264 ms -> 224/197 ms. The cold figure itself cannot be reproduced on this host (the page cache is warm and may not be dropped on a production machine): the claim is 85 % fewer disk reads, not a cold time |
| Supplier list, `q=co&sort=name&page=40&pageSize=100` | 1.09 s idle (3.2 s under load, verifier) | refused in a few ms (offset beyond 500). The deepest page that is still served (page 5 of 100): a query of the same shape as page 1, 0.7-0.8 s on production |
| Supplier list with a country filter | 0.21 s | + one group-size count: 20-70 ms warm (0.68 s the very first time) |
| `/v1/changes` unfiltered | 2.1 s first, 1.2 s filtered; `EXPLAIN`: the amended scan alone is 1.03 s (index-only scan of 307,843 versions, hash anti-join with 333,494 notes: the 12-13 October re-derivation sits in the 14-day window) | computed **once per five minutes per (scope, country, goods)** for every page, page size and the Atom feed (`changes.window_events`); priced 5. **Not under 1.5 s cold**: the miss still costs about 2.1 s until the re-derivation leaves the window (27 October); the feed itself is cached five minutes by the site |
| Prices (`hardening.request_cost`) | 1 token each | partners 5 (+2 with a filter), analytics 8, suppliers 3 (+2 q, +2 filter), organisation/project/supplier profile and directory 2, `/v1/changes` 5, organisation and project slug lists 20 |

## Hostile review of my own diff

Eleven issues found and fixed: (1) the first `HeadAsGet` closed the response on every body message and broke under the real middleware stack
(only a run of the real app showed it; the unit test now stacks `SecurityHeaders`); (2) the project page still showed the amount received by a
hidden person; (3) `/v1/organisations/resolve` confirmed a person by name; (4) the call partner suggestions (`partners.py`) read the participations and
listed persons; (5) an empty group and a small one must not read alike: "withheld" is for a group of 1-2 suppliers, a group with none is plainly empty (it keeps the
e2e wording "No suppliers match"; that a small group exists is not a secret, any supplier is found by name); (6) the role-note stripper changed names that had none (trailing punctuation); (7) read-level versus store-level identifier
rules clashed with existing tests: contact data is dropped when read, a non-number when stored; (8) `refresh_organisation_network` must keep its two-key result; (9)
ambiguous short given names (a Turkish or Dutch word, an acronym) hid organisations: removed from the list; compound words ("Filmuniversitat") needed stems;
(10) two older tests asserted the behaviour the fix removes (a lingering directory row after a suppression; a two-supplier country listed): changed to the
new rule with a comment, not weakened; (11) `HEAD` rewrites only `/v1/`.

## Tests

* Added: `tests/unit/test_wp39.py` (103 cases) and `tests/integration/test_wp39.py` (21 tests). Changed: `test_hardening` (the change feed costs 5),
  `test_network_api` (the entry itself clears the directory row), `test_supplier_map` (a three-supplier scenario needs `K_MIN` = 1 to test the filters),
  contact fixtures of `test_boamp`, `test_aid`, `test_ncbr`, `test_vinnova` (N9).
* Red before, green after: a set of behaviour checks that import nothing the package added (profile shows no telephone number, a suppression clears the
  directory table, a two-supplier country is not listed, a sixth page of 100 is refused, HEAD is not 405, a placeholder is no supplier, a factsheet text has no
  address) failed 7 of 7 on `integration` (fresh database) and passed 7 of 7 on the branch.
* Whole suite on the server at the final commit (log kept as `/root/dev-r/full_run_wp39.log`): `ruff check .` clean, **2,606 unit and 1,024 integration tests, 0 failed**;
  `tsc --noEmit` and `npm run check` in a `node:22-alpine` container pass (run before the last, text-only edits of the privacy page and the one-line `withheld` change).
* Scratch left on the server for the owner to delete (listed in `docs/DELETION_CANDIDATES.md`): `/root/dev-r` (backend, infra, one log), `/root/run_r.sh`, database `agent_r`. Removed by me: database `scratch_r`
  (copy of five tables, `award` and 6,481 `opportunity` rows, 280 MB), `/root/r-scratch` (exports of organisation names and the hand-check lists), `/root/dev-r-base`, the web copy with its `node_modules`.

## N9: what was changed in tracked files

* `docs/verification/product/wp36-selfcheck.md`: the Storage Box host name and the server's address removed.
* `docs/DATA_PROTECTION.md`: the path of the plaintext dump removed (the file stays on the host for the owner to delete).
* `backend/tests/unit/test_boamp.py`: the contact block of the French ministry (a person's name, telephone number and e-mail address that look copied
  from a live notice), the mayor's mailbox and telephone number, the Digne and Roquebrune numbers, two role mailboxes replaced by invented values on
  `example.invalid` and the reserved fictional French numbers (01 99 00 xx xx). `test_aid`, `test_ncbr`, `test_vinnova` (+ the integration pipeline): three
  person-shaped addresses on real domains moved to `example.invalid`. The assertions are unchanged in meaning.
* **Needs the owner's decision (not done, no history rewriting):** the old values stay in git history and on the public GitHub repository (commits
  29cd66d, 32f457f, 5e49469 for the Storage Box host; the BOAMP fixture since its first commit). Removing them means rewriting history and force-pushing
  `main`, or accepting that a host name alone is not a secret (access needs the key) and that the fixture person may be invented. Also: the unredacted raw
  store (EDF factsheet text, the telephone numbers typed into identifier fields in `ted_awards/` bundles, the pre-sweep payloads) and the plaintext dump on the host.

## The texts

`DATA_PROTECTION.md` (every statement in the verifier's list is rewritten with its date): the alias count (172), the dump path, persons in the directory
(measured), the supplier identifiers, "no ranking, share or total" (the list shows a count of notices and can order by it), the OpenAI section (the factsheets,
283 files, sent before the e-mail removal), "nothing is public except `/v1/*`", the profile requests. **Privacy 1.6** is a DRAFT: page source, static copy
`docs/legal/versions/privacy-v1.6-2026-10-18.md`, `PRIVACY_VERSION = "1.6"`, README and lawyer item P8; the page lead carries the visible placeholder
"[date to be set when it is approved]"; nothing is marked published. What changes in the wording:

1. Lead: version 1.6.
2. Section 4: "the only items it ever stores" becomes "the items"; adds `dg.profile.v1` (what it holds, that it stays on the device, how to erase it); adds a paragraph on how a saved readiness profile reaches the server (the verdict request; the fit-facts and partner requests that are made without being asked only when a profile is saved, so the server can tell that a visitor has one, not who).
3. Section 7: sole traders and freelancers; a new bullet on suppliers and project participants (what is shown, that natural persons are left out by a rule on the name with its miss rate of about one in a hundred, that a telephone number or address in a number field is not shown, how to ask for a removal).
4. Section 8: OpenAI for two purposes (call documents and the EDF factsheets, with the table of participants), that factsheets read before 18 October 2026 were sent without e-mail removal, and a visible placeholder for the transfer mechanism to the United States (to be confirmed with the lawyer).

## Not checked / not met

* The cold time of the partner tab (explained above), the unfiltered change feed under 1.5 s (not met until 27 October), a browser run of the 404 and of
  the new sentences, the Playwright specs (CI only), the effect of the two new indexes on the production planner (measured on a copy with the same data, not on production).
* Whether the 283 EDF factsheets printed any address; the raw store and the Storage Box; whether OpenAI keeps anything; legal sufficiency of the wording.
* The rule on names is a rule: it misses about one person in five among Latin-script names and a script other than Latin is not read.
