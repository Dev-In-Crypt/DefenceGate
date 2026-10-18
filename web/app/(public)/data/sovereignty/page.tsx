import type { Metadata } from 'next';
import Link from 'next/link';
import { buildMetadata } from '@/lib/seo';
import { ContentPage, ContentSection } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Where the data runs',
  description: 'What DefenceGate runs where: the server, the archive and its backups, the domain name service, the certificate, the code, and the one language-model service used to read public call documents. What is in the EU and what is not.',
  path: '/data/sovereignty',
});

/** Read on 18 October 2026: the server's compose file and Caddyfile, the DNS and registry records, the certificate, and the pages' HTML. */
const CHECKED = '18 October 2026';

interface Row { what: string; who: string; where: string; eu: 'Yes' | 'No' | 'Not assessed'; note: string }

const RUNS_IN_THE_EU: Row[] = [
  {
    what: 'Server: the website, the API, the database and the collection jobs',
    who: 'Hetzner Online GmbH', where: 'Helsinki, Finland (the server’s address is registered to Hetzner in Helsinki)', eu: 'Yes',
    note: 'One virtual server. There is no content delivery network or proxy in front of it: visitors connect to it directly.',
  },
  {
    what: 'Archive of source payloads, and database backups',
    who: 'Hetzner Online GmbH (a Storage Box)', where: 'Germany (the box’s address is in Hetzner’s German range; we have not asked Hetzner for the data centre)', eu: 'Yes',
    note: 'Backups made since 12 October 2026 are encrypted before they leave the server; the key is not on the server. Older plaintext dumps age out by 11 November 2026. Production writes the archive to the Storage Box only.',
  },
];

const OUTSIDE_THE_EU: Row[] = [
  {
    what: 'Domain registration and name service (DNS)',
    who: 'Cloudflare, Inc.', where: 'United States company; DNS answers come from its worldwide network', eu: 'No',
    note: 'Cloudflare is the registrar and answers the question “what is the server’s address?”. It can see the address of the resolver that asks. It is not a proxy: pages and API calls do not pass through it.',
  },
  {
    what: 'Certificate for https',
    who: 'Let’s Encrypt (Internet Security Research Group)', where: 'United States organisation', eu: 'No',
    note: 'The server asks it for a certificate for our domain name and renews it. It never sees a page or a visitor. The certificate in use on 18 October 2026 was issued by Let’s Encrypt.',
  },
  {
    what: 'Source code, and the tests run on every change',
    who: 'GitHub (Microsoft)', where: 'United States company', eu: 'No',
    note: 'The code is in a public repository, which is the origin of the server’s copy of it. The tests there run on invented data, not on ours. No visitor data is in the repository.',
  },
  {
    what: 'Reading public call documents to find who may apply',
    who: 'OpenAI', where: 'United States company', eu: 'No',
    note: 'For funding calls whose rules are written in a PDF, the text of that public document is sent to OpenAI’s API with a fixed question. Each answer must quote the document, and a quote that is not found in the document is dropped. Sent: the text of public call documents (and of a topic’s published conditions) and our instructions. Not sent: visitor data, account data, profiles from the readiness check, or anything from the database other than the document. We ask that OpenAI does not store the request (the API’s store option is off). A monthly spending cap applies. This is the only language-model service we use.',
  },
  {
    what: 'Operator alerts',
    who: 'Telegram', where: 'Not assessed', eu: 'Not assessed',
    note: 'A short text goes to the operator’s chat when a collection job fails or a backup is late. The texts describe jobs and sources, not visitors. We have not assessed where Telegram processes messages.',
  },
];

function Table({ rows }: { rows: Row[] }) {
  return (
    <ul className="m-0 flex list-none flex-col gap-3 p-0">
      {rows.map((r) => (
        <li key={r.what} className="flex min-w-0 flex-col gap-1 rounded-md bg-surface-inset p-4">
          <p className="m-0 text-body font-semibold">{r.what}</p>
          <dl className="m-0 grid gap-1 text-small sm:grid-cols-[120px_minmax(0,1fr)]">
            <dt className="font-semibold">Provider</dt><dd className="m-0">{r.who}</dd>
            <dt className="font-semibold">Where</dt><dd className="m-0">{r.where}</dd>
            <dt className="font-semibold">In the EU</dt><dd className="m-0">{r.eu}</dd>
          </dl>
          <p className="m-0 text-small text-ink-muted">{r.note}</p>
        </li>
      ))}
    </ul>
  );
}

export default function SovereigntyPage() {
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Source status', href: '/data' }, { label: 'Where the data runs', href: '/data/sovereignty' }]}
      title="Where the data runs"
      lead={`What DefenceGate runs where, as read on ${CHECKED}. The site and its data are on servers in the EU. Some services we depend on are not: they are listed below, with what each one sees.`}
    >
      <ContentSection title="In the EU">
        <Table rows={RUNS_IN_THE_EU} />
      </ContentSection>

      <ContentSection title="Not in the EU, or not assessed">
        <Table rows={OUTSIDE_THE_EU} />
      </ContentSection>

      <ContentSection title="What your browser loads">
        <p className="m-0 text-body">
          The pages load their scripts, styles and fonts from our own server. The fonts are copied into the site when it is built; a visitor’s browser does not contact
          Google Fonts. The site sets no tracking cookies and loads no analytics, advertising or social-media code. Its content security policy only allows requests to our own address.
          We count page views by page, day and kind of referrer without an identifier (see the <Link href="/privacy" className="font-semibold">privacy notice</Link>).
        </p>
        <p className="m-0 text-body">
          We checked the home page and a call page: the HTML names no resource from another host. A call page links to the source’s own website; that is a link you choose to follow.
        </p>
        <p className="m-0 text-small text-ink-muted">At build time, on the server, the build tool downloads the fonts from Google and the code libraries from the npm registry. No visitor data is involved.</p>
      </ContentSection>

      <ContentSection title="What this does not say">
        <ul className="m-0 flex list-none flex-col gap-2 p-0 text-body">
          <li>It does not say that no US company is in the path: the services above are US companies, and the list says which do what.</li>
          <li>It does not say who can be compelled by which country’s law. A server in the EU run by an EU company is one fact; the law that applies to it is another, and we do not give legal advice.</li>
          <li>Account sign-in by e-mail is not open. When it opens, the mail provider will be named in the privacy notice and here.</li>
          <li>Where the answer is “not assessed”, we have not checked it.</li>
        </ul>
      </ContentSection>
    </ContentPage>
  );
}
