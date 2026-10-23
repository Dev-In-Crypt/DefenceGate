// node shots.cjs <base-url> <outdir> <prefix> : first screen of the WP-88 pages, desktop 1280 and phone 375
const path = require('path');
const { chromium } = require('D:/DEFENCEGATE TESTS/wp88/repo/web/node_modules/playwright');
const [base, out, prefix] = process.argv.slice(2);
const pages = ['/suppliers', '/organisations/101-alpha-systems-gmbh', '/suppliers/1-demo-airframes-gmbh', '/readiness', '/readiness/supplier',
  '/networks/consortium-gaps?topic=CYBER&lacking=UA', '/networks/ukraine-partners', '/market', '/requirements', '/regulation', '/funding'];
(async () => {
  const b = await chromium.launch();
  for (const [name, vp] of [['desk', { width: 1280, height: 800 }], ['phone', { width: 375, height: 812 }]]) {
    const ctx = await b.newContext({ viewport: vp, isMobile: name === 'phone', hasTouch: name === 'phone' });
    const p = await ctx.newPage();
    for (const u of pages) {
      await p.goto(base + u, { waitUntil: 'networkidle', timeout: 120000 });
      const f = `${prefix}-${name}-${u.replace(/\?.*$/, '').replace(/[/]+/g, '_').replace(/^_/, '').replace(/-[a-z0-9-]*gmbh$/, '')}`;
      await p.screenshot({ path: path.join(out, f + '.png') });
    }
    await ctx.close();
  }
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
