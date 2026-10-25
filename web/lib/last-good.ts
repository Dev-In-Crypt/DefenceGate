/**
 * The last good answer of a list or a counter, for the moment the data service does not answer (UX walk-throughs of
 * 16 October 2026: the home page rendered "–" and "No tenders to show right now" during a slow minute, and a
 * visitor read that as an empty market).
 *
 * Two layers, both best effort and neither ever a reason to fail: the process memory (a bounded LRU), and, for the
 * few answers worth keeping across a restart (the default lists and counters), a small JSON file in the temp
 * directory of the web container. A value is returned with the time it was received, so the page can say "as of".
 * Pure of Next.js: lib/last-good.check.ts runs it on its own.
 */
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const MEMORY_ENTRIES = 300;
/** A file older than this is not offered: a day-old list is worse than an honest error. */
export const MAX_STALE_MS = 6 * 3_600_000;
const FILE_MAX_BYTES = 2_000_000;

interface Kept { at: string; value: unknown }
const memory = new Map<string, Kept>();

function dir(): string {
  return process.env.DG_LAST_GOOD_DIR || join(tmpdir(), 'dg-last-good');
}
let buildId: string | undefined;
/**
 * WP-128: a copy on disk belongs to the build that wrote it and the data service it read (DG_API_URL, or the demo data). A copy of
 * another build or service (an older deploy's feed page, a second server of the same machine on another API: the e2e run's
 * fake-API site) is another file, never offered: served as a stale page it gave /changes.atom one body and ETag on the first
 * request and another on the next, so a reader holding the first never got its 304.
 */
export function storeScope(): string {
  if (buildId === undefined) {
    try { buildId = readFileSync(join(process.cwd(), '.next', 'BUILD_ID'), 'utf8').trim(); } catch { buildId = ''; }
  }
  return `${buildId}|${process.env.DG_API_URL || 'demo'}`;
}
function file(key: string): string {
  return join(dir(), `${createHash('sha256').update(`${storeScope()}\n${key}`).digest('hex').slice(0, 40)}.json`);
}

/** Keep a good answer. `persist`: also write it to disk (default lists and counters only). */
export async function remember(key: string, value: unknown, opts: { persist?: boolean; at?: Date } = {}): Promise<void> {
  const kept: Kept = { at: (opts.at ?? new Date()).toISOString(), value };
  memory.delete(key);
  memory.set(key, kept);
  if (memory.size > MEMORY_ENTRIES) memory.delete(memory.keys().next().value as string);
  if (!opts.persist) return;
  try {
    const text = JSON.stringify(kept);
    if (text.length > FILE_MAX_BYTES) return;
    await mkdir(dir(), { recursive: true });
    const target = file(key);
    await writeFile(`${target}.tmp`, text);
    await rename(`${target}.tmp`, target);
  } catch {
    /* a read-only container or a full disk: the memory copy still serves */
  }
}

/** The last good answer for the key and when it was received, or null. */
export async function recall<T>(key: string, nowMs: number = Date.now()): Promise<{ value: T; at: string } | null> {
  const fresh = (k: Kept) => nowMs - new Date(k.at).getTime() <= MAX_STALE_MS;
  const held = memory.get(key);
  if (held && fresh(held)) return { value: held.value as T, at: held.at };
  try {
    const kept = JSON.parse(await readFile(file(key), 'utf8')) as Kept;
    if (kept && typeof kept.at === 'string' && fresh(kept)) {
      memory.set(key, kept);
      return { value: kept.value as T, at: kept.at };
    }
  } catch {
    /* no file, or not readable */
  }
  return null;
}

/** Forget everything in memory (tests). */
export function resetLastGood(): void {
  memory.clear();
}
