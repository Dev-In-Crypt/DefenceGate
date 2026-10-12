'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Menu, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Logo } from './logo';
import { Button } from './button';
import { Icon } from './icon';
import { ThemeToggle } from './theme-toggle';

export const MAIN_NAV = [
  { label: 'Funding', href: '/funding' },
  { label: 'Tenders', href: '/tenders' },
  { label: 'Buyers', href: '/buyers' },
  { label: 'Data', href: '/data' },
  { label: 'Pricing', href: '/pricing' },
] as const;

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
export function HeaderBar() {
  const pathname = usePathname();
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
          <Button href="/alerts/subscribe" className="hidden md:inline-flex">Get alerts</Button>
          <button type="button" aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open} aria-controls="mobile-nav" onClick={() => setOpen(!open)}
            className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-ink md:hidden">
            <Icon icon={open ? X : Menu} />
          </button>
        </div>
      </div>
      {open && (
        <nav id="mobile-nav" aria-label="Main" className="mt-2 flex flex-col rounded-lg bg-surface px-6 py-4 md:hidden">
          {MAIN_NAV.map((n) => <NavLink key={n.href} {...n} active={isActive(n.href)} onClick={() => setOpen(false)} />)}
          <div className="pt-3"><Button href="/alerts/subscribe" fullWidth>Get alerts</Button></div>
        </nav>
      )}
    </header>
  );
}
