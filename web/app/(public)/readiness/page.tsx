import type { Metadata } from 'next';
import { getRequirements } from '@/lib/readiness-api';
import { buildMetadata } from '@/lib/seo';
import { Callout } from '@/components/dg/blocks';
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
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Readiness check', href: '/readiness' }]}
      title="Readiness check"
      lead="Five short sets of questions about your company. For each programme you get a verdict, and for each rule the reason and the text of the source. Then an ordered list of what to obtain, who issues it, and what it costs."
    >
      <Callout title="Your answers stay in this browser">
        <p className="m-0">They are saved in this browser, on this device. There is no account and no copy on our server.</p>
        <p className="m-0">The only thing that leaves your browser is the request that computes the verdict: your answers to the questions the rules read, sent to the rules engine. The server does not store or log them. The company name and size you may enter below are never sent.</p>
      </Callout>

      <Wizard requirements={requirements} />

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
