# Sources of cascade calls (financial support to third parties): investigation, 17 October 2026

Question (WP-31): where are the calls that EDF projects, NGI/NLnet and similar projects open for third parties
published, and is there a clean, small, stable, machine-readable source worth a connector?

**Result: no connector was built.** No source below is a single machine-readable feed of such calls, and for none of
them did I find a licence that allows reuse. What the product holds today is the flag on the Commission's own calls
(`call.cascade`, `dgate/cascade.py`): which of the portal's calls let their projects pass money on. The sub-calls
that those projects then open are a different, scattered set.

Method: `robots.txt` of each host and one page each, fetched on 17 October 2026 with the honest User-Agent
(`DefenceGate-wp31-research/1.0`), well under one request a second, about ten requests in all. No login, no form, no
crawl. Nothing here is a reading of terms by a lawyer.

| Source | What it lists | Machine-readable | robots.txt | Licence / terms | Verdict |
|---|---|---|---|---|---|
| EU Funding & Tenders Portal (the sub-calls themselves) | EDF and Horizon *projects* publish their own FSTP calls on their own sites, not on the portal. The portal lists the *parent* call, which we already hold. | Parent calls: yes (our `eu_portal` connector). Sub-calls: no | (portal host, see `docs/sources/eu_portal.md`) | Commission reuse decision, parent calls only | Nothing to add: the parent flag is the useful part |
| EDF projects' own sites (example found: the MaJoR cascade call, 28 January to 25 March 2026, up to 30 innovators, up to EUR 60,000 each, SMEs and start-ups in EU Member States, Norway and Ukraine) | One site per project, each with its own page layout | No common feed | one per site, not read | Not found | Not clean, not stable: one project, one format, one call |
| NLnet (nlnet.nl/propose) | Open calls of the NGI Zero funds, with deadlines (3 November 2026 12:00 CET on the page read) | An Atom feed of news (`/feed.atom`) exists; not a feed of calls | `User-agent: *`, `Disallow: /cgi-bin/`, `/help*`, and any URL with a query string | No licence statement on the page read | Few calls, hand-curated pages. Worth a manual list entry, not a connector. Its calls are Dutch-foundation grants, not the Commission's FSTP |
| NGI (ngi.eu) | Open calls of NGI projects | Not checked beyond robots | `Disallow:` empty (everything allowed) | Not read | Not a feed; same verdict |
| Cascade Funding Hub (cascadefunding.eu, run by Sploro) | A hub of FSTP projects and a matcher; an "Open Calls" page | None seen on the home page (newsletter and social links only) | Only `/wp-admin/` disallowed | Footer has a legal disclaimer, a privacy policy and a cookies policy; no licence statement; the disclaimer was not read | The nearest thing to an index. A private company's editorial content, no feed, no licence found: not ours to copy. Ask the operator for a feed and a licence before anything is built |

What a connector would need, and does not have: a list that is complete for a stated set of projects, in a fixed
format (feed or API), with a licence that allows storing it and showing it with attribution, and a stable URL.
Without that, a scraped list would be partial in a way the site cannot state, which the product rule on completeness
forbids.

If the owner wants this layer: (1) write to the Cascade Funding Hub operator asking for a feed and a licence;
(2) list the five or six largest FSTP-bearing EDF and Horizon projects by hand from the parent calls already flagged
(`/funding?cascade=true`) and link each project's own call page; (3) revisit when the Commission publishes
sub-calls in its open data (not the case on this date).

Not checked: the licence text of any site above, the `robots.txt` of the individual EDF project sites, and whether
NGI publishes a structured calls listing beyond its sitemap.
