import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-110 (round-4 re-check of 24 October 2026, search; docs/verification/round4/wp110-selfcheck.md): the CPV finder's search reads
 * the full vocabulary with the product words (harness, wiring, stamping found "0 codes match"); a search says "Did you mean CPV
 * 31611000 Wiring sets?" on the tender list and in the global search; a services preset reads the main code only.
 */

test('the CPV finder finds harness, wiring and stamping in the full vocabulary', async ({ page }) => {
  await visit(page, '/cpv', { title: /CPV/, h1: 'CPV finder' });
  const box = page.getByLabel('Search by code or words');
  for (const [word, code] of [['harness', '31611000'], ['wiring', '31612000'], ['stamping', '34320000']] as const) {
    await box.fill(word);
    const full = page.locator('[data-cpv-full]');
    await expect(full.getByRole('link', { name: new RegExp(`^${code}`) }).first()).toBeVisible();
    await expect(page.getByText(/codes? match(es)? in the full CPV vocabulary/)).toBeVisible();
    await expect(page.getByText(/0 codes match/)).toHaveCount(0);
  }
  await box.fill('harness');
  await expect(page.locator('[data-cpv-full] a', { hasText: '31611000' }).first()).toHaveAttribute('href', '/tenders?cpv=31611');
});

test('a product search names its CPV code: on the tender list and in the global search', async ({ page }) => {
  await visit(page, '/tenders?q=wiring%20harness&status=all', { title: /tenders/i, h1: 'Tenders' });
  const hint = page.locator('[data-cpv-hints]').first();
  await expect(hint).toContainText('Did you mean');
  await expect(hint.getByRole('link', { name: 'CPV 31611000 Wiring sets' })).toHaveAttribute('href', /cpv=31611/);
  await visit(page, '/search?q=wiring%20harness', { title: /Search/, h1: 'Search' });
  await expect(page.locator('[data-cpv-hints]').first().getByRole('link', { name: 'CPV 31611000 Wiring sets' })).toHaveAttribute('href', '/tenders?cpv=31611');
});

test('a services preset reads the main product code only, a goods preset every code', async ({ page }) => {
  await visit(page, '/tenders', { title: /tenders/i, h1: 'Tenders' });
  const presets = page.locator('[data-cpv-presets]');
  await expect(presets.getByRole('link', { name: 'Vehicle repair and maintenance', includeHidden: true })).toHaveAttribute('href', '/tenders?cpv=501&cpvMain=true');
  await expect(presets.getByRole('link', { name: 'Vehicles and parts', includeHidden: true })).toHaveAttribute('href', `/tenders?cpv=${encodeURIComponent('354,341,343')}`);
});
