/**
 * WP-124: the words of /app/billing. Payments go through Creem, the merchant of record: it sells the plan, charges the VAT, issues the
 * invoices and runs the customer portal. The states are Creem's (backend dgate/billing.py, which decides what each allows).
 */
import { formatDateUtc } from './format';
import { PLAN_LABELS, type Billing, type PlanId } from './plans';
import { PLANS } from './pricing';

export const STATUS_LABEL: Record<string, string> = {
  active: 'Active',
  trialing: 'Trial',
  past_due: 'Payment failed: Creem is trying again, your plan stays open meanwhile',
  unpaid: 'Unpaid: the plan is closed until a payment goes through',
  paused: 'Paused',
  scheduled_cancel: 'Cancelled: it stays open to the end of the paid period',
  canceled: 'Cancelled',
  expired: 'Expired: the period ended without a payment',
  disputed: 'Disputed: the plan is closed while Creem settles the dispute',
};

export interface SubscriptionView { plan: PlanId; period: Billing; status: string; periodEnd: string | null }

/** "Renews on 25 Nov 2026" and the like, or null when there is nothing true to say. */
export function periodLine(s: SubscriptionView): string | null {
  if (!s.periodEnd) return null;
  const day = formatDateUtc(s.periodEnd);
  if (s.status === 'active' || s.status === 'trialing') return `Renews on ${day}.`;
  if (s.status === 'scheduled_cancel') return `Open until ${day}.`;
  if (s.status === 'past_due') return `Paid until ${day}.`;
  return null;
}

export const planName = (plan: PlanId, period?: Billing | null) => `${PLAN_LABELS[plan]}${period ? `, ${period}` : ''}`;

export interface Offer { plan: Exclude<PlanId, 'free'>; billing: Billing; label: string; price: string }

/** Every paid plan and period with its price (lib/pricing.ts), in the order of /pricing. */
export function offers(): Offer[] {
  const out: Offer[] = [];
  for (const p of PLANS) {
    if (p.id === 'free') continue;
    for (const b of ['monthly', 'yearly'] as const) {
      const price = p[b];
      if (price) out.push({ plan: p.id, billing: b, label: planName(p.id, b), price: `${price} / ${b === 'monthly' ? 'month' : 'year'}` });
    }
  }
  return out;
}

/** "3 of 20 places left" only from the API's count of now; null (nothing shown) when there is no count. */
export function foundingLine(left: number | null, cap: number): string | null {
  if (left === null) return null;
  if (left <= 0) return `All ${cap} places are taken.`;
  return `${left} of ${cap} places left.`;
}
