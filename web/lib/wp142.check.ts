/**
 * WP-142, item 3 (and 2, at the end): /methodology and /about give the archive's figures as privacy 1.7 does (docs/DATA_PROTECTION.md, re-count of
 * WP-140 on 25 October 2026): up to about 12,600 TED records in the raw store, about 960 buyer names with about 1,130 spellings that
 * hold a contact block, and no e-mail address left in the earlier versions. They said 221 versions and about 1,000 names.
 *   npx tsc lib/wp142.check.ts --outDir /tmp/chk --module commonjs --target es2022 --skipLibCheck && node /tmp/chk/wp142.check.js
 */
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const page = (p: string) => readFileSync(`app/(public)/${p}/page.tsx`, 'utf8');
const privacy = page('privacy');
const methodology = page('methodology');
const about = page('about');

// the privacy notice is the reference (its wording is the owner's): the figures below must be its own
for (const f of ['about 12,600 TED records', 'about 960 names', 'about 1,130 spellings']) assert.ok(privacy.includes(f), `privacy: ${f}`);
assert.ok(methodology.includes('up to about 12,600 TED records'), 'methodology: the raw store figure of privacy 1.7');
for (const [name, text] of [['methodology', methodology], ['about', about]] as const) {
  assert.ok(text.includes('About 960 buyer names (with about 1,130 spellings)') || text.includes('about 960 buyer names (with about 1,130 spellings)'), `${name}: the buyer names of privacy 1.7`);
  assert.ok(!/about 1,000 buyer names/i.test(text), `${name}: the stale "about 1,000 buyer names"`);
  assert.ok(!/\b221\b/.test(text), `${name}: the stale 221 archive versions`);
  assert.ok(!/earlier versions[^.]*(hold|still) (e-mail|some)/i.test(text), `${name}: the earlier versions hold no e-mail address since 22 October 2026`);
}
// ---- item 2: no async component inside a page ------------------------------------------------------------------------------
// An async server component is a part of the page that arrives on its own; a browser that began to hydrate while the document was
// still arriving failed on the footer with React error #418 (28 of 60 sliced loads of /tenders?q=fastcounts, 1 of 60 once it was
// synchronous). Pages and layouts (app/) read the data and hand it down; a component under components/ is never async.
const walk = (d: string): string[] => readdirSync(d, { withFileTypes: true })
  .flatMap((e) => (e.isDirectory() ? walk(join(d, e.name)) : e.name.endsWith('.tsx') ? [join(d, e.name)] : []));
const asyncComponents = walk('components').filter((f) => /export\s+(default\s+)?async\s+function\s+[A-Z]/.test(readFileSync(f, 'utf8')));
assert.deepEqual(asyncComponents, [], `async components under components/: ${asyncComponents.join(', ')}`);
for (const f of ['app/(public)/layout.tsx', 'app/not-found.tsx']) assert.ok(readFileSync(f, 'utf8').includes('<Footer health={health} />'), `${f}: the footer gets its data`);

console.log('wp142 checks passed');
