# Cloudflare as a proxy: DRAFT additions for the privacy notice (next version) and /data/sovereignty (WP-147, 26 October 2026)

**Not published. For the owner's approval.** Nothing here changes a live text: `web/app/(public)/privacy/page.tsx` stays at
1.7 and `web/app/(public)/data/sovereignty/page.tsx` keeps its Cloudflare row ("It is not a proxy") until the owner approves
this wording. The texts must be published **before** the proxy is switched on (order: our deploy, this approval and its
publication, proxy on, origin lock; docs/verification/round6/wp147-selfcheck.md).

Built from privacy 1.7 as published (`docs/legal/versions/privacy-v1.7-2026-10-26.md`) and the sovereignty page on
integration (9c4295c). Only the sentences below change; everything else stays word for word.

## What Cloudflare would see, and why (the facts the wording rests on)

- **What:** every request to the site and the API passes through Cloudflare's network: the visitor's IP address, the time,
  the full address requested (with any search words in it), the request headers (browser, referrer, language), the response
  our server sends, and Cloudflare's own derived data (the country it assigns to the IP address, a request ID). It ends the
  encrypted connection itself, so it sees the request in clear, as our server does. The session cookie of a signed-in
  visitor passes through it too (it carries the request); Cloudflare does not use it.
- **Cookies Cloudflare sets:** with Bot Fight Mode on, Cloudflare may set `__cf_bm` (bot detection, 30 minutes) and, after a
  visitor passes a challenge, `cf_clearance` (proof the challenge was passed, 30 minutes by default). Both are set on our
  domain by Cloudflare, not by us. This makes the "sets no cookie" sentences of 1.7 untrue once the proxy is on.
- **Where:** Cloudflare, Inc. is a United States company. A request is handled in the Cloudflare data centre nearest the
  visitor (for visitors in Europe normally one in Europe), and Cloudflare processes logs and security data in the United
  States as well. The free plan has no choice of region.
- **Why:** to protect the site against floods of automated requests (bot protection and rate limiting) and to deliver it.
- **Role and transfer:** Cloudflare acts as our processor for this. **For the lawyer / owner to confirm before publishing:**
  that Cloudflare's data processing addendum (offered as part of its self-serve terms) covers the account, and the transfer
  basis (Cloudflare's certification under the EU-US Data Privacy Framework, or the standard contractual clauses in that
  addendum). Retention on Cloudflare's side follows its own policy; we do not set it on the free plan.
- **What we keep does not change:** our own request log keeps the same data for at most 14 days. With the proxy on it also
  records Cloudflare's address for each request and the headers Cloudflare adds (the visitor's address again, the country
  Cloudflare assigns, a request ID).

## Privacy notice: proposed changes

**"In short", first bullet.** 1.7: "Browsing needs no account and sets no cookie." Proposed:
"Browsing needs no account. We set no cookie while you browse; Cloudflare, which protects the site, may set two technically
necessary cookies (section 4)."

**"In short", new bullet after the access-log bullet.** Proposed:
"Every request to the site passes through Cloudflare (United States), which protects it against automated floods (section 2)."

**Section 2, first paragraph.** 1.7: "When your browser loads a page, the server and the reverse proxy in front of it record
the technical details of the request: ..." Proposed (the rest of the paragraph unchanged):
"When your browser loads a page, the request first reaches Cloudflare, which passes it on to our server. Our server and the
reverse proxy on it record the technical details of the request: ..."

**Section 2, new paragraph after the retention sentence.** Proposed:
"Cloudflare, Inc. (United States) stands in front of the server as our processor. It receives every request to the site and
our answer to it: your IP address, the time, the full address requested including any search words, your browser's headers
and the page or file we send back, and it assigns a country to your IP address. It uses this to deliver the site and to tell
visitors from automated floods (it may show a short browser check before a page). Requests are handled in the Cloudflare
data centre nearest to you, normally one in Europe for visitors in Europe; Cloudflare also processes this data in the United
States. [Transfer basis: to be completed after the lawyer's check, see above.] Legal basis: our legitimate interest in a
secure and available service (Art. 6(1)(f) GDPR). Cloudflare keeps its records according to its own policy."

**Section 4, first sentence.** 1.7: "While you browse, the site sets no cookies. These are the only items it ever stores in
your browser:" Proposed:
"While you browse, we set no cookies. Cloudflare, which protects the site (section 2), may set two: `__cf_bm`, to tell a
browser from an automated client (expires after 30 minutes), and `cf_clearance`, only after you have passed its browser check,
so that you are not asked again (expires after 30 minutes). Both are strictly necessary for the security of the site and are
not used for advertising or to follow you across sites. These are the only items the site itself stores in your browser:"

**Section 4, last sentence.** 1.7: "The two cookies are strictly necessary to provide the sign-in you asked for, so no consent
banner is shown. They are never used for tracking." Proposed:
"Our two cookies are strictly necessary to provide the sign-in you asked for, and Cloudflare's two to keep the site secure, so
no consent banner is shown. None of them is used for tracking."

**Section 8, the Cloudflare item.** 1.7: "Cloudflare, Inc. (USA), as the provider of the domain name service only: it answers
requests for the domain's address and can see the address of the resolver that asks. Traffic to the site does not pass
through Cloudflare." Proposed:
"Cloudflare, Inc. (United States), as a processor: it provides the domain name service and stands in front of the server, so
every request to the site and our answer pass through it (section 2). It processes them in its network, including in the
United States."

## /data/sovereignty: proposed changes (`web/app/(public)/data/sovereignty/page.tsx`)

**Row "Server: the website, the API, the database and the collection jobs", note.** Now: "One virtual server. There is no
content delivery network or proxy in front of it: visitors connect to it directly." Proposed:
"One virtual server. Visitors reach it through Cloudflare's proxy (below)." (Once the origin lock is on, the owner may add:
"The server accepts web connections from Cloudflare only.")

**Row "Domain registration and name service (DNS)" (outside the EU).** Proposed new title and note:
- what: "Domain registration, name service (DNS) and the proxy in front of the server"
- who: "Cloudflare, Inc." / where: "United States company; requests are handled in its data centre nearest the visitor, and
  it also processes data in the United States" / eu: "No"
- note: "Cloudflare is the registrar, answers the question “what is the server’s address?”, and stands in front of the
  server: every page and API request, with the visitor's IP address, the address requested and the browser's headers, passes
  through it, and so does our answer. It ends the encrypted connection itself. It is there to keep automated floods off the
  site; it may set the cookies `__cf_bm` and, after a browser check, `cf_clearance` (privacy notice, sections 2 and 4). It acts
  as our processor."

**"What this page does not say" list:** no change (it already says US companies are in the path).

## Not changed by this draft

- The 14-day limit of our own log, the visit counter (it still counts the visitor's address in memory only, now the address
  Cloudflare passes on), the accounts sections.
- `docs/DATA_PROTECTION.md` records the log change (WP-147 note in the Logs row).
