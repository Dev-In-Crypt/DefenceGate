import type { Metadata } from 'next';
import Link from 'next/link';
import { getAccountStatus } from '@/lib/account';
import { buildMetadata } from '@/lib/seo';
import { Callout, Clause, ClauseGroup, ClauseList } from '@/components/dg/blocks';
import { ContentPage } from '@/components/dg/content-page';

// WP-140: rendered per request (was revalidate 3600), so section 5 follows /v1/account/status (itself cached 60 s): a
// page built while accounts were closed must not keep "Sign-in is not open yet" for an hour after they open.
export const dynamic = 'force-dynamic';

export const metadata: Metadata = buildMetadata({
  title: 'Privacy notice',
  description: 'What personal data DefenceGate processes when you visit the site or use an account, why, for how long, and your rights.',
  path: '/privacy',
  // Not indexed while the imprint has no provider details.
  noindex: true,
});

const P = 'm-0';
// WP-140, section 7: the pl_ezam raw re-strip approved on 25 October 2026. TODO(orchestrator): once its result is
// confirmed, set the date (for example 'on 26 October 2026') here and in docs/legal/versions/privacy-v1.7-2026-10-26.md;
// if it did not complete, take the sentence out of both before deploying.
const EZAM_CLEANED = 'in October 2026';

export default async function PrivacyPage() {
  // WP-140: "Sign-in is not open yet" stays in section 5 until the API says accounts are open (in production only once
  // the owner sets DGATE_ACCOUNTS_OPEN=1, backend accounts.accounts_problem). Any failure reads as closed.
  const { open } = await getAccountStatus();
  return (
    <ContentPage
      toc
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Privacy notice', href: '/privacy' }]}
      title="Privacy notice"
      lead="Version 1.7, published 26 October 2026 (accounts with an e-mail address and a password). It says what happens today and what will apply once sign-in opens. It is updated before anything that changes it goes live."
    >
      <Callout title="In short">
        <ClauseList items={[
          'Browsing needs no account and sets no cookie.',
          'No advertising, no third-party trackers, no analytics script and no analytics cookie.',
          'Visits are counted by our own server, by page, by the kind of site you came from and by phone or computer, with no identifier, no address and no user agent stored.',
          'The hosting server keeps ordinary access logs for at most 14 days.',
          'An account, when accounts open, uses your e-mail address and a password, which we keep only as a one-way hash. Two-step sign-in with an authenticator app is optional. Our mail has no tracking pixel and no link tracking.',
          'The notices we show are public. Our collection drops the contact fields a source publishes and removes e-mail addresses from free text. Older records in our private archive still contain some, and some buyer names contain a telephone, fax or e-mail block as the source wrote it; none of it is shown (section 7).',
        ]} />
      </Callout>

      <ClauseGroup>
      <Clause n={1} title="Who is responsible">
        <p className={P}>The controller is the operator identified in the <Link href="/imprint" className="font-semibold">imprint</Link>. The imprint is where the name, address and contact for privacy matters are given and, where one is required, the representative in the Union and the data protection officer.</p>
      </Clause>

      <Clause n={2} title="When you visit the site">
        <p className={P}>When your browser loads a page, the server and the reverse proxy in front of it record the technical details of the request: your IP address, the time, the address requested, the response code, the size, your browser’s headers (including user agent and referrer) and the full address requested, including any search words in it.</p>
        <p className={P}><strong>Purpose:</strong> deliver the site, keep it secure and find abuse. <strong>Legal basis:</strong> our legitimate interest in a secure and working service (Art. 6(1)(f) GDPR). <strong>Retention:</strong> request log lines are deleted after 14 days at the latest: a clean-up job runs every hour and removes older lines and files.</p>
        <p className={P}>Providing this data is technically necessary to receive the site.</p>
      </Clause>

      <Clause n={3} title="Visit statistics">
        <p className={P}>We count page views to see which parts of the service are used. Our own server adds one to a daily counter for the page (for example <span className="font-mono">/tenders/[slug]</span>, not the individual notice), the site you came from, only when it is one of a short list of well-known ones such as search engines (for example <span className="font-mono">google.com</span>) and otherwise just “other” (never the full address or your search words), and whether the device is a phone or not.</p>
        <p className={P}>No cookie is set, no script runs in your browser, and no IP address, user agent or identifier is stored with the count, so it cannot be traced to a person. Requests that announce themselves as automated are not counted. <strong>Legal basis:</strong> our legitimate interest in knowing how the service is used (Art. 6(1)(f) GDPR); since no personal data is stored you have nothing to opt out of. To stop one address from inflating the count, the server keeps the address in memory for at most a minute and counts a limited number of views from it; it is never written to disk or stored with the count.</p>
      </Clause>

      <Clause n={4} title="Cookies and local storage">
        <p className={P}>While you browse, the site sets no cookies. These are the only items it ever stores in your browser:</p>
        <ClauseList items={[
          <><span className="font-mono">dg-theme</span> (local storage, your device only): your light or dark choice. Kept until you clear your browser data.</>,
          <><span className="font-mono">dg.profile.v1</span> (local storage, your device only): only if you use the readiness check or the supplier profile, the answers you give there (for example a company name, its country, its staff count, product codes and certificates). They are kept in your browser; we do not keep them. To compute a result, a page that shows one for your saved answers (the results, the report, the funding list and a call page) sends our server the answers the rules read: the country where your company is established, its kind and legal form, the staff count of your organisation and, for a group, of the whole group, where it is managed and who owns or controls it, where its components come from, your consortium partners and SAFE role, classified work, the export regime and export plans, your answers to the supplier page’s questions for your country and which certificates and registrations you hold. If you chose product codes (CPV) on the supplier page, a second request sends those codes, the seven countries of the demand map and your own country when it is one of them. The company name is never sent, nor the processes, region, NACE code, investor country or topics you may enter. The server uses the answers for that result only and neither stores nor logs them. If you choose to put organisations from your country first in a call’s partner suggestions, your country’s two-letter code is sent in the address of that request, which the access log keeps (section 2). You can delete the answers with &ldquo;Clear my answers&rdquo; in the readiness check, or by clearing your browser data.</>,
          <><span className="font-mono">dg-answer:</span> items (session storage, this browser tab only): the answers to those two requests, for ten minutes, so that the results page and the report do not ask our server twice. They are deleted when the tab is closed.</>,
          <><span className="font-mono">__Host-dg_mfa</span> (cookie, first party): only while you sign in to an account with two-step sign-in on, between your password and your code. Holds a single-use ticket. Expires after 5 minutes.</>,
          <><span className="font-mono">__Host-dg_session</span> (cookie, first party): only when you are signed in. Keeps you signed in. Expires after 30 days at most, or after 7 days without use.</>,
        ]} />
        <p className={P}>The two cookies are strictly necessary to provide the sign-in you asked for, so no consent banner is shown. They are never used for tracking.</p>
      </Clause>

      <Clause n={5} title="Accounts and alerts">
        {!open && <p className={P} data-signin-closed><strong>Sign-in is not open yet.</strong> This section describes what applies once it opens.</p>}
        <p className={P}>You create an account with your e-mail address and a password, and confirm the address through a link we send to it. You sign in with the address and the password. We then hold:</p>
        <ClauseList items={[
          'your e-mail address, when the account was created, when the address was confirmed and when you last visited;',
          'your password as an Argon2id hash (a salted, one-way form from which the password cannot be read back), and when it was last changed. The password itself is never stored or logged;',
          'if you turn on two-step sign-in: the key of your authenticator app, encrypted with a key that is not kept in the database, the last code period used (so that each code works once) and when you turned it on, and ten recovery codes as keyed hashes (HMAC), each marked when used. Turning it off deletes them;',
          'the version of the terms of use and of this notice you accepted, and when;',
          'if you came from our pricing page: the plan and billing period you picked, so that we can show it to you again. Choosing a plan charges nothing and gives no paid plan; until payment opens every account is on the free plan;',
          'the choices you make: your role, whether you follow tenders or funding, countries, scope and alert frequency;',
          'what you save: searches with the name you give them and when they were last alerted, shortlisted notices with the status and note you write, and followed buyers and programmes;',
          'the links we mail you, to confirm your address (valid 24 hours) or to set a new password (valid one hour), and the ticket between your password and your code (valid 5 minutes): each works once and is held only as a hash;',
          'for up to a day: keyed hashes (HMAC) of your e-mail address and of your IP address with the time, kept only to limit how often account mails can be requested and to slow down failed sign-ins (after five failed attempts for one address in an hour, each further attempt has to wait longer, up to an hour);',
          'a hash of your session identifier and when it was used;',
          'a security log of what happens to your account (for example a sign-in, a failed sign-in, a password change or the deletion) with the account’s internal number and the time, never your e-mail address, your IP address or your password. It is kept in our server’s log for at most 90 days.',
        ]} />
        <p className={P}>We do not look at what you save for any purpose other than showing it to you and sending the alerts you asked for, and we do not combine it across accounts.</p>
        <p className={P}><strong>Purpose and legal basis:</strong> to provide the account, the dashboard and the alerts (Art. 6(1)(b) GDPR, or, where the contract is with your employer, our legitimate interest in providing it to you, Art. 6(1)(f)). Security measures such as limiting account mails and failed sign-ins and the security log rest on Art. 6(1)(f).</p>
        <p className={P}><strong>Mail:</strong> the confirmation and password links, a notice when your password is changed or reset, and alert digests are sent as plain text with an HTML version of the same text, with no tracking pixel, no images and no link redirection. They are sent through Brevo (Sendinblue SAS, France), acting as our processor.</p>
        <p className={P}><strong>Retention:</strong> your account and what is in it until you delete it. You can download everything we hold and delete the account yourself in Settings; deletion removes it at once, together with your password hash, two-step key, recovery codes, sessions and unused links, and encrypted backups containing it are overwritten within 30 days. To delete the account you type your e-mail address and your password. An account whose address is not confirmed within two days is deleted. Links and tickets are deleted a day after they expire, and the rate-limit and failed sign-in counters after about a day.</p>
        <p className={P}>Providing an e-mail address and a password is necessary to have an account; without them we cannot offer one.</p>
      </Clause>

      <Clause n={6} title="Forms">
        <p className={P}>The site has no waiting-list and no contact form. What you type into a search or a filter goes into the address of the page you open, which the access log keeps for up to 14 days (section 2). The readiness check and the supplier profile are described in section 4, the account forms in section 5.</p>
      </Clause>

      <Clause n={7} title="Personal data in public notices">
        <p className={P}>Public procurement notices and funding calls are published by public bodies and sometimes name a contact person. We republish them as business information about who buys and who funds what.</p>
        <ClauseList items={[
          <><strong>What we hold.</strong> The notice fields. Our collection drops the contact fields a source publishes (names, e-mail addresses, telephone numbers) and removes e-mail addresses from free text; a name or number typed into a description by the publisher is not removed. The site is not designed to show contact persons. Buyers and suppliers that are legal entities are shown by name; a sole trader’s name can be the name of the business. We keep the registration numbers of companies, never a person’s. Participants in EU-funded projects come from the public data the European Commission publishes (CORDIS, EDF); a few of them are individuals or sole traders and appear as the Commission publishes them.</>,
          <><strong>Where it comes from.</strong> From the public source of the notice, never from you.</>,
          <><strong>Why and on what basis.</strong> To give businesses access to public procurement information in one place: our legitimate interest, and the interest of users and of the public in transparent public procurement (Art. 6(1)(f) GDPR).</>,
          <><strong>Who sees it.</strong> Anyone who visits the site; it is public by design. Our hosting provider processes it for us.</>,
          <><strong>Archive.</strong> We keep a private, append-only archive of earlier versions of notices so that changes can be shown. Parts of it still contain contact details a publisher placed in a notice: in the raw store that the collection lands first, up to about 12,600 TED records landed until 21 October 2026 that hold contact fields the collection now removes (counted on 22 October 2026), and the Spanish notices (PLACSP) collected before 12 October 2026, which were not counted and have not been cleaned since; and in our list of organisations, about 960 names of public buyers (with about 1,130 spellings) that contain a telephone, fax or e-mail block as the source wrote it, which we keep as published. The Polish result notices (e-Zamówienia) landed in the raw store until 21 October 2026, which named the winners, natural persons among them, were cleaned again {EZAM_CLEANED}. The website does not show any of them. They are kept as long as the archive is kept, and we redact them earlier on a valid request or where the law requires.</>,
          <><strong>Telling you.</strong> We do not write to each person named in a public notice; that would take disproportionate effort, so, as Art. 14(5)(b) GDPR provides, we make this information publicly available here and take the measures described in this section.</>,
          <><strong>Your rights.</strong> You may object at any time (Art. 21), ask for access, correction or erasure (Arts. 15 to 17) and complain to a supervisory authority. On a valid objection or request we will stop showing or correct the data without undue delay after verifying the request, and we redact the archive where the law requires. See term 19 of the <Link href="/terms" className="font-semibold">terms</Link> and section 9.</>,
        ]} />
      </Clause>

      <Clause n={8} title="Who receives data">
        <ClauseList items={[
          'Every visitor to the site: public notice data is public by design (section 7).',
          'The hosting provider, Hetzner Online GmbH, as a processor: it operates the server we use, located in Finland, and the storage we use for backups, located in the European Union.',
          'Cloudflare, Inc. (USA), as the provider of the domain name service only: it answers requests for the domain’s address and can see the address of the resolver that asks. Traffic to the site does not pass through Cloudflare.',
          'Brevo (Sendinblue SAS, France), as the processor that sends our mail (section 5).',
          'OpenAI (United States), as a processor: it receives the text of public funding call documents, to read who may apply, and of the European Defence Fund’s published project fact sheets, which name the organisations in each project’s consortium, to read that list. It processes them in the United States; we ask it not to store the requests. We send it nothing about visitors or account holders.',
        ]} />
        <p className={P}>We do not sell personal data. We disclose data to an authority where the law requires it.</p>
      </Clause>

      <Clause n={9} title="Your rights">
        <p className={P}>You have the right to access, rectification, erasure, restriction of processing, data portability and to object (Arts. 15 to 21 GDPR). To use them write to the contact in the <Link href="/imprint" className="font-semibold">imprint</Link>, or, for an account, use Settings. We may ask for what we need to confirm who you are. We reply within one month; where a request is complex or there are many, we may extend that by up to two further months and will tell you why. If we do not act on a request we say why and tell you that you may complain to a supervisory authority or go to court. Where the law lets us refuse (for example for freedom of expression and information, or for the establishment or defence of legal claims) we say which ground we rely on.</p>
        <p className={P}>Where erasure is due we remove the data from the site and redact it in the archive without undue delay after verifying the request. Backups containing it cannot be edited and are overwritten within 30 days.</p>
        <p className={P}>You have the right to lodge a complaint with a supervisory authority, in particular in the country where you live or work, where the alleged infringement took place, or where the operator has its seat, as stated in the imprint.</p>
      </Clause>

      <Clause n={10} title="Automated decisions">
        <p className={P}>We make no decisions about you based solely on automated processing that have legal or similarly significant effects. The defence label on a notice classifies the notice, not a person.</p>
      </Clause>

      <Clause n={11} title="Changes">
        <p className={P}>We update this notice when the site changes. The version and date are at the top, and earlier versions are kept and available on request. Material changes for account holders are also sent by e-mail.</p>
      </Clause>
      </ClauseGroup>
    </ContentPage>
  );
}
