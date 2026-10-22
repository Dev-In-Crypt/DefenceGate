/**
 * The menu of WP-86 (UX audit of 22 October 2026, owner approved): what a visitor came to do, in their words. Every label
 * is the h1 of the page it opens (e2e/wp86.spec.ts checks it). Only routes that exist. A plain module, so the header (a
 * client component) and the footer (a server component) read the same list.
 *   - Companies opens the Won contracts tab (/companies redirects to /suppliers, next.config.ts); its two tabs are the
 *     supplier map and the organisations in EU-funded projects (components/dg/companies-tabs.tsx).
 *   - Check my company is one entry (/check) that asks first what the visitor wants and leads to the readiness check or
 *     the supplier profile.
 *   - What's new has no page of its own: its button opens its three pages.
 * Pricing and the opportunity pack are in the footer only.
 */
export interface NavLinkItem { label: string; href: string }
export interface NavItem {
  /** The id of its small menu (`sub-<key>`). */
  key: string;
  label: string;
  /** None: the item is only the button of its small menu. */
  href?: string;
  /** Other paths under this item (the menu marks it as the current one there). */
  also?: readonly string[];
  children?: readonly NavLinkItem[];
}

export const MAIN_NAV: readonly NavItem[] = [
  { key: 'tenders', label: 'Tenders', href: '/tenders', children: [{ label: 'Tenders', href: '/tenders' }, { label: 'Market overview', href: '/market' }] },
  { key: 'funding', label: 'Funding', href: '/funding' },
  { key: 'buyers', label: 'Buyers', href: '/buyers' },
  { key: 'companies', label: 'Companies', href: '/companies', also: ['/suppliers', '/organisations', '/networks'], children: [
    { label: 'Companies', href: '/companies' }, { label: 'Ukraine partners', href: '/networks/ukraine-partners' },
    { label: 'Consortium gaps', href: '/networks/consortium-gaps' },
  ] },
  { key: 'check', label: 'Check my company', href: '/check', also: ['/readiness'], children: [
    { label: 'Check my company', href: '/check' }, { label: 'Requirements', href: '/requirements' }, { label: 'Regulatory tracker', href: '/regulation' },
  ] },
  { key: 'new', label: 'What’s new', children: [
    { label: 'What changed', href: '/changes' }, { label: 'Weekly digest', href: '/digest' }, { label: 'Deadline calendar', href: '/calendar' },
  ] },
];

type FooterLink = NavLinkItem;
const group = (key: string) => MAIN_NAV.find((n) => n.key === key)!;

/**
 * The footer: the header's groups under the same names and with the same links (taken from MAIN_NAV, so they cannot drift),
 * then the pages only the footer carries. "Directory" holds the header's lists (Tenders and its Market overview, Funding,
 * Buyers). A label is the h1 of its page, except "Alerts (not open yet)", which says what the page says.
 */
export const FOOTER_GROUPS: { title: string; links: readonly FooterLink[] }[] = [
  { title: 'Directory', links: [...group('tenders').children!, { label: 'Funding', href: '/funding' }, { label: 'Buyers', href: '/buyers' }] },
  { title: group('companies').label, links: group('companies').children! },
  { title: group('check').label, links: group('check').children! },
  { title: group('new').label, links: group('new').children! },
  { title: 'About the data', links: [
    { label: 'Source status', href: '/data' }, { label: 'Methodology', href: '/methodology' }, { label: 'Where the data runs', href: '/data/sovereignty' },
    { label: 'Glossary', href: '/glossary' }, { label: 'CPV finder', href: '/cpv' },
  ] },
  { title: 'About', links: [
    { label: 'About DefenceGate', href: '/about' }, { label: 'Pricing', href: '/pricing' }, { label: 'Opportunity pack', href: '/pack' },
    { label: 'Alerts (not open yet)', href: '/alerts' },
  ] },
];
/** On the footer's legal line. */
export const LEGAL_LINKS: FooterLink[] = [{ label: 'Privacy notice', href: '/privacy' }, { label: 'Terms of use', href: '/terms' }, { label: 'Imprint', href: '/imprint' }];
