export const THEME_STORAGE_KEY = 'dg-theme';
export type Theme = 'light' | 'dark';

/** The page colour of each theme (`--bg`), as the browser chrome shows it (`<meta name="theme-color">`). */
export const THEME_COLOR: Record<Theme, string> = { light: '#F4F1EA', dark: '#0F1D17' };

/**
 * Which theme a visitor gets: the saved choice if there is one ("light" or "dark"), otherwise what the system asks for
 * (`prefers-color-scheme`). A saved choice is never overridden by the system.
 */
export function pickTheme(saved: string | null | undefined, systemDark: boolean): Theme {
  if (saved === 'dark' || saved === 'light') return saved;
  return systemDark ? 'dark' : 'light';
}

/**
 * Applies the theme before the first paint (inline script in the <head>; it cannot import, so it repeats `pickTheme`: the
 * check in tokens.check.ts runs it and keeps the two in step). It also sets both theme-color metas to the chosen theme, so the
 * browser bar follows the choice and not only the system scheme.
 */
export const THEME_SCRIPT =
  `try{var s=null;try{s=localStorage.getItem('${THEME_STORAGE_KEY}')}catch(e){}` +
  `var d=s==='dark'||(s!=='light'&&window.matchMedia('(prefers-color-scheme: dark)').matches);` +
  `if(d)document.documentElement.dataset.theme='dark';` +
  `var ms=document.querySelectorAll('meta[name="theme-color"]');for(var i=0;i<ms.length;i++)ms[i].setAttribute('content',d?'${THEME_COLOR.dark}':'${THEME_COLOR.light}')}catch(e){}`;

/** Browser side: the metas follow the theme that is on <html> now (the toggle and ThemeSync call this). */
export function syncThemeColor(theme: Theme): void {
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.setAttribute('content', THEME_COLOR[theme]));
}
