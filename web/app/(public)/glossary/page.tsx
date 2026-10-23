import type { Metadata } from 'next';
import Link from 'next/link';
import { GLOSSARY } from '@/lib/glossary';
import { absoluteUrl, buildMetadata } from '@/lib/seo';
import { Card } from '@/components/dg/card';
import { ContentPage } from '@/components/dg/content-page';
import { Details } from '@/components/dg/details';
import { JsonLd } from '@/components/dg/feedback';

export const revalidate = 86400;

export const metadata: Metadata = buildMetadata({
  title: 'Defence procurement and funding glossary',
  description: 'Short plain-English explanations of the terms a defence supplier meets in tenders and funding calls: 2009/81/EC, CPV, VEAT, framework agreements, EDF, EDIP, SAFE and more.',
  path: '/glossary',
});

const ENTRIES = [...GLOSSARY].sort((a, b) => a.term.localeCompare(b.term, 'en', { sensitivity: 'base' }));

function definedTerms() {
  return {
    '@context': 'https://schema.org', '@type': 'DefinedTermSet',
    name: 'DefenceGate glossary', url: absoluteUrl('/glossary'),
    hasDefinedTerm: ENTRIES.map((e) => ({
      '@type': 'DefinedTerm', name: e.term, termCode: e.id, description: e.body, url: absoluteUrl(`/glossary#${e.id}`),
    })),
  };
}

export default function GlossaryPage() {
  return (
    <ContentPage
      toc={ENTRIES.map((e) => ({ id: e.id, label: e.term }))}
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Glossary', href: '/glossary' }]}
      title="Glossary"
      lead="The terms of tenders and funding calls in plain words; not legal advice, the notice and the legal text are authoritative."
    >
      <JsonLd data={definedTerms()} />
      {/* From lg the page's own contents list (sticky, at the left) does this; below lg the terms are one collapsed list. */}
      <nav aria-label="Terms" className="rounded-lg border border-transparent bg-surface px-5 sm:px-7 lg:hidden print:hidden">
        <Details summary="Jump to a term">
          <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-0 p-0">
            {ENTRIES.map((e) => (
              <li key={e.id}><a href={`#${e.id}`} className="inline-flex min-h-8 items-center font-semibold">{e.term}</a></li>
            ))}
          </ul>
        </Details>
      </nav>

      {/* One card, one hairline between terms: 35 boxes in a row were a wall. */}
      <Card>
        <dl className="m-0 flex flex-col">
          {ENTRIES.map((e) => (
            <div key={e.id} id={e.id} className="flex scroll-mt-4 flex-col gap-2 border-t border-line py-5 first:border-t-0 first:pt-0 last:pb-0">
              <dt className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="text-h3">{e.term}</span>
                {e.full && <span className="text-small text-ink-muted">{e.full}</span>}
              </dt>
              <dd className="m-0 flex flex-col gap-2">
                <p className="m-0 text-body text-ink-muted">{e.body}</p>
                {(e.source || e.see) && (
                  <p className="m-0 flex flex-wrap items-center gap-x-4 gap-y-0 text-small text-ink-muted">
                    {e.source && <span>Official source: {e.source}</span>}
                    {e.see && <Link href={e.see.href} className="inline-flex min-h-8 items-center font-semibold">{e.see.label}</Link>}
                  </p>
                )}
              </dd>
            </div>
          ))}
        </dl>
      </Card>
    </ContentPage>
  );
}

