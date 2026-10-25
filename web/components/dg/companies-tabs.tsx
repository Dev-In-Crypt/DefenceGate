import Link from 'next/link';
import { cn } from '@/lib/utils';
import { MAIN_NAV } from '@/lib/nav';

/**
 * Companies (WP-86): one page, two tabs. Each tab is the list it always was, at its own address (/suppliers, /organisations),
 * so every link, filter and page number keeps working; /companies opens the first tab. One sentence says what each tab is.
 */
export const COMPANY_TABS = [
  { key: 'suppliers', label: 'Won contracts', href: '/suppliers',
    says: 'Companies named as winners of defence contracts in public award notices of the last three years.' },
  { key: 'organisations', label: 'In EU-funded projects', href: '/organisations',
    says: 'Companies and research bodies that took part in EU-funded defence and research projects: the European Defence Fund, Horizon Europe, Horizon 2020 and FP7.' },
] as const;

export type CompanyTab = (typeof COMPANY_TABS)[number]['key'];

/** The crumbs of a tab: Home, Companies (its first tab's address, not the redirect), the tab. */
export const companyCrumbs = (tab: CompanyTab) => {
  const t = COMPANY_TABS.find((x) => x.key === tab)!;
  return [{ label: 'Home', href: '/' }, { label: 'Companies', href: COMPANY_TABS[0].href }, { label: t.label, href: t.href }];
};

/**
 * WP-121: the crumbs of a page of the menu's Partners group (Ukraine partners, Consortium gaps): Home, Partners, the page; the menu's
 * words, not the older "Organisations" and "Gaps in consortia". WP-130: Partners is a menu group with no page of its own, so it is text
 * (it linked to /suppliers, and the structured data called /suppliers "Partners").
 */
export const partnerCrumbs = (label: string, href: string) =>
  [{ label: 'Home', href: '/' }, { label: MAIN_NAV.find((n) => n.key === 'partners')!.label }, { label, href }];

export function CompaniesTabs({ current }: { current: CompanyTab }) {
  const tab = COMPANY_TABS.find((t) => t.key === current)!;
  return (
    <div className="flex flex-col gap-3">
      <nav aria-label="Companies" className="flex flex-wrap gap-2 border-b border-line">
        {COMPANY_TABS.map((t) => (
          <Link key={t.key} href={t.href} aria-current={t.key === current ? 'page' : undefined}
            className={cn('-mb-px inline-flex min-h-11 items-center border-b-[3px] px-3 text-body font-bold no-underline',
              t.key === current ? 'border-accent-text text-ink' : 'border-transparent text-ink-muted hover:text-ink')}>
            {t.label}
          </Link>
        ))}
      </nav>
      <p className="lead m-0 max-w-prose">{tab.says}</p>
      <p className="m-0 text-small text-ink-muted">
        Also: <Link href="/networks/ukraine-partners" className="inline-flex min-h-11 items-center font-semibold text-ink">Ukraine partners</Link>
        {' · '}<Link href="/networks/consortium-gaps" className="inline-flex min-h-11 items-center font-semibold text-ink">Consortium gaps</Link>
      </p>
    </div>
  );
}
