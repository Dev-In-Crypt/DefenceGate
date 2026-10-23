import type { Metadata } from 'next';
import { getHealth } from '@/lib/api';
import { now } from '@/lib/deadline';
import { formatDateTimeUtc, formatNumber } from '@/lib/format';
import { safeHttpUrl } from '@/lib/safe-url';
import { buildMetadata } from '@/lib/seo';
import { gapSentence, heldSpan, lateRuleSentence, minimumMet, sourceFreshness, sourcePage, statusReasonLine, STALE_AFTER_DAYS, type FreshnessKind } from '@/lib/source-status';
import { portalWords } from '@/lib/coverage-copy';
import Link from 'next/link';
import type { SourceHealth, SourceType } from '@/lib/types';
import { ClauseList } from '@/components/dg/blocks';
import { AutoGrid } from '@/components/dg/auto-grid';
import { ContentPage, PageSection } from '@/components/dg/content-page';
import { Card } from '@/components/dg/card';
import { CountryLabel, FactCell } from '@/components/dg/data-display';
import { EmptyState } from '@/components/dg/feedback';
import { RunStatusPill } from '@/components/dg/tag';
import { Button } from '@/components/dg/button';

export const revalidate = 60;

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
  const url = safeHttpUrl(sourcePage(s.id, s.url));
  const fresh = sourceFreshness(s, asOf);
  const reason = statusReasonLine(s);
  const held = typeof s.heldCount === 'number';
  const span = heldSpan(s.heldFrom, s.heldTo);
  const noun = s.type === 'grants' ? 'Calls' : 'Notices';
  return (
    // One surface: the facts are hairline rows on the card (no inset box inside it, no card inside a card).
    <Card as="article" className="h-full">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="m-0 min-w-0 text-h3">{s.name}</h3>
        <RunStatusPill status={fresh.kind} />
      </div>
      {s.country && <span className="text-small"><CountryLabel code={s.country} /></span>}
      {fresh.note && <p className="m-0 text-small font-semibold">{fresh.note}</p>}
      {reason && <p className="m-0 text-small font-semibold">{reason}</p>}
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(8.5rem,1fr))] gap-x-4 border-b border-line">
        <FactCell label="Last run" className="py-2">
          {s.lastRunAt ? <time dateTime={s.lastRunAt}>{formatDateTimeUtc(s.lastRunAt)}</time> : <span className="font-sans">Never</span>}
        </FactCell>
        <FactCell label="Records in last run" className="py-2">{s.lastRunAt ? formatNumber(s.records) : <span className="font-sans">None</span>}</FactCell>
        <FactCell label="Met expected minimum" className="py-2"><span className="font-sans">{minimumMet(s.coverage)}</span></FactCell>
        {held && (
          <>
            <FactCell label="Publication dates held" className="py-2">
              {span ? <span>{span}</span> : <span className="font-sans">Not stated by the source</span>}
            </FactCell>
            <FactCell label={`${noun} held`} className="py-2">{formatNumber(s.heldCount ?? 0)}</FactCell>
          </>
        )}
        <FactCell label="Licence" className="col-span-full py-2"><span className="font-sans text-body">{s.licence}</span></FactCell>
        <FactCell label="Attribution" className="col-span-full py-2"><span className="font-sans text-body">{s.attribution}</span></FactCell>
      </dl>
      {url && <Button href={url} external variant="text" className="self-start">Open {s.name}<span className="sr-only"> (opens in new tab)</span></Button>}
    </Card>
  );
}

export default async function DataPage() {
  const health = await getHealth();
  const ref = now();
  const kinds = health.sources.map((s) => sourceFreshness(s, ref).kind);
  const lateRule = lateRuleSentence(health.sources);
  const portals = portalWords(health.sources);
  const germany = health.sources.find((s) => s.id === 'de_bkms');
  const count = (...k: FreshnessKind[]) => kinds.filter((x) => k.includes(x)).length;
  return (
    <ContentPage
      wide
      toc
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Source status', href: '/data' }]}
      title="Source status"
      lead="Every source we collect from and when it last ran. Met expected minimum compares what a run fetched with the minimum we expect from that source; it is not a share of everything the source publishes."
    >
      <p className="m-0 max-w-prose text-body text-ink-muted">
        <span className="font-semibold text-ink">What OK means:</span> the last run finished and fetched at least that minimum, and it was not late for how often that source is collected
        ({lateRule ? `a run is late for ${lateRule}` : `a run is late after ${STALE_AFTER_DAYS} days`}). It does not mean the source is fully collected. A late run is shown as stale, a load made once as a one-off load,
        and a source that failed or has never run as such. A run that finished with a problem is partial, and its card says why, also when it fetched the minimum.
      </p>

      <dl className="facts-grid m-0 border-b border-line">
        <FactCell label="Sources">{health.sources.length}</FactCell>
        <FactCell label="OK (run on time)">{count('ok', 'ok-incremental')}</FactCell>
        <FactCell label="Stale (run late)">{count('stale')}</FactCell>
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
            <PageSection key={g.type} id={id} title={g.title}>
              <AutoGrid as="ul" min={440} pairs>
                {items.map((s) => <li key={s.id} className="min-w-0"><SourceCard s={s} asOf={ref} /></li>)}
              </AutoGrid>
            </PageSection>
          );
        })
      )}

      <PageSection title="Known gaps">
        <p className="m-0 text-body text-ink-muted">
          The per-source lines are worked out from what we hold on <time dateTime={health.generatedAt}>{formatDateTimeUtc(health.generatedAt)}</time>, month by month,
          and change as the history loads. The first and the last month of a source are left out (they are partial). The rest do not change with the date.
        </p>
        <ClauseList items={[
          `National tender portals and feeds are collected for ${portals.count} countries: ${portals.names}. For every other country, Italy and the Nordic and Baltic countries among them, we hold only what TED carries.`,
          germany
            ? `Germany: the federal notice service (Bekanntmachungsservice, published as open data under CC0) is collected every day${typeof germany.heldCount === 'number' ? ` and we hold ${formatNumber(germany.heldCount)} of its notices` : ''}. It starts on 25 October 2023, when German notices moved to eForms: older German notices are here only if TED carries them, and so is anything published only on a state or municipal portal.`
            : 'Germany: we hold only what TED carries.',
          'TED: notices from April 2024 on have been re-checked with the current classification rules; the older ones (back to 2017) are being re-checked now, so until that finishes an older notice may be mislabelled or missing.',
          'Poland (Atlas): a one-off research dataset, not a live portal. It stops where its dates stop, and the national counts fall there.',
          'Germany: federal funding announcements are not collected automatically. They can be added by hand, so a German call may be missing.',
          ...health.sources.filter((s) => s.type === 'tenders').map((s) => gapSentence(s)).filter((t): t is string => t !== null),
        ]} />
      </PageSection>

      <PageSection title="Using the data">
        <ClauseList items={[
          'CSV: the Download CSV button under the filters of Tenders and of Funding gives the public fields of the current result, with the source, licence and attribution on every row. A tenders file holds at most 2,000 rows (1,000 when the status is All); a result cut at the limit holds the most recently added notices in the order you chose, and every row then says result_truncated = true. The last column of a tenders file, confidence, is the notice’s level (high, medium or low; see Methodology, “How sure are we”).',
          'Atom: What changed has a feed (/changes.atom) of the same list, with the same country and scope choices. No account is needed.',
          'Atom: the weekly digest has a feed (/digest.atom), one entry per week with the counts and the first headlines; a country can be added (/digest.atom?country=ES). Each week is also a page (/digest/2026-W41), and an issue does not change once its week has ended.',
          'Calendar: the deadlines of open tenders and funding calls as an .ics feed (/calendar.ics), for your calendar program.',
          'API: the site reads a JSON interface that is not documented and not supported for use by others; the terms say what automated use is allowed.',
        ]} />
        <p className="m-0 text-body text-ink-muted">
          <span className="font-semibold text-ink">Licence of what we add.</span> The notices and calls keep the licence of the source that published them, listed on each source above; where it allows, you may take them from the source itself. What we add
          (the selection and arrangement, the normalisation, the defence label and the links between sources, the version archive and our texts) is ours, all rights reserved; the{' '}
          <Link href="/terms" className="font-semibold">terms</Link> let you use extracts for your own internal business purposes and say what is not allowed. If you cite a number or a notice, name DefenceGate, the source of the notice and the date you read it.
        </p>
      </PageSection>

      <PageSection title="What is and is not covered">
        <p className="m-0 text-body text-ink-muted">
          We cover the sources listed above and nothing else. A source that is not listed is not collected, and a listed source may publish more than we have collected.
        </p>
        <p className="m-0 text-body text-ink-muted">
          Publication dates held are the earliest and latest date the source gives for what we hold, so a source that starts late shows it; they are not the span of everything the source has published.
          Where we have set no minimum, it is not measured. Amounts are shown in the currency the source states and are never converted. All times are UTC.
        </p>
      </PageSection>
    </ContentPage>
  );
}
