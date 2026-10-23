import type { Metadata } from 'next';
import Link from 'next/link';
import { PHASE_PRODUCTION_BUILD } from 'next/constants';
import { ArrowRight } from 'lucide-react';
import { getRequirement, getRequirements } from '@/lib/readiness-api';
import { CATEGORY_WORD, costStatement, issuerFor, joinWords, programmeName, requirementSlug, siteDay, timeStatement, type IssuerAnswer } from '@/lib/readiness';
import type { RequirementSummary } from '@/lib/readiness-types';
import { safeHttpUrl } from '@/lib/safe-url';
import { BUYER_COUNTRIES, countryName } from '@/lib/taxonomy';
import { Select } from '@/components/dg/form';
import { absoluteUrl, buildMetadata } from '@/lib/seo';
import { AutoGrid } from '@/components/dg/auto-grid';
import { Button } from '@/components/dg/button';
import { Card } from '@/components/dg/card';
import { ContentPage, ContentSection, PageSection } from '@/components/dg/content-page';
import { ErrorState, JsonLd } from '@/components/dg/feedback';
import { FactsGrid } from '@/components/dg/facts-grid';
import { InfoLink } from '@/components/dg/about-data';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Requirements for EU defence programmes: NCAGE, PIC, AQAP, export licences',
  description: 'What separates a company from taking part in EDF, EDIP, SAFE and NATO supply: each requirement, who issues it (in the countries covered so far), what it costs and how long it takes, with the source and the date it was last reviewed.',
  path: '/requirements',
});

/** WP-88: a requirement whose name carries an abbreviation gets an (i) to its glossary entry. */
const TERM_OF: Record<string, { id: string; term: string }> = {
  'REQ-FSC-ES': { id: 'hsem', term: 'HSEM' }, 'REQ-HSES-ES': { id: 'hses', term: 'HSES' }, 'REQ-PIC': { id: 'pic', term: 'PIC' },
};

/** WP-91: who issues a document in the chosen country, as plainly as our sources allow (an unverified issuer is said to be one). */
function IssuerLine({ a, country }: { a: IssuerAnswer; country: string }) {
  if (a.kind === 'verified') {
    const url = safeHttpUrl(a.issuer.url);
    return (
      <p className="m-0 text-small" data-issuer="verified">
        <strong>{a.issuer.country === '*' ? `Issued for ${countryName(country)} by` : `Issued in ${countryName(country)} by`}:</strong>{' '}
        {url ? <a href={url} target="_blank" rel="noopener noreferrer">{a.issuer.name}</a> : a.issuer.name}
      </p>
    );
  }
  return (
    <p className="m-0 text-small" data-issuer={a.kind}>
      {a.text}
      {a.kind === 'unverified' && a.link && <> <a href={a.link.url} target="_blank" rel="noopener noreferrer" className="font-semibold">{a.link.label}<span className="sr-only"> (opens in new tab)</span></a>.</>}
    </p>
  );
}

/** One requirement: name, summary, then Cost and Time as facts (label above value) pinned to the bottom, so the cards of a row line up. */
function RequirementCard({ r, issuer, country }: { r: RequirementSummary; issuer?: IssuerAnswer; country?: string }) {
  const document = r.kind === 'document';
  return (
    <Card as="li" className="gap-3">
      <h3 className="m-0 text-h3"><Link href={`/requirements/${requirementSlug(r.code)}`} className="text-inherit">{r.name}</Link>{TERM_OF[r.code] && <> <InfoLink id={TERM_OF[r.code].id} term={TERM_OF[r.code].term} /></>}</h3>
      <p className="m-0 text-body text-ink-muted">{r.summary}</p>
      {issuer && country && <IssuerLine a={issuer} country={country} />}
      {document && (
        <FactsGrid className="mt-auto" items={[
          { label: 'Cost', value: `${costStatement(r.cost)}${r.cost?.label ? ` (${r.cost.label})` : ''}` },
          { label: 'Time', value: timeStatement(r.days) },
        ]} />
      )}
      <p className={document ? 'm-0 text-small text-ink-muted' : 'm-0 mt-auto text-small text-ink-muted'}>
        {r.programmes.length > 0 ? `Appears in the rules of ${joinWords(r.programmes.map(programmeName))}. ` : ''}Last reviewed {siteDay(r.lastReviewed)}.
      </p>
    </Card>
  );
}

/** The countries of the readiness check (its wizard's list, without "another country"). */
const COUNTRIES = Object.entries({ ...BUYER_COUNTRIES, LI: 'Liechtenstein', UA: 'Ukraine', TR: 'Türkiye', US: 'United States' })
  .map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label, 'en'));

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default async function RequirementsPage({ searchParams }: Props) {
  const raw = (await searchParams).country;
  // WP-91 (UX audit 6: the page read as Spain's): who issues each document in the visitor's country, from the same issuer rows
  const country = typeof raw === 'string' && /^[A-Z]{2}$/.test(raw) ? raw : '';
  let items: RequirementSummary[] = [];
  let failed = false;
  try {
    items = (await getRequirements()).items;
  } catch (e) {
    // At run time a failed refresh is thrown: the page is regenerated in the background (ISR), and a throw keeps the last good
    // catalogue in the cache instead of storing the error state for an hour (WP-63). Only a build, which has nothing older to
    // keep, renders the error state.
    if (process.env.NEXT_PHASE !== PHASE_PRODUCTION_BUILD) throw e;
    failed = true;
  }
  const documents = items.filter((r) => r.kind === 'document');
  const issuers = new Map<string, IssuerAnswer>(country
    ? (await Promise.all(documents.map(async (r) => {
      const d = await getRequirement(r.code).catch(() => null);
      return d ? [[r.code, issuerFor(r.code, d.issuers, country)] as const] : [];
    }))).flat()
    : []);
  const rules = items.filter((r) => r.kind === 'rule');
  const categories = [...new Set(documents.map((r) => r.category))];
  const list = {
    '@context': 'https://schema.org', '@type': 'ItemList', name: 'Requirements for EU defence programmes',
    itemListElement: items.map((r, i) => ({ '@type': 'ListItem', position: i + 1, name: r.name, url: absoluteUrl(`/requirements/${requirementSlug(r.code)}`) })),
  };
  return (
    <ContentPage
      toc
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Requirements', href: '/requirements' }]}
      title="Requirements"
      lead="The codes, registrations, certificates and licences a company needs to take part, and the eligibility rules: open one for who issues it, its cost and time, and its source."
    >
      {failed && <ErrorState title="The catalogue could not be loaded" retryHref="/requirements" />}
      <form method="get" action="/requirements" aria-label="Who issues them in your country" className="flex flex-wrap items-end gap-3">
        <Select name="country" label="Who issues them in your country" placeholder="Choose a country" options={COUNTRIES} defaultValue={country} className="w-72" />
        <button type="submit" className="inline-flex min-h-11 items-center rounded-pill border-strong border-ink bg-surface px-5 text-small font-bold text-ink">Show</button>
      </form>
      {items.length > 0 && <JsonLd data={list} />}
      {categories.map((c) => (
        <PageSection key={c} id={`cat-${c}`} title={CATEGORY_WORD[c] ?? c}>
          <AutoGrid as="ul" min={400} pairs>{documents.filter((r) => r.category === c).map((r) => <RequirementCard key={r.code} r={r} issuer={issuers.get(r.code)} country={country} />)}</AutoGrid>
        </PageSection>
      ))}
      {rules.length > 0 && (
        <PageSection id="cat-rules" title="Eligibility rules of the programmes"
          intro="These are not documents to obtain. They are conditions the programme sets on a company, read from the regulation.">
          <AutoGrid as="ul" min={400} pairs>{rules.map((r) => <RequirementCard key={r.code} r={r} />)}</AutoGrid>
        </PageSection>
      )}
      <ContentSection title="About the costs">
        <p className="m-0 text-body text-ink-muted">
          Each card names the issuer in the countries covered so far, the source and the date it was last reviewed. Every cost on these pages that is not free comes from a certification body or a consultancy, and no neutral body publishes prices. They are shown as ranges, in the currency the vendor used, labelled as vendor ranges and not as a benchmark. Where a source states no cost or time, the page says so and shows none.
        </p>
      </ContentSection>
      <div>
        <Button href="/readiness" iconRight={ArrowRight}>Check where your company stands</Button>
      </div>
    </ContentPage>
  );
}
