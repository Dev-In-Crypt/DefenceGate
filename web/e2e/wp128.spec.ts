import { expect, test } from '@playwright/test';

/**
 * WP-128: the tag and the row tint are named once in app/globals.css (.tag, .tag-programme, .tag-neutral, .row-hover) instead of spelt
 * out on every row (the calendar month was 323 KB against its 300 KB budget, e2e/wp52b-api.spec.ts T9). The look is the same on screen
 * and in print (e2e/wp118.spec.ts covers the row tint); these read a real tag of the calendar.
 */
test('a calendar tag looks as before on screen and still prints dark on white with a border', async ({ page }) => {
  await page.goto('/calendar');
  await page.waitForLoadState('networkidle');
  const read = () => page.evaluate(() => {
    const style = (e: Element | null) => {
      if (!e) return null;
      const s = getComputedStyle(e);
      return { display: s.display, padding: s.padding, size: s.fontSize, weight: s.fontWeight, family: s.fontFamily, color: s.color, bg: s.backgroundColor, border: s.borderTopWidth, radius: s.borderTopLeftRadius, wrap: s.whiteSpace };
    };
    const probe = document.createElement('span');
    probe.className = 'bg-primary text-on-primary font-mono';
    document.body.append(probe);
    const out = { programme: style(document.querySelector('main li .tag-programme')), neutral: style(document.querySelector('main li .tag-neutral')), probe: style(probe) };
    probe.remove();
    return out;
  });
  const screen = await read();
  for (const t of [screen.programme, screen.neutral]) {
    expect(t).not.toBeNull();
    // inline-flex, read as flex: the tag is an item of the row's flex line, which blockifies it (as it did before)
    expect(t).toMatchObject({ display: 'flex', padding: '5px 10px', size: '12px', wrap: 'nowrap' });
    expect(parseFloat(t!.radius)).toBeGreaterThan(100);                      // the pill
  }
  expect(screen.programme).toMatchObject({ weight: '500', family: screen.probe!.family, bg: screen.probe!.bg, color: screen.probe!.color });
  expect(screen.neutral!.weight).toBe('700');
  expect(screen.neutral!.family).not.toBe(screen.probe!.family);
  await page.emulateMedia({ media: 'print' });
  const print = (await read()).programme!;
  const light = (c: string) => (c.match(/\d+/g) ?? []).slice(0, 3).map(Number).every((v) => v > 200);
  expect(light(print.color), `text ${print.color}`).toBe(false);
  expect(parseFloat(print.border), 'a border says what the background no longer does').toBeGreaterThanOrEqual(1);
});
