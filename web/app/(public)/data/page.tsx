import type { Metadata } from 'next';
import { getHealth } from '@/lib/api';
import { formatDateTimeUtc, formatNumber, formatPercent } from '@/lib/format';
import { safeHttpUrl } from '@/lib/safe-url';
import { buildMetadata } from '@/lib/seo';
import type { SourceHealth, SourceType } from '@/lib/types';
import { ContentPage, ContentSection } from '@/components/dg/content-page';
import { CountryLabel, FactCell } from '@/components/dg/data-display';
import { EmptyState } from '@/components/dg/feedback';
import { RunStatusPill } from '@/components/dg/tag';
import { Button } from '@/components/dg/button';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Source status',
  description: 'Every source DefenceGate collects from: when it last ran, whether the run was complete, its licence and attribution.',
  path: '/data',
});

const GROUPS: { type: SourceType; title: string }[] = [
  { type: 'grants', title: 'Funding sources' },
  { type: 'tenders', title: 'Tender sources' },
];

function SourceCard({ s }: { s: SourceHealth }) {
  const url = safeHttpUrl(s.url);
  return (
    <article className="flex min-w-0 flex-col gap-4 rounded-lg bg-surface p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="m-0 min-w-0 text-h3">{s.name}</h3>
        <RunStatusPill status={s.status} />
      </div>
      {s.country && <span className="text-small"><CountryLabel code={s.country} /></span>}
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-3">
        <FactCell label="Last run">
          {s.lastRunAt ? <time dateTime={s.lastRunAt}>{formatDateTimeUtc(s.lastRunAt)}</time> : <span className="font-sans">Never</span>}
        </FactCell>
        <FactCell label="Records in last run">{s.lastRunAt ? formatNumber(s.records) : <span className="font-sans">None</span>}</FactCell>
        <FactCell label="Coverage">
          {s.coverage === null ? <span className="font-sans">Not measured</span> : formatPercent(s.coverage)}
        </FactCell>
      </dl>
      <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 rounded-md bg-surface-inset p-4 font-mono text-[12px] leading-[18px]">
        <dt className="text-ink-muted">Licence</dt><dd className="m-0 break-words text-ink">{s.licence}</dd>
        <dt className="text-ink-muted">Attribution</dt><dd className="m-0 break-words text-ink">{s.attribution}</dd>
      </dl>
      {url && <Button href={url} external variant="text" className="self-start">Open {s.name}<span className="sr-only"> (opens in new tab)</span></Button>}
    </article>
  );
}

export default async function DataPage() {
  const health = await getHealth();
  const count = (st: SourceHealth['status']) => health.sources.filter((s) => s.status === st).length;
  return (
    <ContentPage
      wide
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Source status', href: '/data' }]}
      title="Source status"
      lead="Every source we collect from, when it last ran and how complete that run was. A source that failed or has never run is shown as such."
    >
      <dl className="m-0 grid grid-cols-2 gap-3 rounded-lg bg-surface p-4 lg:grid-cols-4">
        <FactCell label="Sources">{health.sources.length}</FactCell>
        <FactCell label="Last run OK">{count('ok')}</FactCell>
        <FactCell label="Partial, failed or never run">{count('partial') + count('failed') + count('never')}</FactCell>
        <FactCell label="Status as of"><time dateTime={health.generatedAt}>{formatDateTimeUtc(health.generatedAt)}</time></FactCell>
      </dl>

      {health.sources.length === 0 ? (
        <EmptyState title="No sources reported">The source list is empty. Check back later.</EmptyState>
      ) : (
        GROUPS.map((g) => {
          const items = health.sources.filter((s) => s.type === g.type);
          if (items.length === 0) return null;
          const id = `group-${g.type}`;
          return (
            <section key={g.type} aria-labelledby={id} className="flex flex-col gap-4">
              <h2 id={id} className="m-0 text-h2">{g.title}</h2>
              <ul className="m-0 grid list-none gap-4 p-0 md:grid-cols-2">
                {items.map((s) => <li key={s.id} className="min-w-0"><SourceCard s={s} /></li>)}
              </ul>
            </section>
          );
        })
      )}

      <ContentSection title="What is and is not covered">
        <p className="m-0 text-body text-ink-muted">
          We cover the sources listed above and nothing else. A source that is not listed is not collected, and a listed source may publish more than we have collected.
        </p>
        <p className="m-0 text-body text-ink-muted">
          Coverage compares what a run fetched with the minimum we expected from that source. It is not a share of everything the source publishes. Where we have set no minimum, coverage is not measured.
        </p>
        <p className="m-0 text-body text-ink-muted">
          Amounts are shown in the currency the source states and are never converted. All times are UTC.
        </p>
      </ContentSection>
    </ContentPage>
  );
}
