// node shots.cjs <port> <prefix> <outdir> : the WP-89 before/after pictures and the PDF page count, on a mock build (DG_USE_MOCK=1).
const path = require('path');
const fs = require('fs');
const { chromium } = require(path.join(process.cwd(), 'node_modules', '@playwright/test'));
const [port, prefix, out] = process.argv.slice(2);
const base = `http://127.0.0.1:${port}`;
const fixtures = 'D:\\DEFENCEGATE TESTS\\wp89\\repo\\web\\e2e\\fixtures';
const fx = (n) => JSON.parse(fs.readFileSync(path.join(fixtures, n), 'utf8'));
const MARTA = {
  version: 3, step: 1, updatedAt: '2026-10-22T19:00:31.202Z', name: '', sizeClass: 'medium', country: 'ES', legalForm: '', applicantKind: '',
  management: '', managementCountry: '', control: 'no', uaOccupied: '', uaPartner: '', seapPartner: '', regime: '', componentPct: '',
  restricted: '', uaEeaComponents: '', safeRole: '',
  statuses: { 'REQ-ISO9001': 'held', 'REQ-EN9100': 'not_held', 'REQ-AQAP2110': 'not_held', 'REQ-AQAP2310': 'not_held', 'REQ-PECAL': 'not_held', 'REQ-RID': 'not_held', 'REQ-NCAGE': 'not_held' },
  classified: 'unsure', exportIntent: 'within_eu',
  supplier: { region: 'ES-VC', foreignOwner: 'no', foreignCountry: '', nace: '', cpv: ['34300000', '34320000', '34330000', '35420000', '44470000', '34322000', '44500000'],
    processes: ['machining', 'casting'], held: ['IATF16949'], expiry: {}, usComponents: 'no', answers: {} },
};
fs.mkdirSync(out, { recursive: true });
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await ctx.addInitScript((v) => { window.localStorage.setItem('dg.profile.v1', JSON.stringify(v)); }, MARTA);
  await ctx.route('**/api/readiness/assess', async (route) => {
    const body = route.request().postDataJSON();
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fx(body.programmes ? 'assess-es-sup-civil-routes.json' : 'assess-es-sup-civil.json')) });
  });
  const page = await ctx.newPage();
  const go = async (p, wait) => { await page.goto(base + p, { waitUntil: 'load' }); if (wait) await page.locator(wait).first().waitFor({ timeout: 20000 }); await page.waitForTimeout(400); };

  await go('/readiness/results', '[data-approach-winner]');
  await page.locator('[data-approach-summary-section]').screenshot({ path: path.join(out, `${prefix}-results-who-to-approach.png`) });
  await page.screenshot({ path: path.join(out, `${prefix}-results-fold.png`) });
  await page.locator('[data-programme]').first().waitFor();
  const prog = page.locator('#programmes').locator('xpath=..');
  await prog.screenshot({ path: path.join(out, `${prefix}-results-programmes.png`) });

  await go('/readiness/supplier', '#sp-cpv-search');
  await page.fill('#sp-cpv-search', 'castings');
  await page.waitForTimeout(1500);
  await page.locator('#q-cpv').screenshot({ path: path.join(out, `${prefix}-cpv-castings.png`) });

  await go('/buyers?cpv=343', 'h1');
  await page.screenshot({ path: path.join(out, `${prefix}-buyers-cpv.png`) });
  await go('/market?cpv=343', 'h1');
  await page.screenshot({ path: path.join(out, `${prefix}-market-cpv.png`) });

  await go('/readiness/supplier/report', '[data-item]');
  await page.locator('[data-approach-winner]').first().waitFor();
  await page.screenshot({ path: path.join(out, `${prefix}-report-fold.png`) });
  await page.emulateMedia({ media: 'print' });
  await page.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(out, `${prefix}-report-print-preview.png`) });
  const pdf = await page.pdf({ format: 'A4' });
  fs.writeFileSync(path.join(out, `${prefix}-report.pdf`), pdf);
  const pages = (pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) || []).length;
  fs.writeFileSync(path.join(out, `${prefix}-report-pages.txt`), `${pages}\n`);
  console.log(prefix, 'pdf pages', pages);
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
