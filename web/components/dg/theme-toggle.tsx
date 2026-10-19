'use client';

import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { THEME_STORAGE_KEY, syncThemeColor, type Theme } from '@/lib/theme';
import { Icon } from './icon';

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>('light');
  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
  }, []);
  const toggle = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    if (next === 'dark') document.documentElement.dataset.theme = 'dark';
    else delete document.documentElement.dataset.theme;
    syncThemeColor(next);
    try { localStorage.setItem(THEME_STORAGE_KEY, next); } catch { /* storage unavailable */ }
  };
  return (
    <button type="button" onClick={toggle} aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      className="flex size-11 items-center justify-center rounded-pill bg-surface-inset text-ink">
      <Icon icon={theme === 'dark' ? Sun : Moon} />
    </button>
  );
}
