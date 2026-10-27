import { expect, test, type Locator } from '@playwright/test';
import { openAbout, visit } from './helpers';
import { WHAT_IS_SENT } from '../lib/sent-copy';
import { SUPPLIER_QUESTIONS } from '../lib/question-counts';
import sources from '../lib/mock/sources.json';
import regulation from '../lib/mock/regulation.json';

/**
 * WP-131 (round-7 legal-content audit, 25 October 2026): the texts that said what was not true. Against the demo build (DG_USE_MOCK=1):
 * the mock sources hold a refused e-Zamówienia run (partial, 0 records, stale by the daily rule), a failed run that is the newest of all,
 * and the German federal notice service with its first publication date.
 */
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const day = (iso: string) => `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}`;
const stamp = (iso: string) => `${day(iso)}, ${iso.slice(11, 16)} UTC`;
type Src = { id: string; type: string; status: string; records: number; lastRunAt: string | null; heldFrom?: string };
const SOURCES = sources as Src[];

test('1: what leaves the browser is said in the words made from the request builders, on the three pages that say it', async ({ page }) => {
  for (const [path, h1] of [['/readiness', 'Readiness check'], ['/readiness/supplier', 'Supplier profile'], ['/readiness/spain-automotive', /Spain/]] as const) {
    await visit(page, path, { title: /./, h1 });
    await openAbout(page);
    const said = page.locator('main [data-what-is-sent]');
    await expect(said).toContainText(WHAT_IS_SENT);
    await expect(said).toContainText('the staff count of your organisation and, for a group, of the whole group');
    await expect(said).toContainText('the seven countries of the map');
    await expect(page.locator('main')).not.toContainText(/name and size you may enter below are never sent|those codes alone|CPV codes and nothing else/);
  }
});

test('2: pricing says "Opens with sign-in" where /alerts says built, and the free consortium gaps are not "Coming"', async ({ page }) => {
  await visit(page, '/pricing', { title: /Pricing/, h1: 'Pricing' });
  const signin = await page.locator('main li:has(> [data-signin])').evaluateAll((els) => els.map((e) => e.firstChild?.textContent?.trim()));
  expect(signin).toEqual(['Saved searches', 'E-mail alerts']);
  await expect(page.locator('main [data-signin]').first()).toHaveText('Opens with sign-in');
  const gaps = page.locator('main li', { hasText: /^Consortium gap analysis/ });
  await expect(gaps).toContainText('free on the site today');
  await expect(gaps.locator('[data-coming]')).toHaveCount(0);
  await expect(page.locator('main')).not.toContainText('your answers stay in your browser');
  await visit(page, '/alerts', { title: /Alerts/, h1: 'Alerts and saved searches', text: ['Saved searches and e-mail alerts are built'] });
  await visit(page, '/networks/consortium-gaps', { title: /./, h1: /./ });
});

test('3: the trust line counts tender and funding sources apart, and "Last update" is the newest run that brought data', async ({ page }) => {
  const tenders = SOURCES.filter((s) => s.type === 'tenders').length;
  const grants = SOURCES.filter((s) => s.type === 'grants').length;
  const brought = SOURCES.filter((s) => s.status !== 'failed' && s.status !== 'never' && s.records > 0 && s.lastRunAt).map((s) => s.lastRunAt!).sort().at(-1)!;
  const newest = SOURCES.map((s) => s.lastRunAt).filter((t): t is string => Boolean(t)).sort().at(-1)!;
  expect(newest, 'the fixture: the newest run is a failed one').not.toBe(brought);
  await visit(page, '/', { title: /DefenceGate/, h1: 'Win, partner, qualify.' });
  const trust = page.getByRole('region', { name: 'About the data' });
  await expect(trust.locator('[data-trust="sources"]')).toHaveText(`${tenders} tender and ${grants} funding sources`);
  await expect(trust.locator('[data-trust="update"]')).toHaveText(`Last update ${stamp(brought)}`);
  await expect(page.locator('footer')).toContainText(`Last run that brought data (any source) ${stamp(brought)}`);
  await expect(page.locator('body')).not.toContainText(stamp(newest));
});

/** The questions a form shows now: each group (a fieldset) once, and each field outside a group (as e2e/wp121.spec.ts counts). */
const countQuestions = (form: Locator) => form.evaluate((f) => {
  const seen = (e: Element) => (e as HTMLElement).offsetParent !== null || getComputedStyle(e).position === 'fixed';
  const groups = [...f.querySelectorAll('fieldset')].filter((g) => seen(g) && !g.parentElement?.closest('fieldset'));
  const fields = [...f.querySelectorAll('select, input:not([type=hidden]):not([type=radio]):not([type=checkbox]), textarea')]
    .filter((e) => seen(e) && !e.closest('fieldset'));
  return groups.length + fields.length;
});

/** Every follow-up opened: each radio group in turn set to the choice that shows the most questions, until nothing grows. */
const openEverything = (form: Locator) => form.evaluate(async (f) => {
  const tick = () => new Promise((r) => setTimeout(r, 0));
  const seen = (e: Element) => (e as HTMLElement).offsetParent !== null;
  const count = () => {
    const groups = [...f.querySelectorAll('fieldset')].filter((g) => seen(g) && !g.parentElement?.closest('fieldset'));
    const fields = [...f.querySelectorAll('select, input:not([type=hidden]):not([type=radio]):not([type=checkbox]), textarea')].filter((e) => seen(e) && !e.closest('fieldset'));
    return groups.length + fields.length;
  };
  let best = count();
  for (let pass = 0; pass < 6; pass += 1) {
    const before = best;
    const names = [...new Set([...f.querySelectorAll<HTMLInputElement>('input[type=radio]')].filter(seen).map((r) => r.name))];
    for (const name of names) {
      const radios = () => [...f.querySelectorAll<HTMLInputElement>(`input[type=radio][name="${name}"]`)].filter(seen);
      let most = -1;
      let pick = -1;
      for (let i = 0; i < radios().length; i += 1) {
        radios()[i].click(); await tick();
        const n = count();
        if (n > most) { most = n; pick = i; }
      }
      if (pick >= 0 && radios()[pick]) { radios()[pick].click(); await tick(); }
      best = Math.max(best, count());
    }
    if (best === before) break;
  }
  return best;
});

test('4: the supplier profile asks the range the pages print, counted on every route of the form', async ({ page }) => {
  test.skip((page.viewportSize()?.width ?? 1280) < 700, 'counted once, on the desktop project');
  test.setTimeout(240_000);
  let min = Infinity;
  let max = 0;
  for (const path of ['/readiness/supplier', '/readiness/supplier?offer=services']) {
    await visit(page, path, { title: /supplier/i, h1: /supplier/i });
    const form = page.locator('main form').first();
    const select = page.getByLabel('Country where your company is established');
    const codes = await select.locator('option').evaluateAll((os) => os.map((o) => (o as HTMLOptionElement).value).filter(Boolean));
    expect(codes.length).toBeGreaterThan(30);
    for (const code of codes) {
      await select.selectOption(code);
      const n = await countQuestions(form);
      min = Math.min(min, n);
      max = Math.max(max, n);
    }
  }
  // the longest routes: every follow-up opened, in each country whose own rules add questions, and one outside the EU
  for (const code of ['ES', 'DE', 'PL', 'UA', 'US']) {
    await page.evaluate(() => localStorage.clear());
    await visit(page, '/readiness/supplier', { title: /supplier/i, h1: /supplier/i });
    await page.getByLabel('Country where your company is established').selectOption(code);
    max = Math.max(max, await openEverything(page.locator('main form').first()));
  }
  expect({ min, max }, 'lib/question-counts.ts SUPPLIER_QUESTIONS').toEqual(SUPPLIER_QUESTIONS);
  // WP-150: the home tile no longer describes the routes (one line, its figure, one action); /check and /readiness say the range
  await visit(page, '/check', { title: /Check my company/, h1: 'Check my company', text: [`one page of ${min} to ${max} questions`] });
  await visit(page, '/readiness', { title: /readiness/i, h1: /readiness/i, text: [`(one page, ${min} to ${max} questions)`] });
});

test('5: the change feed says how many entries it holds, funding entries included', async ({ page }) => {
  const xml = await (await page.request.get('/changes.atom')).text();
  const entries = [...xml.matchAll(/<entry>[\s\S]*?<\/entry>/g)].map((m) => m[0]);
  const funding = entries.filter((e) => /<category term="call-/.test(e)).length;
  const subtitle = /<subtitle>([^<]*)<\/subtitle>/.exec(xml)?.[1] ?? '';
  const held = /holds the newest ([\d,]+) of/.exec(subtitle)?.[1];
  if (held) expect(entries.length - funding, 'notice changes on the page').toBe(Number(held.replace(/,/g, '')));
  if (funding > 0) expect(subtitle).toContain(`It also carries ${funding} funding-call ${funding === 1 ? 'entry' : 'entries'}.`);
  else expect(subtitle).not.toContain('funding-call entr');
  await visit(page, '/data', { title: /Source status/, h1: 'Source status' });
  await expect(page.locator('main')).not.toContainText('It holds the newest 400 changes');
  await expect(page.locator('main')).toContainText('the unfiltered feed also carries the new funding calls and moved funding dates on top of them');
});

test('6: the German start date is the one the data holds, on /data and /methodology', async ({ page }) => {
  const from = day(SOURCES.find((s) => s.id === 'de_bkms')!.heldFrom!);
  await visit(page, '/data', { title: /Source status/, h1: 'Source status' });
  const card = page.locator('article', { has: page.getByRole('heading', { name: /Bekanntmachungsservice/ }) });
  await expect(card).toContainText(`${from} to`);
  await expect(page.locator('main')).toContainText(`What we hold of it starts on ${from}`);
  await visit(page, '/methodology', { title: /collects and classifies/, h1: 'Methodology' });
  await expect(page.locator('main')).toContainText(`For Germany that is the federal notice service, from ${from}.`);
  // the eForms date of TED's older format stays on /methodology (a fact about TED); the German start date is not written by hand
  expect(await (await page.request.get('/data')).text()).not.toContain('25 October 2023');
  await expect(page.locator('main')).not.toContainText('federal notice service, from 25 October 2023');
});

test('7: the tracker links the entry it means, and says when the sources were checked', async ({ page }) => {
  await visit(page, '/regulation', { title: /Regulatory tracker/, h1: 'Regulatory tracker' });
  const entry = page.locator('li#edf-ukraine-legal-basis');
  await expect(entry).not.toContainText('(next entry)');
  await expect(entry).toContainText('see the entry on Ukraine');
  const link = entry.getByRole('link', { name: /Ukraine's EDF association, not confirmed in force/ });
  await expect(link).toHaveAttribute('href', '/regulation#edf-ukraine-in-force-unconfirmed');
  await expect(page.locator('li#edf-ukraine-in-force-unconfirmed')).toHaveCount(1);
  const days = [...new Set((regulation as { entries: { checkedOn: string }[] }).entries.map((e) => e.checkedOn))].sort();
  await expect(page.locator('[data-checked-line]')).toHaveText(days.length === 1
    ? `Newest event first. Every entry’s source was last checked on ${day(days[0])}, none since.`
    : `Newest event first. The entries’ sources were last checked between ${day(days[0])} and ${day(days.at(-1)!)}; each entry gives its own date.`);
});

test('8: a refused source shows one status with one reason, and the glossary says what /data says', async ({ page }) => {
  await visit(page, '/data', { title: /Source status/, h1: 'Source status' });
  const card = page.locator('article', { has: page.getByRole('heading', { name: 'e-Zamówienia', exact: true }) });
  await expect(card.getByText('Stale', { exact: true })).toBeVisible();
  await expect(card).not.toContainText(/Partial|partial/);
  await expect(card).not.toContainText(/last ran 0 days ago/);
  await expect(card).toContainText('Stale: no run of the last day fetched anything');
  await expect(card).toContainText('Why it is stale: The source refuses access (HTTP 403)');
  await openAbout(page);
  const rules = await page.locator('main').innerText();
  await visit(page, '/glossary', { title: /glossary/i, h1: /glossary/i });
  const entry = page.locator('div#source-status');
  const text = (await entry.innerText()).toLowerCase();
  for (const kind of ['ok', 'stale', 'partial', 'failed', 'never run', 'one-off load']) expect(text, kind).toContain(kind);
  for (const phrase of ['whose every run of the last day fetched nothing', 'a run that finished with a problem is partial', 'also when it fetched the minimum']) {
    expect(text, `glossary: ${phrase}`).toContain(phrase);
    expect(rules.toLowerCase(), `/data: ${phrase}`).toContain(phrase);
  }
  expect(text).not.toContain('partial means the run fetched less than we expected');
});

test('9: where the data runs names the fact sheets and the one dump that stays', async ({ page }) => {
  await visit(page, '/data/sovereignty', { title: /Where the data runs/, h1: 'Where the data runs' });
  const main = page.locator('main');
  await expect(main).toContainText('the text of public EDF project fact sheets');
  await expect(main).toContainText('a full dump of 16 September 2026');
  await expect(main).toContainText('stays on the server until the operator deletes it');
});
