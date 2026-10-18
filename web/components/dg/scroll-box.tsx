'use client';

import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

/**
 * A box that scrolls sideways (a wide table at 375 px) and says so: a line above it while there is more to the right or
 * the left, gone when everything fits (UX walk-through U14: a 640 px table in a 303 px frame gave no cue). The box is a
 * labelled region the keyboard can reach and scroll. Without scripts it still scrolls, only without the line.
 */
export function ScrollBox({ label, children, className }: { label?: string; children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [more, setMore] = useState<{ left: boolean; right: boolean }>({ left: false, right: false });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => setMore({ left: el.scrollLeft > 4, right: el.scrollLeft + el.clientWidth < el.scrollWidth - 4 });
    read();
    el.addEventListener('scroll', read, { passive: true });
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(read);
    ro?.observe(el);
    if (el.firstElementChild) ro?.observe(el.firstElementChild);
    return () => { el.removeEventListener('scroll', read); ro?.disconnect(); };
  }, []);
  const hint = more.left && more.right ? 'More columns on both sides: scroll sideways.' : more.right ? 'More columns to the right: scroll sideways.' : more.left ? 'More columns to the left: scroll sideways.' : '';
  return (
    <div className="flex flex-col gap-1">
      {hint && <p role="note" className="m-0 text-small font-semibold text-ink-muted">{hint}</p>}
      <div ref={ref} {...(label ? { role: 'region', 'aria-label': label, tabIndex: 0 } : {})}
        className={cn('overflow-x-auto rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-text',
          more.right && 'shadow-[inset_-12px_0_8px_-8px_rgba(0,0,0,0.25)]', more.left && !more.right && 'shadow-[inset_12px_0_8px_-8px_rgba(0,0,0,0.25)]', className)}>
        {children}
      </div>
    </div>
  );
}
