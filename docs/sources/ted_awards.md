# TED result notices, winners (`ted_awards`): the supplier map

Read on 18 October 2026. Loader `backend/dgate/awards.py` (`run_awards`), connector call
`backend/dgate/sources/ted.py: fetch_by_numbers`; command `python -m dgate.pipeline awards`. Not a worker job: it is
run by hand after a TED load, and a second run asks about no notice it has read. The feasibility study with the
numbers is `docs/design/SUPPLIER_MAP_FEASIBILITY.md`.

This is the same TED search API as the `ted` source (whose notes are the module docstring of
`dgate/sources/ted.py`), asked for different fields. The `ted_awards` row in `source` exists only
to carry the raw records and the run log; it is seeded **inactive** and stays so, so `/v1/health` does not list it
as a feed that could be stale.

## The twelve questions (technical appendix Part V)

| # | Question | Answer |
|---|---|---|
| 1 | Official open data page, publisher | TED, Publications Office of the European Union: `https://ted.europa.eu`; API documentation `https://docs.ted.europa.eu/api/latest/search.html`; field list `https://docs.ted.europa.eu/ODS/latest/reuse/field-list.html` |
| 2 | API, bulk, feed | the Search API, `POST https://api.ted.europa.eu/v3/notices/search`; up to 100 `publication-number` values in one query |
| 3 | Registration | none (anonymous) |
| 4 | Format, specification | JSON; the fields are the eForms business terms: `winner-name`, `organisation-name-tenderer`, `organisation-country-tenderer`, `organisation-identifier-tenderer` (listed in the field list). Lists, not objects: one entry per organisation (the tenderer block) or per lot (`winner-name`) |
| 5 | History | winners as data only from eForms (optional from 25 October 2022, mandatory from 25 October 2023); in practice 80 % of result notices name one from 2024, 6 % in 2023 |
| 6 | Update frequency, lag | notices appear as published; the loader runs on demand |
| 7 | Licence | Commission Decision 2011/833/EU: reuse including commercial, with attribution and without distortion; TED metadata CC0 1.0 (as `dgate/sources/ted.py` already states). Attribution stored in `source.attribution` and returned by `/v1/suppliers/{slug}` |
| 8 | Rate limits | none stated for the search; the loader makes one request a second and 76 requests for the whole backlog |
| 9 | How updates are represented | a corrected result notice is a new version in TED; the loader reads a notice once. Corrected winners are not re-read (a known limit; `--refresh` was not built) |
| 10 | Personal data | a winner can be a natural person. The loader skips what looks like one and blanks it in the record before the record is landed (`dgate/awards.py`, measured in the feasibility study); contact fields are never requested |
| 11 | robots.txt and terms | the API is the documented, anonymous interface; the page paths of `ted.europa.eu` are not fetched |
| 12 | Failure modes seen | `winner-name` against `winner-country` are not in the same order in notices with several winners (81 % agreement): the loader reads the tenderer block. DNS failures from the server under load surfaced as an exception (the run is resumable: committed batches stay) |
