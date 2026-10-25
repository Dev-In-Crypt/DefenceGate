/**
 * WP-123: the plan a visitor picked on the pricing page (WP-122 buttons: /signup?plan=<id>&billing=<monthly|yearly>), carried
 * through registration and the confirmation link and said again. A choice only: nothing is charged and the plan in force stays
 * Free until payment opens (WP-124). The ids match the API (`accounts.PLANS`, `accounts.BILLINGS`).
 */
export const PLAN_LABELS = { free: 'Free', pro: 'Pro', team: 'Team', consultant: 'Consultant', founding: 'Founding customer' } as const;
export type PlanId = keyof typeof PLAN_LABELS;
export type Billing = 'monthly' | 'yearly';

export interface PlanChoice { plan: PlanId; billing: Billing | null }

const first = (v: unknown): unknown => (Array.isArray(v) ? v[0] : v);

/** The choice from a query string or a form, or null for anything that is not one of the ids. Free has no billing period. */
export function readPlanChoice(plan: unknown, billing: unknown): PlanChoice | null {
  const p = first(plan);
  const b = first(billing);
  if (typeof p !== 'string' || !Object.hasOwn(PLAN_LABELS, p)) return null;
  const id = p as PlanId;
  if (id === 'free') return { plan: id, billing: null };
  return { plan: id, billing: b === 'monthly' || b === 'yearly' ? b : null };
}

/** "You chose Pro, monthly. Payment opens soon." / "You chose Free." */
export function planSentence(c: PlanChoice): string {
  if (c.plan === 'free') return 'You chose Free.';
  return `You chose ${PLAN_LABELS[c.plan]}${c.billing ? `, ${c.billing}` : ''}. Payment opens soon.`;
}
