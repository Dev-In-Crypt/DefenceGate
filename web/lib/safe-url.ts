/**
 * WP-116: where sign-in returns to (`/signin?next=`, then a cookie across the mailed link). Only a page of the signed-in area of
 * this site: a path under /app made of plain URL characters, with an optional query, no `//`, `\`, `..`, scheme or host, so
 * it can never send the visitor to another site (open redirect). null for anything else; the caller then uses /app.
 */
const RETURN_PATH = /^\/app(?:\/[A-Za-z0-9._~%-]+)*\/?(?:\?[A-Za-z0-9._~%&=+,-]*)?$/;
export function safeReturnPath(value: unknown): string | null {
  if (typeof value !== 'string' || value.length > 300 || !RETURN_PATH.test(value)) return null;
  // a percent-encoded slash, backslash or dot segment could be decoded into one of the forms refused above
  if (/%(?:2f|5c|2e)/i.test(value) || /(?:^|\/)\.{1,2}(?:\/|\?|$)/.test(value)) return null;
  return value;
}

/**
 * The return path rides in the sign-in cookie (`__Host-dg_bind`, lib/account.ts) after the binder, across the mailed link: no
 * further cookie. The binder is URL-safe base64, so the first `.` ends it. `readBind` checks the path again on the way back.
 */
export function bindValue(binder: string, next: string | null): string {
  const safe = safeReturnPath(next);
  return safe ? `${binder}.${encodeURIComponent(safe)}` : binder;
}
export function readBind(value: string | undefined): { binder: string | undefined; next: string | null } {
  if (!value) return { binder: undefined, next: null };
  const dot = value.indexOf('.');
  if (dot < 0) return { binder: value, next: null };
  let next: string | null = null;
  try { next = safeReturnPath(decodeURIComponent(value.slice(dot + 1))); } catch { next = null; }
  return { binder: value.slice(0, dot), next };
}

/**
 * Source-supplied URLs (the original record of a call) come from third-party feeds.
 * Only plain http(s) may become an href or a JSON-LD url; `javascript:`, `data:` and the like are dropped.
 * Returns the input unchanged when it is safe, otherwise null (callers then render the text without a link).
 */
export function safeHttpUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const { protocol } = new URL(value);
    return protocol === 'http:' || protocol === 'https:' ? value : null;
  } catch {
    return null;
  }
}
