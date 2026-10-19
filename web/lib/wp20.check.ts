/**
 * Self-check of the WP-20 helpers (UX walk-throughs of 16 October 2026): the buyer's local time, the CPV a filter
 * matched through, the value note, the portals named from the source list, the last good answer, the market selectors
 * and the new default scope. Not part of the app and not imported by it.
 * Run from web/:  npx tsc lib/wp20.check.ts --outDir /tmp/dgchk --module commonjs --target es2022 --skipLibCheck --esModuleInterop --resolveJsonModule && node /tmp/dgchk/wp20.check.js
 */
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { localDeadline } from './deadline';
import { matchedCpv } from './tender-basis';
import { sourcePage, staleNote, valueMissingNote, valueMissingNotes } from './source-status';
import { listWords, nationalCountries, portalWords } from './coverage-copy';
import { DEFAULT_TENDER_SCOPE, parseChangeFilters, parseMarketFilters, parseTenderFilters, toChangeQuery, toTenderQuery } from './filters';
import { MAX_STALE_MS, recall, remember, resetLastGood } from './last-good';

// The deadline in the buyer's own time zone: summer and winter time, another day, a date only, an unknown country.
assert.equal(localDeadline('2026-10-16T08:00:00Z', 'PL'), '10:00 CEST (Warsaw)');
assert.equal(localDeadline('2026-11-26T09:00:00Z', 'PL'), '10:00 CET (Warsaw)');
assert.equal(localDeadline('2026-11-26T23:30:00Z', 'PL'), '00:30 CET on 27 Nov (Warsaw)');
assert.equal(localDeadline('2026-11-26T09:00:00Z', 'GB'), null, 'London reads the same as UTC in winter');
assert.equal(localDeadline('2026-07-01T09:00:00Z', 'GB'), '10:00 BST (London)');
assert.equal(localDeadline('2026-10-16T00:00:00Z', 'PL'), null, 'a date only has no time to convert');
assert.equal(localDeadline('2026-10-16T08:00:00Z', 'PL', true), null);
assert.equal(localDeadline('2026-10-16T08:00:00Z', 'ZZ'), null);
assert.equal(localDeadline(null, 'PL'), null);

// The code a CPV filter matched through, when it is not the main one.
const t = { cpv: '42962000', cpvCodes: ['42962000', '34711200', '34100000', '15000000'] };
assert.deepEqual(matchedCpv(t, ['34']), ['34711200', '34100000']);
assert.deepEqual(matchedCpv(t, ['42']), [], 'the main code matches: nothing to explain');
assert.deepEqual(matchedCpv(t, undefined), []);
assert.deepEqual(matchedCpv(t, []), []);
assert.deepEqual(matchedCpv(t, ['99']), []);

// Why a value is missing: a share of the source's notices, only with enough notices to say so; and a source whose
// connector reads no value at all (WP-49) says "not collected", never "not stated by the buyer".
const notes = valueMissingNotes([
  { id: 'ted', heldCount: 1000, valueStatedCount: 150, valueRead: true },
  { id: 'tiny', heldCount: 10, valueStatedCount: 1 },
  { id: 'old_api', heldCount: 500 },
  { id: 'pl_ezam', heldCount: 52251, valueStatedCount: 0, valueRead: false },
  { id: 'nl_tenderned', heldCount: 5, valueStatedCount: 0, valueRead: false },
]);
assert.deepEqual(Object.keys(notes).sort(), ['nl_tenderned', 'pl_ezam', 'ted']);
assert.equal(valueMissingNote(notes, 'ted'), 'No usable estimated value in 85 % of notices from this source.');
assert.doesNotMatch(valueMissingNote(notes, 'ted') ?? '', /by the buyer/);
assert.match(valueMissingNote(notes, 'pl_ezam') ?? '', /^Not collected from this source/);
assert.doesNotMatch(valueMissingNote(notes, 'pl_ezam') ?? '', /\d %|buyer/, 'a source that reads no value has no share to quote');
assert.match(valueMissingNote(notes, 'nl_tenderned') ?? '', /^Not collected from this source/, 'whatever the count');
assert.equal(valueMissingNote(notes, 'tiny'), null);
assert.equal(valueMissingNote(notes, 'old_api'), null);
assert.equal(valueMissingNote(notes, null), null);
assert.equal(staleNote(undefined, String), null);
assert.match(staleNote('2026-10-16T10:00:00Z', (s) => `<${s}>`) ?? '', /last answer, as of <2026-10-16T10:00:00Z>/);

// The national portals are named from the source list: Germany is among them since 16 October 2026; TED and the one-off
// dataset are not; Spain's two sources are one country.
const sources = [
  { id: 'ted', type: 'tenders', country: null }, { id: 'es_placsp', type: 'tenders', country: 'ES' },
  { id: 'es_placsp_agg', type: 'tenders', country: 'ES' }, { id: 'fr_boamp', type: 'tenders', country: 'FR' },
  { id: 'nl_tenderned', type: 'tenders', country: 'NL' }, { id: 'pl_ezam', type: 'tenders', country: 'PL' },
  { id: 'pl_atlas', type: 'tenders', country: 'PL' }, { id: 'de_bkms', type: 'tenders', country: 'DE' },
  { id: 'se_vinnova', type: 'grants', country: 'SE' },
];
assert.deepEqual(nationalCountries(sources), ['FR', 'DE', 'NL', 'PL', 'ES']);
assert.deepEqual(portalWords(sources), { count: 'five', names: 'France, Germany, the Netherlands, Poland and Spain' });
assert.equal(portalWords([]).count, 'no');
assert.equal(listWords(['A']), 'A');

// The page a person reads for a source, not its API root.
assert.equal(sourcePage('pl_ezam', 'https://ezamowienia.gov.pl/mo-board/api/v1'), 'https://ezamowienia.gov.pl/');
assert.equal(sourcePage('es_bdns', 'https://www.infosubvenciones.es/bdnstrans/GE/es'), 'https://www.infosubvenciones.es/bdnstrans/GE/es');
assert.equal(sourcePage('nowhere', null), null);

// The default scope is the two together, left out of URLs; an explicit scope keeps its meaning.
assert.equal(DEFAULT_TENDER_SCOPE, 'relevant');
assert.equal(parseTenderFilters({}).scope, 'relevant');
assert.equal(parseTenderFilters({ scope: 'core' }).scope, 'core');
assert.equal(parseTenderFilters({ scope: 'nonsense' }).scope, 'relevant');
assert.equal(toTenderQuery(parseTenderFilters({})), '');
assert.equal(toTenderQuery(parseTenderFilters({ scope: 'core' })), '?scope=core');
assert.equal(toTenderQuery(parseTenderFilters({ scope: 'relevant' })), '');
assert.equal(parseChangeFilters({ scope: 'relevant' }).scope, undefined);
assert.equal(toChangeQuery(parseChangeFilters({ scope: 'supply' })), '?scope=supply');

// The market selectors: a year in range and one known country; anything else is dropped.
assert.deepEqual(parseMarketFilters({ year: '2025', country: 'pl' }, 2026), { year: 2025, country: 'PL' });
assert.deepEqual(parseMarketFilters({ year: '2027' }, 2026), {});
assert.deepEqual(parseMarketFilters({ year: '1999', country: 'ZZ' }, 2026), {});
assert.deepEqual(parseMarketFilters({}, 2026), {});

// The last good answer: kept in memory and on disk, offered with its time, not offered when it is too old.
void (async () => {
  process.env.DG_LAST_GOOD_DIR = mkdtempSync(join(tmpdir(), 'dg-last-good-'));
  const at = new Date('2026-10-16T10:00:00Z');
  assert.equal(await recall('k'), null);
  await remember('k', { total: 3 }, { persist: true, at });
  assert.deepEqual(await recall('k', at.getTime() + 60_000), { value: { total: 3 }, at: at.toISOString() });
  resetLastGood();                                                           // a restart: the file still serves
  assert.deepEqual((await recall<{ total: number }>('k', at.getTime() + 60_000))?.value, { total: 3 });
  resetLastGood();
  assert.equal(await recall('k', at.getTime() + MAX_STALE_MS + 1), null, 'too old to offer');
  await remember('m', { n: 1 }, { at });                                     // memory only
  resetLastGood();
  assert.equal(await recall('m', at.getTime()), null);
  console.log('wp20 checks passed');
})();
