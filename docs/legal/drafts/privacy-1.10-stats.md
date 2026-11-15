# Privacy 1.10, visit statistics (WP-169): DRAFT of section 3 and the In short line (15 November 2026)

**Not published. For the owner's approval.** Nothing here changes a live text: `web/app/(public)/privacy/page.tsx` stays at
1.9 and `accounts.PRIVACY_VERSION` stays "1.9". The code that collects the detail is deployed switched off
(`DGATE_STATS_DETAIL` unset or `0`); with it off the counter stores exactly what 1.9 section 3 describes. Order once approved:
publish 1.10 (page, `PRIVACY_VERSION`, `docs/legal/versions/privacy-v1.10-<date>.md`), then set `DGATE_STATS_DETAIL=1` in
`infra/.env` and recreate the `api` container. Section 3 of 1.9 promised no more than it says, so turning the switch on before
publishing would make the published text untrue.

## In short (replaces the third bullet)

> Visits are counted by our own server, by page address, by the website you came from, by country and by phone or
> computer, with no identifier, no IP address and no user agent stored, and without any script or cookie in your browser.

The second bullet ("No advertising, no third-party trackers, no analytics script and no analytics cookie.") stays as it is.

## Section 3 "Visit statistics" (replaces both paragraphs)

> We count page views to see which parts of the service are used and how people find it. Our own server adds one to a
> daily counter made of:
>
> - the address of the page without anything after a `?` (for example `/tenders/123-armoured-vehicles`, never your search
>   words or filters). Pages of the account area and the sign-in, registration and password pages are counted only by their
>   kind (for example `/app`), never by their full address;
> - the website you came from, as its name only (for example `www.google.com` or `news.example.org`), never the page on it
>   or the words you searched for; a view from another page of our own site is counted as "internal", and a view with no
>   referring site as "direct";
> - the country your connection comes from, as the two-letter code that Cloudflare, which delivers the site (section 2),
>   assigns to it. We do not determine it ourselves and do not store the address it was derived from;
> - whether the device is a phone or not.
>
> We keep only how many views each combination of these had on a day, never a record of a single visit or its time: no
> cookie is set, no script runs in your browser, and no IP address, user agent or identifier is stored with the count, so it
> cannot be traced to a person. Requests that announce themselves as automated are not counted. To stop one address from
> inflating the count, the server keeps the address in memory for at most a minute and counts a limited number of views
> from it; it is never written to disk or stored with the count.
>
> **Legal basis:** our legitimate interest in knowing how the service is used and found (Art. 6(1)(f) GDPR). Since no
> personal data is stored you have nothing to opt out of.
>
> **Retention:** after 30 days, a page address or a referring site with fewer than three views on a day is merged into its
> kind of page or into "other" for that day. The daily totals themselves contain no personal data and are kept as long as
> the service runs.

## Open points for the owner (and the lawyer, `docs/legal/OPEN_ITEMS_FOR_LAWYER.md`)

- Retention of the totals: "as long as the service runs" matches the inventory's "indefinite". A fixed limit (for example
  25 months) is easy to add if preferred (a `DELETE` in `accounts._prune`).
- A referring site can be a small one (a personal blog, a company intranet name). It is stored as a host name, a total per
  day, and folded into "other" after 30 days when it brought fewer than three views a day. Whether a host name of a
  one-person site is personal data on its own is the lawyer's question; the fold limits how long one stays.
- On a quiet day a combination (page, referring site, country, device) can have a count of one. It holds no identifier and no
  time, and the fold removes rare pages and sites after 30 days, but the country stays with the page kind. If the lawyer
  prefers, countries can be counted on their own (a separate total per day and country, not combined with the page or the
  referrer); that is a small change in `accounts._count_hits` and `dgate.ops.stats`.
- The country comes from Cloudflare's `CF-IPCountry` header. Cloudflare is already named in section 2 as processor; no new
  recipient.
