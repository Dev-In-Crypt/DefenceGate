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
 * The reading rule since the owner's change "text runs the full content width" (--measure is 100%, commit 77ca9c6; it was 680 px): a
 * paragraph of `main` may be as wide as the content frame, never outside the header's left and right edges (the frame equals the header).
 * Returns the visible paragraphs that break it. `skip` leaves out paragraphs inside those selectors, `minLength` short ones.
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
