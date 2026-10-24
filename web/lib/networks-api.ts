/**
 * The server-side reads of the networks pages (organisations, projects, partners, the two analytics). Same rule as
 * lib/api.ts: with DG_API_URL set they call the API; unset, the site serves the small invented set in lib/mock/networks.ts
 * (development and the CI run only; a production build without the API refuses to start, see lib/api.ts).
 * A request shaped by the visitor goes uncached; the default directory and a profile are cached like the other detail pages.
 */
import { DETAIL_REVALIDATE_SECONDS, LIST_REVALIDATE_SECONDS, REVALIDATE_SECONDS, http, httpOrThrow, withLastGood } from './api';
import * as mock from './mock/networks';
import { effectiveProgrammes, orgApiQuery, toOrgQuery } from './networks';
import type {
  ConsortiumGaps, OrgFilters, OrgFunding, OrgPage, OrgProfile, OrgProjectPage, PartnerPage, ProjectDetail, ProjectHistory, UkrainePartners,
} from './networks-types';

const API_BASE = process.env.DG_API_URL;
const enc = encodeURIComponent;

/** The directory. Only the unfiltered first page is shared; anything built from the URL is read live. */
export async function getOrganisations(f: OrgFilters): Promise<OrgPage & { staleAsOf?: string }> {
  if (!API_BASE) return mock.queryOrgs({ ...f, programme: effectiveProgrammes(f) });
  const shared = toOrgQuery({ ...f, page: 1 }) === '' && (f.page ?? 1) === 1;
  const path = `/v1/organisations${orgApiQuery(f)}`;
  // The last good answer when the service does not answer (re-audit of 20 Oct, N2: /organisations?page=2 served its error state).
  return withLastGood(`organisations:${path}`, () => httpOrThrow<OrgPage>(path, shared ? 'revalidate' : 'no-store', LIST_REVALIDATE_SECONDS), { persist: shared });
}

export async function getOrganisation(slug: string): Promise<OrgProfile | null> {
  if (!API_BASE) return mock.orgProfile(slug);
  return http<OrgProfile>(`/v1/organisations/${enc(slug)}`, 'revalidate', DETAIL_REVALIDATE_SECONDS);
}

export async function getOrganisationFunding(slug: string): Promise<OrgFunding | null> {
  if (!API_BASE) return mock.orgFunding(slug);
  return http<OrgFunding>(`/v1/organisations/${enc(slug)}/funding`, 'revalidate', DETAIL_REVALIDATE_SECONDS);
}

export async function getPartners(slug: string, f: { country?: string; programme?: string; page: number; pageSize: number }): Promise<PartnerPage | null> {
  if (!API_BASE) return mock.orgPartners(slug, f);
  const p = new URLSearchParams({ page: String(f.page), pageSize: String(f.pageSize) });
  if (f.country) p.set('country', f.country);
  if (f.programme) p.set('programme', f.programme);
  const plain = !f.country && !f.programme && f.page === 1;
  return http<PartnerPage>(`/v1/organisations/${enc(slug)}/partners?${p}`, plain ? 'revalidate' : 'no-store', DETAIL_REVALIDATE_SECONDS);
}

export async function getOrganisationProjects(slug: string, f: { programme?: string; page: number; pageSize: number }): Promise<OrgProjectPage | null> {
  if (!API_BASE) return mock.orgProjects(slug, f);
  const p = new URLSearchParams({ page: String(f.page), pageSize: String(f.pageSize) });
  if (f.programme) p.set('programme', f.programme);
  const plain = !f.programme && f.page === 1;
  return http<OrgProjectPage>(`/v1/organisations/${enc(slug)}/projects?${p}`, plain ? 'revalidate' : 'no-store', DETAIL_REVALIDATE_SECONDS);
}

export async function getProject(slug: string): Promise<ProjectDetail | null> {
  if (!API_BASE) return mock.projectDetail(slug);
  return http<ProjectDetail>(`/v1/projects/${enc(slug)}`, 'revalidate', DETAIL_REVALIDATE_SECONDS);
}

export async function getProjectHistory(slug: string): Promise<ProjectHistory | null> {
  if (!API_BASE) return mock.projectHistory(slug);
  return http<ProjectHistory>(`/v1/projects/${enc(slug)}/history`, 'revalidate', DETAIL_REVALIDATE_SECONDS);
}

/** `programmes`: the programme codes to count (empty: all of them). */
export async function getUkrainePartners(since: number, programmes: string[] = [], q = ''): Promise<UkrainePartners> {
  if (!API_BASE) return mock.ukrainePartners(since, programmes, q);
  const p = new URLSearchParams({ since: String(since) });
  if (programmes.length) p.set('programme', programmes.join(','));
  if (q) p.set('q', q);
  return httpOrThrow<UkrainePartners>(`/v1/analytics/ukraine-partners?${p}`, 'no-store', LIST_REVALIDATE_SECONDS);
}

export async function getConsortiumGaps(f: { programme: string; topic?: string; lacking: string }): Promise<ConsortiumGaps | null> {
  if (!API_BASE) return mock.consortiumGaps(f);
  const p = new URLSearchParams({ programme: f.programme, lacking: f.lacking });
  if (f.topic) p.set('topic', f.topic);
  return http<ConsortiumGaps>(`/v1/analytics/consortium-gaps?${p}`, 'no-store', LIST_REVALIDATE_SECONDS);
}

/** For the sitemap: the organisations with the most projects, and the EDF projects. */
export async function getNetworkSlugs(): Promise<{ slug: string; updatedAt: string }[][]> {
  if (!API_BASE) return [mock.mockOrgSlugs(), mock.mockProjectSlugs()];
  return Promise.all([
    httpOrThrow<{ slug: string; updatedAt: string }[]>('/v1/organisations/slugs', 'revalidate', REVALIDATE_SECONDS),
    httpOrThrow<{ slug: string; updatedAt: string }[]>('/v1/projects/slugs', 'revalidate', REVALIDATE_SECONDS),
  ]);
}
