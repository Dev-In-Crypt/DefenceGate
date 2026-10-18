/**
 * Self-check of WP-28 (17 October 2026): what the organisations directory URL asks for, the words for roles and
 * methods, the slug rule and the figures behind the funding chart. Not part of the app and not imported by it.
 * Run from web/:  npm run check
 */
import assert from 'node:assert/strict';
import {
  DEFENCE_PROGRAMMES, EDF_CATEGORY_WORDS, GAP_PROGRAMMES, activeOrgFilterCount, effectiveProgrammes, fundingGroups, isNetworkSlug, methodWord, orgApiQuery, parseOrgFilters, roleWord, toOrgQuery, yearsLabel,
} from './networks';

// ---- the URL -----------------------------------------------------------------------------------------------------------
const none = parseOrgFilters({});
assert.deepEqual(none, { q: undefined, country: [], programme: [], role: [], minProjects: undefined, sort: 'projects', page: 1, pageSize: 20 });
assert.equal(toOrgQuery(none), '');
assert.equal(activeOrgFilterCount(none), 0);

const f = parseOrgFilters({ q: '  Thales  ', country: ['de', 'fr,xx9', 'UA'], programme: 'edf,horizon', role: 'Coordinator,boss', min: '5', sort: 'name', page: '3' });
assert.deepEqual(f.country, ['DE', 'FR', 'UA'], 'a code that is not two letters is dropped, case is folded');
assert.deepEqual(f.programme, ['EDF', 'HORIZON']);
assert.deepEqual(f.role, ['coordinator'], 'an unknown role is dropped');
assert.equal(f.minProjects, 5);
assert.equal(f.q, 'Thales');
assert.equal(activeOrgFilterCount(f), 5);
assert.equal(toOrgQuery(f), '?q=Thales&country=DE%2CFR%2CUA&programme=EDF%2CHORIZON&role=coordinator&min=5&sort=name&page=3');
assert.equal(orgApiQuery(f), '?q=Thales&country=DE%2CFR%2CUA&programme=EDF%2CHORIZON&role=coordinator&sort=name&page=3&minProjects=5&pageSize=20');
assert.equal(orgApiQuery(none), '?programme=EDF%2CEDIDP%2CPADR&sort=projects&pageSize=20', 'U10: with no choice the API is asked for the defence-relevant programmes');
assert.deepEqual(effectiveProgrammes(none), DEFENCE_PROGRAMMES);
assert.equal(toOrgQuery(none), '', 'and the default stays out of the address');

// U10: "all programmes" is one visible choice, kept in the address, and the API is then asked for none.
const everything = parseOrgFilters({ programme: 'all' });
assert.equal(everything.allProgrammes, true);
assert.deepEqual(everything.programme, []);
assert.equal(toOrgQuery(everything), '?programme=all');
assert.equal(orgApiQuery(everything), '?sort=projects&pageSize=20', 'no programme filter at all');
assert.deepEqual(effectiveProgrammes(everything), []);
assert.equal(activeOrgFilterCount(everything), 1, 'a change from the default counts as a filter');
assert.equal(parseOrgFilters({ programme: 'edf,all' }).allProgrammes, true, 'all wins over a list');
assert.deepEqual(parseOrgFilters({ programme: 'h2020' }).programme, ['H2020']);
assert.deepEqual(effectiveProgrammes(parseOrgFilters({ programme: 'h2020' })), ['H2020'], 'a chosen programme replaces the default');
assert.equal('allProgrammes' in none, false, 'the key is absent unless chosen');

for (const bad of ['0', '-3', 'abc', '1', '', '1e99999']) assert.equal(parseOrgFilters({ page: bad }).page, 1, `page ${bad}`);
assert.equal(parseOrgFilters({ page: '99999' }).page, 1000);
assert.equal(parseOrgFilters({ min: '1' }).minProjects, undefined, 'a minimum of one is no filter');
assert.equal(parseOrgFilters({ sort: 'funding' }).sort, 'projects');
assert.equal(parseOrgFilters({ q: 'x'.repeat(500) }).q?.length, 100);
assert.equal(parseOrgFilters({ q: '   ' }).q, undefined);
// 20 values at most; the same value once
assert.equal(parseOrgFilters({ country: Array.from({ length: 40 }, (_, i) => String.fromCharCode(65 + (i % 26)) + 'A').join(',') }).country?.length, 20);
assert.deepEqual(parseOrgFilters({ country: 'DE,de,DE' }).country, ['DE']);

// ---- words -------------------------------------------------------------------------------------------------------------------
assert.equal(roleWord('coordinator'), 'Coordinator');
assert.equal(roleWord('third_party'), 'Third party');
assert.equal(roleWord('something_new'), 'something new');
assert.equal(methodWord('pic'), 'PIC');
assert.equal(methodWord('exact_name_ambiguous'), 'name shared with others');
assert.equal(yearsLabel(2019, 2024), '2019 to 2024');
assert.equal(yearsLabel(2024, 2024), '2024');
assert.equal(yearsLabel(null, 2023), '2023');
assert.equal(yearsLabel(null, null), 'Not stated');

// ---- slugs --------------------------------------------------------------------------------------------------------------------
for (const ok of ['12', '12-thales-sa', '999999999-x']) assert.ok(isNetworkSlug(ok), ok);
for (const bad of ['', 'thales', '12 34', '1234567890-x', '12-Thales', '12/../x', '12-' + 'a'.repeat(90), '-12']) assert.equal(isNetworkSlug(bad), false, bad);

// ---- the funding chart --------------------------------------------------------------------------------------------------------------
const rows = [
  { programme: 'EDF', year: 2024, projects: 2, euContribution: null, projectsWithoutAmount: 2 },
  { programme: 'EDF', year: 2023, projects: 1, euContribution: null, projectsWithoutAmount: 1 },
  { programme: 'H2020', year: 2019, projects: 1, euContribution: 400000, projectsWithoutAmount: 0 },
  { programme: 'H2020', year: 2021, projects: 1, euContribution: 100000, projectsWithoutAmount: 0 },
  { programme: 'H2020', year: null, projects: 1, euContribution: null, projectsWithoutAmount: 1 },
];
const groups = fundingGroups(rows);
assert.deepEqual(groups.map((g) => g.programme), ['EDF', 'H2020'], 'most projects first');
const edf = groups[0];
assert.equal(edf.measure, 'projects', 'EDF states no amount: its bars are projects');
assert.deepEqual(edf.rows.map((r) => [r.year, r.width]), [[2023, 50], [2024, 100]], 'oldest year first, widest = the programme\'s own largest');
assert.equal(edf.totalEur, null);
const h = groups[1];
assert.equal(h.measure, 'eur');
assert.deepEqual(h.rows.map((r) => [r.year, r.width]), [[2019, 100], [2021, 25], [null, 0]], 'a year that is not stated comes last, a row with no amount has no bar');
assert.equal(h.totalEur, 500000);
assert.equal(h.totalProjects, 3);
assert.deepEqual(fundingGroups([]), []);

// U11: the gap analysis explains its capability codes and offers only programmes it can run on.
assert.equal(EDF_CATEGORY_WORDS.UWW, 'Underwater warfare');
assert.ok(!('DS' in EDF_CATEGORY_WORDS), 'a code we cannot read with confidence has no words');
assert.ok(GAP_PROGRAMMES.some((p) => p.value === 'EDF') && GAP_PROGRAMMES.every((p) => /^[A-Z0-9_-]{1,20}$/.test(p.value)));

console.log('networks.check: ok');
