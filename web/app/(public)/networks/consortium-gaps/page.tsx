import type { Metadata } from 'next';
import Link from 'next/link';
import { getConsortiumGaps } from '@/lib/networks-api';
import { buildMetadata } from '@/lib/seo';
import { countryName } from '@/lib/taxonomy';
import { ContentPage, ContentSection } from '@/components/dg/content-page';
import { EmptyState, ErrorState } from '@/components/dg/feedback';
import { DataSources, OrgLink, TableBox } from '@/components/networks/parts';
import type { SearchParams } from '@/lib/filters';

export const revalidate = 900;
type Props = { searchParams: Promise<SearchParams> };

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

function parse(sp: SearchParams) {
  const programme = /^[A-Za-z0-9_-]{1,20}$/.test(one(sp.programme) ?? '') ? (one(sp.programme) as string).toUpperCase() : 'EDF';
  const topic = (one(sp.topic) ?? '').trim().slice(0, 60);
  const lacking = /^[A-Za-z]{2}$/.test(one(sp.lacking) ?? '') ? (one(sp.lacking) as string).toUpperCase() : 'UA';
  return { programme, topic: topic || undefined, lacking };
}

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const q = parse(await searchParams);
  return buildMetadata({
    title: 'Repeat participants of a capability area with no partner from one country',
    description: 'Organisations funded at least twice in a European Defence Fund capability area whose projects never had a participant from a chosen country, with the projects as evidence.',
    path: '/networks/consortium-gaps',
    noindex: q.programme !== 'EDF' || Boolean(q.topic) || q.lacking !== 'UA',
  });
}

export default async function ConsortiumGapsPage({ searchParams }: Props) {
  const q = parse(await searchParams);
  let data = null;
  let problem: string | null = null;
  try { data = await getConsortiumGaps(q); } catch { problem = 'This analysis could not be loaded. A topic that is too broad is refused: give a narrower topic.'; }
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Organisations', href: '/organisations' }, { label: 'Gaps in consortia', href: '/networks/consortium-gaps' }]}
      title="Gaps in consortia"
      lead="Organisations that were funded at least twice in the same capability area and never had a participant established in a chosen country. A starting point for finding a partner the established consortia do not yet have."
      wide
    >
      <form method="get" action="/networks/consortium-gaps" aria-label="Choose the area and the country" className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-label" htmlFor="programme">Programme
          <input id="programme" name="programme" defaultValue={q.programme} maxLength={20} className="h-11 w-32 rounded-md border-strong border-line bg-surface px-4 font-mono text-body text-ink" />
        </label>
        <label className="flex flex-col gap-1 text-label" htmlFor="topic">Capability category or topic code start
          <input id="topic" name="topic" defaultValue={q.topic ?? ''} maxLength={60} placeholder="For example CYBER" className="h-11 w-56 rounded-md border-strong border-line bg-surface px-4 font-mono text-body text-ink" />
        </label>
        <label className="flex flex-col gap-1 text-label" htmlFor="lacking">With no participant from (ISO code)
          <input id="lacking" name="lacking" defaultValue={q.lacking} maxLength={2} className="h-11 w-24 rounded-md border-strong border-line bg-surface px-4 font-mono text-body uppercase text-ink" />
        </label>
        <button type="submit" className="inline-flex min-h-11 items-center rounded-pill border-strong border-ink bg-surface px-5 text-small font-bold text-ink">Apply</button>
      </form>
      {problem && <ErrorState title={problem} retryHref="/networks/consortium-gaps" />}
      {data && (
        <>
          <ContentSection title="What this counts">
            <p className="m-0 text-body">{data.definition}</p>
            <p className="m-0 text-body">
              {data.projectsInArea} projects are in this area. {data.items.length} {data.items.length === 1 ? 'organisation was' : 'organisations were'} funded {data.minProjects} or more times in it
              with no participant from {countryName(data.lacking)}.
            </p>
            {data.areas.length > 0 && (
              <p className="m-0 text-small text-ink-muted">
                EDF capability categories in the data:{' '}
                {data.areas.map((a, i) => <span key={a.code}>{i > 0 ? ', ' : ''}<Link href={`/networks/consortium-gaps?topic=${encodeURIComponent(a.code)}&lacking=${data.lacking}`}>{a.code}</Link> ({a.projects})</span>)}.
              </p>
            )}
          </ContentSection>
          <ContentSection title="Organisations">
            {data.items.length === 0 ? <EmptyState title="Nobody matches">Try another category, or another country.</EmptyState> : (
              <TableBox label="Repeat participants with no partner from the chosen country">
                <table className="w-full min-w-[640px] border-collapse text-left text-small">
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
                        <td className="py-2 pr-4 text-right font-mono tabular-nums">{i.projects}</td>
                        <td className="py-2 pr-4 font-mono">{i.partnerCountries.join(', ') || 'None'}</td>
                        <td className="py-2"><ul className="m-0 list-none p-0">{i.recentProjects.map((p) => <li key={p.slug}><Link href={`/projects/${p.slug}`}>{p.acronym ?? p.title}</Link> <span className="text-ink-muted">{p.year}</span></li>)}</ul></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableBox>
            )}
          </ContentSection>
          <ContentSection title="Limits">
            <ul className="m-0 pl-5 text-small">{data.limits.map((l) => <li key={l}>{l}</li>)}</ul>
          </ContentSection>
          <DataSources sources={data.sources} />
        </>
      )}
    </ContentPage>
  );
}
