# Data protection: what is held, where, and for how long

Status: working document of 12 October 2026, corrected on 18 October 2026 (WP-39: the statements
that the independent check of that day found untrue are rewritten below, each with its date). The inventory is fact (measured on the
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
| Raw store, `pl_ezam/` (e-Zamowienia), every payload landed until WP-71 (21 Oct 2026) | the `contractors[]` of result notices: name, NIP, city, province of each winner, a natural person (CEIDG sole trader) on many of them | 3,484 bundles. In a sample of 4 bundles (21 Oct, read-only): 4,902 contractor entries, 799 named natural persons, 2,433 with no name but a number and a city (treated as persons), 1,670 companies | the boundary stripped top-level keys only (QA H1). Stripped at the boundary since WP-71; `python -m dgate.ops.restrip raw --source pl_ezam` (report only by default, `--yes` to rewrite) scrubs what is landed; not run |
| `opportunity_version.payload` | e-mail addresses inside the stored snapshot | 221 versions on 21 October 2026 (full scan, read-only): 108 TED observed 17-19 Sep, 1 pl_atlas, and 113 TED versions written on 12 and 14 Oct by `ops.repair_ted`, which carried the description of the version before into the new one (fixed in WP-71: `append_version` sweeps every text field) | the append-only trigger refuses correction; redacted on output only. `python -m dgate.ops.restrip archive --emit-sql FILE` prepares the break-glass transaction (docs/RUNBOOK.md, step 4) for the owner; not run |
| `opportunity` | e-mail in a serving column | 4 rows in the title, summary and buyer-name columns on 18 October 2026 (5 on 12 October, other columns not re-counted) | same cause |
| `organisation_alias` | a string with an "@" used as a name | 172 rows on 18 October 2026 (95 on 12 October; some are brand names such as "@HOME B.V."); profiles redact the address-shaped ones on output | a source put it in the buyer field |
| `organisation.canonical_name` / `display_name`, `organisation_alias.raw_name` / `normalised_name` (WP-115) | a telephone, fax or e-mail block written into a buyer's name ("... Tel 0221 ..., Fax ..., E-Mail ...") | 24 Oct 2026 (read-only, coarse SQL filter): 960 organisation rows and 1,029 aliases (96 with an e-mail address) match; none served (no notice, award or directory row) | the source's buyer field. Owner decision of 24 Oct 2026: kept as stated in the alias's raw name; `normalise.strip_name_contacts` leaves the block out of the matching key only (`canonical_name`, `normalised_name`), so a body with and without it is one organisation. Not served. `python -m dgate.ops.org_repair --step contacts` exists but is not run |
| `organisation_repair` (WP-115, migration 0127) | the value a correction replaced: a false "registration number" (a case reference) cleared from a Polish or Spanish organisation, a re-spelt number, a moved `merged_into` pointer, an award marked buyer-as-winner | written only by `ops.org_repair --yes` and by merges; about 10,300 cleared numbers if the correction is run | the undo path. A number that may be a person's (a Polish 11-digit PESEL, a Spanish DNI or NIE shape) is cleared without its value; a removed contact block is logged without its value |
| Database dumps on the host and the Storage Box | everything above | 30 days of nightly dumps; those before 12 Oct are plaintext and age out by 11 Nov 2026, later ones are encrypted | backup |
| A plaintext dump of 16 Sep in the root user's home directory on the host | everything above, as of that day | one file, 110 MB | the migration to the host; **to be deleted by the owner**. (Its file name is not given here: this file is in a public repository.) |
| Logs | the proxy's request log (client address, time, address requested including the query string, response code, size, request headers including user agent and referrer; the `token` query parameter of any address, `/auth/verify` and `/auth/reset` included, also as `Referer`, is removed by a filter before a line is written) and its own error log, both as files in the `caddylogs` volume | **14 days at the latest** since 15 Oct 2026: `dgate.ops.logprune` (compose service `logprune`) cuts older lines from the active files and deletes rolled files, hourly; Caddy's `roll_keep_for 336h` and `roll_size` are a second guard. The API's own access line is switched off (`--no-access-log`). Container logs of the other services hold no request data (size-capped, 5 x 20 MB each); the accounts security log has its own file and limit (90 days, below) | operation |
| Buyer and issuer names | legal entities, occasionally a sole trader's own name | not measured | the notice names the buyer |

Held since the accounts feature (migration 0027, 12 October 2026; sign-in stays closed
until a mail relay is configured, so these tables are empty until then). Since WP-123
(migration 0131, 25 October 2026, bringing over the unmerged WP-79 branch of 22 October) an
account has a password and optional two-step sign-in, and there is no sign-in by e-mail link.
Accounts open only when the relay passes the API's health check, the privacy notice for
password accounts (1.7, a draft for the owner) is published, and in production the API has its
own key `DGATE_ACCOUNT_KEY` (`accounts.accounts_problem`):

| Where | What | Why | Retention proposed |
|---|---|---|---|
| `app_user` | e-mail address (as typed and canonical), role, tracks, countries, scope, alert cadence, created and last-visit time, and (migration 0047) the version of the terms and of the privacy notice accepted and when (`terms_version`, `privacy_version`, `accepted_at`). Since migration 0131: when the address was confirmed (`email_verified_at`; set to the creation time for every account made by the old sign-in link), the password as an Argon2id hash in PHC form (`password_hash`: 19 MiB, 2 passes, 1 lane, 16-byte salt; never the password) and when it was set (`password_changed_at`), and for two-step sign-in the TOTP key sealed with AES-GCM under a key derived from `DGATE_ACCOUNT_KEY` (the API's own; the site's server does not hold it; development falls back to `DGATE_INTERNAL_SECRET`) and bound to the account id (`totp_secret_enc`; unreadable without the API's key), when it was switched on (`totp_enabled_at`) and the last 30-second step used (`totp_last_step`, so a code works once). WP-123 (same migration): the plan picked on the pricing page before registering (`plan_choice`: free, pro, team, consultant or founding; `billing_choice`: monthly or yearly; both empty when the visitor came without one), only remembered and shown again, and the plan in force (`plan`, `free` for everyone; only billing, WP-124, will change it) | the account | until the account is deleted; an account never confirmed is deleted two days after registration (`accounts._prune`, run at the start of every account request and by the status call at most every ten minutes) |
| `app_auth_token` (migration 0131) | per token: SHA-256 of the token, the account, the purpose (`verify`: the confirmation link, 24 hours; `reset`: the password link, 1 hour; `mfa`: the ticket between the password and the code, 5 minutes, never mailed), creation, expiry and use time. Single use. A new registration of an unconfirmed address or a new reset request replaces the earlier token | confirm an address, reset a password, the second step | rows expired for more than a day are deleted as above; all of an account's go with it (cascade) |
| `app_recovery_code` (migration 0131) | ten per account with two-step sign-in: HMAC-SHA256 of each code under the API's key `DGATE_ACCOUNT_KEY` (the codes have about 49 bits, too few for a plain hash), and when it was used | sign in without the phone | until two-step sign-in is switched off or set up again, or the account is deleted |
| `app_session` | SHA-256 of the session id, creation, last-seen and expiry time; at most 10 per account (signing in beyond that ends the account's own oldest) | stay signed in; revocation | 30 days absolute, 7 days idle, then deleted at the next sign-in |
| `app_login_token` | **empty since migration 0131** (WP-79 deleted the rows; nothing writes it). It held the SHA-256 of the one-time sign-in link and of the browser binder, the address and the versions ticked | the old sign-in link | a deletion candidate (`docs/DELETION_CANDIDATES.md`) |
| `app_auth_event` | an HMAC-SHA256 of an address or of a client IP, with a time and a kind. The key is held by the API only (`DGATE_ACCOUNT_KEY` since WP-123; without it, in development, `DGATE_INTERNAL_SECRET` or the accounts role's password). Pseudonymous, not anonymous: whoever holds the key can test a known address against it. Kinds `addr`, `addr_ip`, `ip`, `all`: written only for a mail request (registration, reset) that was accepted; a refused one leaves nothing. Kinds `login_addr`, `login_ip` (WP-79): one row per failed sign-in, wrong current password or wrong code, for the address typed (whether or not it has an account) and the client; a successful sign-in deletes the address's rows | rate limits on account mails; the sign-in delay (5 failures of an address in an hour are free, then 30 s doubling up to an hour; 30 for a client) | rows older than a day are deleted at the start of every account request (index on the time) |
| `app_saved_search`, `app_shortlist`, `app_follow` | what the account searched for, saved, noted and follows | the product | until the account is deleted (cascade) |
| `app_hit_daily` | per day, page, referrer and device class: a count. The referrer is kept only when it is a well-known one (a search engine, a social network, GitHub, Wikipedia, Hacker News), as its own name; every other referrer is stored as `other`, so the table is bounded by pages x that list x device | audience measurement without identifiers | indefinite; contains no person |
| Mail relay (processor, when configured) | recipient address and the text of the mails: the confirmation link, "you already have an account", the password link, "your password was changed" (after a change in Settings and, since WP-123, after a reset), alert digests. Since WP-123 each mail is plain text plus an HTML version made from the same text, sender name "DefenceGate" | delivery | the relay's own; no tracking pixel, no image, no link redirection. The API's health check of the relay (connect, TLS, log in, NOOP) sends no message and no personal data |
| API security log (WP-123), since WP-126 the file `security.log` in the `securitylog` volume (`DGATE_SECURITY_LOG`), no longer the `api` container's log | one line per account event (JSON: time, level, text): the kind (registered, confirmed, signed in, sign-in failed, second step failed, signed out, reset requested, password reset, password changed, two-step on or off, deleted, export) and the account id; never the address, a password, a token, a code, a session id or the IP address (a test reads the lines). A failed sign-in for an address that has an account carries that account's id | security monitoring, answering "was my account used" | **90 days at the latest** (owner decision of 25 Oct 2026; WP-126): `dgate.ops.logprune` (compose service `logprune`, hourly, `--dir /security=90`) cuts older lines from the file; the API writes nothing of it to stdout once `DGATE_SECURITY_LOG` is set (compose sets it). Lines written to the container log before the WP-126 deploy go when the `api` container is recreated by that deploy (Docker drops a removed container's log) |
| Development mail catcher (`DGATE_MAIL_CATCHER_DIR`, WP-123) | in a local run only, each mail as an `.eml` file in that directory, links included | tests and development without a provider | refused when `DGATE_ENV=production`; never set in `infra/docker-compose.yml` |

A saved search is commercially sensitive (it says what a company wants to bid on). It is
private to the account, never aggregated per person, and not shown to anyone else; the
operator can read it in the database and must not use it. The visit counter holds no
address, user agent or identifier: the site's server reduces a request to a page key and
a host before it is sent, and the API reduces the host to a short list of known referrers
before it is written. The access log of the proxy still holds client addresses
(above).

The accounts role (`dgate_app`) reads only the tables the account code needs: the public
notice, call and organisation tables and its own `app_*` tables (migration 0036). It cannot
read the raw ingest records, the run log or the migration table. The worker role reads the
account tables, `password_hash`, `totp_secret_enc` and `app_recovery_code` included, for the
nightly `pg_dump` only (migration 0042; dumps are encrypted). It does not hold
`DGATE_ACCOUNT_KEY`, and neither does the site's server (WP-123), so a sealed TOTP key or a
recovery-code hash is of no use to either.

Export and deletion by the account holder (WP-123): Settings offers "Download my data" (`GET
/v1/account/export`: the account, profile, plan choice, terms accepted, saved searches with
their last alert, shortlist, follows, sessions with their times, and when the address was
confirmed, the password changed and two-step sign-in turned on, with the number of unused
recovery codes; never a hash, key, code or token) and "Delete account" (the typed address and
the password; `app_user` and every table that holds the account id go at once by cascade:
`app_session`, `app_saved_search`, `app_shortlist`, `app_follow`, `app_auth_token`,
`app_recovery_code`). The `app_auth_event` counters hold no account id and expire within a
day; encrypted dumps age out within 30 days.

Held since migration 0047 (15 October 2026), all written only by the owner's command-line tools
and never readable by the public API or the accounts role:

| Where | What | Why | Retention |
|---|---|---|---|
| `suppression` | what was removed from the public site and why: kind (notice, organisation, call), source and native id or organisation id, reason code, when the request arrived, who decided (a name the owner types), a note. Never the requester's identity or message. Lifting sets `lifted_at`; rows are never deleted (a database trigger refuses) | to keep a removal across re-ingestion and to evidence it | as long as the removal stands, then as long as the lawyer says |
| `opportunity.suppressed`, `buyer_withheld`, `organisation.suppressed`, `call.suppressed` | flags set by triggers from `suppression` on the serving rows; the archive rows are untouched | the public read side hides flagged rows | follows `suppression` |
| `data_request` | received date, kind (access, rectification, erasure, restriction, objection, portability, removal, other), status, closed date, a handler note typed by the owner. No name, address or message of the requester; the note must not contain them either | to show when a request arrived and how it ended | as long as the lawyer says; rows are never deleted |

Owner commands (WP-39 added `mark_individuals` and `clean_suppliers`, both dry runs unless `--yes`):
`python -m dgate.ops.mark_individuals` and `python -m dgate.ops.clean_suppliers`; and
`python -m dgate.ops.suppress add|list|lift` and `python -m dgate.ops.data_request add|list|close`
(dry run unless `--yes`). A suppressed notice is a 410 "removed on request" at its address and is
absent from every list, export, feed, sitemap slug, statistic and account view; an organisation
suppression shows its notices with the buyer "Name withheld on request" and removes the buyer page.
When two organisations are merged (`merge_organisations`), a suppression on the absorbed one does
not carry over: add it for the survivor.

Held since migration 0060 (WP-26, 17 October 2026), written only by the monthly networks jobs
(`dgate/networks.py`) and read by the API role:

| Where | What | Why | Retention |
|---|---|---|---|
| `organisation` (new rows, `display_name`, `eu_pic`, `vat_number`) | the legal name, country, participant identification code and VAT number of every organisation that took part in a CORDIS or EDF project, as the source publishes them. Legal names are company names; a sole trader or an individual consultant can be registered under their own name. **Measured on 18 October 2026: 3 of a random 300 of the 73,347 organisations in the directory (1.0 %) were natural persons, shown with PIC, country and EU amounts, indexable** | the participation graph | as long as the organisation is in the source; a removal request is handled through `suppression` (kind organisation) |
| `organisation.individual_reason` (migration 0080, WP-39) | why the organisation is treated as a natural person. The rule is on the name (`dgate/individuals.py`): no legal form and no organisational word, two to five words, at least one a given name of a list; or a sole-proprietor form (PL "S.C.", DE "e.K.", RO "PFA", FR "EIRL") beside a given name; or an owner's name in a trailing parenthesis. It runs with every directory rebuild and with `python -m dgate.ops.mark_individuals`. Such an organisation is **shown nowhere**: not in the directory or the sitemap, its profile is a 410, inside a project or a partner list its name is "Name not shown" and what it received is not shown. The row, its participations and its aliases stay (nothing is deleted). Measured on a copy of the production tables on 18 October 2026: 710 of 73,347 organisations flagged (0.97 %), with about 960 participations in 880 projects and EUR 122 million of EU contribution attached (counted on 699 flagged before the last five names were added); none is also a buyer or a supplier. Hand checks on fresh random samples (taken before the last five names were added to the list): of 100 flagged names 3 were organisations (a cooperative, a Portuguese Lda named for a person, a publisher named for its founder) and 7 were businesses named for their owner (hidden on purpose, they carry a person's name); of 150 unflagged candidate names (two to four plain words, no organisational word) 5 were persons whose names are not on the list, which is about 150 of 4,569. So the rule finds roughly four persons in five among Latin-script names and hides about one organisation in thirty; Arabic, Albanian, Chinese and Indian names are mostly missed and a script other than Latin is not read | the directory must not show persons | follows the participation |
| `project`, `participation` | project title, acronym, grant number, call and topic, dates, cost and EU contribution; per organisation: role, EU contribution and how the link was decided. No person, no contact, no abstract | the participation graph | rows are never deleted by the importers (a participant who left is marked inactive) |
| `consortium_snapshot`, `consortium_change` | the list of organisations of a project at a date and the difference between two dates | history that no public source keeps | indefinite |
| `project_factsheet` | what the language model reported from one EDF factsheet (organisation names, countries, role, amounts) and what the quote check dropped. The technical description of the project is cut before the text is landed or sent to the model | audit of the extraction | indefinite |
| Raw store `cordis/` and `edf_factsheets/` | the result pages of the SPARQL service (organisation, project and participation fields) and the layout and plain text of each factsheet without its description (e-mail addresses are replaced before landing since WP-39; the 283 factsheets landed before are unredacted) | replay without refetching | as the rest of the raw store |
| `resolution_review`, `resolution_gold` | pairs of organisation ids waiting for a person; hand-labelled pairs of company names for the evaluation | working data | until decided; the gold set is a seed file in the repository |

Not held: payment data, passwords in a readable form (only the Argon2id hash; the API passes the password to the hash function and never logs it, the site's server passes it on and never logs or renders it), IP
addresses beyond the proxy's request log (14 days) and the keyed (HMAC) rate-limit counters, which are kept a day. The waitlist form
stores nothing (`web/app/(public)/actions.ts`). This file changes in the same commit as
the first feature that stores anything new.

## Readiness check (WP-29, 17 October 2026): nothing is held

The readiness check asks a company about its country, ownership and control, products and certificates. **None of it is stored or logged by the server.** The answers live in the visitor's browser (localStorage, `dg.profile.v1`). The verdict is computed by `POST /v1/readiness/assess`, which receives them in the body, keeps no copy, opens no write (it runs under the read-only API role; a test asserts it) and logs nothing of the body (a test asserts that too; the proxy's request log holds the address and the path, not a POST body). The company name and size entered in the wizard are not part of the request. WP-93 (23 October 2026) added answers that the call verdict reads and that are sent in the same request, only once answered and only as choices: the kind of organisation (company, university, research organisation), the staff-count band of the organisation and, for a member of a group, of the group, whether it is part of a group, the class of the country that controls it (Ukraine, an EEA EFTA state, China, Russia or Belarus, another country) and whether it holds an investor's pre-commitment; the old size class and the SEAP-partner answer still stay in the browser. They are kept in the same `dg.profile.v1` block (its `version` is now 4). A profile can say who owns a company, so it is treated as private even though it is not personal data of a natural person. The tables `requirement`, `requirement_issuer`, `requirement_prerequisite`, `readiness_programme` and `programme_requirement` hold public regulatory content only: no personal data and no contact details (a test checks the seed file for e-mail addresses).


## "Does this call fit me" and partner suggestions (WP-32, 17 October 2026): nothing new is held

The saved profile of the readiness check is read by the pages of the funding list, the changes list, the digest and a call page, in the browser only. **The profile is never part of a request except the one that computes a verdict** (`POST /v1/readiness/assess`, as above, now also with a call id, which is public). The badge "fits my profile" asks the site for the public document facts of the calls on the page (`GET /api/fit/facts?ids=...`: call ids only) and compares them with the profile in the browser. A visitor without a saved profile causes no such request. The partner list (`GET /api/funding/{slug}/partners`) carries a call and an optional country filter. The list loads with nothing about the profile in the request; the profile's country goes out, as `prefer=XX` (a two-letter code, nothing else of the profile), only when the visitor presses "Put organisations from <country> first", and the page says so beside the button (WP-38). The proxy's request log holds the address and the path with that query, as for the country filter a visitor picks by hand. The partner suggestions name **organisations** (their name as CORDIS or the EDF factsheet gives it, their country, the projects they took part in) and nothing about a person; an organisation removed on request (`organisation.suppressed`) is left out, and one merged into another is shown as the live one. No table is added and nothing is written by these endpoints (the API role cannot write).
The saved profile of the readiness check is read by the pages of the funding list, the changes list, the digest and a call page, in the browser only. **The profile is never part of a request except the one that computes a verdict** (`POST /v1/readiness/assess`, as above, now also with a call id, which is public). The badge "fits my profile" asks the site for the public document facts of the calls on the page (`GET /api/fit/facts?ids=...`: call ids only) and compares them with the profile in the browser. A visitor without a saved profile causes no such request (corrected on 18 October 2026: that also means the server can tell that a visitor who sends `/api/fit/facts`, or the partner request below, without having asked for it has a saved profile; it cannot tell who; the privacy notice 1.6 says so). The partner list (`GET /api/funding/{slug}/partners`) carries a call and an optional country filter; the profile's country only orders the answer in the browser. The partner suggestions name **organisations** (their name as CORDIS or the EDF factsheet gives it, their country, the projects they took part in) and nothing about a person; an organisation removed on request (`organisation.suppressed`) is left out, and one merged into another is shown as the live one. No table is added and nothing is written by these endpoints (the API role cannot write).

## Eligibility reading of funding calls (WP-31 and WP-34, 17 October 2026)

The worker reads the call documents of EU funding calls (public PDFs of the Commission, and the topic texts of the funding portal) with a language model and keeps the eligibility facts. Held, written only by the worker (`dgate/eligibility.py`), read by the API role (`call_eligibility` only):

| Where | What | Why | Retention |
|---|---|---|---|
| `call_document_text` | the plain text of each call document (up to 350,000 characters), its hash, page count and fetch time. **E-mail addresses are replaced by `[email removed]` before the text is stored and before it is sent** (since WP-34; texts stored before are cleaned once with `python -m dgate.ops.extract_eligibility --redact-stored --yes`). A name or telephone number typed into a document is not removed; the documents are public calls for proposals and name a contact point at most. Not served | to check a quote again and to re-read without a new download | as long as the call is on the site; replaceable |
| `call_eligibility` | per document: the facts the model reported (countries, entity types, consortium size, funding rate, and so on), each with a verbatim quote from the document, a confidence, and whether the quote was found (`verified`), the model name, prompt version, tokens and cost. Only verified facts are served, with e-mail-shaped text redacted again on output | the eligibility line of a call | as long as the call is on the site; replaceable |
| `llm_usage` | per day, task and model: requests, tokens, cost in USD. No text, no identifier | the monthly spending cap | indefinite; contains no person |
| `digest_issue`, `list_snapshot` | the weekly digest issues and pre-computed list pages, built from the public serving rows (titles, buyers, dates). They hold what the serving rows held at the time; a removal on request deletes them in the same transaction and the digest is rebuilt (WP-34 C1, C2) | speed; the digest archive | replaceable |

**Processor: OpenAI** (`api.openai.com`, Responses API, `store: false`). The data sent is the cleaned text of a public call document or topic text, **and (corrected on 18 October 2026, verify2-abuse N6) the layout text of each EDF project factsheet without its technical description, with the names of the participants (task `edf_factsheet`: 283 factsheets, 284 requests)**, and the instructions; no visitor, account or request data is ever sent. E-mail addresses are removed from the call documents since WP-34 and from the factsheet text since WP-39 (`edf_factsheets.read_pdf`, before the text is landed, quoted or sent). **The 283 factsheets already read were sent before that removal**; whether any printed an address was not checked (the stored result, `project_factsheet.facts`, holds none, and the two rows with an "@" are the brand name SYSTEM@TIC). The layout and plain text of those factsheets as landed in the raw store (`edf_factsheets/`) are unredacted; rewriting a bundle of the immutable store is the owner's decision, as for the older payloads above. The key is held by the worker only. Whether a data processing agreement, the provider's retention terms and a transfer mechanism for the United States are in place is for the owner and the lawyer to confirm; this file does not decide it. The privacy notice names the processor for call documents (version 1.5, published 18 October 2026); the wording that adds the factsheets and the open transfer question is version 1.6, a draft awaiting approval (`docs/legal/versions/privacy-v1.6-2026-10-18.md`).
## Supplier map (WP-37, 18 October 2026)

| Where | What | Why | Retention |
|---|---|---|---|
| `award`, `award_notice` | per TED result notice of the core scope: the winning organisation (name as the buyer published it, country, registration number as published), the notice it won and how the organisation was found. Counts of the winners left out (natural persons, no country, placeholders, consortium strings, garbled names). **Before 18 October 2026 (WP-39, verify2-abuse N1) the identifier field also kept whatever a buyer typed into it: 1 e-mail address and 3 telephone numbers on 4 of 4,186 profiles, and 547 of 8,368 stored values were not registration numbers.** Now only a number-shaped value is stored and shown (a leading "+", a "tel" label or an "@" makes a value contact data), and `python -m dgate.ops.clean_suppliers --yes` cleans what was stored, including the registration number two organisations had been given from a telephone number. `award.excluded_reason` (migration 0080) marks winner strings that are no supplier; the row is kept and every supplier query skips it | the supplier map | rows are never deleted by the loader; a removal request is handled through `suppression` (kind organisation or notice) |
| `organisation` (new rows), `organisation_alias` | the legal name, country and registration number of every winner | the same | as for the participation graph above |
| Raw store `ted_awards/` | the winner fields of each result notice as TED returned them, **with the entries of natural persons blanked** (`[natural person]`, their number removed) before the record is landed | replay without refetching | as the rest of the raw store |
| Raw store `placsp_awards/` (WP-60, source `es_placsp_awards`) | the award results of each kept PLACSP folder: per lot the result code, award date, tenders received, value, and per winning company its name, tax number (CIF) and country. **A natural person is landed as `{"natural_person": true}` only**: no name, no NIF (DNI, NIE or the publisher's masked "***1234**"), no address; the folder keeps a count of its persons. No winner's street, city or postcode is landed; the result's free-text description is not read. A UTE keeps its name with any member that reads as a person replaced by `[natural person]` (`dgate/placsp_awards.py: redact`) | replay without refetching; the supplier map | as the rest of the raw store |
| `award`, `award_notice` for PLACSP notices (WP-60) | as for TED above, from the landed payloads; `award.superseded_at` marks a winner a later entry no longer names (never deleted). **Not served**: the supplier map leaves PLACSP winners out unless `DGATE_PLACSP_AWARDS_PUBLIC=true`, an owner decision after `docs/sources/es_placsp.md` (commercial reuse allowed by the ministry's aviso legal; natural persons governed by LO 3/2018 and not kept) | stored for the owner's decision | as above |

A winner that looks like a natural person (a sole trader under their own name, a Polish trading name that ends in the
owner's name, an "e.K.") is skipped by `dgate/awards.py: person_reason` and written nowhere. It is a rule on names:
measured on 18 October 2026, of 5,997 distinct core-scope names 184 were skipped (about two thirds of those read by
hand were persons) and about 0.8 % of the rest are probably still a person (`docs/design/SUPPLIER_MAP_FEASIBILITY.md`,
section 3). The public pages say how to ask for a removal. Winners are public in TED; the map adds that they are
collected per company, which is why the aggregate publishes no group of fewer than three suppliers.

**Corrected on 18 October 2026 (verify2-abuse N5, N7):** that rule held for `/v1/suppliers/summary` only, and the
statement that "the pages carry no ranking, share or total" was wider than the truth: the list shows, per supplier, the
number of notices it won (`awardCount`) and can be ordered by it. The list now holds the group rule too: a country or
product-group filter that selects fewer than three suppliers answers "withheld" whatever the sort or the search word
(the group is judged without the search word, so a name search inside a large group works), and it serves at most 500
positions (`suppliers.MAX_OFFSET`; the table was 4,186 suppliers, so 42 requests of 100). A page beyond the cap is
refused (the site answers 404 for it). Narrowing by name, country or product group still reaches every supplier that is
not in a small group, so the cap raises the price of copying the table; it does not forbid it, and the rate limit prices
the rest. The pages state no contract value per supplier, no share and no ranking by value.

Names that are no supplier (N8): a placeholder ("keine Angabe"), a consortium written as one string, text with a
replacement character, contact data in the name, are refused by the loader and counted (`skipped_placeholder`,
`skipped_consortium_string`, `skipped_garbled`, `skipped_contact_in_name`); a role note after one company ("- Lider") is
removed and the company kept. `python -m dgate.ops.clean_suppliers` marks what was stored (dry run unless `--yes`).

## Who can read it

The API and worker service roles (`dgate_api`, `dgate_worker`), the owner on the host,
and whoever holds the Storage Box key. The private half of the backup key is only on the
owner's laptop. The raw store is private and never served. **Corrected on 18 October 2026:**
it is not true that nothing is public except what `/v1/*` returns. The organisation, project
and analytics data (`/v1/organisations*`, `/v1/projects*`, `/v1/analytics/*`, `/v1/fit/facts`) is
blocked at the proxy but public through the HTML pages that read it. What the public gets is the
redacted view, since WP-39 without organisations that are natural persons and without contact data
in a supplier's identifiers; what is behind it (the raw store, the archive snapshots, the account
tables) is not public.

An organisation entry in `suppression` now also clears what was derived from it: the directory table
`organisation_network` (the list, its count, the sitemap slugs and the partner lists) loses the merge
family's rows in the same transaction (a database trigger, migration 0080, verify2-abuse N3), and
`python -m dgate.ops.suppress lift` rebuilds it. What can still be shown after an entry, from caches that no
command can clear: an organisation list or a partner tab for up to five minutes, the Ukraine and gap
analytics for up to fifteen, the site's own pages for five, a feed reader for an hour.

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
