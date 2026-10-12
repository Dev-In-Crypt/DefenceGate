import * as React from 'react';
import Link from 'next/link';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Icon } from './icon';

export const buttonVariants = cva(
  'inline-flex min-h-11 items-center justify-center gap-2 whitespace-nowrap rounded-pill border-strong border-transparent px-5 py-3 font-sans text-small font-bold no-underline transition-colors duration-dg ease-dg hover:no-underline disabled:cursor-not-allowed disabled:opacity-45 aria-disabled:pointer-events-none aria-disabled:opacity-45',
  {
    variants: {
      variant: {
        primary: 'border-primary bg-primary text-on-primary hover:border-primary-hover hover:bg-primary-hover active:border-primary-press active:bg-primary-press',
        secondary: 'border-ink bg-surface text-ink hover:bg-surface-inset',
        text: 'bg-transparent px-1 text-link hover:underline',
      },
      fullWidth: { true: 'w-full' },
    },
    defaultVariants: { variant: 'primary' },
  },
);

type Base = VariantProps<typeof buttonVariants> & { icon?: LucideIcon; iconRight?: LucideIcon; children: React.ReactNode; className?: string };
type AsButton = Base & React.ButtonHTMLAttributes<HTMLButtonElement> & { href?: undefined; asChild?: boolean };
type AsLink = Base & { href: string; external?: boolean; 'aria-label'?: string };

export function Button(props: AsButton | AsLink) {
  const { variant, fullWidth, icon, iconRight, children, className } = props;
  const cls = cn(buttonVariants({ variant, fullWidth }), className);
  const content = (
    <>
      {icon && <Icon icon={icon} size="button" />}
      {children}
      {iconRight && <Icon icon={iconRight} size="button" />}
    </>
  );
  if ('href' in props && props.href) {
    const { href, external } = props;
    return external ? (
      <a href={href} className={cls} target="_blank" rel="noopener noreferrer" aria-label={props['aria-label']}>{content}</a>
    ) : (
      <Link href={href} className={cls} aria-label={props['aria-label']}>{content}</Link>
    );
  }
  const { asChild, variant: _v, fullWidth: _f, icon: _i, iconRight: _r, children: _c, className: _cn, type = 'button', ...rest } = props as AsButton;
  if (asChild) return <Slot className={cls} {...rest}>{children}</Slot>;
  return <button type={type} className={cls} {...rest}>{content}</button>;
}
