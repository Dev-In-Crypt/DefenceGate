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
const policy = (pw) => (typeof pw === 'string' && pw.length >= 12 ? null : [422, { error: 'password_too_short', message: 'use at least 12 characters' }]);

function route(method, path, headers, body) {
  if (path === '/v1/sources') return [200, { generatedAt: '2026-10-12T08:00:00Z', sources: [] }];   // read by the public layout
  if (path === '/v1/account/status') return [200, { open: true, termsVersion: '2.0', privacyVersion: '1.7' }];
  if (method === 'POST' && path === '/v1/account/auth/register') {
    if (!body.acceptTerms || body.termsVersion !== '2.0' || body.privacyVersion !== '1.7') return [422, { error: 'terms_not_accepted' }];
    return policy(body.password) ?? [202, { ok: true }];
  }
  if (method === 'POST' && path === '/v1/account/auth/login') {
    if (body.password !== PASSWORD) return [401, { error: 'invalid_credentials', message: 'the e-mail address or the password is wrong' }];
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
      onboarded: true, lastVisitAt: null, terms: { current: true }, security: { hasPassword: true, totp: false } }];
  }
  return [404, { detail: 'not here' }];
}

createServer((req, res) => {
  let raw = '';
  req.on('data', (c) => { raw += c; });
  req.on('end', () => {
    let body = {};
    try { body = raw ? JSON.parse(raw) : {}; } catch { /* not JSON */ }
    const [status, out] = route(req.method, new URL(req.url ?? '/', 'http://x').pathname, req.headers, body);
    res.writeHead(status, { 'content-type': 'application/json' });
    res.end(JSON.stringify(out));
  });
}).listen(PORT, '127.0.0.1', () => console.log(`fake account API on ${PORT}`));
