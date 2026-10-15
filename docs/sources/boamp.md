# BOAMP (France)

Bulletin officiel des annonces de marchés publics, published by DILA (Direction
de l'information légale et administrative, Premier ministre) and served through
the OpenDataSoft platform. Discovered and measured on 22 September 2026.

The twelve discovery questions from the Technical Appendix, answered against the
live API rather than against documentation.

| # | Question | Answer |
|---|---|---|
| 1 | Endpoint | `GET https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records` |
| 2 | Authentication | None. Anonymous, no key, no registration. |
| 3 | Format | JSON. Administrative columns at the top level, the notice itself as a JSON **string** in `donnees`. |
| 4 | Volume | 1,708,130 notices; 87,739 published in 2026 by 22 September. Per day, measured over three weeks: Mon 171-202, Tue 271-321, Wed 361-431, Thu 383-442, Fri 393-471, Sat 106-133, Sun 283-316. |
| 5 | History | From 2 March 2015. |
| 6 | Update frequency | Twice a day, seven days a week. Saturday is real but small; Sunday is not. |
| 7 | Paging | `limit` ≤ 100 (1000 is rejected), and `offset + limit` ≤ 10,000. A day never approaches the cap, which is why a day is the window. |
| 8 | Filtering | `where=dateparution = date'YYYY-MM-DD'`, ODS query language. `order_by=idweb` for a stable order within a day. |
| 9 | Identifier | `idweb` (`26-90291`). Stable, and the key the public notice page uses. |
| 10 | Defence signal | `perimetre` states the regime: `DIRECTIVE-81` (Directive 2009/81/EC, 4,650 notices) and `CMP-2006-DEFENSE` (1,145). Mapped to CELEX `32009L0081`, so the legal-basis signal is the publisher's own statement, not an inference. |
| 11 | Personal data | Yes, in two places. Named contact fields (`nomContact`, `telContact`, `adresseMailContact`, eForms `cac:Contact`, `IDENTITE.TEL`), and e-mail addresses written into free text. Both are removed at `strip_personal_data`. |
| 12 | Licence | Licence Ouverte / Open Licence (Etalab). Attribution recorded on the `source` row. |

## Three notice shapes in one dataset

`donnees` is not one schema. Measured across recent and 2016 notices:

- **`EFORMS`** — the European standard forms in UBL shape. CPV at
  `cac:MainCommodityClassification.cbc:ItemClassificationCode.#text`, value at
  `cac:RequestedTenderTotal.cbc:EstimatedOverallContractAmount`, contacts deep
  inside `efac:Organizations`.
- **`FNSimple`** — the simplified French form. CPV at
  `natureMarche.codeCPV.objetPrincipal.classPrincipale` and one per lot,
  contacts at `communication.*Contact`.
- **`Boamp_v230.xsd`** (before ~2018) — `IDENTITE`, `OBJET`, `PROCEDURE`
  sections, and **no CPV at all**. Those notices get an empty CPV list, never a
  guessed one, and are classified on the regime and the buyer instead.

A connector that read only the newest shape would silently drop most of the
file, so the mapper reads what the record's own columns give (identifier, buyer,
dates, regime, procedure, subject) and goes into `donnees` only for CPV, value
and description.

## What a defence day looks like

Defence notices are rare and exactly the target: 0 to 2 a day. Collected over
the six days to 22 September 2026 — 2,273 notices, 4 of them defence:

| Notice | Buyer | Signal |
|---|---|---|
| 26-89032 | SID Atlantique (Service d'infrastructure de la Défense) | legal basis |
| 26-89215 | DICOM FAZSOI (armed forces, southern Indian Ocean) | legal basis, EUR 780,000 |
| 26-90126 | Direction de l'administration pénitentiaire, "Casques et Boucliers" | CPV division 35 |
| 26-90291 | Centre de soutien technique et administratif | legal basis, EUR 7,000,000 |

## The honest limits

- Notices before ~2018 carry no CPV, so for them only the regime and the buyer
  list can fire. Their defence coverage is therefore weaker than 2018 onwards.
- BOAMP is not every French notice: buyers may also publish on their own
  profile platforms, and the dataset covers what reaches the bulletin.
- Telephone numbers written into free text are not redacted. French notices put
  SIRET numbers, contract references and amounts in the same sentences, and a
  pattern loose enough to catch the phone numbers corrupts those. E-mail
  addresses in free text *are* redacted, for every source.

## Correction of 12 October 2026 (data-quality audit, finding F10)

The three-shape section above says the `Boamp_v230.xsd` shape has "no CPV at all".
**That is wrong, and the statement is kept above so the error stays visible.** The
legacy shape carries its CPV at `OBJET.CPV.PRINCIPAL` (a single block, or a list of
blocks), one per lot at `OBJET.LOTS.LOT[].CPV`, and the supplementary vocabulary
(`AB25`) at `.SUPPLEMENTAIRE`. 150 of 150 sampled notices of 2015-2020 had it; the
mapper read only the other two shapes, so 4,175 of the 4,185 stored rows had no CPV
and none of 2015-2020 had one. `_fr_cpv` now reads all three, keeps only eight-digit
codes, de-duplicates in document order, and takes `LIRE` (not `INIT`) from a
rectificatif's `CPV` correction block. Schema versions, from DILA's schema book
(`echanges.dila.gouv.fr/schemabook/boamp`): `Boamp_v230.xsd` for 1 March 2015 to
December 2021, `Boamp_v240.xsd` from January 2022; since 2023 the simplified form
(`FNSimple`) and eForms, whose records say `source_schema: "3.2.5"`.

### What a value means

Nothing in the XSDs carries a tax marker (searched in v230 and v240). The standard
forms (JOUE, eForms) define their values excluding VAT; for the national forms (FNS,
FNSimple) no documentation was found that says, and the amount is stored as stated,
never adjusted. Currency is the one the notice states and is never converted; EUR is
assumed only when a notice gives an amount and no currency (the legacy schema makes
`DEVISE` mandatory, so that is malformed input). Zero is "not stated" (the simplified
form writes `0.00` for a lot left blank). Precedence, first that applies:

| Order | Path | Means |
|---|---|---|
| 1 | `ATTRIBUTION.VALEUR_TOTALE` | total final value of the award(s) |
| 2 | eForms `efac:NoticeResult / cbc:TotalAmount` | value of all contracts awarded (BT-161) |
| 3 | `ATTRIBUTION.DECISION.RENSEIGNEMENT.MONTANT`, when there is one decision | final value of that award |
| 4 | `OBJET.CARACTERISTIQUES.VALEUR_TOTALE` | "Valeur totale estimee" (XSD) |
| 5 | `OBJET.CARACTERISTIQUES.VALEUR`, `OBJET.ACCORD_CADRE.VALEUR` | estimated value |
| 6 | eForms `cac:ProcurementProject / cac:RequestedTenderTotal / cbc:EstimatedOverallContractAmount`; the only lot's, when the notice has one lot | estimated value (BT-27) |
| 7 | `FNSimple.*.natureMarche.valeurEstimee.valeur` | estimated value |
| 8 | `DECISION.RENSEIGNEMENT.ESTIMATION_INITIALE`, when there is one decision | the estimate the award was made against |
| 9 | `ACCORD_CADRE.VALEUR_MAX`, `CARACTERISTIQUES.VALEUR_MAX`, eForms `FrameworkMaximumAmount` / `OverallMaximumFrameworkContractsAmount`, `valeurEstimee.fourchette.valeurHaute` | the ceiling; the bottom of a range is never a value |

An award comes before an estimate because an award notice repeats the whole notice.
Several lots or several decisions that state their own amounts and no notice total
give no value: the first lot is not the notice, and nothing is summed.

### Rectificatifs

A "(rectificatif)" is a notice of its own (`etat: RECTIFICATIF`, its own `idweb`)
that repeats the whole of its parent: 229 stored rows, 198 of them with the word in
the title. It is linked in `opportunity.related_native_id`. The parent is
`donnees.RECTIF.ANNONCE_ANTERIEUR.REFERENCE.IDWEB`; the record's `annonce_lie` is
used only when it has one entry, because it lists the parent *and* earlier
rectificatifs and put the corrected notice second in 3 of 198. A 2026 rectificatif
with several `annonce_lie` entries and no reference of its own (31 of 335 sampled)
stays unlinked. An award's `annonce_lie` (its tender) is another relation and is not
stored there.

### Lifecycle (status)

`status` follows the record's `nature`, and an unlisted one is `unknown`, never `open`
(it was `open` for everything unlisted until 13 October 2026; production on 13 October:
`APPEL_OFFRE` 6,386, `ATTRIBUTION` 3,649, `RECTIFICATIF` 449, `INTENTION_CONCLURE` 46,
`PRE-INFORMATION` 47, `MODIFICATION` 29, `EX_ANTE_VOLONTAIRE` 2, `PERIODIQUE` 1, `AUTRE` 1,
`ANNULATION` 1):

| `nature` | status |
|---|---|
| `APPEL_OFFRE` | open |
| `ATTRIBUTION`, `RESULTAT`, `INTENTION_CONCLURE`, `MODIFICATION`, `EX_ANTE_VOLONTAIRE` | awarded (TED's can-*, veat) |
| `PRE-INFORMATION`, `PERIODIQUE` | forthcoming |
| `ANNULATION` | cancelled |
| `RECTIFICATIF` (449 of 453 rectificatifs) or any nature with `etat: RECTIFICATIF` | open when the record states a deadline for offers, otherwise unknown: the notice does not say what its parent was |
| anything else (`AUTRE`, a nature nobody has read) | unknown |

A rectificatif whose nature is a real type (`ATTRIBUTION`, `APPEL_OFFRE`) follows it. The
449 with the nature `RECTIFICATIF` state no deadline in the record, so they are `unknown`
and the parent stays the notice that is listed.

### TED reference

A BOAMP record states **no TED publication number of its own**, so `ted_ref` stays
empty. The JOUE numbers it contains (`PUBLICATION_JOUE`: year and notice number under
`ANNONCE_ANTERIEUR` and `PUBLICATION_ANTERIEURE`) are those of previous notices.
eForms records carry `cbc:ContractFolderID`, the procedure identifier (BT-04) that TED
publishes too, repeated in the record's `contractfolderid` column. It is read by
`from_boamp` into `procedure_identifier` (lower case, braces stripped, only if it is a
UUID) and `dgate.ops.link_twins` joins it to TED's `procedure-identifier`, setting
`ted_ref` and `twin_method = 'procedure_id'`. Legacy records have no such column, so
only the eForms-shaped notices (8 of 4,185 on 12 October 2026, more from now on) link
this way; the rest can only be tied by the strict heuristic of `link_twins` (same buyer,
deadline instant, value and currency, publication within 14 days, a shared 5-digit CPV
class, one candidate on each side: 68 BOAMP notices, nearly all 2017-2020).

### History resume

The load stopped on 23 September 2026 at 429 and was not resumed: 2,087 days
(2015-03-02 to 2020-11-16) are marked done, 2,134 days to 2026-09-20 are not. The
connector now spaces every request one second apart (a request hook, so across days
and retries), honours `Retry-After`, and after the ladder raises `RateLimited` (429,
or the 403 a burst gets); the history then rolls the day back, records the stop in
`backfill_stop` with `resume_after` (the later of 15 minutes and the source's own
window), and exits 75. A rerun refuses to start before `resume_after`.

### Deadline and lots (13 October 2026)

`datelimitereponse` is DILA's own reading of the deadline and is not trusted over the notice:

- It is empty for 2,049 of 6,386 call notices, all eForms ones whose deadline sits in the
  body at `cac:TenderingProcess / cac:ParticipationRequestReceptionPeriod` (restricted and
  negotiated procedures) or `cac:TenderSubmissionDeadlinePeriod` (open ones), as
  `cbc:EndDate` and `cbc:EndTime`, once per lot.
- Where it is present it is the wall time labelled UTC for the `HH:MM:SS.000+02:00`
  spelling of the time: 12 of 30 notices with a TED twin differed from TED by exactly the
  offset, and 49 of 60 twins agree with the body read as stated (28 with the column).
- So an eForms notice's deadline is the latest `EndDate` + `EndTime` of its offers periods,
  the time's own offset first (TED's own reading), then the date's, then Europe/Paris; the
  column is the fallback, and the only source for FNSimple, MAPA and the legacy schemas
  (whose body has a naive local `dateReceptionOffres` / `receptionOffres`, and whose column
  carries the same wall time labelled UTC: not corrected, nothing independent to check it
  against).
- `lot_count` is the number of `cac:ProcurementProjectLot` (not `Part`), `OBJET.LOTS.LOT`,
  `lots.lot`; a notice that lists none is not counted as one.

## Defence buyers by name (15 October 2026, WP-12)

BOAMP does not mark most Ministry of the Armed Forces purchases as defence (they are filed
under the ordinary regimes), so the buyer's name decides: 55 of 59 notices of French defence
bodies since 21 September 2026 were absent from the table (coverage:X1). The vocabulary of
`dgate/buyer_vocab.py` now names the Ministry's families, read against the 81,467 French
organisations of the database:

- the Ministry under its spellings (`Ministère des armées`, `MINARM`, `MINDEF`, `Etat -
  Ministère des armées ...`, typos), the état-major;
- the infrastructure service (SID, ESID, DCSID, DID, DRSID, USID; `defence_infrastructure_service`),
  which the property exclusion kept out until the owner's decision of 15 October;
- the SCA's platforms (PFC, PFAF, plate-forme commissariat), the commissariat d'outre-mer,
  the health supply (DAPSA, PFAF-S; the "santé" exclusion does not apply to these);
- DIRISI / commissariat au numérique de défense, ECPAD, SIMu, SEO, SSF, STAT;
- groupements de soutien de base de défense (GSBDD);
- bodies the Ministry supervises (IGESA, ONAC-VG), `ministry_affiliated`, supply scope only;
- numbered units (régiment, escadre, base aérienne ...).

Left out on purpose: the gendarmerie (Interior; class `security`), military hospitals and
transfusion centres, schools, social clubs ("cercle"), the CEA, the SGDSN, the Paris business
district. A registration number of a Ministry service (`DEFENCE_SIREN_FR`) names a body whose
name says nothing ("DID CAYENNE"); the Ministry's own number is shared by other bodies and is
not used.

A new spelling is flagged when its notice arrives (`db.flag_by_name_rules`, BOAMP only, source
`derived_rule`, the rule stored as the reason). To bring the landed notices in:

    python -m dgate.pipeline seed-buyers          # loads seeds/defence_buyers_derived_FR.csv
    python -m dgate.reprocess --requalify --source fr_boamp --from 2026-06-01 --yes
    python -m dgate.reprocess --reclassify-serving --yes   # serving rows of the held ones
