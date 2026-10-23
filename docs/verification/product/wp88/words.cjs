// node words.cjs <base> [out.json] : words of visible text in <main> before the first useful element (form, table, list item, dl, article)
// Not counted: breadcrumbs and other nav, the h1, text inside a closed <details> (summary line counted), visually hidden text.
// prose: visible words of paragraphs anywhere on the page outside closed details, lists, tables and forms. terms: internal terms visible.
const fs = require('fs');
const { chromium } = require('D:/DEFENCEGATE TESTS/wp88/repo/web/node_modules/playwright');
const base = process.argv[2] || 'http://127.0.0.1:3188';
const out = process.argv[3];
const pages = [
  '/suppliers', '/organisations', '/suppliers/1-demo-airframes-gmbh', '/organisations/101-alpha-systems-gmbh',
  '/funding', '/funding/1-edf-2026-additive-manufacturing-spare-parts', '/check', '/readiness', '/readiness/supplier',
  '/readiness/spain-automotive', '/readiness/results', '/readiness/roadmap', '/readiness/supplier/report', '/readiness/supplier/winners',
  '/requirements', '/regulation', '/networks/consortium-gaps', '/networks/ukraine-partners', '/market', '/methodology', '/about', '/glossary',
];
const B = String.fromCharCode(92) + 'b';
const TERMS = ['confidence [0-9]|(?:low|medium|high)(?:est)? confidence', `${B}alias${B}`, 'normalised name', 'PIC is held', `${B}Regime${B}`,
  'Financial support to third parties', 'PLACSP', 'SEDIA', 'CORDIS', 'EDIDP', 'PADR', 'LCSP', `${B}SDA${B}`, `${B}HSE[MS]${B}`, 'NSIP', 'FNLC',
  'LS-IRA', `${B}FSTP${B}`, '`', 'country of establishment'].map((s) => new RegExp(s, /^[A-Z`]/.test(s) || s.startsWith(B) && /[A-Z]/.test(s[2]) ? '' : 'i'));
const SEL = 'form, table, dl, article, li:not(nav li), [data-useful]';
(async () => {
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
  if (process.env.PROFILE) {   // the es-sup-civil supplier profile of the e2e fixtures, and its assess answer
    const fx = (n) => fs.readFileSync(`D:/DEFENCEGATE TESTS/wp88/repo/web/e2e/fixtures/${n}`, 'utf8');
    await p.addInitScript((v) => { if (!localStorage.getItem('dg.profile.v1')) localStorage.setItem('dg.profile.v1', v); }, fx('profile-es-sup-civil.json'));
    await p.route('**/api/readiness/assess', (r) => r.fulfill({ status: 200, contentType: 'application/json', body: fx('assess-es-sup-civil.json') }));
  }
  const res = {};
  for (const u of (process.env.PAGES ? process.env.PAGES.split(',') : pages)) {
    try {
      await p.goto(base + u, { waitUntil: 'networkidle', timeout: 90000 });
    } catch (e) { res[u] = { error: String(e).slice(0, 80) }; continue; }
    res[u] = await p.evaluate((SEL) => {
      const main = document.querySelector('main') || document.body;
      const useful = [...main.querySelectorAll(SEL)].find((el) => el.getClientRects().length > 0 && !el.closest('nav'));
      const w = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
      const words = []; let n;
      while ((n = w.nextNode())) {
        const el = n.parentElement;
        if (useful && (useful.contains(n) || (useful.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING))) break;
        if (el.closest('nav, h1, script, style, [aria-hidden="true"]')) continue;
        const d = el.closest('details');
        if (d && !d.open && !el.closest('summary')) continue;
        if (!el.getClientRects().length || el.closest('.sr-only')) continue;
        words.push(...n.textContent.split(/\s+/).filter((x) => /[\p{L}\p{N}]/u.test(x)));
      }
      let prose = 0;
      for (const el of main.querySelectorAll('p')) {
        if (!el.getClientRects().length || el.closest('li, table, form, nav, dl, summary')) continue;
        const dd = el.closest('details'); if (dd && !dd.open) continue;
        prose += el.innerText.split(/\s+/).filter((x) => /[\p{L}\p{N}]/u.test(x)).length;
      }
      return { words: words.length, prose, first: useful ? useful.tagName.toLowerCase() : null, text: words.join(' ').slice(0, 300) };
    }, SEL);
    // a source's own credit line ([data-attribution], kept on screen by the sources' terms) is not jargon
    const vis = await p.evaluate(() => {
      const main = document.querySelector('main') || document.body;
      let t = main.innerText;
      for (const a of main.querySelectorAll('[data-attribution]')) t = t.replace(a.innerText, '');
      return t;
    });
    res[u].terms = TERMS.map((re) => (vis.match(re) || [null])[0]).filter(Boolean);
    console.log(u.padEnd(48), String(res[u].words).padStart(4), String(res[u].prose).padStart(5), res[u].first, res[u].terms.join(' | '));
  }
  if (out) fs.writeFileSync(out, JSON.stringify(res, null, 1));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
