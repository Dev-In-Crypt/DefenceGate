import { expect, test, type Page } from '@playwright/test';
import { visit } from './helpers';

/**
 * WP-102 (round 3, 24 October 2026), on the demo build: one verdict per call page (the "Check your company" box says the saved profile's
 * verdict, the programme's lines included, until the visitor changes an answer), and a failed look-up of the call's rules is said as such,
 * never as "Rules not read" (BM-01 69).
 */

const CALL = '/funding/1-edf-2026-additive-manufacturing-spare-parts';
const PROFILE = {
  version: 5, step: 6, updatedAt: '2026-10-24T10:00:00.000Z', name: '', sizeClass: 'small', country: 'ES', legalForm: 'legal_person',
  applicantKind: 'company_or_research', offering: 'products', topics: '', orgKind: 'company', headcount: 'lt50', inGroup: 'no', groupHeadcount: '',
  management: 'same', managementCountry: '', control: 'no', controlCountry: '', investor: '', uaOccupied: '', uaPartner: 'no', seapPartner: 'no',
  regime: 'dual_use', componentPct: '', componentBand: 'le35', restricted: 'no', uaComponents: 'no', eeaComponents: 'no', safeRole: 'contractor',
  statuses: {}, classified: 'no', exportIntent: 'none',
};
const save = (page: Page) => page.addInitScript((value) => { window.localStorage.setItem('dg.profile.v1', JSON.stringify(value)); }, PROFILE);

async function quiet(page: Page, facts: (ids: string[]) => { status: number; body: unknown }) {
  await page.route('**/api/fit/facts*', async (route) => {
    const ids = (new URL(route.request().url()).searchParams.get('ids') ?? '').split(',').filter(Boolean);
    const r = facts(ids);
    // a failed status is answered after the page's own checks (the browser logs it as a console error, which `visit` refuses)
    if (r.status !== 200) await new Promise((done) => setTimeout(done, 1500));
    await route.fulfill({ status: r.status, contentType: 'application/json', body: JSON.stringify(r.body) });
  });
  await page.route('**/api/readiness/assess', (route) => route.fulfill({ status: 200, contentType: 'application/json',
    body: JSON.stringify({ generatedAt: '', rulesReviewed: '2026-10-20', assessments: [], general: [], roadmap: { steps: [], tracks: [] }, consultants: [], call: null, notice: '' }) }));
  await page.route('**/api/funding/*/partners*', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
    call: { id: '1', slug: '1-x', topic: null }, area: null, partners: [], countries: [], total: 0, country: null, prefer: null,
    note: 'No earlier projects can be compared with this call.' }) }));
}

test('the "Check your company" box gives the saved profile\'s one verdict, with the rule of the action that blocks it', async ({ page }) => {
  // the call answers as a common-procurement call of the EDIP: a company cannot apply (Article 11(2)), whatever the document's facts say
  await quiet(page, (ids) => ({ status: 200, body: { items: Object.fromEntries(ids.map((i) => [i, { state: 'read', basis: 'call_document', programme: 'EDF',
    topic: 'EDF-EDIP-P-2027-FNLC-CPA-AMDS', facts: { eligible_countries: { value: 'Legal entities established in EU Member States', note: null, quote: 'Applicants must be established in an EU Member State.', scope: 'call_document' } } }])) } }));
  await save(page);
  await visit(page, CALL, { title: /DefenceGate/, h1: /additive manufacturing/i });
  await expect(page.locator('[data-apply-summary] [data-profile-verdict]')).toHaveAttribute('data-profile-verdict', 'no');
  const results = page.locator('section[aria-labelledby="can-you-apply-"] [aria-live="polite"]').first();
  await expect(results).toContainText('The document appears to exclude you');
  // WP-141: the rule of the action is the row "Who may apply", in a sentence (it read "Rule of the programme or the action: Not allowed. contracting ...")
  await expect(results).toContainText('Who may apply: Not allowed. Only contracting authorities, international organisations, SEAPs and the EDA may apply to this call.');
  await expect(results).not.toContainText(/Not allowed\. [a-z]/);
  await expect(results).not.toContainText('none is a no');
  // another case: the visitor changes an answer, and the document alone speaks again
  await page.getByRole('form', { name: 'Check your company against this call' }).getByLabel('What kind of organisation?').selectOption('large');
  await expect(results).not.toContainText('Rule of the programme or the action');
  await expect(results).not.toContainText('Only contracting authorities');
});

test('a failed look-up of the call\'s rules is not "Rules not read"', async ({ page }) => {
  await quiet(page, () => ({ status: 429, body: { detail: 'Too many requests' } }));
  await save(page);
  await visit(page, CALL, { title: /DefenceGate/, h1: /additive manufacturing/i });
  const verdict = page.locator('[data-apply-summary] [data-profile-verdict]');
  await expect(verdict).toHaveAttribute('data-profile-verdict', 'failed');
  await expect(verdict).toContainText('could not be compared with this call just now');
  await expect(page.locator('[data-apply-summary]')).not.toContainText('Nothing we hold says who may apply');
});
