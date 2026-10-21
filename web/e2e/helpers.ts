import { expect, type Page, type Response } from '@playwright/test';

/** A pause after a page, so a run against a real site is at human speed. */
const PACE_MS = Number(process.env.E2E_PACE_MS ?? 700);
export const pace = (page: Page) => (PACE_MS > 0 ? page.waitForTimeout(PACE_MS) : Promise.resolve());

/** Anything that looks like an e-mail address. Applied to the document without its scripts. */
export const EMAIL = /[A-Z0-9._%+-]+@[A-Z0-9-]+(?:\.[A-Z0-9-]+)*\.[A-Z]{2,}/i;

/** Console errors and uncaught page errors seen while a page loads. */
export function watchErrors(page: Page): string[] {
  const seen: string[] = [];
  page.on('console', (m) => { if (m.type() === 'error') seen.push(`console: ${m.text()}`); });
  page.on('pageerror', (e) => seen.push(`page error: ${e.message}`));
  return seen;
}

export interface Expect {
  /** The document title must match. */
  title: RegExp;
  /** Text the page's h1 must contain. */
  h1: string | RegExp;
  /** Other key text that must be visible. */
  text?: (string | RegExp)[];
  /** The status of the response; 200 unless a test says otherwise. */
  status?: number;
}

/**
 * Open a page and check what every page must do: the status, no console error, the title, the headline and key
 * text, no horizontal scroll (the check that matters at 375 px, kept at every width), and no e-mail address in the
 * document.
 */
export async function visit(page: Page, path: string, want: Expect): Promise<Response> {
  const errors = watchErrors(page);
  const response = await page.goto(path, { waitUntil: 'load' });
  expect(response, `${path} gave no response`).not.toBeNull();
  expect(response!.status(), `${path} status`).toBe(want.status ?? 200);
  await expect(page).toHaveTitle(want.title);
  await expect(page.locator('h1').first()).toContainText(want.h1);
  for (const t of want.text ?? []) await expect(page.getByText(t).first()).toBeVisible();

  const overflow = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(overflow.scroll, `${path}: horizontal scroll (${overflow.scroll} px in ${overflow.client} px)`).toBeLessThanOrEqual(overflow.client);

  const html = await page.evaluate(() => {
    const clone = document.documentElement.cloneNode(true) as HTMLElement;
    clone.querySelectorAll('script, style, template').forEach((n) => n.remove());
    return clone.outerHTML;
  });
  expect(html.match(EMAIL)?.[0] ?? null, `${path}: an e-mail address is in the page`).toBeNull();

  // The browser itself logs the failed status of a page that is expected to answer 404.
  const unexpected = errors.filter((e) => !(want.status && want.status !== 200 && e.includes(`status of ${want.status}`)));
  expect(unexpected, `${path}: console or page errors`).toEqual([]);
  await pace(page);
  return response!;
}

/**
 * The frame rule: a paragraph of `main` never leaves the content frame, the header's left and right edges (the frame equals the header).
 * Since WP-62 the paragraph itself is also capped by the reading measure (62ch, see `paragraphsOverMeasure`); the frame still keeps the
 * header width. Returns the visible paragraphs that break it. `skip` leaves out paragraphs inside those selectors, `minLength` short ones.
 */
export function paragraphsOutsideFrame(page: Page, opts: { skip?: string; minLength?: number } = {}) {
  return page.evaluate(({ skip, minLength }) => {
    const h = document.querySelector('header')!.getBoundingClientRect();
    return [...document.querySelectorAll('main p')]
      .filter((p) => p.getClientRects().length > 0 && !(skip && p.closest(skip)) && (p.textContent ?? '').length >= minLength)
      .map((p) => ({ left: p.getBoundingClientRect().left, right: p.getBoundingClientRect().right, t: (p.textContent ?? '').trim().slice(0, 30) }))
      .filter((p) => p.left < h.left - 1 || p.right > h.right + 1);
  }, { skip: opts.skip, minLength: opts.minLength ?? 0 });
}

/**
 * The reading measure (WP-62, owner's decision of 21 Oct 2026): a running paragraph of `main` holds at most `max` characters on any line
 * but its last (default 95: the 62ch measure gives 70 to 90 in Manrope, a line of short words a few more). It counts the characters of each
 * rendered line (word boxes on the same top), not the box width. Paragraphs under 120 characters are left out. Returns the paragraphs that
 * break it, with their widest line.
 */
export function paragraphsOverMeasure(page: Page, opts: { skip?: string; max?: number } = {}) {
  return page.evaluate(({ skip, max }) => {
    const range = document.createRange();
    const out: { chars: number; t: string }[] = [];
    for (const p of document.querySelectorAll('main p')) {
      if (p.getClientRects().length === 0 || (skip && p.closest(skip)) || (p.textContent ?? '').length < 120) continue;
      const lines: number[] = [];
      let top = -1e9;
      const walker = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        for (const m of (n.nodeValue ?? '').matchAll(/\S+/g)) {
          range.setStart(n, m.index!);
          range.setEnd(n, m.index! + m[0].length);
          // A word that wraps (a URL broken by overflow-wrap, a hyphenated word) has a box on each line: its characters are shared
          // between those lines by width.
          const rects = [...range.getClientRects()].filter((r) => r.width > 0);
          const total = rects.reduce((s, r) => s + r.width, 0);
          for (const r of rects) {
            const chars = Math.round((m[0].length * r.width) / total);
            if (r.top > top + 6) { lines.push(chars); top = r.top; } else lines[lines.length - 1] += chars + 1;
          }
        }
      }
      const widest = Math.max(0, ...lines.slice(0, -1));
      if (widest > max) out.push({ chars: widest, t: (p.textContent ?? '').trim().slice(0, 40) });
    }
    return out;
  }, { skip: opts.skip, max: opts.max ?? 95 });
}
