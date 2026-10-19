import type { LucideIcon, LucideProps } from 'lucide-react';
import { cn } from '@/lib/utils';

/** Brand icon rules: Lucide line icons at 1.75px stroke, 20px in UI, 16px inline, 18px in buttons. Never squeezed by a long label next to it (`shrink-0`). */
export const ICON_STROKE = 1.75;
export const ICON_SIZE = { inline: 16, button: 18, ui: 20 } as const;

export function Icon({ icon: I, size = 'ui', ...rest }: { icon: LucideIcon; size?: keyof typeof ICON_SIZE } & Omit<LucideProps, 'size'>) {
  return <I size={ICON_SIZE[size]} strokeWidth={ICON_STROKE} aria-hidden="true" {...rest} className={cn('shrink-0', rest.className)} />;
}
