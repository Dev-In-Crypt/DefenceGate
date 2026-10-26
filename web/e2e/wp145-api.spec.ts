import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-145 against the fake API (e2e/support/fake-api.mjs, calls 9005 and 9006). An EDIP call whose own document says Ukrainian entities
 * cannot receive funding carries the badge on its card and its page, the page says it in a line with the document's sentence, and the
 * list filters by it. A call whose document is silent (9005) shows nothing new. Tagged @fake-api: the fake-api-* projects run it.
 */

const FUNDING = { title: /funding/i, h1: 'Funding' } as const;
const BADGE = 'No funding for Ukrainian entities';
const card = (page: import('@playwright/test').Page, title: string) => page.locator('#results article', { hasText: title });

test('the list card of a call whose document refuses funding to Ukrainian entities says so, the silent one does not', { tag: '@fake-api' }, async ({ page }) => {
  await visit(page, '/funding?q=wp145', FUNDING);
  await expect(card(page, 'Precision engagement').locator('[data-ua-no-funding]')).toHaveText(BADGE);
  await expect(card(page, 'Key electronic components')).toHaveCount(1);
  await expect(card(page, 'Key electronic components').locator('[data-ua-no-funding]')).toHaveCount(0);
});

test('the filter lists those calls only', { tag: '@fake-api' }, async ({ page }) => {
  await visit(page, '/funding?q=wp145&uaNoFunding=true', FUNDING);
  // the filter bar is folded away on a phone: the box itself, seen or not
  const box = page.locator('input[name="uaNoFunding"][value="true"]');
  await expect(box).toBeChecked();
  await expect(page.locator('label', { has: box })).toContainText('Only calls whose document says Ukrainian entities cannot receive funding');
  await expect(card(page, 'Precision engagement')).toHaveCount(1);
  await expect(card(page, 'Key electronic components')).toHaveCount(0);
});

// WP-145b: the choice is offered only where a call carries the label (none does on 26 Oct 2026), so the folded form stays short (wp47)
test('the filter is offered, with its count, only when a call carries the label', { tag: '@fake-api' }, async ({ page }) => {
  const box = page.locator('input[name="uaNoFunding"][value="true"]');
  await visit(page, '/funding?q=wp145', FUNDING);
  await expect(box).toHaveCount(1);
  await expect(box).not.toBeChecked();
  await expect(page.locator('label', { has: box })).toContainText('Only calls whose document says Ukrainian entities cannot receive funding (1)');
  // the calls of WP-132 (9002-9005): none carries it; the Ukraine filter beside it stays
  await visit(page, '/funding?q=wp132', FUNDING);
  await expect(box).toHaveCount(0);
  await expect(page.locator('input[name="ukraine"][value="true"]')).toHaveCount(1);
});

test('typed into the URL where no call carries the label, the filter stays ticked and the list is honestly empty', { tag: '@fake-api' }, async ({ page }) => {
  await visit(page, '/funding?q=wp132&uaNoFunding=true', FUNDING);
  await expect(page.locator('main')).toContainText('No calls match');
  await expect(page.locator('input[name="uaNoFunding"][value="true"]')).toBeChecked();
  await expect(card(page, 'Key electronic components')).toHaveCount(0);
  await expect(page.getByRole('link', { name: /without the Ukrainian-funding filter/ })).toBeVisible();
});

test('the call page says it in a line, with the document’s sentence', { tag: '@fake-api' }, async ({ page }) => {
  await visit(page, '/funding/9006-wp132-call-9006', { title: /Precision engagement/, h1: 'Precision engagement' });
  await expect(page.locator('[data-ua-no-funding]').first()).toHaveText(BADGE);
  const panel = page.locator('section[aria-labelledby="ukrainian-participants"]');
  await expect(panel).toContainText('Ukrainian entities cannot receive funding under this call: the call document says so.');
  await expect(panel).toContainText('From the call document');
  await expect(panel.locator('q')).toHaveText('Entities established in Ukraine are not eligible to receive funding under this call.');
  await visit(page, '/funding/9005-wp132-call-9005', { title: /Key electronic components/, h1: 'Key electronic components' });
  await expect(page.locator('[data-ua-no-funding]')).toHaveCount(0);
  await expect(page.locator('main')).not.toContainText('the call document says so');
});
