/**
 * Self-check of WP-80 ("who to approach" leads the supplier report): the words of the value and of the winners not named; the demo answer
 * (lib/mock/demand.json, the API's answer on production data) keeps the mosaic rule across countries; and every guide, grant and amount of
 * lib/es-support.ts is in the research file it comes from (docs/research/ANGLE1_SPAIN_LANDSCAPE_2026-10-22.md, in the main checkout's docs:
 * its URLs and figures are copied here as RESEARCH, so that a changed link or an invented amount fails).
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { approachOthersLine, primesOf, valueLine, type Approach, type Demand } from './demand';
import { CHECK_THE_CALL, COURSES, GRANTS, GUIDES, grantsFor, guidesFor } from './es-support';
import mock from './mock/demand.json';

// ---------------------------------------------------------------- words
assert.equal(valueLine({ values: [], contracts: 4 }), null);
assert.equal(valueLine({ values: [{ currency: 'EUR', amount: 1425000, contracts: 1 }], contracts: 9 }), 'EUR 1,425,000 stated for 1 of 9 contracts');
assert.equal(valueLine({ values: [{ currency: 'PLN', amount: 3846310.14, contracts: 3 }, { currency: 'EUR', amount: 10, contracts: 1 }], contracts: 4 }),
  'PLN 3,846,310 stated for 3 of 4 contracts; EUR 10 stated for 1 of 4 contracts');
const none: Approach = { winners: [], below: { winners: 0, awards: 0 }, more: { winners: 0, awards: 0 } };
assert.equal(approachOthersLine(none, 3), null);
assert.equal(approachOthersLine({ ...none, below: { winners: 1, awards: 2 } }, 3), '1 other winner with fewer than 3 awards each (2 awards together) is counted, not named.');
assert.match(approachOthersLine({ ...none, more: { winners: 92, awards: 409 } }, 3) ?? '', /^92 more winners with 3 or more awards \(409 awards\) are not listed: the list stops at 30/);

// ---------------------------------------------------------------- the demo answer
const demo: Demand = mock;
const a = demo.approach;
assert.ok(a.winners.length > 0, 'the demo names winners');
assert.ok(a.winners.every((w) => w.contracts >= demo.kMin), 'a winner below kMin is named');
assert.ok(a.winners.length + a.below.winners + a.more.winners <= demo.total.winners, 'named and counted winners exceed the winners');
assert.ok(a.winners.slice(0, 30).every((w, i, xs) => i === 0 || xs[i - 1].contracts >= w.contracts), 'most contracts first');
assert.ok(a.winners.slice(30).every((w) => w.prime), 'past the 30th only primes');
assert.ok(primesOf(a).length > 0, 'the demo marks a prime (Indra, Saab on 22 October 2026)');
for (const w of a.winners) {
  assert.ok(w.buyers.length <= 3 && w.buyers.every((b) => b.name && b.contracts >= 1), w.name);
  assert.ok(w.values.every((v) => v.contracts <= w.contracts), `${w.name}: more valued contracts than contracts`);
  assert.ok(w.countries.length >= 1 && w.countries.every((c) => demo.countries.includes(c)), w.name);
  if (w.prime) assert.match(w.prime.sourceUrl, /^https:\/\//);
}

// ---------------------------------------------------------------- guides and grants, against the research file
const RESEARCH = {
  urls: [
    'https://caetraprogramme.institutofomentomurcia.es/wp-content/uploads/2024/11/1_Guia_CAETRA_RegistroDGAM.pdf',
    'https://caetraprogramme.institutofomentomurcia.es/wp-content/uploads/2026/06/3_Guia_CAETRA_PECAL_AQAP.pdf',
    'https://sede.institutofomentomurcia.es/infodirecto/servlet/DownloadFile?id=2208091',
    'https://www.iustel.com/diario_del_derecho/noticia.asp?ref_iustel=1269075',
    'https://proxconsultores.com/subvencion/in519g-ayudas-empresas-gallegas-suministradoras-materia-seguridad-defensa',
    'https://www.extremaduraempresarial.es/2026/06/04/ayudas-para-empresas-que-soliciten-las-certificaciones-de-la-otan-para-suministrar-a-la-industria-militar/',
    'https://es.ara.cat/economia/industria/gobierno-impulsa-plan-introducir-400-empresas-sector-defensa_1_5703773.html',
  ],
  // every figure the research states for these programmes (section 2, "Regional")
  amounts: ['EUR 2,500', 'EUR 9,000', 'EUR 4,000', 'EUR 10,000', 'EUR 5,000 to 30,000', '70 %', '50 %', 'EUR 75,000', '80 %', 'EUR 11,000'],
};
const used = [...Object.values(GUIDES).flat().map((g) => g.url), ...GRANTS.map((g) => g.url), ...COURSES.map((c) => c.url)];
for (const u of used) assert.ok(RESEARCH.urls.includes(u), `not a source of the research: ${u}`);
for (const g of GRANTS) {
  const figures = (g.amounts ?? '').match(/EUR [\d,]+( to [\d,]+)?|\d+ %/g) ?? [];
  for (const f of figures) assert.ok(RESEARCH.amounts.includes(f), `${g.programme}: ${f} is not a figure of the research`);
  assert.match(g.read, /20(25|26)/, `${g.programme}: says which call or list it read`);
}
assert.match(CHECK_THE_CALL, /^Check the current call/);
assert.equal(guidesFor('REQ-RID')[0].date, 'November 2024');
assert.equal(guidesFor('REQ-PECAL')[0].date, 'June 2026');
assert.deepEqual(guidesFor('REQ-NCAGE'), []);
assert.deepEqual(grantsFor('REQ-RID', 'ES-GA').map((g) => g.region), ['ES-GA', 'ES-MC', 'ES-AR'], 'own region first');
assert.deepEqual(grantsFor('REQ-PECAL').map((g) => g.region), ['ES-MC', 'ES-AR', 'ES-GA', 'ES-EX']);
assert.deepEqual(grantsFor('REQ-HSES-ES').map((g) => g.region), ['ES-MC', 'ES-AR', 'ES-GA']);
assert.deepEqual(grantsFor('REQ-NCAGE'), [], 'no grant the research does not list');
assert.deepEqual(grantsFor(null), []);
console.log('wp80 ok');
