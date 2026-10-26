import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-141 (round 8, r8-site/text/call114-profile.txt), on the demo build: with a saved company profile, a call of an EDIP action that only some
 * kinds of applicant may apply to (here common procurement, as 108-112; SEAP support 114 and EDPCI preparation 193 alike) says one thing in
 * every box of its page (the demo call 1, answered as such a call): the row "Who may apply" is a no, in a sentence, where it said "Check" under "Blocked by"; the blocker is not
 * printed again as "Not allowed. contracting authorities ..." or as a bare title.
 */

// the demo call whose document was read (it has the form), answered as a common-procurement call of the EDIP, as in wp102.spec.ts
const CALL = '/funding/1-edf-2026-additive-manufacturing-spare-parts';
const PROFILE = {
  version: 5, step: 6, updatedAt: '2026-10-24T10:00:00.000Z', name: '', sizeClass: 'small', country: 'ES', legalForm: 'legal_person',
  applicantKind: 'company_or_research', offering: 'products', topics: '', orgKind: 'company', headcount: 'lt50', inGroup: 'no', groupHeadcount: '',
  management: 'same', managementCountry: '', control: 'no', controlCountry: '', investor: '', uaOccupied: '', uaPartner: 'no', seapPartner: 'no',
  regime: 'dual_use', componentPct: '', componentBand: 'le35', restricted: 'no', uaComponents: 'no', eeaComponents: 'no', safeRole: 'contractor',
  statuses: {}, classified: 'no', exportIntent: 'none',
};
const SENTENCE = 'Only contracting authorities, international organisations, SEAPs and the EDA may apply to this call.';
const fact = (value: unknown, quote: string) => ({ value, note: null, quote, scope: 'call_document' });

async function serve(page: Page) {
  await page.addInitScript((value) => { window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, PROFILE);
  // the document names who may apply and nothing in it says a company may: its own row would be a "Check"
  await page.route('**/api/fit/facts*', async (route) => {
    const ids = (new URL(route.request().url()).searchParams.get('ids') ?? '').split(',').filter(Boolean);
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: Object.fromEntries(ids.map((i) => [i, {
      state: 'read', basis: 'call_document', programme: 'EDIP', topic: 'EDF-EDIP-P-2027-FNLC-CPA-TEST',
      facts: { eligible_countries: fact('EU Member States', 'Applicants must be established in an EU Member State.'),
        entity_types: fact(['Contracting authorities of Member States', 'International organisations'], 'Only contracting authorities may apply.') } }])) }) });
  });
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json',
    body: JSON.stringify({ generatedAt: '', rulesReviewed: '2026-10-20', assessments: [], general: [], roadmap: { steps: [], tracks: [] }, consultants: [], call: null, notice: '' }) }));
  await page.route('**/api/funding/*/partners*', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
    call: { id: '1', slug: '1-x', topic: null }, area: null, partners: [], countries: [], total: 0, country: null, prefer: null, note: '' }) }));
}

test('a saved company profile: the row "Who may apply" says the rule that blocks, in a sentence, in every box', async ({ page }) => {
  await serve(page);
  await visit(page, CALL, { title: /DefenceGate/, h1: /additive manufacturing/i });

  // the first screen ("Can I apply?", the saved profile's verdict)
  const top = page.locator('[data-apply-summary] [data-profile-verdict]');
  await expect(top).toHaveAttribute('data-profile-verdict', 'no');
  await expect(top).toContainText('Blocked by: contracting authorities, international organisations, SEAPs and the EDA');
  await expect(top.locator('[data-profile-line="who"]')).toHaveText(new RegExp(`^Who may apply: ${SENTENCE.replace(/[.,]/g, '\\$&')}`));
  await expect(top.locator('[data-profile-line="entity"]')).toHaveCount(0);
  await expect(top.locator('[data-profile-line="programme"]')).toHaveCount(0);

  // the form ("Check your company"), the same verdict
  const form = page.locator('section[aria-labelledby="can-you-apply-"] [aria-live="polite"]').first();
  await expect(form).toContainText('The document appears to exclude you');
  await expect(form).toContainText(`Who may apply: Not allowed. ${SENTENCE}`);
  await expect(form).not.toContainText('Who may apply: Check.');
  await expect(form).not.toContainText('Rule of the programme or the action');
  await expect(form).not.toContainText(/Not allowed\. [a-z]/);

  // "Your readiness for this call"
  const readiness = page.locator('section[aria-labelledby="readiness-1"]');
  await expect(readiness).toContainText(`Who may apply: Not allowed. ${SENTENCE}`);
  await expect(readiness).not.toContainText('Who may apply: Check.');
  await expect(readiness).not.toContainText(/Not allowed\. [a-z]/);
});
