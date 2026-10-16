# Confidence levels: labelled sample (WP-23, 16 October 2026)

Read-only against production. Sample drawn in SQL with `setseed(0.23)` and `row_number() OVER (PARTITION BY source ORDER BY random())`,
so each cell is stratified by source in proportion to its size; seed and queries are repeatable only while the data does not change.
The population is the default list (`scope=relevant`, every status, 304,958 stored notices, collapse rules not applied). Judged from title, buyer,
buyer class, CPV and the stored signals only; one judge (the implementer), no second reader. Titles are shown as the site shows them.

## Labels

| Label | Meaning |
|---|---|
| Y | the notice itself is defence or security-for-the-forces procurement: a defence item, military repair, uniform or equipment, military construction (CPV 45216200 or a military site named) |
| G | a defence body (or a notice under the directive from one) buying something generic: food, cleaning, IT, fuel, ordinary construction |
| B | borderline: police, prison, border, customs or tax body buying weapons or protective kit; research with defence use; or undecidable from the title |
| N | not defence: hospital, utility, municipal, road, embassy, university, ordinary works |

**Strict precision** = Y. **Lenient precision** = Y + G (the notice is defence procurement itself, or a defence body buying; the definition of round 2,
`docs/verification/round2/data-correctness.md` part B, so the figures are comparable). "Plus B" adds borderline. Intervals are Wilson 95 %.
For a level made of several cells the point estimate is weighted by cell size and the interval is a Wilson interval on the effective sample size
(`p(1-p)/variance` of the stratified estimate); the unweighted counts are shown beside it.

## Result per level

| Level | Cells | Notices on the list | Sample | Y | G | B | N | Strict (weighted, 95 %) | Lenient (weighted, 95 %) | Lenient plus borderline | Not defence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| high | A, B | 30,648 (10 %) | 64 | 61 | 2 | 1 | 0 | 96 % (88 % to 98 %) | 99 % (92 % to 100 %) | 100 % | 0 % (0 % to 6 %) |
| medium | C, D, En | 253,259 (83 %) | 111 | 26 | 78 | 7 | 0 | 11 % (6 % to 19 %) | 93 % (85 % to 97 %) | 100 % | 0 % (0 % to 3 %) |
| low | Es, F, G, H, J, K | 21,051 (7 %) | 188 | 24 | 15 | 83 | 66 | 14 % (9 % to 19 %) | 21 % (16 % to 27 %) | 66 % | 34 % (28 % to 40 %) |

Unweighted for `high`: 61 of 64 Y = 95 % strict (Wilson 87 % to 98 %); 63 of 64 lenient = 98 % (Wilson 92 % to 100 %). The bar (at least 90 % lenient on at least 60 notices) is met: the lower bound is above 90 %.

## Result per cell (the unit the rule table is built from)

| Cell | Signals | Notices | Sample | Y | G | B | N | Strict (Wilson) | Lenient (Wilson) | Level |
|---|---|---|---|---|---|---|---|---|---|---|
| A | directive + military code + listed buyer | 16,661 | 32 | 32 | 0 | 0 | 0 | 100 % (89 % to 100 %) | 100 % (89 % to 100 %) | high |
| B | military code + listed buyer (no directive) | 13,987 | 32 | 29 | 2 | 1 | 0 | 91 % (76 % to 97 %) | 97 % (84 % to 99 %) | high |
| C | directive + listed buyer (no military code) | 28,304 | 32 | 9 | 22 | 1 | 0 | 28 % (16 % to 45 %) | 97 % (84 % to 99 %) | medium |
| D | listed buyer only | 224,413 | 66 | 6 | 55 | 5 | 0 | 9 % (4 % to 18 %) | 92 % (83 % to 97 %) | medium |
| En | directive + military code, buyer class defence/other/unknown, not listed | 542 | 13 | 11 | 1 | 1 | 0 | 85 % (58 % to 96 %) | 92 % (67 % to 99 %) | medium |
| Es | directive + military code, buyer a security or civil body | 680 | 13 | 1 | 1 | 11 | 0 | 8 % (1 % to 33 %) | 15 % (4 % to 42 %) | low |
| F | military code only (not demoted, not a security body) | 4,653 | 36 | 13 | 6 | 12 | 5 | 36 % (22 % to 52 %) | 53 % (37 % to 68 %) | low |
| G | military code only, security body (group security_buyer_cpv) | 5,278 | 35 | 1 | 0 | 31 | 3 | 3 % (1 % to 15 %) | 3 % (1 % to 15 %) | low |
| H | directive only, civil buyer (group directive_civil_buyer) | 7,132 | 51 | 6 | 4 | 9 | 32 | 12 % (6 % to 23 %) | 20 % (11 % to 32 %) | low |
| J | directive only, defence/security class or linked | 3,042 | 31 | 1 | 2 | 14 | 14 | 3 % (1 % to 16 %) | 10 % (3 % to 25 %) | low |
| K | link to a defence notice only | 266 | 22 | 2 | 2 | 6 | 12 | 9 % (3 % to 28 %) | 18 % (7 % to 39 %) | low |

Cells En and Es split the notices with the directive and a military code but no listed buyer by the buyer's class (defence, other or unknown against everything else); n = 13 each, so read them as indicative.

## Limits

- One judge, reading titles, buyers and codes only; no second reader, so the labels carry judgement (G against B and Y against G in particular).
- A cell with 13 notices (En, Es) or 22 (K) gives a wide interval; the level of those cells rests on the pattern of the neighbouring cells as well.
- The sample is of stored notices of every status. Collapse rules (a national notice hidden behind its TED twin) are not applied, so the shares are of rows, not of what one list page shows.
- Medium is dominated by cell D (224,413 of 253,259 notices): its figures are the figures of D. The level says the buyer is a defence body, not that the item is defence goods.

## Sample by source

| Level | de_bkms | es_placsp | es_placsp_agg | fr_boamp | nl_tenderned | pl_atlas | pl_ezam | ted |
|---|---|---|---|---|---|---|---|---|
| high | 4 | 9 | 0 | 3 | 2 | 2 | 1 | 43 |
| medium | 5 | 9 | 0 | 7 | 2 | 10 | 7 | 71 |
| low | 22 | 9 | 3 | 7 | 5 | 4 | 17 | 121 |

## The labelled notices

Columns: id (`/v1/tenders/<id>`), source, country, buyer, first CPV, title, label, reason.

### Level high, cell A: directive + military code + listed buyer

| id | src | cc | buyer | CPV | title | label | reason |
|---|---|---|---|---|---|---|---|
| 271062 | de_bkms | DE | Marinearsenal | 50640000 | Instandsetzung der BUSTER 05 bis 08 der F125 Nordrhein-Westfalen | Y | warship repair |
| 280739 | de_bkms | DE | HIL Heeresinstandsetzungslogistik GmbH | 50600000 | BG_1440_EU/24 - Werksinstandsetzung von Betätigerbaugruppe des Systems TPz 1 Fuchs | Y | armoured vehicle overhaul |
| 290667 | de_bkms | DE | Bundesamt für Ausrüstung, Informationste | 35420000 | 6002922685-BAAINBw E2.5F Dieselmotoren, WS Leopard 2 | Y | tank engines |
| 273304 | es_placsp | ES | Jefatura de Asuntos Económicos del Mando | 50840000 | Mantenimiento de la Estación de    Armas RCWS | Y | weapon-station maintenance |
| 141927 | fr_boamp | FR | Marine/DCSSF/DSSF Toulon | 35520000 | fourniture de groupes surpresseurs pneumatiques mobiles pour oxygène et mélanges de gaz respira | Y | breathing-gas equipment for naval divers/submarines |
| 203491 | fr_boamp | FR | PFC RBT | 35812200 | FABRICATION D’ENSEMBLES INTEMPERIES | Y | military clothing |
| 146870 | nl_tenderned | NL | Ministerie van Defensie | 35000000 | Spare Parts Spike LR2 | Y | missile spare parts |
| 40103 | ted | PL | 4 Regionalna Baza Logistyczna | 35340000 | Poland-Wrocław: Parts of firearms and ammunition | Y | firearm parts and ammunition |
| 40785 | ted | BE | MRMP-N/A — Direction générale Material R | 34510000 | Belgium-Evere: Repair and maintenance services of warships | Y | warship repair |
| 46467 | ted | FR | DGA/DO/S2A | 35332000 | France-Paris: Ammunition for naval warfare | Y | naval ammunition |
| 53002 | ted | FI | Puolustusvoimien Logistiikkalaitos | 35410000 | Finland-Tampere: Armoured military vehicles | Y | armoured vehicles |
| 55670 | ted | FR | ARM/SCA/PFAF — RBT | 35812200 | France-Rambouillet: Combat suits | Y | combat clothing |
| 62693 | ted | GB | Ministry of Defence, Land Equipment, Sol | 31642200 | United Kingdom-Bristol: Bomb-disposal services | Y | bomb disposal service |
| 68897 | ted | DE | Bundesamt für Ausrüstung, Informationste | 35420000 | Germany-Coblenz: Parts of military vehicles | Y | military vehicle parts |
| 69441 | ted | BG | Министерство на отбраната | 35813000 | Bulgaria-Sofia: Military helmets | Y | military helmets |
| 84491 | ted | NL | Ministerie van Defensie | 35710000 | Netherlands-The Hague: Command, control, communication and computer systems | Y | military C4 systems |
| 87101 | ted | BG | Министерство на отбраната | 50640000 | Bulgaria-Sofia: Repair and maintenance services of warships | Y | warship repair |
| 87518 | ted | DE | HIL Heeresinstandsetzungslogistik GmbH | 50630000 | Germany-Bonn: Repair and maintenance services of military vehicles | Y | military vehicle repair |
| 88751 | ted | DE | HIL Heeresinstandsetzungslogistik GmbH | 50000000 | Germany-Bonn: Repair and maintenance services of security and defence materials | Y | defence materiel repair |
| 92191 | ted | CZ | Česká republika - Ministerstvo obrany | 50660000 | Czechia-Prague: Repair and maintenance services of military electronic systems | Y | military electronics repair |
| 94941 | ted | RO | Ministerul Apararii - Unitatea Militara  | 03000000 | Romania-București: Cartridges | Y | cartridges |
| 100274 | ted | DE | Bundesamt für Ausrüstung, Informationste | 35300000 | Germany – Weapons, ammunition and associated parts – Patronen 20mm x 139 Übung | Y | 20 mm training ammunition |
| 107661 | ted | HU | Védelmi Beszerzési Ügynökség Zrt. | 50840000 | Hungary – Repair and maintenance services of weapons and weapon systems – Lokátor- és rakétatec | Y | radar and missile equipment repair |
| 111084 | ted | DE | Marinearsenal Dienstort Rostock | 50000000 | Germany – Repair and maintenance services – Planmäßige Instandsetzung (Zwischeninstandsetzung)  | Y | corvette overhaul |
| 111154 | ted | PL | Skarb Państwa - Jednostka Wojskowa Nr 23 | 35400000 | Poland – Military vehicles and associated parts – Dostawa Pojazdów operacyjnych WS grupy A i B  | Y | military vehicles |
| 119973 | ted | DE | Bundesamt für Ausrüstung, Informationste | 35330000 | Germany – Ammunition – Patrone 12,7 mm x 99 geg 4HK-1HKLS (AF88) | Y | 12.7 mm ammunition |
| 124952 | ted | RO | MINISTERUL APARARII - UNITATEA MILITARA  | 45216200 | Romania – Construction work for military buildings and installations – LUCRĂRI DE INTERVENȚIE L | Y | military building works |
| 126522 | ted | PL | 2. Regionalna Baza Logistyczna | 50630000 | Poland – Repair and maintenance services of military vehicles – W/95/2025 Usługę weryfikacji i  | Y | military vehicle repair |
| 130962 | ted | DE | Bundesamt für Ausrüstung, Informationste | 50660000 | Germany – Repair and maintenance services of military electronic systems – RV für die Technisch | Y | military electronics repair |
| 132758 | ted | DE | HIL Heeresinstandsetzungslogistik GmbH | 50600000 | Germany – Repair and maintenance services of security and defence materials – BG_1662_EU/26 - W | Y | vehicle overhaul |
| 137947 | ted | PL | 1 REGIONALNA BAZA LOGISTYCZNA | 35300000 | Poland – Weapons, ammunition and associated parts – Dostawa technicznych środków materiałowych, | Y | weapon and ammunition supplies |
| 138937 | ted | DE | HIL Heeresinstandsetzungslogistik GmbH | 50630000 | Germany – Repair and maintenance services of military vehicles – SYS_599/25 - Werksinstandhaltu | Y | military vehicle maintenance |

### Level high, cell B: military code + listed buyer (no directive)

| id | src | cc | buyer | CPV | title | label | reason |
|---|---|---|---|---|---|---|---|
| 291111 | de_bkms | DE | Bundesamt für Ausrüstung, Informationste | 80650000 | Qualitative Evaluation auf dem Hubschrauber AW 169 | Y | helicopter evaluation by the armaments office |
| 235702 | es_placsp | ES | Intendente de San Fernando | 35521100 | Lote 2: Repuestos propulsión LCM - Expediente Padre: 2024/AR43U/00001311 (LOTE 2: 2024/AR43U/00 | Y | landing-craft propulsion spares |
| 247660 | es_placsp | ES | Intendente de Rota | 50640000 | CB. 5º AM. Mantenimiento integral de alternadores y cuadros eléctricos principales en buques de | Y | warship generators |
| 251364 | es_placsp | ES | Intendente de Cartagena | 50640000 | OTACV(TA 26) .- CB- 1er Contrato Basado derivado del Acuerdo Marco para el servicio de apoyo al | Y | maintenance of naval vessels |
| 301235 | es_placsp | ES | Jefatura de Asuntos Económicos del Mando | 50840000 | Mantenimiento y formación del sistema de blancos automáticos SAAB (LOTE 2) | Y | automatic target systems |
| 302311 | es_placsp | ES | Jefatura de Intendencia de Asuntos Econó | 45216200 | AS INVIED 202300000100 OBRA TC-204-10/22 construccion vial hormigonado y obstáculos quita lodos | Y | military base works (CPV 45216200) |
| 303836 | es_placsp | ES | Dirección de Gestión Económica de la Jef | 35331400 | Suministro de minas contra carro C-5 | Y | anti-tank mines |
| 315423 | es_placsp | ES | Intendente de Cartagena | 35500000 | JEMAN.- R. ARMAS.- Contrato de suministro de materiales para mantenimientos en buques del Arsen | Y | ship maintenance materials |
| 318469 | es_placsp | ES | Dirección de Gestión Económica de la Jef | 50840000 | 8º Contrato de Servicios Basado, En el AM 1602/21 y prórroga 1206/24 para el Apoyo Técnico al S | Y | weapon-system support |
| 188107 | fr_boamp | FR | Sous-direction de la préfiguration de l' | 75220000 | Observatoire n°2024-05 intitulé Observatoire Boutros-Ghali du maintien de la paix (OBG) | B | peacekeeping study; defence-related but not goods or services for forces |
| 146726 | nl_tenderned | NL | Ministerie van Defensie | 35722000 | Radars at the Netherlands part of the North Sea | Y | radar (defence ministry, 357 code) |
| 325 | pl_atlas | PL | 2. Regionalna Baza Logistyczna | 35420000 | Dostawa części zamiennych do pojazdów wojskowych trał przeciwminowy Bożena | Y | mine-clearing vehicle parts |
| 1258 | pl_atlas | PL | Skarb Państwa - Jednostka Wojskowa Nr 23 | 35814000 | Dostawa masek przeciwgazowych i filtropochłaniaczy z podziałem na 2 części | Y | gas masks and filters |
| 246406 | pl_ezam | PL | Akademia Wojsk Lądowych | 35613000 | DOSTAWA, MONTAŻ, WDROŻENIE 3 SZT. SYSTEMU BEZZAŁOGOWEGO STATKU POWIETRZNEGO (BSP) WRAZ Z INFRAS | Y | UAV system for army academy |
| 38597 | ted | GR | Ανώτατη Στρατιωτική Διοίκηση Υποστήριξης | 35420000 | Greece-Aθήνα: Parts of military vehicles | Y | military vehicle parts |
| 43114 | ted | PL | 2 Regionalna Baza Logistyczna | 18332000 | Poland-Warsaw: Combat uniforms | Y | combat uniforms |
| 56528 | ted | ES | Jefatura del Apoyo Logístico | 35700000 | Spain-Madrid: Military electronic systems | Y | military electronic systems |
| 58966 | ted | GB | Ministry of Defence, Weapons, Torpedoes, | 35620000 | United Kingdom-Bristol: Missiles | Y | missiles |
| 68489 | ted | DE | Bw Bekleidungsmanagement GmbH | 18100000 | Germany-Cologne: Occupational clothing, special workwear and accessories | G | workwear from the Bundeswehr clothing company |
| 69553 | ted | ES | Jefatura de Asuntos Económicos del Mando | 18222000 | Spain-Madrid: Military uniforms | Y | military uniforms |
| 72557 | ted | ES | Sección de Asuntos Económicos del Parque | 35420000 | Spain-Torrejón de Ardoz: Parts of military vehicles | Y | military vehicle parts |
| 77687 | ted | LT | Gynybos resursų agentūra prie Krašto aps | 35813100 | Lithuania-Vilnius: Helmet covers | Y | helmet covers |
| 99181 | ted | IT | COMANDO AVIAZIONE DELL'ESERCITO - DIREZI | 18832100 | Italy-Viterbo: Military uniforms | Y | military uniforms |
| 116452 | ted | IE | Irish Defence Forces_1144 | 50241000 | Ireland – Repair and maintenance services of ships – A11 Contracted Services for the Maintenanc | Y | naval vessel maintenance |
| 123482 | ted | ES | Dirección de Gestión Económica de la Jef | 35522000 | Spain – Electronic and electrical spare parts for warships – Suministro de repuestos para el si | Y | warship electronic spares |
| 130821 | ted | NO | Norwegian Defence Materiel Agency | 35613000 | Norway – Unmanned aerial vehicles – Request for Information - Fiber Cables and Reels for UAV | Y | UAV fibre cables |
| 184822 | ted | IE | Irish Defence Forces_1144 | 45000000 | Ireland-Newbridge: Construction work | G | generic construction for the defence forces |
| 203707 | ted | EE | Riigi Kaitseinvesteeringute Keskus | 50640000 | Estonia-Tallinn: Repair and maintenance services of warships | Y | warship repair |
| 216322 | ted | ES | Intendente de las Palmas | 50640000 | Spain – Repair and maintenance services of warships – Varada reglamentaria del Buque de Acción  | Y | patrol-ship dry-dock repair |
| 237001 | ted | ES | Intendente de Cartagena | 50640000 | Spain – Repair and maintenance services of warships – JEMAN (T.A. 2024).-YSABEL.- Contrato de s | Y | patrol vessel services |
| 239218 | ted | RO | MINISTERUL APARARII - UNITATEA MILITARA  | 45216200 | Romania – Construction work for military buildings and installations – „Platforme, adăposturi u | Y | military shelters |
| 267311 | ted | PL | 41 Baza Lotnictwa Szkolnego | 50112000 | Poland – Repair and maintenance services of cars – Wykonywanie usług: obsług okresowych i napra | Y | servicing of military cars |

### Level medium, cell C: directive + listed buyer (no military code)

| id | src | cc | buyer | CPV | title | label | reason |
|---|---|---|---|---|---|---|---|
| 288235 | de_bkms | DE | Bw Bekleidungsmanagement GmbH | 18310000 | Unterwäsche, Mehrschicht, lang, Herren und Damen, KBS-SK, Rahmenvereinbarungen | G | underwear for soldiers, but ordinary clothing |
| 293162 | de_bkms | DE | Bundesamt für Ausrüstung, Informationste | 32351000 | D-LBO MiB - Wirbelsäulenstecker | Y | connector for a military digitisation programme |
| 305156 | es_placsp | ES | Dirección de Adquisiciones del Mando de  | 71300000 | 202362A5 Acuerdo Marco para la cura de obsolescencias de aviónica del sistema de armas AE.9 | Y | weapon-system avionics |
| 141416 | fr_boamp | FR | MINDEF/DGA/DO/S2A | 33735100 | " Contrôle et fourniture de protections oculaires de sécurité laser " | G | laser eye protection, generic safety item |
| 142158 | fr_boamp | FR | MINDEF/AIR/SIAé | 42921300 | Fourniture de conteneurs d'entreposage et de transport (terre, rail, air, mer) pour les pales r | G | transport containers, generic |
| 143659 | fr_boamp | FR | MINDEF/AIR/SIAé | 42123610 | Maintenance de la production et de la distribution d'air de l'AIA Cuers-Pierrefeu et de son ant | G | air plant of a maintenance workshop |
| 175239 | fr_boamp | FR | MINARM/DMAé | 50212000 | Maintien en condition opérationnelle des hélicoptères H145-D3 de la direction générale de la sé | B | civil-security helicopters |
| 196089 | fr_boamp | FR | MINARM/SGA/DCSID/SID ATL (Ministère des  | 71356100 | 8215-8789 - Accord-cadre à bons de commande de contrôle technique courant pour les sites souten | G | technical inspection of sites |
| 146995 | nl_tenderned | NL | Ministerie van Defensie | 42124000 | Aankoop service kits compressoren | G | compressor kits |
| 43740 | ted | DE | HIL Heeresinstandsetzungslogistik GmbH | 50000000 | Germany-Bonn: Repair and maintenance services of security and defence materials | Y | defence materiel repair |
| 47101 | ted | CZ | Česká republika - Ministerstvo obrany | 18114000 | Czech Republic-Prague: Coveralls | G | coveralls |
| 55356 | ted | GR | Υπουργείο Εθνικής Άμυνας - Γενική Διεύθυ | 34741300 | Greece-Papagoy: Deck-arresting gear | Y | deck arresting gear |
| 58624 | ted | DE | HIL Heeresinstandsetzungslogistik GmbH | 50000000 | Germany-Bonn: Repair and maintenance services of security and defence materials | Y | defence materiel repair |
| 59853 | ted | CZ | Česká republika - Ministerstvo obrany | 50600000 | Czechia-Prague: Repair and maintenance services of security and defence materials | Y | defence materiel repair |
| 69093 | ted | GB | Ministry of Defence, Land Equipment, Spe | 50100000 | United Kingdom-Bristol: Repair, maintenance and associated services of vehicles and related equ | G | vehicle repair, generic |
| 73900 | ted | FR | Minarm/terre/simmt | 38632000 | France-Versailles: Nightglasses | Y | night-vision equipment |
| 79824 | ted | RO | Ministerul Apararii Nationale - Unitatea | 34731000 | Romania-Otopeni: Parts for aircraft | Y | aircraft parts |
| 80176 | ted | DE | Bundesamt für Ausrüstung, Informationste | 35110000 | Germany-Coblenz: Firefighting, rescue and safety equipment | G | fire-fighting equipment, generic |
| 86901 | ted | DE | BWI GmbH | 72411000 | Germany-Bonn: Internet service providers ISP | G | internet access |
| 89342 | ted | FR | arm/sca/pfaf-rbt | 19620000 | France-Rambouillet: Textile waste | G | textile waste |
| 89368 | ted | NO | FORSVARSMATERIELL [the Norwegian Defence | 34965000 | Norway-Oslo: Telescopic sights | Y | telescopic sights |
| 95436 | ted | PL | Skarb Państwa - 1 Regionalna Baza Logist | 35100000 | Poland-Wałcz: Emergency and security equipment | G | emergency/security equipment, generic |
| 95657 | ted | IT | Ministero della Difesa - Segretariato Ge | 34000000 | Italy-Rome: Transport equipment and auxiliary products to transportation | G | generic transport equipment |
| 100012 | ted | CZ | Česká republika - Ministerstvo obrany | 50100000 | Czechia-Prague: Repair, maintenance and associated services of vehicles and related equipment | G | vehicle repair, generic |
| 104470 | ted | CZ | Ministerstvo obrany | 32570000 | Czechia – Communications equipment – Výzva č. 23221000379 - LANPCS | G | network equipment |
| 104829 | ted | CZ | Ministerstvo obrany ČR | 71000000 | Czechia – Architectural, construction, engineering and inspection services – ZPRACOVÁNÍ PROJEKT | G | design documentation |
| 116719 | ted | FR | ESID Metz | 45260000 | France – Roof works and other special trade construction works – Accord-cadre de petits travaux | G | roof works |
| 123675 | ted | CZ | Ministerstvo obrany | 35111000 | Czechia – Firefighting equipment – Vybavení zásahových vozidel VHJ-TZ | G | fire-vehicle equipment |
| 128738 | ted | ES | Jefatura de Asuntos Económicos del Mando | 48000000 | Spain – Software package and information systems – Renovacion de software embebido en equipos f | G | embedded software renewal, not stated military |
| 130231 | ted | FR | SID EPN | 45213351 | France – Maintenance hangar construction work – Réalisation d'infrastructures d'entretien et de | G | hangar construction, generic |
| 133886 | ted | NO | Forsvarsbygg | 72268000 | Norway – Software supply services – The Norwegian Defence Estates Agency invites tenderers to a | G | software supply |
| 135661 | ted | IT | Ministero della Difesa - Direzione Gener | 45000000 | Italy – Construction work – Avviso pubblico di avvenuta costituzione di un elenco di operatori  | G | construction list |

### Level medium, cell D: listed buyer only

| id | src | cc | buyer | CPV | title | label | reason |
|---|---|---|---|---|---|---|---|
| 289127 | de_bkms | DE | BWI GmbH | 79610000 | 1601-JR-Jobbörsen | G | job boards (IT company of the forces) |
| 293917 | de_bkms | DE | Bundesamt für Infrastruktur, Umweltschut | 42000000 | 3D-Koordinatenmessmaschine | G | measuring machine, generic |
| 251627 | es_placsp | ES | Dirección de Adquisiciones del Mando de  | 50200000 | 20235314 Mantenimiento de componentes de aviones UD.13 y UD.14. | Y | aircraft component maintenance, military air arm |
| 268458 | es_placsp | ES | Intendente de Rota | 33696300 | Expediente 2026/AR46U/00001333E Cuarto CB AM 2024/AR46U/00001466E L2 Suministro de material fun | G | consumables |
| 280038 | es_placsp | ES | Jefatura de la Sección Económico Adminis | 32441000 | Adquisición de sistema de captura de datos embarcable y cableado para el sistema de telemetría | G | telemetry data capture, not stated military |
| 306734 | es_placsp | ES | Sección de Asuntos Económicos del Parque | 24452000 | Adquisición insecticidas y repelentes para perros del E.T. usos veterinarios OMP,s | G | insecticide for army dogs |
| 313399 | es_placsp | ES | Intendente de San Fernando | 71317200 | Derivado de Acuerdo Marco de Servicio de coordinación de actividades empresariales y coordinaci | G | safety coordination service |
| 313677 | es_placsp | ES | Jefatura de Intendencia de Asuntos Econó | 31680000 | AM material fungible lote 3. Material eléctrico | G | electrical material |
| 315831 | es_placsp | ES | Intendente de Ferrol | 45223600 | CM-5098-P-24. TERNOR. Construcción modulo para perreras en el Tercio Norte - Edificacion de la  | G | kennel building |
| 316067 | es_placsp | ES | Dirección de Gestión Económica de la Jef | 45311200 | 6 CBAM 1645/22 LOTE 1 (2266/22) para la instalación de puntos de carga para vehículos eléctrico | G | charging points |
| 184225 | fr_boamp | FR | MINARM/SCA/PFC Paris | 90520000 | Collecte et traitement des déchets dangereux et location de contenants au profit des entités so | G | hazardous waste collection |
| 147012 | nl_tenderned | NL | Ministerie van Defensie | 45000000 | Verbouwing OBC Filter te Den Helder | G | building conversion |
| 3797 | pl_atlas | PL | 16 Wojskowy Oddział Gospodarczy | 98310000 | Usługa prania i czyszczenia na sucho | G | laundry service |
| 4373 | pl_atlas | PL | 15 Wojskowy Oddział Gospodarczy |  | WYKONANIE ROBÓT REMONTOWYCH NA TERENIE KOMPLEKSÓW WOJSKOWYCH W SZCZECINIE | G | repair works on barracks |
| 8246 | pl_atlas | PL | Centrum Zasobów Cyberprzestrzeni Sił Zbr | 72000000 | Usługa subskrypcji i wsparcia technicznego Producenta dla oprogramowania IBM Control Desk oraz  | G | software subscription |
| 14624 | pl_atlas | PL | 2 Wojskowy Oddział Gospodarczy | 15000000 | Dostawa żywności w roku 2025: mięso czerwone i tłuszcze zwierzęce, wędliny z mięsa czerwonego,  | G | food |
| 19290 | pl_atlas | PL | Jednostka Wojskowa Nr 6021 | 15981000 | Dostawa napojów bezalkoholowych dla Jednostki Wojskowej Nr 6021. | G | soft drinks |
| 22370 | pl_atlas | PL | Akademia Sztuki Wojennej | 50324100 | Wykonywanie (półrocznych, rocznych) konserwacji, przeglądów technicznych wraz z ewentualnymi bi | G | equipment servicing |
| 27805 | pl_atlas | PL | 22. Wojskowy Oddział Gospodarczy w Olszt | 71221000 | Wykonanie dokumentacji projektowo-kosztorysowych | G | design documentation |
| 35657 | pl_atlas | PL | 33 Wojskowy Oddział Gospodarczy w Nowej  | 90500000 | Odbiór, transport i utylizacja ubocznych produktów pochodzenia zwierzęcego kat. 3 oraz odpadów  | G | animal by-products disposal |
| 35662 | pl_atlas | PL | Ministerstwo Obrony Narodowej | 18512200 | 10/ZP/25 Dostawa medali resortowych i znaków specjalnych – III CZĘŚCI | G | medals and badges |
| 36335 | pl_atlas | PL | Służba Wywiadu Wojskowego | 18939000 | Zakup i dostawa przedmiotów umundurowania i wyekwipowania | Y | uniforms and equipment of the military intelligence service |
| 220875 | pl_ezam | PL | 15 WOJSKOWY ODDZIAŁ GOSPODARCZY | 45000000 | Remont sanitariatów w budynku nr 2 przy ul. Łukasińskiego 33 w Szczecinie | G | sanitary repairs |
| 233387 | pl_ezam | PL | 25. Wojskowy Oddział Gospodarczy w Biały | 30191000 | "Dostawa sprzętu i artykułów biurowych dla 25. Wojskowego Oddziału Gospodarczego i jednostek bę | G | office supplies |
| 233402 | pl_ezam | PL | 16 WOJSKOWY ODDZIAŁ GOSPODARCZY W DRAWSK | 50532300 | Konserwacja wraz z zapewnieniem sprawności w okresie między przeglądami stacjonarnymi agregatów | G | generator maintenance |
| 233560 | pl_ezam | PL | 3 Regionalna Baza Logistyczna | 18223200 | Polska – Kurtki – Dostawa w 2026 roku przedmiotów umundurowania i wyekwipowania – kurta zimowa  | Y | uniform jackets |
| 237880 | pl_ezam | PL | Centrum Zasobów Cyberprzestrzeni Sił Zbr | 80531200 | Polska – Usługi szkolenia technicznego – Usługa szkolenia dla potrzeb bezpieczeństwa teleinform | G | ICT security training |
| 244779 | pl_ezam | PL | 4 WOJSKOWY ODDZIAŁ GOSPODARCZY | 55520000 | 4WOG.1200.2712.93.2025 Świadczenie usługi restauracyjnej w formie przygotowania i dostarczenia  | G | catering |
| 296221 | pl_ezam | PL | 41. Baza Lotnictwa Szkolnego | 34300000 | Dostawa akcesoriów do wojskowych pojazdów mechanicznych. | Y | accessories for military motor vehicles |
| 53919 | ted | NL | Ministerie van Defensie | 34144213 | Netherlands-The Hague: Security, fire-fighting, police and defence equipment | G | fire engines, generic |
| 54828 | ted | PL | 3 Regionalna Baza Logistyczna | 39100000 | Poland-Krakow: Furniture | G | furniture |
| 73863 | ted | PL | Wojskowa Akademia Techniczna im. Jarosła | 31600000 | Poland-Warsaw: Electronic, electromechanical and electrotechnical supplies | G | electrical supplies |
| 84374 | ted | ES | Jefatura de Intendencia de Asuntos Econó | 55300000 | Spain-Valladolid: Restaurant and food-serving services | G | restaurant service |
| 100797 | ted | PL | 3 Regionalna Baza Logistyczna | 43800000 | Poland-Krakow: Workshop equipment | G | workshop equipment |
| 126785 | ted | NL | Ministerie van Defensie | 18412000 | Netherlands – Sportswear – Raamovereenkomst Bikerkleding | G | cycling clothing |
| 139087 | ted | DE | Bundesamt für Ausrüstung, Informationste | 48900000 | Germany – Miscellaneous software package and computer systems – Auswertesoftware TrackEye | B | analysis software, military use not stated |
| 151141 | ted | IT | MINISTERO DELLA DIFESA | 71200000 | Italy – Architectural and related services – GENIODIFE - CE 022619 - AUGUSTA - BASE NAVALE - PF | Y | design for a naval base |
| 153545 | ted | IT | Aeronautica Militare — 2° Reparto Genio  | 71322000 | Italy-Ciampino: Engineering design services for the construction of civil engineering works | G | civil engineering design |
| 156661 | ted | NO | Forsvaret | 38000000 | Norway-Lillehammer: Technical testing, analysis and consultancy services | B | testing and consultancy, not stated |
| 157333 | ted | DE | BWI GmbH | 72000000 | Germany-Munich: IT services: consulting, software development, Internet and support | G | IT consulting |
| 161138 | ted | GR | Γενικό Επιτελείο Αεροπορίας - Υπηρεσία Έ | 45216121 | Greece-Cholargos Attikis: Fire station construction work | G | fire-station construction |
| 161843 | ted | IT | Aeronautica militare — 2° reparto Genio  | 43312400 | Italy-Ciampino: Road rollers | G | road rollers |
| 163118 | ted | RO | Ministerul Apărării – Unitatea Militară  | 38433100 | Romania-Bucharest: Mass spectrometer | G | laboratory instrument |
| 170655 | ted | GR | ΓΕΝΙΚΟ ΕΠΙΤΕΛΕΙΟ ΝΑΥΤΙΚΟΥ ΚΕΝΤΡΟ ΕΦΟΔΙΑΣ | 44321000 | Greece-Athens: Cable | G | cable |
| 170671 | ted | FR | MINDEF/Sga/Spac/S-Direction des achats | 90721600 | France-Paris: Radiation protection services | G | radiation protection service |
| 171183 | ted | FI | Puolustusvoimien logistiikkalaitos | 32562000 | Finland-Tampere: Optical-fibre cables | G | fibre-optic cable |
| 175365 | ted | DE | BWI GmbH | 72000000 | Germany-Munich: IT services: consulting, software development, Internet and support | G | IT consulting |
| 187714 | ted | FR | minarm/ema/sca/pfaf-ce/bap | 37400000 | France-Lyon: Sports goods and equipment | G | sports goods |
| 188379 | ted | LV | Valsts aizsardzības loģistikas un iepirk | 09100000 | Latvia – Fuels – Dinamiskās iepirkumu sistēmas izveide centralizētai degvielas iegādes nodrošin | G | fuel purchasing system |
| 192499 | ted | NL | Ministerie van Defensie, Defensie Materi | 48000000 | Netherlands-Utrecht: Software package and information systems | G | software |
| 201147 | ted | RO | Ministerul Apărării — Unitatea Militară  | 64212000 | Romania-Bucharest: Mobile-telephone services | G | mobile telephony |
| 210740 | ted | ES | Junta de Contratación del Ejército de Ti | 15897100 | Spain-Madrid: Field rations | G | field rations |
| 216967 | ted | CZ | Vojenská lázeňská a rekreační zařízení,  | 71200000 | Czechia – Architectural and related services – VLRZ – VZ Špičák - výstavba nové kapacity pro PR | B | spa facility of the forces, design |
| 220626 | ted | EE | Riigi Kaitseinvesteeringute Keskus | 72300000 | Estonia – Data services – Infosüsteemi loomine ja täiendava teabeallika integreerimine | B | information system, not stated |
| 226435 | ted | DE | BWI GmbH | 79620000 | Germany – Supply services of personnel including temporary staff – 2000249393 ANÜ Senior Projec | G | temporary staff |
| 228445 | ted | FR | Economat des armées | 33000000 | France – Medical equipments, pharmaceuticals and personal care products – EQUIPEMENTS, DISPOSIT | G | medical equipment |
| 230856 | ted | BG | Министерство на отбраната | 18300000 | Bulgaria – Garments – Доставка на термобельо и фланелки по обособени позиции | G | thermal underwear |
| 236300 | ted | RO | MINISTERUL APARARII - UNITATEA MILITARA  | 15000000 | Romania – Food, beverages, tobacco and related products – FURNIZARE PRODUSE AGROALIMENTARE | G | food |
| 238509 | ted | FI | Puolustusvoimat | 60140000 | Finland – Non-scheduled passenger transport – Tilausajopalvelut 2021–2026, MAASK EVK Hamina-Vir | G | charter coach service |
| 239116 | ted | DE | HIL Heeresinstandsetzungslogistik GmbH | 79200000 | Germany – Accounting, auditing and fiscal services – Steuerberatung | G | tax advisory service |
| 241543 | ted | LV | Nodrošinājuma valsts aģentūra | 03413000 | Latvia – Fuel wood – Kurināmā (sagatavotas malkas, brikešu, kokskaidu granulu, ogļu, sašķidrinā | B | fuel wood for a state supply agency |
| 253236 | ted | PL | Rejonowy Zarząd Infrastruktury w Bydgosz | 45000000 | Poland – Construction work – Wykonanie robót budowlanych dla zadania pn.: „Budowa strażnicy woj | Y | military guardhouse construction |
| 261709 | ted | PL | Skarb Państwa – 1 Regionalna Baza Logist | 15900000 | Poland-Wałcz: Beverages, tobacco and related products | G | beverages |
| 262232 | ted | ES | Intendente de San Fernando | 44113300 | Spain-San Fernando: Coated materials | G | materials |
| 265870 | ted | PL | 17 Wojskowy Oddział Gospodarczy w Koszal | 39221000 | Poland-Koszalin: Kitchen equipment | G | kitchen equipment |
| 265990 | ted | DE | Bundeswehr-Dienstleistungszentrum Bad Re | 90911200 | Germany-Bad Reichenhall: Building-cleaning services | G | cleaning service |

### Level medium, cell En: directive + military code, buyer class defence/other/unknown, not listed

| id | src | cc | buyer | CPV | title | label | reason |
|---|---|---|---|---|---|---|---|
| 288795 | de_bkms | DE | Bundesrepublik Deutschland vertreten dur | 45000000 | Truppenübungsplatz Bergen (NATO), Ausbau SB 11 mit SPA 2, Tiefbauarbeiten | Y | military training area earthworks |
| 140862 | fr_boamp | FR | SSFA ANTILLES/GUYANE | 50640000 | Marchés à bons de commandes multi spécialités sur les bâtiments de la Marine Nationale en Marti | Y | naval vessel maintenance |
| 42084 | ted | PL | Skarb Państwa – Inspektorat Uzbrojenia | 35513000 | Poland-Warsaw: Mine warfare and auxiliary ships | Y | mine-warfare ships |
| 53102 | ted | DE | Bundesrepublik Deutschland, vertreten du | 45216200 | Germany-Schwäbisch Hall: Construction work for military buildings and installations | Y | military building works |
| 58440 | ted | LT | LR Ginklų fondas prie LR VRM | 35331300 | Lithuania-Vilnius: Grenades | Y | grenades for the weapons fund |
| 60409 | ted | PL | Skarb Państwa - Inspektorat Uzbrojenia | 35331500 | Poland-Warsaw: Cartridges | Y | cartridges |
| 61599 | ted | ES | Jefatura de Apoyo Logístico | 35520000 | Spain-Madrid: Parts for warships | Y | warship parts |
| 63042 | ted | NO | The Norwegian Defence Estates Agency | 45112100 | Norway-Oslo: Construction work for military buildings and installations | Y | military building works |
| 76075 | ted | GB | Babcock Land Defence Limited | 50630000 | United Kingdom-Telford: Repair and maintenance services of military vehicles | Y | military vehicle repair |
| 76888 | ted | PL | Skarb Państwa - Inspektorat Uzbrojenia | 35620000 | Poland-Warsaw: Missiles | Y | missiles |
| 102524 | ted | BG | ЦАТИП В.Ф. 26940 | 35300000 | Bulgaria-Stara Zagora: Weapons, ammunition and associated parts | Y | weapons and ammunition for a military unit |
| 124638 | ted | DE | Landesbetrieb Bau- und Liegenschaftsmana | 45431000 | Germany – Tiling work – Fliesen- und Plattenarbeiten - Baumaßnahme der Bundeswehr, Übungsplatz  | G | tiling, generic |
| 137290 | ted | RO | Direcția Generală de Protecție Internă | 35711000 | Romania – Command, control, communication systems – Platformă de comunicații operative securiza | B | secure communications for an internal-protection directorate |

### Level low, cell Es: directive + military code, buyer a security or civil body

| id | src | cc | buyer | CPV | title | label | reason |
|---|---|---|---|---|---|---|---|
| 200 | es_placsp | ES | Jefatura de Asuntos Económicos de la Gua | 50334400 | Contratación de un servicio de mantenimiento integral para los despliegues fijos del Sistema In | B | police-type fixed deployments |
| 43522 | ted | BE | Police fédérale service procurement | 35300000 | Belgium-Brussels: Weapons, ammunition and associated parts | B | police weapons |
| 50970 | ted | HR | Ministarstvo unutarnjih poslova | 35815000 | Croatia-Zagreb: Garments for anti-ballistic protection | B | police protective clothing |
| 54850 | ted | HR | Ministarstvo unutarnjih poslova | 35613000 | Croatia-Zagreb: Unmanned aerial vehicles | B | police drones |
| 65470 | ted | CY | Cyprus Police | 80330000 | Cyprus-Nicosia: Training and simulation in security equipment | B | police training |
| 67273 | ted | EE | Politsei- ja Piirivalveamet | 35330000 | Estonia-Tallinn: Ammunition | B | police ammunition |
| 69346 | ted | RO | Inspectoratul General al Poliției de Fro | 35321100 | Romania-Bucharest: Hand guns | B | police handguns |
| 75396 | ted | RO | Inspectoratul General al Poliției de Fro | 35321100 | Romania-Bucharest: Hand guns | B | police handguns |
| 100384 | ted | HR | MINISTARSTVO UNUTARNJIH POSLOVA | 35330000 | Croatia-Zagreb: Ammunition | B | police ammunition |
| 116605 | ted | HR | MINISTARSTVO UNUTARNJIH POSLOVA | 35815100 | Croatia – Bullet-proof vests – Balistička oprema (najam 7 godina) | B | police body armour |
| 120855 | ted | DE | Bundesrepublik Deutschland, vertreten du | 35331500 | Germany – Cartridges – 57MM TARGET PRACTICE (TP) | Y | 57 mm training cartridges |
| 124573 | ted | PL | 17. Terenowy Oddział Lotniskowy | 45000000 | Poland – Construction work – Robota budowlana dla zadania 54113 | G | construction at an airfield, generic |
| 128525 | ted | BG | Дирекция Управление на собствеността и с | 35320000 | Bulgaria – Firearms – Доставка на оръжейни системи за нуждите на ДСОБТ | B | weapons for a security directorate |

### Level low, cell F: military code only (not demoted, not a security body)

| id | src | cc | buyer | CPV | title | label | reason |
|---|---|---|---|---|---|---|---|
| 270908 | de_bkms | DE | Bundesrepublik Deutschland vertreten dur | 45216200 | 23B60196 - Bundesliegenschaft in Wittmund | B | federal property works with only the CPV code as evidence |
| 285384 | de_bkms | DE | Fraunhofer-Gesellschaft zur Förderung de | 35512400 | Modulare, ferngesteuerte Unterwasser-Multisensorenplattform | B | research platform, dual-use |
| 286997 | de_bkms | DE | Bundesrepublik Deutschland, vertreten du | 35331500 | Patrone 9mm x 19 Frangible | B | frangible pistol cartridges, police or forces |
| 289852 | de_bkms | DE | Freie und Hansestadt Hamburg, Bundesbaua | 45216200 | Trockenbauarbeiten | B | drywall, CPV only evidence |
| 290962 | de_bkms | DE | Bundesrepublik Deutschland vertreten dur | 45216200 | 25B30506 - Bundesliegenschaft in Wittmund; Neubau; Blitzschutzanlage | B | lightning protection, CPV only evidence |
| 290993 | de_bkms | DE | Stadt Wuppertal | 34144210 | Rahmenvereinbarung die Neubeschaffung von max. zwei Fahrgestellen und die Auf- und Ausbauten zu | N | fire-brigade vehicle |
| 294363 | de_bkms | DE | Stadt Ahaus | 35000000 | 4 Mannschaftstransportfahrzeuge mit erweiterter IuK-Ausstattung und Beladung für die Feuerwehr  | N | fire-brigade vehicles |
| 250504 | es_placsp | ES | Sección de Asuntos Económicos de la Coma | 45216200 | AM TC 203-47/24 Demolición y Reposición pérgola terraza y reparación suelo Polvorín Renegado Us | G | repairs at an ammunition depot |
| 302850 | es_placsp | ES | Sección de Asuntos Económicos de la Dire | 45216200 | Adecuación de seis salas de calderas conforme al rite para certificación de eficiencia energéti | G | boiler rooms in military buildings |
| 311147 | es_placsp | ES | Dirección del Servicio de Gestión Económ | 35300000 | Suministro de munición para formación del personal de Vigilancia Aduanera del Departamento de A | B | training ammunition for customs |
| 319779 | es_placsp | ES | División Económica y Técnica (Cuerpo Nac | 35740000 | Adquisición de 20 sistemas ópticos de Tiro para la DPG. | B | optical shooting systems for police |
| 290475 | es_placsp_agg | ES | Agencia de Innovación y Desarrollo de An | 39100000 | Suministro de equipos industriales para dotación del centro CFA en Cádiz | N | equipment for a regional training centre |
| 166198 | fr_boamp | FR | ICADE PROMOTION | 45200000 | Construction d'un bâtiment neuf à usage de réserve pour les grands formats métalliques du Musée | N | museum building |
| 146821 | nl_tenderned | NL | Ministerie van Buitenlandse Zaken | 34144000 | BZ EA - gepantserde voertuigen (2025) | B | armoured vehicles for embassies |
| 730 | pl_atlas | PL | Wojskowy Ośrodek Szkoleniowo-Kondycyjny  | 18400000 | Dostawa odzieży sportowej i sprzętu sportowego | G | sportswear for a military centre |
| 298779 | pl_ezam | PL | Akademia Wymiaru Sprawiedliwości | 35331000 | Dostawa amunicji | B | ammunition for a justice academy |
| 41130 | ted | DE | Präsidium für Technik, Logistik und Verw | 35300000 | Germany-Wiesbaden: Weapons, ammunition and associated parts | B | weapons and ammunition, police logistics |
| 101432 | ted | SK | Finančné riaditeľstvo Slovenskej republi | 35331000 | Slovakia – Ammunition for firearms and warfare – Strelivo pre potreby FR SR, KÚ FS a CÚ | B | ammunition for tax and customs |
| 112566 | ted | GR | ΔΙΟΙΚΗΣΗ ΥΠΟΣΤΗΡΙΞΗΣ ΒΑΣΗΣ (ΔΥΒ) | 35421100 | Greece – Engines and engine parts for military vehicles – 16/24 ΑΔ | Y | engines for military vehicles |
| 156566 | ted | IT | Marinarsen | 50640000 | Italy-La Spezia: Repair and maintenance services of warships | Y | warship repair |
| 168691 | ted | DK | Forsvarsministeriets Ejendomsstyrelse | 45000000 | Denmark-Hjørring: Construction work | G | construction by defence estates |
| 171165 | ted | DE | Staatliches Hochbauamt Schwäbisch Hall | 45216200 | Germany-Schwäbisch Hall: Construction work for military buildings and installations | Y | military building works |
| 186323 | ted | DE | Staatliches Hochbauamt Schwäbisch Hall | 45216200 | Germany-Schwäbisch Hall: Construction work for military buildings and installations | Y | military building works |
| 189247 | ted | LT | Infrastruktūros valdymo agentūra | 45216200 | Lithuania – Construction work for military buildings and installations – SPECIALIOSIOS PASKIRTI | Y | special-purpose military buildings |
| 191936 | ted | SE | Regeringskansliet | 71311200 | Sweden-Stockholm: Provision of services to the community | N | government office services |
| 193693 | ted | DE | Staatliches Bauamt Kempten | 45216200 | Germany-Kempten (Allgäu): Construction work for military buildings and installations | Y | military building works |
| 195869 | ted | DE | Staatliches Bauamt Kempten | 45112000 | Germany-Kempten (Allgäu): Excavating and earthmoving work | B | earthworks, CPV only evidence |
| 196512 | ted | DE | Staatliches Bauamt Kempten | 45216200 | Germany-Kempten (Allgäu): Construction work for military buildings and installations | Y | military building works |
| 200955 | ted | DE | Staatliches Bauamt Kempten | 45216200 | Germany-Kempten (Allgäu): Construction work for military buildings and installations | Y | military building works |
| 207062 | ted | DE | Staatliches Bauamt Kempten | 45216200 | Germany-Kempten (Allgäu): Construction work for military buildings and installations | Y | military building works |
| 207694 | ted | DE | Staatliches Bauamt Kempten | 45216200 | Germany-Kempten (Allgäu): Construction work for military buildings and installations | Y | military building works |
| 210215 | ted | GB | Ministry of Defence, DIO, Defence Infras | 45000000 | United Kingdom-Glasgow: Facilities management services | G | facilities management for the defence estate |
| 214490 | ted | DE | Staatl. Hochbauamt Schwäbisch Hall | 45216200 | Germany – Construction work for military buildings and installations – Hardheim, Carl-Schurz-Ka | Y | barracks renovation |
| 215947 | ted | DE | Bundesrepublik Deutschland vertreten dur | 45216200 | Germany – Construction work for military buildings and installations – 26E20050 - DstLg Schorte | Y | military building works |
| 256164 | ted | SK | Akadémia ozbrojených síl generála Milana | 50660000 | Slovakia – Repair and maintenance services of military electronic systems – Zabezpečenie špeciá | G | service for military electronics, academy |
| 262062 | ted | IT | 15° Centro rifornimenti e mantenimento ( | 50630000 | Italy-Padua: Repair and maintenance services of military vehicles | Y | military vehicle repair |

### Level low, cell G: military code only, security body (group security_buyer_cpv)

| id | src | cc | buyer | CPV | title | label | reason |
|---|---|---|---|---|---|---|---|
| 292929 | de_bkms | DE | Bundesrepublik Deutschland, vertreten du | 35330000 | Biathlon-Munition für die Bundespolizei | B | police ammunition |
| 305454 | es_placsp | ES | Concejalía Delegada de Policía Local del | 35330000 | Suministro de munición para formación con destino a la Policía Local de Zaragoza. | B | municipal police ammunition |
| 289282 | es_placsp_agg | ES | Departament d'Interior | 35320000 | Subministrament de 110 escopetes del calibre 12/70 i subministrament i instal·lació de 40 armer | B | regional police shotguns |
| 191689 | fr_boamp | FR | MINISTÈRE DE L'INTÉRIEUR | 35300000 | Acquisition de grenades de calibre 40mm | B | 40 mm grenades, interior ministry |
| 146914 | nl_tenderned | NL | Politie | 35200000 | Kogel- en steekwerend vest met Molle-draagsysteem (KSWV) & opschalingsmodule (OM) | B | police body armour |
| 280 | pl_atlas | PL | Izba Administracji Skarbowej w Kielcach | 35300000 | Zakup i dostawa 12 jednostek broni wraz z oprzyrządowaniem dla Świętokrzyskiego Urzędu Celno-Sk | B | weapons for customs-tax office |
| 1421 | pl_atlas | PL | Komenda Wojewódzka Policji w Szczecinie | 35200000 | Zakup i dostawa sprzętu policyjnego dla SPKP w Szczecinie w ramach projektu "IN SERVICE ++" wsp | B | police equipment |
| 296882 | pl_ezam | PL | Izba Administracji Skarbowej w Olsztynie | 35300000 | Dostawa paralizatorów elektrycznych wraz z ukompletowaniem | B | stun guns, tax administration |
| 38877 | ted | IT | Ministero della Giustizia — Dipartimento | 35331500 | Italy-Rome: Cartridges | B | justice ministry cartridges |
| 40501 | ted | PL | Centralny Zarząd Służby Więziennej | 35331500 | Poland-Warsaw: Cartridges | B | prison service cartridges |
| 45072 | ted | HU | Országos Rendőr-főkapitányság | 35721000 | Hungary-Budapest: Repair and maintenance services | B | police equipment repair |
| 46790 | ted | GR | Υπουργείο Εσωτερικών - Αρχηγείο Ελληνική | 35721000 | Greece-Athens: Electronic intelligence system | B | electronic intelligence system, interior |
| 49167 | ted | DE | Beschaffungsamt des Bundesministeriums d | 35815100 | Germany-Bonn: Bullet-proof vests | B | body armour, federal procurement office |
| 50695 | ted | ES | Ministerio del Interior | 35815100 | Spain-Madrid: Bullet-proof vests | B | body armour, interior ministry |
| 55538 | ted | EE | Politsei- ja Piirivalveamet | 35810000 | Estonia-Tallinn: Individual equipment | B | border-guard individual equipment |
| 58611 | ted | PL | Komenda Główna Policji | 35321100 | Poland-Warsaw: Hand guns | B | police handguns |
| 73164 | ted | RO | Ministerul Afacerilor Interne | 35412500 | Romania-Bucharest: Command and liaison vehicles | B | interior ministry vehicles |
| 77002 | ted | CY | Αστυνομία Κύπρου | 35331500 | Cyprus-Nicosia: Cartridges | B | police cartridges |
| 78057 | ted | PL | Izba Administracji Skarbowej w Rzeszowie | 35000000 | Poland-Rzeszów: Ammunition for firearms and warfare | B | tax administration ammunition |
| 93985 | ted | NO | Politiets fellestjenester | 35200000 | Norway-Jaren: Weapons, ammunition and associated parts | B | police weapons |
| 97023 | ted | DE | Polizeiverwaltungsamt Logistikzentrum | 35810000 | Germany-Markkleeberg: Individual equipment | B | police equipment |
| 99598 | ted | CZ | Česká republika - Ministerstvo vnitra | 35331000 | Czechia-Prague: Ammunition for firearms and warfare | B | interior ministry ammunition |
| 107119 | ted | GR | ΥΠΟΥΡΓΕΙΟ ΠΡΟΣΤΑΣΙΑΣ ΤΟΥ ΠΟΛΙΤΗ / ΓΕΝΙΚΗ | 35000000 | Greece – Security, fire-fighting, police and defence equipment – Υπ' αριθ. 9/2023 Διακήρυξη Γ.Δ | B | civil protection equipment |
| 110856 | ted | CY | Αστυνομία Κύπρου | 35720000 | Cyprus – Intelligence, surveillance, target acquisition and reconnaissance – Δ.Ο 34/2024 ΠΡΟΣΦΟ | B | police surveillance |
| 114093 | ted | FR | Ministère de l'intérieur | 35330000 | France – Ammunition – Fourniture de grenades à main de désencerclement pour les forces de polic | B | police grenades |
| 120471 | ted | LV | LR Tieslietu ministrijas Ieslodzījuma vi | 35812300 | Latvia – Combat gear – Speciālo līdzekļu un metāla detektoru iegāde ar piegādi ieslodzījuma vie | B | prison security equipment |
| 126759 | ted | CZ | Ministerstvo vnitra | 35331000 | Czechia – Ammunition for firearms and warfare – Rámcová dohoda - náboje 4,6x30 mm v provedení p | B | interior ministry ammunition |
| 128754 | ted | PL | AGENCJA BEZPIECZEŃSTWA WEWNĘTRZNEGO | 35811300 | Poland – Military uniforms – Zakup i sukcesywna dostawa składników umundurowania | B | military uniform components for the internal security agency |
| 132462 | ted | HR | MINISTARSTVO PRAVOSUĐA, UPRAVE I DIGITAL | 35220000 | Croatia – Anti-riot equipment – Specijalna oprema za interventni tim po grupama | B | anti-riot equipment |
| 256556 | ted | RO | INSPECTORATUL GENERAL AL POLITIEI DE FRO | 50660000 | Romania – Repair and maintenance services of military electronic systems – Mentenanță preventiv | B | military electronics maintenance for police |
| 261449 | ted | RO | Inspectoratul General al Poliției de Fro | 50660000 | Romania-Bucharest: Repair and maintenance services of military electronic systems | B | military electronics maintenance for police |
| 130062 | ted | IE | Department of Justice Home Affairs and M | 75230000 | Ireland – Justice services – RFT for the provision of an Electronic Monitoring Managed Service  | N | electronic monitoring service |
| 236440 | ted | NL | Ministerie van Justitie en Veiligheid | 48000000 | Netherlands – Software package and information systems – Europese aanbesteding EAP2024 MJenV | N | software |
| 1654 | pl_atlas | PL | Izba Administracji Skarbowej w Gdańsku | 35512400 | Dostawa zdalnie sterowanego pojazdu podwodnego dla Pomorskiego Urzędu Wojewódzkiego w Gdańsku | N | underwater vehicle for a provincial office |
| 130957 | ted | IT | Comando Generale della Guardia di Finanz | 35510000 | Italy – Warships – ATTO AGGIUNTIVO IN FORMA PUBBLICO - AMMINISTRATIVA AL CONTRATTO N. 1628 DI R | Y | warships of the Guardia di Finanza |

### Level low, cell H: directive only, civil buyer (group directive_civil_buyer)

| id | src | cc | buyer | CPV | title | label | reason |
|---|---|---|---|---|---|---|---|
| 292860 | de_bkms | DE | Bundesanstalt für Immobilienaufgaben (BI | 45100000 | Vorinformation – Industrieforum „BwBauProgU“ Umwelt und Medien: Totalunternehmerleistungen für  | Y | Bundeswehr building programme forum |
| 74040 | ted | PL | Skarb Państwa – Inspektorat Uzbrojenia | 32344210 | Poland-Warsaw: Radio equipment | Y | radio equipment, armaments inspectorate |
| 108303 | ted | DE | Bundesrepublik Deutschland vertreten dur | 45213150 | Germany – Office block construction work – 23S30513 - Marinestützpunkt Wilhelmshaven, Neubau Di | Y | naval base building |
| 113316 | ted | DE | Bundesrepublik Deutschland vertreten dur | 45213150 | Germany – Office block construction work – 24S30162 - Marinestützpunkt Wilhelmshaven, Neubau Di | Y | naval base building |
| 115758 | ted | DE | Bundesrepublik Deutschland vertreten dur | 45213150 | Germany – Office block construction work – 24S30344 - Bundesliegenschaft in Wilhelmshaven, Neub | Y | naval base building |
| 123447 | ted | DE | Bundesrepublik Deutschland vertreten dur | 71300000 | Germany – Engineering services – WTD 91 Meppen: Erneuerung Klimakammern | Y | Bundeswehr test-centre climate chambers |
| 160497 | fr_boamp | FR | Atelier Idustriel de l'Aéronautique | 71200000 | La présente procédure concerne une mission de maîtrise d'oeuvre privée pour la construction d'u | G | building at a military aircraft workshop |
| 202863 | fr_boamp | FR | DMAE/SDA/SSAM 33-504 | 71323000 | Prestations de délestage de productique (conception, fabrication, usinage) au profit du périmèt | G | outsourced machining for military aircraft maintenance |
| 75631 | ted | FR | Atelier industriel de l'aéronautique | 24000000 | France-Clermont-Ferrand: Chemical products | G | chemicals for a military aircraft workshop |
| 89076 | ted | PL | Stołeczny Zarząd Infrastruktury | 45000000 | Poland-Warsaw: Construction work | G | military infrastructure body, construction |
| 71500 | ted | FR | CEA (Commissariat à l'énergie atomique e | 72317000 | France-Arpajon: Data storage services | B | data storage at a military nuclear site |
| 77880 | ted | FR | Commissariat à l'énergie atomique et aux | 43800000 | France-Monts: Workshop equipment | B | workshop equipment at a military nuclear site |
| 87806 | ted | FR | Commissariat à l’énergie atomique et aux | 50700000 | France-Monts: Repair and maintenance services of building installations | B | installation repairs at a military nuclear site |
| 98670 | ted | FR | Commissariat à l'énergie atomique et aux | 42997300 | France-Is-sur-Tille: Industrial robots | B | robots at a military nuclear site |
| 124139 | ted | FR | Commissariat à l'énergie atomique et aux | 45316110 | France – Installation of road lighting equipment – Travaux de rénovation de l'éclairage des bât | B | lighting at a military nuclear site |
| 86319 | ted | RO | Serviciul de Telecomunicatii Speciale | 32570000 | Romania-București: Communications equipment | B | state special telecoms |
| 86777 | ted | DE | Bundesrepublik Deutschland, vertreten du | 35000000 | Germany-Bonn: Checking and testing apparatus | B | testing apparatus, buyer unclear |
| 102398 | ted | SK | Generálne riaditeľstvo Zboru väzenskej a | 35113300 | Slovakia – Safety installations – Systém kamier na uniformy príslušníkov ZVJS | B | prison-service body cameras |
| 113537 | ted | FI | Suomen Erillisverkot Oy | 34221000 | Finland – Special-purpose mobile containers – Osallistumishakemus häiriösuojattuja laitekonttej | B | state security network containers |
| 274519 | es_placsp | ES | Servicio de Salud de las Illes Balears | 50710000 | Primera prórroga del contrato de mantenimiento legal obligatorio de los equipos de climatizació | N | hospital air-conditioning |
| 199808 | fr_boamp | FR | 006-DDFIP | 79112100 | Marché Avocats DDFIP06 | N | legal services |
| 146663 | nl_tenderned | NL | Vitens N.V. | 64200000 | 0800/0900 servicenummerdiensten en 088 bedrijfsnummerdiensten | N | utility service numbers |
| 38351 | ted | DE | Land Niedersachen vertreten durch das St | 45331000 | Germany – Heating, ventilation and air-conditioning installation work – 26E30070 - CvO-Uni OL,  | N | university ventilation |
| 40391 | ted | PL | PGE Górnictwo i Energetyka Konwencjonaln | 42124290 | Poland-Bełchatów: Parts of centrifugal pumps | N | power-plant pumps |
| 56009 | ted | PL | Tauron Wytwarzanie S.A. | 42514000 | Poland-Jaworzno: Environmental improvement works | N | power-plant works |
| 58061 | ted | DE | DB Netz AG | 71000000 | Germany-Frankfurt-on-Main: Architectural, construction, engineering and inspection services | N | railway engineering |
| 58367 | ted | IT | ARNAS Civico di Cristina Benfratelli | 33190000 | Italy-Palermo: Miscellaneous medical devices and products | N | hospital supplies |
| 58719 | ted | FR | Commissariat à l'énergie atomique et aux | 71300000 | France-Gif-sur-Yvette: Engineering services | N | research engineering |
| 62934 | ted | NO | Statsbygg | 45000000 | Norway-Oslo: Construction work | N | state building agency |
| 67824 | ted | BY | Ambasada Rzeczypospolitej Polskiej w Rep | 71200000 | Belarus-Minsk: Construction supervision services | N | embassy supervision |
| 70805 | ted | SK | Ministerstvo zahraničných vecí a európsk | 72211000 | Slovakia-Bratislava: System and support services | N | foreign ministry IT |
| 71977 | ted | DE | Staatliches Baumanagement Hannover | 71321000 | Germany-Hanover: Engineering design services for mechanical and electrical installations for bu | N | building design |
| 72411 | ted | FR | Commune de Rivedoux-Plage | 45111291 | France-Rivedoux-Plage: Site-development work | N | municipal site works |
| 72789 | ted | FR | Commissariat à l'énergie atomique et aux | 71300000 | France-Gif-sur-Yvette: Engineering services | N | research engineering |
| 76813 | ted | IT | AZIENDA DI RILIEVO NAZIONALE E DI ALTA S | 33000000 | Italy-Palermo: Medical equipments, pharmaceuticals and personal care products | N | hospital supplies |
| 78208 | ted | DE | Staatliches Baumanagement Ems-Weser | 45316110 | Germany-Wilhelmshaven: Installation of road lighting equipment | N | road lighting |
| 83754 | ted | DE | Auswärtiges Amt vertreten durch das Bund | 32351200 | Germany-Brandenburg an der Havel: Screens | N | screens |
| 84392 | ted | BG | АГЕНЦИЯ ЗА ЯДРЕНО РЕГУЛИРАНЕ | 71321000 | Bulgaria-Sofia: Engineering design services for mechanical and electrical installations for bui | N | nuclear regulator design |
| 93207 | ted | DE | Landesbetrieb Bau- und Liegenschaftsmana | 45331000 | Germany-Magdeburg: Heating, ventilation and air-conditioning installation work | N | ventilation |
| 94686 | ted | DE | Landesbetrieb Bau- und Liegenschaftsmana | 45331200 | Germany-Magdeburg: Ventilation and air-conditioning installation work | N | ventilation |
| 97147 | ted | IT | ANAS S.p.A. - Società con Socio Unico | 30199770 | Italy-Rome: Other services | N | road operator |
| 98295 | ted | CZ | ČEPS, a.s. | 79710000 | Czechia-Prague: Security services | N | grid operator security services |
| 104354 | ted | FR | Commissariat à l'Energie Atomique et aux | 45200000 | France – Works for complete or part construction and civil engineering work – Travaux de rénova | N | renovation |
| 107135 | ted | DE | Staatliches Hochbauamt Heidelberg | 71321000 | Germany – Engineering design services for mechanical and electrical installations for buildings | N | building design |
| 107190 | ted | DE | Staatliches Bauamt Ingolstadt-Vergabeste | 45262670 | Germany – Metalworking – Metallbau Sheaddaecher | N | metalwork |
| 109124 | ted | DE | Bundesanstalt für Immobilienaufgaben | 71200000 | Germany – Architectural and related services – Planungsleistungen Mieterausbau Bonn (Lose 1 bis | N | tenant fit-out |
| 109998 | ted | DE | Thüringer Landesamt für Bau und Verkehr | 45216111 | Germany – Police station construction work – Gerüstbauarbeiten | N | police-station scaffolding |
| 113730 | ted | DE | Thüringer Landesamt für Bau und Verkehr | 45216100 | Germany – Construction work for buildings relating to law and order or emergency services – Fas | N | emergency-services building facade |
| 118221 | ted | DE | Thüringer Landesamt für Bau und Verkehr | 45216100 | Germany – Construction work for buildings relating to law and order or emergency services – San | N | emergency-services building partitions |
| 135561 | ted | PT | Serviços Partilhados do Ministério da Sa | 55511000 | Portugal – Canteen and other restricted-clientele cafeteria services – CONCURSO PÚBLICO COM PUB | N | canteen service |
| 137516 | ted | RO | Compania Nationala Aeroporturi Bucuresti | 79713000 | Romania – Guard services – servicii de pază a obiectivelor, bunurilor și valorilor deținute de  | N | airport guard services |

### Level low, cell J: directive only, defence/security class or linked

| id | src | cc | buyer | CPV | title | label | reason |
|---|---|---|---|---|---|---|---|
| 273412 | de_bkms | DE | Bundesrepublik Deutschland vertreten dur | 45213150 | 24S30162 - Marinestützpunkt Wilhelmshaven, Neubau Dienstgebäude - Fenster/Türen u. innere Metal | Y | naval base building |
| 50821 | ted | DE | Bundesrepublik Deutschland, vertreten du | 14622000 | Germany-Ulm: Metalworking | G | metalworking, defence class body |
| 101633 | ted | DK | Forsvarsministeriets Ejendomsstyrelse | 45200000 | Denmark – Works for complete or part construction and civil engineering work – Hovedentreprisek | G | defence estates construction |
| 271230 | de_bkms | DE | Staatliches Hochbauamt Schwäbisch Hall | 71200000 | Architektenleistungen nach Teil 3 Abschnitt 1 HOAI, Grund-+Besondere Leistungen Lph 2-8 | B | architect services |
| 277870 | de_bkms | DE | Staatliches Hochbauamt Karlsruhe | 45000000 | VE008_Freianlagen DIN 18300, DIN 18318, DIN 18320, DIN 14475 | B | landscaping |
| 278101 | de_bkms | DE | Bundesamt für Auswärtige Angelegenheiten | 32250000 | Beschaffung  20 SINA Communicator Diplo S | B | secure communicator for diplomats |
| 288301 | de_bkms | DE | Freistaat Bayern, vertreten durch das St | 35000000 | Rahmenvertrag über die Beschaffung und den Betrieb cloudbasierter Body-Cam-Systeme für die Baye | B | police body cameras |
| 246668 | es_placsp | ES | División Económica y Técnica (Cuerpo Nac | 34731700 | Suministro de material de repuesto para el mantenimiento de los helicópteros EC-120, EC-135 y d | B | police helicopter spares |
| 146648 | nl_tenderned | NL | Politie | 34100000 | CGD Snelle interventie voertuigen 2022 | B | police vehicles |
| 53266 | ted | DE | Zentrale Polizeidirektion Niedersachen | 50333000 | Germany-Hanover: Maintenance services of radio-communications equipment | B | police radio maintenance |
| 57623 | ted | NO | Politiets fellestjenester [Norwegian Pol | 31351000 | Norway-Oslo: Safety installations | B | police safety installations |
| 61527 | ted | FI | Finnish Customs | 38580000 | Finland-Helsinki: Non-medical equipment based on the use of radiations | B | customs radiation equipment |
| 84336 | ted | HR | MINISTARSTVO UNUTARNJIH POSLOVA | 35121300 | Croatia-Zagreb: Security fittings | B | security fittings |
| 92207 | ted | PL | Komenda Główna Policji | 18444000 | Poland-Warsaw: Protective headgear | B | police helmets |
| 117479 | ted | LU | Ministère des Affaires étrangères et eur | 35000000 | Luxembourg – Security, fire-fighting, police and defence equipment – Acquisition de cent appare | B | protection devices, unclear |
| 129781 | ted | PL | Służba Ochrony Państwa | 32420000 | Poland – Network equipment – Dostawa „Systemu NIDS - zwiększenie bezpieczeństwa systemów telein | B | state protection network system |
| 135218 | ted | PL | Komenda Główna Straży Granicznej | 32323500 | Poland – Video-surveillance system – Zwiększenia zdolności obronnych Straży Granicznej w zakres | B | border-guard surveillance |
| 286671 | de_bkms | DE | Thüringer Landesamt für Bau und Verkehr | 45216100 | Schlosserarbeiten 3.BA | N | locksmith works |
| 287150 | de_bkms | DE | Thüringer Landesamt für Bau und Verkehr | 45216100 | Sanitärtrennwände 3.BA | N | partitions |
| 287516 | de_bkms | DE | Thüringer Landesamt für Bau und Verkehr | 45216100 | Heizung / Lüftung | N | heating and ventilation |
| 290308 | de_bkms | DE | Thüringer Landesamt für Bau und Verkehr | 45215222 | Bauvorbereitung | N | site preparation |
| 288012 | de_bkms | DE | Landeshauptstadt Düsseldorf, Der Oberbür | 31000000 | Rahmenliefervereinbarung Reagenzien und Verbrauchsmaterial | N | laboratory reagents |
| 288513 | de_bkms | DE | Katholisches Klinikum Bochum gGmbH | 48000000 | EX POST: Katholisches Klinikum Bochum / Beschaffung von 70 Lizenzen für die Dokumentation und S | N | hospital licences |
| 204402 | fr_boamp | FR | Ministère de l'intérieur / DEPAFI / SAIL | 72000000 | AMOA_MAYOTTE_LIIC | N | consulting |
| 58914 | ted | BG | Министерство на вътрешните работи | 64000000 | Bulgaria-Sofia: Postal and telecommunications services | N | postal services |
| 67015 | ted | HR | Ministarstvo unutarnjih poslova | 72222300 | Croatia-Zagreb: Information technology services | N | IT services |
| 81344 | ted | PL | Komenda Główna Straży Granicznej | 48000000 | Poland-Warsaw: Repair and maintenance services | N | software maintenance |
| 84747 | ted | DK | Rigspolitiet v./Center for Flåde- og Mat | 34100000 | Denmark-Copenhagen: Repair and maintenance services of cars | N | police car repair |
| 123710 | ted | FI | Poliisihallitus | 72000000 | Finland – IT services: consulting, software development, Internet and support – Kasvokuvavertai | N | police IT |
| 127816 | ted | FI | Poliisihallitus | 72000000 | Finland – IT services: consulting, software development, Internet and support – Ensihoitokertom | N | police IT |
| 131113 | ted | CZ | Zařízení služeb pro Ministerstvo vnitra | 45200000 | Czechia – Works for complete or part construction and civil engineering work – Rekonstrukce zas | N | reconstruction of meeting rooms |

### Level low, cell K: link to a defence notice only

| id | src | cc | buyer | CPV | title | label | reason |
|---|---|---|---|---|---|---|---|
| 269289 | fr_boamp | FR | CNSO Orléans | 32260000 | Acquisition d'équipements optiques tactiques au profit de l'EAC2P de la BA105 d'Evreux | Y | tactical optics for an air base |
| 269959 | pl_ezam | PL | 17. Terenowy Oddział Lotniskowy | 45000000 | Polska – Roboty budowlane – 54055_RB_Rozbudowa i modernizacja składu lotniczych środków bojowyc | Y | aircraft munitions depot works |
| 269942 | pl_ezam | PL | Skarb Państwa-22. Wojskowy Odział Gospod | 15100000 | Polska – Produkty zwierzęce, mięso i produkty mięsne – Dostawy mięsa i produktów mięsnych | G | meat |
| 234757 | ted | PL | 4 WOJSKOWY ODDZIAŁ GOSPODARCZY | 15500000 | Poland – Dairy products – 4WOG.1200.2712.69.2026 Dostawa mleka i produktów mleczarskich w podia | G | dairy products |
| 283714 | de_bkms | DE | Deutsches Zentrum für Luft- und Raumfahr | 42113170 | Rahmenvertrag zur Beschaffung von Hochleistungssteckverbindern für Höhenforschungsraketen | B | research rocket connectors |
| 285254 | de_bkms | DE | Deutsches Zentrum für Luft- und Raumfahr | 31711110 | TM-Empfänger S-Band   Multifunktionaler Telemetrieempfänger | B | research telemetry receiver |
| 269490 | pl_ezam | PL | Ministerstwo Spraw Wewnętrznych i Admini | 32420000 | Polska – Urządzenia sieciowe – Zakup systemu monitoringu bezpieczeństwa sieci wraz z zarządzani | B | network monitoring, interior |
| 269735 | pl_ezam | PL | 17. Terenowy Oddział Lotniskowy | 71000000 | Polska – Usługi architektoniczne, budowlane, inżynieryjne i kontrolne – DP 54078 Budowa wieży p | B | airport tower design |
| 269800 | pl_ezam | PL | Komenda Główna Straży Granicznej | 32323500 | Polska – Urządzenia do nadzoru wideo – Zwiększenia zdolności obronnych Straży Granicznej w zakr | B | border surveillance |
| 270022 | pl_ezam | PL | Izba Administracji Skarbowej w Rzeszowie | 35000000 | Polska – Sprzęt bezpieczeństwa, gaśniczy, policyjny i obronny – Zakup broni, amunicji i środków | B | weapons for tax administration |
| 319781 | es_placsp | ES | Junta de Gobierno del Ayuntamiento de Có | 44100000 | Suministro de materiales necesarios para la Delegación de Infraestructuras | N | municipal materials |
| 293455 | es_placsp_agg | ES | Ayuntamiento de Vitoria-Gasteiz-Junta de | 18221200 | Suministro de vestuario y equipación (plurianual 2024-2026) para el Cuerpo de Policía Local de  | N | municipal police clothing |
| 270152 | nl_tenderned | NL | Gemeente Almere | 35113430 | BOA-bedrijfskleding | N | municipal enforcement clothing |
| 269482 | pl_ezam | PL | Morska Służba Poszukiwania i Ratownictwa | 48000000 | Polska – Pakiety oprogramowania i systemy informatyczne – Rozbudowa systemu bezpieczeństwa żegl | N | sea rescue software |
| 269534 | pl_ezam | PL | Morska Służba Poszukiwania i Ratownictwa | 48000000 | Polska – Pakiety oprogramowania i systemy informatyczne – Rozbudowa systemu bezpieczeństwa żegl | N | sea rescue software |
| 269558 | pl_ezam | PL | Morska Służba Poszukiwania i Ratownictwa | 48000000 | Polska – Pakiety oprogramowania i systemy informatyczne – Rozbudowa systemu bezpieczeństwa żegl | N | sea rescue software |
| 269607 | pl_ezam | PL | Morska Służba Poszukiwania i Ratownictwa | 48000000 | Polska – Pakiety oprogramowania i systemy informatyczne – Rozbudowa systemu bezpieczeństwa żegl | N | sea rescue software |
| 269867 | pl_ezam | PL | Skarb Państwa – Generalny Dyrektor Dróg  | 45000000 | Polska – Roboty budowlane – Projekt i budowa autostrady A2 Warszawa – Kukuryki na odcinku obw.  | N | motorway |
| 270050 | pl_ezam | PL | KOMENDA GŁÓWNA PAŃSTWOWEJ STRAŻY POŻARNE | 35113400 | Polska – Odzież ochronna i zabezpieczająca – Wyposażenie ratowników w odzież ochronną dla SGRW  | N | fire-fighter protective clothing |
| 270126 | pl_ezam | PL | Komenda Wojewódzka Państwowej Straży Poż | 34144200 | Polska – Pojazdy służb ratowniczych – Samochód dowodzenia i łączności (kompanijne stanowisko do | N | fire-brigade command vehicle |
| 270129 | pl_ezam | PL | Centralne Biuro Antykorupcyjne | 32420000 | Polska – Urządzenia sieciowe – Zakup urządzeń sieciowych. | N | anti-corruption bureau network |
| 270144 | pl_ezam | PL | KOMENDA GŁÓWNA POLICJI | 48000000 | Polska – Pakiety oprogramowania i systemy informatyczne – Zakup subskrypcji licencji VMware | N | police software licences |
