import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-167 (owner, 31 Oct 2026): the call document's own total next to the portal's figure, in small type, with a link to the document
 * (the demo's Ukraine Support Instrument call), and the tracker entry on Ukraine's EDF association in force since 16 October 2026.
 * Screenshots go to WP167_SHOTS when it is set (the self-check).
 */
const SHOTS = process.env.WP167_SHOTS;

async function shot(page: Page, name: string) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  const w = page.viewportSize()?.width ?? 0;
  await page.screenshot({ path: path.join(SHOTS, `${name}-${w}.png`), fullPage: false });
}

test('the call page shows the call document total next to the portal budget, with the document', async ({ page }) => {
  await visit(page, '/funding/6-edip-2026-supply-chain-security-raw-materials', { title: /Supply chain security/, h1: 'Supply chain security for critical raw materials' });
  const line = page.locator('[data-document-budget]');
  await expect(line).toHaveCount(1);
  await expect(line).toContainText('Call document total: EUR 20.5 million, including EUR 20 million from the voted EU budget.');
  await expect(line.getByRole('link', { name: /call document/ })).toHaveAttribute('href', /^https:\/\/ec\.europa\.eu\/.+\.pdf$/);
  // the portal's figure stays the budget
  await expect(line.locator('xpath=..')).toContainText('EUR 20,000,000');
  await line.scrollIntoViewIfNeeded();
  await shot(page, 'call-document-budget');
  // a call without a differing document total has no such line
  await visit(page, '/funding/1-edf-2026-additive-manufacturing-spare-parts', { title: /Additive manufacturing/, h1: 'Additive manufacturing of certified spare parts' });
  await expect(page.locator('[data-document-budget]')).toHaveCount(0);
});

test('the tracker says Ukraine\'s EDF association is in force since 16 October 2026 and quotes the Commission', async ({ page }) => {
  await visit(page, '/regulation', { title: /Regulatory tracker/, h1: 'Regulatory tracker' });
  const entry = page.locator('li#edf-ukraine-association-in-force');
  await expect(entry).toContainText("EDF: Ukraine's association is in force since 16 October 2026");
  await expect(entry).toContainText('The Ukrainian association with the European Defence Fund (EDF) and financing under the European Defence Industry Programme (EDIP) agreements have come into force.');
  await expect(page.locator('li#edf-ukraine-in-force-unconfirmed')).toHaveCount(0);
  await entry.scrollIntoViewIfNeeded();
  await shot(page, 'tracker-edf-ukraine');
});
