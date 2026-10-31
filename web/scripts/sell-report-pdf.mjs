// WP-162: print a "Who to sell to" report answer (the JSON of `python -m dgate.ops.sell_report`, the admin's one-off report) to PDF
// through the site's own page, so the PDF is the page a customer prints. Needs a production build (`npx next build`); starts the fake
// API (e2e/support/fake-api.mjs) serving the file as the sample, a `next start` that reads it, and Chromium (Playwright's).
//
//   node scripts/sell-report-pdf.mjs report.json report.pdf [more.json more.pdf ...]
//
// Local only: nothing is sent anywhere, and the ports are on 127.0.0.1.
import { spawn } from 'node:child_process';
import { rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium } from '@playwright/test';

const API = Number(process.env.SELL_REPORT_API_PORT ?? 4962);
const SITE = Number(process.env.SELL_REPORT_SITE_PORT ?? 3962);
const pairs = process.argv.slice(2);
if (pairs.length === 0 || pairs.length % 2) {
  console.error('usage: node scripts/sell-report-pdf.mjs report.json report.pdf [...]');
  process.exit(2);
}

async function until(url) {
  for (let i = 0; i < 90; i += 1) {
    try { if ((await fetch(url)).status < 500) return; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`${url} did not answer`);
}

for (let i = 0; i < pairs.length; i += 2) {
  const [json, pdf] = [resolve(pairs[i]), resolve(pairs[i + 1])];
  // the sample page keeps the API's answer for an hour (Next's fetch cache): each file is printed from a cache of its own
  rmSync('.next/cache/fetch-cache', { recursive: true, force: true });
  const api = spawn(process.execPath, ['e2e/support/fake-api.mjs', String(API)], { env: { ...process.env, FAKE_SELL_REPORT: json }, stdio: 'ignore' });
  const site = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'start', '-p', String(SITE), '-H', '127.0.0.1'],
    { env: { ...process.env, DG_API_URL: `http://127.0.0.1:${API}` }, stdio: 'ignore' });
  try {
    await until(`http://127.0.0.1:${API}/v1/sell-report/sample`);
    await until(`http://127.0.0.1:${SITE}/`);
    const browser = await chromium.launch();
    const page = await browser.newPage({ colorScheme: 'light' });
    await page.goto(`http://127.0.0.1:${SITE}/reports/who-to-sell-to/sample`, { waitUntil: 'networkidle' });
    await page.emulateMedia({ media: 'print' });
    await page.pdf({ path: pdf, format: 'A4', printBackground: true, preferCSSPageSize: true });
    // SELL_REPORT_SHOTS=<dir>: also the screen at 1440 and 375 px, light and dark (for a review)
    if (process.env.SELL_REPORT_SHOTS) {
      for (const [w, h] of [[1440, 900], [375, 812]]) {
        for (const scheme of ['light', 'dark']) {
          const p = await browser.newPage({ colorScheme: scheme, viewport: { width: w, height: h } });
          await p.goto(`http://127.0.0.1:${SITE}/reports/who-to-sell-to/sample`, { waitUntil: 'networkidle' });
          await p.screenshot({ path: resolve(process.env.SELL_REPORT_SHOTS, `${pdf.replace(/^.*[\\/]/, '').replace(/\.pdf$/, '')}-${w}-${scheme}.png`), fullPage: w === 1440 });
          await p.close();
        }
      }
    }
    await browser.close();
    console.log(`written ${pdf}`);
  } finally {
    api.kill();
    site.kill();
  }
}
