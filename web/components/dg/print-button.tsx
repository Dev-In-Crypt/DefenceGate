'use client';

import { Printer } from 'lucide-react';
import { Button } from './button';

/** Opens the browser's print dialog. Hidden in print by the page that uses it (`print:hidden`). */
export function PrintButton({ children = 'Print this page', className }: { children?: string; className?: string }) {
  return <Button icon={Printer} onClick={() => window.print()} className={className}>{children}</Button>;
}
