'use client';

import { useEffect } from 'react';
import { THEME_STORAGE_KEY } from '@/lib/theme';

/**
 * Puts the saved theme back if the page lost it. The pre-paint script in app/layout.tsx sets `data-theme` on <html> before the first
 * paint; if React then gives up hydrating and renders the page again on the client, it rewrites <html> and the attribute is gone (the
 * page turned light for a visitor who chose dark: WP-54, R1). This runs after every mount of the tree, so the choice is restored
 * even then. It reads the storage and the attribute and changes nothing when they agree.
 */
export function ThemeSync() {
  useEffect(() => {
    try {
      const saved = localStorage.getItem(THEME_STORAGE_KEY);
      if (saved === 'dark' && document.documentElement.dataset.theme !== 'dark') document.documentElement.dataset.theme = 'dark';
    } catch { /* storage unavailable: the page keeps what it has */ }
  }, []);
  return null;
}
