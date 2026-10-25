/**
 * The menu (WP-117, owner's choice of 25 October 2026, after WP-86): four items, by the three questions a visitor brings (what is
 * open, who is already in, can I take part) and What's new. Every link label is the h1 of the page it opens (e2e/wp86.spec.ts
 * checks it). Only routes that exist. A plain module, so the header (a client component) and the footer (a server component)
 * read the same list.
 *   - A group whose label is not the h1 of a page ("Tenders & funding", "Partners", "What's new") has no href: its button opens
 *     its small menu. "Check my company" is the h1 of /check, so it is a link with a button for its other pages.
 *   - Companies opens the Won contracts tab (/companies redirects to /suppliers, next.config.ts); its two tabs are the
 *     supplier map and the organisations in EU-funded projects (components/dg/companies-tabs.tsx).
 *   - Check my company is one entry (/check) that asks first what the visitor wants and leads to the readiness check or
 *     the supplier profile.
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
  { key: 'open', label: 'Tenders & funding', children: [
    { label: 'Tenders', href: '/tenders' }, { label: 'Funding', href: '/funding' }, { label: 'Buyers', href: '/buyers' }, { label: 'Market overview', href: '/market' },
  ] },
  { key: 'partners', label: 'Partners', also: ['/suppliers', '/organisations', '/networks'], children: [
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
 * The footer: the header's four groups under the same names and with the same links (taken from MAIN_NAV, so they cannot drift),
 * then the pages only the footer carries. A link label is the h1 of its page, except "Alerts (not open yet)", which says what the
 * page says.
 */
export const FOOTER_GROUPS: { title: string; links: readonly FooterLink[] }[] = [
  { title: group('open').label, links: group('open').children! },
  { title: group('partners').label, links: group('partners').children! },
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
