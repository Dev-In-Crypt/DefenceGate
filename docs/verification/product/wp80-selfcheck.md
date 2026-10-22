# WP-80 self-check: the supplier report leads with "who to approach" (22 October 2026)

Branch `wp-wp80` from `integration` (40991d9, WP-68 merged). Plan: "Change of emphasis" of
`docs/plans/MVP_SPAIN_AUTOMOTIVE_2026-10-21.md`; why: `docs/research/ANGLE1_SPAIN_LANDSCAPE_2026-10-22.md` (rules and roadmap are free
in Spain, the gap is cross-country demand and winners). No model call, no spending, no deploy, no push, no migration, no secret.
Production was only read: the branch's `demand.py` was run inside `dgate-api-1` from stdin (no file written there) on a connection set
`default_transaction_read_only = on`, `statement_timeout = 30s`, plus short read-only `SELECT`s through `psql`. Not touched: WP-76
(organisation merges), WP-78 (eligibility), WP-79 (accounts, `/signin`, `/app`, privacy section 5).

## 1. What was built

| Part | Files |
|---|---|
| `approach` in `POST /v1/readiness/demand` (still stateless, one statement plus two small reads) | `backend/dgate/demand.py` |
| TED + PLACSP twins counted once (`award_twin_set`, WP-75), in `approach` and in the per-country winners of WP-66 | `demand.py` (`aw0` / `aw`) |
| Curated, sourced list of primes and large defence groups, matched on the normalised name | `demand.PRIMES`, `prime_of` |
| "Who to approach" section (report: first; results page: first, short) | `web/components/readiness/approach.tsx`, `report.tsx`, `results.tsx` |
| One demand request per page, read by both sections | `report.tsx`, `results.tsx`, `demand.tsx` (`DemandMap`/`DemandSummary` take the result) |
| Rules as appendices; each roadmap step with the free guide and the regional grants of the research | `web/lib/es-support.ts`, `report.tsx` (`Support`) |
| Entry page and supplier page copy in the new order | `app/(public)/readiness/spain-automotive/page.tsx`, `app/(public)/readiness/supplier/page.tsx` |
| Demo answer regenerated from production (switch on, as production) | `web/lib/mock/demand.json` |
| Contract | `docs/design/API_CONTRACT.md` |

**Rules of `approach`.** Same notices and award rows as the WP-66 map (defence scope, ES/DE/FR/PL/NL, 3 years, the CPV level match;
legal entities only, not excluded, superseded or removed; PLACSP only with `DGATE_PLACSP_AWARDS_PUBLIC`, which is `true` on production).
Per winner (merge head) across the countries asked: **contracts** = distinct procurements (the WP-66 procurement key; a twin pair of
`award_twin_set` drops the second copy when its preferred row is in the answer). **Mosaic rule**: named only with at least 3 contracts
(`K_MIN`); the others are one count (`below`). At most 30 listed, most contracts first, plus every marked prime past the 30th
(`more` counts the rest). **No value per supplier** (follow-up, orchestrator decision): the first version summed the values TED
result notices state per winner; that contradicts the supplier map's own rule ("no sum of values per supplier") and was removed. **Main buyers**: the 3 buyer families it wins from most (a withheld buyer is never
named). **Countries**: where the contracts were. **Latest notice**: the publication date of its newest notice (TED: the result notice;
PLACSP: the procurement's publication, since the award date is not stored; the copy says "latest notice published", not "award date").
**Supplier page link**: only when `/v1/suppliers/{slug}` serves the company (an award in the supplier map's own scope, read with
`suppliers.scope()`), so a link never 404s. **Signals kept separate**: `prime` (curated list), `edfProjects` (EDF/EDIDP/PADR
participations of the organisation and those merged into it), `defenceBuyer` (the curated buyer flag).

**The prime list** (`demand.PRIMES`, with source per entry): the European companies of the SIPRI Top 100 arms-producing and military
services companies of 2024 (fact sheet December 2025, read on 22 October 2026: BAE Systems, Airbus, Leonardo, Thales, Rheinmetall,
Rolls-Royce, Saab, Safran, MBDA, Naval Group, Babcock International, Dassault Aviation, KNDS, Czechoslovak Group, PGZ, Fincantieri,
ThyssenKrupp (as TKMS only), Hensoldt, Diehl, Kongsberg, Navantia); General Dynamics through GDELS and Santa Bárbara Sistemas (FEINDEF
exhibitor page); Indra (its 2026 supplier selection for automotive firms, elDiario.es 16 June 2026, as in the research). A Spanish UTE
with a prime is marked "Joint venture with ...". Patterns were tested against every production winner name that contains one of these
group words (165 names): false friends excluded and tested (`lambda` for MBDA, Kongsberg Automotive, Rolls-Royce Motor Cars, Saab
automobile, Fundación Santa Bárbara, Leonardo hotels, Babcock Wanson, thyssenkrupp Rothe Erde, Dassault Systèmes).

**Appendix guides and grants** (`lib/es-support.ts`, only what the research states, with its link; `wp80.check.ts` fails on a URL or a
figure not in the research): RID: CAETRA guide (Nov 2024); PECAL/AQAP 2110/2310: CAETRA guide (June 2026); grants: Murcia CAETRA CS001
(RID, EUR 2,500), CS002 (PECAL/AQAP or EN 9100, EUR 9,000 per standard), CS004 (HSEM EUR 4,000 / HSES EUR 10,000), all "list of services
2025"; Aragón IAF Orden ECE/1276/2026 (RID, PECAL/AQAP, ISO 9001, EN 9100, HSEM/HSES; EUR 5,000-30,000, 70 %/50 %; window 7-25 Sep 2026,
closed); Galicia IN519G (RID, PECAL/AQAP, HSEM/HSES; up to EUR 75,000, 80 %; 13 Feb-13 May 2026, closed); Extremadura Consolidapyme
(PECAL/AQAP; 80 %, PECAL eligible cost up to EUR 11,000; closed 27 Jul 2026); ACCIÓ's free 7-hour course (Catalonia) above the roadmap.
Every grant list ends "Check the current call before you count on it ...". The company's own region is listed first and marked; grants
are shown only for a company established in Spain. NCAGE, PIC, export classification: no guide or grant in the research, none shown.

## 2. Acceptance criteria

| Criterion | Met | Evidence |
|---|---|---|
| "Who to approach" first in the report and in the supplier results | yes | e2e `wp80.spec.ts` 1 (section order `r-approach, r-demand, r-results, r-roadmap, r-profile, r-about`) and 2 (h2 order on `/readiness/results`) |
| Supplier's CPV codes, ES/DE/FR/PL/NL, 3 years; legal entities; TED + PLACSP deduplicated | yes | same scope as WP-66; twins: `test_a_twin_pair_counts_once_...`; natural persons/removed as WP-66 tests |
| Mosaic rule: fewer than 3 awards as an aggregate count | yes | `test_a_winner_is_named_across_countries_from_k_min_...` (2-award winner counted only; a winner below 3 in each country but 3 across them is named), `wp80.check.ts` on the demo |
| Number of contracts, main buyers, countries, last award date, supplier page link (stated value: removed by decision) | yes, with one honest limit | no value per supplier (`test_no_sum_of_values_per_supplier`, `wp80.check.ts`); "last award date" is the latest notice's publication date (PLACSP has no stored award date); link only where the page exists (`test_the_supplier_page_is_linked_only_where_...`) |
| Marked "prime or large defence group" from existing signals or a sourced curated list | yes | curated list with sources + EDF projects + defence-buyer flag, separate; `test_wp80_primes.py` (28 true, 14 false names), `test_a_prime_is_marked_...`, primes never cut (`test_a_prime_is_listed_past_the_end_of_the_list`) |
| Honest explainer (subcontractors; public notices miss work through primes) | yes | `ApproachExplainer`, e2e checks both sentences |
| Reuse/extend POST /v1/readiness/demand, stateless | yes | one new field; nothing stored (WP-66 `test_nothing_is_stored_or_logged` still green) |
| Budget: under 1 s typical, under 3 s worst, measured on production | **worst yes: at most 2.6 s served, refusals 0.3-0.45 s; typical 0.2-1.2 s (on a server at load 3-4 on 2 cores)** | section 4; `test_a_request_that_matches_too_many_notices_is_refused_...` |
| Demand next (buyers by country) | yes | `r-demand` second |
| Rules as appendix with free guide and regional grant per requirement, links, "check the current call", no invented amounts | yes | `Support`, `wp80.check.ts` (URLs and figures held to the research), e2e (RID: guide link, Galicia first, "Check the current call"; NCAGE: nothing) |
| Entry page and supplier page copy in the new order, every changed string listed | yes | section 5; e2e `wp80.spec.ts` 4, `wp68.spec.ts` updated |

## 3. "Who to approach" for three sample profiles (production, 22 October 2026, PLACSP switch on as in production)

Same three profiles as the WP-66 self-check. "Page": a supplier page exists and is linked. No value per supplier.

### Castings (44470000 cast-iron products, 34312000 engine parts, 34322000 brakes, 42140000 gears, 44210000 structures)

101 winners (legal entities) of 107 procurements with a published winner; 7 named (3 or more contracts), 94 counted only (107 awards), 0 past the 30th (0 awards). Primes marked: none. Timings of the whole call, three runs: 0.41, 0.24, 0.284 s.

| # | Company | Contracts | Countries | Latest notice | Main buyers (contracts) | Mark | Page |
|---|---|---|---|---|---|---|---|
| 1 | Suyfa Defence, S.L. (ES) | 9 | ES | 2026-09-24 | Dirección de Gestión Económica de la Jefatura de Apoyo Logístico de la Armada (5); Intendente de Ferrol (3); Intendente de las Palmas (1) | - | yes |
| 2 | ALFARIVER DEFENSE S.L. (ES) | 6 | ES | 2026-10-02 | Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (6) | - | yes |
| 3 | CLIA SISTEMAS, S.L. (ES) | 3 | ES | 2026-05-15 | Jefatura de la Sección Económico Administrativa 22 - Base Aérea de Torrejón (Agrupación de Base) (2); Jefatura de la Sección Económico-Administrativa 62 - Base Aérea de Cuatro Vientos (1) | - | yes |
| 4 | ELYER SAN FERNANDO 2014, S.L. (ES) | 3 | ES | 2026-06-30 | Intendente de San Fernando (2); Jefatura de Asuntos Económicos de la Fuerza Terrestre (1) | - | yes |
| 5 | PREFABRI, S.L. (ES) | 3 | ES | 2026-08-04 | Dirección General del INTA (2); Jefatura de Intendencia de Asuntos Económicos Centro (1) | - | no |
| 6 | SUMINISTROS SANTO DOMINGO SL (ES) | 3 | ES | 2025-07-21 | Jefatura de Asuntos Económicos de la Fuerza Terrestre (3) | - | no |
| 7 | TRIPLE TANGO S.L. (ES) | 3 | ES | 2025-07-04 | Jefatura de la Sección Económico-Administrativa 62 - Base Aérea de Cuatro Vientos (3) | - | yes |

### Electronics (31711100 electronic components, 31712300 printed circuits, 31610000 electrical equipment for engines and vehicles, 31612000 wiring looms, 31400000 batteries)

80 winners (legal entities) of 106 procurements with a published winner; 11 named (3 or more contracts), 69 counted only (76 awards), 0 past the 30th (0 awards). Primes marked: none. Timings of the whole call, three runs: 0.398, 0.302, 0.186 s.

| # | Company | Contracts | Countries | Latest notice | Main buyers (contracts) | Mark | Page |
|---|---|---|---|---|---|---|---|
| 1 | Suyfa Defence, S.L. (ES) | 15 | ES | 2026-10-14 | Intendente de San Fernando (9); Dirección de Gestión Económica de la Jefatura de Apoyo Logístico de la Armada (4); Intendente de Ferrol (1) | - | yes |
| 2 | MADZEAL, S.L. (ES) | 10 | ES | 2026-08-17 | Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (9); Sección de Asuntos Económicos del Parque y Centro de Mantenimiento de Sistemas Acorazados 2 (1) | - | yes |
| 3 | AEG POWER SOLUTIONS IBERICA S.A. (ES) | 9 | ES | 2025-11-27 | Dirección de Gestión Económica de la Jefatura de Apoyo Logístico de la Armada (8); Sección de Asuntos Económicos del Parque y Centro de Mantenimiento de Sist. Antiaérea, Costa y Misiles (1) | - | yes |
| 4 | SANCHEZ SUR SL (ES) | 8 | ES | 2025-10-25 | Intendente de Rota (8) | - | yes |
| 5 | ANKOL Sp. z o.o. (PL) | 4 | PL | 2026-09-30 | 8. Baza Lotnictwa Transportowego w Krakowie - Balicach (3); 3 Regionalna Baza Logistyczna Wydział Techniki Lotniczej (1) | - | yes |
| 6 | DISTRIBUCION DE BATERIAS MORENO BOLUDA, S.L. (ES) | 4 | ES | 2025-08-19 | Intendente de Cartagena (4) | - | yes |
| 7 | TEDITRONIC, SL (ES) | 4 | ES | 2026-05-14 | Jefatura de Asuntos Económicos de la Fuerza Terrestre (1); Jefatura de Asuntos Económicos del Cuartel General Terrestre Alta Disponibilidad (1); Intendente de las Palmas (1) | - | yes |
| 8 | APUS GLOBAL, S.L. (ES) | 3 | ES | 2025-07-21 | Dirección General del INTA (3) | - | yes |
| 9 | Borimex Sp. zo.o. (PL) | 3 | PL | 2026-07-21 | 8. Baza Lotnictwa Transportowego w Krakowie - Balicach (3) | - | yes |
| 10 | EURONAVAL SERVICIOS INTEGRALES SL (ES) | 3 | ES | 2026-09-16 | Intendente de San Fernando (2); Jefatura de Asuntos Económicos de la Fuerza Terrestre (1) | - | yes |
| 11 | EXIDE Technologies GmbH (DE) | 3 | DE | 2026-07-16 | Bundesamt für Ausrüstung, Informationstechnik und Nutzung der Bundeswehr (3) | - | yes |

### Vehicle parts (34300000, 34100000, 35421000, 42600000, 44300000 (the WP-65 sample))

496 winners (legal entities) of 1310 procurements with a published winner; 32 named (3 or more contracts), 372 counted only (448 awards), 92 past the 30th (409 awards). Primes marked: SAAB AB (Saab), Indra Sistemas, S.A. (Indra). Timings of the whole call, three runs: 0.888, 1.55, 1.34 s.

| # | Company | Contracts | Countries | Latest notice | Main buyers (contracts) | Mark | Page |
|---|---|---|---|---|---|---|---|
| 1 | FERRETERIA FERAYU S.L. (ES) | 73 | ES | 2026-10-19 | Jefatura de Asuntos Económicos de la Fuerza Terrestre (17); Jefatura de Intendencia de Asuntos Económicos Este (15); Jefatura de Intendencia de Asuntos Económicos Centro (10) | - | yes |
| 2 | SUMINISTROS MERA SL (ES) | 56 | ES | 2026-10-21 | Jefatura de Intendencia de Asuntos Económicos Este (56) | - | yes |
| 3 | URO VEHICULOS ESPECIALES, S.A. (ES) | 49 | ES | 2026-09-10 | Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (37); Intendente de San Fernando (7); Jefatura de la Sección Económico-Administrativa 27 - Base Aérea de Getafe (2) | - | yes |
| 4 | Suyfa Defence, S.L. (ES) | 40 | ES | 2026-09-25 | Intendente de San Fernando (10); Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (8); Dirección de Gestión Económica de la Jefatura de Apoyo Logístico de la Armada (5) | - | yes |
| 5 | ITURRI S.A. (ES) | 38 | ES | 2026-10-19 | Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (20); Dirección de Adquisiciones del Mando de Apoyo Logístico del Ejército del Aire y del Espacio (7); Intendente de Cartagena (4) | - | yes |
| 6 | FERRETERIA ARIES SA (ES) | 36 | ES | 2026-10-02 | Jefatura de Intendencia de Asuntos Económicos Este (36) | - | yes |
| 7 | IVECO ESPAÑA, S.L. (ES) | 36 | ES | 2026-01-13 | Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (19); Dirección de Gestión Económica de la Jefatura de Apoyo Logístico de la Armada (11); Dirección de Adquisiciones del Mando de Apoyo Logístico del Ejército del Aire y del Espacio (3) | - | yes |
| 8 | SUMINISTROS SANTO DOMINGO SL (ES) | 32 | ES | 2026-08-11 | Jefatura de Intendencia de Asuntos Económicos Sur (11); Jefatura de Asuntos Económicos de la Fuerza Terrestre (9); Jefatura de Intendencia de Asuntos Económicos Centro (3) | - | no |
| 9 | Ferretería Rafa S.L. (ES) | 31 | ES | 2026-08-25 | Jefatura de Asuntos Económicos de la Fuerza Terrestre (10); Jefatura de Intendencia de Asuntos Económicos Sur (9); Jefatura de la Sección Económico Administrativa 24 de la Base Aérea de Morón (7) | - | no |
| 10 | RECAMBIOS COLON CATARROJA SL (ES) | 31 | ES | 2026-10-02 | Jefatura de Intendencia de Asuntos Económicos Este (21); Jefatura de Asuntos Económicos del Cuartel General Terrestre Alta Disponibilidad (5); Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (1) | - | yes |
| 11 | VOLVO GROUP ESPAÑA, S.A.U. (ES) | 30 | ES | 2026-10-19 | Jefatura de la Sección de Asuntos Económicos de la Unidad Militar de Emergencias (17); Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (9); Dirección de Adquisiciones del Mando de Apoyo Logístico del Ejército del Aire y del Espacio (2) | - | yes |
| 12 | C & A COMERCIAL ARTIGAS E HIJOS SL (ES) | 27 | ES | 2026-10-05 | Jefatura de Intendencia de Asuntos Económicos Este (24); Jefatura de la Sección Económico-Administrativa 26 - Base Aérea de Zaragoza (Agrupación BASE) (3) | - | yes |
| 13 | IBERDEFENSA MANTENIMIENTO TECNICO SL (ES) | 24 | ES | 2026-09-16 | Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (8); Jefatura de la Sección Económico-Administrativa 27 - Base Aérea de Getafe (6); Jefatura de Intendencia de Asuntos Económicos Este (3) | - | yes |
| 14 | MADZEAL, S.L. (ES) | 24 | ES | 2026-10-20 | Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (12); Intendente de San Fernando (5); Sección de Asuntos Económicos del Parque y Centro de Abastecimiento de Material de Intendencia (5) | - | yes |
| 15 | COMERCIAL HERNANDO MORENO COHEMO SL (ES) | 23 | ES | 2026-09-16 | Sección de Asuntos Económicos del Parque y Centro de Abastecimiento de Material de Intendencia (12); Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (7); Sección de Asuntos Económicos del Parque y Centro de Mantenimiento de Sistemas Acorazados 2 (3) | - | yes |
| 16 | RECAMBIOS Y ACCESORIOS GGR, S.L. (ES) | 18 | ES | 2026-09-30 | Jefatura de Intendencia de Asuntos Económicos Centro (5); Jefatura de Asuntos Económicos del Cuartel General Terrestre Alta Disponibilidad (4); Intendencia de Madrid (2) | - | yes |
| 17 | SUMINISTROS IGBUR, S.L.U. (ES) | 17 | ES | 2026-09-23 | Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (14); Sección de Asuntos Económicos de la Jefatura Sistemas de Información, Telecomunicaciones y Asistencia Técnica (1); Jefatura de Intendencia de Asuntos Económicos Este (1) | - | yes |
| 18 | Advantage Servicios y Diseños (ES) | 15 | ES | 2026-10-20 | Intendencia de Madrid (15) | - | yes |
| 19 | FERRETERIA ASENSI HERVAS SLU (ES) | 15 | ES | 2026-09-24 | Jefatura de Intendencia de Asuntos Económicos Este (12); Jefatura de Asuntos Económicos del Cuartel General Terrestre Alta Disponibilidad (3) | - | no |
| 20 | EURONAVAL SERVICIOS INTEGRALES SL (ES) | 14 | ES | 2026-09-04 | Jefatura de Intendencia de Asuntos Económicos Sur (5); Intendente de Ferrol (5); Intendente de las Palmas (3) | - | yes |
| 21 | EMPRESA MONFORTE SA (ES) | 13 | ES | 2026-06-17 | Dirección de Adquisiciones del Mando de Apoyo Logístico del Ejército del Aire y del Espacio (12); Jefatura de Intendencia de Asuntos Económicos Sur (1) | - | yes |
| 22 | FERREGAS GARCIA-VASO, S.L. (ES) | 13 | ES | 2026-09-10 | Intendente de Cartagena (13) | - | no |
| 23 | FERRO SUMINISTROS INDUSTRIALES S.L. (ES) | 12 | ES | 2026-09-24 | Jefatura de Asuntos Económicos del Cuartel General Terrestre Alta Disponibilidad (6); Jefatura de Intendencia de Asuntos Económicos Este (5); Jefatura de Asuntos Económicos de la Fuerza Terrestre (1) | - | no |
| 24 | GRUPO PEÑA AUTOMOCION, S.L.U (ES) | 12 | ES | 2026-04-07 | Jefatura de Intendencia de Asuntos Económicos Sur (3); Jefatura de la Sección Económico Administrativa 24 de la Base Aérea de Morón (3); Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (1) | - | yes |
| 25 | REDONDOYGARCIA, S.A. (ES) | 12 | ES | 2025-11-20 | Sección de Asuntos Económicos del Parque y Centro de Mantenimiento de Sistemas Acorazados 2 (6); Jefatura de la Sección Económico-Administrativa 27 - Base Aérea de Getafe (2); Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (1) | - | yes |
| 26 | Grupo de ingeniería, reconstrucción y recambios JPG S.A. (ES) | 11 | ES | 2026-10-09 | Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (4); Jefatura de Intendencia de Asuntos Económicos Este (2); Sección de Asuntos Económicos del Parque y Centro de Mantenimiento de Sistemas Acorazados 2 (2) | - | yes |
| 27 | INTEGRACION TECNOLOGICA EMPRESARIAL, S.L. (ES) | 11 | ES | 2026-06-03 | Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (4); Jefatura de Asuntos Económicos de la Fuerza Terrestre (2); Sección de Asuntos Económicos del Parque y Centro de Mantenimiento de Helicópteros (2) | - | yes |
| 28 | UTE ITURRI,S.A.-GAUZON IBERICA,SLU LEY 18/1982 (ES) | 11 | ES | 2026-03-05 | Intendente de Cartagena (9); Intendente de San Fernando (2) | - | no |
| 29 | CORVUS INNOVA, SL (ES) | 10 | ES | 2026-08-24 | Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (6); Dirección de Adquisiciones del Mando de Apoyo Logístico del Ejército del Aire y del Espacio (1); Jefatura de Intendencia de Asuntos Económicos Sur (1) | - | no |
| 30 | CONTINENTAL TIRES ESPAÑA S.L. (ES) | 9 | ES | 2026-10-19 | Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (7); Sección de Asuntos Económicos del Parque y Centro de Mantenimiento de Vehículos Ruedas Nº 1 (2) | - | yes |
| 31 | SAAB AB (SE) | 4 | ES | 2026-08-11 | Jefatura de Asuntos Económicos del Mando de Apoyo Logístico (4) | Prime: Saab, EDF 3 | yes |
| 32 | Indra Sistemas, S.A. (ES) | 3 | ES | 2026-02-27 | Jefatura de la Sección de Asuntos Económicos de la Unidad Militar de Emergencias (2); Intendente de Ferrol (1) | Prime: Indra, EDF 64 | yes |

Reading (checked by hand against the notices, read-only SQL):
- Spain dominates because PLACSP publishes winners for nearly every Spanish procurement; in DE/FR/PL/NL only TED result notices name
  winners, and few companies reach 3 contracts there (electronics: EXIDE in DE, ANKOL and Borimex in PL).
- The direct winners are mostly distributors and service firms (ferreterías, recambios) and vehicle makers' Spanish arms (URO, Iveco
  España, Volvo Group España). Primes appear where they win directly: Saab AB (4: individual duel simulators, CPV 34150000, which sits
  under group 341) and Indra Sistemas (3: simulators and a radar maintenance contract; its TED and PLACSP notices of the Ferrol contract
  count once). That is what the explainer says: the work through primes is not in public notices.
- Hand check: the two marked primes notice by notice (read-only SQL: all 10 award rows of Saab AB and Indra Sistemas in this answer's
  scope, with buyer, date, CPV, winners and value): every row is a defence-scope award under one of the codes, the buyers match the list,
  and the TED and PLACSP notices of one purchase count once (Saab: 6 rows give 4 contracts: the 2024 SDU purchase is in both sources,
  and one further row is not counted, not traced further; Indra: 4 rows give 3, the Ferrol radar contract is in both). The other 48
  named winners of the three samples were checked by name only: each carries a company form (S.L., S.A., Sp. z o.o., GmbH, AB, UTE) or
  is a company name ("Advantage Servicios y Diseños"); no person's name is shown.
- Not marked although large: URO Vehículos Especiales, Iveco España / IDV, Escribano (EM&E), Nammo Palencia, Expal (marked: Rheinmetall
  Expal Munitions carries the name). They are not on the SIPRI 2024 list; adding a national-prime list needs a source.

## 4. Timing (production, read-only)

First version: 5-code profiles 0.1-1.3 s, 15 whole divisions 4-5.6 s (over the 3 s target, near the API's 5 s budget). Follow-up
(orchestrator decision): **a request whose codes match more than 30,000 defence-scope notices (window and countries asked) is refused**
with `422 {"detail": {"code": "too_broad", "message": "These CPV codes cover too many defence-scope notices for one map (more than
30,000 in three years). Choose more specific codes: a group such as 34300000 rather than a whole division such as 34000000, or fewer
codes."}}`, the codes not echoed; the report and the results page show that sentence in place of the lists. The count runs first with a
`LIMIT 30,001`, so a refusal costs one bounded index read. The cap was chosen on these measurements: time grows with the matched notices
(8,130: about 1 s; 22,921: 1.6-2.4 s; 40,843: 2.3-2.6 s; 116,562: 5.6-6.0 s, all with a one-off worker job using one of the server's two
cores, load average 3-4). Whole `demand()` call, inside `dgate-api-1`, after the change:

| Codes (whole divisions unless named) | matched notices | count (s) | `demand()` two runs (s) |
|---|---|---|---|
| vehicle parts | 8,130 | 0.174 | 0.915, 1.219 |
| 34 | 10,696 | 0.15 | 0.803, 0.695 |
| 44 | 8,776 | 0.105 | 0.613, 0.585 |
| 35 | 16,830 | 0.174 | 2.633, 1.731 |
| 34+44 | 18,553 | 0.314 | 1.489, 1.484 |
| 34+44+31 | 22,921 | 0.15 | 1.592, 2.446 |
| 34+35 | 26,094 | 0.227 | 1.67, 2.152 |
| 35+31+44 | 29,012 | 0.235 | 2.086, 2.042 |
| 34+44+31+35 | 37,531 | 0.315 | refused in 0.361, refused in 0.329 |
| 34+44+31+35+42 | 40,843 | 0.604 | refused in 0.411, refused in 0.438 |
| 15 divisions | 116,562 | 0.872 | refused in 0.348, refused in 0.366 |

The worst case served (29,012 notices, three whole divisions) took 2.0-2.1 s, the slowest served run 2.6 s (division 35 alone, once);
refusals 0.33-0.44 s. A single whole division (34, 35, 44) is served. Considered and not built: a per-code cache (state in the API
process, and the merge would still read every row) and a materialised per-code aggregate (a new table and worker job for one endpoint);
the cap is one statement and keeps the endpoint stateless.

`EXPLAIN ANALYZE` of the 15-division statement (first version): the matched rows `m`, the buyer counts `b` and the per-code counts `k`
dominate, as in WP-66; what WP-80 adds (twin filter, `ap`, `apb`, `_edf_projects`, `_with_page`) is about 0.15-0.3 s. Two WP-66 counts
were rewritten as hash aggregates (`c`, `k`).

## 5. Every changed copy string

Entry page `/readiness/spain-automotive`:
- Title: "Spain automotive suppliers: defence readiness" -> "Spain automotive: who to approach in defence".
- Description -> "For civilian manufacturers in Spain, such as automotive suppliers: who wins defence contracts under your CPV codes in five countries, who buys, and the rules."
- Lead -> "For civilian manufacturers in Spain, such as automotive component suppliers, that are considering defence work. You say what you make; the report starts with the companies that win defence contracts for it in five countries, then who buys it, then the rules, each with its source."
- "What you get", in the new order:
  - "Who to approach. The companies that won defence-scope contracts under the CPV codes you choose in Spain, Germany, France, Poland and the Netherlands over the last three years, from TED and the Spanish national portal (PLACSP), each contract counted once: how many contracts, the buyers they win from, the countries, the date of the latest notice, and a link to their supplier page. Prime contractors and large defence groups are marked, with the source of the list. A company is named only from three awards up; the others are counted."
  - "Who buys what you make. The buyers of those codes in the five countries (core defence buyers and others), how many procurements, how many under Directive 2009/81/EC, and the newest notices."
  - "The rules, as an appendix. Your answers against the rules of the Spanish Ministry of Defence supplier route, NATO supply and the EU defence programmes, each with its source; then the steps in order (what you hold, what you need now, what usually comes with a first contract, such as the PECAL quality certificate), each with the free guide and the regional grants that have paid for it."
  - "A printable report of all of it, which you can print or save as a PDF." (was "of all three")
  - Removed: "A readiness check. ...", "A roadmap. ...", "A demand map. ..." (their content is in the three items above).
- New paragraph: "Why this order: automotive suppliers usually enter defence as subcontractors of the prime contractors and their large suppliers, and in Spain the rules are already explained for free (the CAETRA guides of the Región de Murcia, a course of ACCIÓ in Catalonia) and regional programmes have paid for the certifications. What we did not find elsewhere is who wins these contracts across the five countries."
- "What it is not", third item, last sentence: "The demand map shows who buys directly and who won, not what primes need." -> "The report shows who won and who buys directly, not what primes need."
- Live sample (only with a live answer), new line: "{n} companies won them; {n} companies won 3 or more and would be named in the report, {n} of them is/are marked as a prime contractor or large defence group."
- Spanish summary -> "Para fabricantes civiles establecidos en España, por ejemplo proveedores de componentes de automoción, que estudian suministrar a compradores de defensa. El informe empieza por las empresas que ganan contratos de defensa con sus códigos CPV en España, Alemania, Francia, Polonia y los Países Bajos, marcando los contratistas principales y los grandes grupos de defensa; sigue con quién compra esos códigos; y termina, como anexo, con las reglas de la ruta de proveedor del Ministerio de Defensa, del suministro OTAN y de los programas de defensa de la UE, cada una con su fuente, la guía gratuita y las ayudas regionales que han cubierto cada paso. Se puede imprimir. Es orientativo, no es asesoramiento jurídico y no garantiza ningún contrato. La herramienta está en inglés."

Supplier page `/readiness/supplier`:
- Title: "Supplier profile: what a parts or materials maker needs to supply defence buyers" -> "Supplier profile: who to approach in defence".
- Description -> "Say what you make (CPV codes) and what you hold: see who wins defence contracts for it in five countries, who buys it, and which rules of the Spanish MoD route, NATO supply and the EU programmes apply to you, each with its source."
- Lead -> "For a company that makes parts or materials and wants defence work. Say what you make and what you hold; the results start with the companies that win defence contracts for what you make, then who buys it, then what the buyers' routes ask of you, rule by rule."
- "Who this is for", second paragraph replaced by two: "From your CPV codes it lists first who to approach: the companies that won defence-scope contracts for them in Spain, Germany, France, Poland and the Netherlands over the last three years, with prime contractors and large defence groups marked, since automotive suppliers usually enter defence as their subcontractors. Then who buys those codes." and "Then the rules: your answers against the Spanish Ministry of Defence supplier route, NATO supply and the EU defence programmes, each with its source, and what you already hold, what you need now, and what usually comes with a first contract, such as the PECAL quality certificate, each step with the free guide and the regional grants that have paid for it. Once you save, your results link to a report you can print or save as a PDF."
- Callout: "... and the one for the map of who buys what you make, ..." -> "... and the one for who wins and who buys what you make, ...".

Report `/readiness/supplier/report` (new or changed):
- Section "Who to approach" (new, first); explainer: "Automotive suppliers usually enter defence as subcontractors: they sell to the prime contractors and their large suppliers, not to a ministry. In Spain, Indra opened a supplier selection for automotive firms in 2026 for its military vehicle programmes (elDiario.es, 16 June 2026)." and "Public notices miss most of that work: what a prime buys from its own suppliers is not published. The list below shows who won the published defence-scope contracts under your CPV codes; a company marked as a prime contractor or large defence group is one to offer your work to as a subcontractor; the others supply the buyers directly."
- Summary: "From {since} to {until}, in {countries}: {n} companies won defence-scope procurements under your codes. {n} won 3 or more and are named below, most contracts first." / "None won 3 or more, so none is named."
- Headings "Prime contractors and large defence groups among them", "The other named winners" / "The named winners"; none-marked text: "None of the named winners is on our list of prime contractors and large defence groups (the European companies of the SIPRI Top 100 of 2024, and Indra). Primes may still buy what you make from their own suppliers; that is not published."
- Per winner: tags "Prime or large defence group: {group}" / "Joint venture with {group}", "EDF projects: {n}", "Also a defence buyer"; "{n} contracts won in {countries}; latest notice published {date}."; "Wins most from: {buyer} ({n}); ..."; "Listed by name from: {source}."
- Counts: "{n} other winners with fewer than 3 awards each ({n} awards together) are counted, not named." and "{n} more winners with 3 or more awards ({n} awards) are not listed: the list stops at 30, and every prime contractor or large defence group is on it."
- Note: "A contract here is a procurement with a published winner, counted once however many notices publish it; no value is summed per company. The latest notice is the newest publication among them: for Spain’s national portal (PLACSP) the date the procurement was published, since its award date is not stored. Marked by name: a group member that carries the group’s name; a subsidiary under another name is not marked."
- Too broad (from the API, shown in place of the lists): "These CPV codes cover too many defence-scope notices for one map (more than 30,000 in three years). Choose more specific codes: a group such as 34300000 rather than a whole division such as 34000000, or fewer codes."
- Without codes: "Choose the CPV codes of what you make on your supplier profile, and this section lists the companies that win those contracts." and button "Add CPV codes to my supplier profile".
- Loading/error: "Finding who wins these contracts", "The list could not be computed"; the readiness error title "The report could not be computed" -> "The readiness appendix could not be computed".
- Section titles: "Readiness results" -> "Appendix A: readiness results"; "Supplier roadmap" -> "Appendix B: supplier roadmap, with the free guides and grants"; "Company profile" -> "Appendix C: company profile" (moved after the appendices).
- Appendix B intro (Spain only): "In Spain these steps are covered by free public material: the guides to the RID and to PECAL/AQAP of Murcia’s CAETRA programme, and regional programmes that have paid for the steps themselves (on each step below, with the call or list they come from). A free course:" + the ACCIÓ line "{title} (ACCIÓ (Generalitat de Catalunya), announced 10 April 2026[, your region]): a free 7-hour in-person course for 400 companies (automotive, space, metalworking, machinery) on certifications, homologation and access to state and EU procurement."
- Per step: "Free guide: {title} ({by}, {date})."; "Regional grants that have paid for this step:" + "{region}[ (your region)]: {programme}, for {covers}; {amounts} ({call read})."; "Check the current call before you count on it: windows, amounts and conditions change from one call to the next, and the figures are those of the call or list named."

Results page `/readiness/results`: section "Who to approach" (first, with the explainer, up to 8 winners primes first, "No company won 3 or more defence-scope procurements under your codes in the last three years, so none is named.", button "Every named winner in your supplier report"); the demand table's button "Buyers, winners and notices in your supplier report" -> "Buyers and notices in your supplier report" (the old label made the page 401 px wide at 375 px once the answer arrived).

## 6. Tests and results

New: `backend/tests/unit/test_wp80_primes.py` (46 cases), `backend/tests/integration/test_wp80_approach.py` (9), `web/lib/wp80.check.ts`,
`web/e2e/wp80.spec.ts` (5 tests x desktop and 375 px, with a side-scroll check after the answer arrives). Changed, nothing loosened:
`e2e/wp68.spec.ts` (the title and the four "What you get" items, the copy changed), `e2e/wp66.spec.ts` (the button label).
`web/lib/mock/demand.json` regenerated from production (now with the PLACSP winners, as production serves them; one partnership named
after its partners left out of the named lists, as WP-66 did).

Local, `D:\DEFENCEGATE TESTS\wp80`, own venv (uv), throwaway Postgres 17 container `dgate-wp80` on 55480, TZ=UTC, web mock env of
`web.yml`, Playwright 4 workers:

| Check | Result |
|---|---|
| ruff | All checks passed |
| unit (`pytest`) | 3126 passed, 1200 deselected (follow-up run) |
| integration (`pytest -m integration`) | follow-up run: 1199 passed, 1 failed (the new too-broad test asserted the request code was absent, but the refusal sentence quotes 34300000 as its example; the test now asks for another code); after the fix the WP-80 and WP-66 integration files: 21 passed |
| `tsc --noEmit` | exit 0 |
| `npm run check` | all ok, incl. `wp80.check.ts`, `wp66`, `wp68` |
| `next build` (mock) | exit 0 |
| Playwright, 4 workers, desktop + 375 px | follow-up run: **519 passed, 47 skipped (the fake-API group, as before), 0 failed** (incl. the new too-broad report test) |

Earlier full runs failed and were fixed (section 7): WP-67's print test (guide link before the source link) and the 375 px side
scroll of the results page (button label).

## 7. Hostile review

Found and fixed 7:
1. The supplier-page link was decided from the notices of this answer: a company with a page (core-scope awards under other codes) showed
   no link, and the same company had a link in one sample and not in another. Now read from the supplier map's own scope (`_with_page`).
2. "Latest award date": PLACSP rows carry the procurement's publication date, not the award date; the copy now says "latest notice published".
3. The roadmap's free guide was placed above the rule's own source, so the rule's link stopped being the first link of the step (WP-67's
   print test caught it): the guides and grants now follow the source.
4. The demand table's button overflowed the 375 px layout once the answer arrived (it had been measured before the answer); shortened,
   and the new e2e measures again after the lists are on the page.
5. Primes past the 30th were cut by the list's end: every marked prime is now listed, and the cut is said ("more").
6. Two organisation rows of one company winning the TED and the PLACSP notice of one procedure counted as two winners (WP-66's open point):
   `award_twin_set` now applies to the whole map.
7. The worst case got slower with the added CTEs; two counts rewritten as hash aggregates, then (follow-up) requests over 30,000 matched
   notices refused (section 4).
8. (Follow-up) The per-supplier value sums contradicted the supplier map's rule: removed from the API, the page, the demo answer and the tests.

## 8. Limits and open points (owner decisions marked)

- The prime list is a name match on a curated list of 23 groups; national primes outside the SIPRI list (URO, Iveco/IDV, Escribano,
  Nammo) are not marked. A subsidiary under another name (e.g. a PGZ company not called PGZ) is not marked.
- A Polish partnership named after its partners ("CLAYMORE GROBLEWSCY sp. j.") is a legal entity to the directory and is named by the
  API when it has 3 contracts (as in WP-66); the demo answer leaves it out.
- Very broad requests (more than 30,000 matched notices, e.g. four or more whole divisions) are refused, not answered. The Spanish winners depend on the PLACSP switch staying on;
  the entry page names PLACSP as a winner source.
- Grants are those of the research of 22 October 2026; Aragón, Galicia and Extremadura windows are closed (said on each line).
- Navigation: no new route. Deletion candidates: none. Production commands: none (no migration; deploy as usual). After deploy:
  `POST /v1/readiness/demand` with the vehicle-parts codes from inside `dgate-api-1` should give 32 named winners, Saab AB and Indra marked.
- Scratch: `D:\DEFENCEGATE TESTS\wp80` (kept, as earlier packages: venv, repo copy, probe scripts and outputs), container `dgate-wp80`
  (removed at the end).
