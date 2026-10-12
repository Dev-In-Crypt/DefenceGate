import type { Config } from 'tailwindcss';

/** Every value points at a DefenceGate CSS variable defined in app/globals.css. */
const v = (name: string) => `var(--${name})`;

const DG_COLORS = [
  'bg', 'surface', 'surface-inset', 'line', 'ink', 'ink-muted', 'primary', 'on-primary',
  'accent', 'accent-text', 'urgent', 'on-urgent', 'link', 'open-bg', 'open-fg', 'soon-bg',
  'soon-fg', 'closed-bg', 'closed-fg', 'alert', 'primary-hover', 'primary-press',
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
      spacing: {
        1: v('space-1'), 2: v('space-2'), 3: v('space-3'), 4: v('space-4'),
        5: v('space-5'), 6: v('space-6'), 8: v('space-8'), 10: v('space-10'),
      },
      borderRadius: { md: v('radius-md'), lg: v('radius-lg'), pill: v('radius-pill') },
      borderWidth: { DEFAULT: '1px', strong: '1.5px' },
      maxWidth: { content: v('content-max') },
      fontFamily: { sans: [v('font-sans')], mono: [v('font-mono')] },
      fontSize: {
        display: ['56px', { lineHeight: '60px', letterSpacing: '-2px', fontWeight: '800' }],
        h1: ['40px', { lineHeight: '48px', letterSpacing: '-1.5px', fontWeight: '800' }],
        h2: ['28px', { lineHeight: '36px', letterSpacing: '-0.5px', fontWeight: '700' }],
        h3: ['20px', { lineHeight: '28px', fontWeight: '600' }],
        body: ['16px', { lineHeight: '24px' }],
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
  plugins: [],
};

export default config;
