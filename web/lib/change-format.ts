/**
 * One side of a version-history line, said for a person. The API already words these (dates as "10 Sep 2026",
 * a status as "Open", an amount with its currency); this is the safety net for an API build that does not,
 * and it leaves an already-worded value alone. Never prints the repr of a Python or JSON value.
 */
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const;
const pad = (n: number) => String(n).padStart(2, '0');

const STATUS: Record<string, string> = {
  open: 'Open', closed: 'Closed', awarded: 'Awarded', cancelled: 'Cancelled', canceled: 'Cancelled',
  forthcoming: 'Planned', planned: 'Planned', expired: 'Closed', evaluated: 'Under evaluation', unknown: 'Status unknown',
};

const day = (d: Date) => `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const ISO_MOMENT = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z| ?UTC|[+-]\d{2}:?\d{2})?$/;

/** A list or mapping that arrived as text ("['35200000', '35810000']"), read back; anything else as it came. */
function plain(value: string): unknown {
  const t = value.trim();
  if (t[0] !== '[' && t[0] !== '{') return value;
  const tries = [t, t.replace(/'/g, '"').replace(/\bNone\b/g, 'null').replace(/\bTrue\b/g, 'true').replace(/\bFalse\b/g, 'false')];
  for (const attempt of tries) {
    try { return JSON.parse(attempt); } catch { /* try the next reading */ }
  }
  return value;
}

function say(v: unknown): string {
  if (Array.isArray(v)) return v.map(say).filter(Boolean).join(', ');
  if (v && typeof v === 'object') {
    const o = v as Record<string, unknown>;
    if (typeof o.amount === 'number' && typeof o.currency === 'string') return `${o.currency} ${o.amount.toLocaleString('en-GB', { maximumFractionDigits: 2 })}`;
    return Object.entries(o).map(([k, x]) => `${k}: ${say(x)}`).join('; ');
  }
  return v === null || v === undefined ? '' : String(v);
}

export function formatChangeValue(field: string, value: string | null | undefined): string | null {
  if (value === null || value === undefined || value.trim() === '') return null;
  const text = value.trim();
  if (ISO_DAY.test(text)) return day(new Date(`${text}T00:00:00Z`));
  if (ISO_MOMENT.test(text)) {
    const d = new Date(/(Z|UTC|[+-]\d{2}:?\d{2})$/.test(text) ? text.replace(' UTC', 'Z').replace(' ', 'T') : `${text.replace(' ', 'T')}Z`);
    if (!Number.isNaN(d.getTime())) {
      return d.getUTCHours() === 0 && d.getUTCMinutes() === 0 ? day(d) : `${day(d)}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
    }
  }
  if (field === 'status' || field === 'statusNative') return STATUS[text.toLowerCase()] ?? text;
  const parsed = plain(text);
  return parsed === text ? text : say(parsed) || text;
}
