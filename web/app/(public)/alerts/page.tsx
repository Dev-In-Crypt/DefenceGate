import type { Metadata } from 'next';
import { ArrowRight, BellRing, Bookmark, CalendarDays, Clock, Download, GitCompare, Link2, Rss } from 'lucide-react';
import { buildMetadata } from '@/lib/seo';
import { getAccountStatus } from '@/lib/account';
import { BenefitGrid } from '@/components/dg/blocks';
import { Fact } from '@/components/dg/facts-grid';
import { Button } from '@/components/dg/button';
import { ContentPage, ContentSection } from '@/components/dg/content-page';

export const revalidate = 60;

export const metadata: Metadata = buildMetadata({
  title: 'Alerts and saved searches',
  description: 'Saved searches and e-mail alerts are built; sign-in is not open yet. Without an account: filters in the address, CSV, a calendar feed and Atom feeds.',
  path: '/alerts',
});

const FEATURES = [
  { icon: Bookmark, title: 'Saved searches', body: 'Save a search by country, buyer, product code or keyword and come back to it with one click. Alert e-mails list the new notices and calls that match it.' },
  { icon: GitCompare, title: 'Changes on your dashboard', body: 'Your dashboard shows what changed since your last visit in the notices you shortlisted and in those of buyers you follow: a moved deadline, a corrected value, a new status. The dashboard does not list funding calls yet; the What changed page lists new calls and moved dates.' },
  { icon: Clock, title: 'Your cadence', body: 'Choose within the hour, a daily digest or a weekly summary, and pause an alert whenever you like.' },
  { icon: BellRing, title: 'Closing soon', body: 'Your dashboard lists the deadlines of the notices you shortlisted, and of your saved-search matches, for the next 14 days.' },
];

/** What a visitor can do today, with no account and nothing to configure. */
const WORKS_TODAY = [
  { icon: Link2, title: 'A search you can keep', body: 'Every filter on the tender, funding and buyer pages is in the address. Bookmark it, or send the link, and it opens the same search.' },
  { icon: Rss, title: 'A feed of what changed', body: 'New notices and amendments to a deadline, value, status or procedure from the last 14 days, as a page and as an Atom feed. Add it to a feed reader and it works like an alert, without an account.' },
  { icon: CalendarDays, title: 'A calendar feed', body: 'Subscribe to the deadline calendar in your own calendar app: open tenders and funding calls with a deadline.' },
  { icon: Download, title: 'CSV of any result', body: 'Download the public fields of a tender or funding list, with the source, licence and attribution on every row.' },
];

export default async function AlertsPage() {
  const { open } = await getAccountStatus();
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Alerts', href: '/alerts' }]}
      title="Alerts and saved searches"
      lead={open
        ? 'Stop re-checking portals. Sign in with your e-mail to save searches, follow buyers and get alerts.'
        : 'Saved searches and e-mail alerts are built, but sign-in is not open yet: it opens once we have chosen a provider to send the e-mails. What works today needs no account, and it is listed first.'}
    >
      {open && <Button href="/signin" iconRight={ArrowRight} className="self-start">Sign in with e-mail</Button>}

      <section aria-labelledby="today" className="flex flex-col gap-4">
        <h2 id="today" className="m-0 text-h2">What works today, without an account</h2>
        <BenefitGrid items={WORKS_TODAY} columns={2} />
        <div className="flex flex-wrap items-center gap-x-5">
          <Button href="/changes" iconRight={ArrowRight}>See what changed</Button>
          <a href="/changes.atom" className="inline-flex min-h-11 items-center text-small font-bold">Atom feed</a>
          <a href="/calendar#feed-heading" className="inline-flex min-h-11 items-center text-small font-bold">Calendar feed</a>
        </div>
      </section>

      {/* One compact block for what is not open (four icon cards, a callout and a dead waitlist form before). */}
      <ContentSection title={open ? 'What you get' : 'What an account adds, once sign-in opens'}>
        <dl className="m-0 flex flex-col">
          {FEATURES.map((f) => <Fact key={f.title} label={f.title}>{f.body}</Fact>)}
        </dl>
        <p className="m-0 text-small text-ink-muted">Browsing tenders, buyers and funding calls is free and needs no account. Alerts are best effort and do not replace checking the original notice. {open ? 'You sign in with your e-mail address and a password.' : 'You will sign in with your e-mail address and a password.'}</p>
      </ContentSection>
    </ContentPage>
  );
}
