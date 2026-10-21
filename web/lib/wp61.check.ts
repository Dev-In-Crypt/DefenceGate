/**
 * Self-check of WP-61: the supplier map says that Spain's national portal is included only when the API lists it as a source, and
 * credits it as its publisher's terms ask (the source and the date of last update). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { coverageText, placspCredit, placspNote, sourceLabel } from './supplier-sources';
import { supplierSummary } from './mock/suppliers';

const ted = { code: 'ted', name: 'TED (Tenders Electronic Daily)', attribution: 'Source: TED (Tenders Electronic Daily), © European Union.' };
const es = { code: 'es_placsp', name: 'PLACSP', attribution: 'Origen de los datos: Ministerio de Hacienda (Plataforma de Contratación del Sector Público).',
  lastUpdated: '2026-10-20T08:00:00Z' };

// Off (the default, and the demo data): TED only, and not a word about PLACSP.
assert.equal(placspNote(undefined), null);
assert.equal(placspNote([ted]), null);
assert.equal(placspNote(supplierSummary().sources), null);
assert.ok(!coverageText(false).includes('PLACSP') && coverageText(false).includes('TED result notices'));
assert.equal(placspCredit(null, (d) => d), '');

// On: the coverage names Spain's national portal and says an award in both is counted once.
assert.equal(placspNote([ted, es]), es);
assert.ok(coverageText(true).includes("Spain's national procurement portal (PLACSP"));
assert.ok(coverageText(true).includes('counted once'));
assert.equal(placspCredit(es, (d) => d.slice(0, 10)),
  'Origen de los datos: Ministerio de Hacienda (Plataforma de Contratación del Sector Público), last updated 2026-10-20.');
assert.equal(placspCredit({ ...es, lastUpdated: null }, (d) => d), 'Origen de los datos: Ministerio de Hacienda (Plataforma de Contratación del Sector Público).');

// The source of one notice; an older API sends none, which is TED.
assert.equal(sourceLabel('es_placsp'), 'PLACSP');
assert.equal(sourceLabel('es_placsp_agg'), 'PLACSP');
assert.equal(sourceLabel('ted'), 'TED');
assert.equal(sourceLabel(undefined), 'TED');

console.log('wp61 checks passed');
