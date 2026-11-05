/**
 * Self-check of WP-143's render gate (web/gate.cjs, in front of the runtime server): at most `active` anonymous renders at once,
 * `queue` more wait in order, the rest are answered 503 with Retry-After at once; static files (by path, never the query string) and the
 * container's own requests are not counted; a request with a session cookie is counted in a pool of its own. Not part of the app. Run with `npm run check` (scripts/run-checks.mjs), from web/.
 */
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { displayName } from './display-name';

// eslint-disable-next-line @typescript-eslint/no-require-imports
const { createGate } = require(join(process.cwd(), 'gate.cjs')) as {
  createGate: (o: { active: number; queue: number; waitMs: number; retryAfter?: number }) => {
    wrap: (l: (req: unknown, res: unknown) => void) => (req: unknown, res: unknown) => void;
    state: () => { running: number; waiting: number };
  };
};

class Res extends EventEmitter {
  status = 0;
  headers: Record<string, string> = {};
  body = '';
  writeHead(s: number, h: Record<string, string>) { this.status = s; this.headers = h; }
  end(b = '') { this.body = b; this.emit('finish'); this.emit('close'); }
}
const req = (url: string, over: { addr?: string; cookie?: string } = {}) =>
  ({ url, headers: { cookie: over.cookie ?? '' }, socket: { remoteAddress: over.addr ?? '172.18.0.5' } });
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const gate = createGate({ active: 2, queue: 1, waitMs: 200, retryAfter: 30 });
  const started: string[] = [];
  const open = new Map<string, Res>();
  const handler = gate.wrap((rq, rs) => { const u = (rq as { url: string }).url; started.push(u); open.set(u, rs as Res); });
  const answers = ['/a', '/b', '/c', '/d'].map((u) => { const r = new Res(); handler(req(u), r); return r; });
  assert.deepEqual(started, ['/a', '/b'], 'two renders at once');
  assert.deepEqual(gate.state(), { running: 2, waiting: 1 });
  assert.equal(answers[3].status, 503, 'past the queue: refused at once');
  assert.equal(answers[3].headers['retry-after'], '30');
  assert.equal(answers[3].headers['cache-control'], 'no-store');
  open.get('/a')!.end('ok');
  assert.deepEqual(started, ['/a', '/b', '/c'], 'the waiting render starts when one ends');
  // not counted: static files, the container itself
  for (const [u, o] of [['/_next/static/chunks/x.js', {}], ['/', { addr: '127.0.0.1' }]] as const) {
    const r = new Res();
    handler(req(u, o), r);
    assert.ok(started.includes(u) && r.status === 0, `${u} passes`);
  }
  // a wait longer than waitMs is answered 503, and the slot is not lost
  const late = new Res();
  handler(req('/e'), late);
  await sleep(260);
  assert.equal(late.status, 503, 'waited too long');
  assert.equal(gate.state().waiting, 0);
  // a client that left the queue does not take a slot
  const gone = new Res();
  handler(req('/f'), gone);
  gone.emit('close');
  assert.equal(gate.state().waiting, 0);
  open.get('/b')!.end();
  open.get('/c')!.end();
  assert.deepEqual(gate.state(), { running: 0, waiting: 0 });
  assert.ok(!started.includes('/f'));
  // security review 2: the static-file test reads the path only, and a session cookie is counted in its own (smaller) pool
  {
    const g = createGate({ active: 1, queue: 0, waitMs: 200 }) as ReturnType<typeof createGate> & { sessionState: () => { running: number; waiting: number } };
    const seen: string[] = [];
    const h = g.wrap((rq) => { seen.push((rq as { url: string }).url); });
    h(req('/hold'), new Res());
    for (const [u, o] of [['/x?.js', {}], ['/funding?page=7&f=.css', {}], ['/tenders/1-x.js', {}], ['/_next/static/..%2ftenders', {}],
      ['/_next/static/../tenders', {}], ['/tenders', { cookie: 'x__Host-dg_session=abc' }]] as const) {
      const r = new Res();
      h(req(u, o), r);
      assert.equal(r.status, 503, `${u} is counted`);
    }
    for (const u of ['/_next/static/chunks/app/tenders/%5Bid%5D/page-1.js?v=2', '/brand/mark.svg', '/icon.svg?abc', '/robots.txt']) {
      const r = new Res();
      h(req(u), r);
      assert.ok(seen.includes(u) && r.status === 0, `${u} passes`);
    }
    const signed = new Res();
    h(req('/tenders', { cookie: 'a=1; __Host-dg_session=made-up' }), signed);
    assert.ok(seen.includes('/tenders') && signed.status === 0, 'a session cookie is admitted in its own pool');
    assert.deepEqual(g.sessionState(), { running: 1, waiting: 0 });
    const second = new Res();
    h(req('/funding', { cookie: '__Host-dg_session=other' }), second);
    assert.equal(second.status, 503, 'the session pool is limited too');
    assert.deepEqual(g.state(), { running: 1, waiting: 0 });
  }
  // item 13: the owner's words for a buyer withheld as a natural person: the same in the API and the site, and shown unchanged
  const PERSON = 'Name not shown: it identifies a private person.';
  for (const f of ['lib/api.ts', '../backend/dgate/suppress.py']) assert.ok(readFileSync(f, 'utf8').includes(PERSON), f);
  assert.equal(displayName(PERSON, 'title'), PERSON);
  assert.equal(displayName(PERSON), PERSON);
  console.log('wp143 ok');
})().catch((e) => { console.error(e); process.exit(1); });
