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
  { title: 'Collect', body: 'Each source is fetched once a day through its public interface. The payload is kept in a private archive, with contact fields removed, before anything else is done to it. A small number of payloads landed before 22 September 2026 still hold some; they are never shown.' },
  { title: 'Normalise', body: 'Fields are mapped to one shape: title, buyer, country, dates, value, codes. The contact fields a source publishes are dropped, and e-mail addresses are also removed from free text.' },
  { title: 'Classify and link', body: 'Each notice is checked for defence and dual-use signals and linked to the same notice on other sources where a shared reference or identifier exists.' },
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

      <ContentSection title="What is versioned">
        <p className="m-0 text-body text-ink-muted">
          We keep a new version when a notice’s title, buyer, country, procedure, legal basis, value, currency, publication date, deadline, product codes, source link or status changes, and record which fields changed. A change to anything else, such as a rewritten description, does not create a version. Earlier versions are never overwritten or deleted.
        </p>
        <p className="m-0 text-body text-ink-muted">
          History starts when we first saw a notice: our archive began in September 2026, and earlier states are not reconstructed. The timeline on a record lists the amendments we observed and when we observed them, which is not necessarily when the source made the change. Versions we add ourselves when we correct how a field is read are kept in the archive but are not listed as amendments.
        </p>
      </ContentSection>

      <ContentSection title="What “defence” and “dual-use” mean here">
        <p className="m-0 text-body text-ink-muted">
          The label is an automated indication built from separate signals. A legal basis or a military product code can qualify a notice. A military code bought by a municipal, health, education or fire body is labelled dual-use or security and is not in the default view. A buyer on our defence list, or a link to a defence notice of another source, puts a notice in the separate “supplies to defence buyers” list. Two kinds of notice with a single defence signal from the wrong kind of buyer are kept in that same list and never deleted: a notice whose only signal is the defence directive, from a buyer that is not a defence or security body (“Filed under the defence procurement directive by a civil buyer”), and a notice whose only signal is a military product code, from a police, prison, border, customs or tax body (“Security-body purchase of a military-type product code”). Search and the scope filter find them. The “Defence goods only” switch narrows the list further, to notices that say defence themselves (the directive or a military product code) and not only through a listed buyer. A security-clearance or confidentiality field and a civil security code are recorded but do not qualify a notice.
        </p>
        <ClauseList items={[
          'The legal basis of the procedure, for example Directive 2009/81/EC on defence and security procurement.',
          'The product classification (CPV), where military and civil groups are told apart.',
          'The buyer, against a curated list of defence buyers, and the kind of body it is.',
          'A security-clearance or confidentiality field in the notice. On TED this field also carries sanctions declarations and criminal-record certificates, so it is shown but never qualifies a notice.',
        ]} />
        <p className="m-0 text-body text-ink-muted">
          The result is not a legal determination and not a statement about export control, eligibility or the procurement regime that applies. It can be wrong in both directions. For funding calls we label a call “dual-use” when it belongs to a civil programme or area we treat as dual-use: all Digital Europe calls, Horizon Europe’s civil-security, digital, industry and space areas and the European Innovation Council, and Connecting Europe military-mobility topics. The label is ours, not the programme’s.
        </p>
      </ContentSection>

      <ContentSection title="Linking the same notice">
        <p className="m-0 text-body text-ink-muted">
          The same procurement is often published on TED and on a national portal. We link a national notice to its TED notice by the reference it states, by the procedure identifier both carry or, where neither exists, by a strict match on buyer, deadline, value and publication date. Each link stores how it was made, and a linked national notice is shown under the TED one, so a wrong link can hide a notice: check both. Buyers are matched by their organisation identifier where the notice carries one, then by an identical name after case, accent and legal-form normalisation, in the same country.
        </p>
      </ContentSection>

      <ContentSection title="Titles and normalisation">
        <p className="m-0 text-body text-ink-muted">
          We do not machine-translate notices. Where a source publishes an English title we show it, with the original title beneath; otherwise only the original is shown. TED composes its English title itself, with country and product words in English followed by the buyer’s own title, which stays in the buyer’s language. Normalised fields and the defence label are ours and are not part of the original notice. Amounts are shown in the currency recorded for the source and are never converted.
        </p>
      </ContentSection>

      <ContentSection title="Limits">
        <ClauseList items={[
          'Collection is scheduled once a day, not real time. The status page shows when each source last ran.',
          'A source can fail, change format or publish late. A run that fell short is marked partial.',
          'National tender portals are collected for four countries (Spain, France, the Netherlands and Poland); elsewhere we hold only what TED carries. Below-threshold procurement is often not published centrally. Known gaps are listed on the source status page.',
          'A field a source does not give, or that we do not read from it, is shown as not available or not read from this source, never as a finding.',
          'A record that cannot be read is skipped and logged instead of being guessed. It is not shown.',
        ]} />
      </ContentSection>

      <Callout title="Always check the original">
        <p className="m-0">Each record links to its source. Confirm deadlines, scope and conditions there. See the <Link href="/data" className="font-semibold">source status</Link> and the <Link href="/terms" className="font-semibold">terms</Link>.</p>
      </Callout>
    </ContentPage>
  );
}
