'use server';

import { redirect } from 'next/navigation';
import { unsubscribeAlerts, unsubscribeDigest } from '@/lib/account';

const TOKEN_RE = /^[0-9a-f]{64}$/;

/** WP-158: the stop link of an association's digest mail; WP-161: and of a saved-search alert mail (`kind=alerts`). A button
 * press (a POST), so a mail scanner that opens links stops nothing. */
export async function stopDigest(form: FormData): Promise<void> {
  const token = form.get('token');
  const alerts = form.get('kind') === 'alerts';
  const back = alerts ? '/unsubscribe?kind=alerts' : '/unsubscribe';
  if (typeof token !== 'string' || !TOKEN_RE.test(token)) redirect(back);
  const r = await (alerts ? unsubscribeAlerts : unsubscribeDigest)(token);
  redirect(`${back}${alerts ? '&' : '?'}${r.ok ? 'done=1' : 'failed=1'}`);
}
