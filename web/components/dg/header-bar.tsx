'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Menu, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from './button';
import { Logo } from './logo';
import { Icon } from './icon';
import { ThemeToggle } from './theme-toggle';

/**
 * Only routes that exist. The call-to-action is a button from lg and a last menu item below md. Alerts by e-mail are
 * not open (they need a mail provider and sign-in), so there is no call-to-action button until accounts are open: then
 * it is "Sign in". "What changed" lives in the footer and on the home page, where it is not a primary action.
 */
export const MAIN_NAV = [
  { label: 'Funding', href: '/funding' },
  { label: 'Tenders', href: '/tenders' },
  { label: 'Buyers', href: '/buyers' },
  { label: 'Data', href: '/data' },
  { label: 'Pricing', href: '/pricing' },
] as const;
/** Shown only once the API says accounts are open (layout reads /v1/account/status, 60 s cache). */
const SIGN_IN = { label: 'Sign in', href: '/signin' } as const;

function NavLink({ href, label, active, onClick }: { href: string; label: string; active: boolean; onClick?: () => void }) {
  return (
    <Link href={href} onClick={onClick} aria-current={active ? 'page' : undefined}
      className={cn('inline-flex min-h-11 items-center px-1 text-body font-semibold no-underline decoration-accent-text decoration-2 underline-offset-[6px] transition-colors duration-dg hover:underline',
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
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  return (
    <header className="relative">
      <div className="flex items-center gap-6 rounded-pill bg-surface py-3 pl-6 pr-3">
        <Logo href="/" />
        <nav aria-label="Main" className="hidden flex-1 justify-center gap-5 md:flex">
          {MAIN_NAV.map((n) => <NavLink key={n.href} {...n} active={isActive(n.href)} />)}
        </nav>
        <div className="ml-auto flex items-center gap-2 md:ml-0">
          <ThemeToggle />
          {cta && <Button href={cta.href} className="hidden lg:inline-flex">{cta.label}</Button>}
          <button type="button" aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open} aria-controls="mobile-nav" onClick={() => setOpen(!open)}
            className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-ink md:hidden">
            <Icon icon={open ? X : Menu} />
          </button>
        </div>
      </div>
      {open && (
        <nav id="mobile-nav" aria-label="Main menu" className="mt-2 flex flex-col rounded-lg bg-surface px-6 py-4 md:hidden">
          {[...MAIN_NAV, ...(cta ? [cta] : [])].map((n) => <NavLink key={n.href} {...n} active={isActive(n.href)} onClick={() => setOpen(false)} />)}
        </nav>
      )}
    </header>
  );
}
