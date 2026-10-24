import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { buildMetadata } from '@/lib/seo';
import { Button } from '@/components/dg/button';
import { ContentPage, PageSection } from '@/components/dg/content-page';
import { Card } from '@/components/dg/card';

export const metadata: Metadata = buildMetadata({
  title: 'Check my company: EU defence funding or supplying defence buyers',
  description: 'One question first: do you want EU defence funding (EDF, EDIP, SAFE) or to supply defence buyers? Then the check that answers it, with the requirements and the rules behind it.',
  path: '/check',
});

/**
 * Check my company (WP-86): the one entry to the three questionnaires (UX audit of 22 October 2026: the readiness check,
 * the supplier profile and the Spain automotive landing linked away from each other). The first question is what the visitor
 * wants; each answer is a link to the check that answers it, so the page works without script and keeps nothing.
 */
const CHOICES = [
  {
    title: 'EU defence funding',
    body: 'May your company take part in the European Defence Fund, EDIP or SAFE? Five short sets of questions give a verdict for each programme, rule by rule, and what to obtain first.',
    href: '/readiness', action: 'Start the readiness check',
  },
  {
    title: 'Become a supplier to defence buyers',
    body: 'You make parts or materials and want defence work. Say what you make: see who wins defence contracts for it, who buys it, and what the buyers’ routes ask of you.',
    href: '/readiness/supplier', action: 'Start the supplier profile',
  },
  {
    // WP-97 (persona round of 23 October 2026): the services path; the same profile, with the services questions and codes
    title: 'Supply services to the armed forces',
    body: 'We provide services: logistics, transport, fuel, facility services, catering, maintenance and repair, training or IT. Say what you provide: see who wins those contracts, who buys them, and what the buyers’ routes ask of you.',
    href: '/readiness/supplier?offer=services', action: 'Start with services',
  },
] as const;

export default function CheckPage() {
  return (
    <ContentPage crumbs={[{ label: 'Home', href: '/' }, { label: 'Check my company', href: '/check' }]} title="Check my company"
      lead="Answer one question first, then the check that fits.">
      <section aria-labelledby="want" className="flex flex-col gap-4">
        <h2 id="want" className="m-0 text-h2">What do you want?</h2>
        <ul className="m-0 grid list-none gap-4 p-0 md:grid-cols-2 lg:grid-cols-3">
          {CHOICES.map((c) => (
            <li key={c.href} className="min-w-0">
              <Card className="h-full gap-3">
                <h3 className="m-0 text-h3">{c.title}</h3>
                <p className="m-0 text-body">{c.body}</p>
                <Button href={c.href} iconRight={ArrowRight} className="mt-auto self-start">{c.action}</Button>
              </Card>
            </li>
          ))}
        </ul>
        <p className="m-0 text-body">
          <Link href="/readiness/spain-automotive" className="inline-flex min-h-11 items-center gap-2 font-bold">
            I make parts in Spain, for example for cars: who buys and who wins my products?<ArrowRight size={18} aria-hidden="true" className="shrink-0" />
          </Link>
        </p>
      </section>
      <PageSection title="The rules behind the checks">
        <ul className="m-0 flex list-none flex-col gap-1 p-0 text-body">
          <li>
            <Link href="/requirements" className="inline-flex min-h-11 items-center font-bold">Requirements</Link>
            <span className="text-ink-muted">: what a company needs for EDF, EDIP, SAFE and NATO supply, who issues it, what it costs and how long it takes.</span>
          </li>
          <li>
            <Link href="/regulation" className="inline-flex min-h-11 items-center font-bold">Regulatory tracker</Link>
            <span className="text-ink-muted">: changes in the rules that matter to a defence supplier, each with its official source.</span>
          </li>
        </ul>
      </PageSection>
    </ContentPage>
  );
}
