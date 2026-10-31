import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';
import { ContentPage, ContentSection } from '@/components/dg/content-page';
import { Fact } from '@/components/dg/facts-grid';

export const revalidate = 3600;

/** The provider's details, as the owner gives them. Every fact here comes from the owner; none is invented. A field that is
 * not given is not shown (WP-161: no empty label, no placeholder on the published page). */
const PROVIDER: Partial<Record<'Provider' | 'Legal form' | 'Address' | 'Registration number' | 'VAT number'
  | 'Represented by' | 'Contact', string>> = {};

const FIELDS = (Object.entries(PROVIDER) as [string, string | undefined][]).filter(([, v]) => v && v.trim());

export const metadata: Metadata = buildMetadata({
  title: 'Imprint',
  description: FIELDS.length ? 'Provider details for DefenceGate.' : 'Provider details for DefenceGate: not published yet.',
  path: '/imprint',
  noindex: true,
});

export default function ImprintPage() {
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Imprint', href: '/imprint' }]}
      title="Imprint"
      lead={FIELDS.length ? undefined : 'The provider’s details are not published yet. They will be here before any plan is sold.'}
    >
      {FIELDS.length > 0 && (
        <ContentSection title="Provider">
          <dl className="m-0 grid gap-x-8 border-b border-line sm:grid-cols-2">
            {FIELDS.map(([f, v], i) => <Fact key={f} label={f} wide={i === FIELDS.length - 1}>{v}</Fact>)}
          </dl>
        </ContentSection>
      )}
    </ContentPage>
  );
}
