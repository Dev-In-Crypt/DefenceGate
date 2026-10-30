import type { Metadata } from 'next';
import Link from 'next/link';
import { dataOrNull, getAccountStatus, getBilling, getCurrentUser } from '@/lib/account';
import { foundingLine, offers, periodLine, planName, STATUS_LABEL } from '@/lib/billing';
import { billingOpen, PLAN_LABELS, readPlanChoice } from '@/lib/plans';
import { BILLING_OPEN } from '@/lib/pricing';
import { Button } from '@/components/dg/button';
import { AppHeader, Block, LoadFailed, Notice } from '@/components/account/ui';
import { continueToPayment, manageSubscription } from '../actions';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = { title: 'Billing', robots: { index: false, follow: false } };

type Props = { searchParams: Promise<{ n?: string | string[]; checkout?: string | string[]; plan?: string | string[]; billing?: string | string[] }> };

/**
 * WP-124: the plan, its state and renewal date, "Manage subscription" (Creem's customer portal: cancel, invoices, payment method)
 * and, for an account without a plan, "Continue to payment" for the plan chosen on the pricing page. Closed (the default): every
 * part that would take a payment says "Payment opens soon" and no checkout is created.
 */
export default async function BillingPage({ searchParams }: Props) {
  const [me, result, status, q] = await Promise.all([getCurrentUser(), getBilling(), getAccountStatus(), searchParams]);
  const state = dataOrNull(result);
  if (!me || !state) return <LoadFailed href="/app/billing" />;
  const open = billingOpen(BILLING_OPEN, status) && state.open;
  const sub = state.subscription;
  const asked = readPlanChoice(q.plan, q.billing) ?? me.planChoice;
  const chosen = asked && asked.plan !== 'free' && asked.billing ? offers().find((o) => o.plan === asked.plan && o.billing === asked.billing) : undefined;
  const founding = foundingLine(state.foundingLeft, state.foundingCap);
  const foundingFull = state.foundingLeft !== null && state.foundingLeft <= 0;
  const returned = (Array.isArray(q.checkout) ? q.checkout[0] : q.checkout) === 'done';
  const others = offers().filter((o) => !(o.plan === chosen?.plan && o.billing === chosen?.billing) && !(o.plan === 'founding' && foundingFull));

  return (
    <>
      <AppHeader title="Billing"
        lead="Payments are handled by Creem, our merchant of record: Creem sells the plan, charges the VAT and sends the invoices. We never see your card." />
      <Notice code={q.n} />
      {returned && state.plan === 'free' && (
        <p role="status" className="m-0 rounded-md bg-surface p-4 text-small font-semibold" data-confirming>
          Thank you. Your payment is being confirmed: your plan opens here as soon as Creem tells us, usually within a minute. Reload this page to see it.
        </p>
      )}

      <Block id="plan" title="Your plan">
        <p className="m-0 text-body" data-current-plan>
          {/* WP-158: a plan with no subscription comes from an association's licence */}
          {!sub && state.plan !== 'free' && me.association
            ? <>Your plan is {PLAN_LABELS[state.plan]}, through your association&apos;s licence (<Link href="/app/association" className="font-semibold">Association</Link>).</>
            : <>Your plan is {sub && state.plan !== 'free' ? planName(sub.plan, sub.period) : 'Free'}.</>}
          {sub && <> Status: <span data-status={sub.status}>{STATUS_LABEL[sub.status] ?? sub.status}</span>.</>}
          {sub && periodLine(sub) && <> {periodLine(sub)}</>}
        </p>
        {sub?.refundedAt && <p className="m-0 text-small text-ink-muted">A refund was made. Creem sends its receipt by e-mail.</p>}
        {sub?.canManage && (
          <form action={manageSubscription} className="flex flex-col items-start gap-3">
            <p className="m-0 max-w-prose text-body text-ink-muted">
              In Creem&rsquo;s customer portal you can cancel the subscription, change the payment method and get your invoices.
              A cancellation there takes effect at once; your saved searches stay, but they stop running and send no alerts.
            </p>
            <Button type="submit" variant="secondary">Manage subscription</Button>
          </form>
        )}
      </Block>

      {state.plan === 'free' && (
        <Block id="pay" title="Choose a plan">
          {!open ? (
            <p className="m-0 text-body font-bold text-ink-muted" data-opens-soon>Payment opens soon. Nothing is charged until then.</p>
          ) : (
            <div className="flex flex-col gap-5">
              {state.testMode && <p className="m-0 text-small font-semibold" data-test-mode>Test mode: no real payment is taken.</p>}
              {chosen && !(chosen.plan === 'founding' && foundingFull) && (
                <form action={continueToPayment} className="flex flex-col items-start gap-3 rounded-md bg-surface-inset p-4" data-chosen>
                  <p className="m-0 text-body">You chose <strong>{chosen.label}</strong>: {chosen.price}, excluding VAT. Creem adds the VAT at checkout.</p>
                  <input type="hidden" name="plan" value={chosen.plan} />
                  <input type="hidden" name="billing" value={chosen.billing} />
                  <Button type="submit">Continue to payment</Button>
                </form>
              )}
              {founding && <p className="m-0 text-small text-ink-muted" data-founding-left>Founding customer: {founding}</p>}
              <ul className="m-0 flex list-none flex-col gap-2 p-0" aria-label={chosen ? 'Other plans' : 'Plans'}>
                {others.map((o) => (
                  <li key={`${o.plan}-${o.billing}`}>
                    <form action={continueToPayment} className="flex flex-wrap items-center gap-3">
                      <input type="hidden" name="plan" value={o.plan} />
                      <input type="hidden" name="billing" value={o.billing} />
                      <Button type="submit" variant="secondary">{`Pay for ${o.label}`}</Button>
                      <span className="text-small text-ink-muted">{o.price}, excluding VAT</span>
                    </form>
                  </li>
                ))}
              </ul>
              <p className="m-0 text-small text-ink-muted">What each plan includes: <Link href="/pricing" className="font-semibold">Pricing</Link>.</p>
            </div>
          )}
        </Block>
      )}
    </>
  );
}
