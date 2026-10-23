import type { Metadata } from 'next';
import Link from 'next/link';
import { buildMetadata } from '@/lib/seo';
import { Clause, ClauseGroup, ClauseList } from '@/components/dg/blocks';
import { ContentPage } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Terms of use',
  description: 'The terms on which DefenceGate is provided: what the service is, that the original source is authoritative, acceptable use, corrections and removal, and limits of liability.',
  path: '/terms',
  // Not indexed while the imprint has no provider details.
  noindex: true,
});

const P = 'm-0';

export default function TermsPage() {
  return (
    <ContentPage
      toc
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Terms of use', href: '/terms' }]}
      title="Terms of use"
      lead="Version 2.0, published 14 October 2026. The numbered terms below are the binding text. They replace version 1.1 of 13 October 2026; earlier versions are kept and available on request."
    >
      <ClauseGroup>
      <Clause n={1} title="Who provides the service and what applies">
        <p className={P}>DefenceGate is provided by the operator identified in the <Link href="/imprint" className="font-semibold">imprint</Link> (“we”, “us”). These terms govern your use of the website and of any account (“the service”). The data endpoints that serve this site are not a supported programming interface and may change or be withdrawn without notice; term 13 applies to automated use.</p>
        <p className={P}>By using the service you accept these terms. If you do not accept them, do not use the service. These terms do not create rights for anyone who is not a party to them, and they do not limit the rights of people whose personal data we process (term 20).</p>
      </Clause>

      <Clause n={2} title="Business use">
        <p className={P}>The service is intended for businesses and professionals. If you create an account you confirm that you act for a trade, business or profession and not as a consumer. We do not offer the service to consumers and we may refuse or end access where we learn that you are one.</p>
        <p className={P}>Mandatory rights that the law gives you and that cannot be excluded by contract are not affected.</p>
      </Clause>

      <Clause n={3} title="What the service is">
        <p className={P}>The service is an information service. It collects public procurement notices and funding calls from the sources listed on the <Link href="/data" className="font-semibold">source status page</Link>, normalises their fields, shows the title in English where the source supplies one (TED composes its English title; the part written by the buyer stays in the buyer’s language), labels them with automated classifications, records changes between versions and links each record to its source.</p>
        <p className={P}>We are not the author or owner of the notices and calls. We are not the publisher or the originating source of any notice. We are not a contracting authority, a funding body or a bidding platform, and we are not a party to any procurement or funding procedure. We do not submit bids or applications for you, and we do not endorse any buyer, bidder, programme or notice.</p>
      </Clause>

      <Clause n={4} title="The source is authoritative">
        <p className={P}>Each record links to its original publication. Only the original publication by the source is authoritative; for TED, only the signed notice published in the Official Journal Supplement is authentic.</p>
        <p className={P}>What we show is a copy that has been collected at a point in time and may have been reformatted, shortened, classified or linked by us. It may differ from the original. Fields that we derive, such as the defence or dual-use label or a normalised buyer name, are ours and not part of the original notice.</p>
        <p className={P}>You must check the original before you rely on any date, value, scope, condition or requirement.</p>
      </Clause>

      <Clause n={5} title="Source data and DefenceGate data">
        <p className={P}>We distinguish two kinds of content.</p>
        <ClauseList items={[
          <><strong>Source data</strong> is what a source published: its text, dates, values, codes and names. We did not create it. We do not verify it, and we are not responsible for its accuracy, completeness, lawfulness or timeliness, or for the way the source publishes or withdraws it. A record that is missing, duplicated or late because of the source is not an error of ours for which we accept responsibility to you.</>,
          <><strong>DefenceGate data</strong> is what we add: selection, normalisation of fields and names, classifications and labels, links between sources, version history, the text we wrote and the design. It is produced by automated rules and can be wrong. Term 6 and term 17 apply to it.</>,
        ]} />
        <p className={P}>The absence of a notice or call from the service is not evidence that it does not exist or that it has closed.</p>
      </Clause>

      <Clause n={6} title="Accuracy, completeness and timeliness">
        <p className={P}>The service is provided “as is” and “as available”. We collect on a schedule and make reasonable efforts, but we do not promise that any record is accurate, complete, current or free of error, or that a notice or call relevant to you is shown.</p>
        <p className={P}>Sources can fail, change, withdraw or publish late. Records can be missing, duplicated, wrongly linked or wrongly classified. The source status page shows the state of each source as we last saw it. A label is an automated indication and not a statement of fact about a buyer, a bidder or a product.</p>
      </Clause>

      <Clause n={7} title="No advice">
        <p className={P}>Nothing in the service is legal, procurement, export-control, sanctions, security-clearance, eligibility, tax, financial or investment advice. A “defence” or “dual-use” label is an automated indication and not a legal determination, and it must not be used as the basis for a compliance decision. No professional or fiduciary relationship arises from your use.</p>
        <p className={P}>Consult a qualified adviser for those questions.</p>
      </Clause>

      <Clause n={8} title="Your decisions and responsibility">
        <p className={P}>You decide whether and how to bid or apply. You are responsible for checking the source documents, deadlines and eligibility before each step that has a legal or financial effect, for complying with the law that applies to you, including export control, sanctions and security rules, and for the consequences of your decisions.</p>
        <p className={P}>We are not responsible for a missed deadline, a lost or rejected bid or application, or the cost of preparing one.</p>
      </Clause>

      <Clause n={9} title="Export control, sanctions and technical data">
        <p className={P}>The service holds commercial information about notices and calls only. It does not contain, and we do not intend to publish, technical specifications, performance or design data of any system. If you find a record that you believe contains controlled or sensitive technical data, tell us under term 19 and we will review it promptly.</p>
        <p className={P}>Showing a notice does not mean that you or anyone may supply, export or transfer anything to it. We do not screen buyers, bidders or users against sanctions lists and we do not assess whether any dealing is permitted. That is for you.</p>
      </Clause>

      <Clause n={10} title="Third-party content, links and names">
        <p className={P}>Sources, linked websites and documents belong to their publishers. We do not control them and are not responsible for their content, availability or terms, which apply when you use them. A link is not an endorsement.</p>
        <p className={P}>Names, marks and logos of authorities, companies and programmes appear only to identify them and belong to their owners. Their appearance does not mean that they are affiliated with us or endorse the service.</p>
      </Clause>

      <Clause n={11} title="Source licences and attribution">
        <p className={P}>The notices and calls shown come from public sources under their own licences and conditions. The licence and the required attribution of each source are stated on the <Link href="/data" className="font-semibold">source status page</Link>. Rights in the original notices remain with their publishers.</p>
        <p className={P}>If you reuse source content you must comply with the conditions of that source, which usually include crediting the source, not distorting the meaning and indicating changes. Where you publish material taken from DefenceGate, credit DefenceGate and the original source and do not present the material as official or as endorsed by anyone.</p>
      </Clause>

      <Clause n={12} title="Our rights">
        <p className={P}>We, or our licensors, hold the rights in what we add: the selection and arrangement of the records, the normalisation, the classification and labels, the version archive, the text we wrote, the design and the software, including any database right that arises in the compilation. We do not claim any right in the source data as published by its source, and nothing in these terms restricts what a source’s own licence lets you do with a notice you take from that source.</p>
        <p className={P}>We grant you a limited, non-exclusive, non-transferable and revocable right to use the service and to use extracts for your own internal business purposes. Nothing in these terms restricts what the law allows a lawful user to do.</p>
      </Clause>

      <Clause n={13} title="Acceptable use">
        <p className={P}>You must not:</p>
        <ClauseList items={[
          'access the service by automated means (crawlers, scrapers, scripts, bots, agents or bulk download) except the CSV export, the calendar feed and the Atom feeds the site offers, used within their limits, search-engine indexing that respects our robots file, or as we have agreed in writing, or exceed the rate limits we apply;',
          'use the service or any part of our compilation to train, fine-tune, evaluate or feed an artificial-intelligence or machine-learning system, or to supply a retrieval or chat tool with it, without our written agreement;',
          'circumvent a limit, access control or security measure, or probe the service for weaknesses;',
          'extract or re-use a substantial part of DefenceGate data to build, feed or operate a competing or redistributed database or service, or resell or sublicense it. This does not restrict what you may do with source data that you take from the source itself;',
          'overload the service or disrupt its operation;',
          'present the service or its content as official, or as endorsed by a source, authority or institution;',
          'use the service for unlawful purposes, including to breach export-control or sanctions rules, or to identify or contact individuals unlawfully;',
          'share your account or credentials with others.',
        ]} />
        <p className={P}>These are terms of use, not a description of what the servers technically prevent: that an endpoint answers without a key or a sign-in is not permission to use it in a way this term excludes. We may limit, suspend or block access that breaches this term, and we may keep the logs needed to show it.</p>
      </Clause>

      <Clause n={14} title="Accounts">
        <p className={P}>Where accounts are offered: give accurate information, keep your credentials secret, and tell us promptly if you suspect misuse. You are responsible for activity under your account. By signing in or creating an account you confirm that you accept these terms and the <Link href="/privacy" className="font-semibold">privacy notice</Link>. You may close your account at any time. We may refuse or suspend an account for breach of these terms or misuse.</p>
      </Clause>

      <Clause n={15} title="Alerts and saved searches">
        <p className={P}>Where alerts or saved searches are offered they are a convenience, run on automated criteria and are best effort. They can be late, incomplete or missed. Do not use them as your only means of monitoring a procurement or funding opportunity.</p>
      </Clause>

      <Clause n={16} title="Availability, changes and events beyond our control">
        <p className={P}>We may maintain, change, limit or discontinue any part of the service. Where a change materially affects a feature you rely on we will give reasonable notice where practical. Paid features, if introduced, will be announced with their own terms before they are offered.</p>
        <p className={P}>We are not liable for a failure or delay caused by an event beyond our reasonable control, including a failure, change or withdrawal of a source, an outage of a hosting, network or mail provider, an attack on the service, or an act of an authority.</p>
      </Clause>

      <Clause n={17} title="Liability">
        <p className={P}>The service is provided free of charge unless we state otherwise. To the extent the law allows:</p>
        <ClauseList items={[
          'we are not liable for source data, for third-party content, or for decisions you take on the basis of the service;',
          'we are not liable for indirect or consequential loss, loss of profit, loss of contracts, bids or opportunities, loss of goodwill or loss of data;',
          'our total liability to you arising from or in connection with the service is limited to EUR 100 for free use and, if a paid tier is ever offered, for paid use to the fees you paid for the service in the twelve months before the event;',
          'you must notify a claim to us in writing within 90 days of becoming aware of the event, and in any case within 12 months of it, unless the law gives you longer.',
        ]} />
        <p className={P}>These limits also protect our staff, contractors and suppliers. Nothing in these terms limits or excludes liability for intent, gross negligence, fraud, injury to life, body or health, or any liability that cannot be limited or excluded by law.</p>
      </Clause>

      <Clause n={18} title="Your responsibility for your use">
        <p className={P}>If you are a business user and your use of the service breaches these terms or the law, and a third party brings a claim against us as a result, you will, as far as the law allows, compensate us for the resulting loss, including reasonable legal costs, provided that we tell you of the claim promptly, let you take part in its defence where the law allows, and do not settle it without asking you. This term does not apply to consumers.</p>
      </Clause>

      <Clause n={19} title="Corrections, removal and complaints">
        <p className={P}>To report a mistake, request a correction or removal, tell us that a record contains technical data, raise a rights or data protection matter, or give notice of a claim, write to the contact in the <Link href="/imprint" className="font-semibold">imprint</Link>.</p>
        <p className={P}>Tell us, as far as you can: the record (its address on the site), what is wrong and why, the evidence, who you are and in what capacity (for example the buyer, the supplier named, the holder of a right, or a person named in a notice), and how to reach you.</p>
        <p className={P}>What we do:</p>
        <ClauseList items={[
          'we check the record against the source and answer without undue delay, and in any case within one month for a data protection request (extended where the law allows);',
          'if our copy differs from the source we correct it. If the source itself is wrong, the publisher must correct it, and our record follows on the next collection;',
          'if a notice, label or link is the subject of a valid objection, a valid rights claim or a well-founded report of technical data, we will remove or correct it without undue delay after verifying the request;',
          'where our record changes, the change is recorded as a version. The earlier state stays in our private archive, as described in the privacy notice, unless the law requires us to erase or redact it, in which case we do so.',
        ]} />
        <p className={P}>Requests about personal data are also handled as described in the <Link href="/privacy" className="font-semibold">privacy notice</Link>. We may ask for proof of identity or of authority where that is needed to avoid disclosing data to the wrong person.</p>
      </Clause>

      <Clause n={20} title="Personal data and people named in notices">
        <p className={P}>Public notices sometimes name a contact person. We do not collect the contact fields a source publishes and we remove e-mail addresses from free text; a name or number typed into a description by the publisher is not removed. If you are named in a record and want it removed or corrected, use term 19. How we process personal data, on what basis and what rights you have is described in the <Link href="/privacy" className="font-semibold">privacy notice</Link>. Nothing in these terms limits those rights, and a person named in a notice is not bound by these terms.</p>
      </Clause>

      <Clause n={21} title="Suspension and end">
        <p className={P}>We may suspend or end your access (and, where accounts are offered, your account) for breach of these terms, misuse, legal reasons or if we discontinue the service. You may stop using the service at any time. Terms that by their nature continue, including terms 3 to 13, 17 and 18, continue.</p>
      </Clause>

      <Clause n={22} title="Changes to these terms">
        <p className={P}>We may change these terms. The current version and its date are on this page, and earlier versions are kept and available on request. For a material change we will announce it on this page and, where accounts are offered, to account holders by e-mail at least 30 days before it takes effect. If you continue to use the service after that date you accept the change; if you do not accept it, stop using the service and, where you have an account, close it before then.</p>
      </Clause>

      <Clause n={23} title="Governing law and courts">
        <p className={P}>For business users these terms are governed by the law of the country in which the operator has its seat as stated in the <Link href="/imprint" className="font-semibold">imprint</Link>, excluding its conflict-of-laws rules and the UN Convention on Contracts for the International Sale of Goods. The courts of that place have jurisdiction, as far as the law allows.</p>
        <p className={P}>If you are nevertheless a consumer, the mandatory consumer protection law of the country where you live applies, and you may bring proceedings in the courts there.</p>
      </Clause>

      <Clause n={24} title="General">
        <p className={P}>If a provision is invalid, the rest remains in force and the invalid part is replaced by the valid provision closest to its purpose. Our failure to enforce a right is not a waiver. These terms are the whole agreement on the service; a written agreement signed by us takes priority over them to the extent it says so. Notices to you may be given by e-mail or on this page. The English text prevails over any translation. We may transfer our rights and duties to a successor of the service.</p>
      </Clause>
      </ClauseGroup>
    </ContentPage>
  );
}
