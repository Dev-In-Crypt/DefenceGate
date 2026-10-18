import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, permanentRedirect } from 'next/navigation';
import { REMOVED, whenRemoved } from '@/lib/api';
import { RemovedOnRequest } from '@/components/dg/removed';
import { formatDateUtc, formatNumber } from '@/lib/format';
import { PARTNER_PAGE_SIZE, PROGRAMME_CHOICES, PROJECT_PAGE_SIZE, formatEur, isNetworkSlug, methodWord, yearsLabel } from '@/lib/networks';
import { getOrganisation, getOrganisationFunding, getOrganisationProjects, getPartners } from '@/lib/networks-api';
import { absoluteUrl, buildMetadata } from '@/lib/seo';
import { BUYER_COUNTRIES } from '@/lib/taxonomy';
import type { OrgProfile } from '@/lib/networks-types';
import { Button } from '@/components/dg/button';
import { CountryLabel, FactCell } from '@/components/dg/data-display';
import { Breadcrumbs, EmptyState, ErrorState, JsonLd } from '@/components/dg/feedback';
import { Select } from '@/components/dg/form';
import { Pagination } from '@/components/dg/pagination';
import { Tag } from '@/components/dg/tag';
import { DataSources, FundingChart, PartnerTable, ProjectTable, TabNav, TableBox, nameOf } from '@/components/networks/parts';
import type { SearchParams } from '@/lib/filters';

export const revalidate = 300;
type Props = { params: Promise<{ slug: string }>; searchParams: Promise<SearchParams> };

const TABS = [
  { id: 'overview', label: 'Overview' }, { id: 'funding', label: 'Funding' }, { id: 'partners', label: 'Partners' },
  { id: 'projects', label: 'Projects' }, { id: 'aliases', label: 'Names' },
];

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
function pageOf(sp: SearchParams): number {
  const n = Number(one(sp.page));
  return Number.isFinite(n) && n >= 1 ? Math.min(Math.floor(n), 500) : 1;
}
function tabOf(sp: SearchParams): string {
  const t = one(sp.tab);
  return TABS.some((x) => x.id === t) ? (t as string) : 'overview';
}

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const [{ slug }, sp] = await Promise.all([params, searchParams]);
  if (!isNetworkSlug(slug)) return { title: 'Organisation not found', robots: { index: false } };
  const org = await getOrganisation(slug).catch(whenRemoved);
  if (org === REMOVED) return { title: 'Removed on request', robots: { index: false } };
  if (!org) return { title: 'Organisation not found', robots: { index: false } };
  const name = nameOf(org.name);
  return buildMetadata({
    title: `${name}: projects, partners and EU funding`,
    description: `${name}: ${org.counts.projects} funded ${org.counts.projects === 1 ? 'project' : 'projects'}${org.counts.firstYear ? ` between ${yearsLabel(org.counts.firstYear, org.counts.lastYear)}` : ''}. From CORDIS and the EDF project factsheets.`,
    path: `/organisations/${org.slug}`,
    noindex: tabOf(sp) !== 'overview' || pageOf(sp) > 1 || Boolean(one(sp.country) || one(sp.programme)),
  });
}

export default async function OrganisationPage({ params, searchParams }: Props) {
  const [{ slug }, sp] = await Promise.all([params, searchParams]);
  if (!isNetworkSlug(slug)) notFound();
  const org = await getOrganisation(slug).catch(whenRemoved);
  if (org === REMOVED) return <RemovedOnRequest what="organisation" />;
  if (!org) notFound();
  const tab = tabOf(sp);
  const page = pageOf(sp);
  // A merged organisation's old address leads to the live one, keeping the section asked for.
  if (org.slug !== slug && isNetworkSlug(org.slug)) {
    const keep = new URLSearchParams();
    for (const k of ['tab', 'page', 'country', 'programme']) if (one(sp[k])) keep.set(k, one(sp[k]) as string);
    permanentRedirect(`/organisations/${org.slug}${keep.size ? `?${keep}` : ''}`);
  }
  const name = nameOf(org.name);
  const base = `/organisations/${org.slug}`;

  return (
    <>
      <Breadcrumbs items={[{ label: 'Home', href: '/' }, { label: 'Organisations', href: '/organisations' }, { label: name, href: base }]} />
      <JsonLd data={{ '@context': 'https://schema.org', '@type': 'Organization', name, url: absoluteUrl(base), address: { '@type': 'PostalAddress', addressCountry: org.country } }} />
      <header className="flex flex-col gap-4">
        <p className="m-0 flex flex-wrap gap-2">{org.programmes.map((p) => <Tag key={p.code || 'none'} kind="programme">{p.code || 'Programme not stated'}</Tag>)}</p>
        <h1 className="m-0 break-words text-[32px] font-extrabold leading-10 tracking-[-1px] md:text-h1">{name}</h1>
        <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-3">
          <FactCell label="Country"><CountryLabel code={org.country} className="font-sans" /></FactCell>
          <FactCell label="Projects"><span className="tabular-nums">{org.counts.projects}</span></FactCell>
          <FactCell label="As coordinator"><span className="tabular-nums">{org.counts.coordinated}</span></FactCell>
          <FactCell label="EU contribution (CORDIS)">
            {org.counts.euContribution === null ? <span className="font-sans">Not stated</span> : formatEur(org.counts.euContribution)}
          </FactCell>
          <FactCell label="Active"><span>{yearsLabel(org.counts.firstYear, org.counts.lastYear)}</span></FactCell>
        </dl>
        {org.buyer && (
          <p className="m-0 max-w-[70ch] text-body">
            Also a procurement buyer: <Link href={`/buyers/${org.buyer.slug}`} className="font-semibold">{org.buyer.tenderCount} defence {org.buyer.tenderCount === 1 ? 'notice' : 'notices'} on its buyer page</Link>.
          </p>
        )}
      </header>

      <TabNav base={base} current={tab} tabs={TABS} />

      {tab === 'overview' && <Overview org={org} />}
      {tab === 'funding' && <FundingTab slug={org.slug} />}
      {tab === 'partners' && <PartnersTab slug={org.slug} sp={sp} page={page} base={base} />}
      {tab === 'projects' && <ProjectsTab slug={org.slug} sp={sp} page={page} base={base} />}
      {tab === 'aliases' && <AliasesTab org={org} />}

      <DataSources sources={org.sources} amountNote={org.amountNote} />
      <p className="m-0 max-w-[80ch] text-small text-ink-muted">
        Names are as CORDIS and the EDF project factsheets publish them. We do not list an organisation whose name looks like a natural person&rsquo;s.
        If this entry is you, or a business named after you, and you want it removed, write to the contact in the <Link href="/imprint" className="font-semibold">imprint</Link>;
        the <Link href="/privacy" className="font-semibold">privacy notice</Link> (sections 7 and 9) says how a request is handled.
      </p>
    </>
  );
}

function Overview({ org }: { org: OrgProfile }) {
  return (
    <>
      <section aria-labelledby="recognised" className="flex flex-col gap-3 rounded-lg bg-surface p-5 sm:p-6">
        <h2 id="recognised" className="m-0 text-h3">How we recognised this organisation</h2>
        <p className="m-0 max-w-[80ch] text-body">{org.resolution.note}</p>
        <dl className="m-0 grid gap-x-8 gap-y-2 sm:grid-cols-[max-content_1fr]">
          <dt className="font-bold">PIC</dt>
          <dd className="m-0">
            {org.pic
              ? <><span className="font-mono tabular-nums">{org.pic.value}</span>{org.pic.method ? <span className="text-ink-muted"> ({org.pic.method === 'source' ? 'given by the source' : `attached after matching by ${methodWord(org.pic.method)}`})</span> : null}</>
              : <span className="text-ink-muted">None held: the EDF factsheets state none.</span>}
          </dd>
          {org.mergedFrom > 0 && (<><dt className="font-bold">Merged names</dt><dd className="m-0">{org.mergedFrom} other organisation {org.mergedFrom === 1 ? 'row was' : 'rows were'} merged into this one; their projects are counted here.</dd></>)}
        </dl>
      </section>
      <section aria-labelledby="by-programme" className="flex flex-col gap-3 rounded-lg bg-surface p-5 sm:p-6">
        <h2 id="by-programme" className="m-0 text-h3">By programme</h2>
        <TableBox label="Projects by programme">
          <table className="w-full min-w-[480px] border-collapse text-left text-small">
            <caption className="sr-only">Projects and EU contribution by programme</caption>
            <thead>
              <tr className="border-b border-line">
                <th scope="col" className="py-2 pr-4 font-semibold">Programme</th>
                <th scope="col" className="py-2 pr-4 text-right font-semibold">Projects</th>
                <th scope="col" className="py-2 pr-4 text-right font-semibold">EU contribution</th>
                <th scope="col" className="py-2 font-semibold">Years</th>
              </tr>
            </thead>
            <tbody>
              {org.programmes.map((p) => (
                <tr key={p.code || 'none'} className="border-b border-line last:border-0">
                  <th scope="row" className="py-2 pr-4 font-normal">{p.name || p.code}</th>
                  <td className="py-2 pr-4 text-right font-mono tabular-nums">{p.projects}</td>
                  <td className="py-2 pr-4 text-right font-mono tabular-nums">{p.euContribution === null ? 'Not stated' : formatEur(p.euContribution)}</td>
                  <td className="py-2 font-mono tabular-nums">{yearsLabel(p.firstYear, p.lastYear)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableBox>
      </section>
    </>
  );
}

async function FundingTab({ slug }: { slug: string }) {
  const funding = await getOrganisationFunding(slug).catch(() => null);
  if (!funding) return <ErrorState title="The funding history could not be loaded" retryHref={`/organisations/${slug}?tab=funding`} />;
  return (
    <section aria-labelledby="funding" className="flex flex-col gap-4 rounded-lg bg-surface p-5 sm:p-6">
      <h2 id="funding" className="m-0 text-h3">Funding by programme and year</h2>
      <p className="m-0 max-w-[80ch] text-small text-ink-muted">
        Years are the year a project started (the call year for EDF projects). {funding.amountNote}
      </p>
      <FundingChart rows={funding.rows} />
    </section>
  );
}

function FilterForm({ base, tab, programme, country }: { base: string; tab: string; programme?: string; country?: string }) {
  const countries = Object.entries({ UA: 'Ukraine', ...BUYER_COUNTRIES }).sort((a, b) => a[1].localeCompare(b[1])).map(([value, label]) => ({ value, label: `${label} (${value})` }));
  return (
    <form method="get" action={base} aria-label="Filter this list" className="flex flex-wrap items-end gap-3">
      <input type="hidden" name="tab" value={tab} />
      <Select name="programme" label="Programme" placeholder="All programmes" options={PROGRAMME_CHOICES} defaultValue={programme ?? ''} />
      {tab === 'partners' && <Select name="country" label="Partner country" placeholder="All countries" options={countries} defaultValue={country ?? ''} />}
      <Button type="submit" variant="secondary">Apply</Button>
    </form>
  );
}

async function PartnersTab({ slug, sp, page, base }: { slug: string; sp: SearchParams; page: number; base: string }) {
  const programme = /^[A-Z0-9_-]{1,20}$/.test(one(sp.programme) ?? '') ? one(sp.programme) : undefined;
  const country = /^[A-Z]{2}$/.test(one(sp.country) ?? '') ? one(sp.country) : undefined;
  const data = await getPartners(slug, { programme, country, page, pageSize: PARTNER_PAGE_SIZE }).catch(() => null);
  if (!data) return <ErrorState title="The partners could not be loaded" retryHref={`${base}?tab=partners`} />;
  const q = (p: number) => {
    const s = new URLSearchParams({ tab: 'partners' });
    if (programme) s.set('programme', programme);
    if (country) s.set('country', country);
    if (p > 1) s.set('page', String(p));
    return `${base}?${s}`;
  };
  return (
    <section aria-labelledby="partners" className="flex flex-col gap-4 rounded-lg bg-surface p-5 sm:p-6">
      <h2 id="partners" className="m-0 text-h3">Partners</h2>
      <p className="m-0 max-w-[80ch] text-small text-ink-muted">{data.note}</p>
      <FilterForm base={base} tab="partners" programme={programme} country={country} />
      {data.items.length === 0 ? (
        <EmptyState title="No partners match">Try another programme or country.</EmptyState>
      ) : (
        <>
          <p className="m-0 font-semibold" aria-live="polite">
            {formatNumber(data.total)} {data.total === 1 ? 'partner' : 'partners'} in {data.countries} {data.countries === 1 ? 'country' : 'countries'}
          </p>
          <PartnerTable items={data.items} />
          <Pagination page={data.page} total={data.total} pageSize={data.pageSize} hrefFor={q} />
        </>
      )}
    </section>
  );
}

async function ProjectsTab({ slug, sp, page, base }: { slug: string; sp: SearchParams; page: number; base: string }) {
  const programme = /^[A-Z0-9_-]{1,20}$/.test(one(sp.programme) ?? '') ? one(sp.programme) : undefined;
  const data = await getOrganisationProjects(slug, { programme, page, pageSize: PROJECT_PAGE_SIZE }).catch(() => null);
  if (!data) return <ErrorState title="The projects could not be loaded" retryHref={`${base}?tab=projects`} />;
  const q = (p: number) => {
    const s = new URLSearchParams({ tab: 'projects' });
    if (programme) s.set('programme', programme);
    if (p > 1) s.set('page', String(p));
    return `${base}?${s}`;
  };
  return (
    <section aria-labelledby="projects" className="flex flex-col gap-4 rounded-lg bg-surface p-5 sm:p-6">
      <h2 id="projects" className="m-0 text-h3">Projects</h2>
      <FilterForm base={base} tab="projects" programme={programme} />
      {data.items.length === 0 ? (
        <EmptyState title="No projects match">Try another programme.</EmptyState>
      ) : (
        <>
          <p className="m-0 font-semibold" aria-live="polite">{formatNumber(data.total)} {data.total === 1 ? 'project' : 'projects'}, newest first</p>
          <ProjectTable items={data.items} />
          <Pagination page={data.page} total={data.total} pageSize={data.pageSize} hrefFor={q} />
        </>
      )}
    </section>
  );
}

function AliasesTab({ org }: { org: OrgProfile }) {
  return (
    <section aria-labelledby="aliases" className="flex flex-col gap-4 rounded-lg bg-surface p-5 sm:p-6">
      <h2 id="aliases" className="m-0 text-h3">Names this organisation is known by</h2>
      <p className="m-0 max-w-[80ch] text-small text-ink-muted">
        Each name below was matched to this organisation, with the method and the confidence of the match. A name is never merged
        into an organisation by similarity alone: similar names are queued for a person to decide.
        {org.aliases.total > org.aliases.items.length ? ` Showing ${org.aliases.items.length} of ${org.aliases.total}.` : ''}
      </p>
      <TableBox label="Names and how they were matched">
        <table className="w-full min-w-[520px] border-collapse text-left text-small">
          <caption className="sr-only">Names, the method of the match and its confidence</caption>
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className="py-2 pr-4 font-semibold">Name</th>
              <th scope="col" className="py-2 pr-4 font-semibold">Matched by</th>
              <th scope="col" className="py-2 pr-4 text-right font-semibold">Confidence</th>
              <th scope="col" className="py-2 font-semibold">First seen</th>
            </tr>
          </thead>
          <tbody>
            {org.aliases.items.map((a) => (
              <tr key={`${a.name}|${a.source}`} className="border-b border-line last:border-0">
                <th scope="row" className="py-2 pr-4 font-normal">{a.name}</th>
                <td className="py-2 pr-4">{methodWord(a.method)}{a.source ? <span className="text-ink-muted"> · {a.source}</span> : null}</td>
                <td className="py-2 pr-4 text-right font-mono tabular-nums">{a.confidence === null ? 'Not stated' : a.confidence.toFixed(2)}</td>
                <td className="py-2 font-mono tabular-nums"><time dateTime={a.firstSeen}>{formatDateUtc(a.firstSeen)}</time></td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableBox>
    </section>
  );
}
