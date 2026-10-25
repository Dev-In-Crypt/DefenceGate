# Privacy notice, version 1.7: DRAFT for the owner's approval (WP-123, 25 October 2026)

**Not published.** The page `web/app/(public)/privacy/page.tsx` keeps version 1.6 (published 24 October 2026) until the
owner approves this text. Accounts with a password stay closed until it is published: the API compares
`PRIVACY_VERSION` (now "1.6") with `PASSWORD_PRIVACY_VERSION` ("1.7") in `backend/dgate/accounts.py`.

To publish: put the approved text into the page, set its date in the lead, set `PRIVACY_VERSION = "1.7"` (and
`TERMS_VERSION = "2.2"` if the terms draft is approved with it), copy the final text to
`docs/legal/versions/privacy-v1.7-<date>.md`, and add the line to `docs/legal/versions/README.md`. Name the mail
provider in section 5 and 8 first (it is a processor and needs a data processing agreement).

Built from version 1.6 as it stands on integration (445c1e5). Sections 1, 2, 3, 9, 10 and 11 are word for word those of
1.6 and are not repeated here. Section 8 changes in two items. WP-131 (round-7 legal-content audit of 25 October 2026,
evidence `D:\DEFENCEGATE TESTS\verify-oct25\r7-legal-content\problems.csv`) adds the changes marked **[WP-131]** below:
the readiness answers that are really sent, the storage items the code really sets, no waiting-list form, the contact data
in the archive as `docs/DATA_PROTECTION.md` states it, and OpenAI as the only language-model service configured.

## What changes, sentence by sentence

| Where | 1.6 (in force) | 1.7 (draft) |
|---|---|---|
| Lead | "Version 1.6, published 24 October 2026 (the sign-in cookie also holds the account page to return to). ..." | "Version 1.7, published [date] (accounts with an e-mail address and a password). It says what happens today and what will apply once sign-in opens. It is updated before anything that changes it goes live." |
| In short, 5th item | "A sign-in account, when it opens, uses a one-time e-mail link. There is no password and no tracking pixel in our mail." | "An account, when accounts open, uses your e-mail address and a password, which we keep only as a one-way hash. Two-step sign-in with an authenticator app is optional. Our mail has no tracking pixel and no link tracking." |
| 4, cookie list | `__Host-dg_bind`: "only while you sign in. Ties the sign-in link to the browser that asked for it and, if you were opening a page of your account, holds that page's address ... Expires after 15 minutes." | `__Host-dg_mfa`: "only while you sign in to an account with two-step sign-in on, between your password and your code. Holds a single-use ticket. Expires after 5 minutes." (`__Host-dg_session` and the sentence after the list unchanged.) |
| 5, opening | "An account is created when you follow a sign-in link sent to your e-mail address. We then hold:" | "You create an account with your e-mail address and a password, and confirm the address through a link we send to it. You sign in with the address and the password. We then hold:" |
| 5, item 1 | "your e-mail address, when the account was created and when you last visited;" | "your e-mail address, when the account was created, when the address was confirmed and when you last visited;" |
| 5, new item | none | "your password as an Argon2id hash (a salted, one-way form from which the password cannot be read back), and when it was last changed. The password itself is never stored or logged;" |
| 5, new item | none | "if you turn on two-step sign-in: the key of your authenticator app, encrypted with a key that is not kept in the database, the last code period used (so that each code works once) and when you turned it on, and ten recovery codes as keyed hashes (HMAC), each marked when used. Turning it off deletes them;" |
| 5, new item | none | "if you came from our pricing page: the plan and billing period you picked, so that we can show it to you again. Choosing a plan charges nothing and gives no paid plan; until payment opens every account is on the free plan;" |
| 5, new item | none | "the links we mail you, to confirm your address (valid 24 hours) or to set a new password (valid one hour), and the ticket between your password and your code (valid 5 minutes): each works once and is held only as a hash;" |
| 5, counters item | "for up to a day: your e-mail address with the one-time link, and a keyed hash (HMAC) of your e-mail address and of your IP address, kept only to limit how often links can be requested;" | "for up to a day: keyed hashes (HMAC) of your e-mail address and of your IP address with the time, kept only to limit how often account mails can be requested and to slow down failed sign-ins (after five failed attempts for one address in an hour, each further attempt has to wait longer, up to an hour);" |
| 5, new item | none | "a security log of what happens to your account (for example a sign-in, a failed sign-in, a password change or the deletion) with the account's internal number and the time, never your e-mail address, your IP address or your password. It is kept in our server's log for at most 90 days;" |
| 5, after the list | "We do not use passwords. We do not look at what you save ..." | "We do not look at what you save ..." (first sentence removed) |
| 5, legal basis | "... Security measures such as limiting sign-in requests rest on Art. 6(1)(f)." | "... Security measures such as limiting account mails and failed sign-ins and the security log rest on Art. 6(1)(f)." |
| 5, Mail | "sign-in links and alert digests are plain text, with no tracking pixel and no link redirection. They will be sent through a mail provider acting as our processor. None has been chosen yet, which is why sign-in is not open; the provider will be named here before it opens." | "the confirmation and password links, a notice when your password is changed or reset, and alert digests are sent as plain text with an HTML version of the same text, with no tracking pixel, no images and no link redirection. They are sent through Brevo (Sendinblue SAS, France), acting as our processor." |
| 5, Retention | "... deletion removes it at once, and encrypted backups containing it are overwritten within 30 days. Sign-in links and rate-limit counters are deleted after about a day." | "... deletion removes it at once, together with your password hash, two-step key, recovery codes, sessions and unused links, and encrypted backups containing it are overwritten within 30 days. To delete the account you type your e-mail address and your password. An account whose address is not confirmed within two days is deleted. Links and tickets are deleted a day after they expire, and the rate-limit and failed sign-in counters after about a day." |
| 5, last | "Providing an e-mail address is necessary to have an account; without it we cannot offer one." | "Providing an e-mail address and a password is necessary to have an account; without them we cannot offer one." |
| 8, mail item | "The mail provider named in section 5, once sign-in opens." | "Brevo (Sendinblue SAS, France), as the processor that sends our mail (section 5)." |

### [WP-131] Further changes (round-7 legal-content audit, 25 October 2026)

Each row: the sentence of 1.6, the draft sentence, and why (the code or the inventory it is read from).

| Where | 1.6 (in force) | 1.7 (draft) | Why |
|---|---|---|---|
| In short, 6th item | "The notices we show are public. We do not keep the contact fields a source publishes, and we remove e-mail addresses from free text. A small number of older records in our private archive still contain them; they are not shown (section 7)." | "The notices we show are public. Our collection drops the contact fields a source publishes and removes e-mail addresses from free text. Older records in our private archive still contain some, and some buyer names contain a telephone, fax or e-mail block as the source wrote it; none of it is shown (section 7)." | "a small number of older records" is narrower than the inventory: about 100 TED payloads, the Spanish payloads landed before 12 Oct (not counted), 221 archive versions, about 1,000 organisation names (`docs/DATA_PROTECTION.md`, "What is actually held") |
| 4, `dg.profile.v1` | "... the answers you give there (for example a company name, its country and size, product codes and certificates). They stay in your browser: we do not see them and do not keep them. To compute a result they are sent once to our server, used for that answer only and neither stored nor logged. ..." | see section 4 below | the request carries the staff counts (`web/lib/profile.ts` `applicantFields`: `headcount`, `group_headcount`), never the company name; the demand map sends the CPV codes, seven countries and the own country (`web/lib/demand.ts` `demandRequest`); the request is repeated on every page that shows a result for the saved profile (results, report, funding list, call page: `use-readiness.ts`, `fit-store.ts`, `call-readiness.tsx`), not "once"; the partner suggestions put the country in the address (`?prefer=XX`, `partner-suggestions.tsx`), which the access log keeps (section 2). The list is the one the site prints since WP-131 (`web/lib/sent-copy.ts`, checked against the request builders by `web/lib/wp131.check.ts`) |
| 4, new item | none | `dg-answer:` items (session storage, this tab only) | `web/lib/answer-cache.ts` (WP-105) keeps the answers of those requests for ten minutes in the tab; not listed in 1.6 |
| 4, `__Host-dg_bind` | the sign-in-link cookie | removed (see the WP-123 row above: `__Host-dg_mfa` instead) | no code sets `__Host-dg_bind` any more (`web/lib/account.ts`: `SESSION_COOKIE`, `SECOND_STEP_COOKIE` only) |
| 6, Forms | "The waitlist form on the alerts page is not open. Our server receives what you type only in order to check it and then discards it: nothing is stored, logged or passed on." | see section 6 below | the waitlist form was removed (`web/app/(public)/alerts/page.tsx`: "a dead waitlist form before"); the search and filter forms are GET forms, so what is typed is in the address the access log keeps |
| 7, Archive | "... Some older records in the archive, in the raw store that the collection lands first and in the history of notices may still contain contact details a publisher placed in a notice; they are a small number. The website does not show them. ..." | see section 7 below | `docs/DATA_PROTECTION.md` rows "Raw store", "`opportunity_version.payload`" and "`organisation.canonical_name` ..." (owner decision of 24 Oct 2026: the blocks are kept, left out of the matching key, not served) |
| 8, AI item | "Artificial-intelligence services we choose (for example OpenAI or Anthropic) may process the text of public documents we collect, such as funding call documents and project factsheets, to read information from them; they may process it outside the European Economic Area. We send them nothing about visitors or account holders." | see section 8 below | only OpenAI is configured (`backend/dgate/llm.py`; `backend/dgate/config.py`: `DGATE_OPENAI_API_KEY`, `DGATE_OPENAI_MODEL`); the Anthropic client of `backend/dgate/enrichment/runner.py` has no key setting and is not scheduled; the fact sheets go to the model in `backend/dgate/networks.py` (`llm.complete_json`). /data/sovereignty says the same since WP-131 |
| 8, transfer basis | none | **owner and lawyer:** the transfer basis for OpenAI (for example the EU-US Data Privacy Framework, if OpenAI is certified, or the standard contractual clauses of its data processing addendum) | a processor outside the EEA needs a stated safeguard (Art. 13(1)(f) GDPR); not decided here |

## Sections 4 and 5 as they would read

### 4. Cookies and local storage

While you browse, the site sets no cookies. These are the only items it ever stores in your browser:

- `dg-theme` (local storage, your device only): your light or dark choice. Kept until you clear your browser data.
- `dg.profile.v1` (local storage, your device only): only if you use the readiness check or the supplier profile, the
  answers you give there (for example a company name, its country, its staff count, product codes and certificates).
  They are kept in your browser; we do not keep them. **[WP-131]** To compute a result, a page that shows one for your
  saved answers (the results, the report, the funding list and a call page) sends our server the answers the rules read:
  the country where your company is established, its kind and legal form, the staff count of your organisation and, for a
  group, of the whole group, where it is managed and who owns or controls it, where its components come from, your
  consortium partners and SAFE role, classified work, the export regime and export plans, your answers to the supplier
  page's questions for your country and which certificates and registrations you hold. If you chose product codes (CPV)
  on the supplier page, a second request sends those codes, the seven countries of the demand map and your own country
  when it is one of them. The company name is never sent, nor the processes, region, NACE code, investor country or
  topics you may enter. The server uses the answers for that result only and neither stores nor logs them. If you choose
  to put organisations from your country first in a call's partner suggestions, your country's two-letter code is sent
  in the address of that request, which the access log keeps (section 2). You can delete the answers with "Clear my
  answers" in the readiness check, or by clearing your browser data.
- **[WP-131]** `dg-answer:` items (session storage, this browser tab only): the answers to those two requests, for ten
  minutes, so that the results page and the report do not ask our server twice. They are deleted when the tab is closed.
- `__Host-dg_mfa` (cookie, first party): only while you sign in to an account with two-step sign-in on, between your
  password and your code. Holds a single-use ticket. Expires after 5 minutes.
- `__Host-dg_session` (cookie, first party): only when you are signed in. Keeps you signed in. Expires after 30 days at
  most, or after 7 days without use.

The two cookies are strictly necessary to provide the sign-in you asked for, so no consent banner is shown. They are
never used for tracking.

*([WP-131] Read from the code on 25 October 2026: the site sets no other cookie, and the only browser storage it uses is
`dg-theme`, `dg.profile.v1` and the `dg-answer:` items; `__Host-dg_bind` no longer exists.)*

### 5. Accounts and alerts

**Sign-in is not open yet.** This section describes what applies once it opens. *(Remove this sentence if accounts open
together with the publication.)*

You create an account with your e-mail address and a password, and confirm the address through a link we send to it.
You sign in with the address and the password. We then hold:

- your e-mail address, when the account was created, when the address was confirmed and when you last visited;
- your password as an Argon2id hash (a salted, one-way form from which the password cannot be read back), and when it
  was last changed. The password itself is never stored or logged;
- if you turn on two-step sign-in: the key of your authenticator app, encrypted with a key that is not kept in the
  database, the last code period used (so that each code works once) and when you turned it on, and ten recovery codes
  as keyed hashes (HMAC), each marked when used. Turning it off deletes them;
- the version of the terms of use and of this notice you accepted, and when;
- if you came from our pricing page: the plan and billing period you picked, so that we can show it to you again.
  Choosing a plan charges nothing and gives no paid plan; until payment opens every account is on the free plan;
- the choices you make: your role, whether you follow tenders or funding, countries, scope and alert frequency;
- what you save: searches with the name you give them and when they were last alerted, shortlisted notices with the
  status and note you write, and followed buyers and programmes;
- the links we mail you, to confirm your address (valid 24 hours) or to set a new password (valid one hour), and the
  ticket between your password and your code (valid 5 minutes): each works once and is held only as a hash;
- for up to a day: keyed hashes (HMAC) of your e-mail address and of your IP address with the time, kept only to limit
  how often account mails can be requested and to slow down failed sign-ins (after five failed attempts for one address
  in an hour, each further attempt has to wait longer, up to an hour);
- a hash of your session identifier and when it was used;
- a security log of what happens to your account (for example a sign-in, a failed sign-in, a password change or the
  deletion) with the account's internal number and the time, never your e-mail address, your IP address or your
  password. It is kept in our server's log for at most 90 days.

We do not look at what you save for any purpose other than showing it to you and sending the alerts you asked for, and
we do not combine it across accounts.

**Purpose and legal basis:** to provide the account, the dashboard and the alerts (Art. 6(1)(b) GDPR, or, where the
contract is with your employer, our legitimate interest in providing it to you, Art. 6(1)(f)). Security measures such
as limiting account mails and failed sign-ins and the security log rest on Art. 6(1)(f).

**Mail:** the confirmation and password links, a notice when your password is changed or reset, and alert digests are
sent as plain text with an HTML version of the same text, with no tracking pixel, no images and no link redirection.
They are sent through Brevo (Sendinblue SAS, France), acting as our processor.

**Retention:** your account and what is in it until you delete it. You can download everything we hold and delete the
account yourself in Settings; deletion removes it at once, together with your password hash, two-step key, recovery
codes, sessions and unused links, and encrypted backups containing it are overwritten within 30 days. To delete the
account you type your e-mail address and your password. An account whose address is not confirmed within two days is
deleted. Links and tickets are deleted a day after they expire, and the rate-limit and failed sign-in counters after
about a day.

Providing an e-mail address and a password is necessary to have an account; without them we cannot offer one.

## [WP-131] Sections 6, 7 (one item) and 8 (one item) as they would read

### 6. Forms

The site has no waiting-list and no contact form. What you type into a search or a filter goes into the address of the
page you open, which the access log keeps for up to 14 days (section 2). The readiness check and the supplier profile are
described in section 4, the account forms in section 5.

### 7. Personal data in public notices, the item "Archive"

**Archive.** We keep a private, append-only archive of earlier versions of notices so that changes can be shown. These
still contain contact details a publisher placed in a notice: in the raw store that the collection lands first, about 100
TED notices collected between 14 and 19 September 2026, and the Spanish notices (PLACSP) collected before 12 October
2026, which were not counted and have not been cleaned since; in the history of notices, 221 earlier versions with an
e-mail address (counted on 21 October 2026), 113 of them written on 12 and 14 October 2026; and in our list of
organisations, about 960 names of public buyers (with about 1,030 spellings) that contain a telephone, fax or e-mail
block as the source wrote it, which we keep as published. The website does not show any of them. They are kept as long
as the archive is kept, and we redact them earlier on a valid request or where the law requires.

*(The other items of section 7 are those of 1.6. The figures are those of `docs/DATA_PROTECTION.md` on 25 October 2026:
re-count before publishing, and drop a part that a clean-up has removed by then.)*

### 8. Who receives data, the AI item

- OpenAI (United States), as a processor: it receives the text of public funding call documents, to read who may apply,
  and of the European Defence Fund's published project fact sheets, which name the organisations in each project's
  consortium, to read that list. It processes them in the United States; we ask it not to store the requests. We send it
  nothing about visitors or account holders. *(Transfer basis: owner and lawyer, open item 5.)*

## Open items for the owner

0. Owner decisions of 25 October 2026: mail provider Brevo (Sendinblue SAS, France); security log kept 90 days (to be enforced on the API log before publishing).
1. The mail provider: name and country in sections 5 and 8, its data processing agreement, SPF/DKIM for the sender
   domain.
2. The security log period: decided 90 days (owner, 25 Oct); WP-126 writes account events to their own file, which
   `logprune` cuts at 90 days (deployed with round 8).
3. Whether "Sign-in is not open yet" stays in section 5 on publication.
4. The lawyer's review (OPEN_ITEMS_FOR_LAWYER.md) of the security log basis and of the plan wording together with the
   terms draft 2.2.
5. [WP-131] The transfer basis for OpenAI in section 8 (Data Privacy Framework or standard contractual clauses) and its
   data processing addendum; the lawyer's reading of the archive item (section 7) and of the `?prefer=` sentence (section 4).
6. [WP-131] The e-Zamowienia raw payloads landed until 21 October 2026 hold the winners of result notices, natural persons
   among them. `docs/DATA_PROTECTION.md` (row "Raw store, `pl_ezam/`") says `ops.restrip raw --source pl_ezam` was not
   run; the operations notes of 22 October say pl_ezam was re-stripped before the owner stopped the re-strip. Confirm which
   is true and, if they are still there, name them in the archive item of section 7.
7. [WP-131] Terms draft 2.2, term 20, says the same as the archive item (docs/legal/drafts/terms-v2.2-draft.md).
