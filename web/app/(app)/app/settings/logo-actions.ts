'use server';

/**
 * WP-162: the Consultant's logo on the cover of its reports. The file goes to the API (`PUT /v1/account/sell-report/logo`), which takes a
 * PNG or JPEG of at most 10 KB, checked by its first bytes; nothing is kept here.
 */
import { redirect } from 'next/navigation';
import { call } from '@/lib/account';

const MAX = 10 * 1024;
const TYPES = ['image/png', 'image/jpeg'];

export async function saveReportLogo(form: FormData): Promise<void> {
  const file = form.get('logo');
  if (!(file instanceof File) || file.size === 0 || file.size > MAX || !TYPES.includes(file.type)) redirect('/app/settings?n=invalid');
  const data = Buffer.from(await file.arrayBuffer()).toString('base64');
  const r = await call<void>('/sell-report/logo', { method: 'PUT', json: { type: file.type, data } });
  if (!r.ok && r.status === 401) redirect('/auth/expired');
  redirect(`/app/settings?n=${r.ok ? 'saved' : r.status === 422 ? 'invalid' : 'error'}`);
}

export async function deleteReportLogo(): Promise<void> {
  const r = await call<void>('/sell-report/logo', { method: 'DELETE' });
  if (!r.ok && r.status === 401) redirect('/auth/expired');
  redirect(`/app/settings?n=${r.ok ? 'saved' : 'error'}`);
}
