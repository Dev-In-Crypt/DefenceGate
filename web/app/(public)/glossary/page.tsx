import type { Metadata } from 'next';
import Link from 'next/link';
import { GLOSSARY } from '@/lib/glossary';
import { absoluteUrl, buildMetadata } from '@/lib/seo';
import { ContentPage } from '@/components/dg/content-page';
import { JsonLd } from '@/components/dg/feedback';

export const revalidate = 86400;

export const metadata: Metadata = buildMetadata({
  title: 'Glossary of defence procurement and funding terms',
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
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Glossary', href: '/glossary' }]}
      title="Glossary"
      lead="The terms a defence supplier meets in tenders and funding calls, explained briefly. These are plain-language explanations, not legal advice; the original notice and the legal text are authoritative."
    >
      <JsonLd data={definedTerms()} />
      <nav aria-label="Terms" className="rounded-lg border border-edge bg-surface p-5 sm:p-6">
        <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0">
          {ENTRIES.map((e) => (
            <li key={e.id}><a href={`#${e.id}`} className="inline-flex min-h-11 items-center text-small font-semibold">{e.term}</a></li>
          ))}
        </ul>
      </nav>

      <dl className="m-0 flex flex-col gap-4">
        {ENTRIES.map((e) => (
          <div key={e.id} id={e.id} className="flex scroll-mt-4 flex-col gap-2 rounded-lg border border-edge bg-surface p-5 sm:p-6">
            <dt className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-h3 font-semibold">{e.term}</span>
              {e.full && <span className="text-small text-ink-muted">{e.full}</span>}
            </dt>
            <dd className="m-0 flex flex-col gap-2">
              <p className="m-0 text-body text-ink-muted">{e.body}</p>
              {(e.source || e.see) && (
                <p className="m-0 flex flex-wrap items-center gap-x-4 gap-y-1 text-small text-ink-muted">
                  {e.source && <span>Official source: {e.source}</span>}
                  {e.see && <Link href={e.see.href} className="inline-flex min-h-11 items-center font-semibold">{e.see.label}</Link>}
                </p>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </ContentPage>
  );
}
