# Data licences: may the data be resold? (WP-153 part A)

- **Date:** 27 October 2026. Every page below was read on that day.
- **Method:** primary sources only: the operator's own legal notice, terms, licence or open-data page, the
  open-data portal entry the operator publishes, or the act the operator cites. robots.txt was read for every host
  first and respected. Pages were fetched one at a time, a few per source, at human pace. No data API was called,
  no form was filled in, nothing was signed up for and no banner was accepted. Where a page is a JavaScript shell,
  the text was read from the static file the site itself ships (the page's own bundle or translation file); this
  is stated per source.
- **Pages that could not be read:**
  - PLACSP's own pages: `robots.txt` on both portal hosts is `Disallow: /`. Not fetched.
  - defmin.fi (MATINE): every request, robots.txt included, gets a Cloudflare challenge (HTTP 403). Not bypassed.
  - EUR-Lex, the text of Commission Decision 2011/833/EU itself: the HTML returned an empty body; no other route
    was tried. The Commission's, TED's and CORDIS's own notices, which cite the Decision, were read instead.
  - EU Funding & Tenders Portal legal notice (`.../portal/screen/support/legalnotice`): JavaScript shell, and the
    text is not in its bundle. The Commission's general legal notice was read instead.
  - govdata.de: `robots.txt` is `User-agent: *` / `Disallow: /`. Not fetched (and not needed: the German operator's
    own page names the licence).
- **This is not legal advice.** It is a reading of what the operators publish, for the owner and a lawyer.
  It covers commercial information only.

## Summary

"Resale" here means serving the data, changed into our records, to paying customers through a key-authenticated
API or a white-label licence.

| Source (code) | Operator | Licence / legal basis | Resale allowed | Conditions | Link |
|---|---|---|---|---|---|
| TED (`ted`, `ted_awards`) | Publications Office of the EU | TED legal notice: notices freely reusable, commercial included (Commission reuse policy, Decision 2011/833/EU); editorial content CC BY 4.0; system metadata CC0 | with conditions | Credit "© European Union"; say what was changed; TED logo needs consent; identifiable private individuals may need extra rights (we drop persons) | https://ted.europa.eu/en/legal-notice |
| PLACSP (`es_placsp`, `es_placsp_agg`, `es_placsp_awards`) | Ministerio de Hacienda | Hacienda aviso legal (Ley 37/2007), the terms the dataset's catalogue entry points to | with conditions | Cite "Origen de los datos: Ministerio de Hacienda"; give the date of last update; do not distort; do not suggest the ministry endorses us; keep the update metadata; personal data under LO 3/2018 (natural-person winners not resold). Platform's own page not read (robots) | https://www.hacienda.gob.es/es-ES/Paginas/Avisolegal.aspx |
| BKMS (`de_bkms`) | Beschaffungsamt des BMI (Datenservice Öffentlicher Einkauf) | Open-Data-Richtlinie, section 4: CC0 | yes | None from the licence. Personal data in the files is still under the GDPR (stripped at ingestion). Disclaimer: content is the buyer's responsibility | https://oeffentlichevergabe.de/ui/de/Open-Data-Richtlinie |
| BOAMP (`fr_boamp`) | DILA (Premier ministre) | Licence Ouverte / Open Licence 2.0 (data.gouv.fr entry; boamp.fr footer etalab-2.0) | with conditions | Name the source (at least DILA) and the date of last update; respect data-protection law (loi Informatique et Libertés); act on DILA's published update requests | https://www.data.gouv.fr/fr/datasets/boamp/ |
| e-Zamówienia (`pl_ezam`) | Urząd Zamówień Publicznych (UZP) | No licence or reuse conditions stated; Polish Open Data Act of 11 August 2021 | unclear | Statute: reuse for any purpose, unconditional by default, limited for personal data; but no conditions are published and the Act routes such cases to a reuse request (art. 39(1)(2)) | https://ezamowienia.gov.pl/pl/regulamin/ and https://eli.gov.pl/eli/DU/2021/1641/ogl/pol/pdf |
| Atlas Przetargów (`pl_atlas`) | Atlas Przetargów (private compiler), on Zenodo | CC BY 4.0 | with conditions | Credit and DOI, licence link, say what was changed, no implied endorsement; the compiled BZP content inherits the e-Zamówienia question; hashed natural persons are still personal data (dropped) | https://zenodo.org/records/19634050 |
| TenderNed (`nl_tenderned`) | PIANOo (Rijk) | CC0 1.0 on data.overheid.nl | yes | None from the licence. The documented API needs credentials; our endpoint is the portal's own (an access question, not a licence one) | https://data.overheid.nl/dataset/aankondigingen-van-overheidsopdrachten---tenderned |
| BDNS (`es_bdns`) | IGAE, Ministerio de Hacienda | SNPSAP aviso legal (Ley 37/2007, RD 130/2019) | with conditions | Calls: cite "Origen de los datos: Intervención General de la Administración del Estado", date of last update, no distortion, no endorsement, keep metadata. Personal data only for control of public managers, or historical/statistical/scientific use after dissociation, so awards to persons are not resellable. API access may be restricted on abuse | https://www.subvenciones.gob.es/bdnstrans/GE/es/avisolegal |
| EU Funding & Tenders Portal (`eu_portal`) | European Commission (SEDIA) | Commission reuse policy, Decision 2011/833/EU; Commission legal notice (CC BY 4.0) | with conditions | Credit, say what was changed; logos and names excluded. The portal's own notice was not readable (JS) | https://commission.europa.eu/legal-notice_en |
| CORDIS (`cordis`) | European Commission (Publications Office) | Decision 2011/833/EU; editorial content CC BY 4.0 | with conditions | Credit, say what was changed; beneficiaries' material only on the grant's terms (abstracts and results, which we do not take); `/data/` is robots-disallowed | https://cordis.europa.eu/about/legal |
| EDF factsheets (`edf_factsheets`) | European Commission, DG DEFIS | Notice on the factsheet itself: CC BY 4.0; site uses the Commission legal notice | with conditions | Credit, say what was changed (our records are an extraction); elements not owned by the EU need the rightholder; images excluded | https://defence-industry-space.ec.europa.eu/funding-opportunities/calls-proposals/result-edf-2025-calls-proposals_en |
| AID (`fr_aid`) | Agence de l'innovation de défense, Ministère des Armées | defense.gouv.fr legal notice: site content under Licence Ouverte 2.0 | with conditions | Name source and date of last update, no alteration; images and some texts excluded; logos need consent. A second paragraph authorises only "non-commercial" reuse of public information: a contradiction to clear | https://www.defense.gouv.fr/mentions-legales-conditions-dutilisation-du-site |
| MATINE (`fi_matine`) | Puolustusministeriö | Not read (Cloudflare challenge) | unclear | None known | https://defmin.fi (not readable) |
| NCBR (`pl_ncbr`) | Narodowe Centrum Badań i Rozwoju | gov.pl: texts CC BY-SA 4.0, audiovisual CC BY-NC-ND 4.0; NCBR reuse page (Open Data Act) | with conditions | Credit; share-alike on texts we adapt; images non-commercial. NCBR may set conditions (source, time, processing, personal data) but none was found set | https://www.gov.pl/web/ncbr/ponowne-wykorzystywanie-informacji-sektora-publicznego |
| Vinnova (`se_vinnova`) | Vinnova | CC0 | yes | None. (The database still records "Public Domain Mark": out of date) | https://www.vinnova.se/en/about-us/about-the-website/open-data/ |

## Per source

### TED (`ted`, `ted_awards`)

- Read: https://ted.europa.eu/en/legal-notice (allowed by robots.txt); https://docs.ted.europa.eu/api/latest/index.html.
- Decisive clause (Copyright notice), the two parts of one sentence: "the procurement notices published in the
  Supplement to the Official Journal of the European Union can be freely reused, … for commercial or
  non-commercial purposes." The sentence starts "Unless otherwise noted".
  English: the procurement notices may be reused freely, for commercial or non-commercial purposes.
- For the editorial content of the TED sites (CC BY 4.0): "reuse is allowed provided appropriate credit is given and
  any changes made are indicated." The SIMAP system metadata is CC0 1.0. The logos, TED's included, "may not be used
  without the prior consent of the Publications Office". The notice adds: "You may be required to clear additional
  rights if specific content depicts identifiable private individuals".
- The API documentation states no terms of use, quotas or licence. It says "The Search API does not require a key."
- Verdict **with conditions**: commercial reuse of notices is stated in plain words. The conditions are the
  Commission's usual ones: credit, mark changes, no logo. Award notices that name natural persons as winners are a
  personal-data matter, not a licence one; the project already drops them.

### PLACSP (`es_placsp`, `es_placsp_agg`, `es_placsp_awards`)

- Not read: the platform's own aviso legal. `robots.txt` on `contrataciondelestado.es` and
  `contrataciondelsectorpublico.gob.es` is `Disallow: /`. The datos.gob.es catalogue entry (read 20 October,
  `docs/sources/es_placsp.md`) names no licence and links its "Condiciones de uso" to the ministry's aviso legal.
- Read: https://www.hacienda.gob.es/es-ES/Paginas/Avisolegal.aspx (allowed by robots.txt).
- Decisive clause: "Las presentes condiciones generales … permiten la reutilización de los documentos sometidos a ellas
  para fines comerciales y no comerciales."
  English: these general conditions permit reuse of the documents they cover for commercial and non-commercial
  purposes. (The two parts were captured verbatim; any words between them were not.)
- Conditions, verbatim: "Está prohibido desnaturalizar el sentido de la información." "Debe citarse la fuente".
  "Debe mencionarse la fecha de la última actualización". It may not be suggested that the ministry "participa,
  patrocina o apoya la reutilización". Update metadata must be kept. Example credit: "Origen de los datos:
  Ministerio de Hacienda". The reuse conditions say nothing about personal data.
- Verdict **with conditions**. It rests on the terms the catalogue points to, not on the platform's own page.
  Natural-person winners: Ley 37/2007 art. 4.6 sends reuse to data-protection law (see `docs/sources/es_placsp.md`),
  so they are not resold. The `es_placsp` and `es_placsp_agg` rows credit "Source: Plataforma de Contratacion del
  Sector Publico, Ministerio de Hacienda". The `es_placsp_awards` row uses the ministry's example wording. Every
  served record also needs the date of last update.

### BKMS (`de_bkms`)

- Read: https://oeffentlichevergabe.de/ui/de/Open-Data-Richtlinie and its English route `/ui/en/Open-Data-Richtlinie`.
  The site has no robots.txt (404). The page is a single-page app, so the text was read from the bundle the page
  loads, `https://oeffentlichevergabe.de/ui/assets/index-Bpwxq_Px.js`, under the key `publicationPolicy`
  (German and English).
- Decisive clause (section "4. Lizenz"): "Für die Nutzung der als Open Data bereitgestellten Daten gilt die Creative
  Commons CC Zero-Lizenz". English, as on the site: "The data provided as Open Data is under the Creative Commons CC
  Zero licence".
- Purpose (section 1): the notices are published in open formats "so dass sie von allen Interessierten genutzt,
  wiederverwendet und weiterverbreitet werden können" (so that anyone interested can use, reuse and redistribute
  them). Section 5: the buyer, not the service, is responsible for each notice's content.
- The platform's Nutzungsbedingungen cover only users of its account features (ELSTER organisation sign-in), not the
  open-data interface: "Nutzer im Sinne dieser Nutzungsbedingungen sind ausschließlich juristische Personen …".
- Verdict **yes**: CC0 on the operator's own policy page. This answers open item 1 of the German section of
  `docs/legal/OPEN_ITEMS_FOR_LAWYER.md`. CC0 does not cover the persons named in the files. They are stripped at
  ingestion, which is the GDPR question (item 4), not a licence one. The source is still `active = FALSE`,
  `commercial_ok = NULL`. Switching it on is the owner's decision. Because the text was read from a script bundle,
  a person should look at the rendered page once (or BeschA confirm it by e-mail) before relying on it.

### BOAMP (`fr_boamp`)

- Read: https://www.data.gouv.fr/fr/datasets/boamp/ (the dataset as published by Premier ministre / DILA);
  https://www.boamp.fr/pages/donnees-ouvertes-et-api/ (JS page; only the footer was readable);
  https://www.dila.gouv.fr/services/repertoire-des-informations-publiques/les-donnees-economiques-et-financieres;
  the licence text https://raw.githubusercontent.com/etalab/licence-ouverte/master/LO.md.
- Decisive: the data.gouv.fr entry gives the licence as "Licence Ouverte / Open Licence", version 2.0 shown. The
  licence grants reuse "à des fins commerciales ou non, dans le monde entier et pour une durée illimitée".
  English: for commercial or non-commercial purposes, worldwide, without time limit.
- Conditions: credit the source (at least the licensor's name) and "la date de la dernière mise à jour". The dataset
  description adds: "Le réutilisateur s’oblige à prendre en compte les demandes de mise à jour de données publiées
  ponctuellement par la DILA" (the reuser must act on update requests DILA publishes). It also says the release
  "n’affranchit pas le réutilisateur du respect de la loi Informatique et Libertés".
- Verdict **with conditions**. Access finding for the owner: `robots.txt` of `boamp-datadila.opendatasoft.com`
  (the connector's host) has `Disallow: /api/` for `User-agent: *` and allows `/api/` only for Googlebot. That
  touches the collection, not the resale. Whether a documented open-data API counts as "crawling" is a question to
  put to DILA.

### e-Zamówienia (`pl_ezam`)

- Read: https://ezamowienia.gov.pl/pl/regulamin/; the API regulation
  https://media.ezamowienia.gov.pl/pod/2023/02/Regulamin-korzystania-z-API-1.pdf (Zarządzenie nr 1/2023,
  1 February 2023); the Act https://eli.gov.pl/eli/DU/2021/1641/ogl/pol/pdf. `robots.txt` of ezamowienia.gov.pl
  holds no rules (its body is the two characters "as").
- Regulation §3(8): "W zakresie Webservice nie wymagane jest składanie wniosku dostępowego. Usługa Webservice jest
  bezpłatna". English: no access request is needed for the Webservice, and it is free. It names the endpoint
  `/mo-client-board/api/notices/`; our connector uses `/mo-board/api/v1/Board/Search`. The platform regulation
  has no clause on reuse, licence or commercial use. §13(6) says notices sometimes contain personal data.
- The Act: art. 2(12), reuse is use "w jakimkolwiek celu" (for any purpose). Art. 14(1), information is made
  available for reuse "bezwarunkowo, z wyjątkiem przypadków określonych w ustawie". Art. 6(2) limits it for
  privacy and personal data. **But** art. 39(1)(2) says a reuse request is lodged where information "są
  udostępniane w innym systemie teleinformatycznym … i nie zostały określone warunki ponownego wykorzystywania …
  albo nie poinformowano o braku takich warunków".
  English: where information is in another ICT system and no conditions, and no statement that there are none, have
  been published.
- Verdict **unclear**. The statute leans permissive, but UZP publishes neither conditions nor a statement that
  there are none, and that is the case the Act sends to a request. A short written request to UZP under art. 39
  would settle it. The database records `commercial_ok = TRUE`, which is more than the reading supports.

### Atlas Przetargów (`pl_atlas`)

- Read: https://zenodo.org/records/19634050 (robots.txt allows records; crawl-delay 10 respected).
- Decisive: the record's licence is "Creative Commons Attribution 4.0 International". Title "Polish Public Tenders
  Dataset (BZP + TED) — 2026.Q2", published 17 April 2026, creator Atlas Przetargów. No other use restriction.
- Personal data: "natural-person contractors (CEIDG sole proprietors, PESEL holders) are anonymized via a stable
  salted SHA-256 hash". A stable hash is pseudonymous, so still personal data; the project drops it.
- Verdict **with conditions** (CC BY 4.0: credit, licence link, indicate changes, no implied endorsement). The
  compiler can license only what it holds. The BZP content underneath is the e-Zamówienia question above, so a
  lawyer should confirm the two together.

### TenderNed (`nl_tenderned`)

- Read: https://data.overheid.nl/dataset/aankondigingen-van-overheidsopdrachten---tenderned (owner PIANOo, updated
  08-10-2025). robots.txt of data.overheid.nl and tenderned.nl allows these paths.
- Decisive: "Licentie: CC-0 (1.0)". Also: "Alle aankondigingen op TenderNed zijn openbaar". English: CC0; all
  notices on TenderNed are public.
- Also: "Om onze API te gebruiken, heeft u een gebruikersnaam en wachtwoord nodig", and the web service may change
  "zonder voorafgaande kennisgeving". English: the API needs a user name and password, and the web service may
  change without notice. The page says nothing about personal data.
- Verdict **yes**. The only open point is access: our endpoint is the portal's own, not the documented API
  (`docs/sources/nl_tenderned.md`).

### BDNS (`es_bdns`)

- The aviso legal page (`/bdnstrans/GE/es/avisolegal`) is an Angular shell. Its text was read from the site's own
  Spanish translation file https://www.subvenciones.gob.es/bdnstrans/assets/i18n/es.json (keys
  `PagAvisoLegal.Texto000`–`053`). robots.txt of both SNPSAP hosts answers with an "Autorización requerida" page, so
  there are no rules to read.
- Decisive (Texto016): "Las presentes condiciones generales permiten la reutilización de los documentos sometidos a
  ellas para fines comerciales y no comerciales." English: the general conditions permit commercial and
  non-commercial reuse.
- Personal-data limit (Texto017): with personal data, reuse "sólo será posible si tiene por fin el control de la
  actuación de los gestores públicos"; historical, statistical or scientific use is allowed after dissociation.
  English: reuse of documents with personal data is allowed only to monitor public managers, or for
  history, statistics or science after the data are dissociated.
- Conditions (Texto022–027): no distortion. Credit "Origen de los datos: Intervención General de la Administración
  del Estado". Give the date of last update. If personal data was dissociated, say so and by whom. No suggestion of
  endorsement. Keep metadata. Texto051: API access may be restricted on "manifiesto abuso del servicio".
- Verdict **with conditions**. Calls name no persons and may be resold. Awards (`concesiones`) to natural persons
  may not. The `source.attribution` row reads "Fuente: Base de Datos Nacional de Subvenciones (BDNS), Intervencion
  General de la Administracion del Estado, Ministerio de Hacienda", which names the right body. The aviso's example
  is "Origen de los datos: Intervención General de la Administración del Estado".

### EU Funding & Tenders Portal (`eu_portal`)

- Not readable: the portal's legal notice (JS shell; the text is not in its bundle).
- Read: https://commission.europa.eu/legal-notice_en (robots.txt allows).
- Decisive: EU-owned content is under CC BY 4.0 unless otherwise indicated, and "reuse is allowed, provided
  appropriate credit is given and changes are indicated". The policy is the "Commission Decision of 12 December 2011
  on the reuse of Commission documents". Excluded: "registered designs, logos and names, are excluded from the
  Commission's reuse policy". The page does not use the word "commercial". The TED and CORDIS notices, which rest on
  the same Decision, do.
- Verdict **with conditions**. The operator is the Commission, and its reuse policy covers Commission documents
  whichever site carries them. The portal's own page and the text of the Decision were not read, so a person
  should confirm both once.

### CORDIS (`cordis`)

- Read: https://cordis.europa.eu/about/legal. robots.txt disallows `/data/`, `/search` and others. `/about/` and
  `/datalab/` are allowed.
- Decisive: "The Commission's reuse policy is implemented by Commission Decision 2011/833/EU". Editorial content is
  CC BY 4.0, "provided appropriate credit is given and any changes are indicated". Beneficiaries' material "may only
  be used according to the terms and conditions applicable to the respective grant."
- Verdict **with conditions**. What we take (organisations, project facts, roles and EU contributions) is Commission
  data. The beneficiaries' abstracts and results, which carry their own terms, are not taken (the connector's
  docstring). Participant contact details can be on CORDIS; we do not take them.

### EDF factsheets (`edf_factsheets`)

- Read: the 2025 results page and the general factsheet linked from it,
  `https://defence-industry-space.ec.europa.eu/document/download/da0507e0-0c76-4f23-8585-40176f757231_en`
  (robots.txt allows `/document/download/`). The site's footer links to the Commission legal notice above.
- Decisive, on the document: "Reuse of this document is allowed, provided appropriate credit is given and any
  changes are indicated (Creative Commons Attribution 4.0 International license)". It adds that elements not owned
  by the EU may need the rightholder's permission. Images: "© European Union, © Adobe Stock".
- Verdict **with conditions**. Our consortium records are extracted and changed, so they must say so and credit the
  Commission. The per-project factsheets were checked in `docs/sources/edf_factsheets.md` (17 October) and carry
  the same notice.

### AID (`fr_aid`)

- Read: https://www.defense.gouv.fr/mentions-legales-conditions-dutilisation-du-site (robots.txt allows).
- Decisive ("Réutilisation des contenus"): "Sauf mention explicite de propriété intellectuelle détenue par des tiers,
  les contenus du Site sont proposés sous licence ouverte" (link to Licence Ouverte v2.0). Graphics, photographs and
  multimedia "ne sont pas réutilisables sans accord exprès". English: site content is under the open licence unless
  third-party rights are stated; images are not reusable without consent.
- Contradiction ("Réutilisation des informations publiques"): "La réutilisation non commerciale, notamment à des fins
  pédagogiques, est autorisée". It is subject to the CRPA, with no alteration, and source and last-update date given.
  English: non-commercial reuse, for example educational, is authorised.
- Verdict **with conditions**, on the strength of the licence clause (LO 2.0 permits commercial reuse). The second
  paragraph names only non-commercial reuse and does not forbid commercial reuse. A lawyer should say which
  paragraph governs, or the ministry should be asked. We take only facts (title, dates) and a link.

### MATINE (`fi_matine`)

- Not read: https://defmin.fi answers every request, robots.txt included, with a Cloudflare "Just a moment…"
  challenge (HTTP 403). It was not bypassed. No licence statement was found by search either.
- Verdict **unclear**. The database already records `commercial_ok = NULL`.

### NCBR (`pl_ncbr`)

- Read: https://www.gov.pl/web/ncbr/ponowne-wykorzystywanie-informacji-sektora-publicznego (dated 12.12.2024;
  robots.txt of gov.pl is `Allow: /`).
- Decisive (gov.pl footer): "Treści tekstowe publikowane w serwisie (z wyłączeniem treści audiowizualnych), są
  udostępniane na licencji typu Creative Commons: uznanie autorstwa - na tych samych warunkach 4.0 (CC BY-SA 4.0)."
  English: text content is CC BY-SA 4.0. Audiovisual material is CC BY-NC-ND 4.0.
- NCBR's own page: "Narodowe Centrum Badań i Rozwoju może określić warunki ponownego wykorzystywania". The
  conditions it may set cover source and time, processing, liability, and personal data. Reuse is free of charge,
  with exceptions for extra costs. The page states no condition as actually set.
- Verdict **with conditions**: commercial reuse is allowed by CC BY-SA and by the Act ("for any purpose"). Adapted
  text must be share-alike. Facts (dates, sums, status) are not text in the copyright sense. The project already
  serves facts and keeps descriptions in the private raw store. The connector docstring says "commercial reuse
  allowed, attribution required". The NCBR page does not say that in those words.

### Vinnova (`se_vinnova`)

- Read: https://www.vinnova.se/en/about-us/about-the-website/open-data/ ("Last updated 8 October 2026";
  robots.txt allows everything).
- Decisive: "Vinnova's open data can be used freely without fees or licenses (CC0)."
- The page also says Vinnova shares data on people only for project managers. That is in funded projects, which we
  do not collect; we take application rounds.
- Verdict **yes**. The `source` row (migration 0019) still says "Public Domain Mark" in `licence` and `attribution`.
  It should say CC0.

## Recommendation for the paid, key-authenticated API

Default allow-list (the builder's TED-only default can grow to this once each row's attribution is served):

1. **TED** (`ted`, `ted_awards` for legal entities only): safe now. Serve "Source: TED, © European Union" and a note
   that records are changed (normalised) from the original.
2. **TenderNed** and **Vinnova**: CC0, safe now. Correct Vinnova's `licence` text to CC0 first.
3. **BOAMP**, **PLACSP notices**, **BDNS calls**: safe once every record carries the required credit and the
   source's date of last update (and, for BOAMP, DILA's update requests are honoured). PLACSP and BDNS: never
   natural persons. PLACSP's own legal page was not readable (robots), so the lawyer may want it read by hand.
4. **EU portal**, **CORDIS**, **EDF factsheets**: Commission reuse policy, safe with "© European Union" and
   "changes indicated". A person should confirm the portal's own notice and the Decision text once.

Hold until answered:

- **BKMS**: CC0 found today. The licence is no longer the blocker, but the source is inactive and the GDPR items
  (open items 2–6) remain. Owner's decision; a one-line confirmation from BeschA would make it certain.
- **e-Zamówienia** and **Atlas Przetargów**: unclear for Poland until UZP answers a written reuse request (or a lawyer
  reads art. 5, 14 and 39 of the Open Data Act as allowing it without one).
- **NCBR**: facts are probably fine. Ask a lawyer whether CC BY-SA on gov.pl texts reaches the API's JSON.
- **AID**: the two paragraphs disagree. Low value (facts and links only); leave it out of the paid API until cleared.
- **MATINE**: unclear. Leave it out.

## Open questions for a lawyer

1. Poland: does the Open Data Act (arts. 5, 14(1), 39(1)(2)) let us resell e-Zamówienia data that UZP publishes
   with no conditions, or must we file a reuse request first? Does that also decide the Atlas (CC BY 4.0)
   compilation of the same notices?
2. France (AID): defense.gouv.fr puts site content under Licence Ouverte 2.0 but authorises "non-commercial" reuse
   of public information in a separate paragraph. Which governs a paid API?
3. Poland (NCBR): does CC BY-SA 4.0 on gov.pl "text content" reach structured JSON from the gov.pl competition API,
   and so a derived paid product?
4. Spain (PLACSP): is the ministry aviso legal enough, given that the platform's own aviso could not be read? And
   what form must "date of last update" take in an API response?
5. Spain (BDNS): confirm that calls may be resold, that awards naming natural persons may not (Texto017), and the
   exact credit wording.
6. EU (TED, portal, CORDIS, EDF): is a "records normalised from the original" note enough to meet "changes
   indicated"? Is database right (Directive 96/9/EC) on our compilation affected by these licences (CC BY 4.0
   allows no added restrictions on the licensed material)?
7. France (BOAMP): does DILA's "update requests" duty need a process on our side? Is collecting through the
   opendatasoft `/api/` path, which robots.txt disallows for generic agents, a terms problem?
8. Germany (BKMS): with the licence now CC0, the remaining items 2–6 of the German section of
   `docs/legal/OPEN_ITEMS_FOR_LAWYER.md` (automated download, GDPR stripping, sui generis right).
9. Finland (MATINE): no licence could be read. Is a title, a date, a sum and a link (facts) resellable without one?
10. All: does CC0 or an open licence ever reach the personal data in a notice? We assume no, and strip at ingestion.

## Database rows that no longer match this reading

- `se_vinnova`: licence "Public Domain Mark" should be CC0.
- `de_bkms`: licence "Not verified" can be CC0 (still inactive; owner's switch).
- `pl_ezam`, `pl_atlas`: `commercial_ok = TRUE` is more than the reading supports (unclear).
- `fr_aid`, `pl_ncbr`: `TRUE` with an open question each.
- `es_placsp`, `es_placsp_agg`: attribution lacks the ministry's "Origen de los datos: Ministerio de Hacienda" form
  and the date of last update.
