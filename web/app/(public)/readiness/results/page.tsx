import type { Metadata } from 'next';
import { ContentPage } from '@/components/dg/content-page';
import { ResultsView } from '@/components/readiness/results';

export const metadata: Metadata = {
  title: 'Your readiness results',
  description: 'Your verdict for each programme, rule by rule, with the source of every rule.',
  // Private to the visitor and different for each: there is nothing here to index.
  robots: { index: false, follow: false },
};

export default function ResultsPage() {
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Check my company', href: '/check' }, { label: 'Readiness check', href: '/readiness' }, { label: 'Results', href: '/readiness/results' }]}
      title="Your readiness results"
      lead="One card for each programme. Open a card to read every rule, the reason for its outcome and the text of the source."
      wide
    >
      <ResultsView />
    </ContentPage>
  );
}
