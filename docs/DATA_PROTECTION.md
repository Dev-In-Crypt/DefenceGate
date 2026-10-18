# Data protection: what is held, where, and for how long

Status: working document of 12 October 2026. The inventory is fact (measured on the
production database or read from the code). The retention periods are **proposals** for
the owner and a lawyer to accept or change; nothing below is legal advice and no lawful
basis is decided here. The procedure for a request from a person is in
`docs/RUNBOOK.md`, "Data subject requests".

## What the product is meant to hold

Commercial market intelligence about public notices and grants: titles, buyers (public
bodies and companies), CPV codes, dates, amounts, links to the source. Not contact
persons. `strip_personal_data()` (`backend/dgate/normalise.py`) removes names, e-mail
addresses and phones at the single boundary every connector passes, and the serving layer
redacts anything e-mail-shaped again on output.

## What is actually held

| Where | What | How much | Why it is there |
|---|---|---|---|
| Raw store (Storage Box `dgate/`), payloads landed before the sweeps | notice payloads with the contact fields the source published (e-mail, sometimes phone and a person's name) | about 100 TED notices (landed 14-19 Sep, swept 22-23 Sep); PLACSP payloads landed before 12 Oct were not measured | landed before the boundary was applied to every connector; the store is immutable by design |
| `opportunity_version.payload` | e-mail addresses inside the stored snapshot | 108 versions (103 in `description`) | the append-only trigger refuses correction; redacted on output only, by the owner's decision of 12 Oct |
| `opportunity` | e-mail in a serving column | 5 rows | same cause |
| `organisation_alias` | an e-mail-shaped string used as a name | 95 rows | a source put it in the buyer field |
| Database dumps on the host and the Storage Box | everything above | 30 days of nightly dumps; those before 12 Oct are plaintext and age out by 11 Nov 2026, later ones are encrypted | backup |
| `/root/dgate-cutover.sql.gz` on the host | a plaintext dump of 16 Sep | one file, 110 MB | the migration to the host; **to be deleted by the owner** |
| Logs | the proxy's request log (client address, time, address requested including the query string, response code, size, request headers including user agent and referrer; the `token` query parameter of `/auth/verify`, also as `Referer`, is removed by a filter before a line is written) and its own error log, both as files in the `caddylogs` volume | **14 days at the latest** since 15 Oct 2026: `dgate.ops.logprune` (compose service `logprune`) cuts older lines from the active files and deletes rolled files, hourly; Caddy's `roll_keep_for 336h` and `roll_size` are a second guard. The API's own access line is switched off (`--no-access-log`). Container logs of the other services hold no request data (size-capped, 5 x 20 MB each) | operation |
| Buyer and issuer names | legal entities, occasionally a sole trader's own name | not measured | the notice names the buyer |

Held since the accounts feature (migration 0027, 12 October 2026; sign-in stays closed
until a mail relay is configured, so these tables are empty until then):

| Where | What | Why | Retention proposed |
|---|---|---|---|
| `app_user` | e-mail address (as typed and canonical), role, tracks, countries, scope, alert cadence, created and last-visit time, and (migration 0047) the version of the terms and of the privacy notice accepted and when (`terms_version`, `privacy_version`, `accepted_at`) | the account | until the account is deleted |
| `app_session` | SHA-256 of the session id, creation, last-seen and expiry time; at most 10 per account (signing in beyond that ends the account's own oldest) | stay signed in; revocation | 30 days absolute, 7 days idle, then deleted at the next sign-in |
| `app_login_token` | SHA-256 of the one-time link and of the browser binder, the address, expiry, and the versions of the texts ticked on the form with the time (copied to `app_user` when the link is used) | sign in | rows expired for more than a day are deleted at the start of every sign-in request and, at most every ten minutes, by the status call the site makes every minute |
| `app_auth_event` | an HMAC-SHA256 of an address or of a client IP, with a time. The key is held by the server only (`DGATE_INTERNAL_SECRET`, or the accounts role's password when that is unset). Pseudonymous, not anonymous: whoever holds the key can test a known address against it. Written only for a request that was accepted; a refused one leaves nothing | rate limits on sign-in links | rows older than a day are deleted at the start of every sign-in request (index on the time) |
| `app_saved_search`, `app_shortlist`, `app_follow` | what the account searched for, saved, noted and follows | the product | until the account is deleted (cascade) |
| `app_hit_daily` | per day, page, referrer and device class: a count. The referrer is kept only when it is a well-known one (a search engine, a social network, GitHub, Wikipedia, Hacker News), as its own name; every other referrer is stored as `other`, so the table is bounded by pages x that list x device | audience measurement without identifiers | indefinite; contains no person |
| Mail relay (processor, when configured) | recipient address and the text of sign-in and alert mails | delivery | the relay's own; plain text, no tracking |

A saved search is commercially sensitive (it says what a company wants to bid on). It is
private to the account, never aggregated per person, and not shown to anyone else; the
operator can read it in the database and must not use it. The visit counter holds no
address, user agent or identifier: the site's server reduces a request to a page key and
a host before it is sent, and the API reduces the host to a short list of known referrers
before it is written. The access log of the proxy still holds client addresses
(above).

The accounts role (`dgate_app`) reads only the tables the account code needs: the public
notice, call and organisation tables and its own `app_*` tables (migration 0036). It cannot
read the raw ingest records, the run log or the migration table.

Held since migration 0047 (15 October 2026), all written only by the owner's command-line tools
and never readable by the public API or the accounts role:

| Where | What | Why | Retention |
|---|---|---|---|
| `suppression` | what was removed from the public site and why: kind (notice, organisation, call), source and native id or organisation id, reason code, when the request arrived, who decided (a name the owner types), a note. Never the requester's identity or message. Lifting sets `lifted_at`; rows are never deleted (a database trigger refuses) | to keep a removal across re-ingestion and to evidence it | as long as the removal stands, then as long as the lawyer says |
| `opportunity.suppressed`, `buyer_withheld`, `organisation.suppressed`, `call.suppressed` | flags set by triggers from `suppression` on the serving rows; the archive rows are untouched | the public read side hides flagged rows | follows `suppression` |
| `data_request` | received date, kind (access, rectification, erasure, restriction, objection, portability, removal, other), status, closed date, a handler note typed by the owner. No name, address or message of the requester; the note must not contain them either | to show when a request arrived and how it ended | as long as the lawyer says; rows are never deleted |

Owner commands: `python -m dgate.ops.suppress add|list|lift` and `python -m dgate.ops.data_request add|list|close`
(dry run unless `--yes`). A suppressed notice is a 410 "removed on request" at its address and is
absent from every list, export, feed, sitemap slug, statistic and account view; an organisation
suppression shows its notices with the buyer "Name withheld on request" and removes the buyer page.
When two organisations are merged (`merge_organisations`), a suppression on the absorbed one does
not carry over: add it for the survivor.

Held since migration 0060 (WP-26, 17 October 2026), written only by the monthly networks jobs
(`dgate/networks.py`) and read by the API role:

| Where | What | Why | Retention |
|---|---|---|---|
| `organisation` (new rows, `display_name`, `eu_pic`, `vat_number`) | the legal name, country, participant identification code and VAT number of every organisation that took part in a CORDIS or EDF project, as the source publishes them. Legal names are company names; a sole trader or an individual consultant can be registered under their own name (not measurable from the data) | the participation graph | as long as the organisation is in the source; a removal request is handled through `suppression` (kind organisation) |
| `project`, `participation` | project title, acronym, grant number, call and topic, dates, cost and EU contribution; per organisation: role, EU contribution and how the link was decided. No person, no contact, no abstract | the participation graph | rows are never deleted by the importers (a participant who left is marked inactive) |
| `consortium_snapshot`, `consortium_change` | the list of organisations of a project at a date and the difference between two dates | history that no public source keeps | indefinite |
| `project_factsheet` | what the language model reported from one EDF factsheet (organisation names, countries, role, amounts) and what the quote check dropped. The technical description of the project is cut before the text is landed or sent to the model | audit of the extraction | indefinite |
| Raw store `cordis/` and `edf_factsheets/` | the result pages of the SPARQL service (organisation, project and participation fields) and the layout and plain text of each factsheet without its description | replay without refetching | as the rest of the raw store |
| `resolution_review`, `resolution_gold` | pairs of organisation ids waiting for a person; hand-labelled pairs of company names for the evaluation | working data | until decided; the gold set is a seed file in the repository |

Not held: payment data, passwords (there are none: sign-in is by one-time link), IP
addresses beyond the proxy's request log (14 days) and the keyed (HMAC) rate-limit counters, which are kept a day. The waitlist form
stores nothing (`web/app/(public)/actions.ts`). This file changes in the same commit as
the first feature that stores anything new.

## Readiness check (WP-29, 17 October 2026): nothing is held

The readiness check asks a company about its country, ownership and control, products and certificates. **None of it is stored or logged by the server.** The answers live in the visitor's browser (localStorage, `dg.profile.v1`). The verdict is computed by `POST /v1/readiness/assess`, which receives them in the body, keeps no copy, opens no write (it runs under the read-only API role; a test asserts it) and logs nothing of the body (a test asserts that too; the proxy's request log holds the address and the path, not a POST body). The company name and size entered in the wizard are not part of the request. A profile can say who owns a company, so it is treated as private even though it is not personal data of a natural person. The tables `requirement`, `requirement_issuer`, `requirement_prerequisite`, `readiness_programme` and `programme_requirement` hold public regulatory content only: no personal data and no contact details (a test checks the seed file for e-mail addresses).

## Supplier map (WP-37, 18 October 2026)

| Where | What | Why | Retention |
|---|---|---|---|
| `award`, `award_notice` | per TED result notice of the core scope: the winning organisation (name as the buyer published it, country, registration number as published), the notice it won and how the organisation was found. Counts of the winners left out (natural persons, no country). No contact, no person | the supplier map | rows are never deleted by the loader; a removal request is handled through `suppression` (kind organisation or notice) |
| `organisation` (new rows), `organisation_alias` | the legal name, country and registration number of every winner | the same | as for the participation graph above |
| Raw store `ted_awards/` | the winner fields of each result notice as TED returned them, **with the entries of natural persons blanked** (`[natural person]`, their number removed) before the record is landed | replay without refetching | as the rest of the raw store |

A winner that looks like a natural person (a sole trader under their own name, a Polish trading name that ends in the
owner's name, an "e.K.") is skipped by `dgate/awards.py: person_reason` and written nowhere. It is a rule on names:
measured on 18 October 2026, of 5,997 distinct core-scope names 184 were skipped (about two thirds of those read by
hand were persons) and about 0.8 % of the rest are probably still a person (`docs/design/SUPPLIER_MAP_FEASIBILITY.md`,
section 3). The public pages say how to ask for a removal. Winners are public in TED; the map adds that they are
collected per company, which is why the aggregate publishes no group of fewer than three suppliers and the pages carry
no ranking, share or total.

## Who can read it

The API and worker service roles (`dgate_api`, `dgate_worker`), the owner on the host,
and whoever holds the Storage Box key. The private half of the backup key is only on the
owner's laptop. The raw store is private and never served. Nothing here is public except
what `/v1/*` returns, which is the allow-listed and redacted view.

## Proposed retention (owner and lawyer to decide)

| Data | Proposal | Reasoning |
|---|---|---|
| Archive facts (`opportunity_version`, structured fields) | indefinite | the product; facts about public procurement |
| Free text snapshot fields in the archive | indefinite, redacted on output | removing them needs the break-glass step; the output is already clean |
| Raw payloads | keep while they are the replay base; payloads with contact data landed before the sweep: rewrite or drop at the owner's decision | the only copy of the original; the contact data is the part with no use |
| Dumps | 30 days (as now) | restore window |
| Access log | 14 days, then dropped (implemented 15 Oct 2026: `logprune`) | abuse analysis only |
| Account data | until the account is deleted by its owner (self-service, cascades); no grace copy; invoices as the law requires once billing exists | minimal; nothing outlives the account except the aggregate counter |
| Backups containing a deleted account | roll off with the 30-day dump window | the dumps are encrypted and cannot be edited |

## Open questions that are not technical

1. Lawful basis for the contact data in the pre-sweep payloads (Art. 6) and whether the
   notice-to-the-person duty (Art. 14) is met by the exemption for disproportionate
   effort (Art. 14(5)(b)) or by not holding them any more.
2. Whether translating or summarising a notice by a model is a "modification" under the
   licences that require attribution (CC BY 4.0, the BDNS notice).
3. Commercial redistribution of TED, PLACSP and e-Zamowienia text and of the archive.
4. Whether a company's readiness profile (planned) is personal data when the company is a
   sole trader, and what the profile aggregate reveals about which firms seek what work.
