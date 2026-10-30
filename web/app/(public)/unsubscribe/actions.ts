'use server';

import { redirect } from 'next/navigation';
import { unsubscribeDigest } from '@/lib/account';

const TOKEN_RE = /^[0-9a-f]{64}$/;

/** WP-158: the stop link of an association's digest mail. A button press (a POST), so a mail scanner that opens links stops nothing. */
export async function stopDigest(form: FormData): Promise<void> {
  const token = form.get('token');
  if (typeof token !== 'string' || !TOKEN_RE.test(token)) redirect('/unsubscribe');
  const r = await unsubscribeDigest(token);
  redirect(r.ok ? '/unsubscribe?done=1' : '/unsubscribe?failed=1');
}
