'use client';

import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Icon } from './icon';
import { CONTROL } from './field';

/**
 * The branded select: the native `<select>` stays THE control (one element: label, name, value, focus, form field, `change`),
 * and with a mouse its opened list is a listbox of our own (WAI-ARIA select-only combobox pattern, the native select being the
 * combobox) instead of the system menu.
 *
 * Why one element and not a hidden select plus a button: a second element needs its own accessible name, and then every label
 * lookup (a screen reader's, a test's `getByLabel`) finds two controls; a script that moves focus to "the field" (the wizard
 * focuses the first `aria-invalid`) would land on the hidden one. The native select is first in the DOM, labelled by its
 * `<label>`, and styled as the branded box in every case, so the closed control looks the same with and without script.
 *
 *   - No script: the system select.
 *   - A touch screen (`pointer: coarse`): the system select. The system picker is a wheel or a full-screen list with its own
 *     search, reads well with VoiceOver and TalkBack and is never clipped by a small viewport; ours would be a second, worse
 *     picker on a 375 px screen. Its options carry our surface and ink colours, and the page sets `color-scheme`, so the opened
 *     list is dark in the dark theme.
 *   - Otherwise (after mount): a press on the select does not open the system menu; it opens ours, a fixed-position portal on
 *     `document.body`, so no scroll box or sticky column clips it; it flips above the select when the space below is short and
 *     scrolls inside itself. The select gets `aria-expanded`, `aria-controls` and `aria-activedescendant`.
 *
 * Keys: Down/Up/Enter/Space open; Home/End first/last; typing jumps to the option that starts with the letters (repeat a
 * letter to step through those that share it); while open Up/Down/Home/End/PageUp/PageDown move, Enter/Space choose,
 * Escape closes, Tab chooses and moves on. Focus never leaves the select (aria-activedescendant), so it is "returned" by design.
 * `data-value` holds the value.
 */
export interface SelectOption { value: string; label: string }
type NativeProps = Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'children'>;

/** The menu is at most this high (8 rows of 44 px); less where the window is short. */
const MENU_MAX = 352;
const PAGE = 8;

interface Pos { left: number; top?: number; bottom?: number; minWidth: number; maxWidth: number; maxHeight: number }

export function ListboxSelect({ options, placeholder, accessibleName, ...rest }: NativeProps & {
  options: SelectOption[]; placeholder?: string;
  /** The name of the opened list (the visible label's text). */
  accessibleName?: string;
}) {
  const auto = useId();
  const baseId = rest.id ?? auto;
  const selectRef = useRef<HTMLSelectElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const typed = useRef<{ buf: string; timer?: ReturnType<typeof setTimeout> }>({ buf: '' });
  const items = useMemo<SelectOption[]>(() => (placeholder ? [{ value: '', label: placeholder }, ...options] : options), [options, placeholder]);

  const [custom, setCustom] = useState(false);
  const [current, setCurrent] = useState(String(rest.value ?? rest.defaultValue ?? ''));
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [pos, setPos] = useState<Pos | null>(null);

  const selIdx = Math.max(0, items.findIndex((i) => i.value === current));

  // After mount, and only without a touch screen, the custom control takes over from the native one.
  useEffect(() => { setCustom(!window.matchMedia('(pointer: coarse)').matches); }, []);

  // The display follows the native select: a controlled value changed, the form was reset, a test or the browser set it.
  useEffect(() => {
    const s = selectRef.current;
    if (s && s.value !== current) setCurrent(s.value);
  });
  useEffect(() => {
    const s = selectRef.current;
    if (!s) return;
    const sync = () => setCurrent(s.value);
    const reset = () => { setTimeout(sync, 0); };
    const form = s.form;
    s.addEventListener('change', sync);
    form?.addEventListener('reset', reset);
    return () => { s.removeEventListener('change', sync); form?.removeEventListener('reset', reset); };
  }, []);

  const place = useCallback(() => {
    const b = selectRef.current;
    if (!b) return;
    const r = b.getBoundingClientRect();
    const vh = window.innerHeight; const vw = window.innerWidth;
    const below = vh - r.bottom - 12; const above = r.top - 12;
    const down = below >= Math.min(MENU_MAX, 220) || below >= above;
    const left = Math.max(8, Math.min(r.left, vw - 8 - r.width));
    setPos({
      left, minWidth: r.width, maxWidth: Math.max(r.width, Math.min(440, vw - left - 8)),
      maxHeight: Math.max(132, Math.min(MENU_MAX, down ? below : above)),
      ...(down ? { top: r.bottom + 4 } : { bottom: vh - r.top + 4 }),
    });
  }, []);

  const openAt = (i: number) => { if (rest.disabled) return; place(); setActive(i); setOpen(true); };
  const choose = (i: number) => {
    const s = selectRef.current; const it = items[i];
    if (s && it && s.value !== it.value) {
      s.value = it.value;
      s.dispatchEvent(new Event('change', { bubbles: true }));
      setCurrent(it.value);
    }
    setOpen(false);
    s?.focus();
  };

  // While open: follow the window, close on a press outside, keep the active option in view.
  useEffect(() => {
    if (!open) return;
    const away = (e: Event) => {
      const t = e.target as Node;
      if (!menuRef.current?.contains(t) && !selectRef.current?.contains(t)) setOpen(false);
    };
    document.addEventListener('pointerdown', away, true);
    // The menu follows the select when the window or a scroll box under it moves; its own scrolling is left alone.
    const follow = (e: Event) => { if (!menuRef.current?.contains(e.target as Node)) place(); };
    window.addEventListener('resize', place);
    window.addEventListener('scroll', follow, true);
    return () => {
      document.removeEventListener('pointerdown', away, true);
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', follow, true);
    };
  }, [open, place]);
  useEffect(() => {
    if (!open) return;
    const m = menuRef.current; const el = m?.children[active] as HTMLElement | undefined;
    if (!m || !el) return;
    if (el.offsetTop < m.scrollTop) m.scrollTop = el.offsetTop - 4;
    else if (el.offsetTop + el.offsetHeight > m.scrollTop + m.clientHeight) m.scrollTop = el.offsetTop + el.offsetHeight - m.clientHeight + 4;
  }, [open, active]);

  /** The index of the option the typed letters lead to, or -1. */
  const lookup = (ch: string, from: number) => {
    const T = typed.current;
    clearTimeout(T.timer);
    T.buf += ch.toLowerCase();
    T.timer = setTimeout(() => { T.buf = ''; }, 700);
    const repeat = T.buf.length > 1 && [...T.buf].every((c) => c === T.buf[0]);
    const needle = repeat ? T.buf[0] : T.buf;
    const start = repeat || T.buf.length === 1 ? from + 1 : from;
    const n = items.length;
    const tests = [(l: string) => l.startsWith(needle), (l: string) => l.split(/[\s(,]+/).some((w) => w.startsWith(needle))];
    for (const hit of tests) {
      for (let k = 0; k < n; k++) {
        const i = (start + k) % n;
        if (hit(items[i].label.toLowerCase())) return i;
      }
    }
    return -1;
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.ctrlKey || e.metaKey || (e.altKey && e.key !== 'ArrowDown' && e.key !== 'ArrowUp')) return;
    const k = e.key; const n = items.length;
    // A space is a letter of the search while one is going on ("united k"), otherwise it opens or chooses.
    const printable = k.length === 1 && (k !== ' ' || typed.current.buf !== '');
    // The select must not change its own value on a key: we do it, with a change event, when a choice is made.
    if (printable || k.startsWith('Arrow') || k === 'Home' || k === 'End' || k === 'PageUp' || k === 'PageDown' || k === ' ' || k === 'Enter') e.preventDefault();
    if (!open) {
      if (printable) { const i = lookup(k, selIdx); if (i >= 0) openAt(i); }
      else if (['ArrowDown', 'ArrowUp', 'Enter', ' ', 'Home', 'End'].includes(k)) openAt(k === 'Home' ? 0 : k === 'End' ? n - 1 : selIdx);
      return;
    }
    const go = (i: number) => setActive(Math.max(0, Math.min(n - 1, i)));
    if (k === 'ArrowDown') go(active + 1);
    else if (k === 'ArrowUp') go(active - 1);
    else if (k === 'Home') go(0);
    else if (k === 'End') go(n - 1);
    else if (k === 'PageDown') go(active + PAGE);
    else if (k === 'PageUp') go(active - PAGE);
    else if (k === 'Escape') { e.preventDefault(); setOpen(false); }
    else if (k === 'Tab') { if (active !== selIdx) choose(active); else setOpen(false); }
    else if (printable) { const i = lookup(k, active); if (i >= 0) setActive(i); }
    else if (k === 'Enter' || k === ' ') choose(active);
  };

  const { className: nativeClass, ...nativeRest } = rest;

  return (
    <>
      <select
        {...nativeRest}
        ref={selectRef}
        id={baseId}
        {...(custom ? {
          'aria-haspopup': 'listbox' as const,
          'aria-expanded': open,
          'aria-controls': open ? `${baseId}-menu` : undefined,
          'aria-activedescendant': open ? `${baseId}-o${active}` : undefined,
          'data-value': current,
          // The press that would open the system menu opens ours; the select still takes focus.
          onMouseDown: (e: React.MouseEvent<HTMLSelectElement>) => {
            if (e.button !== 0 || rest.disabled) return;
            e.preventDefault();
            e.currentTarget.focus();
            if (open) setOpen(false); else openAt(selIdx);
          },
          onKeyDown,
          // A space opens on keydown; the click-like keyup (Firefox) would close it again.
          onKeyUp: (e: React.KeyboardEvent) => { if (e.key === ' ') e.preventDefault(); },
        } : {})}
        className={cn(CONTROL, 'cursor-pointer appearance-none pr-7', nativeClass)}
      >
        {items.map((o) => <option key={o.value} value={o.value} className="bg-surface text-ink">{o.label}</option>)}
      </select>
      <Icon icon={ChevronDown} className={cn('pointer-events-none absolute right-3.5 text-ink-muted transition-transform duration-dg', custom && open && 'rotate-180')} />
      {custom && open && pos && createPortal(
          <div
            ref={menuRef}
            id={`${baseId}-menu`}
            role="listbox"
            aria-label={accessibleName}
            onMouseDown={(e) => e.preventDefault()}
            style={{ position: 'fixed', left: pos.left, top: pos.top, bottom: pos.bottom, minWidth: pos.minWidth, maxWidth: pos.maxWidth, maxHeight: pos.maxHeight }}
            className="z-[60] w-max overflow-y-auto overscroll-contain rounded-md border border-edge bg-surface p-1 font-sans text-body text-ink shadow-[var(--shadow-menu)]"
          >
            {items.map((o, i) => (
              <div
                key={o.value}
                id={`${baseId}-o${i}`}
                role="option"
                aria-selected={i === selIdx}
                data-value={o.value}
                data-active={i === active ? '' : undefined}
                onMouseMove={() => { if (i !== active) setActive(i); }}
                onClick={() => choose(i)}
                className="flex min-h-11 cursor-pointer items-center justify-between gap-3 rounded-[10px] px-3 py-2 data-[active]:bg-surface-inset aria-selected:font-bold"
              >
                <span className="min-w-0 break-words">{o.label}</span>
                {i === selIdx && <Icon icon={Check} className="shrink-0 text-accent-text" />}
              </div>
            ))}
          </div>,
        document.body,
      )}
    </>
  );
}
