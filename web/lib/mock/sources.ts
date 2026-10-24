import raw from './sources.json';
import type { Health, SourceHealth } from '../types';

export const sources = raw as unknown as SourceHealth[];

export function sourceById(id: string): SourceHealth {
  const s = sources.find((x) => x.id === id);
  if (!s) throw new Error(`Unknown source: ${id}`);
  return s;
}

export function health(): Health {
  const generatedAt = sources.flatMap((s) => (s.lastRunAt ? [s.lastRunAt] : [])).sort().at(-1) ?? new Date().toISOString();
  // WP-114: one data check in alert, so the demo build shows where /data says it
  const alerts = [{ control: 'placsp_links', since: '2026-10-11T07:10:00Z', checkedAt: generatedAt,
    message: 'Spanish data check in alert: PLACSP notices without a publication date or TED notices of Spain not linked to their PLACSP copy are above their limit.' }];
  return { generatedAt, sources, alerts };
}
