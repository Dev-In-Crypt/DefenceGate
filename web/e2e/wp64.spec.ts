import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-64: the Spain, Germany and NATO/EU rules in the readiness pages, for a civilian Spanish automotive supplier with ISO 9001.
 * The answer is `e2e/fixtures/assess-es-auto.json`, which the backend generates from the seed (see readiness.spec.ts). What this proves:
 * the Spanish defence supplier card is shown with its rules, quotes and sources; a question the wizard does not ask is named without a
 * link to a step; the "consultant needed" flags are listed; the RID is a roadmap step that, once marked done, is sent; the PECAL step
 * explains its chicken-and-egg.
 */

const fixture = (name: string) => JSON.parse(readFileSync(path.join(__dirname, 'fixtures', name), 'utf8'));

interface Posted { profile: Record<string, unknown>; statuses: Record<string, string> }

const ES_AUTO = {
  version: 2, step: 6, updatedAt: '2026-10-21T10:00:00.000Z', name: '', sizeClass: 'medium', country: 'ES', legalForm: 'legal_person', applicantKind: 'company_or_research',
  management: 'same', managementCountry: '', control: 'no', uaOccupied: '', uaPartner: '', seapPartner: '', regime: 'none', componentPct: '15', restricted: 'no',
  uaEeaComponents: 'no', safeRole: 'other_supplier', statuses: { 'REQ-ISO9001': 'held' }, classified: 'no', exportIntent: 'within_eu',
};

async function setUp(page: Page): Promise<Posted[]> {
  const posted: Posted[] = [];
  await page.route('**/api/readiness/assess', async (route) => {
    posted.push(route.request().postDataJSON() as Posted);
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture('assess-es-auto.json')) });
  });
  await page.addInitScript((value) => { if (!window.localStorage.getItem('dg.profile.v1')) window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, ES_AUTO);
  return posted;
}

test('the Spanish defence supplier route: rules with their quotes and sources, unasked questions, consultant flags', async ({ page }) => {
  const posted = await setUp(page);
  await visit(page, '/readiness/results', { title: /readiness results|your readiness/i, h1: 'Your readiness results' });
  const card = page.getByRole('article', { name: 'Spanish defence supplier (MoD)' });
  await expect(card).toBeVisible();
  await expect(card).toHaveAttribute('data-verdict', 'conditional');
  // the RID is asked by no step of the wizard: since WP-65 the supplier profile asks it, so the question links there, not to a step
  await expect(card.locator('[data-supplier-asks="REQ-RID"]')).toContainText('Does the company hold a current RID certificate');
  await expect(card.getByRole('link', { name: /current RID certificate/ })).toHaveAttribute('href', '/readiness/supplier#q-REQ-RID');
  await card.getByText(/Show the \d+ rules behind this/).click();
  const rid = card.locator('[data-rule="ES-RID"]');
  await expect(rid).toHaveAttribute('data-outcome', 'unknown');
  await rid.getByText('Show the text of the source').click();
  await expect(rid.getByText(/REGISTRO DE LA INDUSTRIA DE DEFENSA \(RID\)/)).toBeVisible();
  await expect(rid.getByText(/Quoted from the official source linked here, read on 2026-10-20/)).toBeVisible();
  await expect(rid.getByRole('link', { name: 'Open the source' })).toHaveAttribute('href', 'https://sede.defensa.gob.es/acceda/procedimientos');
  // the prime-qualification flag on the PECAL contract rule, and the list of specialist questions
  await expect(card.locator('[data-rule="ES-PECAL-CONTRACT"] [data-consultant]')).toContainText('Prime qualification');
  const flags = page.getByRole('region', { name: 'Where you need a specialist' });
  await expect(flags.locator('[data-consultant-flag="US-COMPONENTS"]')).toContainText('ITAR');
  await expect(flags.locator('[data-consultant-flag="ES-FOREIGN-CAPITAL"]')).toContainText('RD 664/1999');
  // nothing about the company left the browser but the computing call, and the unasked RID was not sent as "not held"
  expect(posted.length).toBeGreaterThan(0);
  expect(posted[posted.length - 1].statuses['REQ-RID']).toBeUndefined();
});

test('the roadmap: the RID step, marked done, is sent; the PECAL step explains its chicken-and-egg', async ({ page }) => {
  const posted = await setUp(page);
  await visit(page, '/readiness/roadmap', { title: /roadmap/i, h1: 'Your roadmap' });
  const pecal = page.locator('[data-step="REQ-PECAL"]');
  await expect(pecal.locator('[data-step-note="REQ-PECAL"]')).toContainText('not a block before a first contract');
  await expect(pecal).toContainText(/Only when a contract names it/);
  const rid = page.locator('[data-step="REQ-RID"]');
  await expect(rid).toContainText('Needed now');
  await rid.getByRole('button', { name: /Mark as done: RID registration/ }).click();
  await expect.poll(() => posted[posted.length - 1]?.statuses['REQ-RID']).toBe('held');
  expect(await page.evaluate(() => JSON.parse(window.localStorage.getItem('dg.profile.v1') ?? '{}').statuses['REQ-RID'])).toBe('held');
});
