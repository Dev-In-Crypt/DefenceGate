import type { Metadata } from 'next';
import { ContentPage } from '@/components/dg/content-page';
import { RoadmapView } from '@/components/readiness/roadmap';

export const metadata: Metadata = {
  title: 'Your readiness roadmap',
  description: 'What to obtain, in what order, who issues it, and what it costs and takes, with the ranges and their sources.',
  robots: { index: false, follow: false },
};

export default function RoadmapPage() {
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Check my company', href: '/check' }, { label: 'Readiness check', href: '/readiness' }, { label: 'Roadmap', href: '/readiness/roadmap' }]}
      title="Your roadmap"
      lead="What to obtain, in the order the dependencies allow, with who issues it and what it costs and takes."
      wide
    >
      <RoadmapView />
    </ContentPage>
  );
}
