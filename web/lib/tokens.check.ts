/**
 * Self-check of the layout tokens (WP-44). It reads app/globals.css and tailwind.config.ts as text, so a token edit that breaks
 * contrast, a size class that is used but not defined (the `text-h4` bug: seven headings rendered as plain text) or a
 * spacing override that comes back fails here. Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const css = readFileSync(join(process.cwd(), 'app/globals.css'), 'utf8');
const config = readFileSync(join(process.cwd(), 'tailwind.config.ts'), 'utf8');

/** The `--name: #hex` pairs of one block (":root {" or "[data-theme="dark"] {"). */
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

for (const [name, head] of [['light', ':root {'], ['dark', '[data-theme="dark"] {']] as const) {
  const light = tokens(':root {');
  const t = name === 'light' ? light : { ...light, ...tokens(head) };
  // Text on the card surface and on the inset tint stays AA (4.5:1).
  for (const bg of ['surface', 'surface-inset'] as const) {
    for (const fg of ['ink', 'ink-muted', 'link', 'accent-text', 'alert'] as const) {
      // --accent-text is the text form of the accent; the light "alert" on inset is the only pair the design never uses.
      assert.ok(ratio(t[fg], t[bg]) >= 4.5, `${name}: ${fg} on ${bg} is ${ratio(t[fg], t[bg]).toFixed(2)}:1, below 4.5`);
    }
  }
  assert.ok(ratio(t['open-fg'], t['open-bg']) >= 4.5, `${name}: open pill`);
  assert.ok(ratio(t['soon-fg'], t['soon-bg']) >= 4.5, `${name}: soon pill`);
  assert.ok(ratio(t['closed-fg'], t['closed-bg']) >= 4.5, `${name}: closed pill`);
  // A card reads as a card: its 1px edge is clearly visible against the page and against its own surface.
  assert.ok(ratio(t.edge, t.bg) >= 1.4, `${name}: card edge on the page ${ratio(t.edge, t.bg).toFixed(2)}:1`);
  assert.ok(ratio(t.edge, t.surface) >= 1.5, `${name}: card edge on the surface ${ratio(t.edge, t.surface).toFixed(2)}:1`);
  assert.ok(ratio(t.surface, t.bg) >= 1.12, `${name}: surface on the page ${ratio(t.surface, t.bg).toFixed(2)}:1`);
}
// The dark surface was 1.14:1 against the page; it must stay clearly lighter than that.
assert.ok(ratio(tokens('[data-theme="dark"] {').surface, tokens('[data-theme="dark"] {').bg) >= 1.25);

// One reading measure, one content box, gutters 16 / 24 / 32.
assert.match(css, /--measure:\s*680px/);
assert.match(css, /--content-max:\s*1296px/);
assert.match(css, /--gutter:\s*16px/);
assert.match(css, /min-width: 640px\) \{ :root \{ --gutter: 24px/);
assert.match(css, /min-width: 1024px\) \{ :root \{ --gutter: 32px/);

// The spacing scale is Tailwind's own (4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96): no `spacing:` override in the config.
assert.ok(!/^\s*spacing:/m.test(config), 'tailwind.config.ts overrides the spacing scale');

// Every font-size class used in the app is defined (text-h4 was not).
const sizes = new Set([...config.slice(config.indexOf('fontSize:')).matchAll(/^\s+'?([\w-]+)'?:\s*\[/gm)].map((m) => m[1]));
for (const must of ['display', 'h1', 'h1-sm', 'h2', 'h3', 'h4', 'lead', 'body', 'small', 'label', 'mono', 'mono-strong', 'figure']) assert.ok(sizes.has(must), `fontSize ${must} missing`);
function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? (f === 'node_modules' || f === '.next' ? [] : files(p)) : p.endsWith('.tsx') ? [p] : [];
  });
}
const used = new Set<string>();
for (const f of [...files(join(process.cwd(), 'app')), ...files(join(process.cwd(), 'components'))]) {
  for (const m of readFileSync(f, 'utf8').matchAll(/(?<![\w-])text-(h\d(?:-sm)?|lead|display|body|small|label|figure|mono(?:-strong)?)(?![\w-])/g)) used.add(m[1]);
}
for (const u of used) assert.ok(sizes.has(u), `text-${u} is used but not defined`);

console.log('tokens: ok');
