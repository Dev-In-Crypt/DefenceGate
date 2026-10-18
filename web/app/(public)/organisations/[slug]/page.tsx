import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, permanentRedirect } from 'next/navigation';
import { REMOVED, whenRemoved } from '@/lib/api';
import { RemovedOnRequest } from '@/components/dg/removed';
import { formatDateUtc, formatNumber } from '@/lib/format';
import { DEFENCE_PROGRAMMES, PARTNER_PAGE_SIZE, PROGRAMME_CHOICES, PROJECT_PAGE_SIZE, formatEur, isNetworkSlug, methodWord, yearsLabel } from '@/lib/networks';
import { getOrganisation, getOrganisationFunding, getOrganisationProjects, getPartners } from '@/lib/networks-api';
import { absoluteUrl, buildMetadata } from '@/lib/seo';
import { BUYER_COUNTRIES } from '@/lib/taxonomy';
import type { OrgProfile } from '@/lib/networks-types';
import { Button } from '@/components/dg/button';
import { CountryLabel, FactCell } from '@/components/dg/data-display';
import { EmptyState, ErrorState, JsonLd } from '@/components/dg/feedback';
import { PageHeader } from '@/components/dg/page-header';
import { Card } from '@/components/dg/card';
import { DataTable } from '@/components/dg/data-table';
import { Fact, FactsGrid } from '@/components/dg/facts-grid';
import { Select } from '@/components/dg/form';
import { Pagination } from '@/components/dg/pagination';
import { Tag } from '@/components/dg/tag';
import { CountryNote, DataSources, FundingChart, PartnerTable, ProjectTable, TabNav, nameOf } from '@/components/networks/parts';
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
      <JsonLd data={{ '@context': 'https://schema.org', '@type': 'Organization', name, url: absoluteUrl(base), address: { '@type': 'PostalAddress', addressCountry: org.country } }} />
      <PageHeader
        crumbs={[{ label: 'Home', href: '/' }, { label: 'Organisations', href: '/organisations' }, { label: name, href: base }]}
        eyebrow={<p className="m-0 flex flex-wrap gap-2">{org.programmes.map((p) => <Tag key={p.code || 'none'} kind="programme">{p.code || 'Programme not stated'}</Tag>)}</p>}
        title={name}
      >
        <FactsGrid>
          <FactCell label="Country">
            <CountryLabel code={org.country} className="font-sans" />
            {countryBasisNote(org) && <span className="block font-sans text-small font-normal text-ink-muted">{countryBasisNote(org)}</span>}
          </FactCell>
          <FactCell label="Defence projects"><span className="tabular-nums">{defenceProjectsOf(org)}</span></FactCell>
          <FactCell label="Projects, all programmes"><span className="tabular-nums">{org.counts.projects}</span></FactCell>
          <FactCell label="As coordinator"><span className="tabular-nums">{org.counts.coordinated}</span></FactCell>
          <FactCell label="EU contribution (CORDIS)">
            {org.counts.euContribution === null ? <span className="font-sans">Not stated</span> : formatEur(org.counts.euContribution)}
          </FactCell>
          <FactCell label="Active"><span>{yearsLabel(org.counts.firstYear, org.counts.lastYear)}</span></FactCell>
        </FactsGrid>
        {org.buyer && (
          <p className="m-0 max-w-prose text-body">
            Also a procurement buyer: <Link href={`/buyers/${org.buyer.slug}`} className="font-semibold">{org.buyer.tenderCount} defence {org.buyer.tenderCount === 1 ? 'notice' : 'notices'} on its buyer page</Link>.
          </p>
        )}
      </PageHeader>

      <TabNav base={base} current={tab} tabs={TABS} />

      {tab === 'overview' && <Overview org={org} />}
      {tab === 'funding' && <FundingTab slug={org.slug} />}
      {tab === 'partners' && <PartnersTab slug={org.slug} sp={sp} page={page} base={base} />}
      {tab === 'projects' && <ProjectsTab slug={org.slug} sp={sp} page={page} base={base} />}
      {tab === 'aliases' && <AliasesTab org={org} />}

      <CountryNote />
      <DataSources sources={org.sources} amountNote={org.amountNote} />
      <p className="m-0 max-w-prose text-small text-ink-muted">
        Names are as CORDIS and the EDF project factsheets publish them. We do not list an organisation whose name looks like a natural person&rsquo;s.
        If this entry is you, or a business named after you, and you want it removed, write to the contact in the <Link href="/imprint" className="font-semibold">imprint</Link>;
        the <Link href="/privacy" className="font-semibold">privacy notice</Link> (sections 7 and 9) says how a request is handled.
      </p>
    </>
  );
}

/** Projects of the defence programmes (EDF, EDIDP, PADR): a project has one programme, so the rows add up. */
function defenceProjectsOf(org: OrgProfile): number {
  return org.programmes.filter((p) => DEFENCE_PROGRAMMES.includes(p.code)).reduce((n, p) => n + p.projects, 0);
}

/** What the country rests on, said only where it is not the plain address. */
function countryBasisNote(org: OrgProfile): string | null {
  if (org.countryBasis === 'vote') return 'The site name and the VAT number in the record agree on this country; its recorded address is elsewhere.';
  if (org.countryBasis === 'several') return `Sites in ${(org.countrySites ?? []).join(', ')}; the first is shown.`;
  return null;
}

function Overview({ org }: { org: OrgProfile }) {
  return (
    <>
      <Card title="How we recognised this organisation" id="recognised">
        <p className="m-0 text-body">{org.resolution.note}</p>
        <FactsGrid className="border-b-0 [&>div:first-child]:border-t-0">
          <Fact label="PIC" wide={!org.pic}>
            {org.pic
              ? <><span className="font-mono tabular-nums">{org.pic.value}</span>{org.pic.method ? <span className="text-ink-muted"> ({org.pic.method === 'source' ? 'given by the source' : `attached after matching by ${methodWord(org.pic.method)}`})</span> : null}</>
              : <span className="text-ink-muted">None held: the EDF factsheets state none.</span>}
          </Fact>
          {org.nameVariants && (<Fact label="Name variants" wide>{org.nameVariants.total === 1 ? 'One other row carries' : `${org.nameVariants.total} other rows carry`} a name of this organisation that could not be proved to be the same legal body; they are not merged, and their projects are counted here. {org.nameVariants.items.map((v, i) => (<span key={v.organisation.id ?? i}>{i > 0 ? '; ' : ''}{v.organisation.slug ? <Link href={`/organisations/${v.organisation.slug}`} className="underline underline-offset-2">{v.organisation.name}</Link> : v.organisation.name} ({v.projects})</span>))}</Fact>)}
          {org.variantOf && (<Fact label="Name variant of" wide>This row is shown under {org.variantOf.organisation.slug ? <Link href={`/organisations/${org.variantOf.organisation.slug}`} className="underline underline-offset-2">{org.variantOf.organisation.name}</Link> : org.variantOf.organisation.name} in the directory; it is a separate row and is not merged.</Fact>)}
          {org.mergedFrom > 0 && (<Fact label="Merged names" wide>{org.mergedFrom} other organisation {org.mergedFrom === 1 ? 'row was' : 'rows were'} merged into this one; their projects are counted here.</Fact>)}
        </FactsGrid>
      </Card>
      <Card title="By programme" id="by-programme">
        {org.programmes.length <= 2 ? (
          // One or two rows do not make a table: each programme is a short facts list.
          <div className="flex flex-col gap-4">
            {org.programmes.map((p) => (
              <FactsGrid key={p.code || 'none'} className="facts-grid--4 border-b-0 [&>div:first-child]:border-t-0">
                <Fact label="Programme">{p.name || p.code}</Fact>
                <Fact label="Projects" mono>{p.projects}</Fact>
                <Fact label="EU contribution" mono>{p.euContribution === null ? <span className="font-sans">Not stated</span> : formatEur(p.euContribution)}</Fact>
                <Fact label="Years" mono>{yearsLabel(p.firstYear, p.lastYear)}</Fact>
              </FactsGrid>
            ))}
          </div>
        ) : (
          <DataTable label="Projects by programme">
            <thead>
              <tr>
                <th scope="col">Programme</th>
                <th scope="col" className="text-right">Projects</th>
                <th scope="col" className="whitespace-nowrap text-right">EU contribution</th>
                <th scope="col">Years</th>
              </tr>
            </thead>
            <tbody>
              {org.programmes.map((p) => (
                <tr key={p.code || 'none'}>
                  <th scope="row" className="min-w-40 font-normal">{p.name || p.code}</th>
                  <td className="text-right font-mono tabular-nums">{p.projects}</td>
                  <td className="whitespace-nowrap text-right font-mono tabular-nums">{p.euContribution === null ? 'Not stated' : formatEur(p.euContribution)}</td>
                  <td className="whitespace-nowrap font-mono tabular-nums">{yearsLabel(p.firstYear, p.lastYear)}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        )}
      </Card>
    </>
  );
}

async function FundingTab({ slug }: { slug: string }) {
  const funding = await getOrganisationFunding(slug).catch(() => null);
  if (!funding) return <ErrorState title="The funding history could not be loaded" retryHref={`/organisations/${slug}?tab=funding`} />;
  return (
    <Card title="Funding by programme and year" id="funding">
      <p className="m-0 text-small text-ink-muted">
        Years are the year a project started (the call year for EDF projects). {funding.amountNote}
      </p>
      <FundingChart rows={funding.rows} />
    </Card>
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
    <Card title="Partners" id="partners">
      <p className="m-0 text-small text-ink-muted">{data.note}</p>
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
    </Card>
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
    <Card title="Projects" id="projects">
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
    </Card>
  );
}

function AliasesTab({ org }: { org: OrgProfile }) {
  return (
    <Card title="Names this organisation is known by" id="aliases">
      <p className="m-0 text-small text-ink-muted">
        Each name below was matched to this organisation, with the method and the confidence of the match. A name is never merged
        into an organisation by similarity alone: similar names are queued for a person to decide.
        {org.aliases.total > org.aliases.items.length ? ` Showing ${org.aliases.items.length} of ${org.aliases.total}.` : ''}
      </p>
      <DataTable label="Names and how they were matched" minWidth={560}>
        <thead>
          <tr>
            <th scope="col" className="min-w-44">Name</th>
            <th scope="col" className="min-w-36">Matched by</th>
            <th scope="col" className="text-right">Confidence</th>
            <th scope="col" className="whitespace-nowrap">First seen</th>
          </tr>
        </thead>
        <tbody>
          {org.aliases.items.map((a) => (
            <tr key={`${a.name}|${a.source}`}>
              <th scope="row" className="font-normal">{a.name}</th>
              <td>{methodWord(a.method)}{a.source ? <span className="text-ink-muted"> · {a.source}</span> : null}</td>
              <td className="whitespace-nowrap text-right font-mono tabular-nums">{a.confidence === null ? 'Not stated' : a.confidence.toFixed(2)}</td>
              <td className="whitespace-nowrap font-mono tabular-nums"><time dateTime={a.firstSeen}>{formatDateUtc(a.firstSeen)}</time></td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </Card>
  );
}
