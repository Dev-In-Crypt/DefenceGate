import type { Config } from 'tailwindcss';
import plugin from 'tailwindcss/plugin';

/** Every value points at a DefenceGate CSS variable defined in app/globals.css. */
const v = (name: string) => `var(--${name})`;

const DG_COLORS = [
  'bg', 'surface', 'surface-inset', 'line', 'ink', 'ink-muted', 'primary', 'on-primary',
  'accent', 'accent-text', 'urgent', 'on-urgent', 'link', 'open-bg', 'open-fg', 'soon-bg',
  'soon-fg', 'closed-bg', 'closed-fg', 'alert', 'primary-hover', 'primary-press', 'edge', 'input-edge',
] as const;

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ...Object.fromEntries(DG_COLORS.map((n) => [n, v(n)])),
        // shadcn/ui role names, aliased to DG tokens (see globals.css)
        background: v('background'),
        foreground: v('foreground'),
        border: v('border'),
        input: v('input'),
        ring: v('ring'),
        destructive: { DEFAULT: v('destructive'), foreground: v('destructive-foreground') },
        muted: { DEFAULT: v('muted'), foreground: v('muted-foreground') },
        card: { DEFAULT: v('card'), foreground: v('card-foreground') },
        popover: { DEFAULT: v('popover'), foreground: v('popover-foreground') },
        secondary: { DEFAULT: v('secondary'), foreground: v('secondary-foreground') },
      },
      // Spacing is Tailwind's own scale. The brand book's steps (--space-* in globals.css: 4, 8, 12, 16, 20, 28, 48, 64) are all on it: the
      // book's 28 px card padding is `p-7`, its 48 px section gap `gap-12`, its 64 px band `p-16`. The book's own code instead redefines
      // `p-6` as 28 and `gap-8` as 48 for every utility (WP-44 removed that; WP-62 tried it again and it widened the header pill, which uses
      // `pl-6`, past a 320 px screen). Do not override it.
      borderRadius: { md: v('radius-md'), lg: v('radius-lg'), pill: v('radius-pill') },
      borderWidth: { DEFAULT: '1px', strong: '1.5px' },
      maxWidth: {
        /** The content box of a data page (the container adds the gutters). */
        content: v('content-max'),
        /** The reading measure of running paragraphs (62ch). Frames (cards, the page column) do not take it. */
        prose: v('measure'),
        /** A reading page: title column, gap, one measure, padding. */
        reading: v('reading-max'),
        /** The width of a form, everywhere. */
        form: v('form-max'),
      },
      fontFamily: { sans: [v('font-sans')], mono: [v('font-mono')] },
      // The brand book's type scale (00-shared.md), plus four steps the book does not name: h1-sm and h2-sm (its mobile sizes of the page
      // title and the card title), display-sm (its mobile hero), and h4 / lead (a heading inside a card, the opening paragraph).
      fontSize: {
        display: ['56px', { lineHeight: '60px', letterSpacing: '-2px', fontWeight: '800' }],
        /** The home headline on a phone (book: 40/44). */
        'display-sm': ['40px', { lineHeight: '44px', letterSpacing: '-1.5px', fontWeight: '800' }],
        // Page title: `h1-sm` below md, `h1` from md up (the `.page-title` class in globals.css picks).
        h1: ['40px', { lineHeight: '48px', letterSpacing: '-1.5px', fontWeight: '800' }],
        'h1-sm': ['32px', { lineHeight: '40px', letterSpacing: '-1px', fontWeight: '800' }],
        h2: ['28px', { lineHeight: '36px', letterSpacing: '-0.5px', fontWeight: '700' }],
        /** A list card's title in a narrow card (book: 22/30 on mobile). */
        'h2-sm': ['22px', { lineHeight: '30px', letterSpacing: '-0.5px', fontWeight: '700' }],
        /** Sub-section title and the title of a titled card. */
        h3: ['20px', { lineHeight: '28px', fontWeight: '600' }],
        /** Heading inside a card (a question, a step, a verdict). */
        h4: ['18px', { lineHeight: '24px', fontWeight: '600' }],
        /** Opening paragraph of a page: larger than the body and set in the ink colour. */
        lead: ['18px', { lineHeight: '28px' }],
        body: ['16px', { lineHeight: '24px' }],
        small: ['14px', { lineHeight: '20px' }],
        label: ['12px', { lineHeight: '16px', fontWeight: '700' }],
        mono: ['13px', { lineHeight: '20px' }],
        'mono-strong': ['15px', { lineHeight: '22px', fontWeight: '500' }],
        figure: ['24px', { lineHeight: '30px', fontWeight: '500' }],
      },
      // Every transition is the book's 120ms ease, also the ones that only say `transition-colors` (Tailwind's default was 150ms cubic-bezier).
      transitionDuration: { DEFAULT: v('duration'), dg: v('duration') },
      transitionTimingFunction: { DEFAULT: v('ease'), dg: v('ease') },
      outlineOffset: { focus: '2px' },
    },
  },
  plugins: [
    // Variants on the width of the list card itself (the card is a size container): its text/facts columns depend on the card, not on the
    // viewport (a card in a 3-column grid on the home page is 400 px wide on a 1333 px screen).
    plugin(({ addVariant }) => {
      addVariant('cq', '@container (min-width: 664px)');
      addVariant('cqw', '@container (min-width: 884px)');
    }),
  ],
};

export default config;
