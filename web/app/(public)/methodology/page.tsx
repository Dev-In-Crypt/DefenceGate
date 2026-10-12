import type { Metadata } from 'next';
import Link from 'next/link';
import { buildMetadata } from '@/lib/seo';
import { Callout, ClauseList, Steps } from '@/components/dg/blocks';
import { ContentPage, ContentSection } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'How DefenceGate collects and classifies',
  description: 'How notices are collected, normalised, classified as defence or dual-use, linked across sources and versioned, and what the limits of that are.',
  path: '/methodology',
});

const PIPELINE = [
  { title: 'Collect', body: 'Each source is fetched on a schedule through its public interface. The payload is kept, with contact fields removed, before anything else is done to it.' },
  { title: 'Normalise', body: 'Fields are mapped to one shape: title, buyer, country, dates, value, codes. The contact fields a source publishes are dropped, and e-mail addresses are also removed from free text.' },
  { title: 'Classify and link', body: 'Each notice is checked for defence and dual-use signals and linked to the same notice on other sources where a shared reference exists.' },
];

export default function MethodologyPage() {
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Methodology', href: '/methodology' }]}
      title="How we collect and classify"
      lead="What happens to a notice between the source and this site, and where the limits are."
    >
      <section aria-labelledby="flow" className="flex flex-col gap-4">
        <h2 id="flow" className="m-0 text-h2">From source to screen</h2>
        <Steps items={PIPELINE} />
      </section>

      <ContentSection title="Every change is kept">
        <p className="m-0 text-body text-ink-muted">
          When a source publishes a changed version of a notice, we store it as a new version and record which fields changed. Earlier versions are not overwritten. The timeline on a record shows what changed and when we observed it, which is not necessarily when the source made the change.
        </p>
      </ContentSection>

      <ContentSection title="What “defence” and “dual-use” mean here">
        <p className="m-0 text-body text-ink-muted">
          The label is an automated indication built from separate signals. A legal basis or a military product code can qualify a notice alone. A buyer on our defence list also qualifies it, but such notices are listed separately and are not in the default view. Security clearance and civil product codes need a partner signal.
        </p>
        <ClauseList items={[
          'The legal basis of the procedure, for example Directive 2009/81/EC on defence and security procurement.',
          'The product classification (CPV), where military and civil groups are told apart.',
          'The buyer, against a curated list of defence buyers.',
          'Security clearance or confidentiality requirements stated in the notice.',
        ]} />
        <p className="m-0 text-body text-ink-muted">
          The result is not a legal determination and not a statement about export control, eligibility or the procurement regime that applies. It can be wrong in both directions. For funding calls, “dual-use” is the regime the programme or source itself assigns, not our classification.
        </p>
      </ContentSection>

      <ContentSection title="Linking the same notice">
        <p className="m-0 text-body text-ink-muted">
          The same procurement is often published on TED and on a national portal. Where both carry the same TED reference we link them and show one record. Buyers are matched only when the name is identical after case, accent and legal-form normalisation, in the same country.
        </p>
      </ContentSection>

      <ContentSection title="Titles and normalisation">
        <p className="m-0 text-body text-ink-muted">
          We do not machine-translate notices. Where a source publishes an English title we show it, with the original title beneath; otherwise only the original is shown. Normalised fields and the defence label are ours and are not part of the original notice. Amounts are shown in the currency recorded for the source and are never converted.
        </p>
      </ContentSection>

      <ContentSection title="Limits">
        <ClauseList items={[
          'Collection is scheduled, not real time. The status page shows when each source last ran.',
          'A source can fail, change format or publish late. A run that fell short is marked partial.',
          'Not every portal is covered, and below-threshold procurement is often not published centrally.',
          'A record that cannot be read is skipped and logged instead of being guessed. It is not shown.',
        ]} />
      </ContentSection>

      <Callout title="Always check the original">
        <p className="m-0">Each record links to its source. Confirm deadlines, scope and conditions there. See the <Link href="/data" className="font-semibold">source status</Link> and the <Link href="/terms" className="font-semibold">terms</Link>.</p>
      </Callout>
    </ContentPage>
  );
}
