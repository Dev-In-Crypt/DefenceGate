import type { Metadata } from 'next';
import Link from 'next/link';
import { Eye, FileSearch, Scale, ShieldCheck } from 'lucide-react';
import { getAccountStatus } from '@/lib/account';
import { getHealth } from '@/lib/api';
import { portalWords } from '@/lib/coverage-copy';
import { buildMetadata, faqJsonLd } from '@/lib/seo';
import { HOME_QUESTIONS, STEPS, benefits, faqItems } from '@/lib/site-copy';
import { Button } from '@/components/dg/button';
import { BenefitGrid, Callout, Faq, Steps } from '@/components/dg/blocks';
import { ContentPage, ContentSection, PageSection } from '@/components/dg/content-page';
import { JsonLd } from '@/components/dg/feedback';

// WP-117: the page now carries the home page's former blocks, whose words follow the sources and whether sign-in is open (as home did).
export const revalidate = 60;

export const metadata: Metadata = buildMetadata({
  title: 'About DefenceGate',
  description: 'DefenceGate is an independent information service that makes public defence and dual-use procurement and funding notices easier to find, read and verify.',
  path: '/about',
});

const PRINCIPLES = [
  { icon: FileSearch, title: 'Source first', body: 'Every record links to the original publication. We make notices easier to find; the source stays the authority.' },
  { icon: Eye, title: 'Gaps in the open', body: 'We publish which sources we collect, when each last ran, whether the run met the minimum we expect and which gaps we know of, including when a run failed.' },
  { icon: Scale, title: 'Facts, not opinions', body: 'We show what notices say and what changed. We do not rate buyers, predict outcomes or advise on bids.' },
  { icon: ShieldCheck, title: 'Commercial information only', body: 'We show dates, buyers, values and codes. We do not display, summarise or extract technical specifications. Our collection drops the contact fields a source publishes. Older payloads in our private archive still hold some, and about 960 buyer names (with about 1,130 spellings) hold a telephone, fax or e-mail block as the source wrote it; none of it is shown (see the methodology).' },
];

const RESOURCES = [
  { label: 'Deadline calendar', href: '/calendar', body: 'Upcoming tender and funding deadlines, also as a calendar feed.' },
  { label: 'CPV finder', href: '/cpv', body: 'Find the procurement codes that describe your products.' },
  { label: 'Glossary', href: '/glossary', body: 'Plain-English explanations of procurement and funding terms.' },
  { label: 'Source status', href: '/data', body: 'When each source last ran, whether that run met the minimum we expect, and the known gaps.' },
];

export default async function AboutPage() {
  const { open: accountsOpen } = await getAccountStatus();
  const health = await getHealth().catch(() => null);
  const portals = portalWords(health?.sources ?? []);
  const faq = faqItems(portals, accountsOpen);
  const home = new Set<string>(HOME_QUESTIONS);
  return (
    <ContentPage
      toc
      crumbs={[{ label: 'Home', href: '/' }, { label: 'About', href: '/about' }]}
      title="About DefenceGate"
      lead="Public notices about defence and dual-use work are spread over many portals, formats and languages. We bring them into one place and make them easy to check."
    >
      {/* WP-117: the home page's structured data keeps its four questions; this page's carries the others */}
      <JsonLd data={faqJsonLd(faq.filter((f) => !home.has(f.q)))} />
      <ContentSection title="Why we exist">
        <p className="m-0 text-body text-ink-muted">
          A supplier who wants to work for European defence buyers has to watch TED, national portals and funding programmes, each with its own layout, language and search. Deadlines move. Values are corrected. Notices appear on one portal and again on another.
        </p>
        <p className="m-0 text-body text-ink-muted">
          DefenceGate collects those public notices, puts them side by side, links the same notice across sources where it can and keeps a version history of the changes it observes, so the people who bid, advise and write grant applications spend their time on the work and not on the searching.
        </p>
      </ContentSection>

      {/* WP-117: moved from the home page, unchanged */}
      <PageSection title="Why DefenceGate" id="why">
        <BenefitGrid items={benefits(portals.names)} />
      </PageSection>

      <PageSection title="How it works" id="how">
        <Steps items={STEPS} />
      </PageSection>

      <PageSection title="How we work" id="principles">
        <BenefitGrid items={PRINCIPLES} columns={2} />
      </PageSection>

      <ContentSection title="Who is behind it">
        <p className="m-0 text-body text-ink-muted">
          DefenceGate is built and run by a small independent team. We are not part of, paid by or endorsed by any contracting authority, ministry, programme or the European Union. The legal provider is named in the <Link href="/imprint" className="font-semibold">imprint</Link>.
        </p>
      </ContentSection>

      <Callout title="What we are not">
        <p className="m-0">An official publisher, a bidding platform, a contracting authority or an adviser. We do not submit bids or applications for anyone, and nothing here is legal, export-control or eligibility advice.</p>
      </Callout>

      {/* WP-117: moved from the home page, unchanged */}
      <Callout title="Please note">
        <p className="m-0">DefenceGate is an information service, not an official source and not advice. The original publication is authoritative; check it before you act. See the <Link href="/terms" className="font-semibold">terms</Link>.</p>
      </Callout>

      <PageSection title="Questions" id="faq">
        <Faq items={faq} />
      </PageSection>

      <ContentSection title="Resources">
        <ul className="m-0 grid list-none gap-3 p-0 sm:grid-cols-2">
          {RESOURCES.map((r) => (
            <li key={r.href} className="flex min-w-0 flex-col gap-0.5">
              <Link href={r.href} className="inline-flex min-h-11 items-center text-body font-semibold">{r.label}</Link>
              <span className="text-small text-ink-muted">{r.body}</span>
            </li>
          ))}
        </ul>
      </ContentSection>

      <ContentSection title="Get in touch">
        <p className="m-0 text-body text-ink-muted">
          To report a mistake, ask for a record to be corrected, or raise a data protection question, use the contact details in the <Link href="/imprint" className="font-semibold">imprint</Link>.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button href="/methodology" variant="secondary">How we collect and classify</Button>
          <Button href="/data" variant="secondary">See the sources</Button>
        </div>
      </ContentSection>
    </ContentPage>
  );
}
