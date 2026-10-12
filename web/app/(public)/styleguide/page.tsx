import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { ArrowRight, Bell } from 'lucide-react';
import { getCalls, now } from '@/lib/api';
import { getDeadline, SOON_DAYS, URGENT_DAYS } from '@/lib/deadline';
import { cn } from '@/lib/utils';
import type { Call, DeadlineState, Opportunity, OpportunityVersion, StatusKind } from '@/lib/types';
import { Logo, LogoMark } from '@/components/dg/logo';
import { Button } from '@/components/dg/button';
import { Tag, StatusPill } from '@/components/dg/tag';
import { DeadlineBadge } from '@/components/dg/deadline-badge';
import { CallCard, TenderCard } from '@/components/dg/cards';
import { SourceBadge } from '@/components/dg/source-badge';
import { VersionTimeline } from '@/components/dg/version-timeline';
import { AmountDisplay, CountryLabel, FactCell } from '@/components/dg/data-display';
import { Breadcrumbs, CallCardSkeleton, ComingSoon, EmptyState, ErrorState, LockedFeature } from '@/components/dg/feedback';
import { Pagination } from '@/components/dg/pagination';
import { Choice, Select, TextInput } from '@/components/dg/form';

export const metadata: Metadata = { title: 'Styleguide', robots: { index: false, follow: false } };

const COLOR_TOKENS = ['bg', 'surface', 'surface-inset', 'line', 'ink', 'ink-muted', 'primary', 'on-primary', 'accent', 'accent-text', 'urgent', 'on-urgent', 'link', 'open-bg', 'open-fg', 'soon-bg', 'soon-fg', 'closed-bg', 'closed-fg', 'alert', 'primary-hover', 'primary-press'];
const TYPE = [
  ['display', 'Manrope 800 · 56/60', 'Your way in'], ['h1', 'Manrope 800 · 40/48', 'Funding calls'], ['h2', 'Manrope 700 · 28/36', 'Additive manufacturing'],
  ['h3', 'Manrope 600 · 20/28', 'Eligibility'], ['body', 'Manrope 400 · 16/24', 'Closes in 46 days.'], ['small', 'Manrope 400 · 14/20', 'Retrieved daily'],
  ['label', 'Manrope 700 · 12/16', 'Deadline'], ['mono', 'DM Mono 400 · 13/20', 'EDF-2026-DA-MATCOMP-AMSP'], ['mono-strong', 'DM Mono 500 · 15/22', 'EUR 25,000,000'], ['figure', 'DM Mono 500 · 24/30', '26 Nov 2026'],
] as const;
const SPACES = [1, 2, 3, 4, 5, 6, 8, 10];
const RADIUS_CLASS = { md: 'rounded-md', lg: 'rounded-lg', pill: 'rounded-pill' } as const;
const STATUSES: StatusKind[] = ['open', 'upcoming', 'soon', 'closed', 'amended'];

const DEMO_SOURCE = { sourceId: 'eu-ted', sourceName: 'TED', url: 'https://ted.europa.eu', retrievedAt: '2026-10-11T06:20:00Z', licence: 'Commission Decision 2011/833/EU', attribution: '© European Union, TED' };
const DEMO_TENDER: Opportunity = {
  id: 'demo', slug: 'demo', noticeId: '2026/S 188-561204', title: 'Framework agreement for machined aluminium housings', originalTitle: 'Raamovereenkomst voor gefreesde aluminium behuizingen', originalLanguage: 'nl',
  buyerId: 'b1', buyerName: 'Fictional Logistics Agency', country: 'NL', cpv: '44316400', cpvDivision: '44', procedure: 'Restricted', deadline: '2026-11-26T11:00:00Z', publishedAt: '2026-09-28T00:00:00Z',
  estimatedValue: { amount: 3_400_000, currency: 'EUR' }, status: 'open', amended: true, versionCount: 3, source: DEMO_SOURCE,
};
const DEMO_VERSIONS: OpportunityVersion[] = [
  { version: 3, detectedAt: '2026-11-03T06:20:00Z', changes: [{ field: 'deadline', label: 'Deadline', before: '12 Nov 2026', after: '26 Nov 2026' }] },
  { version: 2, detectedAt: '2026-10-08T06:20:00Z', changes: [{ field: 'lots', label: 'Lots', before: '2', after: '3' }] },
  { version: 1, detectedAt: '2026-09-28T06:20:00Z', changes: [] },
];

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4">
      <h2 id={id} className="m-0 text-h2">{title}</h2>
      {children}
    </section>
  );
}
function Specimen({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('flex flex-col gap-3 rounded-lg bg-surface p-6', className)}>
      <span className="text-label text-ink-muted">{label}</span>
      {children}
    </div>
  );
}

function TokenPanel({ theme }: { theme: 'light' | 'dark' }) {
  return (
    <div data-theme={theme === 'dark' ? 'dark' : undefined} className="flex flex-col gap-4 rounded-lg bg-bg p-5 text-ink">
      <span className="text-h3">{theme === 'dark' ? 'Dark' : 'Light'}</span>
      <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(130px,1fr))] gap-3 p-0">
        {COLOR_TOKENS.map((t) => (
          <li key={t} className="flex flex-col gap-1.5">
            <span className="h-12 rounded-md border border-line" style={{ background: `var(--${t})` }} />
            <code className="font-mono text-mono">--{t}</code>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default async function StyleguidePage() {
  // Internal design reference: development and review only, never served in production.
  if (process.env.NODE_ENV === 'production') notFound();
  const ref = now();
  const { items } = await getCalls({ status: 'all', pageSize: 100 });
  const byState = (s: DeadlineState) => items.find((c) => getDeadline(c.deadline, ref).state === s) as Call;
  const states: DeadlineState[] = ['normal', 'soon', 'urgent', 'closed', 'none'];
  const forthcoming = items.find((c) => c.status === 'forthcoming');

  return (
    <>
      <header className="flex flex-col gap-2">
        <h1 className="m-0 text-h1">Styleguide</h1>
        <p className="m-0 max-w-[62ch] text-body text-ink-muted">Tokens and shared components. Values come from the DefenceGate design system; see README for the mapping.</p>
      </header>

      <Section id="brand" title="Brand">
        <div className="grid gap-4 md:grid-cols-2">
          <Specimen label="Logo on light"><Logo size={28} /></Specimen>
          <Specimen label="Logo reversed" className="bg-primary"><Logo size={28} reversed /></Specimen>
          <Specimen label="Marks: default 48 · small 32 · favicon 20">
            <div className="flex items-center gap-4"><LogoMark size={48} /><LogoMark variant="small" size={32} /><LogoMark variant="favicon" size={20} /></div>
          </Specimen>
        </div>
      </Section>

      <Section id="colour" title="Colour tokens">
        <div className="grid gap-4 xl:grid-cols-2"><TokenPanel theme="light" /><TokenPanel theme="dark" /></div>
      </Section>

      <Section id="type" title="Type scale">
        <div className="flex flex-col rounded-lg bg-surface p-6">
          {TYPE.map(([cls, spec, sample]) => (
            <div key={cls} className="grid items-baseline gap-2 border-b border-line py-3 last:border-0 md:grid-cols-[200px_minmax(0,1fr)]">
              <span className="font-mono text-mono text-ink-muted">.{cls} · {spec}</span>
              <span className={cn(cls, 'min-w-0 break-words')}>{sample}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section id="space" title="Spacing and radius">
        <div className="grid gap-4 md:grid-cols-2">
          <Specimen label="Spacing">
            {SPACES.map((s) => (
              <div key={s} className="flex items-center gap-3">
                <code className="w-24 font-mono text-mono">--space-{s}</code>
                <span className="h-3 rounded-pill bg-primary" style={{ width: `var(--space-${s})` }} />
              </div>
            ))}
          </Specimen>
          <Specimen label="Radius">
            <div className="flex flex-wrap gap-4">
              {(['md', 'lg', 'pill'] as const).map((r) => (
                <div key={r} className="flex flex-col items-center gap-2">
                  <span className={cn('size-20 bg-surface-inset', RADIUS_CLASS[r])} />
                  <code className="font-mono text-mono">--radius-{r}</code>
                </div>
              ))}
            </div>
          </Specimen>
        </div>
      </Section>

      <Section id="buttons" title="Buttons">
        <Specimen label="Primary · secondary · text · with icon · disabled">
          <div className="flex flex-wrap items-center gap-3">
            <Button>Get alerts</Button>
            <Button variant="secondary">Save as watchlist</Button>
            <Button variant="text">View original</Button>
            <Button icon={Bell}>Get alerts for similar calls</Button>
            <Button variant="secondary" iconRight={ArrowRight}>Browse open calls</Button>
            <Button disabled>Disabled</Button>
            <Button variant="secondary" disabled>Disabled</Button>
          </div>
        </Specimen>
      </Section>

      <Section id="status" title="Tags, status pills, deadline badges">
        <div className="grid gap-4 md:grid-cols-2">
          <Specimen label="Tag: programme · neutral"><div className="flex flex-wrap gap-2"><Tag kind="programme">EDF</Tag><Tag kind="programme">EDIP</Tag><Tag>Dual-use</Tag><Tag>PL</Tag></div></Specimen>
          <Specimen label="StatusPill"><div className="flex flex-wrap gap-2">{STATUSES.map((s) => <StatusPill key={s} status={s} />)}</div></Specimen>
        </div>
        <Specimen label={`DeadlineBadge: over ${SOON_DAYS} days · ${SOON_DAYS} days or fewer · ${URGENT_DAYS} days or fewer · closed · no fixed deadline`}>
          <div className="flex flex-wrap gap-3">
            {states.map((s) => byState(s) && <DeadlineBadge key={s} deadline={byState(s).deadline} />)}
            {forthcoming && <DeadlineBadge deadline={forthcoming.deadline} opening={forthcoming.openingDate} />}
          </div>
        </Specimen>
      </Section>

      <Section id="data" title="Data display">
        <div className="grid gap-4 md:grid-cols-2">
          <Specimen label="AmountDisplay · CountryLabel">
            <AmountDisplay money={{ amount: 25_000_000, currency: 'EUR' }} size="lg" />
            <AmountDisplay money={{ amount: 4_000_000, currency: 'PLN' }} />
            <AmountDisplay money={null} />
            <div className="flex flex-wrap gap-4"><CountryLabel code="PL" /><CountryLabel code="SE" /><CountryLabel code="EU" /></div>
          </Specimen>
          <Specimen label="FactCell: default · soon">
            <dl className="m-0 grid grid-cols-2 gap-3"><FactCell label="Call ID">EDF-2026-DA</FactCell><FactCell label="Closing soon" tone="soon">30 Oct 2026</FactCell></dl>
          </Specimen>
          <Specimen label="SourceBadge: full"><SourceBadge source={DEMO_SOURCE} version="v3 of 3" /></Specimen>
          <Specimen label="SourceBadge: inline"><SourceBadge source={DEMO_SOURCE} variant="inline" /></Specimen>
        </div>
      </Section>

      <Section id="cards" title="Call cards in every deadline state, and a forthcoming call">
        <ul className="m-0 grid list-none gap-4 p-0 lg:grid-cols-2">
          {states.map((s) => byState(s) && <li key={s}><CallCard call={byState(s)} headingLevel="h3" /></li>)}
          {forthcoming && <li><CallCard call={forthcoming} headingLevel="h3" /></li>}
          <li><CallCardSkeleton /></li>
        </ul>
      </Section>

      <Section id="tenders" title="Tender card and version timeline">
        <div className="grid gap-4 lg:grid-cols-2">
          <TenderCard tender={DEMO_TENDER} />
          <Specimen label="VersionTimeline"><VersionTimeline versions={DEMO_VERSIONS} /></Specimen>
        </div>
      </Section>

      <Section id="forms" title="Inputs">
        <div className="grid gap-4 rounded-lg bg-surface p-6 md:grid-cols-2">
          <TextInput search placeholder="Search calls" label="Search" />
          <TextInput label="Company name" hint="As registered" />
          <TextInput label="Work email" defaultValue="name@company" error="Enter a valid email address" />
          <TextInput label="Disabled" defaultValue="Locked value" disabled />
          <Select label="Country" placeholder="Choose country" options={[{ value: 'PL', label: 'PL Poland' }, { value: 'ES', label: 'ES Spain' }]} />
          <div className="flex flex-col"><Choice label="Checkbox" defaultChecked /><Choice label="Checkbox" /><Choice type="radio" name="r" label="Radio" defaultChecked /><Choice type="radio" name="r" label="Radio disabled" disabled /></div>
        </div>
      </Section>

      <Section id="nav" title="Navigation">
        <Specimen label="Breadcrumbs"><Breadcrumbs items={[{ label: 'Home', href: '/' }, { label: 'Funding', href: '/funding' }, { label: 'EDF', href: '/funding?programme=EDF' }]} /></Specimen>
        <Specimen label="Pagination"><Pagination page={3} total={96} pageSize={10} hrefFor={(p) => `/funding?page=${p}`} /></Specimen>
      </Section>

      <Section id="states" title="States">
        <div className="grid gap-4 lg:grid-cols-2">
          <EmptyState title="No calls match these filters" action={<Button variant="secondary">Clear filters</Button>}>Try a wider deadline range or fewer programmes.</EmptyState>
          <ErrorState retryHref="/styleguide" />
          <LockedFeature feature="Full version history" />
          <div className="flex flex-col gap-3"><ComingSoon feature="Readiness check" /><ComingSoon feature="Organisations" /></div>
        </div>
      </Section>
    </>
  );
}
