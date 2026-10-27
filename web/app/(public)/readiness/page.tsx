import type { Metadata } from 'next';
import Link from 'next/link';
import { LockKeyhole } from 'lucide-react';
import { getRequirements } from '@/lib/readiness-api';
import { buildMetadata } from '@/lib/seo';
import { WHAT_IS_SENT } from '@/lib/sent-copy';
import { STEPS_QUESTIONS, SUPPLIER_QUESTIONS, rangeWords } from '@/lib/question-counts';
import { NoteLine } from '@/components/dg/blocks';
import { AboutData } from '@/components/dg/about-data';
import { ContentPage, ContentSection } from '@/components/dg/content-page';
import { Wizard, type WizardRequirement } from '@/components/readiness/wizard';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Readiness check: may your company take part in EDF, EDIP and SAFE?',
  description: 'Answer a few questions about your company and see, rule by rule, whether EDF, EDIP and SAFE let it take part, what blocks it and what to obtain first.',
  path: '/readiness',
});

async function requirementNames(): Promise<WizardRequirement[]> {
  try {
    return (await getRequirements()).items.map((r) => ({ code: r.code, name: r.name, summary: r.summary }));
  } catch {
    return [];       // the wizard then names the items by their codes; the check itself does not need the names
  }
}

export default async function ReadinessPage() {
  const requirements = await requirementNames();
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Check my company', href: '/check' }, { label: 'Readiness check', href: '/readiness' }]}
      title="Readiness check"
      lead={`See whether your company can take part in EU defence funding and what to obtain first: five sets of questions, ${rangeWords(STEPS_QUESTIONS)} in all.`}
    >
      {/* WP-149: the first question comes right under the title; the privacy statement and the scope are one line each beside it. */}
      <div className="flex min-w-0 flex-col gap-4">
        <div className="flex min-w-0 flex-col">
          {/* WP-88: the line says what is true of the whole flow (the paragraph behind it says what is sent once); the detail is collapsed. */}
          <NoteLine icon={LockKeyhole} data-privacy-line more={
            <AboutData summary="What is kept and what is sent">
              <p className="m-0">They are saved in this browser, on this device. There is no account and no copy on our server. The verdict, each rule with its reason and the text of its source, and an ordered list of what to obtain, who issues it and what it costs, are worked out from them.</p>
              {/* WP-131: the list is made from the two request builders (lib/sent-copy.ts), so it cannot drift from what is sent */}
              <p className="m-0" data-what-is-sent>{WHAT_IS_SENT}</p>
            </AboutData>
          }>Your answers are not stored on our server.</NoteLine>
          {/* WP-65: the second way in. The funding wizard below is unchanged. */}
          <nav aria-label="Which check">
            <NoteLine>
              For EU defence funding (EDF, EDIP and SAFE). Something else?{' '}
              <Link href="/readiness/supplier" className="font-semibold">I make parts or materials and want to supply defence buyers (one page, {rangeWords(SUPPLIER_QUESTIONS)} questions)</Link>
              {' · '}
              <Link href="/readiness/spain-automotive" className="font-semibold">A civilian manufacturer in Spain</Link>
            </NoteLine>
          </nav>
        </div>
        <Wizard requirements={requirements} />
      </div>

      <ContentSection title="What it checks">
        <p className="m-0 text-body text-ink-muted">
          The conditions the regulations set on a company: the European Defence Fund (Regulation (EU) 2021/697), the European Defence Industry Programme and its Ukraine Support Instrument (Regulation (EU) 2025/2643), the SAFE instrument (Council Regulation (EU) 2025/1106), and what NATO and NSPA supply asks for. It also lists the export control, exporter registration and security clearance steps that depend on what you make and where you sell.
        </p>
      </ContentSection>
      <ContentSection title="What it does not do">
        <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-body text-ink-muted">
          <li>It is not legal advice and does not replace the call text or the contracting authority. A call can set conditions of its own.</li>
          <li>It checks the company, not a consortium, a proposal or a product. The 35 % origin rule of SAFE is about one end product: you answer for the main one.</li>
          <li>AQAP quality certification is not an eligibility condition of EDF, EDIP or SAFE. It enters through contracts that name it, so it is listed as something a contract may ask for.</li>
          <li>No environmental, social or governance requirement is encoded, because none specific to these programmes was confirmed in a primary source.</li>
          <li>It does not ask about the technical detail of any product, and never will.</li>
        </ul>
      </ContentSection>
    </ContentPage>
  );
}
