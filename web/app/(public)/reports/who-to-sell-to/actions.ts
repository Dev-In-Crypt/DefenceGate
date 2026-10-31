'use server';

/**
 * WP-162: the form of the "Who to sell to" report goes from the browser to the API through this action and comes back as the report.
 * Nothing of it is read, logged or kept here; the API keeps it only when `consent` is ticked. Next.js checks Origin against Host first.
 */
import { generateSellReport, deleteKeptForm, type SellForm } from '@/lib/sell-report-api';
import type { SellReport } from '@/lib/sell-report';

export type MakeResult = { ok: true; report: SellReport } | { ok: false; status: number; error: string; message?: string };

const CODE = /^\d{8}$/;
const str = (v: unknown, max: number) => (typeof v === 'string' ? v.slice(0, max) : undefined);

export async function makeReport(form: SellForm): Promise<MakeResult> {
  const body: SellForm = {
    name: str(form.name, 120) || undefined, country: str(form.country, 2), nace: str(form.nace, 12) || undefined,
    cpv: Array.isArray(form.cpv) ? form.cpv.filter((c) => typeof c === 'string' && CODE.test(c)).slice(0, 15) : [],
    size: form.size === 'sme' || form.size === 'large' ? form.size : '',
    held: Array.isArray(form.held) ? form.held.filter((h) => typeof h === 'string').slice(0, 20) : [],
    classified: str(form.classified, 8) ?? '', exports: str(form.exports, 12) ?? '', usComponents: str(form.usComponents, 8) ?? '',
    consent: form.consent === true,
  };
  const r = await generateSellReport(body);
  return r.ok ? { ok: true, report: r.data } : { ok: false, status: r.status, error: r.error, message: r.message };
}

export async function forgetForm(): Promise<boolean> {
  return (await deleteKeptForm()).ok;
}
