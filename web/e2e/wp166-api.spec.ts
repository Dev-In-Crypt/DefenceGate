import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-166 against the fake API (company 152001): "Where it wins" and "Its share" carry the one share note (lib/coverage-copy.ts
 * SHARE_NOTE): the figures come from the award notices we read, a part of defence spending, so shares are indicative.
 * Tagged @fake-api: the fake-api-* projects run it. Screenshots go to WP166_SHOTS when it is set.
 */
const SLUG = '152001-fake-defence-gmbh';

test('the company page says its shares are indicative, where it wins and under its share', { tag: '@fake-api' }, async ({ page }) => {
  await visit(page, `/suppliers/${SLUG}`, { title: /Fake Defence GmbH/, h1: 'Fake Defence GmbH' });
  const wins = page.locator('section[aria-labelledby="where-it-wins"] [data-share-coverage]');
  await expect(wins).toContainText('TED holds about a tenth of EU defence spending (ECIPE Policy Brief 20/2025). Shares are indicative.');
  await expect(wins).not.toContainText('too few');           // 12 contracts: not "very few"
  await expect(page.locator('section[aria-labelledby="share"] [data-share-coverage]')).toContainText('Shares are indicative.');
  await expect(page.locator('[data-few-awards]')).toHaveCount(0);   // the share rows stand on 250 and 1,900 contracts
  const shots = process.env.WP166_SHOTS;
  if (shots) {
    mkdirSync(shots, { recursive: true });
    await page.locator('section[aria-labelledby="where-it-wins"]').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(shots, `company-share-note-${(page.viewportSize()?.width ?? 1280) < 700 ? '375' : '1280'}.png`), fullPage: true });
  }
});

test('the competitors page carries the share note too', { tag: '@fake-api' }, async ({ page, context, baseURL }) => {
  const host = new URL(baseURL ?? 'http://127.0.0.1').hostname;
  await context.addCookies([{ name: '__Host-dg_session', value: 'a'.repeat(43), domain: host, path: '/', secure: true, httpOnly: true, sameSite: 'Lax' }]);
  await visit(page, `/suppliers/${SLUG}/competitors`, { title: /Competitors/, h1: 'Competitors of Fake Defence GmbH' });
  await expect(page.locator('[data-share-coverage]')).toContainText('Shares are indicative.');
});
