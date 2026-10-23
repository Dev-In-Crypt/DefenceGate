/**
 * WP-80: the free official guides and the Spanish regional grants that cover a step of the supplier roadmap, from the desk research of
 * 22 October 2026 (docs/research/ANGLE1_SPAIN_LANDSCAPE_2026-10-22.md, section 2). Only what that research states, with its source; an
 * amount only where it gives one. Calls open and close: every grant line says which call it read and that the current call decides.
 * Pure data; lib/wp80.check.ts holds it to the research file.
 */

export interface Guide { title: string; by: string; date: string; url: string }

export interface Grant {
  /** ISO 3166-2 code of the region, as the supplier page stores it (`supplier.region`). */
  region: string;
  regionName: string;
  programme: string;
  /** What the research says the call or list pays for, in its words. */
  covers: string;
  /** The figures the research states for it, or null. */
  amounts: string | null;
  /** The call or list read, and its window. */
  read: string;
  url: string;
  /** Requirement codes of the roadmap it covers. */
  requirements: string[];
}

const QUALITY = ['REQ-PECAL', 'REQ-AQAP2110', 'REQ-AQAP2310'];
const SECURITY = ['REQ-FSC-ES', 'REQ-HSES-ES'];

export const GUIDES: Record<string, Guide[]> = {
  'REQ-RID': [{
    title: 'Guide to registration in the RID (Registro de Empresas DGAM)', by: 'CAETRA programme, Instituto de Fomento de la Región de Murcia',
    date: 'November 2024', url: 'https://caetraprogramme.institutofomentomurcia.es/wp-content/uploads/2024/11/1_Guia_CAETRA_RegistroDGAM.pdf',
  }],
  ...Object.fromEntries(QUALITY.map((code) => [code, [{
    title: 'Guide to PECAL/AQAP certification', by: 'CAETRA programme, Instituto de Fomento de la Región de Murcia', date: 'June 2026',
    url: 'https://caetraprogramme.institutofomentomurcia.es/wp-content/uploads/2026/06/3_Guia_CAETRA_PECAL_AQAP.pdf',
  }]])),
};

/** Free courses that cover several steps at once (shown once, above the roadmap). */
export const COURSES: (Guide & { region: string; covers: string })[] = [{
  title: 'Dual Technology & Industry Readiness Programme', by: 'ACCIÓ (Generalitat de Catalunya)', date: 'announced 10 April 2026',
  region: 'ES-CT', covers: 'a free 7-hour in-person course for 400 companies (automotive, space, metalworking, machinery) on certifications, homologation and access to state and EU procurement',
  url: 'https://es.ara.cat/economia/industria/gobierno-impulsa-plan-introducir-400-empresas-sector-defensa_1_5703773.html',
}];

export const GRANTS: Grant[] = [
  {
    region: 'ES-MC', regionName: 'Región de Murcia', programme: 'CAETRA (INFO Murcia), service CS001',
    covers: 'first registration in the RID', amounts: 'EUR 2,500 for the service', read: 'list of services 2025',
    url: 'https://sede.institutofomentomurcia.es/infodirecto/servlet/DownloadFile?id=2208091', requirements: ['REQ-RID'],
  },
  {
    region: 'ES-MC', regionName: 'Región de Murcia', programme: 'CAETRA (INFO Murcia), service CS002',
    covers: 'PECAL/AQAP or EN 9100 certification', amounts: 'EUR 9,000 per standard', read: 'list of services 2025',
    url: 'https://sede.institutofomentomurcia.es/infodirecto/servlet/DownloadFile?id=2208091', requirements: [...QUALITY, 'REQ-EN9100'],
  },
  {
    region: 'ES-MC', regionName: 'Región de Murcia', programme: 'CAETRA (INFO Murcia), service CS004',
    covers: 'the HSEM company clearance or the HSES establishment clearance', amounts: 'EUR 4,000 (HSEM) or EUR 10,000 (HSES)',
    read: 'list of services 2025', url: 'https://sede.institutofomentomurcia.es/infodirecto/servlet/DownloadFile?id=2208091', requirements: SECURITY,
  },
  {
    region: 'ES-AR', regionName: 'Aragón', programme: 'IAF, Orden ECE/1276/2026 (BOA 4 September 2026)',
    covers: 'PECAL/AQAP, ISO 9001 and EN 9100; RID registration; HSEM/HSES paperwork; homologation; tender and proposal consultancy',
    amounts: 'EUR 5,000 to 30,000 per company; 70 % for micro-companies and start-ups, 50 % for SMEs', read: 'call open 7 to 25 September 2026 (closed)',
    url: 'https://www.iustel.com/diario_del_derecho/noticia.asp?ref_iustel=1269075',
    requirements: ['REQ-RID', ...QUALITY, 'REQ-ISO9001', 'REQ-EN9100', ...SECURITY],
  },
  {
    region: 'ES-GA', regionName: 'Galicia', programme: 'Xunta de Galicia, IN519G (suppliers in security and defence)',
    covers: 'first RID registration, PECAL/AQAP, homologation, HSEM/HSES, proposals for national and EU calls',
    amounts: 'up to EUR 75,000 per company, 80 %', read: 'call open 13 February to 13 May 2026 (closed)',
    url: 'https://proxconsultores.com/subvencion/in519g-ayudas-empresas-gallegas-suministradoras-materia-seguridad-defensa',
    requirements: ['REQ-RID', ...QUALITY, ...SECURITY],
  },
  {
    region: 'ES-EX', regionName: 'Extremadura', programme: 'Consolidapyme',
    covers: 'PECAL/AQAP and other defence certifications', amounts: '80 %; eligible cost of PECAL up to EUR 11,000',
    read: 'call closed 27 July 2026',
    url: 'https://www.extremaduraempresarial.es/2026/06/04/ayudas-para-empresas-que-soliciten-las-certificaciones-de-la-otan-para-suministrar-a-la-industria-militar/',
    requirements: QUALITY,
  },
];

export const CHECK_THE_CALL = 'Check the current call before you count on it: windows, amounts and conditions change from one call to the next, and the figures are those of the call or list named.';

export function guidesFor(requirement: string | null): Guide[] {
  return requirement ? GUIDES[requirement] ?? [] : [];
}

/** The grants that have covered a requirement, the company's own region first. */
export function grantsFor(requirement: string | null, region = ''): Grant[] {
  if (!requirement) return [];
  const xs = GRANTS.filter((g) => g.requirements.includes(requirement));
  return [...xs.filter((g) => g.region === region), ...xs.filter((g) => g.region !== region)];
}

/** WP-89: whether the call or list a grant line read is closed (its `read` says so). */
export function isClosed(g: Grant): boolean {
  return g.read.toLowerCase().includes('closed');
}

/**
 * WP-89 (UX audit, section 4): the grants a company can use for a step. With its region chosen, that region's only (a regional
 * programme is for the companies established there: Murcia's and Galicia's were listed to a company in the Comunitat Valenciana); with
 * none chosen, every one. `none` is true when the region is chosen, none of its programmes covers the step and another region's does:
 * the report then says so in plain words and points to the regional development agency. No agency is named: our sources name none for
 * a region they hold no programme of (docs/research/ANGLE1_SPAIN_LANDSCAPE_2026-10-22.md).
 */
export function regionalGrants(requirement: string | null, region: string): { grants: Grant[]; none: boolean } {
  const all = grantsFor(requirement, region);
  if (!region) return { grants: all, none: false };
  const own = all.filter((g) => g.region === region);
  return { grants: own, none: own.length === 0 && all.length > 0 };
}

/** The sentence for a step no programme of the company's region covers. */
export function noRegionalGrant(regionName: string): string {
  return `No programme of ${regionName} in our sources pays for this step. Ask your regional development agency whether it has one; the programmes of other regions are for companies established there.`;
}
