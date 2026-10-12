import { useId } from 'react';
import { CircleAlert, ChevronDown, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Icon } from './icon';

const BOX = 'flex h-11 items-center gap-2 border-strong bg-surface px-4 transition-colors duration-dg focus-within:border-ink focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent-text';
const CONTROL = 'h-full w-full min-w-0 border-0 bg-transparent font-sans text-body text-ink outline-none focus-visible:outline-none disabled:cursor-not-allowed disabled:text-ink-muted';

interface FieldProps { label?: string; hint?: string; error?: string; className?: string }

function Field({ id, label, hint, error, className, children }: FieldProps & { id: string; children: React.ReactNode }) {
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      {label && <label htmlFor={id} className="text-label text-ink">{label}</label>}
      {children}
      {error ? (
        <span id={`${id}-help`} className="flex items-center gap-1 text-small text-alert"><Icon icon={CircleAlert} size="inline" />{error}</span>
      ) : hint ? <span id={`${id}-help`} className="text-small text-ink-muted">{hint}</span> : null}
    </div>
  );
}

const boxCls = (error?: string, disabled?: boolean, pill?: boolean) =>
  cn(BOX, pill ? 'rounded-pill' : 'rounded-md', error ? 'border-alert' : 'border-line', disabled && 'bg-surface-inset');

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

export function Select({ label, hint, error, className, options, placeholder, ...rest }: FieldProps & { options: { value: string; label: string }[]; placeholder?: string } & React.SelectHTMLAttributes<HTMLSelectElement>) {
  const auto = useId(); const id = rest.id ?? auto;
  return (
    <Field id={id} label={label} hint={hint} error={error} className={className}>
      <div className={cn(boxCls(error, rest.disabled), 'relative')}>
        <select id={id} aria-invalid={!!error || undefined} aria-describedby={error || hint ? `${id}-help` : undefined} className={cn(CONTROL, 'cursor-pointer appearance-none pr-7')} {...rest}>
          {placeholder && <option value="">{placeholder}</option>}
          {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <Icon icon={ChevronDown} className="pointer-events-none absolute right-3.5 text-ink-muted" />
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

export function Fieldset({ legend, children, className }: { legend: string; children: React.ReactNode; className?: string }) {
  return (
    <fieldset className={cn('m-0 flex min-w-0 flex-col border-0 p-0', className)}>
      <legend className="mb-1 p-0 text-label text-ink">{legend}</legend>
      {children}
    </fieldset>
  );
}
