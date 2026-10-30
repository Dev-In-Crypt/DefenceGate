'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Bell, Bookmark, CreditCard, KeyRound, LayoutDashboard, Search, Settings, Users } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Icon } from '../dg/icon';

const ITEMS = [
  { label: 'Dashboard', href: '/app', icon: LayoutDashboard },
  { label: 'Searches', href: '/app/searches', icon: Search },
  { label: 'Shortlist', href: '/app/shortlist', icon: Bookmark },
  { label: 'Following', href: '/app/following', icon: Bell },
  { label: 'Billing', href: '/app/billing', icon: CreditCard },
  { label: 'Settings', href: '/app/settings', icon: Settings },
] as const;

/** WP-153: shown while the API issues keys (`Me.apiKeys`), before Settings. */
const KEYS = { label: 'API keys', href: '/app/keys', icon: KeyRound } as const;

/** WP-158: shown to a member of a licensed association (`Me.association`), before Settings. */
const ASSOCIATION = { label: 'Association', href: '/app/association', icon: Users } as const;

/** Sidebar on desktop, the list inside the mobile menu below lg. The dashboard matches /app exactly. */
export function AppNav({ label = 'Account', apiKeys = false, association = false }: { label?: string; apiKeys?: boolean; association?: boolean }) {
  const pathname = usePathname();
  const extra = [...(association ? [ASSOCIATION] : []), ...(apiKeys ? [KEYS] : [])];
  const items = [...ITEMS.slice(0, -1), ...extra, ITEMS[ITEMS.length - 1]];
  return (
    <nav aria-label={label}>
      <ul className="m-0 flex list-none flex-col gap-1 p-0">
        {items.map((i) => {
          const active = i.href === '/app' ? pathname === '/app' : pathname === i.href || pathname.startsWith(`${i.href}/`);
          return (
            <li key={i.href}>
              <Link href={i.href} aria-current={active ? 'page' : undefined}
                className={cn('flex min-h-11 items-center gap-3 rounded-pill px-4 text-body font-semibold no-underline transition-colors duration-dg hover:no-underline',
                  active ? 'bg-primary text-on-primary' : 'text-ink hover:bg-surface-inset')}>
                <Icon icon={i.icon} />{i.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
