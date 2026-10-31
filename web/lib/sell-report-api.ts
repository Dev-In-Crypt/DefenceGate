import 'server-only';

/**
 * WP-162: the calls of the "Who to sell to" report (backend/dgate/sell_report.py). The form goes to the API in the request body and
 * is not read, logged or kept here; the API keeps it only when the account ticked the consent box.
 */
import { call, type AccountResult } from './account';
import { http } from './api';
import { isSellReport, type SellReport } from './sell-report';

const TIMEOUT = 30_000;           // a report reads the demand map, the open lists and the rules: seconds, not the 10 s default

function parse(raw: unknown): SellReport {
  if (!isSellReport(raw)) throw new Error('bad report');
  return raw;
}

export interface SellForm {
  org?: string; name?: string; country?: string; cpv?: string[]; nace?: string; size?: 'sme' | 'large' | '';
  held?: string[]; classified?: string; exports?: string; usComponents?: string; consent?: boolean;
}

/** One counted report (402 `plan_required` / `report_quota`, 404 `not_open` while reports are switched off). */
export const generateSellReport = (form: SellForm): Promise<AccountResult<SellReport>> =>
  call<SellReport>('/sell-report', { method: 'POST', json: form, timeoutMs: TIMEOUT }, parse);

/** The sample for a signed-in account: companies named under the mosaic rule; never counted. */
export const getNamedSample = (): Promise<AccountResult<SellReport>> => call<SellReport>('/sell-report/sample', { timeoutMs: TIMEOUT }, parse);

/** The form this account chose to keep, or null. */
export async function getKeptForm(): Promise<SellForm | null> {
  const r = await call<{ profile: SellForm }>('/sell-report/profile');
  return r.ok && r.data && typeof r.data.profile === 'object' ? r.data.profile : null;
}

export const deleteKeptForm = () => call<void>('/sell-report/profile', { method: 'DELETE' });

/** The public sample (no company named in section 3), or null while reports are switched off. */
export async function getPublicSample(): Promise<SellReport | null> {
  if (!process.env.DG_API_URL) return null;
  const r = await http<unknown>('/v1/sell-report/sample', 'revalidate', 60 * 60).catch(() => null);
  return isSellReport(r) ? r : null;
}
