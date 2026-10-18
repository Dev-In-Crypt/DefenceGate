import type { Metadata } from 'next';
import Link from 'next/link';
import { ExternalLink, Link2, Rss } from 'lucide-react';
import { getRegulation } from '@/lib/regulation-api';
import { STATUS_MEANING, STATUS_WORD, citation, linkHref, newestFirst } from '@/lib/regulation';
import { formatDateUtc } from '@/lib/format';
import { safeHttpUrl } from '@/lib/safe-url';
import { SITE, buildMetadata } from '@/lib/seo';
import { ContentPage } from '@/components/dg/content-page';
import { Icon } from '@/components/dg/icon';
import { Tag } from '@/components/dg/tag';

export const revalidate = 3600;

const meta = buildMetadata({
  title: 'Regulatory tracker',
  description: 'Changes in the rules that matter to a defence supplier (SAFE, EDIP, the Ukraine Support Instrument, the European Defence Fund, the defence procurement directive), each with the official source and the day we last checked it.',
  path: '/regulation',
});
export const metadata: Metadata = { ...meta, alternates: { ...meta.alternates, types: { 'application/atom+xml': '/regulation.atom' } } };

export default async function RegulationPage() {
  const feed = await getRegulation();
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Regulatory tracker', href: '/regulation' }]}
      title="Regulatory tracker"
      lead="What changed in the rules that decide who may supply European defence programmes. Each entry gives the official source, one sentence of it copied word for word, and the day we last read it."
      wide
    >
      <p className="m-0 text-small text-ink-muted">
        {feed.notice}{feed.lastChecked ? ` Last checked ${formatDateUtc(feed.lastChecked)}.` : ''}{' '}
        <a href="/regulation.atom" className="inline-flex min-h-11 items-center gap-1 font-semibold"><Icon icon={Rss} size="inline" />Atom feed</a>
      </p>
      <p className="m-0 max-w-[90ch] text-small text-ink-muted">Newest event first. Each entry has a link to itself and a line you can copy into a note.</p>
      <ol className="m-0 flex list-none flex-col gap-4 p-0">
        {newestFirst(feed.entries).map((e) => {
          const url = safeHttpUrl(e.source.url);
          return (
            <li key={e.code} id={e.code} className="flex min-w-0 flex-col gap-3 rounded-lg border border-edge bg-surface p-5 sm:p-6">
              <div className="flex flex-wrap items-center gap-2">
                <Tag>{STATUS_WORD[e.status]}</Tag>
                <Tag>{e.instrument}</Tag>
                <time dateTime={e.eventDate} className="font-mono text-mono text-ink-muted">{formatDateUtc(e.eventDate)}</time>
              </div>
              <h2 className="m-0 text-h3">
                {e.title}{' '}
                <a href={`#${e.code}`} aria-label={`Link to this entry: ${e.title}`} title="Link to this entry"
                  className="inline-flex min-h-12 min-w-12 items-center justify-center align-middle text-ink-muted"><Icon icon={Link2} size="inline" /></a>
              </h2>
              <p className="m-0 max-w-[90ch] text-body">{e.whatChanged}</p>
              <p className="m-0 max-w-[90ch] text-small text-ink-muted">{STATUS_MEANING[e.status]}</p>
              <p className="m-0 max-w-[90ch] text-body"><strong>Who is affected.</strong> {e.affected}</p>
              <figure className="m-0 flex flex-col gap-1">
                <blockquote className="m-0 max-w-[90ch] break-words border-l-4 border-line pl-3 text-small">{e.source.quote}</blockquote>
                <figcaption className="flex flex-wrap items-center gap-x-3 text-small text-ink-muted">
                  <span>{e.source.ref}</span>
                  {url && (
                    <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-1 font-semibold">
                      Primary source<Icon icon={ExternalLink} size="inline" /><span className="sr-only">(opens in new tab)</span>
                    </a>
                  )}
                </figcaption>
              </figure>
              {e.links.length > 0 && (
                <p className="m-0 flex flex-wrap gap-x-4 text-small">
                  <span className="text-ink-muted">On this site:</span>
                  {e.links.map((l) => <Link key={`${l.kind}:${l.code}`} href={linkHref(l)} className="inline-flex min-h-11 items-center font-semibold">{l.label}</Link>)}
                </p>
              )}
              <p className="m-0 text-small text-ink-muted">Last checked <time dateTime={e.checkedOn}>{formatDateUtc(e.checkedOn)}</time>.</p>
              <p className="m-0 text-small">
                <span className="font-semibold">Cite this entry: </span>
                <span className="break-words select-all text-ink-muted">{citation(e, SITE.url)}</span>
              </p>
            </li>
          );
        })}
      </ol>
    </ContentPage>
  );
}
