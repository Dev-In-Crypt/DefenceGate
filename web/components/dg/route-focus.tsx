'use client';

import { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';

/**
 * After a client-side route change, focus goes to the new page's main heading (WCAG 2.4.3), not to `<body>` where the browser
 * leaves it when the link that was pressed is gone. Not on the first load (the skip link stays the first tab stop), not when only
 * the query changes (a filter keeps focus on its control), and not when the page has already put focus inside `main` itself.
 * The heading gets `tabindex=-1` so it can take focus without becoming a tab stop.
 */
export function RouteFocus() {
  const pathname = usePathname();
  const seen = useRef<string | null>(null);
  useEffect(() => {
    const before = seen.current;
    seen.current = pathname;
    if (before === null || before === pathname) return;
    const main = document.getElementById('main');
    const now = document.activeElement;
    if (!main || (now && now !== document.body && main.contains(now))) return;
    const target = main.querySelector<HTMLElement>('h1') ?? main;
    if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
    target.focus({ preventScroll: true });
  }, [pathname]);
  return null;
}
