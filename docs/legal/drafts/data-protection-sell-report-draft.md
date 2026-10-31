# "Who to sell to" report (WP-162): DRAFT additions for docs/DATA_PROTECTION.md and the privacy notice (31 October 2026)

**Not published. For the owner's approval.** Nothing here changes a live text: `docs/DATA_PROTECTION.md` and
`web/app/(public)/privacy/page.tsx` stay as they are. The report is closed (`DGATE_COMPANY_REPORT_OPEN` unset), so nothing
below can be written until the owner opens it; these texts should be in place before that.

## What is held (migration 0154)

Rows to add to the inventory table of `docs/DATA_PROTECTION.md`, after the company report rows:

| Where | What | Why | Retention |
|---|---|---|---|
| Report form, not kept (default) | the answers of the form (company name, country, CPV and NACE codes, size, certificates, exports, classified work, US-origin parts) | make the one report asked for | none: used in memory for the request only, written to no log and no table (test `test_without_consent_the_form_reaches_no_log_and_no_table`) |
| `sell_profile` (migration 0154) | the same answers, one set per account, **only when the account ticked "Keep these answers on DefenceGate's server"** | fill the form in again for the next report | until the account deletes them (the form's button, `DELETE /v1/account/sell-report/profile`), replaces them with the next consented set, or deletes the account (cascade) |
| `sell_report_use` (migration 0154) | per report: the account, the calendar month (UTC), when, and for a report on a company in our data which company; for an association member drawing on its pool, the association. No field of a form | count the reports against the plan's monthly number or the association's yearly pool | the current and the previous calendar year; older rows are deleted by the accounts housekeeping (`accounts._prune`); all of it with the account (cascade) |
| `report_logo` (migration 0154) | the Consultant's own logo for the cover (PNG or JPEG, at most 10 KB) | print it on the account's own reports instead of ours | until the account deletes it or the account is deleted (cascade) |
| Security log lines (WP-162) | `account event=sell_report user=<account id> mode=A|B`, `sell_profile_saved`, `sell_profile_deleted`, `report_logo_set` (with its size); never a field of the form | evidence of use | as the accounts lines (90 days) |

The data export (`GET /v1/account/export`) now includes `supplierReports` (month, company id, time), `supplierProfile` (the kept
answers, or null) and `reportLogo` (type, size, time). Deleting the account deletes all of it.

The form describes a company (commercial data). The company name is free text: a sole trader may type their own name. That is
why it is kept only with consent, and never sent to a third party or a language model: CPV codes are suggested in the browser from
the CPV dictionary and our product-word map.

## Privacy notice: proposed addition (next version, section 5 "Accounts")

> **Supplier reports.** To make a "Who to sell to" report you describe your company in a form. We use the answers to make that
> report and keep them nowhere, unless you tick "Keep these answers on DefenceGate's server": then we keep one set of answers with
> your account until you delete them or your account. We note that you made a report (and, for a report on a company in our data,
> which company) to count your plan's reports, and delete these notes after the following year. If your plan prints your own name
> and logo on reports, we keep the logo you upload until you delete it or your account.
