import Link from 'next/link';
import { ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { displayName } from '@/lib/display-name';
import { formatDateUtc, formatNumber } from '@/lib/format';
import { safeHttpUrl } from '@/lib/safe-url';
import { DEFENCE_PROGRAMMES, DEFENCE_PROGRAMMES_WORDS, PROGRAMME_CHOICES, contributionMissing, PROGRAMME_WORD, programmeName, effectiveProgrammes, fundingGroups, formatEur, methodWord, roleWord, toOrgQuery, yearsLabel, activeOrgFilterCount } from '@/lib/networks';
import { BUYER_COUNTRIES } from '@/lib/taxonomy';
import type { FundingRow, OrgFilters, OrgListItem, OrgProjectRow, OrgRef, PartnerRow, ProjectMember, SourceNote } from '@/lib/networks-types';
import { Button } from '../dg/button';
import { DataTable } from '../dg/data-table';
import { CARD_BODY, CARD_TEXT, CARD_TITLE } from '../dg/cards';
import { CardLink } from '../dg/card-link';
import { CountryLabel, FactCell } from '../dg/data-display';
import { Choice, FoldGroup, Select, TextInput } from '../dg/form';
import { FORM_BUTTONS } from '../funding/filter-bar';
import { Icon } from '../dg/icon';
import { ScrollBox } from '../dg/scroll-box';
import { Tag } from '../dg/tag';
import { FilterPanel } from '../funding/filter-panel';
import { AboutData } from '../dg/about-data';

/** A list card as in components/dg/cards.tsx: no outline, padding 20, 12 px gaps, a 1.5px --ink-muted edge on hover. */
const CARD = '[container-type:inline-size] group relative flex flex-col gap-3 rounded-lg border-strong border-transparent bg-surface p-5 transition-colors duration-dg hover:border-ink-muted has-[:focus-visible]:border-ink-muted has-[[data-link-pending]]:opacity-70';
const TITLE_LINK = 'break-words text-inherit no-underline decoration-2 underline-offset-4 after:absolute after:inset-0 after:rounded-lg after:content-[""]';

/** The name of an organisation as a person reads it. */
export const nameOf = (name: string) => displayName(name, 'title');

/** An organisation in someone else's list: a link to its profile, or, when it was removed on request, just the neutral text. */
export function OrgLink({ org }: { org: OrgRef }) {
  if (!org.slug) return <span>{nameOf(org.name)}</span>;
  return <Link href={`/organisations/${org.slug}`} className="font-semibold">{nameOf(org.name)}</Link>;
}

export function Country({ code }: { code: string | null }) {
  return code ? <CountryLabel code={code} /> : <span className="text-ink-muted">Not stated</span>;
}

/** A table that scrolls inside its own box at 375 px, reachable and labelled for the keyboard, with a line that says there is more. */
export function TableBox({ label, children }: { label: string; children: React.ReactNode }) {
  return <ScrollBox label={label}>{children}</ScrollBox>;
}

/**
 * `scope`: what the list is limited to. In the defence scope (the default of the directory) the first figure is the number of
 * defence projects (EDF, EDIDP, PADR) and the others are labelled as all-programme figures: CNRS has 10 EDF projects among 4,336
 * (verification 3, finding 4). Over all programmes the first figure is every project and the defence ones are named beside it.
 */
export function OrgCard({ org, scope = 'all' }: { org: OrgListItem; scope?: 'defence' | 'all' }) {
  const defence = scope === 'defence';
  const num = (n: number) => <span className="tabular-nums">{n}</span>;
  return (
    <article className={cn(CARD, 'text-ink')}>
      <div className={cn(CARD_BODY, 'cqw:grid-cols-[minmax(0,1fr)_560px]')}>
        <div className={CARD_TEXT}>
          <h2 className={CARD_TITLE}>
            <CardLink href={`/organisations/${org.slug}`} className={TITLE_LINK} title={nameOf(org.name)}>{nameOf(org.name)}</CardLink>
          </h2>
          <span className="text-small text-ink-muted"><CountryLabel code={org.country} /></span>
          {org.nameVariants ? <span className="text-small text-ink-muted">Includes {org.nameVariants} name {org.nameVariants === 1 ? 'variant' : 'variants'}</span> : null}
          <p className="m-0 flex flex-wrap gap-2">{org.programmes.map((p) => <Tag key={p} kind="programme">{programmeName(p)}</Tag>)}</p>
        </div>
        <dl className="facts-grid facts-grid--4 m-0 border-b border-line cqw:col-start-2 cqw:row-start-1 cqw:self-start">
          {defence ? (
            <>
              <FactCell label="Defence projects">{num(org.defenceProjects)}</FactCell>
              <FactCell label="Projects, all programmes">{num(org.projects)}</FactCell>
            </>
          ) : (
            <>
              <FactCell label="Projects">{num(org.projects)}</FactCell>
              <FactCell label="Of which defence">{num(org.defenceProjects)}</FactCell>
            </>
          )}
          <FactCell label={defence ? 'Coordinated, all programmes' : 'As coordinator'}>{num(org.coordinated)}</FactCell>
          <FactCell label={defence ? 'EU contribution, all programmes' : 'EU contribution'}>{org.euContribution === null ? <span className="font-sans">{contributionMissing(org.programmes)}</span> : formatEur(org.euContribution)}</FactCell>
          <FactCell label="Active">{yearsLabel(org.firstYear, org.lastYear)}</FactCell>
        </dl>
      </div>
    </article>
  );
}

/**
 * Which programmes the list shows, said above it with the switch to the other choice (U10: the directory used to open with the
 * largest civil research bodies). `filters.programme` empty and no `allProgrammes`: the defence-relevant default.
 */
export function ProgrammeScope({ filters, basePath }: { filters: OrgFilters; basePath: string }) {
  const chosen = filters.programme ?? [];
  const link = (f: OrgFilters) => `${basePath}${toOrgQuery({ ...f, page: 1 })}`;
  return (
    <p role="status" className="m-0 max-w-prose rounded-md bg-surface-inset px-4 py-3 text-body">
      {filters.allProgrammes ? (
        <>Showing <strong>all programmes</strong>, including civil research from Horizon Europe, Horizon 2020 and FP7.{' '}
          <Link href={link({ ...filters, allProgrammes: false, programme: [] })} className="font-semibold">Show only {DEFENCE_PROGRAMMES_WORDS}</Link>.</>
      ) : chosen.length > 0 ? (
        <>Showing <strong>{chosen.map((c) => PROGRAMME_WORD[c] ?? c).join(', ')}</strong>.{' '}
          <Link href={link({ ...filters, allProgrammes: true, programme: [] })} className="font-semibold">Show all programmes</Link>.</>
      ) : (
        <>Showing <strong>{DEFENCE_PROGRAMMES_WORDS}</strong>, the defence programmes.{' '}
          <Link href={link({ ...filters, allProgrammes: true, programme: [] })} className="font-semibold">Show all programmes</Link>, including civil research (Horizon Europe, Horizon 2020, FP7).</>
      )}
    </p>
  );
}

/** What the country of an organisation means: one country per registration, and a multi-site body shows one of them (U10: CSIC under Italy). */
export function CountryNote({ className }: { className?: string }) {
  return (
    <p className={cn('m-0 max-w-prose text-small text-ink-muted', className)}>
      The country is the one the source records for the organisation’s registration (its PIC), and each profile says what it rests on. Where the record
      contradicts itself (the address in one country, the site name and the VAT number in another) we follow the two that agree: the Spanish research council
      CSIC is shown under Spain although its address is recorded in Italy. A body with sites in several countries is shown under the first of them in
      alphabetical order, and its profile lists the others. Beyond that we do not guess.
    </p>
  );
}

/** URL-synced filter form (GET) for /organisations; FilterPanel makes it live when scripts run. */
export function OrgFilterBar({ filters, basePath }: { filters: OrgFilters; basePath: string }) {
  const countries = Object.entries({ UA: 'Ukraine', ...BUYER_COUNTRIES }).sort((a, b) => a[1].localeCompare(b[1])).map(([value, label]) => ({ value, label: `${label} (${value})` }));
  return (
    <FilterPanel activeCount={activeOrgFilterCount(filters)}
      defaults={{ programme: PROGRAMME_CHOICES.map((p) => p.value).filter((v) => DEFENCE_PROGRAMMES.includes(v)).join(',') }}>
      <form method="get" action={basePath} role="search" aria-label="Filter organisations" className="flex flex-col gap-3 rounded-lg border border-transparent bg-surface p-5">
        {/* WP-99 (p05): this box is the name; the topic of the projects has its own box below (a "cyber" here found names with cyber in them) */}
        <TextInput search name="q" maxLength={100} label="Name of the organisation" placeholder="For example Thales" defaultValue={filters.q ?? ''} />
        {/* WP-91 (UX audit 6): who worked on a topic, from the titles of the projects we hold (synonyms as in the funding search) */}
        <TextInput name="topic" maxLength={100} label="Project topic" placeholder="For example drone, cyber, radar" defaultValue={filters.topic ?? ''}
          hint="Words of the projects’ titles, acronyms and EDF categories; drone also finds unmanned, UAS and UAV. Every word must be in one project." />
        <FoldGroup legend="Programme" count={filters.programme?.length}>
          {PROGRAMME_CHOICES.map((p) => (
            <Choice key={p.value} name="programme" value={p.value} label={p.label} defaultChecked={effectiveProgrammes(filters).includes(p.value)} />
          ))}
          <Choice name="programme" value="all" label="All programmes (turns the others off)" defaultChecked={filters.allProgrammes} />
        </FoldGroup>
        <FoldGroup legend="Role" count={filters.role?.length}>
          <Choice name="role" value="coordinator" label="Has coordinated a project" defaultChecked={filters.role?.includes('coordinator')} />
        </FoldGroup>
        <Select name="country" label="Country of the organisation" placeholder="Any country" options={countries} defaultValue={filters.country?.[0] ?? ''} />
        <Select name="min" label="Projects" placeholder="Any number" options={[2, 5, 10, 25].map((n) => ({ value: String(n), label: `At least ${n}` }))}
          defaultValue={filters.minProjects ? String(filters.minProjects) : ''} />
        {filters.sort && filters.sort !== 'projects' && <input type="hidden" name="sort" value={filters.sort} />}
        <div className={FORM_BUTTONS}>
          <Button type="submit">Apply filters</Button>
          <Link href={basePath} className="inline-flex min-h-11 items-center text-small font-bold">Clear all</Link>
        </div>
      </form>
    </FilterPanel>
  );
}

/**
 * Where the data comes from, its licence and the day it was read. On every page of this layer. WP-88: one line, and the sources,
 * licences, amounts and method in a collapsed About this data (`children`, for example CountryNote, go in it too).
 */
export function DataSources({ sources, amountNote, only, children }: { sources: SourceNote[]; amountNote?: string; only?: string[]; children?: React.ReactNode }) {
  const shown = only ? sources.filter((s) => only.includes(s.code)) : sources;
  return (
    <section aria-labelledby="data-sources" className="flex flex-col gap-1 rounded-lg border border-transparent bg-surface p-5 sm:p-7">
      <h2 id="data-sources" className="m-0 text-h3">Where this comes from</h2>
      {/* WP-88: each source's attribution and licence stay on screen; read dates, notes, amounts and method are collapsed. */}
      <ul className="m-0 flex list-none flex-col gap-1 p-0 text-small text-ink-muted" data-attribution>
        {shown.map((s) => <li key={s.code} className="max-w-prose">{s.attribution}. Licence: {s.licence}.</li>)}
      </ul>
      <AboutData>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {shown.map((s) => (
          <li key={s.code} className="flex max-w-prose flex-col gap-1">
            <span className="font-semibold">{s.name}</span>
            <span className="max-w-prose text-small text-ink-muted">
              {s.readAt ? <>Last read on <time dateTime={s.readAt}>{formatDateUtc(s.readAt)}</time>. </> : 'Not read yet. '}
              Licence: {s.licence}. {s.attribution}.
            </span>
            {s.note && <span className="max-w-prose text-small">{s.note}</span>}
          </li>
        ))}
      </ul>
      {amountNote && <p className="m-0 max-w-prose text-small text-ink-muted">{amountNote}</p>}
      <p className="m-0 max-w-prose text-small text-ink-muted">
        Organisation-level facts only: a name, a country, a role, an amount, a year. A participant is recognised by its PIC where the source gives one,
        otherwise by name; the page says which. <Link href="/methodology" className="font-semibold">How the data is built</Link>.
      </p>
      {children}
      </AboutData>
    </section>
  );
}

/** Sections of a profile as links (each is a page of its own, so it can be shared and read without scripts). */
export function TabNav({ base, current, tabs }: { base: string; current: string; tabs: { id: string; label: string }[] }) {
  return (
    <nav aria-label="Sections of this profile">
      <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
        {tabs.map((t) => (
          <li key={t.id}>
            <Link href={t.id === tabs[0].id ? base : `${base}?tab=${t.id}`} aria-current={t.id === current ? 'page' : undefined}
              className={cn('inline-flex min-h-11 items-center rounded-pill px-4 text-small font-bold no-underline hover:no-underline',
                t.id === current ? 'bg-primary text-on-primary' : 'bg-surface text-ink hover:bg-surface-inset')}>
              {t.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/**
 * Funding by programme and year. Each programme is a table whose last column is a bar: the numbers are text, the bar repeats
 * them for the eye and is hidden from assistive technology. Which programme a row belongs to is its heading, never a colour.
 */
export function FundingChart({ rows }: { rows: FundingRow[] }) {
  const groups = fundingGroups(rows);
  return (
    <div className="flex flex-col gap-6">
      {groups.map((g) => (
        <section key={g.programme || 'none'} aria-labelledby={`fund-${g.programme || 'none'}`} className="flex flex-col gap-2">
          <h3 id={`fund-${g.programme || 'none'}`} className="m-0 text-body font-bold">
            {PROGRAMME_WORD[g.programme] ?? (g.programme || 'Programme not stated')}
          </h3>
          <p className="m-0 text-small text-ink-muted">
            {g.totalProjects} {g.totalProjects === 1 ? 'project' : 'projects'}
            {g.totalEur !== null ? `, ${formatEur(g.totalEur)} EU contribution.` : '. This programme states no amount per participant, so the bars show projects.'}
          </p>
          <DataTable label={`Funding by year, ${PROGRAMME_WORD[g.programme] ?? g.programme}`} caption={`${PROGRAMME_WORD[g.programme] ?? g.programme}: projects and EU contribution per year`} minWidth={520}>
            <thead>
              <tr>
                <th scope="col" className="whitespace-nowrap">Year</th>
                <th scope="col" className="whitespace-nowrap text-right">Projects</th>
                <th scope="col" className="whitespace-nowrap text-right">EU contribution</th>
                <th scope="col" className="w-1/3 min-w-24"><span className="sr-only">Bar, {g.measure === 'eur' ? 'EU contribution' : 'projects'}</span></th>
              </tr>
            </thead>
            <tbody>
              {g.rows.map((r) => (
                <tr key={r.year ?? 'none'}>
                  <th scope="row" className="whitespace-nowrap font-normal tabular-nums">{r.year ?? 'Year not stated'}</th>
                  <td className="whitespace-nowrap text-right font-mono tabular-nums">{formatNumber(r.projects)}</td>
                  <td className="whitespace-nowrap text-right font-mono tabular-nums">{r.euContribution === null ? 'Not stated' : formatEur(r.euContribution)}</td>
                  <td aria-hidden="true" className="align-middle">
                    {r.width > 0 && <div className="h-3 rounded-pill bg-primary" style={{ width: `${r.width}%` }} />}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </section>
      ))}
    </div>
  );
}

export function PartnerTable({ items }: { items: PartnerRow[] }) {
  return (
    <DataTable label="Partners, most shared projects first" minWidth={720}>
      <thead>
        <tr>
          <th scope="col" className="min-w-44">Organisation</th>
          <th scope="col" className="min-w-32">Country</th>
          <th scope="col" className="whitespace-nowrap text-right">Shared projects</th>
          <th scope="col">Years</th>
          <th scope="col" className="min-w-44">Latest shared projects</th>
        </tr>
      </thead>
      <tbody>
        {items.map((p, i) => (
          <tr key={p.organisation.id ?? `w${i}`}>
            <th scope="row" className="font-normal"><OrgLink org={p.organisation} /></th>
            <td><Country code={p.organisation.country} /></td>
            <td className="text-right font-mono tabular-nums">{p.shared}</td>
            <td className="whitespace-nowrap font-mono tabular-nums">{yearsLabel(p.firstYear, p.lastYear)}</td>
            <td>
              <ul className="m-0 flex list-none flex-wrap gap-x-3 gap-y-1 p-0">
                {p.projects.map((pr) => (
                  <li key={pr.slug}><Link href={`/projects/${pr.slug}`}>{pr.acronym ?? pr.title}</Link>{pr.year ? <span className="text-ink-muted"> {pr.year}</span> : null}</li>
                ))}
              </ul>
            </td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}

export function ProjectTable({ items }: { items: OrgProjectRow[] }) {
  return (
    <DataTable label="Projects, newest first" minWidth={720}>
      <thead>
        <tr>
          <th scope="col" className="min-w-56">Project</th>
          <th scope="col">Programme</th>
          <th scope="col">Year</th>
          <th scope="col">Role</th>
          <th scope="col" className="whitespace-nowrap text-right">EU contribution</th>
        </tr>
      </thead>
      <tbody>
        {items.map((p) => (
          <tr key={p.slug}>
            <th scope="row" className="font-normal">
              <Link href={`/projects/${p.slug}`} className="font-semibold">{p.acronym ?? p.title}</Link>
              {p.acronym && <span className="block max-w-prose text-ink-muted">{p.title}</span>}
            </th>
            <td>{p.programme ?? 'Not stated'}</td>
            <td className="whitespace-nowrap font-mono tabular-nums">{p.year ?? 'Not stated'}</td>
            <td>{roleWord(p.role)}</td>
            <td className="whitespace-nowrap text-right font-mono tabular-nums">{p.contribution === null ? 'Not stated' : formatEur(p.contribution)}</td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}

export function ConsortiumTable({ members }: { members: ProjectMember[] }) {
  return (
    <DataTable label="Members of the consortium" minWidth={720}>
      <thead>
        <tr>
          <th scope="col" className="min-w-48">Organisation</th>
          <th scope="col" className="min-w-32">Country</th>
          <th scope="col" className="whitespace-nowrap">Role</th>
          <th scope="col" className="whitespace-nowrap text-right">EU contribution</th>
          <th scope="col" className="min-w-36">Recognised by</th>
        </tr>
      </thead>
      <tbody>
        {members.map((m, i) => (
          <tr key={m.organisation.id ?? `w${i}`}>
            <th scope="row" className="font-normal"><OrgLink org={m.organisation} /></th>
            <td><Country code={m.organisation.country} /></td>
            <td className="whitespace-nowrap">{roleWord(m.role)}</td>
            <td className="whitespace-nowrap text-right font-mono tabular-nums">{m.contribution === null ? 'Not stated' : formatEur(m.contribution)}</td>
            <td>
              {methodWord(m.resolution.method)}{m.resolution.confidence !== null ? <span className="font-mono tabular-nums text-ink-muted"> ({m.resolution.confidence.toFixed(2)})</span> : null}
            </td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}

/** A link out to the source's own record. Only http(s) becomes a link. */
export function SourceLink({ url, label }: { url: string | null; label: string }) {
  const safe = safeHttpUrl(url);
  if (!safe) return <span className="text-small text-ink-muted">The source gives no link to this record.</span>;
  return (
    <a href={safe} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-1 text-small font-bold">
      {label}<Icon icon={ExternalLink} size="inline" /><span className="sr-only"> (opens in new tab)</span>
    </a>
  );
}
