/**
 * Self-check of WP-57 (suppliers and organisations, UX audit 19 October 2026): the country as a visitor types it, the product words that
 * must not match pieces of words, and the case of organisation names. Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { countryToIso2, parseCountries } from './country-input';
import { cpvForWords, isForm, PRODUCT_KEYWORDS } from './cpv';
import { displayName } from './display-name';
import cpvData from './data/cpv.json';
import sample from './fixtures/org-names-sample.json';

// ---- M6: a country is a code, a three-letter code or an English name ----
for (const [given, code] of [
  ['DE', 'DE'], ['de', 'DE'], ['DEU', 'DE'], ['deu', 'DE'], ['Germany', 'DE'], ['germany', 'DE'], [' GERMANY ', 'DE'], ['Deutschland', 'DE'],
  ['GBR', 'GB'], ['UK', 'GB'], ['United Kingdom', 'GB'], ['Great Britain', 'GB'], ['Czech Republic', 'CZ'], ['Czechia', 'CZ'], ['CZE', 'CZ'],
  ['Türkiye', 'TR'], ['Turkey', 'TR'], ['Netherlands', 'NL'], ['The Netherlands', 'NL'], ['Poland', 'PL'], ['POL', 'PL'], ['Ukraine', 'UA'],
  ['United States', 'US'], ['USA', 'US'], ['Bosnia and Herzegovina', 'BA'], ['Bosnia & Herzegovina', 'BA'], ['North Macedonia', 'MK'],
  ['Côte d’Ivoire', 'CI'], ['XKX', 'XK'], ['ZZ', 'ZZ'],
] as const) assert.equal(countryToIso2(given), code, given);
for (const given of ['', ' ', 'Atlantis', 'Germ', 'DEUT', 'XYZ', 'G', '1', 'DE;DROP']) assert.equal(countryToIso2(given), null, JSON.stringify(given));
assert.deepEqual(parseCountries('Germany, DEU,fr'), { codes: ['DE', 'FR'], unknown: [] }, 'a list: normalised, no repeats');
assert.deepEqual(parseCountries('DE, Atlantis'), { codes: ['DE'], unknown: ['Atlantis'] }, 'an unknown part is reported, not dropped silently');
assert.deepEqual(parseCountries(''), { codes: [], unknown: [] });

// ---- M7: a product word is a word of a CPV title, not a piece of one ----
assert.ok(isForm('guns', 'gun') && isForm('armoured', 'armour') && isForm('batteries', 'battery') && isForm('missiles', 'missile'));
assert.ok(!isForm('gunmetal', 'gun') && !isForm('fuelled', 'fuel') && !isForm('bomber', 'bomb') && !isForm('determine', 'mine'));
const gun = cpvForWords('gun');
assert.ok(gun.codes.length > 0 && gun.codes.every((c) => /\bguns?\b/i.test(c.title)), 'gun: only guns');
assert.ok(!gun.codes.some((c) => /gunmetal/i.test(c.title)) && !gun.prefixes.some((p) => '35341100'.startsWith(p)), 'gun is not gunmetal pipe fittings (35341100)');
const fuel = cpvForWords('fuel');
assert.ok(!fuel.prefixes.some((p) => '35512100'.startsWith(p) || '35512200'.startsWith(p) || '35512300'.startsWith(p)), 'fuel is not "nuclear fuelled" submarines');
assert.ok(fuel.codes.every((c) => /\bfuel\b/i.test(c.title)));
assert.deepEqual(cpvForWords('bomb').prefixes, ['353331'], 'bomb: Bombs, not bombers');
assert.deepEqual(cpvForWords('pistol').prefixes, ['353211'], 'a pistol is a hand gun');
assert.deepEqual(cpvForWords('Handguns').prefixes, ['353211']);
assert.deepEqual(cpvForWords('radar').prefixes, ['35722', '35723'], 'radar: not radar detectors (35121900)');
assert.deepEqual(cpvForWords('helmet').prefixes, ['35813'], 'a helmet is a military helmet, not a helmet cover only');
assert.deepEqual(cpvForWords('Drohnen').prefixes, cpvForWords('drone').prefixes, 'the German word');
const armour = cpvForWords('armour');
assert.deepEqual(armour.prefixes, ['3541', '35815']);
assert.deepEqual(cpvForWords('armor').prefixes, armour.prefixes, 'the American spelling');
assert.deepEqual(cpvForWords('body armour').prefixes, ['35815'], 'the longer phrase wins over "armour"');
assert.deepEqual(cpvForWords('armoured vehicles').prefixes, ['3541'], 'and over "armoured"');
assert.deepEqual(cpvForWords('land mines').prefixes, ['353314'], 'land mines are not sea mines or ships');
assert.deepEqual(cpvForWords('sea mine').prefixes, ['353322']);
assert.deepEqual(cpvForWords('mine').prefixes, ['35513', '353314', '353322'], 'a mine alone: both weapons and the mine-warfare ships');
assert.match(cpvForWords('mine').note ?? '', /CPV box/);
assert.equal(cpvForWords('tank').prefixes.join(), '35411', 'the nine earlier entries still read as before');

// Thirty-odd defence words, each against the whole vocabulary: no code is offered for a word it only contains a piece of.
const WORDS = [
  'ammunition', 'armour', 'armor', 'radar', 'uniform', 'uniforms', 'vehicle', 'vehicles', 'boat', 'boats', 'drone', 'helicopter', 'helicopters',
  'explosive', 'explosives', 'missile', 'missiles', 'rifle', 'rifles', 'tank', 'tanks', 'gun', 'guns', 'fuel', 'truck', 'boots', 'rocket', 'rockets',
  'bomb', 'bombs', 'ship', 'ships', 'submarine', 'aircraft', 'weapon', 'weapons', 'pistol', 'grenade', 'mine', 'torpedo', 'sonar', 'parachute',
  'helmet', 'camouflage', 'simulator', 'warship', 'frigate', 'patrol', 'ballistic', 'artillery', 'mortar', 'firearm', 'firearms', 'shotgun',
  'sniper', 'tent', 'jet', 'night', 'cannon', 'carrier', 'jacket', 'engine', 'part', 'air',
];
assert.ok(WORDS.length >= 40);
const CODES = cpvData.codes as Record<string, string>;
const lettersOf = (s: string) => s.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
let leaks = 0;
for (const w of WORDS) {
  const found = cpvForWords(w);
  const leaky = Object.entries(CODES).filter(([, t]) => t.toLowerCase().includes(w) && !lettersOf(t).some((x) => isForm(x, w)));
  leaks += leaky.length;
  if (found.via === 'title') {
    for (const c of found.codes) assert.ok(lettersOf(c.title).some((x) => isForm(x, w)), `${w}: ${c.code} ${c.title} holds the word only as a piece`);
    for (const [code, title] of leaky) assert.ok(!found.prefixes.some((p) => code.startsWith(p)), `${w}: leaks ${code} ${title}`);
  } else {
    // a curated entry: its codes are those the entry names, whatever the finder's titles say
    assert.ok(found.codes.every((c) => PRODUCT_KEYWORDS.some((e) => e.codes.some((k) => k.code === c.code))), `${w}: curated codes only`);
  }
}
assert.ok(leaks >= 2, 'the vocabulary does hold pieces-of-words (gunmetal, fuelled): the loop above had something to refuse');
for (const w of ['truck', 'boots', 'sonar', 'parachute', 'shotgun', 'sniper', 'tent', 'jet']) {
  assert.deepEqual(cpvForWords(w).prefixes, [], `${w}: no code of the finder names it, so no filter is made up`);
}
// Every curated word still lands on codes the finder holds with the same title, and no phrase is listed twice.
PRODUCT_KEYWORDS.forEach((e) => e.codes.forEach((c) => { if (CODES[c.code]) assert.equal(CODES[c.code], c.title, c.code); }));
assert.ok(PRODUCT_KEYWORDS.length >= 9 && PRODUCT_KEYWORDS.length <= 30);

// ---- M8: the case of organisation names ----
const N = (s: string) => displayName(s, 'title');
for (const [given, shown] of [
  // the audit's examples: capitals of the source, acronyms and legal forms
  ['CENTRE NATIONAL DE LA RECHERCHE SCIENTIFIQUE CNRS', 'Centre National de la Recherche Scientifique CNRS'],
  ['NEDERLANDSE ORGANISATIE VOOR TOEGEPAST NATUURWETENSCHAPPELIJK ONDERZOEK TNO', 'Nederlandse Organisatie voor Toegepast Natuurwetenschappelijk Onderzoek TNO'],
  ['TEKNOLOGIAN TUTKIMUSKESKUS VTT OY', 'Teknologian Tutkimuskeskus VTT OY'],
  ['THALES SIX GTS FRANCE SAS', 'Thales Six GTS France SAS'],
  ['NAMMO RAUFOSS AS', 'Nammo Raufoss AS'],
  ['ELECTRICITE DE FRANCE EDF SA', 'Electricite de France EDF SA'],
  ['FRAUNHOFER GESELLSCHAFT ZUR FORDERUNG DER ANGEWANDTEN FORSCHUNG EV', 'Fraunhofer Gesellschaft zur Forderung der Angewandten Forschung e.V.'],
  ['EQQUS LTD OU', 'Eqqus Ltd OÜ'],
  ['HELLON OY', 'Hellon OY'],
  ['BAUGRUND DRESDEN INGENIEURGESELLSCHAFT MBH', 'Baugrund Dresden Ingenieurgesellschaft mbH'],
  ['AIRBUS DEFENCE AND SPACE GMBH', 'Airbus Defence and Space GmbH'],
  ['LEONARDO SPA', 'Leonardo SpA'],
  ['TERN SYSTEMS EHF', 'Tern Systems ehf'],
  ['EYE-D INNOVATION APS', 'Eye-D Innovation ApS'],
  ['V-CHILLER KFT', 'V-Chiller Kft'],
  // the same names when the source already cased them as words
  ['Thales Six Gts France Sas', 'Thales Six GTS France SAS'],
  ['Nammo Raufoss As', 'Nammo Raufoss AS'],
  ['Centre National de la Recherche Scientifique Cnrs', 'Centre National de la Recherche Scientifique CNRS'],
  ['Ait Austrian Institute of Technology Gmbh', 'AIT Austrian Institute of Technology GmbH'],
  ['Hensoldt Sensors Gmbh', 'Hensoldt Sensors GmbH'],
  // all lower case: cased as a name; acronyms and small words as in the audit
  ['inria', 'INRIA'],
  ['ministere des armees', 'Ministere des Armees'],
  ['aalborg university', 'Aalborg University'],
  ['vtt technical research centre of finland', 'VTT Technical Research Centre of Finland'],
  ['fraunhofer gesellschaft e v', 'Fraunhofer Gesellschaft e.V.'],
  ['deutsches zentrum fur luft- und raumfahrt dlr - oberpfaffenhofen', 'Deutsches Zentrum fur Luft- und Raumfahrt DLR - Oberpfaffenhofen'],
  ['sveuciliste u zagrebu fakultet elektrotehnike i racunarstva', 'Sveuciliste u Zagrebu Fakultet Elektrotehnike i Racunarstva'],
  ['estado-maior do exercito', 'Estado-Maior do Exercito'],
  ['technische universitat munchen', 'Technische Universitat Munchen'],
  ['straße und weg', 'Straße und Weg'],
  // left as they are: already right, mixed case of their own, other scripts, words that look like legal forms
  ['Baltico GmbH', 'Baltico GmbH'],
  ['MEYER WERFT GmbH', 'MEYER WERFT GmbH'],
  ['iXblue', 'iXblue'],
  ['Rovsing A/S', 'Rovsing A/S'],
  ['Nokia R&D (UK) Limited', 'Nokia R&D (UK) Limited'],
  ['河南科隆集团有限公司', '河南科隆集团有限公司'],
  ['türkiye kızılay derneği', 'türkiye kızılay derneği'],      // a letter that would change ("ı") leaves the name as it is
  ['київ інститут матеріалів', 'Київ Інститут Матеріалів'],
  ['As Good As Gold Ltd', 'As Good As Gold Ltd'],
  ['MINISTRSTVO ZA OBRAMBO', 'Ministrstvo za Obrambo'],
  ['Hensoldt Sensors GmbH', 'Hensoldt Sensors GmbH'],
  ['TED', 'TED'],
] as const) assert.equal(N(given), shown, given);
assert.equal(displayName('MINISTRSTVO ZA OBRAMBO'), 'Ministrstvo za obrambo', 'a title (sentence case) is read as before');
assert.equal(displayName('SUPPLY AS REQUIRED AND SA'), 'Supply as required and SA', 'the final-word legal forms are for names, not for titles');
assert.equal(N(''), '');

// The 200+ names the directory served on 19 October 2026 (fixtures/org-names-sample.json): the letters never change, only their case; a second
// pass changes nothing; a legal form at the end is never left in the wrong case; no name starts in lower case.
const letters = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').replace(/[^\p{L}\p{N}]/gu, '').toLowerCase();
assert.ok(sample.names.length >= 200, 'at least 200 names');
let changed = 0;
for (const name of sample.names) {
  const shown = N(name);
  assert.equal(letters(shown), letters(name), `letters changed: ${name} -> ${shown}`);
  if (shown !== shown.toUpperCase()) assert.equal(N(shown), shown, `not idempotent: ${name} -> ${shown} -> ${N(shown)}`);   // an all-capitals result ("NHP SRL") is read as shouting again, as it always was
  assert.ok(!/ (Sas|As|Gmbh|Srl|Ou|Ev|Bv|Nv|Sarl|Sro|Aps|Mbh)$/.test(shown), `wrong-case ending: ${shown}`);
  if (shown !== name) changed += 1;
}
assert.ok(changed > 100, `most of the sample was in capitals or lower case, so most of it changes (${changed})`);
const lower = sample.names.filter((n) => /\p{Ll}/u.test(n) && !/\p{Lu}/u.test(n));
assert.ok(lower.length >= 20, 'the sample holds all-lower-case names');
for (const n of lower) assert.ok(/^\p{Lu}/u.test(N(n)) || !/^\p{L}/u.test(n), `lower-case name left lower: ${n}`);
console.log('wp57.check ok');
