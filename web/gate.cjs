/**
 * WP-143: a global limit on the anonymous page renders the site works on at once, in front of Next's own server (the runtime image
 * starts `node gate.cjs`, which starts `server.js`; web/Dockerfile).
 *
 * On 26 October 2026 09:12-09:32 UTC a crawler from 7,447 addresses (three requests each, browser user agents) asked for deep pages
 * faster than two cores render them: every render waited for the others, p50 rose to 11 s and 111 requests hit the proxy's 30 s.
 * A limit per address cannot see that. This one counts renders, not addresses: at most ACTIVE at a time; the next QUEUE wait, in
 * order, up to WAIT_MS; anything beyond is answered 503 with Retry-After at once, and costs nothing. A render admitted stays as
 * fast as the API lets it, instead of every render waiting for all the others. It cannot tell a visitor from the flood: in a flood
 * a visitor gets the quick 503 as often as a crawler does (a challenge that tells them apart needs a front service: the owner's).
 *
 * Not counted: the static files (/_next/static, images, icons), requests from the container itself (its healthcheck, the feed
 * warmer), and a signed-in visitor (the session cookie). Sizes (DG_GATE_ACTIVE, DG_GATE_QUEUE, DG_GATE_WAIT_MS; set in
 * infra/docker-compose.yml): the server has 2 cores and the API 24 database connections, a page asks the API 3 to 6 times; 12 at
 * about 0.5 s each are 24 pages a second, six times the busiest normal hour (~4 a second). Lab measurements: the WP-143 self-check.
 */
'use strict';
const http = require('node:http');

const SKIP = /^\/(?:_next\/static\/|_next\/image|favicon|icon|apple-icon|robots\.txt|.*\.(?:css|js|png|svg|ico|woff2?|txt|webmanifest)$)/;
const SESSION = '__Host-dg_session=';

function createGate({ active = 12, queue = 24, waitMs = 5000, retryAfter = 30, countLoopback = false } = {}) {
  let running = 0;
  const waiting = [];
  const stats = { admitted: 0, queued: 0, refused: 0, timedOut: 0 };

  function release() {
    running -= 1;
    while (waiting.length > 0 && running < active) {
      const next = waiting.shift();
      if (next.done) continue;
      next.done = true;
      clearTimeout(next.timer);
      running += 1;
      next.go();
    }
  }

  function refuse(res, why) {
    stats[why] += 1;
    res.writeHead(503, { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store', 'retry-after': String(retryAfter) });
    res.end('The site is busy. Please try again in a minute.');
  }

  function counted(req) {
    const addr = req.socket && req.socket.remoteAddress;
    // countLoopback: the load lab only (its clients are on the same machine)
    if (!countLoopback && (addr === '127.0.0.1' || addr === '::1' || addr === '::ffff:127.0.0.1')) return false;
    if (SKIP.test(req.url || '/')) return false;
    if ((req.headers.cookie || '').includes(SESSION)) return false;
    return true;
  }

  /** Wraps a request listener: the listener runs when the render is admitted. */
  function wrap(listener) {
    return function gated(req, res) {
      if (!counted(req)) return listener.call(this, req, res);
      const self = this;
      const go = () => {
        stats.admitted += 1;
        let freed = false;
        const free = () => { if (!freed) { freed = true; release(); } };
        res.once('finish', free);
        res.once('close', free);
        return listener.call(self, req, res);
      };
      if (running < active) { running += 1; return go(); }
      if (waiting.length >= queue) return refuse(res, 'refused');
      stats.queued += 1;
      const entry = { done: false, go, timer: null };
      const leave = () => { entry.done = true; clearTimeout(entry.timer); const at = waiting.indexOf(entry); if (at >= 0) waiting.splice(at, 1); };
      entry.timer = setTimeout(() => { if (!entry.done) { leave(); refuse(res, 'timedOut'); } }, waitMs);
      // a client that gave up while waiting leaves the queue
      res.once('close', () => { if (!entry.done) leave(); });
      waiting.push(entry);
      return undefined;
    };
  }

  return { wrap, stats, state: () => ({ running, waiting: waiting.length }) };
}

module.exports = { createGate };

if (require.main === module) {
  const gate = createGate({
    active: Number(process.env.DG_GATE_ACTIVE || 12),
    queue: Number(process.env.DG_GATE_QUEUE || 24),
    waitMs: Number(process.env.DG_GATE_WAIT_MS || 5000),
  });
  const create = http.createServer;
  http.createServer = function createServer(...args) {
    const i = args.findIndex((a) => typeof a === 'function');
    if (i >= 0) args[i] = gate.wrap(args[i]);
    const server = create.apply(this, args);
    if (i < 0) {
      // a listener added later (server.on('request', fn)) is wrapped the same way
      const on = server.on;
      server.on = function onEvent(event, fn) { return on.call(this, event, event === 'request' ? gate.wrap(fn) : fn); };
      server.addListener = server.on;
    }
    return server;
  };
  setInterval(() => {
    const s = gate.stats;
    if (s.refused || s.timedOut) console.log(`gate: ${s.admitted} admitted, ${s.queued} queued, ${s.refused} refused, ${s.timedOut} timed out (last minute)`);
    s.admitted = s.queued = s.refused = s.timedOut = 0;
  }, 60_000).unref();
  require('./server.js');
}
