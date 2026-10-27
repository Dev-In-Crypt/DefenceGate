import { CircleAlert } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Icon } from './icon';

export const BOX = 'flex h-11 items-center gap-2 border-strong bg-surface px-4 transition-colors duration-dg focus-within:border-ink focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent-text';
export const CONTROL = 'h-full w-full min-w-0 border-0 bg-transparent font-sans text-body text-ink outline-none focus-visible:outline-none disabled:cursor-not-allowed disabled:text-ink-muted';

export interface FieldProps { label?: string; hint?: string; error?: string; className?: string }

export function Field({ id, label, hint, error, className, children }: FieldProps & { id: string; children: React.ReactNode }) {
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      {/* WP-150: the label 8 px above its control (4 of its own, 4 of the gap); the hint stays 4 px under it */}
      {label && <label htmlFor={id} className="mb-1 text-label text-ink">{label}</label>}
      {children}
      {error ? (
        <span id={`${id}-help`} className="flex items-center gap-1 text-small text-alert"><Icon icon={CircleAlert} size="inline" />{error}</span>
      ) : hint ? <span id={`${id}-help`} className="text-small text-ink-muted">{hint}</span> : null}
    </div>
  );
}

export const boxCls = (error?: string, disabled?: boolean, pill?: boolean) =>
  cn(BOX, pill ? 'rounded-pill' : 'rounded-md', error ? 'border-alert' : 'border-input-edge', disabled && 'bg-surface-inset');
