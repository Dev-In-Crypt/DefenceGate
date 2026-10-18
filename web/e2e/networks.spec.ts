import { expect, test, type Page } from '@playwright/test';
import { pace, visit } from './helpers';

/**
 * The networks pages (WP-28): the organisations directory with its filters, an organisation's profile (funding table and
 * bars, partners, projects, names), a project's consortium and history, and the two analyses. The CI run has no API behind
 * it: the pages read the small invented set of web/lib/mock/networks.ts (Alpha Systems, Bravo Ingenierie, a Kyiv institute,
 * Echo Iberica; three projects), so the numbers below are those of the demo set. Locators are roles and labels.
 * The same file runs at desktop width and at 375 px.
 */

const ALPHA = '/organisations/101-alpha-systems-gmbh';

/** Below the `lg` breakpoint the filters sit behind a "Filters" button; open it so the form is reachable. */
async function openFilters(page: Page) {
  const button = page.getByRole('button', { name: /^Filters/ });
  if (await button.isVisible() && (await button.getAttribute('aria-expanded')) !== 'true') await button.click();
}

test('/organisations: the directory lists the organisations with their counts and says where the data comes from', async ({ page }) => {
  await visit(page, '/organisations', {
    title: /organisations/i, h1: 'Organisations in funded projects', text: ['Where this comes from', 'Showing 1–4 of 4 organisations'],
  });
  const cards = page.getByRole('article');
  await expect(cards).toHaveCount(4);
  // most projects first: Bravo and Alpha hold two or three projects each, Kyiv and Echo one
  await expect(cards.first().getByRole('heading', { level: 2 })).toContainText(/alpha systems|bravo/i);
  await expect(page.getByRole('link', { name: /Kyiv Institute/i })).toBeVisible();
  await expect(page.getByText(/EDF factsheets state none per participant/i).first()).toBeVisible();
  await expect(page.getByText(/Licence: Commission Decision 2011\/833\/EU/i).first()).toBeVisible();
  await expect(page.getByText(/read by a language model/i).first()).toBeVisible();
});

test('/organisations: search folds accents, and the country filter travels in the URL', async ({ page }) => {
  await visit(page, '/organisations?q=ingenierie', { title: /organisations/i, h1: 'Organisations in funded projects' });
  await expect(page.getByRole('article')).toHaveCount(1);
  await expect(page.getByRole('link', { name: /Bravo/i })).toBeVisible();

  await visit(page, '/organisations', { title: /organisations/i, h1: 'Organisations in funded projects' });
  await openFilters(page);
  await page.getByLabel('Country of the organisation').selectOption('UA');
  await page.getByRole('button', { name: 'Apply filters' }).click();
  await page.waitForURL(/country=UA/);
  await expect(page.getByRole('article')).toHaveCount(1);
  await expect(page.getByRole('link', { name: /Kyiv Institute/i })).toBeVisible();
  await pace(page);
});

test('/organisations: a filter that matches nothing says so', async ({ page }) => {
  await visit(page, '/organisations?q=nothinglikethis', { title: /organisations/i, h1: 'Organisations in funded projects' });
  await expect(page.getByText('No organisations match these filters')).toBeVisible();
});

test('an organisation profile: facts, how it was recognised, and its sections', async ({ page }) => {
  await visit(page, ALPHA, { title: /Alpha Systems/i, h1: /Alpha Systems/i, text: ['How we recognised this organisation', 'By programme'] });
  await expect(page.getByText('As coordinator', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('999000001')).toBeVisible();
  await expect(page.getByText(/matched by its PIC/i).first()).toBeVisible();
  const sections = page.getByRole('navigation', { name: 'Sections of this profile' });
  for (const name of ['Overview', 'Funding', 'Partners', 'Projects', 'Names']) await expect(sections.getByRole('link', { name })).toBeVisible();
  await expect(sections.getByRole('link', { name: 'Overview' })).toHaveAttribute('aria-current', 'page');
});

test('the funding section draws bars and gives the same figures as a table', async ({ page }) => {
  await visit(page, `${ALPHA}?tab=funding`, { title: /Alpha Systems/i, h1: /Alpha Systems/i, text: ['Funding by programme and year'] });
  const h2020 = page.getByRole('table', { name: /Horizon 2020: projects and EU contribution per year/i });
  await expect(h2020).toBeVisible();
  await expect(h2020.getByRole('row', { name: /2019/ })).toContainText('EUR 400,000');
  // EDF states no amount per participant: the table says so and its bars are projects
  const edf = page.getByRole('table', { name: /European Defence Fund: projects and EU contribution per year/i });
  await expect(edf.getByRole('row', { name: /2024/ })).toContainText('Not stated');
  await expect(page.getByText(/states no amount per participant, so the bars show projects/i)).toBeVisible();
});

test('the partners section ranks partners by shared projects and links to their projects', async ({ page }) => {
  await visit(page, `${ALPHA}?tab=partners`, { title: /Alpha Systems/i, h1: /Alpha Systems/i, text: ['Partners'] });
  const table = page.getByRole('table', { name: /Partners, most shared projects first/i });
  const rows = table.getByRole('row');
  await expect(rows.nth(1)).toContainText(/Bravo/i);
  await expect(rows.nth(1)).toContainText('3');
  await expect(table.getByRole('link', { name: 'CHARLIE' }).first()).toBeVisible();
  // the country filter keeps what matches
  await visit(page, `${ALPHA}?tab=partners&country=UA`, { title: /Alpha Systems/i, h1: /Alpha Systems/i });
  await expect(page.getByRole('table', { name: /Partners/i }).getByRole('row')).toHaveCount(2);
  await expect(page.getByRole('link', { name: /Kyiv Institute/i })).toBeVisible();
});

test('the projects section leads to a project page with its consortium', async ({ page }) => {
  await visit(page, `${ALPHA}?tab=projects`, { title: /Alpha Systems/i, h1: /Alpha Systems/i });
  const table = page.getByRole('table', { name: /Projects, newest first/i });
  await expect(table.getByRole('row')).toHaveCount(4);
  await table.getByRole('link', { name: 'ALPHA' }).click();
  await page.waitForURL(/\/projects\/201-alpha/);
  await expect(page.locator('h1').first()).toHaveText('ALPHA');
  const members = page.getByRole('table', { name: /Members of the consortium/i });
  await expect(members.getByRole('row')).toHaveCount(4);          // header and three members
  await expect(members.getByRole('row').nth(1)).toContainText('Coordinator');
  await expect(members.getByRole('link', { name: /Kyiv Institute/i })).toBeVisible();
  await pace(page);
});

test('a project page: facts, consortium, history and the source', async ({ page }) => {
  await visit(page, '/projects/201-alpha', { title: /ALPHA/, h1: 'ALPHA', text: ['Consortium', 'Changes of the consortium', 'Where this comes from'] });
  await expect(page.getByText(/Coordinated by/i)).toContainText(/Alpha Systems/i);
  await expect(page.getByText(/First seen on/i)).toBeVisible();
  await expect(page.getByRole('link', { name: /Project page on CORDIS/i })).toHaveAttribute('href', /cordis\.europa\.eu\/project\/id\//);
  await expect(page.getByText('How the participants were read')).toHaveCount(0);   // a CORDIS project was not read by a model
});

test('an EDF project says its participants were read by a model and what the checks removed', async ({ page }) => {
  await visit(page, '/projects/203-charlie', { title: /CHARLIE/, h1: 'CHARLIE', text: ['How the participants were read'] });
  await expect(page.getByText(/read from the factsheet by a language model/i).first()).toBeVisible();
  await expect(page.getByText(/names the model returned that are not in the factsheet text/i)).toBeVisible();
  await expect(page.getByRole('link', { name: /EDF project factsheet/i })).toBeVisible();
  await expect(page.getByText(/factsheet states no amount per participant/i).first()).toBeVisible();
});

test('the Ukraine partners analysis names the coordinator and the Ukrainian participant, and states its definition', async ({ page }) => {
  await visit(page, '/networks/ukraine-partners', { title: /Ukrainian organisations/i, h1: 'Who partners with Ukrainian organisations', text: ['What this counts', 'Limits'] });
  await expect(page.getByText(/country of establishment, as the source states it, is Ukraine/i)).toBeVisible();
  const table = page.getByRole('table', { name: /Coordinators with a Ukrainian participant/i });
  await expect(table.getByRole('link', { name: /Alpha Systems/i })).toBeVisible();
  await expect(table.getByRole('link', { name: /Kyiv Institute/i })).toBeVisible();
});

test('the consortium gaps analysis defines its area and category, and lists repeat participants', async ({ page }) => {
  await visit(page, '/networks/consortium-gaps?topic=CYBER&lacking=UA', { title: /Repeat participants/i, h1: 'Gaps in consortia', text: ['What this counts', 'Limits'] });
  await expect(page.getByText(/Capability area:/i)).toBeVisible();
  await expect(page.getByRole('table', { name: /Organisations funded repeatedly/i }).getByRole('link', { name: /Bravo/i })).toBeVisible();
  await expect(page.getByText(/read by a language model/i).first()).toBeVisible();
});

test('an unknown organisation or project is a 404 and a made-up address never reaches the API', async ({ request }) => {
  for (const path of ['/organisations/999-nothing', '/organisations/not-a-slug', '/projects/999-nothing', '/projects/x']) {
    expect((await request.get(path)).status(), path).toBe(404);
  }
});

test('the sitemap lists the directory and the analyses', async ({ request }) => {
  const xml = await (await request.get('/sitemap.xml')).text();
  for (const path of ['/organisations', '/networks/ukraine-partners', '/organisations/101-alpha-systems-gmbh']) expect(xml).toContain(path);
});
