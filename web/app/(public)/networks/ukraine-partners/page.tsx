import type { Metadata } from 'next';
import Link from 'next/link';
import { getUkrainePartners } from '@/lib/networks-api';
import { buildMetadata } from '@/lib/seo';
import { DEFENCE_PROGRAMMES, DEFENCE_PROGRAMMES_WORDS, PROGRAMME_WORD, yearsLabel } from '@/lib/networks';
import { ContentPage, ContentSection } from '@/components/dg/content-page';
import { AboutData } from '@/components/dg/about-data';
import { CountryNote, DataSources, OrgLink, TableBox } from '@/components/networks/parts';
import type { SearchParams } from '@/lib/filters';

export const revalidate = 900;
type Props = { searchParams: Promise<SearchParams> };

const DEFAULT_SINCE = 2021;
function sinceOf(sp: SearchParams): number {
  const raw = Array.isArray(sp.since) ? sp.since[0] : sp.since;
  const n = Number(raw);
  return Number.isInteger(n) && n >= 2007 && n <= 2100 ? n : DEFAULT_SINCE;
}

/** `programme=all` switches the defence-relevant default off; any other list is passed on. */
function programmesOf(sp: SearchParams): { codes: string[]; all: boolean } {
  const raw = (Array.isArray(sp.programme) ? sp.programme[0] : sp.programme) ?? '';
  const codes = raw.split(',').map((c) => c.trim().toUpperCase()).filter((c) => /^[A-Z0-9_-]{1,20}$/.test(c)).slice(0, 10);
  if (codes.includes('ALL')) return { codes: [], all: true };
  return { codes: codes.length ? codes : DEFENCE_PROGRAMMES, all: false };
}

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const sp = await searchParams;
  return buildMetadata({
    title: 'Who partners with Ukrainian organisations',
    description: 'Coordinators of EU-funded defence and research projects with a participant established in Ukraine, with the Ukrainian organisations and projects as evidence.',
    path: '/networks/ukraine-partners',
    noindex: sinceOf(sp) !== DEFAULT_SINCE || programmesOf(sp).all || Boolean(sp.programme),
  });
}

export default async function UkrainePartnersPage({ searchParams }: Props) {
  const sp = await searchParams;
  const since = sinceOf(sp);
  const chosen = programmesOf(sp);
  let { codes, all } = chosen;
  // A failure is thrown, not drawn here: the page then answers 503 at the edge, not 200 (re-audit N2), and ../error.tsx says so.
  let data = await getUkrainePartners(since, codes);
  // The defence-programme default can be empty (no EDF, EDIDP or PADR project has a Ukrainian participant yet) while the other
  // programmes hold hundreds: open on those, with a line that says so, instead of an empty headline view. A programme the visitor
  // chose stays as chosen.
  let fellBack = false;
  if (!sp.programme && data.totals.projects === 0 && data.byProgramme?.some((b) => b.projects > 0)) {
    try {
      const wide = await getUkrainePartners(since, []);
      if (wide.totals.projects > 0) { data = wide; codes = []; all = true; fellBack = true; }
    } catch { /* keep the empty defence view and its link to all programmes */ }
  }
  const others = (data.byProgramme ?? []).filter((b) => !codes.includes(b.code));
  const base = `/networks/ukraine-partners?since=${since}`;
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Organisations', href: '/organisations' }, { label: 'Partners of Ukrainian organisations', href: '/networks/ukraine-partners' }]}
      title="Ukraine partners"
      lead="Organisations that led an EU-funded project with a Ukrainian participant: primes that already work with Ukrainian companies, and consortia to join."
      wide
    >
        <>
          <form method="get" action="/networks/ukraine-partners" aria-label="Choose the first year" className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-label" htmlFor="since">Projects started in or after
              <input id="since" name="since" type="number" min={2007} max={2100} defaultValue={data.since}
                className="h-11 w-32 rounded-md border-strong border-input-edge bg-surface px-4 font-mono text-body text-ink" />
            </label>
            {all && <input type="hidden" name="programme" value="all" />}
            {!all && codes.join() !== DEFENCE_PROGRAMMES.join() && <input type="hidden" name="programme" value={codes.join(',')} />}
            <button type="submit" className="inline-flex min-h-11 items-center rounded-pill border-strong border-ink bg-surface px-5 text-small font-bold text-ink">Apply</button>
          </form>
          <p role="status" className="m-0 max-w-prose rounded-lg border border-transparent bg-surface p-4 text-body">
            {all ? (
              <>{fellBack && <>No project of {DEFENCE_PROGRAMMES_WORDS} started in or after {data.since} has a Ukrainian participant. </>}Showing <strong>all programmes</strong>, including civil research from Horizon Europe, Horizon 2020 and FP7. <Link href={base} className="font-semibold">Show only {DEFENCE_PROGRAMMES_WORDS}</Link>.</>
            ) : (
              <>Showing <strong>{codes.join() === DEFENCE_PROGRAMMES.join() ? DEFENCE_PROGRAMMES_WORDS : codes.map((c) => PROGRAMME_WORD[c] ?? c).join(', ')}</strong>.
                {others.length > 0 && <> All programmes together hold {others.reduce((n, b) => n + b.projects, 0)} more {others.reduce((n, b) => n + b.projects, 0) === 1 ? 'project' : 'projects'} with a Ukrainian participant, in {others.map((b) => PROGRAMME_WORD[b.code] ?? b.code).join(', ')}. </>}
                <Link href={`${base}&programme=all`} className="font-semibold">Show all programmes</Link>.</>
            )}
          </p>
          {/* WP-88: the definition, the totals and the limits are one collapsed block; the table follows the scope line. */}
          <AboutData summary="How we count">
            <h3 className="m-0 text-h4">What this counts</h3>
            <p className="m-0">{data.definition}</p>
            <p className="m-0">
              {data.totals.projects} {data.totals.projects === 1 ? 'project' : 'projects'} since {data.since} had a Ukrainian participant; {data.totals.coordinators} {data.totals.coordinators === 1 ? 'coordinator' : 'coordinators'} led {data.totals.projects === 1 ? 'it' : 'them'}
              {data.totals.projectsCoordinatedFromUkraine > 0 ? `, and ${data.totals.projectsCoordinatedFromUkraine} were led from Ukraine` : ''}.
              {' '}{data.totals.ukrainianOrganisations} Ukrainian {data.totals.ukrainianOrganisations === 1 ? 'organisation' : 'organisations'} took part.
            </p>
            <h3 className="m-0 text-h4">Limits</h3>
            <ul className="m-0 list-disc pl-5 [&>li+li]:mt-1">{data.limits.map((l) => <li key={l}>{l}</li>)}</ul>
          </AboutData>
          <ContentSection title="Coordinators">
            {/* WP-91 (UX audit 6): with all programmes shown, civil research led the table; the API now orders defence-relevant work first */}
            {data.order && <p className="m-0 max-w-prose text-small text-ink-muted" data-order>{data.order}</p>}
            {data.coordinators.length === 0 ? <p className="m-0">No project started in or after {data.since} matches.</p> : (
              <TableBox label="Coordinators with a Ukrainian participant">
                <table className="stack-sm w-full min-w-[720px] border-collapse text-left text-small">
                  <caption className="sr-only">Coordinators with a Ukrainian participant, defence and dual-use projects first</caption>
                  <thead>
                    <tr className="border-b border-line">
                      <th scope="col" className="py-2 pr-4 font-semibold">Coordinator</th>
                      <th scope="col" className="py-2 pr-4 text-right font-semibold">Projects</th>
                      <th scope="col" className="py-2 pr-4 font-semibold">Ukrainian participants</th>
                      <th scope="col" className="py-2 font-semibold">Recent projects</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.coordinators.map((c) => (
                      <tr key={c.organisation.id ?? c.organisation.name} className="border-b border-line align-top last:border-0">
                        <th scope="row" className="py-2 pr-4 font-normal"><OrgLink org={c.organisation} />{c.organisation.country ? <span className="text-ink-muted"> ({c.organisation.country})</span> : null}</th>
                        <td data-label="Projects" className="py-2 pr-4 text-right font-mono tabular-nums">{c.projects}<span className="block text-ink-muted">{yearsLabel(null, c.lastYear)}</span></td>
                        <td data-label="Ukrainian participants" className="py-2 pr-4">
                          <ul className="m-0 list-none p-0">{c.ukrainianParticipants.map((u) => <li key={u.organisation.id ?? u.organisation.name}><OrgLink org={u.organisation} /> <span className="text-ink-muted">({u.projects})</span></li>)}</ul>
                        </td>
                        <td data-label="Recent projects" className="py-2">
                          <ul className="m-0 list-none p-0">{c.recentProjects.map((p) => <li key={p.slug}><Link href={`/projects/${p.slug}`}>{p.acronym ?? p.title}</Link> <span className="text-ink-muted">{p.year}</span></li>)}</ul>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableBox>
            )}
          </ContentSection>
          <ContentSection title="Ukrainian organisations in these projects">
            <ul className="m-0 list-none p-0 [column-gap:2rem] [column-width:22rem] [&>li]:mb-1 [&>li]:break-inside-avoid">
              {data.ukrainianOrganisations.map((u) => (
                <li key={u.organisation.id ?? u.organisation.name}><OrgLink org={u.organisation} /> <span className="text-ink-muted">{u.projects} {u.projects === 1 ? 'project' : 'projects'}, {u.coordinated} as coordinator</span></li>
              ))}
            </ul>
          </ContentSection>
          <DataSources sources={data.sources}><CountryNote /></DataSources>
        </>
    </ContentPage>
  );
}
