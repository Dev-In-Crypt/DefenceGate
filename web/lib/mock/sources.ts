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
  return { generatedAt, sources };
}
