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

/** A-26: the official sources a term names, linked to their own sites (a source of several documents stays plain text). */
const SOURCE_URL: Record<string, string> = {
  'Directive 2009/81/EC on EUR-Lex': 'https://eur-lex.europa.eu/eli/dir/2009/81/oj',
  'EUR-Lex': 'https://eur-lex.europa.eu/',
  'EU Funding & Tenders Portal': 'https://ec.europa.eu/info/funding-tenders/opportunities/portal/',
  'TED': 'https://ted.europa.eu/',
  'TED and the Publications Office of the European Union': 'https://ted.europa.eu/',
  'CORDIS, European Commission': 'https://cordis.europa.eu/',
  'European Commission': 'https://commission.europa.eu/',
  'European Defence Agency': 'https://eda.europa.eu/',
  'BOE (Boletín Oficial del Estado)': 'https://www.boe.es/',
  'Ministerio de Defensa': 'https://www.defensa.gob.es/',
  'Ministerio de Hacienda': 'https://www.hacienda.gob.es/',
};

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
        {/* A-25: each term a 44 px target (they were 22 x 32 px on a phone) */}
        <Details summary="Jump to a term">
          <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-0 p-0">
            {ENTRIES.map((e) => (
              <li key={e.id}><a href={`#${e.id}`} className="inline-flex min-h-11 min-w-11 items-center font-semibold">{e.term}</a></li>
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
                    {e.source && <span>Official source: {SOURCE_URL[e.source] ? <a href={SOURCE_URL[e.source]} rel="noopener">{e.source}</a> : e.source}</span>}
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

