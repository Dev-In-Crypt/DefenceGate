/**
 * Self-check of WP-55 (design-system fixes): the tokens it adds keep their contrast (form-field border 3:1 in both themes, the logo
 * in the dark theme), the placeholder rule outranks Tailwind's preflight, the inline theme script and `pickTheme` agree
 * (saved choice first, else the system scheme; the theme-color metas follow), and no `italic`/mono-bold utility comes back
 * on a shared component. Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { THEME_COLOR, THEME_SCRIPT, pickTheme } from './theme';

const css = readFileSync(join(process.cwd(), 'app/globals.css'), 'utf8');

function tokens(head: string): Record<string, string> {
  const start = css.indexOf(head);
  assert.ok(start >= 0, `block ${head} not found`);
  const end = css.indexOf('}', start);
  const out: Record<string, string> = {};
  for (const m of css.slice(start, end).matchAll(/--([\w-]+):\s*(#[0-9A-Fa-f]{6})/g)) out[m[1]] = m[2];
  return out;
}
const lum = (hex: string) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const ratio = (a: string, b: string) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

const light = tokens(':root {');
const dark = { ...light, ...tokens('[data-theme="dark"] {') };
for (const [name, t] of [['light', light], ['dark', dark]] as const) {
  // WCAG 1.4.11: the border of a form field against what is inside it, and against what is outside it (card or page).
  for (const bg of ['surface', 'surface-inset', 'bg'] as const) {
    assert.ok(ratio(t['input-edge'], t[bg]) >= 3, `${name}: --input-edge on ${bg} is ${ratio(t['input-edge'], t[bg]).toFixed(2)}:1, below 3`);
  }
  // Placeholder text is --ink-muted: AA on every surface a field sits on.
  for (const bg of ['surface', 'surface-inset', 'bg'] as const) assert.ok(ratio(t['ink-muted'], t[bg]) >= 4.5, `${name}: placeholder on ${bg}`);
}
// The logo in the dark theme: the disc against the header (surface) and the posts on the disc; "Gate" is the book's #F09A62 and reads as text.
assert.ok(ratio(dark['logo-disc'], dark.surface) >= 3, 'dark logo disc on the header');
assert.ok(ratio(dark['logo-post'], dark['logo-disc']) >= 3, 'dark logo posts on the disc');
assert.ok(ratio(dark['logo-chev'], dark['logo-disc']) >= 3, 'dark logo chevron on the disc');
assert.equal(dark['logo-gate'].toUpperCase(), '#F09A62');
assert.ok(ratio(dark['logo-gate'], dark.surface) >= 4.5, 'dark "Gate" on the header');
assert.ok(ratio(light['logo-disc'], light.surface) >= 3, 'light logo disc on the header');

// Preflight's `input::placeholder` (gray-400, 2.5:1) is as specific as this selector; the DG rule must name it.
assert.match(css, /input::placeholder/);
assert.match(css, /--input:\s*var\(--input-edge\)/);

// The theme: the inline script and pickTheme give the same answer for every case; the metas follow.
function runScript(saved: string | null, systemDark: boolean) {
  const metas = [{ attrs: {} as Record<string, string>, setAttribute(k: string, v: string) { this.attrs[k] = v; } }, { attrs: {} as Record<string, string>, setAttribute(k: string, v: string) { this.attrs[k] = v; } }];
  const doc = { documentElement: { dataset: {} as Record<string, string> }, querySelectorAll: () => metas };
  new Function('document', 'localStorage', 'window', THEME_SCRIPT)(doc, { getItem: () => saved }, { matchMedia: () => ({ matches: systemDark }) });
  return { theme: doc.documentElement.dataset.theme === 'dark' ? 'dark' : 'light', colors: metas.map((m) => m.attrs.content) };
}
for (const saved of [null, 'light', 'dark', 'garbage']) {
  for (const systemDark of [false, true]) {
    const want = pickTheme(saved, systemDark);
    const got = runScript(saved, systemDark);
    assert.equal(got.theme, want, `saved=${saved} system dark=${systemDark}`);
    assert.deepEqual(got.colors, [THEME_COLOR[want], THEME_COLOR[want]], `theme-color metas for saved=${saved} system dark=${systemDark}`);
  }
}
assert.equal(pickTheme(null, true), 'dark');      // first visit, dark system: dark
assert.equal(pickTheme('light', true), 'light');  // a saved choice is never overridden
assert.equal(pickTheme('dark', false), 'dark');
assert.equal(pickTheme(null, false), 'light');
// A storage that throws must not stop the system scheme from deciding.
{
  const doc = { documentElement: { dataset: {} as Record<string, string> }, querySelectorAll: () => [] };
  const boom = { getItem() { throw new Error('blocked'); } };
  new Function('document', 'localStorage', 'window', THEME_SCRIPT)(doc, boom, { matchMedia: () => ({ matches: true }) });
  assert.equal(doc.documentElement.dataset.theme, 'dark');
}

// DM Mono has two weights (400, 500); the stylesheet maps every heavier request to 500 (checked in the browser by e2e/wp55.spec.ts).
const layout = readFileSync(join(process.cwd(), 'app/layout.tsx'), 'utf8');
assert.match(layout, /DM_Mono\(\{[^}]*weight: \['400', '500'\]/);
assert.match(css, /\.font-mono[^{]*\.font-semibold[^{]*\{\s*font-weight: 500;/);
// Manrope has no italic face: no shared component asks for `italic` (the stylesheet also keeps `.italic` upright for pages that still do).
function tsxFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? tsxFiles(join(dir, e.name)) : e.name.endsWith('.tsx') ? [join(dir, e.name)] : []));
}
for (const f of tsxFiles(join(process.cwd(), 'components'))) assert.ok(!/className="[^"]*\bitalic\b/.test(readFileSync(f, 'utf8')), `${f} uses the italic class`);
assert.match(css, /\.italic\s*\{\s*font-style: normal/);
console.log('wp55.check ok');
