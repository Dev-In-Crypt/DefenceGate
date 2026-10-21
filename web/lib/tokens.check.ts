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
  // A form field's border is a UI boundary (WCAG 1.4.11): 3:1 against the card, the page and the inset tint. The book's --line is not.
  for (const bg of ['surface', 'bg', 'surface-inset'] as const) {
    assert.ok(ratio(t['input-edge'], t[bg]) >= 3, `${name}: field border on ${bg} ${ratio(t['input-edge'], t[bg]).toFixed(2)}:1`);
  }
}

// WP-62: the colours are the brand book's (design_handoff_defencegate/pages/00-shared.md), every one, in both themes. --input-edge (above)
// is the one colour the book does not have; --edge is an alias of --line (the hairline of a floating layer).
const BOOK_LIGHT: Record<string, string> = {
  bg: '#F4F1EA', surface: '#FFFFFF', 'surface-inset': '#F4F1EA', line: '#DDD8CC', ink: '#12372A', 'ink-muted': '#56605A', primary: '#12372A',
  'on-primary': '#F4F1EA', accent: '#C4581F', 'accent-text': '#A8481A', urgent: '#A8481A', 'on-urgent': '#FFFFFF', link: '#2F6B4F',
  'open-bg': '#DCE6DE', 'open-fg': '#1F5A3F', 'soon-bg': '#F7E1D3', 'soon-fg': '#8E3A12', 'closed-bg': '#E7E4DC', 'closed-fg': '#4A524D',
  alert: '#A12F2F', 'primary-hover': '#1C4A39', 'primary-press': '#0C2A20',
};
const BOOK_DARK: Record<string, string> = {
  bg: '#0F1D17', surface: '#17291F', 'surface-inset': '#1F3328', line: '#2C4237', ink: '#EEF1EA', 'ink-muted': '#A5B1A9', primary: '#DCE6DE',
  'on-primary': '#0F1D17', accent: '#E07A3A', 'accent-text': '#F09A62', urgent: '#E07A3A', 'on-urgent': '#0F1D17', link: '#8FC4A6',
  'open-bg': '#1F3A2C', 'open-fg': '#A8D5BB', 'soon-bg': '#3D2416', 'soon-fg': '#F5B48C', 'closed-bg': '#26332C', 'closed-fg': '#B9C2BC',
  alert: '#F08A8A', 'primary-hover': '#C9D8CD', 'primary-press': '#B8CABD',
};
for (const [book, head] of [[BOOK_LIGHT, ':root {'], [BOOK_DARK, '[data-theme="dark"] {']] as const) {
  const t = { ...tokens(':root {'), ...tokens(head) };
  for (const [k, hex] of Object.entries(book)) assert.equal(t[k]?.toUpperCase(), hex, `${head} --${k} is not the brand book's ${hex}`);
}
assert.match(css, /--edge:\s*var\(--line\)/);
assert.ok(!/--shadow-menu/.test(css), 'the book has no shadows');

// A card has no outline (book: "no border"); the transparent 1px border only keeps its box and shows in forced colours.
const cardSrc = readFileSync(join(process.cwd(), 'components/dg/card.tsx'), 'utf8');
assert.match(cardSrc, /CARD_SURFACE = 'rounded-lg border border-transparent bg-surface'/);
assert.match(cardSrc, /CARD_PADDING = 'p-5 sm:p-7'/);
// No box of the site that pads like a card keeps the old 24 px (`p-5 sm:p-6`): the book's card padding is 28 (Tailwind 7). The header
// pill and the footer are wired by the orchestrator and keep theirs.
for (const f of [...files(join(process.cwd(), 'app')), ...files(join(process.cwd(), 'components'))]) {
  if (/header-bar|footer/.test(f)) continue;
  assert.ok(!readFileSync(f, 'utf8').includes('p-5 sm:p-6'), `${f}: card padding 24 px, the book's is 28 (sm:p-7)`);
}

// The reading measure 62ch (owner, 21 Oct 2026), the content box 1200 px and the gutters 16 / 28 of the book.
assert.match(css, /--measure:\s*62ch/);
assert.match(css, /--content-max:\s*1200px/);
assert.match(css, /--gutter:\s*16px/);
assert.match(css, /min-width: 768px\) \{ :root \{ --gutter: 28px/);

// The book's spacing scale: --space-1..10 as in the book. All of its steps are on Tailwind's own scale (28 = 7, 48 = 12, 64 = 16), so
// the config does not override it (the book's code redefines p-6 as 28 for every utility, which widened the header pill past 320 px).
for (const [k, px] of Object.entries({ 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 28, 8: 48, 10: 64 })) {
  assert.match(css, new RegExp(`--space-${k}:\\s*${px}px`), `--space-${k} is not ${px}px`);
}
assert.ok(!/^\s*(spacing|padding|margin|gap|space):/m.test(config), 'tailwind.config.ts overrides the spacing scale');

// The book's type scale: size / line / tracking / weight, and the 16/24 body.
const TYPE_BOOK: Record<string, string> = {
  display: "['56px', { lineHeight: '60px', letterSpacing: '-2px', fontWeight: '800' }]",
  h1: "['40px', { lineHeight: '48px', letterSpacing: '-1.5px', fontWeight: '800' }]",
  h2: "['28px', { lineHeight: '36px', letterSpacing: '-0.5px', fontWeight: '700' }]",
  h3: "['20px', { lineHeight: '28px', fontWeight: '600' }]",
  body: "['16px', { lineHeight: '24px' }]",
  small: "['14px', { lineHeight: '20px' }]",
  label: "['12px', { lineHeight: '16px', fontWeight: '700' }]",
  mono: "['13px', { lineHeight: '20px' }]",
  "'mono-strong'": "['15px', { lineHeight: '22px', fontWeight: '500' }]",
  figure: "['24px', { lineHeight: '30px', fontWeight: '500' }]",
};
for (const [k, v] of Object.entries(TYPE_BOOK)) assert.ok(config.includes(`${k}: ${v}`), `fontSize ${k} is not the book's ${v}`);
assert.match(css, /body \{[^}]*line-height: 1\.5;/);
// Every transition is the book's 120ms ease, also Tailwind's default one.
assert.match(config, /transitionTimingFunction: \{ DEFAULT: v\('ease'\)/);

// Every font-size class used in the app is defined (text-h4 was not).
const sizes = new Set([...config.slice(config.indexOf('fontSize:')).matchAll(/^\s+'?([\w-]+)'?:\s*\[/gm)].map((m) => m[1]));
for (const must of ['display', 'display-sm', 'h1', 'h1-sm', 'h2', 'h2-sm', 'h3', 'h4', 'lead', 'body', 'small', 'label', 'mono', 'mono-strong', 'figure']) assert.ok(sizes.has(must), `fontSize ${must} missing`);
function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? (f === 'node_modules' || f === '.next' ? [] : files(p)) : p.endsWith('.tsx') ? [p] : [];
  });
}
const used = new Set<string>();
for (const f of [...files(join(process.cwd(), 'app')), ...files(join(process.cwd(), 'components'))]) {
  for (const m of readFileSync(f, 'utf8').matchAll(/(?<![\w-])text-(h\d(?:-sm)?|lead|display(?:-sm)?|body|small|label|figure|mono(?:-strong)?)(?![\w-])/g)) used.add(m[1]);
}
for (const u of used) assert.ok(sizes.has(u), `text-${u} is used but not defined`);

// No ad hoc line-length cap: running text takes the one measure (`max-w-prose`). The breadcrumb (40ch), the footer (36/34ch) are not prose;
// the home page keeps its own until the home layout work (WP-46) replaces them. WP-45 removed the ones on /regulation and /requirements.
const ALLOWED_CH = ['components/dg/feedback.tsx', 'components/dg/footer.tsx', 'app/(public)/page.tsx'];
for (const f of [...files(join(process.cwd(), 'app')), ...files(join(process.cwd(), 'components'))]) {
  const rel = f.slice(process.cwd().length + 1).replaceAll('\\', '/');
  if (ALLOWED_CH.includes(rel)) continue;
  const bad = readFileSync(f, 'utf8').match(/max-w-\[\d+ch\]/);
  assert.ok(!bad, `${rel}: ${bad?.[0]} is an ad hoc measure, use max-w-prose`);
}

console.log('tokens: ok');
