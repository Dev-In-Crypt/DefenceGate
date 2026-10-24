/**
 * Demo data of the networks pages, used only when DG_API_URL is unset (the CI build and end-to-end run, development).
 * Invented organisations and projects ("Alpha Systems GmbH"); the shapes are those of the API (lib/networks-types.ts).
 * Nothing here is real, and the pages say "Demo" nowhere: a production build without the API refuses to start.
 */
import { parseQuery } from '../text-search';
import type {
  ConsortiumGaps, FundingRow, OrgFilters, OrgFunding, OrgListItem, OrgPage, OrgProfile, OrgProjectPage, OrgRef, PartnerPage,
  ProjectDetail, ProjectHistory, ProjectRef, SourceNote, UkrainePartners,
} from '../networks-types';

const SOURCES: SourceNote[] = [
  { code: 'cordis', name: 'CORDIS: EU research projects (Horizon Europe, Horizon 2020, FP7)', licence: 'Commission Decision 2011/833/EU (reuse of Commission documents)',
    attribution: 'Source: CORDIS, European Commission', readAt: '2026-10-17T20:00:00Z',
    note: "Participants and amounts as the Commission's CORDIS database states them (reuse under Commission Decision 2011/833/EU)." },
  { code: 'edf_factsheets', name: 'European Defence Fund: project factsheets of the call results', licence: 'Commission Decision 2011/833/EU (reuse of Commission documents)',
    attribution: 'Source: European Commission, DG DEFIS, EDF results factsheets', readAt: '2026-10-17T21:00:00Z',
    note: 'European Defence Fund participants are read from the project factsheets that DG DEFIS publishes, by a language model; every name is checked against the factsheet text and a name that is not in it is dropped. The factsheets state no amount per participant.' },
];
const AMOUNT_NOTE = 'EU contribution is the amount the open data of CORDIS pays to the participant. For a participant with linked third parties it may include their share (the CORDIS page prints the net); an amount the data does not hold is left out, not counted as zero. EDF factsheets state none per participant, so EDF projects count as projects but add nothing to the amounts.';

interface MockOrg { id: number; name: string; country: string; pic: string | null; slug: string }
const org = (id: number, name: string, country: string, pic: string | null, slug: string): MockOrg => ({ id, name, country, pic, slug: `${id}-${slug}` });
const A = org(101, 'ALPHA SYSTEMS GMBH', 'DE', '999000001', 'alpha-systems-gmbh');
const B = org(102, 'BRAVO INGÉNIERIE SAS', 'FR', '999000002', 'bravo-ingenierie-sas');
const C = org(103, 'KYIV INSTITUTE OF MATERIALS', 'UA', '999000003', 'kyiv-institute-of-materials');
const E = org(104, 'ECHO IBERICA SL', 'ES', null, 'echo-iberica-sl');
const ORGS = [A, B, C, E];
const ref = (o: MockOrg): OrgRef => ({ id: String(o.id), slug: o.slug, name: o.name, country: o.country });

interface MockProject { id: number; slug: string; acronym: string; title: string; programme: string; year: number; edf: boolean; members: [MockOrg, string, number | null][] }
const PROJECTS: MockProject[] = [
  { id: 201, slug: '201-alpha', acronym: 'ALPHA', title: 'Alpha sensing for resilient networks', programme: 'H2020', year: 2019, edf: false,
    members: [[A, 'coordinator', 400000], [B, 'participant', 300000], [C, 'participant', 200000]] },
  { id: 202, slug: '202-bravo', acronym: 'BRAVO', title: 'Bravo space networks', programme: 'HORIZON', year: 2023, edf: false,
    members: [[A, 'coordinator', 250000], [B, 'participant', 150000]] },
  { id: 203, slug: '203-charlie', acronym: 'CHARLIE', title: 'Charlie cyber shield', programme: 'EDF', year: 2024, edf: true,
    members: [[B, 'coordinator', null], [A, 'participant', null], [E, 'participant', null]] },
];
// A project whose source names no coordinator (UX audit M9: CORDIS 55762); kept out of PROJECTS so no count above changes.
const NO_COORDINATOR: MockProject = { id: 299, slug: '299-delta', acronym: 'DELTA', title: 'Delta consortium without a stated coordinator', programme: 'HORIZON', year: 2022, edf: false,
  members: [[A, 'participant', 100000], [B, 'participant', null]] };
const ref3 = (p: MockProject): ProjectRef => ({ slug: p.slug, acronym: p.acronym, title: p.title, programme: p.programme, year: p.year });
const projectsOf = (o: MockOrg) => PROJECTS.filter((p) => p.members.some(([m]) => m.id === o.id));

function item(o: MockOrg): OrgListItem {
  const ps = projectsOf(o);
  const amounts = ps.flatMap((p) => p.members.filter(([m, , eur]) => m.id === o.id && eur !== null).map(([, , eur]) => eur as number));
  const years = ps.map((p) => p.year);
  return {
    id: String(o.id), slug: o.slug, name: o.name, country: o.country, projects: ps.length,
    defenceProjects: ps.filter((p) => ['EDF', 'EDIDP', 'PADR'].includes(p.programme)).length,
    coordinated: ps.filter((p) => p.members.some(([m, r]) => m.id === o.id && r === 'coordinator')).length,
    euContribution: amounts.length ? amounts.reduce((a, b) => a + b, 0) : null,
    firstYear: Math.min(...years), lastYear: Math.max(...years), programmes: [...new Set(ps.map((p) => p.programme))].sort(),
  };
}

export function findOrg(slug: string): MockOrg | undefined {
  return ORGS.find((o) => o.slug === slug || slug.startsWith(`${o.id}-`));
}

export function queryOrgs(f: OrgFilters): OrgPage {
  const q = (f.q ?? '').toLowerCase();
  const topic = f.topic ? parseQuery(f.topic) : null;
  let items = ORGS.map(item).filter((i) =>
    i.projects >= (f.minProjects ?? 1)
    && (!f.country?.length || f.country.includes(i.country))
    && (!f.programme?.length || f.programme.some((p) => i.programmes.includes(p)))
    && (!f.role?.length || ORGS.some((o) => o.id === Number(i.id) && projectsOf(o).some((p) => p.members.some(([m, r]) => m.id === o.id && f.role?.includes(r)))))
    && (!q || i.name.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').includes(q.normalize('NFD').replace(/[̀-ͯ]/g, '')))
    // WP-91: as the API's `topic`: an organisation with a project whose acronym and title hold every word (or a synonym)
    && (!topic || ORGS.some((o) => o.id === Number(i.id) && projectsOf(o).some((p) => topic.matches(`${p.acronym} ${p.title}`)))));
  items = f.sort === 'name' ? items.sort((a, b) => a.name.localeCompare(b.name))
    : f.sort === 'defence' ? items.sort((a, b) => b.defenceProjects - a.defenceProjects || b.projects - a.projects || a.name.localeCompare(b.name))
      : items.sort((a, b) => b.projects - a.projects || a.name.localeCompare(b.name));
  const size = f.pageSize ?? 20;
  const page = f.page ?? 1;
  return { items: items.slice((page - 1) * size, page * size), total: items.length, totalExact: true, page, pageSize: size,
    meta: { updatedAt: '2026-10-17T21:30:00Z', sources: SOURCES, amountNote: AMOUNT_NOTE, sort: f.sort ?? 'projects', defenceProgrammes: ['EDF', 'EDIDP', 'PADR'] } };
}

export function orgProfile(slug: string): OrgProfile | null {
  const o = findOrg(slug);
  if (!o) return null;
  const i = item(o);
  const ps = projectsOf(o);
  const methods: Record<string, number> = o.pic ? { pic: ps.filter((p) => !p.edf).length, exact_name: ps.filter((p) => p.edf).length } : { exact_name: ps.length };
  return {
    id: String(o.id), slug: o.slug, name: o.name, country: o.country,
    pic: o.pic ? { value: o.pic, method: 'source', confidence: 1 } : null,
    counts: { projects: i.projects, participations: i.projects, coordinated: i.coordinated, euContribution: i.euContribution, firstYear: i.firstYear, lastYear: i.lastYear },
    programmes: i.programmes.map((code) => {
      const own = ps.filter((p) => p.programme === code);
      const eur = own.flatMap((p) => p.members.filter(([m, , e]) => m.id === o.id && e !== null).map(([, , e]) => e as number));
      return { code, name: code, projects: own.length, euContribution: eur.length ? eur.reduce((a, b) => a + b, 0) : null, firstYear: Math.min(...own.map((p) => p.year)), lastYear: Math.max(...own.map((p) => p.year)) };
    }),
    resolution: { note: `Participations: ${Object.entries(methods).map(([m, n]) => `${n} of ${ps.length} matched by ${m === 'pic' ? 'its PIC' : 'the same name (ignoring accents, capitals and the legal form) in the same country'}`).join('; ')}.`,
      participations: methods, lowestConfidence: o.pic ? 0.9 : 0.9 },
    aliases: { total: 1, items: [{ name: o.name.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()), method: 'pic', confidence: 1, firstSeen: '2026-10-17', source: 'cordis' }] },
    mergedFrom: 0, buyer: null, sources: SOURCES, amountNote: AMOUNT_NOTE,
  };
}

export function orgFunding(slug: string): OrgFunding | null {
  const o = findOrg(slug);
  if (!o) return null;
  const rows: FundingRow[] = projectsOf(o).map((p) => {
    const e = p.members.find(([m]) => m.id === o.id)?.[2] ?? null;
    return { programme: p.programme, year: p.year, projects: 1, euContribution: e, projectsWithoutAmount: e === null ? 1 : 0 };
  });
  const eur = rows.filter((r) => r.euContribution !== null);
  return { organisation: ref(o), rows, totals: { projects: rows.length, euContribution: eur.length ? eur.reduce((a, r) => a + (r.euContribution as number), 0) : null }, amountNote: AMOUNT_NOTE };
}

export function orgPartners(slug: string, f: { country?: string; programme?: string; page: number; pageSize: number }): PartnerPage | null {
  const o = findOrg(slug);
  if (!o) return null;
  const shared = new Map<number, MockProject[]>();
  for (const p of projectsOf(o)) {
    if (f.programme && p.programme !== f.programme) continue;
    for (const [m] of p.members) if (m.id !== o.id) shared.set(m.id, [...(shared.get(m.id) ?? []), p]);
  }
  const rows = [...shared.entries()]
    .map(([id, ps]) => ({ o: ORGS.find((x) => x.id === id) as MockOrg, ps }))
    .filter((r) => !f.country || r.o.country === f.country)
    .sort((a, b) => b.ps.length - a.ps.length || a.o.name.localeCompare(b.o.name));
  return {
    organisation: ref(o), total: rows.length, countries: new Set(rows.map((r) => r.o.country)).size, page: f.page, pageSize: f.pageSize,
    items: rows.slice((f.page - 1) * f.pageSize, f.page * f.pageSize).map((r) => ({
      organisation: ref(r.o), shared: r.ps.length, firstYear: Math.min(...r.ps.map((p) => p.year)), lastYear: Math.max(...r.ps.map((p) => p.year)),
      programmes: [...new Set(r.ps.map((p) => p.programme))].sort(), projects: r.ps.sort((a, b) => b.year - a.year).map(ref3),
    })),
    note: 'Partners are the organisations that were active in a project this organisation was active in. The shared projects shown are the most recent five.',
  };
}

export function orgProjects(slug: string, f: { programme?: string; page: number; pageSize: number }): OrgProjectPage | null {
  const o = findOrg(slug);
  if (!o) return null;
  const rows = projectsOf(o).filter((p) => !f.programme || p.programme === f.programme).sort((a, b) => b.year - a.year);
  return {
    organisation: ref(o), total: rows.length, page: f.page, pageSize: f.pageSize,
    items: rows.slice((f.page - 1) * f.pageSize, f.page * f.pageSize).map((p) => {
      const mine = p.members.find(([m]) => m.id === o.id) as [MockOrg, string, number | null];
      return { ...ref3(p), role: mine[1], contribution: mine[2], status: 'CLOSED', topic: null, category: p.edf ? 'CYBER' : null, totalCost: null, projectEuContribution: null };
    }),
  };
}

export function projectDetail(slug: string): ProjectDetail | null {
  const p = [...PROJECTS, NO_COORDINATOR].find((x) => x.slug === slug || slug.startsWith(`${x.id}-`));
  if (!p) return null;
  const members = [...p.members].sort((a, b) => Number(b[1] === 'coordinator') - Number(a[1] === 'coordinator') || a[0].country.localeCompare(b[0].country));
  const coordinator = members.find(([, r]) => r === 'coordinator');
  return {
    id: String(p.id), slug: p.slug, acronym: p.acronym, title: p.title, programme: { code: p.programme, name: p.programme },
    grantNumber: p.edf ? null : `70${p.id}`, call: null, topic: p.edf ? 'EDF-2023-DA-CYBER-CSAD' : null, actionType: p.edf ? 'DA' : null, category: p.edf ? 'CYBER' : null,
    callYear: p.year, status: 'CLOSED', startDate: p.edf ? null : `${p.year}-03-01`, endDate: null, durationMonths: p.edf ? 36 : null,
    totalCost: p.edf ? 8000000 : 1200000, euContribution: p.edf ? 6000000 : 900000,
    coordinator: coordinator ? ref(coordinator[0]) : null,
    members: members.map(([m, role, eur]) => ({ organisation: ref(m), role, contribution: eur, resolution: { method: p.edf ? 'exact_name' : 'pic', confidence: p.edf ? 0.9 : 1 } })),
    memberCount: members.length, countryCount: new Set(members.map(([m]) => m.country)).size,
    source: p.edf
      ? { code: 'edf_factsheets', name: SOURCES[1].name, licence: SOURCES[1].licence, attribution: SOURCES[1].attribution, url: 'https://defence-industry-space.ec.europa.eu/', urlLabel: 'EDF project factsheet' }
      : { code: 'cordis', name: SOURCES[0].name, licence: SOURCES[0].licence, attribution: SOURCES[0].attribution, url: `https://cordis.europa.eu/project/id/70${p.id}`, urlLabel: 'Project page on CORDIS' },
    factsheet: p.edf ? { readBy: 'language model', readAt: '2026-10-17T20:30:00Z', pages: 3, dropped: [{ kind: 'not_in_text', count: 2, meaning: 'names the model returned that are not in the factsheet text (dropped)' }],
      note: 'The participants were read from the factsheet by a language model. Every name was checked against the factsheet text; one that is not in it was dropped. Countries come from the factsheet\'s own table where it could be read without the model. The factsheet states no amount per participant.' } : null,
    readAt: p.edf ? SOURCES[1].readAt : SOURCES[0].readAt, amountNote: AMOUNT_NOTE,
  };
}

export function projectHistory(slug: string): ProjectHistory | null {
  const p = [...PROJECTS, NO_COORDINATOR].find((x) => x.slug === slug || slug.startsWith(`${x.id}-`));
  if (!p) return null;
  return {
    project: { slug: p.slug, acronym: p.acronym, title: p.title },
    firstObserved: { observedAt: '2026-09-01', memberCount: p.members.length - 1, countryCount: 2 },
    changes: [{ observedAt: '2026-10-01', added: [ref(p.members[p.members.length - 1][0])], removed: [], coordinatorBefore: ref(p.members[0][0]), coordinatorAfter: ref(p.members[0][0]) }],
    note: "A snapshot of each project's members is taken once a month; a change is recorded when a snapshot differs from the one before. A project with no change listed has had the same members since it was first observed.",
  };
}

export function ukrainePartners(since: number, programmes: string[] = [], q = ''): UkrainePartners {
  // The one invented Ukrainian project is an H2020 one: a filter that leaves it out leaves nothing, and says what it left out.
  // WP-99: a keyword keeps it when its acronym or title has the word (a plain fold, the API's synonyms aside)
  const p = PROJECTS[0];
  const matches = !q || q.toLowerCase().split(/\s+/).filter(Boolean).every((w) => `${p.acronym ?? ''} ${p.title}`.toLowerCase().includes(w));
  const shown = (programmes.length === 0 || programmes.includes('H2020')) && matches;
  return {
    since, programme: programmes, byProgramme: matches ? [{ code: 'H2020', projects: 1 }] : [], q: q ? q.toLowerCase().split(/\s+/).filter(Boolean) : null, alsoSearched: [],
    definition: 'A coordinator is the organisation that leads a funded project (the prime of its consortium). It is listed when a project it coordinated, started in or after the year given, had an active participant whose country of establishment, as the source states it, is Ukraine. Ukrainian coordinators are counted apart. This says who partnered with Ukrainian organisations, not who controls them or what they supplied.',
    order: 'Coordinators with projects of the defence programmes come first, then those with projects of the calls we label dual-use (Horizon Europe Cluster 3, the digital and space topics of Cluster 4, the EIC Accelerator and STEP, Horizon 2020 Secure Societies and Digital Security, FP7 Security), then the rest; within each, most projects first.',
    totals: shown ? { projects: 1, coordinators: 1, ukrainianOrganisations: 1, projectsCoordinatedFromUkraine: 0 } : { projects: 0, coordinators: 0, ukrainianOrganisations: 0, projectsCoordinatedFromUkraine: 0 },
    coordinators: shown ? [{ organisation: ref(A), projects: 1, ukrainianOrganisations: 1, lastYear: 2019, programmes: ['H2020'],
      ukrainianParticipants: [{ organisation: ref(C), projects: 1 }], recentProjects: [ref3(PROJECTS[0])] }] : [],
    ukrainianOrganisations: shown ? [{ organisation: ref(C), projects: 1, coordinated: 0, lastYear: 2019 }] : [],
    limits: ['Country is the country of establishment that CORDIS or the EDF factsheet states for the participant.'],
    sources: SOURCES,
  };
}

export function consortiumGaps(f: { programme: string; topic?: string; lacking: string }): ConsortiumGaps {
  return {
    programme: [f.programme], topic: f.topic ?? null, lacking: f.lacking, minProjects: 2, projectsInArea: 2,
    definition: `Capability area: the projects of the programme(s) named, narrowed by the topic you give. An organisation is listed when it took part in at least 2 projects of the area and no project of the area it took part in had a participant established in ${f.lacking}.`,
    items: [{ organisation: ref(B), projects: 2, partnerCountries: ['DE', 'ES'], recentProjects: [{ ...ref3(PROJECTS[2]), category: 'CYBER', countries: ['DE', 'ES', 'FR'] }] }],
    areas: [{ code: 'CYBER', projects: 2 }, { code: 'GROUND', projects: 2 }],
    limits: ['The EDF factsheets are read by a language model; a participant missed or misplaced would show a gap that is not there.'],
    sources: SOURCES,
  };
}

export const mockOrgSlugs = () => ORGS.map((o) => ({ slug: o.slug, updatedAt: '2026-10-17T21:30:00Z' }));
export const mockProjectSlugs = () => PROJECTS.filter((p) => p.edf).map((p) => ({ slug: p.slug, updatedAt: '2026-10-17T21:30:00Z' }));
