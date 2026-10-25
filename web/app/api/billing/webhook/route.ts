/**
 * WP-124: Creem's webhook (Creem dashboard, Developers, Webhooks: https://<domain>/api/billing/webhook). The site's server is the only
 * public way in, so it forwards the request to the API unread: the raw bytes and the `creem-signature` header, nothing else. The API
 * verifies the signature (it alone holds the secret) and answers; that answer goes back to Creem, which retries anything but a 2xx.
 * The body is capped at 64 KiB here, as in Caddy and the API.
 */
export const dynamic = 'force-dynamic';

const MAX = 64 * 1024;

export async function POST(request: Request): Promise<Response> {
  const declared = Number(request.headers.get('content-length') ?? '0');
  if (declared > MAX) return new Response(null, { status: 413 });
  const raw = new Uint8Array(await request.arrayBuffer());
  if (raw.byteLength > MAX) return new Response(null, { status: 413 });
  const api = process.env.DG_API_URL;
  if (!api) return new Response(null, { status: 503 });
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  const signature = request.headers.get('creem-signature');
  if (signature && signature.length <= 128) headers['creem-signature'] = signature;
  if (process.env.DG_INTERNAL_SECRET) headers['x-dg-internal'] = process.env.DG_INTERNAL_SECRET;
  try {
    const res = await fetch(`${api}/v1/billing/webhook`, {
      method: 'POST', headers, body: raw, cache: 'no-store', signal: AbortSignal.timeout(15_000),
    });
    return new Response(null, { status: res.status, headers: { 'cache-control': 'no-store' } });
  } catch {
    return new Response(null, { status: 502 });
  }
}
