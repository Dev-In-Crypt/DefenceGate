import { useId } from 'react';
import { ChevronDown, CircleAlert, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Icon } from './icon';
import { CONTROL, Field, boxCls, type FieldProps } from './field';
import { ListboxSelect } from './select';

export function TextInput({ label, hint, error, className, search, ...rest }: FieldProps & { search?: boolean } & React.InputHTMLAttributes<HTMLInputElement>) {
  const auto = useId(); const id = rest.id ?? auto;
  return (
    <Field id={id} label={label} hint={hint} error={error} className={className}>
      <div className={boxCls(error, rest.disabled, search)}>
        {search && <Icon icon={Search} className="shrink-0 text-ink-muted" />}
        <input id={id} type={search ? 'search' : 'text'} aria-invalid={!!error || undefined} aria-describedby={error || hint ? `${id}-help` : undefined} className={CONTROL} {...rest} />
      </div>
    </Field>
  );
}

/**
 * The branded select: the native `<select>` is the control and the one element the label points at; with script and a mouse
 * its opened list is a listbox of our own (`ListboxSelect`, select.tsx), on a phone and without script the system picker.
 */
export function Select({ label, hint, error, className, options, placeholder, ...rest }: FieldProps & { options: { value: string; label: string }[]; placeholder?: string } & React.SelectHTMLAttributes<HTMLSelectElement>) {
  const auto = useId(); const id = rest.id ?? auto;
  return (
    <Field id={id} label={label} hint={hint} error={error} className={className}>
      <div className={cn(boxCls(error, rest.disabled), 'relative')}>
        <ListboxSelect {...rest} id={id} options={options} placeholder={placeholder} accessibleName={label ?? rest['aria-label']}
          aria-invalid={!!error || undefined} aria-describedby={error || hint ? `${id}-help` : undefined} />
      </div>
    </Field>
  );
}

export function Textarea({ label, hint, error, className, ...rest }: FieldProps & React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const auto = useId(); const id = rest.id ?? auto;
  return (
    <Field id={id} label={label} hint={hint} error={error} className={className}>
      <textarea id={id} aria-invalid={!!error || undefined} className={cn(boxCls(error, rest.disabled), 'h-auto min-h-28 rounded-md px-4 py-3 font-sans text-body text-ink')} {...rest} />
    </Field>
  );
}

/** Native checkbox/radio, 20px, ink border, primary fill when checked. */
export function Choice({ type = 'checkbox', label, hint, ...rest }: { type?: 'checkbox' | 'radio'; label: React.ReactNode; hint?: string } & Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'>) {
  return (
    <label className={cn('flex min-h-11 cursor-pointer items-start gap-2.5 pt-3 text-body', rest.disabled && 'cursor-not-allowed text-ink-muted')}>
      <input type={type} className={cn('mt-0.5 size-5 shrink-0 cursor-[inherit] border-strong border-ink accent-primary', type === 'checkbox' ? 'rounded-[6px]' : 'rounded-pill')} {...rest} />
      <span className="flex flex-col">
        <span>{label}</span>
        {hint && <span className="text-small text-ink-muted">{hint}</span>}
      </span>
    </label>
  );
}

/**
 * A group of radios or checkboxes under one question. With `id`, a `hint` and an `error` are tied to the group (`aria-describedby`
 * on the fieldset, read when focus enters it) and the error is shown inside it, as for a single field (WP-58).
 */
export function Fieldset({ legend, hint, error, id, children, className }: {
  legend: string; hint?: string; error?: string; id?: string; children: React.ReactNode; className?: string;
}) {
  const hintId = id && hint ? `${id}-hint` : undefined;
  const errorId = id && error ? `${id}-error` : undefined;
  return (
    <fieldset aria-describedby={[hintId, errorId].filter(Boolean).join(' ') || undefined} className={cn('m-0 flex min-w-0 flex-col border-0 p-0', className)}>
      <legend className="mb-1 p-0 text-label text-ink">{legend}</legend>
      {hint && <p id={hintId} className="m-0 max-w-prose text-small text-ink-muted">{hint}</p>}
      {error && <p id={errorId} className="m-0 flex items-center gap-1 text-small font-bold text-alert"><Icon icon={CircleAlert} size="inline" />{error}</p>}
      {children}
    </fieldset>
  );
}

/**
 * A group of a filter form that folds away: the summary is the legend (with how many of its options are chosen), the options
 * stay in the form whether it is open or not, so a closed group is still submitted. Native `<details>`: it works without
 * script. A group with a chosen option opens by itself. `scroll` keeps a long list (31 countries) in a box of its own.
 * Options are 36 px apart here (a filter column is dense); the label is the target, 36 px high.
 */
export function FoldGroup({ legend, children, className, open = true, count = 0, scroll = false }: {
  legend: string; children: React.ReactNode; className?: string; open?: boolean; count?: number; scroll?: boolean;
}) {
  return (
    <details open={open || count > 0 || undefined} className={cn('group/fg min-w-0 border-t border-line first:border-t-0', className)}>
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 text-label text-ink [&::-webkit-details-marker]:hidden">
        <span>
          {legend}
          {count > 0 && <span className="ml-2 rounded-pill bg-surface-inset px-2 py-0.5 font-mono text-label font-medium tabular-nums">{count}</span>}
        </span>
        <Icon icon={ChevronDown} size="inline" className="shrink-0 text-ink-muted transition-transform duration-dg group-open/fg:rotate-180" />
      </summary>
      <fieldset className="m-0 flex min-w-0 flex-col border-0 p-0 pb-2">
        <legend className="sr-only">{legend}</legend>
        <div className={cn('flex min-w-0 flex-col [&_label]:min-h-9 [&_label]:pt-1.5', scroll && 'max-h-64 overflow-y-auto pr-1')}>{children}</div>
      </fieldset>
    </details>
  );
}
