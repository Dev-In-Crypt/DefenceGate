import type { Metadata } from 'next';
import Link from 'next/link';
import { ExternalLink, Link2, Rss } from 'lucide-react';
import { getRegulation } from '@/lib/regulation-api';
import { STATUS_MEANING, STATUS_WORD, checkedLine, citation, linkHref, newestFirst, type RegulationStatus } from '@/lib/regulation';
import { formatDateUtc } from '@/lib/format';
import { safeHttpUrl } from '@/lib/safe-url';
import { SITE, buildMetadata } from '@/lib/seo';
import { ContentPage } from '@/components/dg/content-page';
import { Details } from '@/components/dg/details';
import { AboutData } from '@/components/dg/about-data';
import { Fact } from '@/components/dg/facts-grid';
import { Icon } from '@/components/dg/icon';
import { Tag } from '@/components/dg/tag';
import { EntryList, type EntryItem } from '@/components/regulation/entry-list';

export const revalidate = 3600;

const meta = buildMetadata({
  title: 'Regulatory tracker',
  // WP-139 (r8 audit: the trim kept 55 characters, the part before the bracket): one that fits the 160 a description has
  description: 'Changes in the rules a defence supplier works under: SAFE, EDIP, the Ukraine Support Instrument, the EDF and directive 2009/81, each with its official source.',
  path: '/regulation',
});
export const metadata: Metadata = { ...meta, alternates: { ...meta.alternates, types: { 'application/atom+xml': '/regulation.atom' } } };

/** The order of the status chips: from a text in force to a point nobody has settled. */
const STATUS_ORDER: RegulationStatus[] = ['in_force', 'adopted', 'agreed', 'proposed', 'announced', 'unconfirmed'];

export default async function RegulationPage() {
  const feed = await getRegulation();
  const entries = newestFirst(feed.entries);
  const checked = checkedLine(entries, formatDateUtc);
  const chips = STATUS_ORDER
    .map((s) => ({ status: s as string, label: STATUS_WORD[s], count: entries.filter((e) => e.status === s).length }))
    .filter((c) => c.count > 0);
  const items: EntryItem[] = entries.map((e) => {
    const url = safeHttpUrl(e.source.url);
    return {
      code: e.code,
      status: e.status,
      node: (
        <>
          <div className="justify-col flex min-w-0 flex-col gap-3 [&_blockquote]:max-w-prose [&_p]:max-w-prose">
            <div className="flex flex-wrap items-center gap-2">
              <Tag kind={e.status === 'in_force' || e.status === 'adopted' ? 'programme' : 'neutral'}>{STATUS_WORD[e.status]}</Tag>
              <Tag>{e.instrument}</Tag>
              <time dateTime={e.eventDate} className="font-mono text-mono text-ink-muted">{formatDateUtc(e.eventDate)}</time>
            </div>
            <h2 className="m-0 flex items-start justify-between gap-2 text-h3">
              <span className="min-w-0 break-words">{e.title}</span>
              <a href={`#${e.code}`} aria-label={`Link to this entry: ${e.title}`} title="Link to this entry"
                className="-mr-2 -mt-1 inline-flex size-9 shrink-0 items-center justify-center rounded-md text-ink-muted hover:bg-surface-inset hover:text-ink"><Icon icon={Link2} size="inline" /></a>
            </h2>
            <p className="justify-p m-0 text-body max-sm:leading-6">{e.whatChanged}</p>
            <Details summary="Quote, source, status and how to cite">
              <p className="m-0"><span className="font-semibold text-ink">{STATUS_WORD[e.status]}. </span>{STATUS_MEANING[e.status]}</p>
              <figure className="m-0 flex flex-col gap-2">
                <blockquote className="m-0 border-l-4 border-line pl-3 text-body text-ink">{e.source.quote}</blockquote>
                <figcaption>{e.source.ref}</figcaption>
              </figure>
              <p className="m-0">
                <span className="font-semibold text-ink">Cite this entry: </span>
                <span className="select-all">{citation(e, SITE.url)}</span>
              </p>
            </Details>
          </div>
          {/* On a phone the facts are packed: the status is the tag above (so its fact is dropped there), the day we checked and the source share a row, the rest take a row each. */}
          <dl className="m-0 grid h-fit grid-cols-2 gap-x-6 border-b border-line">
            <Fact label="Status" className="py-2 max-sm:hidden">
              <span className="font-semibold">{STATUS_WORD[e.status]}</span>
            </Fact>
            <Fact label="Last checked" className="py-2 max-sm:order-1"><time dateTime={e.checkedOn}>{formatDateUtc(e.checkedOn)}</time></Fact>
            <Fact label="Who is affected" wide className="py-2 max-sm:order-3">{e.affected}</Fact>
            {url && (
              <Fact label="Source" wide={e.links.length > 1} className="py-2 max-sm:order-2 max-sm:col-auto">
                <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-8 items-center gap-1 font-semibold">
                  Primary source<Icon icon={ExternalLink} size="inline" /><span className="sr-only">(opens in new tab)</span>
                </a>
              </Fact>
            )}
            {e.links.length > 0 && (
              <Fact label="On this site" wide={e.links.length > 1} className="py-2 max-sm:order-4 max-sm:col-span-full">
                <span className="flex flex-wrap gap-x-4">
                  {e.links.map((l) => <Link key={`${l.kind}:${l.code}`} href={linkHref(l)} className="inline-flex min-h-8 items-center font-semibold">{l.label}</Link>)}
                </span>
              </Fact>
            )}
          </dl>
        </>
      ),
    };
  });
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Regulatory tracker', href: '/regulation' }]}
      title="Regulatory tracker"
      lead="What changed in the rules that decide who may supply European defence programmes."
      wide
    >
      <div className="flex max-w-prose flex-col gap-2">
        {/* WP-88: what the tracker is and is not (the feed's notice) is collapsed under one line. */}
        <p className="m-0 text-small text-ink-muted" data-checked-line>Newest event first.{checked ? ` ${checked}` : ''}</p>
        <AboutData>
          <p className="m-0">{feed.notice}</p>
          <p className="m-0">Each entry has a link to itself and a line you can copy into a note.</p>
        </AboutData>
        <a href="/regulation.atom" className="inline-flex min-h-11 items-center gap-1 self-start text-small font-semibold"><Icon icon={Rss} size="inline" />Atom feed</a>
      </div>
      <EntryList chips={chips} items={items} />
    </ContentPage>
  );
}
