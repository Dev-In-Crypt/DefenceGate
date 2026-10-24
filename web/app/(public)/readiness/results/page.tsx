import type { Metadata } from 'next';
import { ContentPage } from '@/components/dg/content-page';
import { ResultsView } from '@/components/readiness/results';

type Props = { searchParams: Promise<{ from?: string | string[] }> };

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const supplier = (await searchParams).from === 'supplier';
  return {
    title: supplier ? 'Your supplier report' : 'Your readiness results',
    description: 'Your verdict for each programme, rule by rule, with the source of every rule.',
    // Private to the visitor and different for each: there is nothing here to index.
    robots: { index: false, follow: false },
  };
}

/** WP-97: reached from the supplier profile (`?from=supplier`), the page is the supplier's report and its crumbs lead back to the profile. */
export default async function ResultsPage({ searchParams }: Props) {
  const supplier = (await searchParams).from === 'supplier';
  return (
    <ContentPage
      crumbs={supplier
        ? [{ label: 'Home', href: '/' }, { label: 'Check my company', href: '/check' }, { label: 'Supplier profile', href: '/readiness/supplier' }, { label: 'Supplier report', href: '/readiness/results?from=supplier' }]
        : [{ label: 'Home', href: '/' }, { label: 'Check my company', href: '/check' }, { label: 'Readiness check', href: '/readiness' }, { label: 'Results', href: '/readiness/results' }]}
      title={supplier ? 'Your supplier report' : 'Your readiness results'}
      lead={supplier
        ? 'What is open now under your codes, who to approach, who buys, and the rules of your supply routes, each with its source.'
        : 'One card for each programme. Open a card to read every rule, the reason for its outcome and the text of the source.'}
      wide
    >
      <ResultsView fromSupplier={supplier} />
    </ContentPage>
  );
}
