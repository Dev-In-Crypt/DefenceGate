import type { Metadata } from 'next';
import Link from 'next/link';
import { ApiError } from '@/lib/api';
import { getConsortiumGaps } from '@/lib/networks-api';
import { buildMetadata } from '@/lib/seo';
import { BUYER_COUNTRIES, countryName } from '@/lib/taxonomy';
import { EDF_CATEGORY_WORDS, GAP_PROGRAMMES } from '@/lib/networks';
import { Select } from '@/components/dg/form';
import { FilterNotices } from '@/components/dg/filter-notices';
import { ContentPage, ContentSection } from '@/components/dg/content-page';
import { EmptyState, ErrorState } from '@/components/dg/feedback';
import { DataSources, OrgLink, TableBox } from '@/components/networks/parts';
import { AboutData } from '@/components/dg/about-data';
import type { SearchParams } from '@/lib/filters';

export const revalidate = 900;
type Props = { searchParams: Promise<SearchParams> };

const COUNTRIES = Object.entries({ UA: 'Ukraine', LI: 'Liechtenstein', TR: 'Türkiye', US: 'United States', ...BUYER_COUNTRIES })
  .map(([value, label]) => ({ value, label: `${label} (${value})` })).sort((a, b) => a.label.localeCompare(b.label, 'en'));

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

/** Horizon programmes are too large to read whole: the API takes them with a topic code start only. */
const NEEDS_TOPIC = new Set(['HORIZON', 'H2020']);

function parse(sp: SearchParams) {
  // WP-116: a programme the form does not offer falls back to the EDF, as the select shows, and the page says so (it used to be
  // sent on and refused, with the reason "a topic that is too broad")
  const asked = (one(sp.programme) ?? '').trim();
  const known = GAP_PROGRAMMES.some((p) => p.value === asked.toUpperCase());
  const programme = known ? asked.toUpperCase() : 'EDF';
  const topic = (one(sp.topic) ?? '').trim().slice(0, 60);
  const lacking = /^[A-Za-z]{2}$/.test(one(sp.lacking) ?? '') ? (one(sp.lacking) as string).toUpperCase() : 'UA';
  return { programme, topic: topic || undefined, lacking, unknownProgramme: asked && !known ? asked.slice(0, 20) : null };
}

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const q = parse(await searchParams);
  return buildMetadata({
    title: 'Repeat participants lacking a partner country',
    description: 'Organisations funded at least twice in one European Defence Fund capability area that never had a partner from a chosen country, with the projects as evidence.',
    path: '/networks/consortium-gaps',
    noindex: q.programme !== 'EDF' || Boolean(q.topic) || q.lacking !== 'UA',
  });
}

export default async function ConsortiumGapsPage({ searchParams }: Props) {
  const { unknownProgramme, ...q } = parse(await searchParams);
  let data = null;
  let problem: string | null = null;
  try {
    data = await getConsortiumGaps(q);
  } catch (e) {
    // A refusal (4xx: a topic too broad, a Horizon programme without a topic) is an answer to the form; a service that did not
    // answer is thrown, so the page answers 503 at the edge and not 200 (re-audit N2), and ../error.tsx says so.
    if (!(e instanceof ApiError && e.status >= 400 && e.status < 500)) throw e;
    problem = NEEDS_TOPIC.has(q.programme) && !q.topic
      ? 'This analysis could not be loaded. A Horizon programme is read by topic: give a topic code start, for example HORIZON-CL3.'
      : 'This analysis could not be loaded. A topic that is too broad is refused: give a narrower topic.';
  }
  const notices = unknownProgramme ? [`Unknown programme ${unknownProgramme}: the European Defence Fund is shown.`] : [];
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Organisations', href: '/organisations' }, { label: 'Gaps in consortia', href: '/networks/consortium-gaps' }]}
      title="Consortium gaps"
      lead="Organisations funded at least twice in one capability area that never had a partner from the country you choose: a place to look for a partner the established consortia do not have."
      wide
    >
      <form method="get" action="/networks/consortium-gaps" aria-label="Choose the area and the country" className="flex flex-wrap items-end gap-3">
        <Select name="programme" label="Programme" options={GAP_PROGRAMMES} defaultValue={GAP_PROGRAMMES.some((p) => p.value === q.programme) ? q.programme : 'EDF'} className="w-64" />
        <label className="flex flex-col gap-1 text-label" htmlFor="topic">Capability category or topic code start
          <input id="topic" name="topic" defaultValue={q.topic ?? ''} maxLength={60} placeholder="For example CYBER" className="h-11 w-56 rounded-md border-strong border-input-edge bg-surface px-4 font-mono text-body text-ink" />
        </label>
        <Select name="lacking" label="With no participant from" options={COUNTRIES.some((c) => c.value === q.lacking) ? COUNTRIES : [...COUNTRIES, { value: q.lacking, label: `${countryName(q.lacking)} (${q.lacking})` }]} defaultValue={q.lacking} className="w-56"
          hint="Ukraine unless you choose another country." />
        <button type="submit" className="inline-flex min-h-11 items-center rounded-pill border-strong border-ink bg-surface px-5 text-small font-bold text-ink">Apply</button>
      </form>
      <FilterNotices notices={notices} />
      {problem && <ErrorState title={problem} retryHref="/networks/consortium-gaps" />}
      {data && (
        <>
          {/* WP-88: one result line and the category links stay; the definition and the limits are in How we count. */}
          <ContentSection title="Area and result">
            <p className="m-0 text-body">
              {data.projectsInArea} projects are in this area. {data.items.length} {data.items.length === 1 ? 'organisation was' : 'organisations were'} funded {data.minProjects} or more times in it
              with no participant from {countryName(data.lacking)}.
            </p>
            {data.areas.length > 0 && (
              <>
                <p className="m-0 text-small text-ink-muted">EDF capability categories, with the number of projects:</p>
                <ul className="m-0 flex list-none flex-wrap gap-x-5 gap-y-1 p-0 text-small">
                  {data.areas.map((a) => (
                    <li key={a.code}>
                      <Link href={`/networks/consortium-gaps?topic=${encodeURIComponent(a.code)}&lacking=${data.lacking}`} className="inline-flex min-h-12 items-center font-mono font-semibold">{a.code}</Link>
                      {EDF_CATEGORY_WORDS[a.code] ? <span> {EDF_CATEGORY_WORDS[a.code]}</span> : null} <span className="text-ink-muted">({a.projects})</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <AboutData summary="How we count">
              <h3 className="m-0 text-h4">What this counts</h3>
              <p className="m-0">{data.definition}</p>
              {data.areas.length > 0 && (
                <p className="m-0">The category codes are those of the Commission’s own file names; the words beside them are our plain reading of the abbreviation, and the EDF work programme is authoritative.</p>
              )}
              <h3 className="m-0 text-h4">Limits</h3>
              <ul className="m-0 list-disc pl-5 [&>li+li]:mt-1">{data.limits.map((l) => <li key={l}>{l}</li>)}</ul>
            </AboutData>
          </ContentSection>
          <ContentSection title="Organisations">
            {data.items.length === 0 ? <EmptyState title="Nobody matches">Try another category, or another country.</EmptyState> : (
              <TableBox label="Repeat participants with no partner from the chosen country">
                <table className="stack-sm w-full min-w-[640px] border-collapse text-left text-small">
                  <caption className="sr-only">Organisations funded repeatedly in the area, with no participant from {countryName(data.lacking)}</caption>
                  <thead>
                    <tr className="border-b border-line">
                      <th scope="col" className="py-2 pr-4 font-semibold">Organisation</th>
                      <th scope="col" className="py-2 pr-4 text-right font-semibold">Projects in the area</th>
                      <th scope="col" className="py-2 pr-4 font-semibold">Partner countries seen</th>
                      <th scope="col" className="py-2 font-semibold">Projects</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((i) => (
                      <tr key={i.organisation.id ?? i.organisation.name} className="border-b border-line align-top last:border-0">
                        <th scope="row" className="py-2 pr-4 font-normal"><OrgLink org={i.organisation} />{i.organisation.country ? <span className="text-ink-muted"> ({i.organisation.country})</span> : null}</th>
                        <td data-label="Projects in the area" className="py-2 pr-4 text-right font-mono tabular-nums">{i.projects}</td>
                        <td data-label="Partner countries seen" className="py-2 pr-4 font-mono">{i.partnerCountries.join(', ') || 'None'}</td>
                        <td data-label="Projects" className="py-2"><ul className="m-0 list-none p-0">{i.recentProjects.map((p) => <li key={p.slug}><Link href={`/projects/${p.slug}`}>{p.acronym ?? p.title}</Link> <span className="text-ink-muted">{p.year}</span></li>)}</ul></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableBox>
            )}
          </ContentSection>
          <DataSources sources={data.sources} />
        </>
      )}
    </ContentPage>
  );
}
