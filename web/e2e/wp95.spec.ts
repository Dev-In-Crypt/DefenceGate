import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-95 (persona round of 23 October 2026, A1): an award notice names its winners and says what its value is; a supplier's
 * framework ceilings and estimates are listed apart from the contract values, with its largest contracts and the framework a
 * call-off is based on; the change list tells a new award from a new tender. Mock build (lib/mock).
 */

test('an award notice names its legal-entity winners with a link, counts a person, and labels the awarded value', async ({ page }) => {
  await visit(page, '/tenders/7-packaging-and-logistics-services', { title: /Packaging and logistics services/, h1: 'Packaging and logistics services' });
  const awarded = page.locator('[data-awarded-to]');
  await expect(awarded).toContainText('Awarded to:');
  await expect(awarded.getByRole('link', { name: 'Demo Logistics B.V.' })).toHaveAttribute('href', '/suppliers/4-demo-logistics-bv');
  await expect(awarded).toContainText('a natural person, not named');
  await expect(page.getByLabel('Key facts').getByText('Awarded value', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Key facts').getByText('Estimated value', { exact: true })).toHaveCount(0);
  await expect(page.locator('[data-other-buyers]')).toContainText('(joint procurement)');
  await expect(page.getByText('Buyers:', { exact: true })).toBeVisible();
});

test('a notice with no award shows no winner block and keeps "Estimated value"', async ({ page }) => {
  await visit(page, '/tenders/2-workshop-consumables-supply', { title: /workshop consumables/i, h1: 'Supply of workshop consumables' });
  await expect(page.locator('[data-awarded-to]')).toHaveCount(0);
  await expect(page.getByLabel('Key facts').getByText('Estimated value', { exact: true })).toBeVisible();
});

test('the supplier page lists ceilings apart, names the largest contracts and the framework of a call-off', async ({ page }) => {
  await visit(page, '/suppliers/1-demo-airframes-gmbh', { title: /Demo Airframes GmbH/, h1: 'Demo Airframes GmbH' });
  const details = page.locator('details', { has: page.locator('summary', { hasText: 'Contract values' }) }).first();
  await details.locator('summary').click();
  await expect(details.locator('[data-value-apart]')).toHaveText('Framework ceilings, not added to the contract values: EUR 5,000,000 (1 framework).');
  const largest = details.locator('[data-largest] li');
  await expect(largest).toHaveCount(3);
  await expect(largest.first()).toContainText('EUR 1,800,000');
  await expect(largest.first().getByRole('link')).toHaveAttribute('href', '/tenders/904');
  await expect(page.locator('[data-framework]')).toContainText('Call-off under the framework agreement 2026/S 010-000');
  await expect(page.locator('[data-framework] a')).toHaveAttribute('href', '/tenders/900');
});

test('the change list names new award notices apart from new notices', async ({ page }) => {
  await visit(page, '/changes', { title: /What changed/, h1: 'What changed' });
  await expect(page.getByText('new award notices', { exact: false }).first()).toBeVisible();
  await expect(page.locator('select option', { hasText: 'New award notices' })).toHaveCount(1);
});
