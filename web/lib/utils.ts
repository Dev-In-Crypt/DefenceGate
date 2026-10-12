import { clsx, type ClassValue } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

/**
 * tailwind-merge only knows Tailwind's own scale, so `text-small` and `text-label` (our
 * font sizes) read as text colours and were dropped whenever a colour class was merged in
 * (secondary buttons lost their border and 14px/12px sizing). Teach it the design's names.
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [{ text: ['display', 'h1', 'h2', 'h3', 'body', 'small', 'label', 'mono', 'mono-strong', 'figure'] }],
      'border-w': [{ border: ['strong'] }],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
