'use client';

import { useEffect } from 'react';
import { THEME_COLOR, THEME_STORAGE_KEY, pickTheme, syncThemeColor, type Theme } from '@/lib/theme';

/**
 * Puts the saved theme back if the page lost it. The pre-paint script in app/layout.tsx sets `data-theme` on <html> before the first
 * paint; if React then gives up hydrating and renders the page again on the client, it rewrites <html> and the attribute is gone (the
 * page turned light for a visitor who chose dark: WP-54, R1). This runs after every mount of the tree, so the choice is restored
 * even then. It reads the storage and the attribute and changes nothing when they agree.
 */
export function ThemeSync() {
  useEffect(() => {
    let saved: string | null = null;
    try { saved = localStorage.getItem(THEME_STORAGE_KEY); } catch { /* storage unavailable: the system's scheme decides */ }
    const theme = pickTheme(saved, window.matchMedia('(prefers-color-scheme: dark)').matches);
    if (theme === 'dark' && document.documentElement.dataset.theme !== 'dark') document.documentElement.dataset.theme = 'dark';
    syncThemeColor(theme);
    // Next streams the viewport metas and may insert them after this ran (with the per-scheme colours): keep them on the theme.
    const current = (): Theme => (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
    const watch = new MutationObserver(() => {
      const want = THEME_COLOR[current()];
      if ([...document.querySelectorAll('meta[name="theme-color"]')].some((m) => m.getAttribute('content') !== want)) syncThemeColor(current());
    });
    watch.observe(document.head, { childList: true, subtree: true, attributes: true, attributeFilter: ['content'] });
    return () => watch.disconnect();
  }, []);
  return null;
}
