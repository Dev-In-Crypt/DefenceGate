import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-143, item 7 (r9-site, 26 October 2026): privacy notice 1.7 names the mail processor, Brevo (Sendinblue SAS, France). /alerts
 * still said sign-in opens "once we have chosen a provider", and /data/sovereignty promised to name it later and had no row for it.
 */
test('/alerts and /data/sovereignty say what is true of the mail provider now', async ({ page }) => {
  await visit(page, '/alerts', { title: /alerts/i, h1: 'Alerts and saved searches' });
  await expect(page.locator('main')).not.toContainText('chosen a provider');
  await visit(page, '/data/sovereignty', { title: /Where the data runs/, h1: 'Where the data runs' });
  const main = page.locator('main');
  await expect(main).toContainText('Brevo (Sendinblue SAS)');
  await expect(main).toContainText('Account mail: confirmation and password links');
  await expect(main).not.toContainText('will be named in the privacy notice');
});
