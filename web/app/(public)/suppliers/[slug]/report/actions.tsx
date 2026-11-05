'use server';

/**
 * The company report is counted here, from the page's button (a POST; Next.js checks Origin against Host first), never by opening the
 * page: a link or a redirect from another site must not spend an account's reports (security review of 5 November 2026).
 */
import { getUserState } from '@/lib/account';
import { Gate, loadReport, openAndRender } from './report-view';

export async function openCompanyReport(slug: unknown): Promise<React.ReactNode> {
  const l = await loadReport(typeof slug === 'string' ? slug : '');
  if (l.kind !== 'ok') return <p className="m-0" data-report-gone>There is no company report at this address.</p>;
  if (!l.c.available) return <Gate name={l.s.name} slug={l.s.slug}><p className="m-0">The figures of this report are being renewed. Try again in a few minutes.</p></Gate>;
  return openAndRender(l, await getUserState());
}
