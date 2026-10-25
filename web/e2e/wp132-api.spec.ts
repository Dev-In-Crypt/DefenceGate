import { expect, test } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-132 (round-7 funding audit of 25 October 2026) against the fake API (e2e/support/fake-api.mjs, calls 9001-9005), with the site clock
 * pinned to 12 October 2026, 08:00 UTC. Tagged @fake-api: it runs in the fake-api-* projects of playwright.config.ts.
 */

test('a call outside the scope rule says so, is not indexed and has no dual-use or closing label', { tag: '@fake-api' }, async ({ page }) => {
  await visit(page, '/funding/9001-wp132-call-9001', { title: /RAISE/, h1: 'RAISE doctoral networks' });
  await expect(page.locator('[data-out-of-scope]')).toContainText('outside DefenceGate’s scope');
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/);
  await expect(page.locator('main')).not.toContainText('Closing soon');
  await expect(page.locator('main').getByText('Dual-use', { exact: true })).toHaveCount(0);
  await expect(page.locator('#can-you-apply-')).toHaveCount(0);
  await expect(page.locator('[data-call-ics]')).toHaveCount(0);
});

test('a call the source stopped listing says since when and is not shown open', { tag: '@fake-api' }, async ({ page }) => {
  await visit(page, '/funding/9002-wp132-call-9002', { title: /European network for upscaling/, h1: 'European network for upscaling venture builders' });
  await expect(page.locator('[data-unlisted]')).toContainText('has not listed this call since 7 Oct 2026');
  await expect(page.getByText('No longer listed', { exact: true }).first()).toBeVisible();
  await expect(page.locator('main')).not.toContainText('The source still lists this call');
  await expect(page.locator('[data-call-ics]')).toHaveCount(0);
});

test('on its closing day a date-only call says to check the hour, and a timed one says 17:00 Brussels', { tag: '@fake-api' }, async ({ page }) => {
  await visit(page, '/funding/9003-wp132-call-9003', { title: /Advanced materials/, h1: 'Advanced materials' });
  await expect(page.locator('[data-deadline]').first()).toContainText('Closing day: check the cut-off hour');
  // the opening date is a date: no time zone (it read "6 Nov 2025 UTC")
  await expect(page.getByText('6 Nov 2025 (date only)').first()).toBeVisible();
  await expect(page.locator('main')).not.toContainText('6 Nov 2025 UTC');
  await visit(page, '/funding/9004-wp132-call-9004', { title: /cybersecurity/i, h1: 'Strengthening cybersecurity capacities' });
  await expect(page.locator('[data-deadline]').first()).toContainText('Closes today');
  await expect(page.locator('[data-deadline]').first()).toContainText('17:00 CEST (Brussels)');
});

test('an EDIP call filed under the EDF names its programme under the title', { tag: '@fake-api' }, async ({ page }) => {
  await visit(page, '/funding/9005-wp132-call-9005', { title: /Key electronic components/, h1: 'Key electronic components' });
  await expect(page.getByText('European Commission · European Defence Industry Programme').first()).toBeVisible();
});

test('the call CSV writes a date-only deadline as the date and a call no longer listed as such', { tag: '@fake-api' }, async ({ request }) => {
  const r = await request.get('/funding/export.csv?q=wp132&status=all');
  expect(r.status()).toBe(200);
  const lines = (await r.text()).replace(/^﻿/, '').split(/\r?\n/);
  const header = lines.find((l) => l.includes('title,funder'))!.split(',');
  const row = (id: string) => lines.find((l) => l.startsWith(`${id},`))!;
  const cell = (id: string, name: string) => row(id).split(',')[header.indexOf(name)];
  expect(cell('9003', 'deadline_utc')).toBe('2026-10-12');
  expect(cell('9004', 'deadline_utc')).toBe('2026-10-12T15:00:00Z');
  expect(cell('9002', 'deadline_utc')).toBe('2027-02-02');
  expect(row('9002')).toContain('No longer listed by the source');
  expect(cell('9005', 'programme')).toBe('European Defence Industry Programme');
});
