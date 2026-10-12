import { accountFetch } from '@/lib/account';

export const dynamic = 'force-dynamic';

const back = (code: string) =>
  new Response(null, { status: 303, headers: { location: `/app/settings?n=${code}`, 'cache-control': 'private, no-store' } });

/**
 * Streams the account export as a download. POST only (the export is logged by the API, so it is not a GET),
 * and only from this site: a server action gets the Origin check from Next.js, a route handler does it here.
 */
export async function POST(req: Request) {
  const origin = req.headers.get('origin');
  const host = req.headers.get('x-forwarded-host') ?? req.headers.get('host');
  let sameOrigin = false;
  try { sameOrigin = origin !== null && host !== null && new URL(origin).host === host; } catch { /* not a URL */ }
  if (!sameOrigin) return new Response(null, { status: 403 });

  let res: Response;
  try {
    res = await accountFetch('/export');
  } catch {
    return back('error');
  }
  if (res.status === 401) return new Response(null, { status: 303, headers: { location: '/auth/expired', 'cache-control': 'private, no-store' } });
  if (!res.ok || !res.body) return back('error');

  return new Response(res.body, {
    status: 200,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'content-disposition': 'attachment; filename="defencegate-account-export.json"',
      'cache-control': 'private, no-store',
      'x-content-type-options': 'nosniff',
    },
  });
}
