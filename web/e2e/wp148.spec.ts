import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-148 (26 October 2026): privacy notice 1.8 names Cloudflare as processor for network security and content delivery
 * (docs/legal/drafts/privacy-cloudflare-draft.md, approved by the owner), and /data/sovereignty no longer says it is not a proxy.
 */
test('/privacy 1.8: Cloudflare as processor, its two cookies, the DPF basis, and no "(USA)" or "does not pass through"', async ({ page }) => {
  await visit(page, '/privacy', { title: /privacy/i, h1: 'Privacy notice', text: [
    'Version 1.8, published 26 October 2026 (Cloudflare as processor for network security and content delivery)',
    'Requests to the site are processed by Cloudflare, our provider of network security and content delivery (section 2).',
    'the request first reaches Cloudflare, which passes it on to our server',
    'Cloudflare, Inc. acts as our processor (Art. 28 GDPR) for network security and content delivery.',
    '__cf_bm', 'cf_clearance',
    'Where data is processed outside the EEA, the transfer is based on the EU-US Data Privacy Framework (Art. 45 GDPR).',
  ] });
  const main = page.locator('main');
  await expect(main).not.toContainText('Cloudflare, Inc. (USA)');
  await expect(main).not.toContainText('Traffic to the site does not pass through Cloudflare');
  await expect(main).not.toContainText('sets no cookie.');
});

test('/data/sovereignty: the server is reached through Cloudflare’s proxy, and the Cloudflare row says so', async ({ page }) => {
  await visit(page, '/data/sovereignty', { title: /Where the data runs/, h1: 'Where the data runs', text: [
    'Visitors reach it through Cloudflare’s proxy (below).',
    'Domain registration, name service (DNS) and the proxy in front of the server',
    'all requests to the site pass through it (privacy notice, sections 2 and 4)',
  ] });
  const main = page.locator('main');
  await expect(main).not.toContainText('It is not a proxy');
  await expect(main).not.toContainText('visitors connect to it directly');
});
