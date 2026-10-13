import type { Metadata } from 'next';
import { getHealth } from '@/lib/api';
import { now } from '@/lib/deadline';
import { formatDateTimeUtc, formatNumber } from '@/lib/format';
import { safeHttpUrl } from '@/lib/safe-url';
import { buildMetadata } from '@/lib/seo';
import { heldSpan, minimumMet, sourceFreshness, STALE_AFTER_DAYS, type FreshnessKind } from '@/lib/source-status';
import type { SourceHealth, SourceType } from '@/lib/types';
import { ContentPage, ContentSection } from '@/components/dg/content-page';
import { CountryLabel, FactCell } from '@/components/dg/data-display';
import { EmptyState } from '@/components/dg/feedback';
import { RunStatusPill } from '@/components/dg/tag';
import { Button } from '@/components/dg/button';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Source status',
  description: 'Every source DefenceGate collects from: when it last ran, whether the run met the minimum we expect, its licence and attribution.',
  path: '/data',
});

const GROUPS: { type: SourceType; title: string }[] = [
  { type: 'grants', title: 'Funding sources' },
  { type: 'tenders', title: 'Tender sources' },
];

function SourceCard({ s, asOf }: { s: SourceHealth; asOf: Date }) {
  const url = safeHttpUrl(s.url);
  const fresh = sourceFreshness(s, asOf);
  const held = typeof s.heldCount === 'number';
  const span = heldSpan(s.heldFrom, s.heldTo);
  const noun = s.type === 'grants' ? 'Calls' : 'Notices';
  return (
    <article className="flex min-w-0 flex-col gap-4 rounded-lg bg-surface p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="m-0 min-w-0 text-h3">{s.name}</h3>
        <RunStatusPill status={fresh.kind} />
      </div>
      {s.country && <span className="text-small"><CountryLabel code={s.country} /></span>}
      {fresh.note && <p className="m-0 text-small font-semibold">{fresh.note}</p>}
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-3">
        <FactCell label="Last run">
          {s.lastRunAt ? <time dateTime={s.lastRunAt}>{formatDateTimeUtc(s.lastRunAt)}</time> : <span className="font-sans">Never</span>}
        </FactCell>
        <FactCell label="Records in last run">{s.lastRunAt ? formatNumber(s.records) : <span className="font-sans">None</span>}</FactCell>
        <FactCell label="Met expected minimum"><span className="font-sans">{minimumMet(s.coverage)}</span></FactCell>
      </dl>
      {held && (
        <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-3">
          <FactCell label="Publication dates held">
            {span ? <span>{span}</span> : <span className="font-sans">Not stated by the source</span>}
          </FactCell>
          <FactCell label={`${noun} held`}>{formatNumber(s.heldCount ?? 0)}</FactCell>
        </dl>
      )}
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
  const ref = now();
  const kinds = health.sources.map((s) => sourceFreshness(s, ref).kind);
  const count = (...k: FreshnessKind[]) => kinds.filter((x) => k.includes(x)).length;
  return (
    <ContentPage
      wide
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Source status', href: '/data' }]}
      title="Source status"
      lead="Every source we collect from and when it last ran. Met expected minimum compares what a run fetched with the minimum we expect from that source; it is not a share of everything the source publishes."
    >
      <p className="m-0 max-w-[860px] text-body text-ink-muted">
        <span className="font-semibold text-ink">What OK means:</span> the last run finished and fetched at least that minimum, and it was within the last {STALE_AFTER_DAYS} days.
        It does not mean the source is fully collected. A run older than that is shown as stale, a load made once as a one-off load, and a source that failed or has never run as such.
      </p>

      <dl className="m-0 grid grid-cols-2 gap-3 rounded-lg bg-surface p-4 lg:grid-cols-3">
        <FactCell label="Sources">{health.sources.length}</FactCell>
        <FactCell label="OK and current">{count('ok')}</FactCell>
        <FactCell label="Stale (last run over 3 days ago)">{count('stale')}</FactCell>
        <FactCell label="One-off loads">{count('one-off')}</FactCell>
        <FactCell label="Partial, failed or never run">{count('partial', 'failed', 'never')}</FactCell>
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
                {items.map((s) => <li key={s.id} className="min-w-0"><SourceCard s={s} asOf={ref} /></li>)}
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
          Publication dates held are the earliest and latest date the source gives for what we hold, so a source that starts late shows it; they are not the span of everything the source has published.
          Where we have set no minimum, it is not measured. Amounts are shown in the currency the source states and are never converted. All times are UTC.
        </p>
      </ContentSection>
    </ContentPage>
  );
}
