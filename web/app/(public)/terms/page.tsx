import type { Metadata } from 'next';
import Link from 'next/link';
import { buildMetadata } from '@/lib/seo';
import { Callout, Clause, ClauseList } from '@/components/dg/blocks';
import { ContentPage } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Terms of use',
  description: 'The terms on which DefenceGate is provided: what the service is, that the original source is authoritative, acceptable use and limits of liability.',
  path: '/terms',
});

const P = 'm-0';

export default function TermsPage() {
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Terms of use', href: '/terms' }]}
      title="Terms of use"
      lead="Version 1.1, published 13 October 2026. The short version comes first; the numbered terms below are the binding text."
    >
      <Callout title="In short">
        <ClauseList items={[
          'DefenceGate is an information service for business use. It republishes public notices and funding calls and links each one to its original source.',
          'The original source is authoritative. What we show can be late, incomplete or wrong. Check the source before you act.',
          'We give no legal, procurement, export-control or financial advice and we are not affiliated with any publisher, government or EU body.',
          'You use the service at your own responsibility. Our liability is limited as far as the law allows.',
          'Do not scrape around our limits or resell the data as a competing database.',
          'To report a mistake or ask for a correction, see term 17.',
        ]} />
      </Callout>

      <Clause n={1} title="Who provides the service and what applies">
        <p className={P}>DefenceGate is provided by the operator named in the <Link href="/imprint" className="font-semibold">imprint</Link> (“we”, “us”). These terms govern your use of the website and of any account (“the service”). The data endpoints that serve this site are not a supported programming interface and may change or be withdrawn without notice; term 11 applies to automated use.</p>
        <p className={P}>By using the service you accept these terms. If you do not accept them, do not use the service.</p>
      </Clause>

      <Clause n={2} title="Business use">
        <p className={P}>The service is intended for businesses and professionals. If you create an account you confirm that you act for a trade, business or profession and not as a consumer.</p>
        <p className={P}>Mandatory rights that the law gives you and that cannot be excluded by contract are not affected.</p>
      </Clause>

      <Clause n={3} title="What the service is">
        <p className={P}>The service is an information service. It collects public procurement notices and funding calls from the sources listed on the <Link href="/data" className="font-semibold">source status page</Link>, normalises their fields, shows the title in English where the source supplies one (TED composes its English title; the part written by the buyer stays in the buyer’s language), labels them with automated classifications, records changes between versions and links each record to its source.</p>
        <p className={P}>We are not the publisher of any notice. We are not a contracting authority, a funding body or a bidding platform, and we are not a party to any procurement or funding procedure. We do not submit bids or applications for you, and we do not endorse any buyer, bidder, programme or notice.</p>
      </Clause>

      <Clause n={4} title="The source is authoritative">
        <p className={P}>Each record links to its original publication. Only the original publication by the source is authoritative.</p>
        <p className={P}>What we show is a copy that has been collected at a point in time and may have been reformatted, shortened, classified or linked by us. It may differ from the original. Fields that we derive, such as the defence or dual-use label or a normalised buyer name, are ours and not part of the original notice.</p>
        <p className={P}>You must check the original before you rely on any date, value, scope, condition or requirement.</p>
      </Clause>

      <Clause n={5} title="Accuracy, completeness and timeliness">
        <p className={P}>The service is provided “as is” and “as available”. We collect on a schedule and make reasonable efforts, but we do not promise that any record is accurate, complete, current or free of error, or that a notice or call relevant to you is shown.</p>
        <p className={P}>Sources can fail, change, withdraw or publish late. Records can be missing, duplicated, wrongly linked or wrongly classified. The source status page shows the state of each source as we last saw it.</p>
      </Clause>

      <Clause n={6} title="No advice">
        <p className={P}>Nothing in the service is legal, procurement, export-control, sanctions, security-clearance, eligibility, tax, financial or investment advice. A “defence” or “dual-use” label is an automated indication and not a legal determination, and it must not be used as the basis for a compliance decision.</p>
        <p className={P}>Consult a qualified adviser for those questions.</p>
      </Clause>

      <Clause n={7} title="Your decisions and responsibility">
        <p className={P}>You decide whether and how to bid or apply. You are responsible for checking the source documents, deadlines and eligibility, for complying with the law that applies to you, including export control, sanctions and security rules, and for the consequences of your decisions.</p>
        <p className={P}>We are not responsible for a missed deadline, a lost or rejected bid or application, or the cost of preparing one.</p>
      </Clause>

      <Clause n={8} title="Third-party content and links">
        <p className={P}>Sources, linked websites and documents belong to their publishers. We do not control them and are not responsible for their content, availability or terms, which apply when you use them.</p>
      </Clause>

      <Clause n={9} title="Source licences and attribution">
        <p className={P}>The notices and calls shown come from public sources under their own licences and conditions. The licence and the required attribution of each source are stated on the source status page. Rights in the original notices remain with their publishers.</p>
        <p className={P}>If you reuse source content you must comply with the conditions of that source, which usually include crediting the source, not distorting the meaning and indicating changes. Where you publish material taken from DefenceGate, credit DefenceGate and the original source and do not present the material as official or as endorsed by anyone.</p>
      </Clause>

      <Clause n={10} title="Our rights">
        <p className={P}>The selection, arrangement, normalisation, classification, version archive, text we wrote, design and software are ours or our licensors’, including any database right. We grant you a limited, non-exclusive, non-transferable and revocable right to use the service and to use extracts for your own internal business purposes.</p>
        <p className={P}>Nothing in these terms restricts what the law allows a lawful user to do.</p>
      </Clause>

      <Clause n={11} title="Acceptable use">
        <p className={P}>You must not:</p>
        <ClauseList items={[
          'access the service by automated means (crawlers, scrapers, scripts or bulk download) except the CSV export and the calendar feed the site offers, used within their limits, or as we have agreed in writing, or exceed the rate limits we apply;',
          'circumvent a limit, access control or security measure, or probe the service for weaknesses;',
          'extract or re-use a substantial part of the service to build, feed or operate a competing or redistributed database or service, or resell or sublicense it;',
          'overload the service or disrupt its operation;',
          'present the service or its content as official, or as endorsed by a source, authority or institution;',
          'use the service for unlawful purposes, including to breach export-control or sanctions rules, or to identify or contact individuals unlawfully;',
          'share your account or credentials with others.',
        ]} />
        <p className={P}>We may limit, suspend or block access that breaches this term.</p>
      </Clause>

      <Clause n={12} title="Accounts">
        <p className={P}>Where accounts are offered: give accurate information, keep your credentials secret, and tell us promptly if you suspect misuse. You are responsible for activity under your account. You may close your account at any time. We may refuse or suspend an account for breach of these terms or misuse.</p>
      </Clause>

      <Clause n={13} title="Alerts and saved searches">
        <p className={P}>Where alerts or saved searches are offered they are a convenience, run on automated criteria and are best effort. They can be late, incomplete or missed. Do not use them as your only means of monitoring a procurement or funding opportunity.</p>
      </Clause>

      <Clause n={14} title="Availability and changes to the service">
        <p className={P}>We may maintain, change, limit or discontinue any part of the service. Where a change materially affects a feature you rely on we will give reasonable notice where practical. Paid features, if introduced, will be announced with their own terms before they are offered.</p>
      </Clause>

      <Clause n={15} title="Liability">
        <p className={P}>The service is provided free of charge unless we state otherwise. To the extent the law allows:</p>
        <ClauseList items={[
          'we are not liable for indirect or consequential loss, loss of profit, loss of contracts, bids or opportunities, loss of goodwill or loss of data;',
          'our total liability to you arising from or in connection with the service is limited to EUR 100 for free use and, if a paid tier is ever offered, for paid use to the fees you paid for the service in the twelve months before the event.',
        ]} />
        <p className={P}>Nothing in these terms limits or excludes liability for intent, gross negligence, fraud, injury to life, body or health, or any liability that cannot be limited or excluded by law.</p>
      </Clause>

      <Clause n={16} title="Your responsibility for your use">
        <p className={P}>If your use of the service breaches these terms or the law and a third party brings a claim against us as a result, you will, as far as the law allows, compensate us for the resulting loss, including reasonable legal costs.</p>
      </Clause>

      <Clause n={17} title="Corrections, removal and complaints">
        <p className={P}>To report a mistake, request a correction or removal, or raise a rights or data protection matter, write to the contact in the <Link href="/imprint" className="font-semibold">imprint</Link>. Tell us the record, what is wrong and, where you can, the evidence.</p>
        <p className={P}>We check the record against the source. If our copy differs from the source we correct it. If the source itself is wrong, the publisher must correct it, and our record follows on the next collection. Requests about personal data are handled as described in the <Link href="/privacy" className="font-semibold">privacy notice</Link>.</p>
      </Clause>

      <Clause n={18} title="Suspension and end">
        <p className={P}>We may suspend or end your access (and, where accounts are offered, your account) for breach of these terms, misuse, legal reasons or if we discontinue the service. You may stop using the service at any time. Terms that by their nature continue, including terms 4 to 11, 15 and 16, continue.</p>
      </Clause>

      <Clause n={19} title="Changes to these terms">
        <p className={P}>We may change these terms. The current version and its date are on this page. For a material change we will announce it on this page and, where accounts are offered, to account holders by e-mail at least 30 days before it takes effect. If you continue to use the service after that date you accept the change; if you do not accept it, stop using the service and, where you have an account, close it before then.</p>
      </Clause>

      <Clause n={20} title="Governing law and courts">
        <p className={P}>For business users these terms are governed by the law of the country in which the operator has its seat as stated in the imprint, excluding its conflict-of-laws rules and the UN Convention on Contracts for the International Sale of Goods. The courts of that place have jurisdiction, as far as the law allows.</p>
        <p className={P}>If you are nevertheless a consumer, the mandatory consumer protection law of the country where you live applies, and you may bring proceedings in the courts there.</p>
      </Clause>

      <Clause n={21} title="General">
        <p className={P}>If a provision is invalid, the rest remains in force and the invalid part is replaced by the valid provision closest to its purpose. Our failure to enforce a right is not a waiver. These terms are the whole agreement on the service. The English text prevails over any translation. We may transfer our rights and duties to a successor of the service.</p>
      </Clause>
    </ContentPage>
  );
}
