// A fake of the account API (backend/dgate/accounts.py, WP-79) with accounts open, for e2e/wp79.spec.ts only. The real flows and
// their security rules are tested against the API itself (backend/tests/integration/test_accounts*.py); this checks that the site's
// forms send what the API expects, show what it answers and set the cookies.
//
//   node e2e/support/fake-accounts.mjs [port]      then:  DG_API_URL=http://127.0.0.1:4011 npx next start -p 3101
//   E2E_FAKE_ACCOUNTS=1 E2E_BASE_URL=http://127.0.0.1:3101 npx playwright test e2e/wp79.spec.ts
//
// Accounts: any address with the password "right password here"; an address starting with "totp" asks for the code 123456. The
// confirmation and reset token is "k" x 43.
import { createServer } from 'node:http';

const PORT = Number(process.argv[2] ?? process.env.FAKE_ACCOUNTS_PORT ?? 4011);
const PASSWORD = 'right password here';
const SESSION = 's'.repeat(43);
const TICKET = 't'.repeat(43);
const TOKEN = 'k'.repeat(43);
const session = () => [200, { session: SESSION, expiresAt: new Date(Date.now() + 30 * 86400e3).toISOString(), isNew: false }];
const KEYS = [];
const EVENTS = [];
const policy = (pw) => (typeof pw === 'string' && pw.length >= 12 ? null : [422, { error: 'password_too_short', message: 'use at least 12 characters' }]);

function route(method, path, headers, body, query) {
  if (path === '/v1/sources') return [200, { generatedAt: '2026-10-12T08:00:00Z', sources: [] }];   // read by the public layout
  if (path === '/v1/account/status') return [200, { open: true, termsVersion: '2.0', privacyVersion: '1.7' }];
  if (method === 'POST' && path === '/v1/account/auth/register') {
    if (!body.acceptTerms || body.termsVersion !== '2.0' || body.privacyVersion !== '1.7') return [422, { error: 'terms_not_accepted' }];
    return policy(body.password) ?? [202, { ok: true }];
  }
  if (method === 'POST' && path === '/v1/account/auth/login') {
    if (body.password !== PASSWORD) return [401, { error: 'invalid_credentials', message: 'the e-mail address or the password is wrong' }];
    // WP-157: an address starting with "team" is a Consultant account in a workspace (e2e/wp157.spec.ts)
    if (String(body.email).startsWith('team')) return [200, { ...session()[1], session: TEAM_SESSION }];
    return String(body.email).startsWith('totp') ? [200, { secondStep: true, ticket: TICKET }] : session();
  }
  if (method === 'POST' && path === '/v1/account/auth/login/second') {
    if (body.ticket !== TICKET) return [400, { error: 'invalid_or_expired' }];
    return body.code === '123456' ? session() : [401, { error: 'invalid_code' }];
  }
  if (method === 'POST' && path === '/v1/account/auth/verify') return body.token === TOKEN ? [200, { ok: true }] : [400, { error: 'invalid_or_expired' }];
  if (method === 'POST' && path === '/v1/account/auth/reset/request') return [202, { ok: true }];
  if (method === 'POST' && path === '/v1/account/auth/reset/confirm') {
    if (body.token !== TOKEN) return [400, { error: 'invalid_or_expired' }];
    return policy(body.password) ?? [200, { ok: true }];
  }
  if (headers['x-dg-session'] === TEAM_SESSION) return team(method, path, body, query);
  const signedIn = headers['x-dg-session'] === SESSION;
  if (method === 'POST' && path === '/v1/account/me/totp/setup') {
    if (!signedIn) return [401, { error: 'unauthenticated' }];
    if (body.password !== PASSWORD) return [403, { error: 'wrong_password' }];
    return [200, { secret: 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP', uri: 'otpauth://totp/DefenceGate:ann%40example.test?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP' }];
  }
  if (method === 'POST' && path === '/v1/account/me/totp/enable') {
    if (!signedIn) return [401, { error: 'unauthenticated' }];
    return body.code === '123456' ? [200, { recoveryCodes: Array.from({ length: 10 }, (_, i) => `abcde-fgh${String(i).padStart(2, '2')}`) }]
      : [422, { error: 'invalid_code' }];
  }
  if (method === 'POST' && path === '/v1/account/me/password') {
    if (!signedIn) return [401, { error: 'unauthenticated' }];
    if (body.currentPassword !== PASSWORD) return [403, { error: 'wrong_password' }];
    return policy(body.newPassword) ?? [200, { ok: true }];
  }
  if (path === '/v1/account/me') {
    if (headers['x-dg-session'] !== SESSION) return [401, { error: 'unauthenticated' }];
    return [200, { id: 'u1', email: 'ann@example.test', createdAt: '2026-10-22T08:00:00Z', profile: { role: 'supplier', tracks: ['tenders'], countries: [], scope: 'core', cadence: 'daily' },
      onboarded: true, lastVisitAt: null, terms: { current: true }, security: { hasPassword: true, totp: false }, features: ['api_keys'] }];
  }
  // WP-153 (e2e/wp153.spec.ts): API keys, open. The key is made of the counter so a test can tell one from another.
  if (path === '/v1/account/keys' || path.startsWith('/v1/account/keys/')) {
    if (!signedIn) return [401, { error: 'unauthenticated' }];
    if (method === 'GET') return [200, { open: true, sources: ['ted'], scopes: ['tenders', 'archive'], maxKeys: 50, keys: [...KEYS].reverse(), events: [...EVENTS].reverse() }];
    if (body.password !== PASSWORD) return [403, { error: 'wrong_password' }];
    const now = new Date().toISOString();
    if (method === 'POST' && path === '/v1/account/keys') {
      const n = KEYS.length + 1;
      const prefix = String(n).padStart(12, 'a');
      const meta = { id: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`, name: body.name, prefix, scopes: body.scopes, ratePerMinute: 60,
        dailyQuota: 10000, createdAt: now, expiresAt: new Date(Date.now() + 365 * 86400e3).toISOString(), lastUsedAt: null, revokedAt: null, requestsToday: 0 };
      KEYS.push(meta);
      EVENTS.push({ event: 'created', at: now, name: meta.name, prefix });
      return [201, { ...meta, key: `dgk_${prefix}_${'x'.repeat(42)}${n}` }];
    }
    const k = KEYS.find((x) => path === `/v1/account/keys/${x.id}/revoke` && !x.revokedAt);
    if (method === 'POST' && k) {
      k.revokedAt = now;
      EVENTS.push({ event: 'revoked', at: now, name: k.name, prefix: k.prefix });
      return [200, k];
    }
    return [404, { error: 'not_found' }];
  }
  // WP-150 (e2e/wp150.spec.ts): a dashboard with an entry in each block that has titles (a saved search, a change, a follow)
  if (path === '/v1/account/dashboard') {
    if (headers['x-dg-session'] !== SESSION) return [401, { error: 'unauthenticated' }];
    const src = { sourceId: 'ted', sourceName: 'TED', url: 'https://ted.europa.eu/en/notice/-/detail/1', retrievedAt: '2026-10-11T06:20:00Z', lastChangeKind: 'first_seen', licence: 'Commission Decision 2011/833/EU', attribution: '© European Union, TED' };
    const tender = { id: '102', slug: '102-sample-notice', noticeId: '102-2026', title: 'Maintenance of logistics vehicles (sample)', titleLanguage: 'en', originalTitle: null, originalLanguage: null,
      buyerId: '5', buyerSlug: '5-sample-buyer', buyerName: 'Sample Ministry of Defence', country: 'PL', cpv: '35800000', cpvCodes: ['35800000'], procedure: 'Open procedure', legalBasis: '32009L0081',
      scope: 'core', deadline: '2026-10-23T12:00:00Z', publishedAt: '2026-10-01T00:00:00Z', estimatedValue: null, status: 'open', statusNative: 'open', amended: true, versionCount: 3,
      securityClearance: false, subcontracting: false, sameNotice: [], source: src };
    return [200, {
      lastVisitAt: '2026-10-10T08:00:00Z',
      matches: [{ search: { id: 'q1', name: 'Poland, vehicles', kind: 'tender' }, newCount: 1, totalCount: 17, items: [tender] }],
      closingSoon: [{ kind: 'tender', item: tender, source: 'shortlist' }],
      changes: [{ kind: 'tender', item: tender, observedAt: '2026-10-11T06:00:00Z', changes: [{ field: 'deadline', label: 'Deadline', before: '2026-10-16T12:00:00Z', after: '2026-10-23T12:00:00Z' }] }],
      following: [{ kind: 'buyer', ref: '5', name: 'Sample Ministry of Defence', openCount: 4, latestAt: '2026-10-11T06:00:00Z' }],
      shortlist: { counts: { bidding: 1 }, items: [{ kind: 'tender', ref: '102', status: 'bidding', note: '', createdAt: '2026-10-04T08:00:00Z', updatedAt: '2026-10-10T08:00:00Z', item: tender }] },
      pulse: null,
    }];
  }
  return [404, { detail: 'not here' }];
}

// WP-157 (e2e/wp157.spec.ts): the team workspace and client profiles of a Consultant account, kept in memory. Names and addresses
// are the tests' own (unique per project), so the desktop and mobile runs do not step on each other.
const TEAM_SESSION = 'T'.repeat(43);
const JOIN_TOKEN = 'j'.repeat(43);
const WS = { members: [{ id: '00000000-0000-4000-8000-0000000000a1', email: 'team@example.test', role: 'owner', joinedAt: '2026-10-29T08:00:00Z', me: true }],
  invites: [], clients: [] };
let wsMade = false;
let n = 0;
const uuid = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
const TENDER = { id: '102', slug: '102-sample-notice', noticeId: '102-2026', title: 'Maintenance of logistics vehicles (sample)', buyerName: 'Sample Ministry of Defence',
  country: 'PL', cpv: '35800000', cpvCodes: ['35800000'], deadline: '2026-11-23T12:00:00Z', publishedAt: '2026-10-01T00:00:00Z', status: 'open', scope: 'core', source: {} };

function team(method, path, body, query) {
  const client = query.get('client');
  if (path === '/v1/account/me') {
    return [200, { id: 'u2', email: 'team@example.test', createdAt: '2026-10-22T08:00:00Z', profile: { role: 'consultant', tracks: ['tenders'], countries: [], scope: 'core', cadence: 'daily' },
      onboarded: true, lastVisitAt: null, terms: { current: true }, security: { hasPassword: true, totp: false }, plan: { current: 'consultant' },
      features: ['saved_searches', 'email_alerts', 'team_workspace', 'client_profiles'], limits: { savedSearches: 200, reportsPerMonth: null },
      workspace: wsMade ? { role: 'owner', active: true } : null }];
  }
  if (path === '/v1/account/workspace') {
    if (method === 'POST') { wsMade = true; return [201, { id: 'w1' }]; }
    if (method === 'DELETE') { wsMade = false; return [204, null]; }
    return [200, wsMade ? { workspace: { id: 'w1', role: 'owner', active: true, seats: 5, members: WS.members, invites: WS.invites }, canCreate: false, seats: 5 }
      : { workspace: null, canCreate: true, seats: 5 }];
  }
  if (method === 'POST' && path === '/v1/account/workspace/invites') {
    if (String(body.email).startsWith('full')) return [409, { error: 'seats_full' }];
    WS.invites.push({ id: uuid(), email: body.email, createdAt: new Date().toISOString(), expiresAt: new Date(Date.now() + 7 * 86400e3).toISOString() });
    return [201, WS.invites.at(-1)];
  }
  if (method === 'DELETE' && path.startsWith('/v1/account/workspace/invites/')) {
    const i = WS.invites.findIndex((x) => path.endsWith(x.id));
    if (i < 0) return [404, { error: 'not_found' }];
    WS.invites.splice(i, 1);
    return [204, null];
  }
  if (method === 'POST' && path === '/v1/account/workspace/join') return body.token === JOIN_TOKEN ? [200, { ok: true }] : [400, { error: 'invalid_or_expired' }];
  if (path === '/v1/account/clients') {
    if (method === 'POST') {
      wsMade = true;                                       // as the API: the first client profile makes the workspace
      WS.clients.push({ id: uuid(), name: body.name, country: body.country, cpvCodes: body.cpvCodes, note: body.note, createdAt: '', updatedAt: '' });
      return [201, WS.clients.at(-1)];
    }
    return [200, { items: WS.clients, limit: 15, allowed: true }];
  }
  if (path.startsWith('/v1/account/clients/')) {
    const c = WS.clients.find((x) => path.endsWith(x.id));
    if (!c) return [404, { error: 'not_found' }];
    if (method === 'DELETE') { WS.clients.splice(WS.clients.indexOf(c), 1); return [204, null]; }
    Object.assign(c, body);
    return [200, c];
  }
  if (path === '/v1/account/searches') {
    const items = [{ id: '00000000-0000-4000-8000-0000000000b1', name: 'Vehicles for a client', kind: 'tender', filters: { q: 'vehicles' }, cadence: 'daily',
      createdAt: '2026-10-20T08:00:00Z', matchCount: 3, newCount: 0, lastMatchAt: null, paused: false, clientId: client ?? WS.clients[0]?.id ?? null, mine: true },
    { id: '00000000-0000-4000-8000-0000000000b2', name: 'A colleague\'s search', kind: 'tender', filters: {}, cadence: 'weekly',
      createdAt: '2026-10-21T08:00:00Z', matchCount: 9, newCount: 1, lastMatchAt: null, paused: false, clientId: null, mine: false }];
    return [200, { items: client ? items.filter((s) => s.clientId === client) : items, limit: 200 }];
  }
  if (method === 'PATCH' && path.startsWith('/v1/account/searches/')) return [200, {}];
  if (path === '/v1/account/shortlist') {
    const items = [{ kind: 'tender', ref: '102', status: 'bidding', note: 'Team note', createdAt: '2026-10-04T08:00:00Z', updatedAt: '2026-10-10T08:00:00Z',
      item: TENDER, clientId: client ?? WS.clients[0]?.id ?? null }];   // the entry is the picked client's (the run's own)
    return [200, { items }];
  }
  if (method === 'PUT' && path.startsWith('/v1/account/shortlist/')) return [200, {}];
  return [404, { detail: 'not here' }];
}

createServer((req, res) => {
  let raw = '';
  req.on('data', (c) => { raw += c; });
  req.on('end', () => {
    let body = {};
    try { body = raw ? JSON.parse(raw) : {}; } catch { /* not JSON */ }
    const url = new URL(req.url ?? '/', 'http://x');
    const [status, out] = route(req.method, url.pathname, req.headers, body, url.searchParams);
    res.writeHead(status, { 'content-type': 'application/json' });
    res.end(JSON.stringify(out));
  });
}).listen(PORT, '127.0.0.1', () => console.log(`fake account API on ${PORT}`));
