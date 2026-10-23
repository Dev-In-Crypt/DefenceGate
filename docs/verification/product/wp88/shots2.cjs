// node shots2.cjs <base-url> <outdir> <prefix> : first screen of WP-87's pages after the WP-88 rules, desktop 1280 and phone 375
const path = require('path');
const { chromium } = require('D:/DEFENCEGATE TESTS/wp88/repo/web/node_modules/playwright');
const [base, out, prefix] = process.argv.slice(2);
const pages = ['/tenders', '/tenders/1-framework-agreement-machined-aluminium-housings', '/buyers/1-demo-armaments-agency', '/data', '/changes', '/calendar'];
(async () => {
  const b = await chromium.launch();
  for (const [name, vp] of [['desk', { width: 1280, height: 800 }], ['phone', { width: 375, height: 812 }]]) {
    const ctx = await b.newContext({ viewport: vp, isMobile: name === 'phone', hasTouch: name === 'phone' });
    const p = await ctx.newPage();
    for (const u of pages) {
      await p.goto(base + u, { waitUntil: 'networkidle', timeout: 180000 });
      const f = `${prefix}-${name}-${u.replace(/^\//, '').replace(/\//g, '_').replace(/^(tenders|buyers)_(\d+)-.*$/, '$1_$2')}`;
      await p.screenshot({ path: path.join(out, f + '.png') });
    }
    await ctx.close();
  }
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
