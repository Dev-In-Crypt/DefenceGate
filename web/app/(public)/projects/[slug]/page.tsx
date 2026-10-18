import type { Metadata } from 'next';
import { notFound, permanentRedirect } from 'next/navigation';
import { formatDateUtc } from '@/lib/format';
import { formatEur, isNetworkSlug, roleWord } from '@/lib/networks';
import { getProject, getProjectHistory } from '@/lib/networks-api';
import { buildMetadata } from '@/lib/seo';
import { CountryLabel, FactCell } from '@/components/dg/data-display';
import { PageHeader } from '@/components/dg/page-header';
import { Card } from '@/components/dg/card';
import { FactsGrid } from '@/components/dg/facts-grid';
import { Tag } from '@/components/dg/tag';
import { ConsortiumTable, DataSources, OrgLink, SourceLink } from '@/components/networks/parts';

export const revalidate = 300;
type Props = { params: Promise<{ slug: string }> };

const day = (iso: string | null) => (iso ? <time dateTime={iso}>{formatDateUtc(iso)}</time> : <span className="font-sans">Not stated</span>);

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const p = isNetworkSlug(slug) ? await getProject(slug).catch(() => null) : null;
  if (!p) return { title: 'Project not found', robots: { index: false } };
  const label = p.acronym ?? p.title;
  return buildMetadata({
    title: `${label}: consortium and EU funding`,
    description: `${label}${p.acronym ? `: ${p.title}` : ''}. ${p.memberCount} participants from ${p.countryCount} countries${p.programme ? `, ${p.programme.name}` : ''}${p.callYear ? `, ${p.callYear}` : ''}. From ${p.source.name}.`.slice(0, 300),
    path: `/projects/${p.slug}`,
  });
}

export default async function ProjectPage({ params }: Props) {
  const { slug } = await params;
  if (!isNetworkSlug(slug)) notFound();
  const p = await getProject(slug);
  if (!p) notFound();
  if (p.slug !== slug && isNetworkSlug(p.slug)) permanentRedirect(`/projects/${p.slug}`);
  const history = await getProjectHistory(p.slug).catch(() => null);
  const label = p.acronym ?? p.title;
  const edf = p.source.code === 'edf_factsheets';
  const sourceNote = {
    code: p.source.code, name: p.source.name, licence: p.source.licence, attribution: p.source.attribution, readAt: p.readAt,
    note: edf ? 'The participants were read from the project factsheet by a language model (see "How the participants were read" below).' : "Participants and amounts as the Commission's CORDIS database states them.",
  };

  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Home', href: '/' }, { label: 'Organisations', href: '/organisations' }, { label, href: `/projects/${p.slug}` }]}
        eyebrow={(
          <p className="m-0 flex flex-wrap gap-2">
            {p.programme && <Tag kind="programme">{p.programme.code}</Tag>}
            {p.category && <Tag>{p.category}</Tag>}
          </p>
        )}
        title={label}
      >
        {p.acronym && <p className="m-0 max-w-prose text-body text-ink-muted">{p.title}</p>}
        <FactsGrid>
          <FactCell label="Programme"><span className="font-sans">{p.programme?.name ?? 'Not stated'}</span></FactCell>
          <FactCell label={edf ? 'Call year' : 'Started'}>{edf ? (p.callYear ?? 'Not stated') : day(p.startDate)}</FactCell>
          {!edf && <FactCell label="Ends">{day(p.endDate)}</FactCell>}
          {p.durationMonths !== null && <FactCell label="Duration">{p.durationMonths} months</FactCell>}
          <FactCell label="Total cost">{p.totalCost === null ? <span className="font-sans">Not stated</span> : formatEur(p.totalCost)}</FactCell>
          <FactCell label="EU contribution">{p.euContribution === null ? <span className="font-sans">Not stated</span> : formatEur(p.euContribution)}</FactCell>
          <FactCell label="Participants"><span className="tabular-nums">{p.memberCount}</span> <span className="font-sans text-ink-muted">from {p.countryCount} countries</span></FactCell>
          {p.topic && <FactCell label="Topic">{p.topic}</FactCell>}
          {p.grantNumber && <FactCell label="Grant agreement">{p.grantNumber}</FactCell>}
        </FactsGrid>
        {p.coordinator && (
          <p className="m-0 text-body">
            Coordinated by <OrgLink org={p.coordinator} />{p.coordinator.country ? <> (<CountryLabel code={p.coordinator.country} />)</> : null}.
          </p>
        )}
      </PageHeader>

      <Card title="Consortium" id="consortium">
        <p className="m-0 text-small text-ink-muted">
          {edf ? 'The factsheet states no amount per participant.' : 'EU contribution per participant as the open data of CORDIS states it; for a participant with linked third parties it may include their share, and a participant whose amount the data does not hold or cannot make consistent shows Not stated.'} A participant who left the project is not listed; see the history below.
        </p>
        <ConsortiumTable members={p.members} />
      </Card>

      {p.factsheet && (
        <Card title="How the participants were read" id="read">
          <p className="m-0 text-body">{p.factsheet.note}</p>
          <p className="m-0 text-small text-ink-muted">Read on <time dateTime={p.factsheet.readAt}>{formatDateUtc(p.factsheet.readAt)}</time> from {p.factsheet.pages} pages.</p>
          {p.factsheet.dropped.length > 0 ? (
            <>
              <p className="m-0 text-small font-semibold">What the checks removed or corrected for this factsheet:</p>
              <ul className="m-0 pl-5 text-small">{p.factsheet.dropped.map((d) => <li key={d.kind}>{d.count}: {d.meaning}</li>)}</ul>
            </>
          ) : <p className="m-0 text-small text-ink-muted">The checks removed or corrected nothing for this factsheet.</p>}
        </Card>
      )}

      <Card title="Changes of the consortium" id="history">
        {history ? (
          <>
            {history.firstObserved
              ? <p className="m-0">First seen on <time dateTime={history.firstObserved.observedAt}>{formatDateUtc(history.firstObserved.observedAt)}</time> with {history.firstObserved.memberCount} participants from {history.firstObserved.countryCount} countries.</p>
              : <p className="m-0 text-ink-muted">No monthly snapshot of this consortium has been taken yet.</p>}
            {history.changes.length > 0 && (
              <ul className="m-0 flex list-none flex-col gap-3 p-0">
                {history.changes.map((c) => (
                  <li key={c.observedAt} className="flex flex-col gap-1">
                    <span className="font-semibold"><time dateTime={c.observedAt}>{formatDateUtc(c.observedAt)}</time></span>
                    {c.added.length > 0 && <span>Joined: {c.added.map((o, i) => <span key={o.id ?? i}>{i > 0 ? ', ' : ''}<OrgLink org={o} /></span>)}</span>}
                    {c.removed.length > 0 && <span>Left: {c.removed.map((o, i) => <span key={o.id ?? i}>{i > 0 ? ', ' : ''}<OrgLink org={o} /></span>)}</span>}
                    {c.coordinatorBefore && c.coordinatorAfter && c.coordinatorBefore.id !== c.coordinatorAfter.id && (
                      <span>{roleWord('coordinator')} changed from <OrgLink org={c.coordinatorBefore} /> to <OrgLink org={c.coordinatorAfter} />.</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <p className="m-0 text-small text-ink-muted">{history.note}</p>
          </>
        ) : <p className="m-0 text-ink-muted">The history could not be loaded.</p>}
      </Card>

      <p className="m-0"><SourceLink url={p.source.url} label={p.source.urlLabel} /></p>
      <DataSources sources={[sourceNote]} amountNote={p.amountNote} />
    </>
  );
}
