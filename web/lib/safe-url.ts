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
