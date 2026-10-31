/**
 * The plans and prices of /pricing (owner, 25 October 2026, WP-122). EUR, excluding VAT. Nothing is on sale yet: no payment provider,
 * no legal entity, no e-mail service. `coming` marks a feature that is not built yet. `signin` (WP-131) marks one that is built and
 * opens with sign-in, which is closed until an e-mail provider exists (/alerts says the same). A feature with neither works today.
 */
export interface Feature { text: string; coming?: boolean; signin?: boolean }
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

/**
 * Whether plans can be chosen: NEXT_PUBLIC_BILLING_OPEN=1 (web/.env.example), set at build time; default off. Off: no button anywhere,
 * the page says "Opens soon". Accounts with payment through a merchant-of-record provider are a later package (owner, 25 Oct 2026).
 */
export const BILLING_OPEN = ['1', 'true'].includes(process.env.NEXT_PUBLIC_BILLING_OPEN ?? '');

export const PLANS: Plan[] = [
  // WP-155 (owner, 28 October 2026): the plan split of the company pages, reports, signals and saved searches
  { id: 'free', name: 'Free', audience: 'For everyone', features: [
    { text: 'Browse tenders, funding calls, buyers and companies' },
    { text: 'What changed in the last 14 days' },
    { text: 'Atom and calendar feeds' },
    { text: 'CSV export of the lists' },
    { text: 'Readiness check (answers saved in your browser, not on our server)' },
    { text: 'On every company page: where it wins, its share and its top 5 competitors' },
    { text: 'Company signals: the first 10 rows of each list' },
    { text: 'Contracts ending soon: the first 10 rows, and each buyer’s next 12 months in full' },
  ] },
  { id: 'pro', name: 'Pro', audience: 'For one bid manager or a small company', monthly: '€59', yearly: '€590', features: [
    { text: 'Up to 10 saved searches', signin: true },
    { text: 'E-mail alerts', signin: true },
    { text: 'Full competitor lists', signin: true },
    { text: 'Company signals: the full lists', signin: true },
    { text: 'Contracts ending soon: the full list and e-mail alerts', signin: true },
    { text: '3 company reports a month', signin: true },
    { text: 'Export of the eligibility check', signin: true },
    { text: '1 user' },
  ] },
  { id: 'team', name: 'Team', audience: 'For a company’s business development team', monthly: '€149', yearly: '€1,490', features: [
    { text: 'Everything in Pro' },
    { text: 'Up to 5 users' },
    { text: 'Shared workspace: saved searches, shortlist and follows', signin: true },
    { text: 'Up to 50 saved searches', signin: true },
    { text: '15 company reports a month', signin: true },
    { text: 'Company signals as CSV', signin: true },
    { text: 'Contracts ending soon as CSV', signin: true },
    // WP-161: the 'free today' note is true only while no plan is on sale
    { text: BILLING_OPEN ? 'Consortium gap analysis' : 'Consortium gap analysis (free on the site today, until plans go on sale)' },
    { text: 'Supplier-map export', signin: true },
  ] },
  { id: 'consultant', name: 'Consultant', audience: 'For grant and tender consultants', monthly: '€299', yearly: '€2,990', features: [
    { text: 'Everything in Team' },
    { text: 'Up to 15 client profiles', signin: true },
    { text: 'Unlimited saved searches', signin: true },
    { text: 'Unlimited company reports, with your firm’s name on them', signin: true },
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
    { text: 'Access for members, up to 50 companies' },
    { text: 'A weekly digest by e-mail in the association’s name' },
    { text: '3–5 “who to approach” reports a year for members' },
  ] },
  { name: 'White-label, API or data licence', price: 'From €12,000 / year', features: [
    { text: 'White-label', coming: true },
    { text: 'API with keys, by licence (TED notices today)' },
    { text: 'Data licence' },
  ] },
  { name: '“Who to approach” report', price: '€450–900, one-off', features: [
    { text: 'For one company: which buyers buy its products and which companies win those contracts, in the countries we cover' },
  ] },
];

/** The sign-up of one plan and billing period (the page /signup is built by the accounts package). */
export const signupHref = (plan: PlanId, billing: Billing) => `/signup?plan=${plan}&billing=${billing}`;
