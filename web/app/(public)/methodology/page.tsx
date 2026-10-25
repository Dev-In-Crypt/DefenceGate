import type { Metadata } from 'next';
import Link from 'next/link';
import { getHealth } from '@/lib/api';
import { portalWords } from '@/lib/coverage-copy';
import { heldSpan } from '@/lib/source-status';
import { SCOPE_CHOICES } from '@/lib/taxonomy';
import { buildMetadata } from '@/lib/seo';
import { Callout, ClauseList, Steps } from '@/components/dg/blocks';
import { ContentPage, ContentSection, PageSection } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'How DefenceGate collects and classifies',
  description: 'How notices are collected, normalised, classified as defence or dual-use, linked across sources and versioned, and what the limits of that are.',
  path: '/methodology',
});

const PIPELINE = [
  { title: 'Collect', body: 'Each source is fetched through its public interface on its own schedule: tender sources and funding portals daily, the EU research datasets (CORDIS and the EDF results) monthly; the status page shows each one. The payload is kept in a private archive, with contact fields removed, before anything else is done to it. Payloads landed before that was done for every source still hold some: about 100 TED notices of mid-September 2026, and Spanish payloads landed before 12 October 2026, which were not counted. Some earlier versions of notices in the archive also hold e-mail addresses (221 on 21 October 2026, 113 of them written on 12 and 14 October), and about 1,000 buyer names hold a telephone, fax or e-mail block as the source wrote it. None of it is shown.' },
  { title: 'Normalise', body: 'Fields are mapped to one shape: title, buyer, country, dates, value, codes. The contact fields a source publishes are dropped, and e-mail addresses are also removed from free text.' },
  { title: 'Classify and link', body: 'Each notice is checked for defence and dual-use signals and linked to the same notice on other sources where a shared reference or identifier exists.' },
];

export default async function MethodologyPage() {
  const { sources } = await getHealth();
  const portals = portalWords(sources);
  // WP-131: the German start date from the data, as /data says it (the first publication date held)
  const germanyStart = heldSpan(sources.find((s) => s.id === 'de_bkms')?.heldFrom, null) ?? 'October 2023';
  return (
    <ContentPage
      toc
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Methodology', href: '/methodology' }]}
      title="Methodology"
      lead="What happens to a notice between the source and this site, and where the limits are."
    >
      <PageSection id="flow" title="From source to screen">
        <Steps rows items={PIPELINE} />
      </PageSection>

      <ContentSection title="What is versioned">
        <p className="m-0 text-body text-ink-muted">
          We keep a new version when a notice’s title, buyer, country, procedure, legal basis, value, currency, publication date, deadline, product codes, source link or status changes, and record which fields changed. A change to anything else, such as a rewritten description, does not create a version. Earlier versions are never overwritten or deleted.
        </p>
        <p className="m-0 text-body text-ink-muted">
          History starts when we first saw a notice: our archive began in September 2026, and earlier states are not reconstructed. The timeline on a record lists the amendments we observed and when we observed them, which is not necessarily when the source made the change. Versions we add ourselves when we correct how a field is read are kept in the archive but are not listed as amendments. When we load a source&rsquo;s older notices, the changes we find in them are real but old: the record lists them marked as read from history, and they are not counted in the change list, the feeds or the amendment shares.
        </p>
        <p className="m-0 text-body text-ink-muted">
          The change list and its Atom feed show a notice as new only if it was published in the last 14 days, not merely loaded in them. The amendment shares of the market page count notices with an amendment we saw live.
        </p>
      </ContentSection>

      <ContentSection title="What “defence” and “dual-use” mean here">
        <p className="m-0 text-body text-ink-muted">
          The label is an automated indication built from separate signals. A legal basis or a military product code can qualify a notice. A military code bought by a municipal, health, education or fire body is labelled dual-use or security and is not in the default view. A buyer on our defence list, or a link to a defence notice of another source, puts a notice in the separate “supplies to defence buyers” list.
          The default list, “{SCOPE_CHOICES.relevant.short}”, is the core defence notices and the supplies to defence buyers together, and every card says why it is there; “{SCOPE_CHOICES.core.short}” and “{SCOPE_CHOICES.supply.short}” show one part each. Two kinds of notice with a single defence signal from the wrong kind of buyer are kept in that same list and never deleted: a notice whose only signal is the defence directive, from a buyer that is not a defence or security body (“Filed under the defence procurement directive by a civil buyer”), and a notice whose only signal is a military product code, from a police, prison, border, customs or tax body (“Security-body purchase of a military-type product code”). Search and the scope filter find them. The “Defence goods only” switch narrows the list further, to notices that say defence themselves (the directive or a military product code) and not only through a listed buyer. A security-clearance or confidentiality field and a civil security code are recorded but do not qualify a notice.
        </p>
        <ClauseList items={[
          'The legal basis of the procedure, for example Directive 2009/81/EC on defence and security procurement.',
          'The product classification (CPV), where military and civil groups are told apart. A military code that is one of more than 20 codes of a civil buyer’s catch-all notice (a purchasing system that lists everything it may buy), and not its main code, does not count.',
          'The buyer, against a curated list of defence buyers, and the kind of body it is.',
          'A security-clearance or confidentiality field in the notice. On TED this field also carries sanctions declarations and criminal-record certificates, so it is shown but never qualifies a notice.',
        ]} />
        <p className="m-0 text-body text-ink-muted">
          The result is not a legal determination and not a statement about export control, eligibility or the procurement regime that applies. It can be wrong in both directions. For funding calls we label a call “dual-use” when it belongs to a civil programme or area we treat as dual-use: all Digital Europe calls, Horizon Europe’s civil-security, digital, industry and space areas and the European Innovation Council, and Connecting Europe military-mobility topics. The label is ours, not the programme’s.
        </p>
      </ContentSection>

      <ContentSection title="How sure are we">
        <p className="m-0 text-body text-ink-muted">
          Every notice in the list carries a confidence level, high, medium or low, next to the reasons it is listed. The card names the level by what it rests on: “Clearly defence”; “Defence buyer, ordinary purchase”, “Defence buyer, some military codes” or “Defence directive, unlisted buyer”; “Weak defence signal”. The level is worked out from the same signals, when you open the page, and it does not change which notices are listed. It describes the group of notices that get the level, not the single notice: read the reasons on the card, then the original.
        </p>
        <ClauseList items={[
          <><span className="font-semibold text-ink">High.</span> The notice’s main product code is a military one and a buyer on our defence list or the defence directive agrees, or a buyer on our defence list uses the defence directive. Measured under the earlier rule (any military code and a listed buyer): in our sample, 96 % of these notices were themselves defence goods or services (95 % interval 88 to 98) and 99 % were defence goods or services or a defence body buying (92 to 100). Sample: 64 notices.</>,
          <><span className="font-semibold text-ink">Medium.</span> The buyer is on our defence list, or the defence directive and a military product code that is not the main code agree for a buyer that is not a security or civil body. The buyer is a defence body in 93 % of the sample (85 to 97), but only 11 % of the notices were defence goods or services themselves (6 to 19): most are ordinary purchases such as food, cleaning, IT or building work. Sample: 111 notices.</>,
          <><span className="font-semibold text-ink">Low.</span> One weak signal, or a signal from the wrong kind of buyer: only the directive from a civil body, only a military product code, a military code bought by a police, prison, border, customs or tax body. In the sample 21 % were defence goods or services or a defence body buying (16 to 27) and 34 % were not defence at all (28 to 40). Sample: 188 notices.</>,
        ]} />
        <p className="m-0 text-body text-ink-muted">
          These are estimates from a random sample of 363 notices read by hand on 16 October 2026, drawn at random within each combination of signals and, inside it, in proportion across sources; the figures are weighted by the size of each combination. One person judged the notices from the title, the buyer and the product codes. The intervals are 95 % intervals; a different sample would give different numbers, and they will drift as the sources and our rules change. The low level is a small share of the list (about 7 %), the medium level most of it (about 83 %). Since 23 October 2026 the high level needs the military code to be the notice’s main code; the sample has not been read again under that rule.
        </p>
      </ContentSection>

      <ContentSection title="Contract values and winners">
        <p className="m-0 text-body text-ink-muted">
          The amount of an award notice is one of three things, and we say which: the value of the contract awarded (a call-off under a framework agreement is a contract), the ceiling of a framework agreement or dynamic purchasing system, or the buyer’s estimate where the award states no value. Only contract values are summed for a company; ceilings and estimates are listed apart and never added, so a framework and its call-offs are never counted twice. On TED we read the notice’s own value fields: the notice value, the framework maximum and the winning tenders’ values. On Spain’s national portal the amount is the awarded amount without VAT; for a framework agreement it is the ceiling, which we read from the portal’s contracting-system field where the entry carries it, otherwise from the title (acuerdo marco, contrato basado). A call-off whose title quotes its framework’s file number is linked to the framework.
        </p>
        <p className="m-0 text-body text-ink-muted">
          Winners are named from the result notices of the defence scope on TED and from the award results of Spain’s national portal; natural persons are counted and never named. TED’s search data names the winners of notices in its current format (eForms) only. A result notice in TED’s older format (most notices before 25 October 2023, and some notices under the defence directive into 2024) names its winners in the notice document alone: for the core scope we read them from that document. Where the document names no winner, or we cannot read it, the notice shows none.
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
          'Collection is scheduled, not real time: tender sources and funding portals daily, the EU research datasets (CORDIS, EDF results) monthly. The status page shows when each source last ran.',
          'A source can fail, change format or publish late. A run that fell short is marked partial.',
          `National tender portals and feeds are collected for ${portals.count} countries (${portals.names}); elsewhere we hold only what TED carries. For Germany that is the federal notice service, from ${germanyStart}. Below-threshold procurement is often not published centrally. Known gaps are listed on the source status page.`,
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
