/**
 * A country as a visitor writes it ("DE", "DEU", "Germany") to its ISO 3166-1 alpha-2 code (UX audit M6: `?country=Germany`
 * and `?country=DEU` on /suppliers were a 404 page). Mirrors backend/dgate/countries.py, which the API applies as well.
 * The three-letter table is the one the TED connector uses (backend/dgate/normalise.py); English names are the browser's
 * own (Intl.DisplayNames) plus the usual alternatives. Pure, so lib/country-input.check.ts runs it on its own.
 */

const ISO3_PAIRS = `
  AFG AF ALA AX ALB AL DZA DZ ASM AS AND AD AGO AO AIA AI ATA AQ ATG AG ARG AR ARM AM ABW AW AUS AU AUT AT
  AZE AZ BHS BS BHR BH BGD BD BRB BB BLR BY BEL BE BLZ BZ BEN BJ BMU BM BTN BT BOL BO BES BQ BIH BA BWA BW
  BVT BV BRA BR IOT IO BRN BN BGR BG BFA BF BDI BI CPV CV KHM KH CMR CM CAN CA CYM KY CAF CF TCD TD CHL CL
  CHN CN CXR CX CCK CC COL CO COM KM COG CG COD CD COK CK CRI CR CIV CI HRV HR CUB CU CUW CW CYP CY CZE CZ
  DNK DK DJI DJ DMA DM DOM DO ECU EC EGY EG SLV SV GNQ GQ ERI ER EST EE SWZ SZ ETH ET FLK FK FRO FO FJI FJ
  FIN FI FRA FR GUF GF PYF PF ATF TF GAB GA GMB GM GEO GE DEU DE GHA GH GIB GI GRC GR GRL GL GRD GD GLP GP
  GUM GU GTM GT GGY GG GIN GN GNB GW GUY GY HTI HT HMD HM VAT VA HND HN HKG HK HUN HU ISL IS IND IN IDN ID
  IRN IR IRQ IQ IRL IE IMN IM ISR IL ITA IT JAM JM JPN JP JEY JE JOR JO KAZ KZ KEN KE KIR KI PRK KP KOR KR
  KWT KW KGZ KG LAO LA LVA LV LBN LB LSO LS LBR LR LBY LY LIE LI LTU LT LUX LU MAC MO MDG MG MWI MW MYS MY
  MDV MV MLI ML MLT MT MHL MH MTQ MQ MRT MR MUS MU MYT YT MEX MX FSM FM MDA MD MCO MC MNG MN MNE ME MSR MS
  MAR MA MOZ MZ MMR MM NAM NA NRU NR NPL NP NLD NL NCL NC NZL NZ NIC NI NER NE NGA NG NIU NU NFK NF MKD MK
  MNP MP NOR NO OMN OM PAK PK PLW PW PSE PS PAN PA PNG PG PRY PY PER PE PHL PH PCN PN POL PL PRT PT PRI PR
  QAT QA REU RE ROU RO RUS RU RWA RW BLM BL SHN SH KNA KN LCA LC MAF MF SPM PM VCT VC WSM WS SMR SM STP ST
  SAU SA SEN SN SRB RS SYC SC SLE SL SGP SG SXM SX SVK SK SVN SI SLB SB SOM SO ZAF ZA SGS GS SSD SS ESP ES
  LKA LK SDN SD SUR SR SJM SJ SWE SE CHE CH SYR SY TWN TW TJK TJ TZA TZ THA TH TLS TL TGO TG TKL TK TON TO
  TTO TT TUN TN TUR TR TKM TM TCA TC TUV TV UGA UG UKR UA ARE AE GBR GB USA US UMI UM URY UY UZB UZ VUT VU
  VEN VE VNM VN VGB VG VIR VI WLF WF ESH EH YEM YE ZMB ZM ZWE ZW XKX XK EUR EU`.split(/\s+/).filter(Boolean);

const ISO3_TO_2 = new Map<string, string>();
for (let i = 0; i < ISO3_PAIRS.length; i += 2) ISO3_TO_2.set(ISO3_PAIRS[i], ISO3_PAIRS[i + 1]);

/** Names people type that the browser's list does not carry (the browser says "Czechia", "Türkiye", "Myanmar (Burma)"). */
const ALTERNATIVES: Record<string, string> = {
  'czech republic': 'CZ', turkey: 'TR', uk: 'GB', 'great britain': 'GB', britain: 'GB', england: 'GB', holland: 'NL',
  'the netherlands': 'NL', usa: 'US', 'united states of america': 'US', america: 'US', uae: 'AE', russia: 'RU',
  'russian federation': 'RU', macedonia: 'MK', 'slovak republic': 'SK', korea: 'KR', 'republic of korea': 'KR',
  'ivory coast': 'CI', burma: 'MM', 'czech rep': 'CZ', deutschland: 'DE', espana: 'ES', italia: 'IT', polska: 'PL',
  'holy see': 'VA', bosnia: 'BA', palestine: 'PS',
};

/** Lower case, no accents, "&" read as "and", every other mark dropped, words joined by one space. */
const key = (s: string) => s.replace(/&/g, ' and ').normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();

let byName: Map<string, string> | undefined;
function names(): Map<string, string> {
  if (byName) return byName;
  byName = new Map();
  let display: Intl.DisplayNames | null = null;
  try { display = new Intl.DisplayNames(['en'], { type: 'region' }); } catch { display = null; }
  if (display) {
    for (const code of new Set(ISO3_TO_2.values())) {
      try {
        const name = display.of(code);
        if (name && name !== code && !/^unknown/i.test(name)) byName.set(key(name), code);
      } catch { /* a code the platform does not know has no name */ }
    }
  }
  byName.set('kosovo', 'XK');
  byName.set('european union', 'EU');
  for (const [name, code] of Object.entries(ALTERNATIVES)) byName.set(name, code);
  return byName;
}

/**
 * `DE`, `deu`, `Germany`, ` germany ` -> `DE`; null when the text is none of the three. Two letters are a code as written
 * (an empty group, not an error, for a code nobody holds), except "UK", which is no ISO code and is read as the name it is.
 */
export function countryToIso2(input: string): string | null {
  const raw = input.trim();
  const code = raw.toUpperCase();
  if (/^[A-Z]{2}$/.test(code)) return names().get(key(raw)) ?? code;
  return ISO3_TO_2.get(code) ?? names().get(key(raw)) ?? null;
}

/** A comma-separated list as typed: the codes it holds, in order and without repeats, and the parts that are no country. */
export function parseCountries(input: string): { codes: string[]; unknown: string[] } {
  const codes: string[] = [];
  const unknown: string[] = [];
  for (const part of input.split(',').map((p) => p.trim()).filter(Boolean)) {
    const code = countryToIso2(part);
    if (code === null) unknown.push(part);
    else if (!codes.includes(code)) codes.push(code);
  }
  return { codes, unknown };
}
