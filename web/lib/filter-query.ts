/**
 * The query string a filter form produces, and how two of them are compared. Pure (no DOM, no React): the live form in
 * components/funding/filter-panel.tsx feeds it the form's entries, lib/wp49.check.ts runs it on its own.
 */

/** Values a filter has when it is not in the address (the page's own defaults): left out of the address, so it stays short. */
export type FormDefaults = Record<string, string>;

/**
 * The query string of form entries: empty values and `defaults` dropped, repeats of one name joined with commas, the page dropped
 * (a changed filter starts at page 1). "" when nothing is left, else "?a=b&...".
 */
export function queryFromEntries(entries: Iterable<[string, unknown]>, defaults: FormDefaults = {}): string {
  const map = new Map<string, string[]>();
  for (const [k, v] of entries) {
    if (typeof v !== 'string' || v === '') continue;
    map.set(k, [...(map.get(k) ?? []), v]);
  }
  const p = new URLSearchParams();
  for (const [k, vals] of map) {
    const joined = vals.join(',');
    if (defaults[k] !== joined) p.set(k, joined);
  }
  p.delete('page');
  const s = p.toString();
  return s ? `?${s}` : '';
}

/** A query in a form that compares: no page, no empty value, no default, sorted. Two addresses with the same filters are equal. */
export function canonQuery(search: string, defaults: FormDefaults = {}): string {
  return [...new URLSearchParams(search).entries()]
    .filter(([k, v]) => v !== '' && k !== 'page' && defaults[k] !== v)
    .map(([k, v]) => `${k}=${v}`)
    .sort()
    .join('&');
}
