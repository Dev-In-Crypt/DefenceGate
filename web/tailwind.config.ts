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
      // Spacing is Tailwind's own scale (4 = 16, 6 = 24, 8 = 32, 12 = 48, 16 = 64, 24 = 96). Until WP-44 it was
      // overridden (6 = 28, 8 = 48, 10 = 64), which made `p-6` an odd 28 px and `gap-8` a 48 px gap. Do not override it again.
      borderRadius: { md: v('radius-md'), lg: v('radius-lg'), pill: v('radius-pill') },
      borderWidth: { DEFAULT: '1px', strong: '1.5px' },
      maxWidth: {
        /** The content box of a data page (the container adds the gutters). */
        content: v('content-max'),
        /** The ONE reading measure: the whole content box (was 680 px). Replaces every ad hoc `ch` cap. */
        prose: v('measure'),
        /** A reading page: title column, gap, one measure, padding. */
        reading: v('reading-max'),
        /** The width of a form, everywhere. */
        form: v('form-max'),
      },
      fontFamily: { sans: [v('font-sans')], mono: [v('font-mono')] },
      fontSize: {
        display: ['56px', { lineHeight: '60px', letterSpacing: '-2px', fontWeight: '800' }],
        /** The home headline beside its figures (the 56 px display wraps to three lines in a two-column hero). */
        'display-sm': ['44px', { lineHeight: '48px', letterSpacing: '-1.5px', fontWeight: '800' }],
        // Page title: `h1-sm` below md, `h1` from md up (the `.page-title` class in globals.css picks).
        h1: ['36px', { lineHeight: '44px', letterSpacing: '-0.5px', fontWeight: '700' }],
        'h1-sm': ['32px', { lineHeight: '40px', letterSpacing: '-0.5px', fontWeight: '700' }],
        h2: ['24px', { lineHeight: '32px', letterSpacing: '-0.3px', fontWeight: '700' }],
        /** Card title and sub-section title. */
        h3: ['20px', { lineHeight: '28px', fontWeight: '700' }],
        /** Heading inside a card (a question, a step, a verdict). Was undefined: seven headings rendered as plain text. */
        h4: ['18px', { lineHeight: '26px', fontWeight: '600' }],
        /** Opening paragraph of a page: larger than the body and set in the ink colour. */
        lead: ['18px', { lineHeight: '28px' }],
        body: ['16px', { lineHeight: '26px' }],
        small: ['14px', { lineHeight: '20px' }],
        label: ['12px', { lineHeight: '16px', fontWeight: '700' }],
        mono: ['13px', { lineHeight: '20px' }],
        'mono-strong': ['15px', { lineHeight: '22px', fontWeight: '500' }],
        figure: ['24px', { lineHeight: '30px', fontWeight: '500' }],
      },
      transitionDuration: { dg: v('duration') },
      transitionTimingFunction: { dg: v('ease') },
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
