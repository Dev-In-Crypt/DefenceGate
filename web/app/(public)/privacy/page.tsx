import type { Metadata } from 'next';
import Link from 'next/link';
import { buildMetadata } from '@/lib/seo';
import { Callout, Clause, ClauseList } from '@/components/dg/blocks';
import { ContentPage, Placeholder } from '@/components/dg/content-page';

export const revalidate = 3600;

export const metadata: Metadata = buildMetadata({
  title: 'Privacy notice',
  description: 'What personal data DefenceGate processes when you visit the site or use an account, why, for how long, and your rights.',
  path: '/privacy',
});

const P = 'm-0';

export default function PrivacyPage() {
  return (
    <ContentPage
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Privacy notice', href: '/privacy' }]}
      title="Privacy notice"
      lead="Version 1.1, published 12 October 2026. It says what happens today and what will apply once sign-in opens. It is updated before anything that changes it goes live."
    >
      <Callout title="In short">
        <ClauseList items={[
          'Browsing needs no account and sets no cookie.',
          'No advertising, no third-party trackers, no analytics script and no analytics cookie.',
          'Visits are counted by page only, by our own server, with no identifier, no address and no user agent stored.',
          'The hosting server keeps ordinary access logs.',
          'A sign-in account, when it opens, uses a one-time e-mail link. There is no password and no tracking pixel in our mail.',
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

      <Clause n={3} title="Visit statistics">
        <p className={P}>We count page views to see which parts of the service are used. Our own server adds one to a daily counter for the page (for example <span className="font-mono">/tenders/[slug]</span>, not the individual notice), the host of the site you came from (for example <span className="font-mono">www.google.com</span>, never the full address or your search words) and whether the device is a phone or not.</p>
        <p className={P}>No cookie is set, no script runs in your browser, and no IP address, user agent or identifier is stored with the count, so it cannot be traced to a person. Requests that announce themselves as automated are not counted. <strong>Legal basis:</strong> our legitimate interest in knowing how the service is used (Art. 6(1)(f) GDPR); since no personal data is stored you have nothing to opt out of.</p>
      </Clause>

      <Clause n={4} title="Cookies and local storage">
        <p className={P}>While you browse, the site sets no cookies. These are the only items it ever stores in your browser:</p>
        <ClauseList items={[
          <><span className="font-mono">dg-theme</span> (local storage, your device only): your light or dark choice. Kept until you clear your browser data.</>,
          <><span className="font-mono">dg_bind</span> (cookie, first party): only while you sign in. Ties the sign-in link to the browser that asked for it. Expires after 15 minutes.</>,
          <><span className="font-mono">dg_session</span> (cookie, first party): only when you are signed in. Keeps you signed in. Expires after 30 days at most, or after 7 days without use.</>,
        ]} />
        <p className={P}>The two cookies are strictly necessary to provide the sign-in you asked for, so no consent banner is shown. They are never used for tracking.</p>
      </Clause>

      <Clause n={5} title="Accounts and alerts">
        <p className={P}><strong>Sign-in is not open yet.</strong> This section describes what applies once it opens.</p>
        <p className={P}>An account is created when you follow a sign-in link sent to your e-mail address. We then hold:</p>
        <ClauseList items={[
          'your e-mail address;',
          'the choices you make: your role, whether you follow tenders or funding, countries, scope and alert frequency;',
          'what you save: searches, shortlisted notices with the status and note you write, and followed buyers and programmes;',
          'a hash of your session identifier and when it was used.',
        ]} />
        <p className={P}>We do not use passwords. We do not look at what you save for any purpose other than showing it to you and sending the alerts you asked for, and we do not combine it across accounts.</p>
        <p className={P}><strong>Purpose and legal basis:</strong> to provide the account, the dashboard and the alerts (Art. 6(1)(b) GDPR, or, where the contract is with your employer, our legitimate interest in providing it to you, Art. 6(1)(f)). Security measures such as limiting sign-in requests rest on Art. 6(1)(f).</p>
        <p className={P}><strong>Mail:</strong> sign-in links and alert digests are plain text, with no tracking pixel and no link redirection. They are sent through a mail provider acting as our processor: <Placeholder>mail provider to be named when sign-in opens</Placeholder></p>
        <p className={P}><strong>Retention:</strong> your account and what is in it until you delete it. You can download everything we hold and delete the account yourself in Settings; deletion removes it at once, and encrypted backups containing it are overwritten within 30 days. Sign-in links and rate-limit counters are deleted after a day.</p>
        <p className={P}>Providing an e-mail address is necessary to have an account; without it we cannot offer one.</p>
      </Clause>

      <Clause n={6} title="Forms">
        <p className={P}>The waitlist form on the alerts page is not open. Our server receives what you type only in order to check it and then discards it: nothing is stored, logged or passed on.</p>
      </Clause>

      <Clause n={7} title="Personal data in public notices">
        <p className={P}>Public procurement notices are published by public bodies and sometimes name a contact person. Our collection removes names, e-mail addresses and phone numbers of contact persons, and the site is not designed to show them. Buyers and suppliers that are legal entities are shown by name; a sole trader’s name can be the name of the business.</p>
        <p className={P}>Some older source files in our private archive, which is not accessible from the website, may still contain contact details that a publisher placed in a notice. If your personal data is shown or held and you want it removed, write to us using the contact in the imprint.</p>
        <p className={P}><strong>Legal basis:</strong> our legitimate interest in providing access to public procurement information (Art. 6(1)(f) GDPR). You may object at any time (Art. 21).</p>
      </Clause>

      <Clause n={8} title="Who receives data">
        <ClauseList items={[
          'The hosting provider, Hetzner Online GmbH, as a processor: it operates the server we use, located in Finland, and the storage we use for backups, located in the European Union.',
          'Cloudflare, as the provider of the domain name service only. Traffic to the site does not pass through Cloudflare.',
          'The mail provider named in section 5, once sign-in opens.',
        ]} />
        <p className={P}>We do not sell personal data. We do not transfer personal data outside the European Economic Area as part of operating the site.</p>
      </Clause>

      <Clause n={9} title="Your rights">
        <p className={P}>You have the right to access, rectification, erasure, restriction of processing, data portability and to object (Arts. 15 to 21 GDPR). To use them write to the contact in the imprint, or, for an account, use Settings. We reply within one month.</p>
        <p className={P}>You have the right to lodge a complaint with a supervisory authority, in particular in the country where you live or work, or where the operator has its seat.</p>
      </Clause>

      <Clause n={10} title="Automated decisions">
        <p className={P}>We make no decisions about you based solely on automated processing that have legal or similarly significant effects. The defence label on a notice classifies the notice, not a person.</p>
      </Clause>

      <Clause n={11} title="Changes">
        <p className={P}>We update this notice when the site changes. The version and date are at the top. Material changes for account holders are also sent by e-mail.</p>
      </Clause>
    </ContentPage>
  );
}
