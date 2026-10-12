import Link from 'next/link';
import { cn } from '@/lib/utils';

/** Mark geometry copied from public/brand/*.svg. Logo colours are fixed and do not follow theme. */
const MARKS = {
  default: { disc: '#12372A', post: '#F4F1EA', chev: '#E07A3A', posts: [[11, 14, 5, 20], [32, 14, 5, 20]], d: 'M20 16.5 L27.5 24 L20 31.5', sw: 4.5 },
  reversed: { disc: '#F4F1EA', post: '#12372A', chev: '#C4581F', posts: [[11, 14, 5, 20], [32, 14, 5, 20]], d: 'M20 16.5 L27.5 24 L20 31.5', sw: 4.5 },
  small: { disc: '#12372A', post: '#F4F1EA', chev: '#E07A3A', posts: [[10, 13, 6, 22], [32, 13, 6, 22]], d: 'M20 16 L28 24 L20 32', sw: 5.5 },
  favicon: { disc: '#12372A', post: '#F4F1EA', chev: '#E07A3A', posts: [], d: 'M18 13 L29 24 L18 35', sw: 8 },
} as const;
type MarkVariant = keyof typeof MARKS;

/** Lockup ratios from the brand book. */
const CAP_HEIGHT = 0.72;
const MARK_TO_CAP = 1.33;
const GAP_TO_MARK = 0.33;
const SMALL_MARK_MAX = 32;
const FAVICON_MAX = 24;

export function LogoMark({ variant = 'default', size = 48, title }: { variant?: MarkVariant; size?: number; title?: string }) {
  const m = MARKS[variant];
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} role={title ? 'img' : undefined} aria-label={title} aria-hidden={title ? undefined : true} className="block shrink-0">
      <circle cx="24" cy="24" r="24" fill={m.disc} />
      {m.posts.map(([x, y, w, h], i) => <rect key={i} x={x} y={y} width={w} height={h} rx="1.5" fill={m.post} />)}
      <path d={m.d} fill="none" stroke={m.chev} strokeWidth={m.sw} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** "Defence" in ink + "Gate" in accent, Manrope 800. Live text. */
export function Wordmark({ size, reversed = false }: { size: number; reversed?: boolean }) {
  return (
    <span className={cn('whitespace-nowrap font-sans font-extrabold leading-none tracking-[-0.033em]', reversed ? 'text-[#F4F1EA]' : 'text-ink')} style={{ fontSize: size }}>
      Defence<span className={reversed ? 'text-[#F09A62]' : 'text-accent'}>Gate</span>
    </span>
  );
}

export function Logo({ size = 21, reversed = false, href }: { size?: number; reversed?: boolean; href?: string }) {
  const markH = Math.round(size * CAP_HEIGHT * MARK_TO_CAP);
  const variant: MarkVariant = reversed ? 'reversed' : markH < FAVICON_MAX ? 'favicon' : markH <= SMALL_MARK_MAX ? 'small' : 'default';
  const inner = (
    <>
      <LogoMark variant={variant} size={markH} />
      <Wordmark size={size} reversed={reversed} />
    </>
  );
  const style = { gap: Math.round(markH * GAP_TO_MARK) };
  return href ? (
    <Link href={href} aria-label="DefenceGate home" className="inline-flex items-center hover:no-underline" style={style}>{inner}</Link>
  ) : (
    <span className="inline-flex items-center" style={style}>{inner}</span>
  );
}
