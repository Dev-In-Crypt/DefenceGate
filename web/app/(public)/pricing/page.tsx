import type { Metadata } from 'next';
import { buildMetadata } from '@/lib/seo';
import { BILLING_OPEN, ON_REQUEST, PLANS, signupHref, type Billing, type Feature, type Plan } from '@/lib/pricing';
import { AutoGrid } from '@/components/dg/auto-grid';
import { Faq } from '@/components/dg/blocks';
import { buttonVariants } from '@/components/dg/button';
import { Card } from '@/components/dg/card';
import { ContentPage, PageSection } from '@/components/dg/content-page';
import { Tag } from '@/components/dg/tag';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Pricing: Free, Pro, Team and Consultant plans',
  description: 'Browsing stays free. Pro, Team, Consultant and Founding customer plans in euros, excluding VAT; none is on sale yet and nothing is charged.',
  path: '/pricing',
  noindex: true,
});

/** WP-122 (owner, 25 Oct 2026): plans and prices, none on sale yet. The data and the billing setting are lib/pricing.ts. */
function Features({ items }: { items: Feature[] }) {
  return (
    <ul className="m-0 flex list-disc flex-col gap-1.5 pl-5 text-body">
      {items.map((f) => (
        <li key={f.text}>
          {f.text}
          {f.coming && <> <span data-coming><Tag>Coming</Tag></span></>}
          {f.signin && <> <span data-signin><Tag>Opens with sign-in</Tag></span></>}
        </li>
      ))}
    </ul>
  );
}

const PER: Record<Billing, string> = { monthly: 'month', yearly: 'year' };
const billingsOf = (plan: Plan) => (['monthly', 'yearly'] as const).filter((b) => plan[b]);

function Prices({ plan }: { plan: Plan }) {
  const billings = billingsOf(plan);
  if (!billings.length) return <p className="m-0 text-h2 font-bold" data-price>€0</p>;
  return (
    <div className="flex flex-col gap-0.5">
      {billings.map((b, i) => (
        <p key={b} className={i === 0 ? 'm-0 text-h2 font-bold' : 'm-0 text-small text-ink-muted'} data-price={b}>
          {i > 0 && 'or '}{plan[b]} / {PER[b]}
        </p>
      ))}
      {plan.priceNote && <p className="m-0 text-small text-ink-muted">{plan.priceNote}</p>}
    </div>
  );
}

/**
 * One "Choose" button per billing period while billing is open. A plain <a>, not a prefetched Link: /signup is the accounts
 * package's page. Billing off: "Opens soon" in place of the buttons, never a dead link.
 */
function Choose({ plan }: { plan: Plan }) {
  const billings = billingsOf(plan);
  if (!BILLING_OPEN) return <p className="m-0 mt-auto text-small font-bold text-ink-muted" data-opens-soon>Opens soon</p>;
  return (
    <div className="mt-auto flex flex-wrap gap-2">
      {billings.map((b, i) => (
        <a key={b} href={signupHref(plan.id, b)} data-choose={b} className={buttonVariants({ variant: i === 0 ? 'primary' : 'secondary' })}>
          {`Choose ${plan.name}${billings.length > 1 ? `, ${b}` : ''}`}
        </a>
      ))}
    </div>
  );
}

const FAQ = [
  { q: 'Is anything charged now?', a: 'No. No plan is on sale and we ask for no payment details. Nothing is charged until a feature works and its terms are published.' },
  { q: 'What stays free?', a: 'Browsing tenders, funding calls, buyers and companies, what changed in the last 14 days, the Atom and calendar feeds, the CSV export, the readiness check, and on every company page where it wins, its share and its top 5 competitors.' },
  { q: 'Do the prices include VAT?', a: 'No. Prices are in euros and exclude VAT.' },
  { q: 'How do I get access?', a: BILLING_OPEN
    ? 'Choose a plan above: its button leads to sign-up for that plan and billing period.'
    : 'Plans open soon: each paid plan will then have a button to choose it.' },
];

export default function PricingPage() {
  return (
    <ContentPage
      wide
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Pricing', href: '/pricing' }]}
      title="Pricing"
      lead="Browsing stays free, and no paid plan is on sale yet: nothing is charged until a feature works and its terms are published."
    >
      <PageSection title="Plans" id="plans" intro="Prices in euros, excluding VAT.">
        <AutoGrid as="ul" min={260} fill aria-label="Plans">
          {PLANS.map((p) => (
            <Card as="li" key={p.id} className="gap-4">
              <div className="flex flex-col gap-1">
                <h3 className="m-0 text-h3">{p.name}</h3>
                <p className="m-0 text-small text-ink-muted">{p.audience}</p>
              </div>
              <Prices plan={p} />
              <Features items={p.features} />
              {p.id !== 'free' && <Choose plan={p} />}
            </Card>
          ))}
        </AutoGrid>
      </PageSection>

      <PageSection title="On request" id="on-request">
        <AutoGrid as="ul" min={260} aria-label="On request">
          {ON_REQUEST.map((o) => (
            <Card as="li" key={o.name} className="gap-4">
              <h3 className="m-0 text-h3">{o.name}</h3>
              <p className="m-0 text-body font-bold" data-price>{o.price}</p>
              <Features items={o.features} />
              <p className="m-0 mt-auto text-small font-bold text-ink-muted" data-opens-soon>On request, opens soon</p>
            </Card>
          ))}
        </AutoGrid>
      </PageSection>

      <PageSection title="Questions" id="faq">
        <Faq items={FAQ} />
      </PageSection>
    </ContentPage>
  );
}
