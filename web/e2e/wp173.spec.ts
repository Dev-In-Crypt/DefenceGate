import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-173 (QA of 24 November 2026, funding), on the demo build (lib/mock): every cut-off of a multiple cut-off call on its page (C-1), the
 * budget labelled the same way in the header and in Key facts (F03, C-8), "N conditions to check" listing those N (F12), the country chips
 * that never lead to an empty list (C-12), and the neutral wording of the Spanish parts entry on /check (F34).
 */

const CALL = '/funding/1-edf-2026-additive-manufacturing-spare-parts';

test('a call page lists its cut-offs and says whose budget the figure is', async ({ page }) => {
  await visit(page, CALL, { title: /DefenceGate/, h1: 'Additive manufacturing of certified spare parts' });
  const cuts = page.locator('[data-cut-offs]');
  await expect(cuts).toHaveText('29 Sep 2026 (passed); 26 Nov 2026; 2 Mar 2027');
  await expect(page.getByText('All cut-offs', { exact: true })).toBeVisible();
  await expect(page.locator('[data-head-facts]')).toContainText('Topic budget');
  await expect(page.locator('[data-budget-scope]')).toHaveText('Budget of this topic');
});

test('"N conditions to check" lists exactly those N', async ({ page }) => {
  await visit(page, CALL, { title: /DefenceGate/, h1: 'Additive manufacturing of certified spare parts' });
  const box = page.locator('[data-apply-summary]');
  await box.getByLabel('Your country').selectOption('PL');
  await box.getByLabel('Your kind of organisation').selectOption('sme');
  const word = await box.locator('[data-page-verdict]').innerText();
  const n = Number(word.match(/(\d+) conditions? to check/)?.[1] ?? 0);
  await expect(box.locator('[data-to-check] li')).toHaveCount(n);
});

test('the country chips of /funding open all of that country’s calls, and /check words the Spanish entry neutrally', async ({ page }) => {
  await visit(page, '/funding', { title: /funding/i, h1: /funding/i });
  await expect(page.getByRole('link', { name: 'SE Sweden' })).toHaveAttribute('href', '/funding?country=SE&status=all');
  await visit(page, '/check', { title: /DefenceGate/, h1: /./ });
  await expect(page.getByRole('link', { name: /I make parts in Spain/ })).not.toContainText('cars');
});
