import type { Metadata } from 'next';
import Link from 'next/link';
import { CPV_SOURCE, cpvSections } from '@/lib/cpv';
import { buildMetadata } from '@/lib/seo';
import { Callout } from '@/components/dg/blocks';
import { ContentPage } from '@/components/dg/content-page';
import { CpvBrowser } from '@/components/cpv/cpv-browser';

export const revalidate = 86400;

export const metadata: Metadata = buildMetadata({
  title: 'CPV codes for defence and security procurement',
  description: 'A searchable list of CPV codes that matter to defence and security suppliers: division 35 and its military groups, defence-adjacent codes and the common supply divisions, with official English titles.',
  path: '/cpv',
});

export default function CpvPage() {
  const sections = cpvSections();
  return (
    <ContentPage
      wide
      crumbs={[{ label: 'Home', href: '/' }, { label: 'CPV finder', href: '/cpv' }]}
      title="CPV finder"
      lead="The Common Procurement Vocabulary (CPV) is the code list a buyer uses to say what a notice is about. Find the codes for your products and open the tenders that carry them."
    >
      <Callout title="How the links work">
        <p className="m-0">
          Each code opens <Link href="/tenders" className="font-semibold">tenders</Link> whose CPV codes start with its digits, so a group code also finds the codes under it. Whether a notice is defence is decided by more than its code: see <Link href="/methodology" className="font-semibold">how we classify</Link>.
        </p>
      </Callout>

      <CpvBrowser sections={sections} />

      <p className="m-0 max-w-[860px] text-small text-ink-muted">
        Titles are the English names in the CPV 2008 vocabulary (Commission Regulation (EC) No 213/2008) as published by the Publications Office of the European Union, retrieved {CPV_SOURCE.retrieved}.
        This is a selection of {CPV_SOURCE.held} of the vocabulary&rsquo;s {CPV_SOURCE.vocabularySize.toLocaleString('en-GB')} codes, and the selection is ours. The complete vocabulary is on the EU Vocabularies site of the Publications Office.
      </p>
    </ContentPage>
  );
}
