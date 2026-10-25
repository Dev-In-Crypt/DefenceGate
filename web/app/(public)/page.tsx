import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { getAccountStatus } from '@/lib/account';
import { getCalls, getHealth, getSiteStats, getSupplierSummary, getTenders, lastDataUpdate } from '@/lib/api';
import { portalWords } from '@/lib/coverage-copy';
import { getCallDeadline, getTenderDeadline, type DeadlineInfo } from '@/lib/deadline';
import { displayName } from '@/lib/display-name';
import { formatDateTimeUtc, formatDateUtc, formatMoney, formatNumber, isPlaceholderAmount, plural, repeatedCallBudgets } from '@/lib/format';
import { buildMetadata, faqJsonLd, organizationJsonLd } from '@/lib/seo';
import { faqItems, homeFaq } from '@/lib/site-copy';
import { PROGRAMMES, countryName, isNonEnglish } from '@/lib/taxonomy';
import type { Money } from '@/lib/types';
import { Button } from '@/components/dg/button';
import { Faq } from '@/components/dg/blocks';
import { EmptyState, JsonLd } from '@/components/dg/feedback';
import { CARD_PADDING, CARD_SURFACE } from '@/components/dg/card';
import { Icon } from '@/components/dg/icon';
import { SiteSearchForm } from '@/components/dg/site-search';

export const revalidate = 60;
const SAMPLE_SIZE = 3;

export const metadata: Metadata = buildMetadata({
  title: 'Defence and dual-use tenders and funding calls',
  description: 'Tenders, buyers and funding calls from TED and national portals in one place. Every record links to its original source, and changes to dates, values and status are kept.',
  path: '/',
});

/** A figure of a tile: the number, or nothing at all when the data service gave none (never a dash, never a zero it did not say). */
function Figure({ value, label }: { value: number | null | undefined; label: string }) {
  if (value === null || value === undefined) return null;
  return (
    <span data-figure="" className="flex flex-col">
      <span className="font-mono text-h3 tabular-nums">{formatNumber(value)}</span>
      <span className="text-small text-ink-muted">{label}</span>
    </span>
  );
}

/**
 * One of the three questions (WP-117, owner's option A): the whole tile is one link, named by its question and its title (the
 * rest is read as its description). The question is the heading, so the three stand in the page's outline.
 */
function Tile({ id, href, question, title, body, go, children }: { id: string; href: string; question: string; title: string; body: string; go: string; children?: React.ReactNode }) {
  return (
    <li className="min-w-0">
      <Link href={href} data-tile="" aria-labelledby={`${id}-q ${id}-t`} aria-describedby={children ? `${id}-b ${id}-n` : `${id}-b`}
        className={`group flex h-full flex-col gap-3 border-strong text-ink no-underline transition-colors duration-dg hover:border-ink-muted ${CARD_SURFACE} ${CARD_PADDING}`}>
        <h2 id={`${id}-q`} className="m-0 text-h4 text-accent-text">{question}</h2>
        <span id={`${id}-t`} className="text-h3 font-bold group-hover:underline">{title}</span>
        <span id={`${id}-b`} className="text-body text-ink-muted">{body}</span>
        {children && <span id={`${id}-n`} className="mt-auto flex flex-wrap gap-x-6 gap-y-2 pt-1">{children}</span>}
        <span className={`inline-flex items-center gap-2 text-body font-bold ${children ? '' : 'mt-auto'}`}>{go}<Icon icon={ArrowRight} size="inline" /></span>
      </Link>
    </li>
  );
}

/** A row of a closing-soon list: the title, what it is from (and its value where stated) and the deadline, nothing more. */
function Row({ href, title, lang, meta, deadline }: { href: string; title: string; lang?: string; meta: string; deadline: DeadlineInfo }) {
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-0.5 border-t border-line px-5 py-3 first:border-t-0">
      <Link href={href} prefetch={false} lang={lang} title={title} className="inline-flex min-h-11 min-w-0 items-center font-semibold no-underline hover:underline">
        {/* two lines at most: one line cut a phone's titles to two words */}
        <span className="line-clamp-2 min-w-0 break-words">{title}</span>
      </Link>
      <span className="col-start-2 row-span-2 row-start-1 text-right text-small">
        {deadline.rolling || !deadline.iso
          ? <span className="font-bold">{deadline.rolling ? deadline.label : 'No fixed deadline'}</span>
          : <><span className="block font-bold text-accent-text">{deadline.countdown}</span><time dateTime={deadline.iso} className="font-mono tabular-nums">{formatDateUtc(deadline.iso)}</time></>}
      </span>
      <span className="min-w-0 text-small text-ink-muted">{meta}</span>
    </li>
  );
}

const stated = (m: Money | null | undefined) => (m && !isPlaceholderAmount(m.amount) ? formatMoney(m) : null);

function ClosingList({ id, title, more, empty, children }: { id: string; title: string; more: { href: string; label: string }; empty: React.ReactNode; children: React.ReactNode[] }) {
  return (
    <section aria-labelledby={id} className="flex min-w-0 flex-col gap-3">
      <h2 id={id} className="m-0 text-h2">{title}</h2>
      {children.length === 0 ? empty : <ul className={`m-0 list-none p-0 ${CARD_SURFACE}`}>{children}</ul>}
      <Link href={more.href} className="inline-flex min-h-11 items-center gap-2 self-start text-body font-bold">{more.label}<Icon icon={ArrowRight} size="inline" /></Link>
    </section>
  );
}

export default async function LandingPage() {
  const today = new Date().toISOString().slice(0, 10);
  // Cached for a minute; any failure reads as "not open", which keeps the earlier wording.
  const { open: accountsOpen } = await getAccountStatus();
  const health = await getHealth().catch(() => null);
  const faq = homeFaq(faqItems(portalWords(health?.sources ?? []), accountsOpen));
  const [stats, current, dated, closingCalls, suppliers] = await Promise.all([
    getSiteStats().catch(() => null),
    // The tender list's default (/tenders, status Open): not past its deadline, and with no deadline only if published within the last year.
    getTenders({ pageSize: 1 }, { cacheable: true }).catch(() => null),
    // With a stated deadline that has not passed, the nearest first: the ones a reader can still act on by date.
    getTenders({ deadlineFrom: today, pageSize: SAMPLE_SIZE }, { cacheable: true }).catch(() => null),
    getCalls({ status: 'closing-soon', pageSize: SAMPLE_SIZE }, { cacheable: true }).catch(() => null),
    // Cached (an hour); null when the API has no supplier map: the tile then carries no number.
    getSupplierSummary(),
  ]);
  // A list that did not come is not an empty list, and not a page to keep. This page is prerendered and revalidated every minute
  // (`revalidate`): an error thrown here fails the build (which tries a page again, next.config.ts) or the revalidation, and Next
  // goes on serving the last page that rendered. Rendering "could not be loaded" instead baked that sentence into the page until the
  // next revalidation (18 October 2026, a build while the API's database role was exhausted). `withLastGood` cannot help in a fresh
  // build container (nothing is held yet), and its key for the closing-tenders list carries today's date.
  if (dated === null || closingCalls === null) throw new Error('home: the data service did not answer for the closing lists');
  const budgetRepeats = repeatedCallBudgets(closingCalls.items);
  const openTenders = current?.total ?? null;
  const openCalls = stats?.openCalls ?? null;
  const sources = health?.sources.length ?? stats?.sources ?? null;
  const lastUpdate = stats?.lastUpdate ?? (health ? lastDataUpdate(health) : null);
  return (
    <>
      <JsonLd data={organizationJsonLd()} />
      {/* WP-117: only the questions this page shows; /about carries the others */}
      <JsonLd data={faqJsonLd(faq)} />

      {/* WP-117 (owner's option A of 25 October 2026): the headline and lead are the owner's words; one search, nothing else. */}
      <section aria-labelledby="hero" className="flex flex-col gap-5 pt-2 md:pt-6">
        <h1 id="hero" className="m-0 text-display-sm [text-wrap:balance] md:text-display">Win, partner, qualify.<br className="hidden md:inline" /> Across Europe’s defence market.</h1>
        <p className="m-0 max-w-prose text-body text-ink-muted md:text-h3 md:font-normal">
          Defence and dual-use tenders and EU funding calls, the companies already in EU-funded projects, and a five-question check against EDF, EDIP and SAFE rules. Free to browse, every fact linked to its source.
        </p>
        <SiteSearchForm id="home-search" className="max-w-3xl" />
      </section>

      <section aria-label="Three questions" className="flex flex-col gap-3">
        <ul aria-label="What do you want to know?" className="m-0 grid list-none gap-4 p-0 md:grid-cols-3">
          <Tile id="t-open" href="/tenders" question="What is open?" title="Find tenders and funding" go="Browse"
            body="Defence and dual-use tenders from TED and national portals, and EU and national funding calls, with their deadlines.">
            {(openTenders !== null || openCalls !== null) && <><Figure value={openTenders} label={plural(openTenders ?? 0, 'open tender')} /><Figure value={openCalls} label={plural(openCalls ?? 0, 'open funding call')} /></>}
          </Tile>
          <Tile id="t-partners" href="/companies" question="Who is already in?" title="Find partners" go="Find partners"
            body="Companies that won defence contracts or took part in EU-funded projects, and partners in Ukraine.">
            {suppliers && <Figure value={suppliers.suppliers} label={`${plural(suppliers.suppliers, 'company', 'companies')} that won contracts`} />}
          </Tile>
          {/* Five steps: the readiness check's wizard (components/readiness/wizard.tsx, "Step n of 5") */}
          <Tile id="t-check" href="/check" question="Can I take part?" title="Check if my company qualifies" go="Start the check"
            body="Five short sets of questions. The answer says what the EDF, EDIP and SAFE rules mean for your company, with the rule text it rests on.">
            <span data-figure="" className="flex flex-col"><span className="font-mono text-h3 tabular-nums">5</span><span className="text-small text-ink-muted">steps, no account</span></span>
          </Tile>
        </ul>
        <p className="m-0 text-body text-ink-muted">
          Make parts or provide services?{' '}
          <Link href="/readiness/supplier" className="inline-flex min-h-11 items-center font-bold text-ink">See who buys what you make</Link>
        </p>
      </section>

      <div className="grid gap-8 md:grid-cols-2 md:gap-6">
        <ClosingList id="closing-tenders" title="Tenders closing soon"
          more={{ href: '/tenders', label: openTenders === null ? 'All open tenders' : `All ${formatNumber(openTenders)} open tenders` }}
          empty={<EmptyState title="No tenders to show right now" action={<Button variant="secondary" href="/tenders">Browse all tenders</Button>} />}>
          {dated.items.map((t) => (
            <Row key={t.id} href={`/tenders/${t.slug}`} title={displayName(t.title)} lang={isNonEnglish(t.titleLanguage) ? (t.titleLanguage ?? undefined) : undefined}
              meta={[t.country ? countryName(t.country) : null, stated(t.estimatedValue)].filter(Boolean).join(' · ')} deadline={getTenderDeadline(t)} />
          ))}
        </ClosingList>
        <ClosingList id="closing" title="Funding closing soon"
          more={{ href: '/funding', label: openCalls === null ? 'All open calls' : `All ${formatNumber(openCalls)} open ${plural(openCalls, 'call')}` }}
          empty={<EmptyState title="No calls close in the next 30 days" action={<Button variant="secondary" href="/funding">Browse all open calls</Button>} />}>
          {closingCalls.items.map((c) => (
            // A call budget shared by the topics of one call is stated once (on its first row), as the list cards do.
            <Row key={c.id} href={`/funding/${c.slug}`} title={displayName(c.title)} lang={isNonEnglish(c.titleLanguage) ? c.titleLanguage : undefined}
              meta={[PROGRAMMES[c.programme].label, budgetRepeats.has(c.id) ? null : stated(c.budget)].filter(Boolean).join(' · ')} deadline={getCallDeadline(c)} />
          ))}
        </ClosingList>
      </div>

      <section aria-label="About the data" className="flex flex-wrap items-center gap-x-6 gap-y-1 border-y border-line py-3 text-body text-ink-muted">
        {sources !== null && <span data-trust="sources"><span className="font-bold text-ink">{formatNumber(sources)} {plural(sources, 'source')}</span> (TED and national portals)</span>}
        {lastUpdate && <span data-trust="update">Last update <span className="font-mono tabular-nums text-ink">{formatDateTimeUtc(lastUpdate)}</span></span>}
        <Link href="/methodology" className="inline-flex min-h-11 items-center font-bold text-ink">Methodology</Link>
        <Link href="/data" className="inline-flex min-h-11 items-center font-bold text-ink">Source status</Link>
      </section>

      {/* No e-mail provider yet: the digest is read on its page or in a feed reader; no field that would collect an address. */}
      <section aria-labelledby="digest" className={`flex flex-col gap-4 md:flex-row md:items-center md:justify-between md:gap-8 ${CARD_SURFACE} ${CARD_PADDING}`}>
        <div className="flex min-w-0 flex-col gap-2">
          <h2 id="digest" className="m-0 text-h2">The week in Europe’s defence market</h2>
          <p className="m-0 max-w-prose text-body text-ink-muted">New and amended defence notices, and funding calls that are new, opening or closing, once a week. Free, with an Atom feed for your feed reader.</p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2">
          <Button href="/digest" iconRight={ArrowRight}>Read the latest digest</Button>
          <a href="/digest.atom" className="inline-flex min-h-11 items-center font-bold">Atom feed</a>
        </div>
      </section>

      <section aria-labelledby="faq" className="flex flex-col gap-4">
        <h2 id="faq" className="m-0 text-h2">Questions</h2>
        <Faq items={faq} />
        <Link href="/about" className="inline-flex min-h-11 items-center gap-2 self-start text-body font-bold">More questions<Icon icon={ArrowRight} size="inline" /></Link>
      </section>
    </>
  );
}
