import type { Metadata } from 'next';
import Link from 'next/link';
import { buildMetadata } from '@/lib/seo';
import { Callout, Clause, ClauseList } from '@/components/dg/blocks';
import { ContentPage, Placeholder } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Privacy notice',
  description: 'What personal data DefenceGate processes when you visit the site, why, for how long, and your rights.',
  path: '/privacy',
});

const P = 'm-0';

export default function PrivacyPage() {
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Privacy notice', href: '/privacy' }]}
      title="Privacy notice"
      lead="Version 1.0, published 12 October 2026. This notice describes what the site does today. It is updated before any feature that changes it goes live."
    >
      <Callout title="In short">
        <ClauseList items={[
          'No account is needed to browse and none can be created today.',
          'No advertising, no third-party trackers and no analytics cookies.',
          'The site sets no cookies. Your light or dark theme choice stays on your device.',
          'The hosting server keeps ordinary access logs. That is the personal data this site processes about visitors.',
          'The notices we show are public. We remove contact persons’ names, e-mail addresses and phone numbers when we collect them.',
        ]} />
      </Callout>

      <Clause n={1} title="Who is responsible">
        <p className={P}>The controller is the operator named in the <Link href="/imprint" className="font-semibold">imprint</Link>. Name, address and contact: <Placeholder>to be provided in the imprint</Placeholder></p>
      </Clause>

      <Clause n={2} title="When you visit the site">
        <p className={P}>When your browser loads a page, the server and the reverse proxy in front of it record the technical details of the request: your IP address, the time, the address requested, the response code, the size and your browser’s user-agent and referrer text.</p>
        <p className={P}><strong>Purpose:</strong> deliver the site, keep it secure and find abuse. <strong>Legal basis:</strong> our legitimate interest in a secure and working service (Art. 6(1)(f) GDPR). <strong>Retention:</strong> the log files are rotated automatically and old files are overwritten. <Placeholder>maximum retention period to be fixed by the operator</Placeholder></p>
        <p className={P}>Providing this data is technically necessary to receive the site.</p>
      </Clause>

      <Clause n={3} title="Cookies and local storage">
        <p className={P}>The site sets no cookies. It stores one item in your browser’s local storage: your choice of light or dark theme. It stays on your device, is not sent to us and is kept until you clear your browser data. It is stored because you asked for it by using the theme switch.</p>
      </Clause>

      <Clause n={4} title="Forms">
        <p className={P}>The waitlist form on the alerts page is not open. Our server receives what you type only in order to check it and then discards it: nothing is stored, logged or passed on.</p>
      </Clause>

      <Clause n={5} title="Personal data in public notices">
        <p className={P}>Public procurement notices are published by public bodies and sometimes name a contact person. Our collection removes names, e-mail addresses and phone numbers of contact persons, and the site is not designed to show them. Buyers and suppliers that are legal entities are shown by name; a sole trader’s name can be the name of the business.</p>
        <p className={P}>Some older source files in our private archive, which is not accessible from the website, may still contain contact details that a publisher placed in a notice. If your personal data is shown or held and you want it removed, write to us using the contact in the imprint.</p>
        <p className={P}><strong>Legal basis:</strong> our legitimate interest in providing access to public procurement information (Art. 6(1)(f) GDPR). You may object at any time (Art. 21).</p>
      </Clause>

      <Clause n={6} title="Who receives data">
        <ClauseList items={[
          'The hosting provider, Hetzner Online GmbH, as a processor: it operates the server we use, located in Finland, and the storage we use for backups, located in the European Union.',
          'Cloudflare, as the provider of the domain name service only. Traffic to the site does not pass through Cloudflare.',
        ]} />
        <p className={P}>We do not sell personal data. We do not transfer personal data outside the European Economic Area as part of operating the site.</p>
      </Clause>

      <Clause n={7} title="Accounts, alerts and statistics">
        <p className={P}>The site has no accounts, alerts or visit statistics today. When we introduce any of them, this notice will be updated and the date and version will change before the feature goes live.</p>
      </Clause>

      <Clause n={8} title="Your rights">
        <p className={P}>You have the right to access, rectification, erasure, restriction of processing, data portability and to object (Arts. 15 to 21 GDPR). To use them write to the contact in the imprint. We reply within one month.</p>
        <p className={P}>You have the right to lodge a complaint with a supervisory authority, in particular in the country where you live or work, or where the operator has its seat.</p>
      </Clause>

      <Clause n={9} title="Automated decisions">
        <p className={P}>We make no decisions about you based solely on automated processing that have legal or similarly significant effects. The defence label on a notice classifies the notice, not a person.</p>
      </Clause>

      <Clause n={10} title="Changes">
        <p className={P}>We update this notice when the site changes. The version and date are at the top.</p>
      </Clause>
    </ContentPage>
  );
}
