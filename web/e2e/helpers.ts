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
/** WP-88: open every collapsed About this data / How we count of the page, so a test can read what is in it. */
export async function openAbout(page: Page): Promise<void> {
  await page.evaluate(() => document.querySelectorAll<HTMLDetailsElement>('main [data-about] details').forEach((d) => { d.open = true; }));
}

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
 * Since WP-83 a running paragraph also fills its block (see `paragraphsNarrowerThanBlock`). Returns the visible paragraphs that break it. `skip` leaves out paragraphs inside those selectors, `minLength` short ones.
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

/** The widths `paragraphsNarrowerThanBlock` is checked at (WP-83): a wide desktop and a small laptop. */
export const BLOCK_WIDTHS = [1440, 1024];

/**
 * The full-width rule (WP-83, owner's decision of 22 Oct 2026, "text across the full width of the block"; it replaces the 62ch measure
 * of WP-62, 21 Oct): a running paragraph of `main` (more than `minLength` characters, default 200) is at least `ratio` (default 0.9) as
 * wide as the content box of its block. The block is the nearest card body, padded box, grid or flex-row column, or `main`; a wrapper with a
 * max-width of its own (anything but none or 100 %) is never the block, so a cap on a wrapper is caught as well as one on the paragraph.
 * Returns the paragraphs that break it, with their width and the block's.
 */
export function paragraphsNarrowerThanBlock(page: Page, opts: { skip?: string; minLength?: number; ratio?: number } = {}) {
  return page.evaluate(({ skip, minLength, ratio }) => {
    const isBlock = (e: Element) => {
      if (e.tagName === 'MAIN' || e.classList.contains('card-body')) return true;
      const es = getComputedStyle(e);
      if (!['none', '100%'].includes(es.maxWidth)) return false;
      if (parseFloat(es.paddingLeft) + parseFloat(es.paddingRight) > 0) return true;
      const ps = e.parentElement && getComputedStyle(e.parentElement);
      return !!ps && (ps.display.includes('grid') || (ps.display.includes('flex') && ps.flexDirection.startsWith('row')));
    };
    const out: { p: number; block: number; t: string }[] = [];
    for (const p of document.querySelectorAll('main p')) {
      if (p.getClientRects().length === 0 || (skip && p.closest(skip)) || (p.textContent ?? '').trim().length <= minLength) continue;
      let b = p.parentElement!;
      while (!isBlock(b)) b = b.parentElement!;
      const s = getComputedStyle(b);
      const inner = b.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight);
      const w = p.getBoundingClientRect().width;
      if (w < ratio * inner) out.push({ p: Math.round(w), block: Math.round(inner), t: (p.textContent ?? '').trim().slice(0, 40) });
    }
    return out;
  }, { skip: opts.skip, minLength: opts.minLength ?? 200, ratio: opts.ratio ?? 0.9 });
}
