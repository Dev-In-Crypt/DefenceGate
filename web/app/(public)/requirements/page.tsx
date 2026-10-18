import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { getRequirements } from '@/lib/readiness-api';
import { CATEGORY_WORD, formatDays, formatRange, isoDay, joinWords, programmeName, requirementSlug } from '@/lib/readiness';
import type { RequirementSummary } from '@/lib/readiness-types';
import { absoluteUrl, buildMetadata } from '@/lib/seo';
import { Button } from '@/components/dg/button';
import { ContentPage, ContentSection } from '@/components/dg/content-page';
import { ErrorState, JsonLd } from '@/components/dg/feedback';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Requirements for EU defence programmes: NCAGE, PIC, AQAP, export licences',
  description: 'What separates a company from taking part in EDF, EDIP, SAFE and NATO supply: each requirement, who issues it (in the countries covered so far), what it costs and how long it takes, with the source and the date it was last reviewed.',
  path: '/requirements',
});

function Card({ r }: { r: RequirementSummary }) {
  return (
    <li className="flex min-w-0 flex-col gap-3 rounded-lg bg-surface p-5 sm:p-6">
      <h3 className="m-0 text-h3"><Link href={`/requirements/${requirementSlug(r.code)}`} className="text-inherit">{r.name}</Link></h3>
      <p className="m-0 text-body text-ink-muted">{r.summary}</p>
      {r.kind === 'document' && (
        <dl className="m-0 grid gap-x-6 gap-y-1 text-small sm:grid-cols-2">
          <div><dt className="inline font-bold">Cost: </dt><dd className="m-0 inline">{formatRange(r.cost)}{r.cost?.label ? ` (${r.cost.label})` : ''}</dd></div>
          <div><dt className="inline font-bold">Time: </dt><dd className="m-0 inline">{formatDays(r.days)}</dd></div>
        </dl>
      )}
      <p className="m-0 text-small text-ink-muted">
        {r.programmes.length > 0 ? `Appears in the rules of ${joinWords(r.programmes.map(programmeName))}. ` : ''}Last reviewed {isoDay(r.lastReviewed)}.
      </p>
    </li>
  );
}

export default async function RequirementsPage() {
  let items: RequirementSummary[] = [];
  let failed = false;
  try {
    items = (await getRequirements()).items;
  } catch {
    failed = true;
  }
  const documents = items.filter((r) => r.kind === 'document');
  const rules = items.filter((r) => r.kind === 'rule');
  const categories = [...new Set(documents.map((r) => r.category))];
  const list = {
    '@context': 'https://schema.org', '@type': 'ItemList', name: 'Requirements for EU defence programmes',
    itemListElement: items.map((r, i) => ({ '@type': 'ListItem', position: i + 1, name: r.name, url: absoluteUrl(`/requirements/${requirementSlug(r.code)}`) })),
  };
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Requirements', href: '/requirements' }]}
      title="Requirements for EU defence programmes"
      lead="What separates a company from taking part: the codes, registrations, certificates and licences, and the eligibility rules. For each one: who issues it (in the countries covered so far), what it costs and how long it takes, with the source and the date it was last reviewed."
    >
      {failed && <ErrorState title="The catalogue could not be loaded" retryHref="/requirements" />}
      {items.length > 0 && <JsonLd data={list} />}
      {categories.map((c) => (
        <section key={c} aria-labelledby={`cat-${c}`} className="flex flex-col gap-4">
          <h2 id={`cat-${c}`} className="m-0 text-h2">{CATEGORY_WORD[c] ?? c}</h2>
          <ul className="m-0 grid list-none gap-4 p-0 md:grid-cols-2">{documents.filter((r) => r.category === c).map((r) => <Card key={r.code} r={r} />)}</ul>
        </section>
      ))}
      {rules.length > 0 && (
        <section aria-labelledby="cat-rules" className="flex flex-col gap-4">
          <h2 id="cat-rules" className="m-0 text-h2">Eligibility rules of the programmes</h2>
          <p className="m-0 max-w-[70ch] text-body text-ink-muted">These are not documents to obtain. They are conditions the programme sets on a company, read from the regulation.</p>
          <ul className="m-0 grid list-none gap-4 p-0 md:grid-cols-2">{rules.map((r) => <Card key={r.code} r={r} />)}</ul>
        </section>
      )}
      <ContentSection title="About the costs">
        <p className="m-0 text-body text-ink-muted">
          Every cost on these pages that is not free comes from a certification body or a consultancy, and no neutral body publishes prices. They are shown as ranges, in the currency the vendor used, labelled as vendor ranges and not as a benchmark. Where a source states no cost or time, the page says so and shows none.
        </p>
      </ContentSection>
      <div>
        <Button href="/readiness" iconRight={ArrowRight}>Check where your company stands</Button>
      </div>
    </ContentPage>
  );
}
