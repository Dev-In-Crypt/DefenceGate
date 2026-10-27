import type { Metadata } from 'next';
import Link from 'next/link';
import { buildMetadata } from '@/lib/seo';
import endpoints from '@/lib/data/api-endpoints.json';
import { NoteLine } from '@/components/dg/blocks';
import { CARD_PADDING, CARD_SURFACE } from '@/components/dg/card';
import { ContentPage, ContentSection, PageSection } from '@/components/dg/content-page';
import { Tag } from '@/components/dg/tag';

export const revalidate = 3600;

/** WP-153: the data API, described. Not linked from the menus and not indexed until the owner opens keys (DGATE_API_KEYS_OPEN). */
export const metadata: Metadata = buildMetadata({
  title: 'Data API: defence notices and their archive',
  description: 'What the DefenceGate data API gives: the defence procurement notices and every version of each, read with a key. Licence on request.',
  path: '/api',
  noindex: true,
});

const SCOPE_LABEL: Record<string, string> = { tenders: 'Notices', archive: 'Archive' };

export default function ApiPage() {
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Data API', href: '/api' }]}
      title="Data API"
      lead="The defence notices and the archive of their versions, as JSON, for your own systems. Licence on request."
    >
      <PageSection title="Endpoints" id="endpoints">
        <ul className="m-0 flex list-none flex-col gap-4 p-0" aria-label="Endpoints">
          {endpoints.endpoints.map((e) => (
            <li key={e.path} className={`${CARD_SURFACE} ${CARD_PADDING} flex min-w-0 flex-col gap-3`} data-endpoint={e.path}>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="m-0 text-h3">{e.title}</h3>
                <Tag>{SCOPE_LABEL[e.scope] ?? e.scope}</Tag>
              </div>
              <p className="m-0 font-mono text-mono [overflow-wrap:anywhere]">GET {e.path}</p>
              <p className="m-0 max-w-prose text-body text-ink-muted">{e.summary}</p>
              {e.params.length > 0 && (
                <dl className="m-0 grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-[max-content_minmax(0,1fr)]">
                  {e.params.map((p) => (
                    <div key={p.name} className="contents">
                      <dt className="font-mono text-mono">{p.name}</dt>
                      <dd className="m-0 mb-2 text-small text-ink-muted sm:mb-0">{p.text}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </li>
          ))}
        </ul>
        <NoteLine>Personal data is removed before anything is stored, and only commercial facts are held: no technical specifications.</NoteLine>
      </PageSection>

      <ContentSection title="How a request looks">
        <p className="m-0 text-body text-ink-muted">Every request carries the key in a header. A key is read-only, has the scopes it was made with, and expires after a year.</p>
        <pre className="m-0 overflow-x-auto rounded-md bg-surface-inset p-4 font-mono text-mono"><code>{'GET /v1/opportunities?country=PL&cpv=35&limit=100\nAuthorization: Bearer dgk_<prefix>_<secret>'}</code></pre>
        <p className="m-0 text-body text-ink-muted">
          A key makes up to 60 requests a minute and 10,000 a day unless the licence says otherwise; over that the answer is 429 with
          Retry-After. Keys are made, listed and revoked by the account that holds the licence, under API keys in the account area,
          and each one is shown only once. The address to call is given with the licence.
        </p>
      </ContentSection>

      <ContentSection title="Sources and credit">
        <p className="m-0 text-body text-ink-muted">
          A key reads only the sources whose terms allow reuse in a paid service, starting with TED (Tenders Electronic Daily, the EU’s
          procurement journal). Sources are added as their terms are confirmed. Records are changed from the original notice:
          fields are mapped to one shape, classified, and contact details are removed.
        </p>
        <p className="m-0 text-body text-ink-muted">
          Every record carries <code className="font-mono text-mono">attribution</code>, the credit line its source asks for (for TED,
          “© European Union”), and <code className="font-mono text-mono">source_url</code>, the original notice. Wherever you show or pass on
          the data, show its credit line and say that it was changed if you changed it. Do not suggest that a source endorses you.
        </p>
      </ContentSection>

      <ContentSection title="Licence">
        <p className="m-0 text-body text-ink-muted">
          The API is offered as a yearly licence, alone or with a white-label service. Write to us through the contact details in
          the <Link href="/imprint" className="font-semibold">imprint</Link>, with what you want to build and roughly how many requests a day.
        </p>
      </ContentSection>
    </ContentPage>
  );
}
