'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronDown, Menu, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from './button';
import { Logo } from './logo';
import { Icon } from './icon';
import { ThemeToggle } from './theme-toggle';

/**
 * Only routes that exist. The call-to-action is a button from lg and a last menu item below md. Alerts by e-mail are
 * not open (they need a mail provider and sign-in), so there is no call-to-action button until accounts are open: then
 * it is "Sign in". "What changed" lives in the footer and on the home page, where it is not a primary action.
 * Market is in the header and Methodology is under Data (UX walk-throughs of 16 October 2026: analysts looked for them there).
 */
export interface NavItem { label: string; href: string; children?: readonly { label: string; href: string }[] }
export const MAIN_NAV: readonly NavItem[] = [
  { label: 'Funding', href: '/funding' },
  { label: 'Tenders', href: '/tenders' },
  { label: 'Buyers', href: '/buyers' },
  // Layer 2: who is already inside. Layer 3: what it takes to qualify (the concept's three questions).
  { label: 'Network', href: '/organisations', children: [
    { label: 'Organisations', href: '/organisations' }, { label: 'Suppliers', href: '/suppliers' },
    { label: 'Ukraine partners', href: '/networks/ukraine-partners' }, { label: 'Consortium gaps', href: '/networks/consortium-gaps' },
  ] },
  { label: 'Readiness', href: '/readiness', children: [
    { label: 'Readiness check', href: '/readiness' }, { label: 'Requirements', href: '/requirements' }, { label: 'Regulatory tracker', href: '/regulation' },
  ] },
  { label: 'Market', href: '/market' },
  { label: 'Data', href: '/data', children: [
    { label: 'Source status', href: '/data' }, { label: 'Methodology', href: '/methodology' },
    { label: 'Weekly digest', href: '/digest' }, { label: 'Data sovereignty', href: '/data/sovereignty' },
  ] },
  { label: 'Pricing', href: '/pricing' },
];
/** Shown only once the API says accounts are open (layout reads /v1/account/status, 60 s cache). */
const SIGN_IN = { label: 'Sign in', href: '/signin' } as const;

function NavLink({ href, label, active, onClick }: { href: string; label: string; active: boolean; onClick?: () => void }) {
  return (
    <Link href={href} onClick={onClick} aria-current={active ? 'page' : undefined}
      className={cn('inline-flex min-h-11 items-center whitespace-nowrap px-1 text-body font-semibold no-underline decoration-accent-text decoration-2 underline-offset-[6px] transition-colors duration-dg hover:underline',
        active ? 'text-accent-text' : 'text-ink')}>
      {label}
    </Link>
  );
}

/** Pill header bar (not fixed). Collapses to a menu button below md. */
export function HeaderBar({ accountsOpen = false }: { accountsOpen?: boolean }) {
  const pathname = usePathname();
  const cta = accountsOpen ? SIGN_IN : null;
  const [open, setOpen] = useState(false);
  // The small menus of the desktop bar open on hover, and on a button that says so (aria-expanded): the hover alone was
  // unreachable on a touch screen, and focus-within alone cost four tab stops per menu (U16).
  const [sub, setSub] = useState<string | null>(null);
  const mobileRef = useRef<HTMLElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  useEffect(() => {
    if (!open && sub === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (open) { setOpen(false); toggleRef.current?.focus(); }
      setSub(null);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, sub]);
  // The mobile menu opens with focus on its first link, not left behind on the page.
  useEffect(() => { if (open) mobileRef.current?.querySelector<HTMLElement>('a')?.focus(); }, [open]);
  useEffect(() => { setSub(null); setOpen(false); }, [pathname]);
  return (
    <header className="relative">
      <div className="flex items-center gap-6 rounded-pill bg-surface py-3 pl-6 pr-3">
        <Logo href="/" />
        <nav aria-label="Main" className="hidden flex-1 justify-center gap-5 xl:flex">
          {MAIN_NAV.map((n) => n.children ? (
            // A link with a small menu under it: open on hover, or on its button.
            <div key={n.href} className="group relative flex items-center"
              onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setSub((cur) => (cur === n.href ? null : cur)); }}>
              <NavLink href={n.href} label={n.label} active={isActive(n.href) || n.children.some((c) => isActive(c.href))} />
              <button type="button" aria-expanded={sub === n.href} aria-controls={`sub-${n.label}`} aria-label={`${n.label}: more pages`}
                onClick={() => setSub(sub === n.href ? null : n.href)}
                className="inline-flex min-h-11 w-8 items-center justify-center border-0 bg-transparent p-0 text-ink">
                <Icon icon={ChevronDown} size="inline" className={cn('transition-transform duration-dg', sub === n.href && 'rotate-180')} />
              </button>
              <div id={`sub-${n.label}`} className={cn('absolute left-0 top-full z-20 flex min-w-44 flex-col rounded-lg border border-edge bg-surface px-4 py-2 shadow-lg group-hover:visible', sub === n.href ? 'visible' : 'invisible')}>
                {n.children.map((c) => <NavLink key={c.href} href={c.href} label={c.label} active={pathname === c.href} />)}
              </div>
            </div>
          ) : <NavLink key={n.href} href={n.href} label={n.label} active={isActive(n.href)} />)}
        </nav>
        <div className="ml-auto flex items-center gap-2 xl:ml-0">
          <ThemeToggle />
          {cta && <Button href={cta.href} className="hidden lg:inline-flex">{cta.label}</Button>}
          <button ref={toggleRef} type="button" aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open} aria-controls="mobile-nav" onClick={() => setOpen(!open)}
            className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-ink xl:hidden">
            <Icon icon={open ? X : Menu} />
          </button>
        </div>
      </div>
      {open && (
        <nav ref={mobileRef} id="mobile-nav" aria-label="Main menu" className="mt-2 flex flex-col rounded-lg border border-edge bg-surface px-6 py-4 xl:hidden">
          {[...MAIN_NAV, ...(cta ? [cta] : [])].map((n) => (
            <div key={n.href} className="flex flex-col">
              <NavLink href={n.href} label={n.label} active={isActive(n.href)} onClick={() => setOpen(false)} />
              {'children' in n && n.children?.filter((c) => c.href !== n.href).map((c) => (
                <span key={c.href} className="pl-4"><NavLink href={c.href} label={c.label} active={pathname === c.href} onClick={() => setOpen(false)} /></span>
              ))}
            </div>
          ))}
        </nav>
      )}
    </header>
  );
}
