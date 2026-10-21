# CPV 2008 vocabulary (`cpv_vocabulary`): the static code list of the supplier page

Read on 21 October 2026 (WP-73). Not a connector: one file, `web/lib/data/cpv-full.json` (9,454 codes, English titles), loaded on
`/readiness/supplier` and its report only (`web/lib/cpv-full.ts`, imported dynamically). The 371-code selection `web/lib/data/cpv.json`
is unchanged and still serves every other page.

## How it was obtained, and robots.txt

- `https://op.europa.eu/robots.txt` (also what `https://publications.europa.eu/robots.txt` redirects to), read 21 October 2026:
  `User-agent: * Allow: /`; none of its `Disallow` lines (portal actions, `p_p_*` parameters, `/s/`, `*requestAction=rdf`, `/webdav/`,
  `/*/eu-vocabularies/dataset/*version`, `/*/web/eu-vocabularies/dataset?*`) matches the paths used.
- Requests, one at a time, about a second apart, `User-Agent: DefenceGate/1.0 (EU defence procurement data research; robots.txt honoured)`:
  1. `http://publications.europa.eu/resource/dataset/cpv` with `Accept: application/rdf+xml` (the dataset; latest release `20260520-0`);
  2. `http://publications.europa.eu/resource/dataset/cpv/20260520-0` with `Accept: application/rdf+xml;notice=tree` (its distributions);
  3. `http://publications.europa.eu/resource/cellar/5a2097dc-5453-11f1-b3e2-01aa75ed71a1.0001.01/DOC_1`: the genericode distribution
     `xml/gc` (`Cpv.gc`, 26 MB, 24 languages), published 2026-05-20;
  4. the copyright notice `https://op.europa.eu/en/web/about-us/legal-notices/publications-office-of-the-european-union-copyright`.
- The SIMAP page (`simap.ted.europa.eu`) answered 429 to a robots.txt request and was not used. `data.europa.eu`'s search API is
  robots-disallowed (`/*search?*`) and was not used.
- The file was converted with a one-off script (code, `en_label`, white space normalised; the other 23 languages and the check digits
  left out). The downloaded files were in `D:\DEFENCEGATE TESTS\wp73-cpv-dl` and were deleted after the conversion.

## The twelve questions (technical appendix Part V)

| # | Question | Answer |
|---|---|---|
| 1 | Official open data page, publisher | Publications Office of the European Union, EU Vocabularies, dataset `http://publications.europa.eu/resource/dataset/cpv` (Commission Regulation (EC) No 213/2008) |
| 2 | API, bulk, feed | Bulk files per release (genericode XML, SKOS RDF); the Cellar resolver serves them by URI. The genericode file is used |
| 3 | Registration | None |
| 4 | Format, specification | OASIS genericode 1.0 (`gc:CodeList`, columns `Code`, `Name`, `<lang>_label`) |
| 5 | History | CPV 2008 only (the vocabulary in force); releases of the dataset are corrections and translations |
| 6 | Update frequency, lag | Irregular releases; the one used is `20260520-0`. A new CPV version would be a new regulation |
| 7 | Licence | EU content of the Publications Office is under CC BY 4.0 (its copyright notice); reuse of Commission documents under Commission Decision 2011/833/EU. Attribution in the file (`_source`, `_licence`) and on the page (the CPV hint) |
| 8 | Rate limits | None stated; four requests in all |
| 9 | How updates are represented | A new release replaces the file; codes are not renumbered within CPV 2008 |
| 10 | Personal data | None |
| 11 | Content restrictions | Product and service categories only; no technical specification of any system |
| 12 | What we keep | The code and its English title, verbatim |
