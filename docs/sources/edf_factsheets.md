# EDF project factsheets (`edf_factsheets`): who is in each selected project

Read on 17 October 2026. Connector: `backend/dgate/sources/edf_factsheets.py`; loader `backend/dgate/networks.py`
(`run_edf`); command `python -m dgate.pipeline edf`; monthly worker job `edf_monthly` (day 6). The model call is
`dgate.llm.complete_json` (task `edf_factsheet`, prompt version 1, strict schema); nothing here calls a model by
itself, and no live model run was made while building it.

EDF projects are not in CORDIS (the EDF is not a framework programme; grant numbers of EDF projects such as 101224281
and 101304876 do not exist in CORDIS). Each call year publishes a results page on the DG DEFIS website with one
factsheet PDF per selected project.

## What the plan said, and what is true

| Plan (M2-03, appendix Part III) | Found |
|---|---|
| Results page `.../funding-opportunities/calls-proposals/result-edf-YYYY-calls-proposals_en` | Holds for **2024 and 2025 only**. The five pages are at four different addresses (below). The crawler reads them from the site's `sitemap.xml`, which robots.txt allows, and tries the two known shapes for a year the sitemap does not list |
| File name `FACTSHEET_EDF_{YEAR}_{ACTION}_{CATEGORY}_{TOPIC}_{GA}_{ACRONYM}.pdf` | Holds for 2024 and 2025 (with exceptions: `FACTSHEET_EDF_2024_HYROGLIVE.pdf` has no grant number). 2023, 2022 and 2021 each use another convention (below). `parse_filename` reads all four; 25 real names are in the unit test |
| 57 projects for 2025 | The 2025 page links 61 factsheet files: 60 distinct acronyms and the GEDIRIS factsheet twice (`..._GEDIRIS.pdf`, `..._GEDIRIS_0.pdf`) |

Results pages (all `https://defence-industry-space.ec.europa.eu/...`):

| Year | Path | Factsheet links | File name convention |
|---|---|---|---|
| 2021 | `/funding-and-grants/calls-proposals/european-defence-fund-2021-calls-proposals-results_en` | 61 | `Factsheet_EDF21_<ACRONYM>[_0\|_updated].pdf` |
| 2022 | `/funding-and-grants/calls-proposals/result-edf-2022-calls-proposals_en` | 41 | `<ACRONYM> - Factsheet_EDF22[_0].pdf` |
| 2023 | `/funding-opportunities-0/calls-proposals/results-edf-2023-calls-proposals_en` | about 60 | `EDF-2023-<ACTION-CATEGORY-TOPIC> <ACRONYM>.pdf`, some `FACTSHEET_EDF-2023-<..>_<GA>_<ACRONYM>.pdf` |
| 2024 | `/funding-opportunities/calls-proposals/result-edf-2024-calls-proposals_en` | 63 | `FACTSHEET_EDF_2024_<tokens>_<GA>_<ACRONYM>.pdf` |
| 2025 | `/funding-opportunities/calls-proposals/result-edf-2025-calls-proposals_en` | 61 | `FACTSHEET_EDF_2025_<tokens>_<GA>_<ACRONYM>.pdf` |
| 2026 | none yet (the 2026 calls are open) | | |

Each page also links a general factsheet or a summary (`EDF 2025 results - general factsheet v7.pdf`, `EDF 2021 -
Summary of Projects_UPDATE.pdf`, `PESCO Related Projects.pdf`); these are skipped by name.

Only 2024 and 2025 names carry the grant number, so the deterministic join with Horizon grant numbers the plan counted
on exists for those two years only. The project key inside the loader is therefore `<call year>:<acronym without
punctuation>` (the grant number is stored when the name has it).

## The factsheet

A PDF of two or three pages. Page 1: acronym, full title, call title, topic title, duration, estimated total cost,
maximum EU contribution, and a technical description. The next pages: a table "Members of the consortium and country of
establishment" with `NAME` and `COUNTRY` columns and "(Coordinator)" marking the coordinator (before the name in 2024
and 2025, after it in 2021 and 2022). **There is no PIC, no amount per entity and no SME flag**; countries are written
in full ("Slovakia"). The plan's schema field `is_sme` is therefore null unless a factsheet says so.

Reading it: pypdf's layout mode keeps a table row on one line but splits a name wrapped over two lines around the
country; its plain mode keeps the wrapped name whole but loses the rows. The model is given the layout text; the quote
check accepts a name found in either. The technical description (everything after "SHORT DESCRIPTION OF THE PROJECT"
on its page) is cut before the text is landed or sent anywhere.

## The site limits the rate

Fetching the factsheets one a second, 125 of the first 284 downloads were answered HTTP 429 (after about a hundred).
`fetch_pdf` waits (the `Retry-After` the site gives, else 10, 20, 40 and 80 seconds), doubles the pause between
requests for the rest of the run (up to 10 s) and raises `RateLimited` when the site keeps refusing, which ends the run
as `partial` ("run again later"). A file read in the last 25 days is not fetched again unless `--reread` is given. A
full first load takes about 40 minutes; the first pass read 159 files in 8 minutes, the second 125 in 31.

The source is seeded inactive and switched on by the first run that read a factsheet (see `cordis.md`).

## What the 284 factsheets gave (17 October 2026)

Projects per call year: 2021: 60, 2022: 41, 2023: 61, 2024: 62, 2025: 60 (284 in all; 2021-2024 together 224, the figure
of the appendix). 4,139 participations. The appendix says 57 projects for 2025: the page holds 60 factsheets, among
them two continuation grants of the 2024 RESILIENCE project and one coordination action; whether those are "selected
projects" is not stated anywhere read.

## Safeguards (as in `dgate/eligibility.py`)

* A strict JSON schema with every field present and nullable; "never fill a gap" in the instruction.
* **Quote check**: every participant name must appear in the factsheet text; otherwise the entity is dropped and counted
  (`dropped_not_in_text` in the run detail and in `project_factsheet.dropped`). Duplicates, a country that is not a known
  name, and a second "coordinator" are counted too.
* The table of each factsheet is also read **without a model** (`table_rows`) and checked against the answer: a country
  the model pairs with a name differently from the name's own row is replaced by the printed one (`country_corrected`),
  and rows of the table that the answer leaves out are counted (`missing_from_answer`).
* Held by file hash and prompt version in `project_factsheet`: a file read in the last 25 days is skipped without a
  request; after that a run fetches it, sees the same hash and asks the model nothing.
* The model budget is the shared monthly cap (`DGATE_LLM_MONTHLY_CAP_USD`); reaching it stops the run as `partial`.
  A factsheet the model could not read, or one that gave no participants, makes the run `partial`, never a green tick.

## The twelve questions

| # | Question | Answer |
|---|---|---|
| 1 | Official open data page | The DEFIS results pages above (DG DEFIS, European Commission). Not an open-data portal dataset |
| 2 | API, bulk, feed | HTML pages with PDF links; no feed. The sitemap lists the pages |
| 3 | Registration | None |
| 4 | Format, specification | PDF, no specification; layout read from 5 files of 2021, 2022, 2025 |
| 5 | History | EDF 2021 to 2025 results (2021 calls decided in 2022, and so on) |
| 6 | Frequency, lag | Once a year per call, a few months after the call closes (2025 results published 15 April 2026, per the appendix) |
| 7 | Licence | Each factsheet says "© European Union. Reuse of this document is allowed, provided appropriate credit is given and any changes are indicated" (Commission Decision 2011/833/EU). Commercial reuse is permitted with credit; the attribution is stored in `source.attribution` |
| 8 | Rate limits | None stated. robots.txt (`defence-industry-space.ec.europa.eu`) disallows `/admin/`, `/search/`, `/core/`, `/profiles/` and a few others; `/document/download/` and the results pages are allowed. One request a second, honest User-Agent |
| 9 | Updates | Silent overwrite, and some files are re-uploaded under a new name (`_0`, `_updated`, `v2`); the loader folds them into one project by key and re-reads a file whose hash changed |
| 10 | Retention limit | None seen |
| 11 | Separate datasets | One page per call year |
| 12 | Personal data | The factsheet names organisations only; the coordinator's contact person is not in the file read. The description (which can name a system) is cut before storage |

## Wrapped and glued names (WP-41, 18 October 2026)

The consortium table is typeset so that a name can wrap over two or three lines, break inside a word ("PLIROF" /
"ORIAS", "ANGEWA" / "NDTEN"), and in the layout text spaces collapse at random ("UNIVERSITEDULUXEMBOURG", "DINAPOLI",
"ISDLYSEIS"). The first reading compared words with spaces, so a name that the model wrote correctly was "not in the
text" and was dropped (35 names and 43 rows left out of the answer, 31 of 283 sheets: ARCHER, EMISSARY, MARTE among
them), and a name the model copied glued from the layout became an organisation of its own (10 participations).

* The quote check compares **letters only** (`edf_factsheets.fold`), in the layout text and in the plain text. A name must
  still be in the document; a name of fewer than four letters is never accepted.
* A name the model copied glued is stored with the spacing the plain text prints on one line (`printed_spelling`); a
  spelling that wraps is not used for a name the model gave.
* The rows of the table the answer lacks are read without a model (`table_entries`, `recover_missing`) and added by
  `python -m dgate.ops.edf_recover [--yes]` from the text still in the raw store; the same tool refiles an EDF project under
  the last capability category its topic code names (`EDF-2023-DA-DS-AIRDEF-EATMI` was DS).
* What the rule cannot recover (a table it cannot pair, a name the answer never had and the layout broke apart) is listed
  by the tool with the cost of a model re-read: about USD 0.0015 a sheet. A re-read needs the stored row of that sheet
  removed or `PROMPT_VERSION` raised, otherwise the loader finds the same file hash and asks nothing.

