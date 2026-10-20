# PLACSP (Spain): notices `es_placsp`, `es_placsp_agg`; award winners `es_placsp_awards`

Read on 20 October 2026 (WP-60). Connector `backend/dgate/sources/placsp.py` (notices: `parse_entry`; award
results: `parse_results`, `award_payload`), award loader `backend/dgate/placsp_awards.py`, archive command
`python -m dgate.ops.placsp_archives` (dry run by default). Before this note the project recorded PLACSP as
"open public sector information, commercial use allowed" without anyone having read the publisher's own terms
(legal benchmark L3, open item O10). This note is that reading.

## Licence and reuse terms: what was read

> **Commercial reuse is allowed** by the terms the publisher points to (quotes below). **These terms say nothing
> about personal data.** Award winners include natural persons (autónomos); for those, Ley 37/2007 sends reuse to
> data-protection law. The loader therefore never keeps a person (see "Personal data"). **PLACSP winners are not
> served** in this package: `DGATE_PLACSP_AWARDS_PUBLIC=false` (the default) keeps them off the supplier map until
> the owner decides. **Also note:** the platform's own pages could not be read, see the first point.

1. **PLACSP's own pages were not read.** Both hosts of the platform answer `robots.txt` with `User-agent: *` /
   `Disallow: /` (checked 20 October 2026): `https://contrataciondelestado.es/robots.txt` and
   `https://contrataciondelsectorpublico.gob.es/robots.txt`. Its "Aviso legal" and "Datos abiertos" pages were
   therefore not fetched. The terms below are the ones the official catalogue entry and the ministry's open-data
   pages point to. A person reading the platform's own legal notice in a browser should confirm they agree.
2. **The official catalogue entry** of the dataset this connector reads (datos.gob.es, publisher Ministerio de
   Hacienda, updated daily):
   `https://datos.gob.es/es/catalogo/e05250001-licitaciones-publicadas-en-los-perfiles-del-contratante-ubicados-en-la-plataforma-de-contratacion-del-sector-publico-excluyendo-los-contratos-menores`.
   It names no licence (no CC BY or similar). Its "Condiciones de uso" field is a link to the ministry's aviso
   legal, `https://www.hacienda.gob.es/es-ES/Paginas/Avisolegal.aspx`.
3. **Ministerio de Hacienda, Aviso legal** (`https://www.hacienda.gob.es/es-ES/Paginas/Avisolegal.aspx`; the page
   states no date; read 20 October 2026):
   - Commercial use: "Las presentes condiciones generales … permiten la reutilización de los documentos sometidos a
     ellas para fines comerciales y no comerciales" ("these general conditions … permit reuse of the documents
     subject to them for commercial and non-commercial purposes"). The middle of the sentence was not captured
     verbatim; the beginning and the end are.
   - The grant: "la cesión gratuita y no exclusiva de los derechos de propiedad intelectual" (a free, non-exclusive
     grant of the intellectual property rights).
   - Conditions: "Está prohibido desnaturalizar el sentido de la información." "Debe citarse la fuente de los
     documentos objeto de la reutilización." "Debe mencionarse la fecha de la última actualización de los documentos
     objeto de la reutilización". "No se podrá indicar, insinuar o sugerir que este Ministerio … participa,
     patrocina" [the reuse]. "Deben conservarse, no alterarse ni suprimirse los metadatos sobre la fecha de
     actualización".
   - Attribution example: "Origen de los datos: Ministerio de Hacienda". This is what `source.attribution` of
     `es_placsp_awards` carries (migration 0092).
   - No warranty, no liability: "Este Ministerio no garantiza la continuidad en la puesta a disposición de los
     documentos reutilizables"; "Este Ministerio no será responsable del uso que de su información hagan los agentes
     reutilizadores".
   - Personal data: not mentioned in the reuse conditions (only a footer link "Protección de datos").
4. **Ministerio de Hacienda, Datos abiertos** (`https://www.hacienda.gob.es/es-ES/GobiernoAbierto/Datos%20Abiertos`):
   the ministry "opta por la modalidad básica de puesta a disposición de los datos sin sujeción a condiciones
   específicas"; "Debe citarse la fuente de los datos y documentos reutilizados."; "Debe mencionarse la fecha de la
   última actualización de los datos". The PLACSP page under it
   (`.../Datos%20Abiertos/Paginas/licitaciones_plataforma_contratacion.aspx`) says the information is "disponible
   para su reutilización" and links to the same aviso legal.
5. **Ley 37/2007, de 16 de noviembre, sobre reutilización de la información del sector público** (consolidated text,
   `https://www.boe.es/buscar/act.php?id=BOE-A-2007-19814`, last update published 09/05/2023):
   - Art. 3.1.a: reuse is use "con fines comerciales o no comerciales distintos del propósito inicial".
   - Art. 4.1: documents are to be reusable "para fines comerciales o no comerciales"; 4.1.a, the basic modality:
     "Reutilización de documentos puestos a disposición del público sin sujeción a condiciones."
   - Art. 8 (general conditions that may be set): "Que el contenido de la información, incluyendo sus metadatos, no
     sea alterado." "Que no se desnaturalice el sentido de la información." "Que se cite la fuente." "Que se mencione
     la fecha de la última actualización." and 8.e: where the information contains personal data, the purposes for
     which reuse is possible may be stated.
   - Personal data: art. 4.6, the reuse of documents with personal data "se regirá por lo dispuesto en" the data
     protection law (Ley Orgánica 3/2018); art. 3.4 excludes from reuse information where the transparency weighing
     (Ley 19/2013, arts. 5.3 and 15) gives priority to data protection, unless it is anonymised (paraphrased).
6. **Ley 9/2017 (LCSP)** (`https://www.boe.es/buscar/act.php?id=BOE-A-2017-12902`): art. 63.1, all information in
   the contracting profiles "se publicará en formatos abiertos y reutilizables"; art. 63.3.e, the profile publishes
   "El número e identidad de los licitadores participantes en el procedimiento" and the award decision. Art. 154.7
   allows a buyer to withhold contract data (public interest, legitimate commercial interests, secret or reserved
   contracts, essential security interests): for defence, some awards are simply not in the feed.

**Conclusion.** Commercial reuse of PLACSP notices and award data is allowed under the ministry's general
conditions (cite "Origen de los datos: Ministerio de Hacienda", state the date of last update, do not distort, do
not suggest endorsement, keep the update metadata). It rests on the catalogue's link, not on the platform's own
page, which robots.txt kept us from reading. **For winners that are natural persons, commercial reuse is not
clearly allowed** by anything read: those are governed by the GDPR and LO 3/2018, and this project does not keep
them at all. Whether to serve the company winners publicly is the owner's decision (`DGATE_PLACSP_AWARDS_PUBLIC`).
If they are served, the supplier pages must carry the attribution and the date of last update.

## The twelve questions (technical appendix Part V), for the award results

| # | Question | Answer |
|---|---|---|
| 1 | Official page, publisher | Plataforma de Contratación del Sector Público, Ministerio de Hacienda; datos.gob.es entry above |
| 2 | API, bulk, feed | ATOM syndication (`sindicacion_643`, `sindicacion_1044`) and monthly / annual ZIP archives of the same files; the award results are inside the same CODICE entries as the notices |
| 3 | Registration | none |
| 4 | Format | CODICE 2.x XML. Per `cac:TenderResult` (in practice one per lot): `cbc:ResultCode` (8 awarded, 9 formalised; 3 deserted and 4 withdrawn name no winner), `cbc:AwardDate`, `cbc:ReceivedTenderQuantity`, `cbc:SMEAwardedIndicator`, `cac:WinningParty` (`cac:PartyIdentification/cbc:ID` with `schemeName` NIF or OTROS, `cac:PartyName/cbc:Name`, `cac:PhysicalLocation/cac:Address/cac:Country/cbc:IdentificationCode`), `cac:AwardedTenderedProject/cbc:ProcurementProjectLotID` and `cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount` / `cbc:PayableAmount`. Measured on the live feed of 20 October 2026 (500 entries, 85 results, 80 winners) |
| 5 | History | annual archives from 2012, monthly archives for the current year |
| 6 | Update frequency | daily; the current month's archive is rebuilt daily through the previous day |
| 7 | Licence | see above: commercial reuse allowed with attribution; natural persons excluded by this project |
| 8 | Rate limits | none stated. One archive at a time, one request a second at most, the connector's User-Agent; a 429 stops the run. The server sends archives chunked, without `Content-Length`, ignores `Range` and drops `HEAD` (measured 20 October 2026), so a size is known only after the download |
| 9 | Updates | a folder is republished on every change; its results come again with each entry. The loader keeps the hash of the last read payload on `award_notice` and reads again when it moves; a winner no longer named is marked `award.superseded_at`, never deleted |
| 10 | Personal data | the publisher masks a natural person's NIF ("***1234**": 7 of 80 live winners, all capitals-only personal names). The loader treats as a person a masked number, a DNI or an NIE, and a name without a CIF that reads as a person's, and lands of a person only `{"natural_person": true}` (no name, number, address); no winner's street, city or postcode is landed; the result's free-text description is not read. UTEs are kept as joint ventures, a member that reads as a person blanked |
| 11 | robots.txt | `Disallow: /` on both portal hosts. The connector reads only the syndication files under `/sindicacion/`, as it has since September 2026; this note did not fetch the portal's pages |
| 12 | Failure modes | the archive of a month includes 1,430 entries of September 2021 (a loose filename match; filtered by `since`); a frozen live feed (handled by `pipeline.run_placsp_live`); a large monthly archive nearly filled a 2 GiB worker (entries spooled to disk). datos.gob.es comments of 24 September and 7 October 2026 report failed syndications being regenerated |
