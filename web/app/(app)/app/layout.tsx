import type { Metadata } from 'next';

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function AppLayout({ children }: { children: React.ReactNode }) {
  // P3: sidebar navigation, top bar with search, plan badge, account menu.
  return <>{children}</>;
}
