/**
 * Self-check of WP-128: a last good answer kept on disk belongs to the build and the data service that wrote it, so a server
 * started after another (a deploy, or the e2e run's fake-API site beside the demo one) never serves that other's copy, and two
 * consecutive /changes.atom requests with unchanged data give one body: the second, conditional on the first's ETag, is a 304.
 * Not part of the app and not imported by it.
 * Run from web/:  npx tsc lib/wp128.check.ts --outDir /tmp/dgchk --module commonjs --target es2022 --skipLibCheck --esModuleInterop --resolveJsonModule && node /tmp/dgchk/wp128.check.js
 */
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildAtom, etagOf, feedSubtitle } from './atom';
import { recall, remember, resetLastGood, storeScope } from './last-good';

type Feed = Awaited<ReturnType<typeof import('./api').getChangesForFeed>>;

// The route's body of page 1 (app/(public)/changes.atom/route.ts), whose hash is the ETag.
const etag = (p: Feed) => {
  assert.ok(p);
  return etagOf(buildAtom(p.items, {
    origin: 'https://ci.example.test', selfPath: '/changes.atom', pagePath: '/changes', title: 'DefenceGate: what changed',
    subtitle: feedSubtitle(p.windowDays, p.total, p.held, { page: 1, pages: p.feedPages, size: 400 }), generatedAt: p.windowTo,
  }, p.funding ?? []));
};

// lib/api imports next/headers (not called in demo mode); the check is compiled to a temporary folder, so it is found from web/.
process.env.NODE_PATH = join(process.cwd(), 'node_modules');
require('node:module').Module._initPaths();

/** A fresh server process: no memory of the last good answers, a new lib/api (its feed caches are empty). */
async function restart() {
  resetLastGood();
  delete require.cache[require.resolve('./api')];
  return import('./api');
}

void (async () => {
  process.env.DG_LAST_GOOD_DIR = mkdtempSync(join(tmpdir(), 'dg-last-good-'));
  delete process.env.DG_API_URL;                                                 // the demo data, as the CI build

  // 1. The store: a copy written while reading another data service is not this server's.
  const demo = storeScope();
  assert.match(demo, /\|demo$/);
  process.env.DG_API_URL = 'http://127.0.0.1:4010';
  assert.notEqual(storeScope(), demo);
  await remember('k', { total: 2311 }, { persist: true });
  resetLastGood();
  assert.deepEqual((await recall<{ total: number }>('k'))?.value, { total: 2311 }, 'the same build and service: kept across a restart');
  delete process.env.DG_API_URL;
  resetLastGood();
  assert.equal(await recall('k'), null, 'another service\'s copy is not offered');

  // 2. /changes.atom after a restart with another build's or service's copy of page 1 on disk (the fake API's 2,311 changes).
  const api = await restart();
  const own = await api.getChangesForFeed({}, 1);
  assert.ok(own && own.items.length > 0);
  await new Promise((r) => setTimeout(r, 300));                                  // the build's own copy is written first
  process.env.DG_API_URL = 'http://127.0.0.1:4010';
  await remember('feed:#1', { ...own, items: own.items.slice(1), total: 2311, held: own.items.length - 1 }, { persist: true });
  delete process.env.DG_API_URL;
  let fresh = await restart();
  const first = await fresh.getChangesForFeed({}, 1);
  const second = await fresh.getChangesForFeed({}, 1);
  assert.equal(etag(first), etag(own), 'the first request is not served the other copy');
  assert.equal(etag(second), etag(first), 'the second request, with the first one\'s ETag, is a 304');

  // 3. A restart of the same build with its own copy on disk: served while the page is built again (the speed of WP-98c), and the
  // same body as the rebuilt page, so the next conditional request is still a 304.
  await remember('feed:#1', own, { persist: true });
  fresh = await restart();
  const a = await fresh.getChangesForFeed({}, 1);
  const b = await fresh.getChangesForFeed({}, 1);
  assert.equal(etag(a), etag(own));
  assert.equal(etag(b), etag(a));
  console.log('wp128 checks passed');
})().catch((e) => { console.error(e); process.exit(1); });
