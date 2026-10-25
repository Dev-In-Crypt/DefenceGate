/**
 * The plans and prices of /pricing (owner, 25 October 2026, WP-122). EUR, excluding VAT. Nothing is on sale yet: no payment provider,
 * no legal entity, no e-mail service. `coming` marks a feature that does not work for customers today (accounts and alerts are built,
 * but sign-in is closed until an e-mail provider exists, so everything that needs an account is coming too).
 */
export interface Feature { text: string; coming?: boolean }
export type PlanId = 'free' | 'pro' | 'team' | 'consultant' | 'founding';
export type Billing = 'monthly' | 'yearly';
export interface Plan {
  id: PlanId;
  name: string;
  /** Who it is for. */
  audience: string;
  /** Prices in euros as shown ("€59"); a paid plan has a button per price it has. Free has neither. */
  monthly?: string;
  yearly?: string;
  /** What is fixed about the price (Founding customer). */
  priceNote?: string;
  features: Feature[];
}

export const PLANS: Plan[] = [
  { id: 'free', name: 'Free', audience: 'For everyone', features: [
    { text: 'Browse tenders, funding calls, buyers and companies' },
    { text: 'What changed in the last 14 days' },
    { text: 'Atom and calendar feeds' },
    { text: 'CSV export of the lists' },
    { text: 'Readiness check (your answers stay in your browser)' },
  ] },
  { id: 'pro', name: 'Pro', audience: 'For one bid manager or a small company', monthly: '€59', yearly: '€590', features: [
    { text: 'Saved searches', coming: true },
    { text: 'E-mail alerts', coming: true },
    { text: 'Export of the eligibility check', coming: true },
    { text: '1 user' },
  ] },
  { id: 'team', name: 'Team', audience: 'For a company’s business development team', monthly: '€149', yearly: '€1,490', features: [
    { text: 'Up to 5 users' },
    { text: 'Shared workspace', coming: true },
    { text: 'Consortium gap analysis', coming: true },
    { text: 'Supplier-map export', coming: true },
  ] },
  { id: 'consultant', name: 'Consultant', audience: 'For grant and tender consultants', monthly: '€299', yearly: '€2,990', features: [
    { text: 'Up to 15 client profiles', coming: true },
    { text: 'Branded PDF reports', coming: true },
  ] },
  { id: 'founding', name: 'Founding customer', audience: 'For the first 20 customers', yearly: '€390', priceNote: 'Price fixed', features: [
    { text: 'Everything in Pro' },
    { text: 'A direct line to the founder' },
  ] },
];

export interface OnRequest { name: string; price: string; features: Feature[] }

export const ON_REQUEST: OnRequest[] = [
  { name: 'Call & Consortium Brief', price: '€450–900, one-off', features: [
    { text: 'For one call: a shortlist of 10–20 partners, the eligibility conditions and the consortium’s gaps' },
  ] },
  { name: 'Cluster or association licence', price: '€4,900–9,900 / year', features: [
    { text: 'Access for members, up to 50 companies', coming: true },
    { text: 'A co-branded digest', coming: true },
  ] },
  { name: 'White-label, API or data licence', price: 'From €12,000 / year', features: [
    { text: 'White-label', coming: true },
    { text: 'API (offered only here)', coming: true },
    { text: 'Data licence' },
  ] },
];

/**
 * Whether plans can be chosen: NEXT_PUBLIC_BILLING_OPEN=1 (web/.env.example), set at build time; default off. Off: no button anywhere,
 * the page says "Opens soon". Accounts with payment through a merchant-of-record provider are a later package (owner, 25 Oct 2026).
 */
export const BILLING_OPEN = ['1', 'true'].includes(process.env.NEXT_PUBLIC_BILLING_OPEN ?? '');

/** The sign-up of one plan and billing period (the page /signup is built by the accounts package). */
export const signupHref = (plan: PlanId, billing: Billing) => `/signup?plan=${plan}&billing=${billing}`;
