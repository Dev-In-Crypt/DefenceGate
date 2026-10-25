'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronDown, Menu, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MAIN_NAV, type NavItem } from '@/lib/nav';
import { Button } from './button';
import { Logo } from './logo';
import { Icon } from './icon';
import { SiteSearchForm } from './site-search';
import { ThemeToggle } from './theme-toggle';

/**
 * The menu is lib/nav.ts (WP-86). Alerts by e-mail are not open (they need a mail provider and sign-in), so there is no
 * call-to-action button until accounts are open: then it is "Sign in".
 * Shown only once the API says accounts are open (layout reads /v1/account/status, 60 s cache). */
const SIGN_IN = { label: 'Sign in', href: '/signin' } as const;

function NavLink({ href, label, active, onClick, prefetch, className }: { href: string; label: string; active: boolean; onClick?: () => void; prefetch?: false; className?: string }) {
  return (
    <Link href={href} onClick={onClick} prefetch={prefetch} aria-current={active ? 'page' : undefined}
      className={cn('inline-flex min-h-11 items-center whitespace-nowrap px-1 text-body font-semibold no-underline decoration-accent-text decoration-2 underline-offset-[6px] transition-colors duration-dg hover:underline',
        active ? 'text-accent-text' : 'text-ink', className)}>
      {label}
    </Link>
  );
}

/** Pill header bar (not fixed). Collapses to a menu button below xl; the menu then starts with the search field. */
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
  const groupActive = (n: NavItem) => [n.href, ...(n.also ?? []), ...(n.children ?? []).map((c) => c.href)].some((h) => h && isActive(h));
  useEffect(() => {
    if (!open && sub === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (open) { setOpen(false); toggleRef.current?.focus(); }
      // Escape on a link of a small menu: the menu hides, so focus goes back to its button, not to the page (WP-58).
      const panel = (document.activeElement as HTMLElement | null)?.closest('[id^="sub-"]');
      if (panel) document.querySelector<HTMLElement>(`[aria-controls="${CSS.escape(panel.id)}"]`)?.focus();
      setSub(null);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, sub]);
  // The mobile menu opens with focus on its first field (the search), not left behind on the page.
  useEffect(() => { if (open) mobileRef.current?.querySelector<HTMLElement>('input, a')?.focus(); }, [open]);
  useEffect(() => { setSub(null); setOpen(false); }, [pathname]);
  return (
    <header className="relative">
      <div className="flex items-center gap-4 rounded-pill bg-surface py-3 pl-6 pr-3">
        <Logo href="/" />
        <nav aria-label="Main" className="hidden flex-1 justify-center gap-4 xl:flex">
          {MAIN_NAV.map((n) => n.children ? (
            // A link with a small menu under it (open on hover, or on its button); an item without a page is only the button.
            <div key={n.key} className="group relative flex items-center"
              onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setSub((cur) => (cur === n.key ? null : cur)); }}>
              {n.href && <NavLink href={n.href} label={n.label} active={groupActive(n)} />}
              <button type="button" aria-expanded={sub === n.key} aria-controls={`sub-${n.key}`} aria-label={n.href ? `${n.label}: more pages` : undefined}
                onClick={() => setSub(sub === n.key ? null : n.key)}
                className={cn('inline-flex min-h-11 items-center justify-center gap-1 border-0 bg-transparent p-0 text-ink', n.href ? 'w-7' : 'whitespace-nowrap px-1 text-body font-semibold', !n.href && groupActive(n) && 'text-accent-text')}>
                {!n.href && n.label}
                <Icon icon={ChevronDown} size="inline" className={cn('transition-transform duration-dg', sub === n.key && 'rotate-180')} />
              </button>
              <div id={`sub-${n.key}`} data-group={n.label} className={cn('absolute left-0 top-full z-20 flex min-w-48 flex-col rounded-lg border border-edge bg-surface px-4 py-2 shadow-lg group-hover:visible', sub === n.key ? 'visible' : 'invisible')}>
                {/* Not prefetched: the menu is hidden until opened, and its pages were half of the prefetches of every page load (WP-58). */}
                {n.children.map((c) => <NavLink key={c.href} href={c.href} label={c.label} active={pathname === c.href} prefetch={false} />)}
              </div>
            </div>
          ) : <NavLink key={n.key} href={n.href!} label={n.label} active={groupActive(n)} />)}
        </nav>
        <div className="ml-auto flex items-center gap-2 xl:ml-0">
          {/* WP-121: one search on the home page's first screen: its own (the phone menu keeps the header's) */}
          {pathname !== '/' && <SiteSearchForm id="header-search" compact className="hidden w-48 xl:flex" />}
          <ThemeToggle />
          {cta && <Button href={cta.href} className="hidden lg:inline-flex">{cta.label}</Button>}
          <button ref={toggleRef} type="button" aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open} aria-controls="mobile-nav" onClick={() => setOpen(!open)}
            className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-ink xl:hidden">
            <Icon icon={open ? X : Menu} />
          </button>
        </div>
      </div>
      {open && (
        // Every item, each a 44 px row: a group is a heading with its pages under it, its own page among them (WP-139, r8 audit:
        // "Check my company" was a dark link among the grey group headings); an item without pages is a link.
        <nav ref={mobileRef} id="mobile-nav" aria-label="Main menu" className="mt-2 flex flex-col gap-1 rounded-lg border border-edge bg-surface px-6 py-4 xl:hidden">
          <SiteSearchForm id="menu-search" compact className="mb-2" />
          {[...MAIN_NAV, ...(cta ? [{ key: 'signin', ...cta }] : [])].map((n: NavItem) => (
            <div key={n.key} className="flex flex-col">
              {n.children || !n.href
                ? <p className="m-0 flex min-h-11 items-center px-1 text-body font-semibold text-ink-muted">{n.label}</p>
                : <NavLink href={n.href} label={n.label} active={isActive(n.href)} onClick={() => setOpen(false)} />}
              {n.children?.map((c) => (
                <NavLink key={c.href} href={c.href} label={c.label} active={pathname === c.href} onClick={() => setOpen(false)} className="pl-5" />
              ))}
            </div>
          ))}
        </nav>
      )}
    </header>
  );
}
