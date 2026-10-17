# Source notes: readiness content (requirements, issuers, rules)

WP-29, 17 October 2026. The readiness layer is compiled, not scraped: `backend/seeds/requirements.json`
is written by people from the regulations and the technical appendix of 7 September 2026, and
every line carries its source. Two kinds of source were used while compiling it. The answers to the
12-question checklist (technical appendix, Part V) are below for the one that was fetched by a program.

## Official Journal texts (Publications Office, CELLAR)

Used to check, word for word, the passages of the regulations quoted in the rules (53 passages in the
seed, 0 not found; the script is `backend/tests/verify_quotes.py`). Not part of the pipeline: nothing
is downloaded when the product runs.

| # | Question | Answer |
|---|---|---|
| 1 | Official open data page, publisher | Publications Office of the European Union, `https://publications.europa.eu/resource/celex/{CELEX}` (content negotiation on the act's CELEX number) |
| 2 | API, bulk, feed or HTML | One request per act. `Accept: application/xhtml+xml` and `Accept-Language: eng` return the act as XHTML. EUR-Lex itself (`eur-lex.europa.eu`) answers an automated client with HTTP 202 and a bot challenge; it was not worked around |
| 3 | Registration | none |
| 4 | Format and specification | XHTML produced by the Publications Office converter from the Formex text of the act |
| 5 | History | every act of the Official Journal; this is the text as published, not a consolidated version |
| 6 | Update frequency and lag | an act is published once; amendments are new acts. The consolidated text of Regulation (EU) 2021/697 as amended by 2025/2653 was **not** read: Article 9 was read in the original act and the replaced Article 5 in the amending act. Article 9 is not among the articles Regulation (EU) 2025/2653 amends (checked in its Article 3) |
| 7 | Licence | reuse of Commission documents under Decision 2011/833/EU (technical appendix, Part III), source acknowledged. The site cites the act and links its ELI address |
| 8 | Rate limits | none stated. About ten requests in all, at least one second apart, with the client name `DefenceGate/1.0 (readiness content check; contact via defencegatehub.com/imprint)`; `robots.txt` of `publications.europa.eu` allows everything outside `/c/portal/`, `/webdav/` and the like |
| 9 | How updates are represented | as a new act. Watching for amendments (plan task M3-08, EUR-Lex monitoring) is **not built** |
| 10 | Retention limit | none |
| 11 | Separate datasets that would be missed | the consolidated versions (not used) |
| 12 | Personal data | none |

Acts read: Regulation (EU) 2021/697 (`32021R0697`), Regulation (EU) 2025/2643 (`32025R2643`),
Regulation (EU) 2025/2653 (`32025R2653`), Council Regulation (EU) 2025/1106 (`32025R1106`), Regulation (EU)
2021/821 (`32021R0821`, Article 3(1) only). A search for "AQAP" and "NCAGE" in the first four returns
nothing, which is what the AQAP rules say.

## What the research notes (technical appendix) are quoted for

The costs, durations, issuing bodies and the Spanish and Ukrainian procedures come from the technical
appendix of 7 September 2026, with its marks kept: [V] verified, [S] seen in search results, [U]
unverified. Their primary pages were **not** re-read in this work, so a rule or requirement whose text is
quoted from the appendix has `text_origin = notes` and says so on the page. They are: NCAGE (NSPA), PIC
(Funding and Tenders Portal), AQAP and ISO/EN, Spanish export control and REOCE, the Spanish facility
clearance.

## Where the appendix and the Official Journal differ

The Official Journal wins, and the rule says what the regulation says.

- **SAFE Article 16(10), second sentence.** The appendix quotes "...contravenes the security and defence
  interests of the Union." The Official Journal text continues "of the Union and its Member States", and
  begins "For the purpose of procurements" (singular). The seed uses the Official Journal wording.
- **SAFE Article 16(4), relief for a subcontractor outside the Union.** The appendix says the
  contractual relationship must predate 29 May 2025. The Official Journal text says "prior to the date of
  entry into force of this Regulation". The seed quotes that and does not state a date.
- **Ukraine and EDIP.** The appendix quotes the Commission as saying Ukraine is "fully associated" to EDIP.
  In the regulation's text, the associated countries of the EDIP Programme are the EEA EFTA members (Article 2,
  Article 8); a Ukrainian company is eligible under the Ukraine Support Instrument (Article 26: established in
  the Union or in Ukraine), which therefore has its own card. Both are encoded as the regulation states them.

## Addresses checked (17 October 2026, from the server, one request a second)

| Address | Result |
|---|---|
| `eportal.nspa.nato.int/Codification/CageTool/`, the Funding and Tenders Portal participant register, `cni.es/oficina-nacional-de-seguridad`, `defence-industry-space.ec.europa.eu/support-ukraine_en`, the BAFA export control page, `asd-stan.org` | 200 |
| `iso.org/standard/62085.html`, `nso.nato.int`, `iaqg.org` | 403 to an automated client (bot protection; not worked around). The addresses are used as the sources of ISO 9001 and AQAP, and are marked in the seed as not machine-checked |
| `comercio.gob.es` (Spanish export control and REOCE) | no connection from our server. The appendix marks it [V]; the address is kept as the appendix gives it |
| ELI addresses (`data.europa.eu/eli/reg/...`) | redirect to EUR-Lex, which gives automated clients a bot challenge; they open in a browser |

## What was not covered

No source for: the cost or time of ISO 9001, EN 9100, AQAP 2310, the export licence, REOCE or the HSEM; the
issuing body of any requirement for the countries the appendix did not cover (an issuer is then "not
collected", never guessed); the name of the national codification bureau of ten NATO countries; the
National Security Authority of any country but Spain; any environmental, social or governance requirement
specific to the programmes (the appendix says none was confirmed, so none is encoded); the EDF consortium
composition rule, the SAFE rules on infrastructure location, the EDF/EDIP conditions of each call (the
call text decides).
