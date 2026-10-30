'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Bell, Bookmark, Briefcase, CreditCard, FileCheck, KeyRound, LayoutDashboard, Search, Settings, Users, UsersRound } from 'lucide-react';
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
/** WP-157: shown when the plan has the team workspace or the account is in one (`team`), and with client profiles (`clients`), after Following. */
const TEAM = { label: 'Team', href: '/app/team', icon: UsersRound } as const;
const CLIENTS = { label: 'Clients', href: '/app/clients', icon: Briefcase } as const;

/** WP-156: shown when the account's features include `eligibility_export`, after Following. */
const PACK = { label: 'Eligibility pack', href: '/app/eligibility', icon: FileCheck } as const;

/** WP-158: shown to a member of a licensed association (`Me.association`), before Settings. */
const ASSOCIATION = { label: 'Association', href: '/app/association', icon: Users } as const;

/** Sidebar on desktop, the list inside the mobile menu below lg. The dashboard matches /app exactly. */
export function AppNav({ label = 'Account', apiKeys = false, eligibility = false, association = false, team = false, clients = false }:
  { label?: string; apiKeys?: boolean; eligibility?: boolean; association?: boolean; team?: boolean; clients?: boolean }) {
  const pathname = usePathname();
  // after Following: Eligibility pack (WP-156), Team and Clients (WP-157); before Settings: Association (WP-158), API keys (WP-153)
  const middle = [...(eligibility ? [PACK] : []), ...(team ? [TEAM] : []), ...(clients ? [CLIENTS] : [])];
  const base = [...ITEMS.slice(0, 4), ...middle, ...ITEMS.slice(4)];
  const extra = [...(association ? [ASSOCIATION] : []), ...(apiKeys ? [KEYS] : [])];
  const items = [...base.slice(0, -1), ...extra, base[base.length - 1]];
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
