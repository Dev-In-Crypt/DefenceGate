import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { getRequirements } from '@/lib/readiness-api';
import { CATEGORY_WORD, formatDays, formatRange, isoDay, joinWords, programmeName, requirementSlug } from '@/lib/readiness';
import type { RequirementSummary } from '@/lib/readiness-types';
import { absoluteUrl, buildMetadata } from '@/lib/seo';
import { AutoGrid } from '@/components/dg/auto-grid';
import { Button } from '@/components/dg/button';
import { Card } from '@/components/dg/card';
import { ContentPage, ContentSection, PageSection } from '@/components/dg/content-page';
import { ErrorState, JsonLd } from '@/components/dg/feedback';
import { FactsGrid } from '@/components/dg/facts-grid';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Requirements for EU defence programmes: NCAGE, PIC, AQAP, export licences',
  description: 'What separates a company from taking part in EDF, EDIP, SAFE and NATO supply: each requirement, who issues it (in the countries covered so far), what it costs and how long it takes, with the source and the date it was last reviewed.',
  path: '/requirements',
});

/** One requirement: name, summary, then Cost and Time as facts (label above value) pinned to the bottom, so the cards of a row line up. */
function RequirementCard({ r }: { r: RequirementSummary }) {
  const document = r.kind === 'document';
  return (
    <Card as="li" className="gap-3">
      <h3 className="m-0 text-h3"><Link href={`/requirements/${requirementSlug(r.code)}`} className="text-inherit">{r.name}</Link></h3>
      <p className="m-0 text-body text-ink-muted">{r.summary}</p>
      {document && (
        <FactsGrid className="mt-auto" items={[
          { label: 'Cost', value: `${formatRange(r.cost)}${r.cost?.label ? ` (${r.cost.label})` : ''}` },
          { label: 'Time', value: formatDays(r.days) },
        ]} />
      )}
      <p className={document ? 'm-0 text-small text-ink-muted' : 'm-0 mt-auto text-small text-ink-muted'}>
        {r.programmes.length > 0 ? `Appears in the rules of ${joinWords(r.programmes.map(programmeName))}. ` : ''}Last reviewed {isoDay(r.lastReviewed)}.
      </p>
    </Card>
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
      toc
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Requirements', href: '/requirements' }]}
      title="Requirements for EU defence programmes"
      lead="What separates a company from taking part: the codes, registrations, certificates and licences, and the eligibility rules. For each one: who issues it (in the countries covered so far), what it costs and how long it takes, with the source and the date it was last reviewed."
    >
      {failed && <ErrorState title="The catalogue could not be loaded" retryHref="/requirements" />}
      {items.length > 0 && <JsonLd data={list} />}
      {categories.map((c) => (
        <PageSection key={c} id={`cat-${c}`} title={CATEGORY_WORD[c] ?? c}>
          <AutoGrid as="ul" min={400} pairs>{documents.filter((r) => r.category === c).map((r) => <RequirementCard key={r.code} r={r} />)}</AutoGrid>
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
          Every cost on these pages that is not free comes from a certification body or a consultancy, and no neutral body publishes prices. They are shown as ranges, in the currency the vendor used, labelled as vendor ranges and not as a benchmark. Where a source states no cost or time, the page says so and shows none.
        </p>
      </ContentSection>
      <div>
        <Button href="/readiness" iconRight={ArrowRight}>Check where your company stands</Button>
      </div>
    </ContentPage>
  );
}
