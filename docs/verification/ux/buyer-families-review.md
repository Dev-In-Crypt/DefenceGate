# Buyer families: precision review (WP-22, 16 October 2026)

Method: the rules of `backend/dgate/buyer_family.py` were run (`groups_of`) over the 6,908 organisations that are the buyer of at least one defence notice on production (read-only SQL, `opportunity` joined to `organisation`, one query of under a second). Every group formed is listed below with a judgement. "Core" is the default list's scope (`CORE_SQL`), "defence" is `is_defence`. A group needs two organisation rows; the head is the row with most defence notices, then the lowest id.

## Result

- **217 groups, 622 member rows** (non-head rows put under a head). No group was removed after review.
- **3,730 core notices** (and 10,141 defence notices of all scopes) move from a member row to the head's count.
- Core buyers on the list: **2,184 before, 2,031 after** (153 fewer cards). 148 of the groups touch the core list.

### The biggest 15 buyers on the core list, before and after

| # | before (organisation row) | core | after (family) | core | rows |
|---|---|---:|---|---:|---:|
| 1 | bundesamt fur ausrustung informationstechnik und nutzung der | 4,688 | bundesamt fur ausrustung informationstechnik und nutzung der | 5,363 | 144 |
| 2 | hil heeresinstandsetzungslogistik | 2,963 | hil heeresinstandsetzungslogistik | 2,986 | 3 |
| 3 | ministerstvo obrany | 2,906 | ministerstvo obrany | 2,906 | 1 |
| 4 | jefatura de asuntos economicos del mando de apoyo logistico | 1,843 | minarm dga do s2a | 2,212 | 7 |
| 5 | minarm dga do s2a | 1,406 | jefatura de asuntos economicos del mando de apoyo logistico | 1,843 | 1 |
| 6 | 3 regionalna baza logistyczna w krakowie | 1,364 | 3 regionalna baza logistyczna w krakowie | 1,364 | 1 |
| 7 | ministerie van defensie | 1,091 | mindef air siae | 1,341 | 3 |
| 8 | direccion de gestion economica de la jefatura de apoyo logis | 983 | ministerie van defensie | 1,091 | 1 |
| 9 | mindef air siae | 893 | direccion de gestion economica de la jefatura de apoyo logis | 986 | 2 |
| 10 | fmv | 763 | fmv | 763 | 1 |
| 11 | ministrstvo za obrambo | 761 | ministrstvo za obrambo | 761 | 1 |
| 12 | danish ministry of defence acquisition and logistics organis | 757 | marinearsenal | 758 | 27 |
| 13 | 2 regionalna baza logistyczna | 734 | danish ministry of defence acquisition and logistics organis | 757 | 1 |
| 14 | inspektorat uzbrojenia | 699 | inspektorat uzbrojenia | 748 | 5 |
| 15 | puolustusvoimien logistiikkalaitos | 661 | 2 regionalna baza logistyczna | 734 | 1 |

Nothing is merged that was not already one body by name (judgements below).

## What the registration numbers say (and do not)

Nearly every group contains rows with different `national_reg_no` values. These values mix schemes (VAT numbers, SIRET, Leitweg-ID, per-notice codes): the two Spanish `intendente de rota` rows carry `S2800147G` and `10000140007381`, the two `jednostka wojskowa nr 6021` rows a REGON-like and a NIP-like number, the BAAINBw rows 94 different values. A difference of numbers therefore does not show two bodies. The owner's decision not to merge rows with different numbers (`buyer_cleanup --merge-conflicting`) is untouched: this layer merges nothing, it only displays. `python -m dgate.ops.buyer_families` prints the number of distinct values for each group.

## Judgement per group

"yes" = one body. The reason for an identical-name group is the same: the same normalised name in the same country (confidence 0.95). For a French group it is the same service name once the ministry routing prefix `minarm`/`mindef` (and a title suffix that only repeats the ministry) is removed (0.90). For the named rules see the first rows.

| group key | rows | core | defence | judgement |
|---|---:|---:|---:|---|
| DE: rule:baainbw | 144 | 5,363 | 9,714 | yes. Every member name begins with `baainbw` or with the office's full name (Bundesamt fuer Ausruestung, Informationstechnik und Nutzung der Bundeswehr), including its typos, its desks (K2 4, G2 1, E3 6 ...), the Koblenz seat and the tender collection point. Nothing else in the Bundeswehr starts that way. |
| DE: rule:hil | 3 | 2,986 | 3,255 | yes. Heeresinstandsetzungslogistik GmbH with and without its abbreviation, plus one typo. A row that is only called `hil` is NOT in it (separate key, tested). |
| FR: dga do s2a | 7 | 2,212 | 2,255 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| FR: air siae | 3 | 1,341 | 1,873 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| ES: direccion de gestion economica de la jefatura de apoyo logistico de la | 2 | 986 | 3,217 | yes. Identical name, same country. |
| DE: rule:marinearsenal | 27 | 758 | 1,079 | yes. Every member name begins with `marinearsenal`: one authority, two sites (Wilhelmshaven, Rostock/Warnowwerft) and a sub-desk of the same authority. |
| PL: rule:inspektorat_uzbrojenia | 5 | 748 | 949 | yes. The predecessor of the Agencja, with and without the State Treasury prefix; one record carries the notice text about the rename. Kept as its own family, NOT merged with the Agencja (two names of one unit over time is not a spelling variant). |
| DE: rule:bwbm | 2 | 557 | 1,893 | yes. Two rows with the identical name `BW Bekleidungsmanagement` (BwBM). |
| BG: министерство на отбраната | 2 | 548 | 1,755 | yes. Identical name, same country. |
| ES: direccion de adquisiciones del mando de apoyo logistico del ejercito d | 2 | 541 | 1,230 | yes. Identical name, same country. |
| ES: intendente de cartagena | 2 | 487 | 1,560 | yes. Identical name, same country. |
| FR: terre simmt | 2 | 474 | 501 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| ES: intendente de rota | 2 | 373 | 1,902 | yes. Identical name, same country. |
| ES: intendente de las palmas | 2 | 373 | 1,003 | yes. Identical name, same country. |
| DE: bundesrepublik deutschland vertreten durch das bundesministerium des i | 2 | 366 | 520 | yes. Identical name, same country. |
| HU: vedelmi beszerzesi ugynokseg zartkoruen mukodo reszvenytarsasag | 4 | 350 | 896 | yes. Identical name, same country. |
| ES: intendente de ferrol | 2 | 289 | 1,790 | yes. Identical name, same country. |
| HU: honvedelmi miniszterium vedelemgazdasagi hivatal | 3 | 252 | 686 | yes. Identical name, same country. |
| ES: seccion de asuntos economicos de la direccion de infraestructura | 2 | 247 | 247 | yes. Identical name, same country. |
| BE: ministere de la defense | 22 | 243 | 934 | yes, with a caveat: a generic name, but a single ministry; no sub-unit in any of the names. |
| FR: arm sca pfaf-rbt | 3 | 231 | 762 | yes. Identical name, same country. |
| DE: bundesamt fur infrastruktur umweltschutz und dienstleistungen der bund | 43 | 213 | 3,749 | yes. Identical name, same country. |
| ES: jefatura de asuntos economicos del estado mayor de la defensa | 2 | 143 | 948 | yes. Identical name, same country. |
| GR: γενικο επιτελειο ναυτικου - κεντρο εφοδιασμου ναυτικου | 2 | 141 | 414 | yes. Identical name, same country. |
| ES: intendente de san fernando | 2 | 130 | 1,641 | yes. Identical name, same country. |
| FR: sca pfaf ouest | 4 | 113 | 641 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| ES: seccion de asuntos economicos del parque y centro de mantenimiento de  | 2 | 109 | 268 | yes. Identical name, same country. |
| GR: υπουργειο εθνικης αμυνας | 2 | 109 | 195 | yes. Identical name, same country. |
| PL: jednostka wojskowa nr 6021 | 2 | 105 | 2,176 | yes. Identical name, same country. |
| FR: sca pfaf so | 4 | 102 | 796 | yes. Identical name, same country. |
| PL: rejonowy zarzad infrastruktury w gdyni | 2 | 90 | 644 | yes. Identical name, same country. |
| DE: bundeswehr-dienstleistungszentrum munster | 5 | 89 | 509 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| IE: department of defence | 3 | 87 | 238 | yes. Identical name, same country. |
| FR: ema dcssa daps-ssa | 2 | 84 | 1,017 | yes. Identical name, same country. |
| DE: verpflegungsamt der bundeswehr | 10 | 83 | 652 | yes. Identical name, same country. |
| ES: direccion general del inta | 2 | 82 | 1,557 | yes. Identical name, same country. |
| PL: rejonowy zarzad infrastruktury w olsztynie | 2 | 81 | 296 | yes. Identical name, same country. |
| DE: bundesamt fur auswartige angelegenheiten | 2 | 81 | 170 | yes. Identical name, same country. |
| ES: direccion economico financiero de la direccion general de infraestruct | 2 | 80 | 139 | yes. Identical name, same country. |
| PL: komenda portu wojennego swinoujscie | 2 | 79 | 464 | yes. Identical name, same country. |
| IE: irish defence forces_1144 | 11 | 77 | 407 | yes. Identical name, same country. |
| PL: rejonowy zarzad infrastruktury w lublinie | 3 | 75 | 235 | yes. Identical name, same country. |
| FR: saelsi | 2 | 68 | 396 | yes. Identical name, same country. |
| PL: 31 baza lotnictwa taktycznego | 2 | 65 | 426 | yes. Identical name, same country. |
| FR: sga sdpamg | 2 | 60 | 115 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| PL: rule:agencja_uzbrojenia | 2 | 60 | 60 | yes. `Skarb Panstwa - Agencja Uzbrojenia` and `Agencja Uzbrojenia` (the second carries a removed e-mail after the name): the State Treasury prefix is the form the budget unit signs with. |
| DE: bundeswehr-dienstleistungszentrum zweibrucken | 4 | 59 | 164 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| FR: ema sca pfaf-idf | 3 | 53 | 729 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| PL: 32 baza lotnictwa taktycznego w lasku | 2 | 51 | 449 | yes. Identical name, same country. |
| PL: 1 baza lotnictwa transportowego | 2 | 51 | 368 | yes. Identical name, same country. |
| DE: bundeswehr-dienstleistungszentrum burg | 6 | 51 | 228 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum husum | 2 | 49 | 163 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum oldenburg | 6 | 49 | 146 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum bogen | 2 | 46 | 107 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum berlin | 3 | 42 | 196 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| PL: sluzba ochrony panstwa | 2 | 42 | 156 | yes. Identical name, same country. |
| IT: marinarsen | 3 | 41 | 41 | yes. Identical name, same country. |
| DE: bundeswehr-dienstleistungszentrum doberlug-kirchhain | 2 | 38 | 179 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum bruchsal | 6 | 36 | 109 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| PL: 17 wojskowy oddzial gospodarczy | 2 | 35 | 737 | yes. Identical name, same country. |
| DE: bundeswehr-dienstleistungszentrum rostock | 10 | 35 | 263 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| ES: jefatura de intendencia de asuntos economicos oeste | 2 | 34 | 1,445 | yes. Identical name, same country. |
| PL: 18 wojskowy oddzial gospodarczy | 2 | 34 | 770 | yes. Identical name, same country. |
| PL: 22 baza lotnictwa taktycznego | 2 | 34 | 335 | yes. Identical name, same country. |
| DE: bundeswehr-dienstleistungszentrum mayen | 3 | 33 | 85 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum landsberg am lech | 4 | 30 | 201 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum koln | 4 | 30 | 185 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum torgelow | 5 | 30 | 153 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| FR: sga dcsid sid atl | 2 | 30 | 30 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| PL: rejonowy zarzad infrastruktury w szczecinie | 2 | 29 | 219 | yes. Identical name, same country. |
| PL: 24 wojskowy oddzial gospodarczy | 2 | 28 | 1,645 | yes. Identical name, same country. |
| ES: division economica y tecnica cuerpo nacional de policia | 2 | 28 | 106 | yes. Identical name, same country. |
| PL: 33 baza lotnictwa transportowego | 2 | 27 | 219 | yes. Identical name, same country. |
| DE: bundeswehr-dienstleistungszentrum hannover | 6 | 27 | 129 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: staatliches bauamt weilheim | 2 | 27 | 27 | yes. Identical name, same country. |
| ES: jefatura de asuntos economicos de la guardia civil | 2 | 26 | 222 | yes. Identical name, same country. |
| DE: bundeswehr-dienstleistungszentrum koblenz | 3 | 26 | 103 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum idar-oberstein | 8 | 25 | 197 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum ingolstadt | 3 | 25 | 120 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| FR: sca pfc brest | 2 | 25 | 100 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| DE: bundeswehr-dienstleistungszentrum plon | 4 | 23 | 66 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum kiel | 4 | 22 | 208 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| PL: 23 baza lotnictwa taktycznego | 3 | 22 | 181 | yes. Identical name, same country. |
| FR: economat des armees | 3 | 21 | 958 | yes. Identical name, same country. |
| PL: 42 baza lotnictwa szkolnego w radomiu | 6 | 21 | 192 | yes. Identical name, same country. |
| DE: bundesrepublik deutschland vertreten durch d bundesministerium d verte | 2 | 21 | 41 | yes. Identical name, same country. |
| IT: direzione degli armamenti terrestri | 4 | 21 | 40 | yes. Identical name, same country. |
| DE: thuringer polizei landespolizeidirektion sachgebiet 24 | 2 | 20 | 54 | yes. Identical name, same country. |
| FR: ema sca pfc sud | 3 | 19 | 526 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| DE: bundeswehr-dienstleistungszentrum bonn | 5 | 19 | 162 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| FR: ema sca pfaf-ce bap | 2 | 18 | 488 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| DE: bundeswehr-dienstleistungszentrum wunstorf | 3 | 18 | 152 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum erfurt | 2 | 18 | 84 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum ulm | 3 | 18 | 83 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: zentraldienst der polizei des landes brandenburg | 4 | 17 | 68 | yes. Identical name, same country. |
| DE: land niedersachsen vertreten durch das staatliche baumanagement nieder | 2 | 17 | 23 | yes. Identical name, same country. |
| DE: bundeswehr-dienstleistungszentrum weissenfels | 3 | 16 | 114 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum kaufbeuren | 11 | 16 | 78 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| PL: rejonowy zarzad infrastruktury zielona gora | 2 | 16 | 74 | yes. Identical name, same country. |
| DE: bundeswehr-dienstleistungszentrum rotenburg | 8 | 16 | 66 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| IT: comando brigata paracadutisti folgore | 2 | 15 | 62 | yes. Identical name, same country. |
| DE: staatliches hochbauamt freiburg | 2 | 15 | 29 | yes. Identical name, same country. |
| FR: simmt sdo ddc | 2 | 14 | 14 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| DE: bundeswehr-dienstleistungszentrum aachen | 18 | 13 | 144 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum wilhelmshaven | 6 | 13 | 124 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum munchen | 3 | 12 | 184 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum augustdorf | 14 | 12 | 81 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: staatliches hochbauamt karlsruhe | 2 | 12 | 43 | yes. Identical name, same country. |
| ES: consejero delegado de ingenieria de sistemas para la defensa de espana | 2 | 11 | 3,054 | yes. Identical name, same country. |
| IT: ministero della difesa direzione generale di commissariato e di serviz | 3 | 11 | 64 | yes. Identical name, same country. |
| DE: polizei berlin | 2 | 11 | 32 | yes. Identical name, same country. |
| DE: staatliches bauamt schweinfurt | 2 | 11 | 11 | yes. Identical name, same country. |
| ES: intendencia de madrid | 2 | 10 | 1,201 | yes. Identical name, same country. |
| ES: direccion del servicio de gestion economica de la agencia estatal de l | 2 | 10 | 29 | yes. Identical name, same country. |
| PL: dowodztwo 1 brygady logistycznej | 2 | 10 | 10 | yes. Identical name, same country. |
| ES: jefatura de la seccion economico-administrativa 26 - base aerea de zar | 2 | 9 | 397 | yes. Identical name, same country. |
| PL: centralne biuro antykorupcyjne | 2 | 9 | 49 | yes. Identical name, same country. |
| DE: bundesamt fur infrastruktur umweltschutz und dienstleistungen der bund | 2 | 9 | 14 | yes. Identical name, same country. |
| FR: sdpamg | 2 | 9 | 10 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| ES: empresa nacional de residuos radiactivos s m e enresa | 2 | 9 | 9 | yes. Identical name, same country. |
| DE: bundeswehr-dienstleistungszentrum bergen | 3 | 8 | 142 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| DE: bundeswehr-dienstleistungszentrum homberg efze | 6 | 8 | 77 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| FR: ema sca pfc sud divap | 3 | 8 | 75 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| ES: subdireccion general de planificacion y gestion de infraestructuras y  | 2 | 8 | 52 | yes. Identical name, same country. |
| DE: kreisverwaltung mayen-koblenz | 2 | 8 | 8 | yes. Identical name, same country. |
| PL: amw sinevia | 3 | 8 | 8 | yes. Identical name, same country. |
| PL: rejonowy zarzad infrastruktury we wroclawiu | 2 | 7 | 78 | yes. Identical name, same country. |
| DE: polizeiinspektion zentrale dienste sachsen-anhalt | 3 | 7 | 24 | yes. Identical name, same country. |
| FR: dicom guyane | 2 | 6 | 152 | yes. Identical name, same country. |
| FR: cnd | 2 | 6 | 15 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| DE: staatliches hochbauamt heidelberg | 2 | 6 | 12 | yes. Identical name, same country. |
| DE: bundeswehr-dienstleistungszentrum stetten a k m | 2 | 6 | 11 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| FR: union des groupements d achats publics | 2 | 6 | 10 | yes. Identical name, same country. |
| PL: muzeum wojska polskiego | 2 | 6 | 6 | yes. Identical name, same country. |
| FR: ministere des affaires etrangeres | 2 | 5 | 17 | yes. Identical name, same country. |
| IT: ministero della difesa direzione di intendenza del comando brigata alp | 3 | 5 | 9 | yes. Identical name, same country. |
| FR: dicom antilles | 3 | 4 | 64 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| DE: landespolizeiprasidium saarland | 2 | 4 | 11 | yes. Identical name, same country. |
| DE: polizeiprasidium koln | 2 | 4 | 9 | yes. Identical name, same country. |
| FR: sga dcsid sid-atl | 2 | 4 | 4 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| ES: direccion general de trafico | 2 | 3 | 59 | yes. Identical name, same country. |
| DE: bundeswehr-dienstleistungszentrum bad reichenhall | 2 | 3 | 30 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| CH: armasuisse einkauf und kooperationen cc wto | 4 | 2 | 522 | yes. Identical name, same country. |
| ES: jefatura de intendencia de asuntos economicos de operaciones | 2 | 2 | 103 | yes. Identical name, same country. |
| IT: direzione del genio per la marina militare di augusta | 2 | 2 | 9 | yes. Identical name, same country. |
| DE: vergabe und beschaffungszentrum dortmund | 2 | 2 | 6 | yes. Identical name, same country. |
| DE: staatsbetrieb sachsische informatik dienste | 2 | 2 | 4 | yes. Identical name, same country. |
| DE: howoge wohnungsbaugesellschaft | 2 | 1 | 2 | yes. Identical name, same country. |
| PL: stoleczny zarzad infrastruktury | 2 | 0 | 145 | yes. Identical name, same country. |
| DE: bundesministerium der verteidigung | 2 | 0 | 123 | yes. Identical name, same country. |
| ES: direccion economico-financiera de enaire | 2 | 0 | 88 | yes. Identical name, same country. |
| PL: jednostka wojskowa nr 2286 | 2 | 0 | 79 | yes. Identical name, same country. |
| PL: osrodek reprezentacyjny ministerstwa obrony narodowej | 2 | 0 | 69 | yes. Identical name, same country. |
| ES: area de gobierno de vicealcaldia portavoz seguridad y emergencias del  | 2 | 0 | 43 | yes. Identical name, same country. |
| DE: bundeswehr-dienstleistungszentrum hammelburg | 2 | 0 | 36 | yes. The same town's service centre (the town is in the key; other towns stay apart). |
| ES: presidencia del consejo de administracion de la autoridad portuaria de | 2 | 0 | 35 | yes. Identical name, same country. |
| FR: sga | 2 | 0 | 34 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| FR: ema dcdirisi cnso | 2 | 0 | 26 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| DE: einkauf der stadt duisburg 10-31 | 2 | 0 | 20 | yes. Identical name, same country. |
| PL: izba administracji skarbowej w szczecinie | 2 | 0 | 19 | yes. Identical name, same country. |
| ES: junta de gobierno del ajuntament de valencia | 2 | 0 | 17 | yes. Identical name, same country. |
| PL: malopolski urzad wojewodzki w krakowie | 2 | 0 | 17 | yes. Identical name, same country. |
| DE: deutsche gesellschaft fur internationale zusammenarbeit giz | 2 | 0 | 16 | yes. Identical name, same country. |
| PL: izba administracji skarbowej w olsztynie | 2 | 0 | 15 | yes. Identical name, same country. |
| IT: ministero della difesa - direzione di intendenza - comando per la form | 7 | 0 | 14 | yes. Identical name, same country. |
| ES: junta de gobierno del ayuntamiento de fuengirola | 2 | 0 | 13 | yes. Identical name, same country. |
| ES: junta de gobierno del ayuntamiento de palma de mallorca | 2 | 0 | 13 | yes. Identical name, same country. |
| ES: junta de gobierno del ayuntamiento de sevilla | 2 | 0 | 13 | yes. Identical name, same country. |
| ES: junta de gobierno del ayuntamiento de torrevieja | 2 | 0 | 12 | yes. Identical name, same country. |
| ES: junta de gobierno del ayuntamiento de leganes | 2 | 0 | 11 | yes. Identical name, same country. |
| PL: 16 wojskowy oddzial gospodarczy drawsko pomorskie | 5 | 0 | 11 | yes. Identical name, same country. |
| PL: komenda stoleczna policji | 2 | 0 | 11 | yes. Identical name, same country. |
| HU: debreceni egyetem | 2 | 0 | 10 | yes. Identical name, same country. |
| ES: alcaldia del ayuntamiento de las palmas de gran canaria | 2 | 0 | 9 | yes. Identical name, same country. |
| ES: junta de gobierno del ayuntamiento de malaga | 2 | 0 | 9 | yes. Identical name, same country. |
| ES: organo de contratacion de la ciudad autonoma de ceuta | 2 | 0 | 9 | yes. Identical name, same country. |
| ES: servei catala de transit | 2 | 0 | 9 | yes. Identical name, same country. |
| FR: stat | 2 | 0 | 9 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| GR: πολεμικη αεροπορια δου α β λαρισας | 4 | 0 | 9 | yes. Identical name, same country. |
| ES: alcaldia del ayuntamiento de arrecife | 2 | 0 | 8 | yes. Identical name, same country. |
| ES: junta de gobierno del ayuntamiento de elche | 2 | 0 | 8 | yes. Identical name, same country. |
| ES: rectorado de la universidad de salamanca | 2 | 0 | 8 | yes. Identical name, same country. |
| ES: barcelona d infraestructures municipals | 2 | 0 | 7 | yes. Identical name, same country. |
| ES: junta de gobierno del ayuntamiento de cordoba | 2 | 0 | 7 | yes. Identical name, same country. |
| ES: subdireccion general de gestion economica y patrimonial | 2 | 0 | 7 | yes. Identical name, same country. |
| PL: gmina sobotka | 2 | 0 | 7 | yes. Identical name, same country. |
| PL: miasto leszno | 2 | 0 | 7 | yes. Identical name, same country. |
| PL: powiat wolominski | 2 | 0 | 7 | yes. Identical name, same country. |
| DE: global security-sector-reform foundation ggmbh | 2 | 0 | 6 | yes. Identical name, same country. |
| ES: alcaldia del ayuntamiento de ponferrada | 2 | 0 | 6 | yes. Identical name, same country. |
| PL: powiat nowodworski | 2 | 0 | 6 | yes. Identical name, same country. |
| DE: landkreis rotenburg wumme | 2 | 0 | 5 | yes. Identical name, same country. |
| DE: landkreis schaumburg - vergabestelle | 2 | 0 | 5 | yes. Identical name, same country. |
| ES: ajuntament de sant feliu de guixols | 2 | 0 | 5 | yes. Identical name, same country. |
| PL: gmina niepolomice | 2 | 0 | 5 | yes. Identical name, same country. |
| PL: komenda miejska panstwowej strazy pozarnej w krakowie | 2 | 0 | 5 | yes. Identical name, same country. |
| PL: kujawsko-pomorski urzad wojewodzki w bydgoszczy | 2 | 0 | 5 | yes. Identical name, same country. |
| ES: consejo de gobierno insular del cabildo insular de tenerife | 2 | 0 | 4 | yes. Identical name, same country. |
| ES: junta de gobierno del ayuntamiento de cox | 2 | 0 | 4 | yes. Identical name, same country. |
| ES: rectorado de la universidad de les illes balears | 2 | 0 | 4 | yes. Identical name, same country. |
| PL: gmina kolbuszowa | 2 | 0 | 4 | yes. Identical name, same country. |
| PL: gmina miasto ozorkow | 2 | 0 | 4 | yes. Identical name, same country. |
| CZ: ceska republika ministerstvo obrany | 2 | 0 | 3 | yes. Identical name, same country. |
| ES: consejo ejecutivo de la sociedad valenciana de gestion integral de ser | 2 | 0 | 3 | yes. Identical name, same country. |
| ES: junta de gobierno local del ayuntamiento de cartagena | 2 | 0 | 3 | yes. Identical name, same country. |
| FR: sga dcsid esid toulon service achats infrastructure | 2 | 0 | 3 | yes. Same service once the ministry prefix is removed; no division, site or production pole in any name. |
| PL: gmina biala rawska | 2 | 0 | 3 | yes. Identical name, same country. |
| PL: gmina miasto mragowo | 2 | 0 | 3 | yes. Identical name, same country. |
| PL: gmina miejska walcz | 2 | 0 | 3 | yes. Identical name, same country. |
| PL: powiat jedrzejowski | 2 | 0 | 3 | yes. Identical name, same country. |
| DE: hamburger energienetze | 2 | 0 | 2 | yes. Identical name, same country. |
| DE: landratsamt ortenaukreis | 2 | 0 | 2 | yes. Identical name, same country. |
| ES: junta de gobierno del ayuntamiento de leon | 2 | 0 | 2 | yes. Identical name, same country. |
| ES: junta de gobierno del ayuntamiento de murcia | 2 | 0 | 2 | yes. Identical name, same country. |
| ES: junta de gobierno del ayuntamiento de roquetas de mar | 2 | 0 | 2 | yes. Identical name, same country. |
| ES: servicio aragones de salud salud | 2 | 0 | 2 | yes. Identical name, same country. |
| ES: servicio de salud de las illes balears | 2 | 0 | 2 | yes. Identical name, same country. |

## Members of the named-rule and French groups

**DE:rule:baainbw**

- 196 (4688 core, 8382 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 28871 (163 core, 311 defence) `baainbw` [rule:baainbw]
- 242927 (97 core, 165 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr - s2 2` [rule:baainbw]
- 340978 (85 core, 158 defence) `baainbw` [rule:baainbw]
- 110611 (6 core, 79 defence) `baainbw g2 1` [rule:baainbw]
- 31896 (17 core, 36 defence) `bundesamt fur ausruestung informationstechnik und nutzung der bundeswehr baainbw` [rule:baainbw]
- 326493 (17 core, 33 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr baainbw` [rule:baainbw]
- 110646 (27 core, 29 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr -e1 3- angebotssammelstelle` [rule:baainbw]
- 97122 (4 core, 26 defence) `baainbw u2 4` [rule:baainbw]
- 343912 (19 core, 19 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 113186 (11 core, 17 defence) `baainbw-e3 6` [rule:baainbw]
- 118655 (0 core, 17 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr referat e2 4` [rule:baainbw]
- 57208 (0 core, 16 defence) `bundesamt fur ausrustung informationstechnik und ausrustung der bundeswehr referat e2 4` [rule:baainbw]
- 347528 (14 core, 14 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 350435 (14 core, 14 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 330029 (0 core, 12 defence) `baainbw` [rule:baainbw]
- 90934 (10 core, 11 defence) `baainbw koblenz` [rule:baainbw]
- 106835 (2 core, 10 defence) `baainbw e2 4` [rule:baainbw]
- 349034 (2 core, 10 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 77791 (9 core, 9 defence) `baainbw k2 4` [rule:baainbw]
- 185856 (0 core, 9 defence) `bundesamt fur ausrustung informatonstechnik und nutzung der bundeswehr` [rule:baainbw]
- 309625 (0 core, 9 defence) `baainbw g2 1` [rule:baainbw]
- 71161 (2 core, 8 defence) `bundesamt fur ausrustung informationstechnologie und nutzung der bundeswehr` [rule:baainbw]
- 88020 (6 core, 8 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr e3 6` [rule:baainbw]
- 102628 (0 core, 8 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr l2 1` [rule:baainbw]
- 111623 (5 core, 8 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundewehr` [rule:baainbw]
- 121202 (8 core, 8 defence) `baainbw l2 2` [rule:baainbw]
- 345268 (8 core, 8 defence) `baainbw` [rule:baainbw]
- 101837 (2 core, 7 defence) `bundesamt fur ausrustung infrastruktur und nutzung der bundeswehr` [rule:baainbw]
- 136601 (7 core, 7 defence) `baainbw k2 2` [rule:baainbw]
- 170732 (2 core, 7 defence) `bundesamt fur ausrustung informationsmanagement und nutzung der bundeswehr` [rule:baainbw]
- 328188 (1 core, 7 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr baainbw` [rule:baainbw]
- 39054 (5 core, 6 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr e1 3 angebotssammelstelle` [rule:baainbw]
- 102679 (2 core, 6 defence) `bundesamt fur ausrustung informationstechnik und nutzung des bundeswehr` [rule:baainbw]
- 327841 (0 core, 6 defence) `baainbw` [rule:baainbw]
- 353555 (4 core, 6 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 118256 (5 core, 5 defence) `bundesamt fur ausrustung und informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 174385 (3 core, 5 defence) `bundesamt fur ausrustung nutzung und informationstechnik der bundeswehr` [rule:baainbw]
- 340419 (5 core, 5 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 340789 (5 core, 5 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 340873 (5 core, 5 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 347708 (4 core, 5 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 347856 (0 core, 5 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 349150 (5 core, 5 defence) `baainbw` [rule:baainbw]
- 354966 (0 core, 5 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 38756 (0 core, 4 defence) `bundesamt fur ausrustung informationstechnik und nutzung referat e2 4` [rule:baainbw]
- 156205 (0 core, 4 defence) `baainbw i2 1` [rule:baainbw]
- 222676 (0 core, 4 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr - baainbw` [rule:baainbw]
- 236339 (4 core, 4 defence) `bundesamt fur ausrustung informationstechnik und beschaffung der bundeswehr` [rule:baainbw]
- 245466 (0 core, 4 defence) `bundesamt fur ausrustung informationstechni und nutzung der bundeswehr` [rule:baainbw]
- 261421 (2 core, 4 defence) `bundesamt fur ausrustung informationstechnkik und nutzung der bundeswehr` [rule:baainbw]
- 335761 (4 core, 4 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 341378 (4 core, 4 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 349429 (0 core, 4 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 352423 (4 core, 4 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 353174 (0 core, 4 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 112226 (3 core, 3 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bw` [rule:baainbw]
- 117382 (0 core, 3 defence) `bundesamt fur ausrustung informationstechnik und ausrustung der bundeswehr` [rule:baainbw]
- 205039 (0 core, 3 defence) `baainbw i2 4` [rule:baainbw]
- 333935 (0 core, 3 defence) `baainbw` [rule:baainbw]
- 344711 (3 core, 3 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 345706 (3 core, 3 defence) `baainbw` [rule:baainbw]
- 349803 (0 core, 3 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 351492 (3 core, 3 defence) `bundesamt fur ausrustung informationstechnik und nutzung` [rule:baainbw]
- 46442 (0 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr -h1 6-` [rule:baainbw]
- 62710 (1 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr h1 6 -` [rule:baainbw]
- 110895 (2 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr u2 sanmat` [rule:baainbw]
- 122727 (2 core, 2 defence) `baainbw k 2 2` [rule:baainbw]
- 126798 (2 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr-e22l` [rule:baainbw]
- 139151 (0 core, 2 defence) `baainbw l2 1` [rule:baainbw]
- 141613 (2 core, 2 defence) `baainbw s2 4 im hause marinearsenal af 911` [rule:baainbw]
- 171037 (2 core, 2 defence) `baainbw l2 3` [rule:baainbw]
- 176420 (2 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr -e 2 2-` [rule:baainbw]
- 181288 (0 core, 2 defence) `bundesamt fur ausrustung infrastuktur und nutzung der bundeswehr` [rule:baainbw]
- 186670 (0 core, 2 defence) `baainbw e3 6` [rule:baainbw]
- 194671 (2 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr referat l2 6` [rule:baainbw]
- 236991 (2 core, 2 defence) `bundesamt fur ausrustung informationstechnick und nutzung der bundeswehr` [rule:baainbw]
- 287469 (0 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr baainbw` [rule:baainbw]
- 308217 (0 core, 2 defence) `baainbw g2 1` [rule:baainbw]
- 329195 (0 core, 2 defence) `baainbw` [rule:baainbw]
- 332987 (0 core, 2 defence) `baainbw g2 1` [rule:baainbw]
- 340341 (2 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 340381 (0 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 340478 (0 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 340524 (2 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 340625 (2 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr -e1 3- angebotssammelstelle` [rule:baainbw]
- 341629 (2 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 341698 (2 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 342265 (2 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr baainbw` [rule:baainbw]
- 345193 (0 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 345298 (0 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 347436 (0 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 348686 (1 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 350273 (0 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 352189 (2 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 353451 (0 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 353466 (0 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 353485 (0 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 354167 (0 core, 2 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 43804 (0 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr h1 6` [rule:baainbw]
- 46059 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr e1 angebotssammelstelle` [rule:baainbw]
- 77430 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr referat s2 1` [rule:baainbw]
- 78380 (0 core, 1 defence) `baainbw u2 1h` [rule:baainbw]
- 98424 (0 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bw baainbw` [rule:baainbw]
- 114387 (0 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr - k2 4` [rule:baainbw]
- 123744 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr-e1 3- angebotssammelstelle` [rule:baainbw]
- 139293 (0 core, 1 defence) `bundesamt fur ausrustung inforamtionstechnik und nutzung der bundeswehr baainbw` [rule:baainbw]
- 139756 (0 core, 1 defence) `baainbw-u2 2` [rule:baainbw]
- 149735 (0 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehrt` [rule:baainbw]
- 150483 (1 core, 1 defence) `bundesamt fur ausrustung infomationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 160148 (1 core, 1 defence) `bundesamt fur ausrustung nutzung und informatonstechnik der bw` [rule:baainbw]
- 162200 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr i2 2` [rule:baainbw]
- 179905 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr -i2 2` [rule:baainbw]
- 184429 (1 core, 1 defence) `baainbw k2 2l` [rule:baainbw]
- 192920 (1 core, 1 defence) `baainbw l2 4` [rule:baainbw]
- 201408 (1 core, 1 defence) `bundesamt fur ausrustung informastionstechnik und nutzung der bundeswehr` [rule:baainbw]
- 291581 (0 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr baainbw` [rule:baainbw]
- 291582 (0 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr baainbw` [rule:baainbw]
- 340370 (0 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 340421 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 340422 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 340790 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 341152 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 341376 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 341739 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 343789 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 344327 (0 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 347385 (0 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 348575 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 348896 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 349705 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 350186 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 352639 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 353465 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 353467 (0 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 353675 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 354473 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 354499 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 354563 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 355103 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 355143 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 355144 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 355504 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]
- 355786 (1 core, 1 defence) `bundesamt fur ausrustung informationstechnik und nutzung der bundeswehr` [rule:baainbw]

**DE:rule:hil**

- 200 (2963 core, 3232 defence) `hil heeresinstandsetzungslogistik` [rule:hil]
- 138847 (14 core, 14 defence) `heeresinstandsetzungslogistik` [rule:hil]
- 215183 (9 core, 9 defence) `hil heeresinstandsetzungslogistk` [rule:hil]

**FR:dga do s2a**

- 78917 (1406 core, 1441 defence) `minarm dga do s2a` [fr_ministry]
- 61158 (472 core, 474 defence) `dga do s2a` [identical_name]
- 32406 (308 core, 311 defence) `mindef dga do s2a` [fr_ministry]
- 189241 (25 core, 25 defence) `minarm dga do s2a ministere des armees - direction generale de l armement - direction des operations - service` [fr_ministry]
- 318165 (0 core, 2 defence) `minarm dga do s2a` [fr_ministry]
- 165558 (1 core, 1 defence) `minarm dga do s2a ministere des armees direction generale de l armement direction des operations service des a` [fr_ministry]
- 318884 (0 core, 1 defence) `minarm dga do s2a` [fr_ministry]

**FR:air siae**

- 34117 (893 core, 911 defence) `mindef air siae` [fr_ministry]
- 196441 (186 core, 699 defence) `minarm air siae` [fr_ministry]
- 202 (262 core, 263 defence) `minarm air siae ministere des armees` [fr_ministry]

**DE:rule:marinearsenal**

- 30945 (194 core, 340 defence) `marinearsenal` [rule:marinearsenal]
- 129583 (113 core, 145 defence) `marinearsenal wilhelmshaven` [rule:marinearsenal]
- 365 (141 core, 141 defence) `marinearsenal warnowwerft` [rule:marinearsenal]
- 226337 (99 core, 99 defence) `marinearsenal dienstort rostock` [rule:marinearsenal]
- 307774 (42 core, 90 defence) `marinearsenal` [rule:marinearsenal]
- 226974 (53 core, 53 defence) `marinearsenal dienstort wilhelmshaven` [rule:marinearsenal]
- 235441 (19 core, 47 defence) `marinearsenal do wilhelmshaven` [rule:marinearsenal]
- 306087 (11 core, 31 defence) `marinearsenal wilhelmshaven` [rule:marinearsenal]
- 153764 (29 core, 30 defence) `marinearsenal wilhelmshaven sachgebiet firmen` [rule:marinearsenal]
- 307627 (9 core, 30 defence) `marinearsenal wilhelmshaven` [rule:marinearsenal]
- 325482 (3 core, 15 defence) `marinearsenal` [rule:marinearsenal]
- 349336 (11 core, 11 defence) `marinearsenal dienstort wilhelmshaven` [rule:marinearsenal]
- 351883 (10 core, 10 defence) `marinearsenal dienstort rostock` [rule:marinearsenal]
- 333599 (0 core, 7 defence) `marinearsenal` [rule:marinearsenal]
- 236689 (6 core, 6 defence) `marinearsenal wilhelmshaven do wilhelmshaven` [rule:marinearsenal]
- 341054 (5 core, 5 defence) `marinearsenal wilhelmshaven` [rule:marinearsenal]
- 331684 (4 core, 4 defence) `marinearsenal wilhelmshaven sachgebiet soft ins` [rule:marinearsenal]
- 165445 (3 core, 3 defence) `marinearsenal wilhelmshaven sachgebiet soft ins` [rule:marinearsenal]
- 191535 (0 core, 2 defence) `marinearsenal wilhelmshaven sachgebiet werften` [rule:marinearsenal]
- 327398 (2 core, 2 defence) `marinearsenal` [rule:marinearsenal]
- 333694 (0 core, 2 defence) `marinearsenal wilhelmshaven` [rule:marinearsenal]
- 146669 (0 core, 1 defence) `marinearsenal wilhelmshaven frasmaschinen` [rule:marinearsenal]
- 146670 (0 core, 1 defence) `marinearsenal wilhelmshaven drehmaschinen` [rule:marinearsenal]
- 341217 (1 core, 1 defence) `marinearsenal wilhelmshaven` [rule:marinearsenal]
- 341914 (1 core, 1 defence) `marinearsenal` [rule:marinearsenal]
- 341935 (1 core, 1 defence) `marinearsenal` [rule:marinearsenal]
- 342495 (1 core, 1 defence) `marinearsenal wilhelmshaven` [rule:marinearsenal]

**PL:rule:inspektorat_uzbrojenia**

- 31637 (699 core, 831 defence) `inspektorat uzbrojenia` [rule:inspektorat_uzbrojenia]
- 38459 (32 core, 79 defence) `skarb panstwa inspektorat uzbrojenia` [rule:inspektorat_uzbrojenia]
- 88660 (15 core, 35 defence) `skarb panstwa - inspektorat uzbrojenia` [rule:inspektorat_uzbrojenia]
- 49227 (0 core, 2 defence) `skarb panstwa-inspektorat uzbrojenia` [rule:inspektorat_uzbrojenia]
- 183399 (2 core, 2 defence) `skarb panstwa - inspektorat uzbrojenia - w zwiazku z zarzadzeniem nr 74 mon ministra obrony narodowej z dnia 1` [rule:inspektorat_uzbrojenia]

**DE:rule:bwbm**

- 67975 (547 core, 1850 defence) `bw bekleidungsmanagement` [rule:bwbm]
- 305787 (10 core, 43 defence) `bw bekleidungsmanagement` [rule:bwbm]

**FR:terre simmt**

- 75459 (360 core, 385 defence) `minarm terre simmt` [fr_ministry]
- 44162 (114 core, 116 defence) `mindef terre simmt` [fr_ministry]

**FR:sca pfaf ouest**

- 34368 (113 core, 631 defence) `mindef sca pfaf ouest` [fr_ministry]
- 318717 (0 core, 8 defence) `mindef sca pfaf ouest` [fr_ministry]
- 299900 (0 core, 1 defence) `mindef sca pfaf ouest` [fr_ministry]
- 314522 (0 core, 1 defence) `mindef sca pfaf ouest` [fr_ministry]

**FR:sga sdpamg**

- 220839 (54 core, 89 defence) `minarm sga sdpamg` [fr_ministry]
- 250344 (6 core, 26 defence) `sga sdpamg` [identical_name]

**PL:rule:agencja_uzbrojenia**

- 185739 (58 core, 58 defence) `skarb panstwa - agencja uzbrojenia` [rule:agencja_uzbrojenia]
- 332501 (2 core, 2 defence) `agencja uzbrojenia email removed` [rule:agencja_uzbrojenia]

**FR:ema sca pfaf-idf**

- 34664 (53 core, 706 defence) `mindef ema sca pfaf-idf` [fr_ministry]
- 288885 (0 core, 20 defence) `mindef ema sca pfaf-idf` [fr_ministry]
- 313642 (0 core, 3 defence) `mindef ema sca pfaf-idf` [fr_ministry]

**FR:sga dcsid sid atl**

- 243945 (28 core, 28 defence) `minarm sga dcsid sid atl ministere des armees secretariat general pour l administration direction centrale du` [fr_ministry]
- 249573 (2 core, 2 defence) `minarm sga dcsid sid atl ministere des armees secretariat general pour l administration direction centrale du` [fr_ministry]

**FR:sca pfc brest**

- 220256 (23 core, 78 defence) `minarm sca pfc brest` [fr_ministry]
- 223833 (2 core, 22 defence) `mindef sca pfc brest` [fr_ministry]

**FR:ema sca pfc sud**

- 171986 (16 core, 482 defence) `mindef ema sca pfc sud` [fr_ministry]
- 220545 (3 core, 41 defence) `minarm ema sca pfc sud` [fr_ministry]
- 310763 (0 core, 3 defence) `minarm ema sca pfc sud` [fr_ministry]

**FR:ema sca pfaf-ce bap**

- 71994 (8 core, 444 defence) `minarm ema sca pfaf-ce bap` [fr_ministry]
- 40846 (10 core, 44 defence) `mindef ema sca pfaf-ce bap` [fr_ministry]

**FR:simmt sdo ddc**

- 227327 (12 core, 12 defence) `simmt sdo ddc` [identical_name]
- 225896 (2 core, 2 defence) `minarm simmt sdo ddc` [fr_ministry]

**FR:sdpamg**

- 220155 (9 core, 9 defence) `sdpamg` [identical_name]
- 221071 (0 core, 1 defence) `minarm sdpamg` [fr_ministry]

**FR:ema sca pfc sud divap**

- 219054 (8 core, 57 defence) `minarm ema sca pfc sud divap` [fr_ministry]
- 311689 (0 core, 17 defence) `minarm ema sca pfc sud divap` [fr_ministry]
- 310561 (0 core, 1 defence) `minarm ema sca pfc sud divap` [fr_ministry]

**FR:cnd**

- 28599 (4 core, 13 defence) `cnd` [identical_name]
- 317345 (2 core, 2 defence) `minarm cnd` [fr_ministry]

**FR:dicom antilles**

- 248180 (2 core, 50 defence) `minarm dicom antilles` [fr_ministry]
- 247767 (2 core, 10 defence) `dicom antilles` [identical_name]
- 324993 (0 core, 4 defence) `minarm dicom antilles` [fr_ministry]

**FR:sga dcsid sid-atl**

- 242583 (2 core, 2 defence) `minarm sga dcsid sid-atl ministere des armees secretariat general pour l administration direction centrale du` [fr_ministry]
- 242701 (2 core, 2 defence) `minarm sga dcsid sid-atl ministere des armees secretariat general pour l administration direction centrale du` [fr_ministry]

**FR:sga**

- 38216 (0 core, 29 defence) `mindef sga` [fr_ministry]
- 320894 (0 core, 5 defence) `mindef sga` [fr_ministry]

**FR:ema dcdirisi cnso**

- 35196 (0 core, 25 defence) `mindef ema dcdirisi cnso` [fr_ministry]
- 313083 (0 core, 1 defence) `mindef ema dcdirisi cnso` [fr_ministry]

**FR:stat**

- 242813 (0 core, 6 defence) `minarm stat` [fr_ministry]
- 330945 (0 core, 3 defence) `minarm stat` [fr_ministry]

**FR:sga dcsid esid toulon service achats infrastructure**

- 220710 (0 core, 2 defence) `mindef sga dcsid esid toulon service achats infrastructure` [fr_ministry]
- 331798 (0 core, 1 defence) `minarm sga dcsid esid toulon service achats infrastructure` [fr_ministry]

## Stays apart (checked on the data)

- The Bundeswehr-Dienstleistungszentren: one family per town only (the same town written twice is one office). No two towns share a key.
- `mindef dga dt scat toulon` / `toulouse` / `cazaux` / `val de reuil` (DT SCAT sites of the DGA) are not under `dga do s2a`; `mindef air siae aia ...` (aeronautical industrial workshops) are not under `air siae`; a `minarm dga do s2a ... division achats-sud-est site d istres` name is left whole (it names a division and a site).
- Staatliche Bauaemter and Hochbauaemter: only identical names group.
- Polish military units (`jednostka wojskowa nr N`, `N wojskowy oddzial gospodarczy`, `N baza lotnictwa ...`): only the same number groups.
- UK MoD commercial teams: no group (no rule, and no identical names in the data).
- Related but not grouped, left to the owner: `inspektorat uzbrojenia` with `agencja uzbrojenia` (a rename), `lh bundeswehr bekleidungsgesellschaft` with `bw bekleidungsmanagement`.

