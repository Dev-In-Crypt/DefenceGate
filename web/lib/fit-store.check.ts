/**
 * Self-check of the store behind the "fits my profile" badges (WP-32). Not part of the app.
 * Run from web/:  node scripts/run-checks.mjs   (npm run check)
 *
 * A fake `window.localStorage` and a fake `fetch` stand in for the browser. What it proves:
 *   - without a saved profile no request is ever made, however many items mount;
 *   - with one, the items of a page are asked for in one request, and a call is asked for once;
 *   - the facts are compared with the profile in the store, and the profile never appears in a request;
 *   - the filter hides what is not eligible or not read, only once the facts are in, and turns off when the list goes;
 *   - a failed look-up is "unknown", never a verdict, and is asked again by the next page;
 *   - a profile saved after the first page is seen by the next item that mounts.
 */
import assert from 'node:assert/strict';

const storage = new Map<string, string>();
(globalThis as unknown as { window: unknown }).window = {
  localStorage: { getItem: (k: string) => storage.get(k) ?? null, setItem: (k: string, v: string) => { storage.set(k, v); } },
};
const requests: string[] = [];
let failNext = false;
const facts = (sme: boolean) => ({ state: 'read', basis: 'call_document', facts: {
  eligible_countries: { value: 'EU Member States', note: null, scope: 'call_document' },
  consortium_required: { value: false, note: null, scope: 'call_document' },
  sme_only: { value: sme, note: null, scope: 'call_document' },
} });
(globalThis as unknown as { fetch: unknown }).fetch = async (url: string, init?: { body?: unknown }) => {
  requests.push(url);
  assert.equal(init?.body, undefined, 'a GET with no body: the profile is not sent');
  if (failNext) { failNext = false; return { ok: false, status: 502, json: async () => ({}) }; }
  const ids = new URL(url, 'http://x').searchParams.get('ids')!.split(',');
  // 1: SME only, 2: open to all, 3: rules not read, 4: not in the answer (removed)
  const items: Record<string, unknown> = {};
  for (const id of ids) {
    if (id === '1') items[id] = facts(true);
    else if (id === '2') items[id] = facts(false);
    else if (id === '3') items[id] = { state: 'not_read', basis: null, facts: {} };
  }
  return { ok: true, status: 200, json: async () => ({ items }) };
};
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const profile = (over: object) => JSON.stringify({
  version: 1, step: 6, updatedAt: null, name: 'Secret Works', sizeClass: 'large', country: 'ES', managementSameCountry: true, managementCountry: '',
  control: 'no', uaOccupied: '', regime: 'none', componentPct: '', restricted: '', statuses: {}, classified: '', exportIntent: '', ...over,
});

async function main() {
  const store = await import('./fit-store');

  // 1. No saved profile: the items mount, nothing is asked.
  store.mount('1'); store.mount('2'); store.mount('3');
  await sleep(120);
  assert.deepEqual(requests, [], 'no request without a profile');
  assert.equal(store.getSnapshot().ready, true);
  assert.equal(store.getSnapshot().hasProfile, false);
  for (const id of ['1', '2', '3']) store.unmount(id);

  // 2. A large Spanish company: one request for the page, each call once.
  storage.set('dg.profile.v1', profile({}));
  store.mount('1'); store.mount('2'); store.mount('3'); store.mount('4'); store.mount('1');   // a call twice on the page
  await sleep(120);
  assert.equal(requests.length, 1);
  assert.equal(requests[0], '/api/fit/facts?ids=1,2,3,4');
  assert.ok(!requests[0].includes('ES') && !requests[0].includes('Secret'), 'the profile is not in the request');
  const verdict = (id: string) => store.fitFor(id).fit;
  assert.deepEqual(['1', '2', '3', '4'].map(verdict), ['no', 'yes', 'unknown', 'unknown']);
  assert.ok(['1', '2', '3', '4'].every((id) => store.isLoaded(id)));
  assert.deepEqual(store.getSnapshot().counts, { yes: 1, check: 0, no: 1, unknown: 2 });

  // 3. The filter hides what is not eligible and what has nothing to compare, and only when the facts are in.
  store.setOnlyFits(true);
  const s = store.getSnapshot();
  assert.deepEqual(['1', '2', '3', '4', '9'].map((id) => store.hiddenByFilter(s, id)), [true, false, true, true, false], 'call 9 was never looked up: not hidden');
  store.setOnlyFits(false);
  assert.equal(store.hiddenByFilter(store.getSnapshot(), '1'), false);

  // 4. Mounting again asks for nothing; leaving the list turns the filter off.
  store.setOnlyFits(true);
  store.mount('2');
  await sleep(120);
  assert.equal(requests.length, 1, 'a call already looked up is not asked again');
  for (const id of ['1', '2', '3', '4']) store.unmount(id);
  store.unmount('1'); store.unmount('2');
  assert.equal(store.getSnapshot().onlyFits, false, 'the filter does not outlive the list');

  // 5. A failed look-up is unknown, never a verdict, and the next page asks again.
  failNext = true;
  store.mount('5');
  await sleep(120);
  assert.equal(store.fitFor('5').fit, 'unknown');
  assert.ok(store.isLoaded('5'));
  const before = requests.length;
  store.unmount('5');
  store.mount('5');
  await sleep(120);
  assert.equal(requests.length, before + 1, 'asked again');
  store.unmount('5');

  // 6. A profile saved after the first page is seen by the next item (a client-side navigation).
  storage.set('dg.profile.v1', profile({ sizeClass: 'small' }));
  store.mount('1');
  await sleep(120);
  assert.equal(store.fitFor('1').fit, 'yes', 'a small company is allowed where the large one was not');
  store.unmount('1');

  // 7. The profile is removed: the badges go.
  storage.delete('dg.profile.v1');
  store.mount('2');
  await sleep(120);
  assert.equal(store.getSnapshot().hasProfile, false);
  console.log('fit-store checks passed');
}

main().then(() => process.exit(0), (e) => { console.error(e); process.exit(1); });
