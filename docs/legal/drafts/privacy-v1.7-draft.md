# Privacy notice, version 1.7: DRAFT for the owner's approval (WP-123, 25 October 2026)

**Not published.** The page `web/app/(public)/privacy/page.tsx` keeps version 1.6 (published 24 October 2026) until the
owner approves this text. Accounts with a password stay closed until it is published: the API compares
`PRIVACY_VERSION` (now "1.6") with `PASSWORD_PRIVACY_VERSION` ("1.7") in `backend/dgate/accounts.py`.

To publish: put the approved text into the page, set its date in the lead, set `PRIVACY_VERSION = "1.7"` (and
`TERMS_VERSION = "2.2"` if the terms draft is approved with it), copy the final text to
`docs/legal/versions/privacy-v1.7-<date>.md`, and add the line to `docs/legal/versions/README.md`. Name the mail
provider in section 5 and 8 first (it is a processor and needs a data processing agreement).

Built from version 1.6 as it stands on integration (445c1e5). Sections 1, 2, 3, 6, 7, 9, 10 and 11 are word for word
those of 1.6 and are not repeated here. Section 8 changes in one item.

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

## Sections 4 and 5 as they would read

### 4. Cookies and local storage

While you browse, the site sets no cookies. These are the only items it ever stores in your browser:

- `dg-theme` (local storage, your device only): your light or dark choice. Kept until you clear your browser data.
- `dg.profile.v1` (local storage, your device only): unchanged from 1.6.
- `__Host-dg_mfa` (cookie, first party): only while you sign in to an account with two-step sign-in on, between your
  password and your code. Holds a single-use ticket. Expires after 5 minutes.
- `__Host-dg_session` (cookie, first party): only when you are signed in. Keeps you signed in. Expires after 30 days at
  most, or after 7 days without use.

The two cookies are strictly necessary to provide the sign-in you asked for, so no consent banner is shown. They are
never used for tracking.

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

## Open items for the owner

0. Owner decisions of 25 October 2026: mail provider Brevo (Sendinblue SAS, France); security log kept 90 days (to be enforced on the API log before publishing).
1. The mail provider: name and country in sections 5 and 8, its data processing agreement, SPF/DKIM for the sender
   domain.
2. The security log period: decided 90 days (owner, 25 Oct); WP-126 writes account events to their own file, which
   `logprune` cuts at 90 days (deployed with round 8).
3. Whether "Sign-in is not open yet" stays in section 5 on publication.
4. The lawyer's review (OPEN_ITEMS_FOR_LAWYER.md) of the security log basis and of the plan wording together with the
   terms draft 2.2.
