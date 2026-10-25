// HTTPS in front of a local `next start`, for e2e/wp79.spec.ts: the account cookies are `__Host-` and Secure, and a browser keeps
// them only from an https origin. A throwaway self-signed certificate is enough (the test context ignores certificate errors):
//
//   openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=localhost -keyout key.pem -out cert.pem
//   node e2e/support/https-proxy.mjs 3443 3101 key.pem cert.pem
import { readFileSync } from 'node:fs';
import { request } from 'node:http';
import { createServer } from 'node:https';

const [listen = '3443', target = '3101', key = 'key.pem', cert = 'cert.pem'] = process.argv.slice(2);

createServer({ key: readFileSync(key), cert: readFileSync(cert) }, (req, res) => {
  const upstream = request({ host: '127.0.0.1', port: Number(target), path: req.url, method: req.method,
    headers: { ...req.headers, 'x-forwarded-proto': 'https' } }, (up) => {
    res.writeHead(up.statusCode ?? 502, up.headers);
    up.pipe(res);
  });
  upstream.on('error', () => { res.writeHead(502); res.end(); });
  req.pipe(upstream);
}).listen(Number(listen), '127.0.0.1', () => console.log(`https on ${listen} -> ${target}`));
