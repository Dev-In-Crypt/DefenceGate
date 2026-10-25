/**
 * Self-check of WP-130 (round-7 accessibility and SEO audit): tender titles say what is bought and keep the notice number, abbreviations
 * end no sentence, a name shouted in its head only, breadcrumb data without a repeated address, years inside a sentence.
 * Not part of the app. Run from web/:  node scripts/run-checks.mjs   (npm run check)
 */
import assert from 'node:assert/strict';
import { TITLE_MAX, titleWithRef, trimAtPhrase } from './seo-trim';
import { breadcrumbJsonLd, buildMetadata, crumbLinks, tenderSubject, tenderTitle } from './seo';
import { displayName } from './display-name';
import { yearsLabel, yearsPhrase } from './networks';

// 1. The subject of a TED title, without the place TED puts first.
assert.equal(tenderSubject('France-Toulon: Microwave tubes and equipment', 'FR'), 'Microwave tubes and equipment');
assert.equal(tenderSubject('Bulgaria-Sofia: Repair, maintenance and associated services related to aircraft', 'BG'), 'Repair, maintenance and associated services related to aircraft');
assert.equal(tenderSubject('United Kingdom-London: Fuel', 'GB'), 'Fuel');
assert.equal(tenderSubject('Italy – Individual and support equipment – Materiali di equipaggiamento', 'IT'), 'Individual and support equipment – Materiali di equipaggiamento');
assert.equal(tenderSubject('Polska – Pojazdy wojskowe i ich części – Dostawa zestawów obsługowych', 'PL'), 'Pojazdy wojskowe i ich części – Dostawa zestawów obsługowych');
assert.equal(tenderSubject('France-Toulon', 'FR'), '', 'only the place: no subject');
for (const own of ['Warehouse racking: supply and installation', 'Prior information: vehicle spare parts framework for 2027', 'Framework agreement – lot A – fuel', 'Anti-tank training: rounds'])
  assert.equal(tenderSubject(own, 'DE'), own, `no place prefix: ${own}`);

const ted = { noticeId: '40702-2026', country: 'FR', cpv: '32300000', buyerName: 'MINISTERE DES ARMEES' };
const titles = [
  tenderTitle({ ...ted, title: 'France-Toulon: Microwave tubes and equipment' }),
  tenderTitle({ ...ted, noticeId: '45542-2026', country: 'BG', title: 'Bulgaria-Sofia: Repair, maintenance and associated services related to aircraft' }),
  tenderTitle({ ...ted, noticeId: '144203-2026', country: 'IT', title: 'Italy – Individual and support equipment – Materiali di equipaggiamento' }),
  tenderTitle({ ...ted, noticeId: '2-2026', country: 'PL', title: 'Polska – Pojazdy wojskowe i ich części – Dostawa zestawów obsługowych' }),
  tenderTitle({ ...ted, noticeId: '40703-2026', title: 'France-Toulon: Microwave tubes and equipment' }),
];
assert.deepEqual(titles, [
  'Microwave tubes and equipment (40702-2026)',
  // a subject that does not fit with the number keeps its words; the number goes
  'Repair, maintenance and associated services…',
  'Individual and support equipment',
  'Pojazdy wojskowe i ich części',
  'Microwave tubes and equipment (40703-2026)',
]);
assert.equal(new Set(titles).size, titles.length, 'unique per notice');
for (const t of titles) {
  assert.ok(t.length <= TITLE_MAX, t);
  assert.equal(buildMetadata({ title: t, description: 'x', path: '/x' }).title, t, 'the metadata helper keeps it whole');
}
// No subject: the main product code's label, else the buyer.
assert.equal(tenderTitle({ ...ted, title: 'France-Toulon' }), 'Radio, television, communication…', 'CPV 323: its label');
assert.ok(!tenderTitle({ ...ted, title: 'France-Toulon' }).startsWith('France-Toulon'));
assert.equal(tenderTitle({ ...ted, cpv: null, title: 'France-Toulon' }), 'Ministere des Armees (40702-2026)');
// A long source key does not take the subject's room; a title that fits with its number keeps it.
assert.equal(titleWithRef('Supply of fasteners at a unit price', '2024/ETSAE0903/00001150E'), 'Supply of fasteners at a unit price');
assert.equal(titleWithRef('Laboratory consumables', '605113-2026'), 'Laboratory consumables (605113-2026)');
assert.equal(tenderTitle({ ...ted, title: 'Laboratory consumables' }, 'Evidence: '), 'Evidence: Laboratory consumables (40702-2026)');
assert.equal(tenderTitle({ ...ted, title: 'France-Toulon: Microwave tubes and equipment' }, 'Evidence: '), 'Evidence: Microwave tubes and equipment');
// the mock tender wp88 and wp90 look for: what is bought stays whole rather than make room for the number
assert.equal(titleWithRef('Framework agreement for machined aluminium housings', '561204-2026'), 'Framework agreement for machined aluminium…');

// 7. The dot of an abbreviation ends no sentence; a real sentence end still does (lib/wp59.check.ts keeps the others).
const academy = displayName('AKADEMIA MARYNARKI Wojennej im. Bohaterów Westerplatte', 'title');
assert.equal(academy, 'Akademia Marynarki Wojennej im. Bohaterów Westerplatte', 'the shouted head is cased as the rest');
assert.ok(!trimAtPhrase(academy, TITLE_MAX, 12).endsWith('im.'), trimAtPhrase(academy, TITLE_MAX, 12));
assert.equal(trimAtPhrase('Acme Ltd. makes housings for vehicles of every kind and size in Europe', 40, 12), 'Acme Ltd. makes housings for vehicles…');
assert.equal(trimAtPhrase('E-mail alerts are not open yet. What works today without an account is a feed.', 40, 12), 'E-mail alerts are not open yet.');
// a name shouted in its head only; short initialisms and a fully mixed name stay
assert.equal(displayName('NATO SUPPORT AND PROCUREMENT Agency of Luxembourg', 'title'), 'NATO Support and Procurement Agency of Luxembourg');
assert.equal(displayName('MEYER WERFT GmbH', 'title'), 'MEYER WERFT GmbH', 'a name in capitals with its legal form stays (lib/wp57.check.ts)');
assert.equal(displayName('THALES SIX Communications', 'title'), 'THALES SIX Communications', 'one mixed word after the head: left as published');
assert.equal(displayName('HENSOLDT Sensors GmbH', 'title'), 'HENSOLDT Sensors GmbH', 'one word in capitals is a brand');
assert.equal(displayName('Plataforma Femar SL', 'title'), 'Plataforma Femar SL');
assert.equal(displayName('AKADEMIA MARYNARKI Wojennej im. Bohaterów Westerplatte'), 'AKADEMIA MARYNARKI Wojennej im. Bohaterów Westerplatte', 'a title (sentence kind) is not a name');

// 7. Years in a sentence.
assert.equal(yearsPhrase(2021, 2025), 'between 2021 and 2025');
assert.equal(yearsPhrase(2024, 2024), 'in 2024');
assert.equal(yearsPhrase(null, 2023), 'in 2023');
assert.equal(yearsLabel(2021, 2025), '2021 to 2025', 'the label of a table cell is unchanged');

// 6. Breadcrumbs: a group without a page and an address the next crumb repeats are text, and not in the structured data.
const suppliers = [{ label: 'Home', href: '/' }, { label: 'Companies', href: '/suppliers' }, { label: 'Won contracts', href: '/suppliers' }];
assert.deepEqual(crumbLinks(suppliers), [true, false, true]);
const ld = (items: Parameters<typeof breadcrumbJsonLd>[0]) => breadcrumbJsonLd(items).itemListElement.map((i) => `${i.position} ${i.name} ${new URL(i.item).pathname}`);
assert.deepEqual(ld(suppliers), ['1 Home /', '2 Won contracts /suppliers']);
assert.deepEqual(ld([...suppliers, { label: 'Rafa', href: '/suppliers/1-rafa' }]), ['1 Home /', '2 Won contracts /suppliers', '3 Rafa /suppliers/1-rafa']);
assert.deepEqual(ld([{ label: 'Home', href: '/' }, { label: 'Partners' }, { label: 'Consortium gaps', href: '/networks/consortium-gaps' }]), ['1 Home /', '2 Consortium gaps /networks/consortium-gaps']);
const orgs = [{ label: 'Home', href: '/' }, { label: 'Companies', href: '/suppliers' }, { label: 'In EU-funded projects', href: '/organisations' }];
assert.deepEqual(ld(orgs), ['1 Home /', '2 Companies /suppliers', '3 In EU-funded projects /organisations'], 'distinct addresses are all kept');

console.log('wp130 checks passed');
