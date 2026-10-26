# WP-140 self-check: privacy 1.7 and terms 2.2 published (accounts part)

Brief: `D:\DEFENCEGATE TESTS\verify-oct25\BUILDER-WP140.md` (owner approval in chat, 25 Oct 2026). Branch `wp-wp140` from
`integration` (d2cb603). No migration, no ops module. Production was only read (SQL through the postgres container with a
30 s statement timeout; `infra/.env` read for "set / empty" of variable names only, no value printed; three small report
files in /root). Test copy `D:\DEFENCEGATE TESTS\wp140\`.

**Publication date: 26 October 2026** (the planned deploy date; if the deploy is later, change the date in the two page
leads, the two archive file names and first lines, `accounts.py` comments and `tests/unit/test_wp140.py`).

> **TODO (orchestrator), privacy section 7, e-Zamowienia sentence.** The page says the Polish result notices landed until
> 21 Oct 2026 "were cleaned again in October 2026" (`EZAM_CLEANED` in `web/app/(public)/privacy/page.tsx`, and the same
> sentence in `docs/legal/versions/privacy-v1.7-2026-10-26.md`). The re-strip (`ops.restrip raw --source pl_ezam --yes`)
> started on 25 Oct 18:55 UTC (`/root/restrip-raw-ezam-report-oct25.log`). After its result: set the date
> (e.g. "on 26 October 2026") in both places, or, if it did not finish clean, take the sentence out of both before deploying.
> Also update `docs/DATA_PROTECTION.md`, row "Raw store, `pl_ezam/`".

## 1. Privacy 1.7

Every WP-123 and WP-131 row of `docs/legal/drafts/privacy-v1.7-draft.md` is in `web/app/(public)/privacy/page.tsx` as
drafted: lead, "In short" items 5 and 6, section 4 (`dg.profile.v1` with the list of what is sent, `dg-answer:`,
`__Host-dg_mfa` instead of `__Host-dg_bind`), section 5 (opening, all new items, the counters item, the security log
**90 days**, legal basis, Mail with **Brevo (Sendinblue SAS, France)**, Retention, last sentence; "We do not use
passwords" removed), section 6 (no forms), section 7 Archive (re-counted, below), section 8 mail item (Brevo) and the
**OpenAI item exactly as drafted, with no transfer-basis sentence**. Sections 1, 2, 3, 9, 10, 11 unchanged.
Left out: every WP-124 row (Creem, "Choosing a plan charges nothing by itself", the paid-plan items, legal basis and
retention additions, the Creem recipient, section 9 transfers). The plan-choice item of section 5 is the WP-123 one
("... gives no paid plan; until payment opens every account is on the free plan").
Archive copy: `docs/legal/versions/privacy-v1.7-2026-10-26.md` (extracted from the page source, as earlier copies);
`docs/legal/versions/README.md` has the line. `PRIVACY_VERSION = "1.7"`.

## 2. Section 7, the Archive item: figures re-counted (production, read-only, 25 Oct 2026)

| Part of the draft | Draft figure | Re-count | In the published text |
|---|---|---|---|
| History of notices (`opportunity_version.payload`) | 221 versions with an e-mail address (21 Oct), 113 of 12-14 Oct | **0** versions hold an e-mail address (nine id-range SELECTs over 839,671 versions, regex of `normalise._EMAIL`); 124 hold an "@" that is not an address. The observed days of the 221 (TED 17 and 19 Sep, pl_atlas 13 Sep, TED 12 Oct) now carry `[email removed]`; the append-only trigger is enabled (`O`) | **dropped**, as the draft says for a part a clean-up has removed. **For the orchestrator:** `DATA_PROTECTION.md` said the break-glass was "not run"; who redacted these rows is not recorded (no `/root/restrip-wp71.sql`). Confirm before deploying |
| Raw store, TED | "about 100 TED notices collected between 14 and 19 September" | cannot be counted by SQL (Storage Box). The latest count is the re-strip report of 22 Oct (`/root/restrip-raw.log`, today's boundary): **864 of 4,460 `ted/` bundles, 12,605 records** landed until 21 Oct would still change; the `--yes` pass of `ted/` was stopped by the owner the same day | "up to about 12,600 TED records landed until 21 October 2026 that hold contact fields the collection now removes (counted on 22 October 2026)": "about 100" was narrower than the report |
| Raw store, PLACSP before 12 Oct | not counted | not counted (no SQL path) | as drafted |
| Raw store, e-Zamowienia | not in the draft (brief item 2) | 25 Oct check: 711 records, 947 person entries; re-strip running | "were cleaned again in October 2026" (TODO above) |
| Organisation names with a contact block | about 960 names, about 1,030 spellings | **961** organisation rows, **1,133** aliases (96 with an e-mail), same filter as WP-115 (`org_repair._CONTACT_SQL`) | "about 960 names of public buyers (with about 1,130 spellings)" |

Term 20 (2.2) has no figures; its sentences are still true after the re-count (older raw records and buyer names still
hold contact details; none shown). "In short" item 6 likewise.

## 3. Terms 2.2

Term 14 (both paragraphs, including "Choosing a plan ... is not an order") and term 20 (first two sentences) as drafted;
every other term word for word 2.1. Not published: the WP-124 term "Paid plans". The lead names version 2.2 of
26 October 2026 and what changed (my wording, in the pattern of the 2.1 lead). `TERMS_VERSION = "2.2"`: the
registration form shows the versions `/v1/account/status` returns, so it now shows 2.2 and 1.7, and a registration that
sends other versions is refused (unchanged code). Archive copy `docs/legal/versions/terms-v2.2-2026-10-26.md`.

## 4. The sign-in gate

What opened sign-in on integration (`accounts.accounts_problem`, any one closes it):
1. `PRIVACY_VERSION` < `PASSWORD_PRIVACY_VERSION` ("1.7"): closed while 1.6 was published. **Publishing 1.7 removes it.**
2. production without `DGATE_ACCOUNT_KEY`: production has it set.
3. `mailer.ready()`: SMTP host and sender set and the relay passing the API's health check (connect, TLS, login, NOOP;
   no mail sent). Production has every `DGATE_SMTP_*` set; whether the relay passes now I could not read (container
   logs are not mine to read).

So publishing 1.7 **would open sign-in by itself** as soon as the relay passes, with the imprint still empty. Hence:

**The switch.** `DGATE_ACCOUNTS_OPEN` (`config.accounts_open`, true only for the value `1`): in production
`accounts_problem()` returns `"DGATE_ACCOUNTS_OPEN"` until it is `1`, after the key check and before the relay check.
`infra/docker-compose.yml` passes `${DGATE_ACCOUNTS_OPEN:-0}` to the API only. Development and tests do not need it
(as with `DGATE_ACCOUNT_KEY`), so the e2e and integration runs keep working. `infra/.env` on the server has no such line:
**after the deploy sign-in stays closed**. To open: add `DGATE_ACCOUNTS_OPEN=1` to `infra/.env` and recreate `api`.

**Section 5 sentence.** The privacy page reads `/v1/account/status` (cached 60 s, any failure = closed) and shows
"**Sign-in is not open yet.** This section describes what applies once it opens." only while `open` is false
(`data-signin-closed`); it disappears by itself when the API says open. The status is false while the switch is closed,
and also while the relay fails, which is true then as well. The page is now rendered per request (`dynamic =
'force-dynamic'`, was `revalidate = 3600`): the first open-state run failed because `next start` served the HTML built
while the API was absent (closed) for up to an hour; the status fetch itself stays cached 60 s.

## 5. DATA_PROTECTION.md, OPEN_ITEMS_FOR_LAWYER.md

- `docs/DATA_PROTECTION.md`: the accounts paragraph (1.7 published, the switch), the mail relay row (Brevo, named), the
  OpenAI paragraph (1.7 section 8), and the re-counts in rows "Raw store" (TED report), `opportunity_version.payload`
  (0 now, how to be confirmed) and organisation names (961 / 1,133).
- `docs/legal/OPEN_ITEMS_FOR_LAWYER.md`: new row P9 (what 1.7 and 2.2 published and what the lawyer still reviews:
  security log basis and period, Brevo DPA, OpenAI DPA and transfer mechanism, archive item and term 20, `?prefer=`,
  the plan paragraph); P7/P8 noted as published, review open; engineering item 5 notes the dated counts.
- Drafts: a "published 26 October" note on top of both; the WP-124 parts stay drafts.

## Tests

| Change | Test |
|---|---|
| switch: only `1` opens; closed by default in production with key and relay; dev needs none; compose default `0`, API only | `tests/unit/test_wp140.py` (new, 13 cases) |
| shipped settings keep production closed, a registration is refused with 503 until the switch | `test_accounts_wp123.py::test_the_shipped_settings_keep_accounts_closed` (replaces `test_the_shipped_versions_keep_accounts_closed`, whose premise, 1.6 < 1.7, ended with the publication; the property "shipped = closed" is kept, now by the switch) |
| the key is still needed with the switch on | `test_in_production_accounts_need_the_apis_own_key` (sets the switch; was open without it) |
| versions = page leads = archive files; no Creem / "Paid plans" on either page | `tests/unit/test_wp140.py` |
| page closed state: 1.7, `__Host-dg_mfa`, Argon2id, Brevo, 90 days, "Sign-in is not open yet", no `__Host-dg_bind`, no Creem; terms 2.2 | `e2e/wp79.spec.ts` "the privacy notice 1.7 ..." (replaces the WP-123 test that held the page at 1.6 until approval) and "the terms 2.2 ..." |
| page open state: no "Sign-in is not open yet" | `e2e/wp79.spec.ts` "WP-140: once accounts are open ..." (fake account API, runs in `web-gated.yml`) |
| mail provider named | `e2e/wp63.spec.ts` (asserted "None has been chosen yet"; now asserts the Brevo sentence and its absence) |

Results: see below.

## Overlaps

WP-137, WP-138, WP-139 had no commits when I checked. Files of mine another package may also touch:
`docs/DATA_PROTECTION.md` (WP-138, data), `infra/docker-compose.yml` (one line in `api`). WP-139 (site texts):
/methodology and /about carry the same archive figures (221 versions, about 1,000 buyer names) and are not changed here;
with the re-count above they are now stale ("221 archive versions"): theirs to fix, or a follow-up.

## Open

- The TODO above (e-Zamowienia date) and the history-of-notices redaction to confirm.
- Owner: the imprint is empty; `DGATE_ACCOUNTS_OPEN=1` only when the owner says so. Brevo's data processing agreement.
- Lawyer: P9 (and P7, P8).
- `tests/e2e_api.py` still sets `PASSWORD_PRIVACY_VERSION = PRIVACY_VERSION` (now a no-op, left as is).
