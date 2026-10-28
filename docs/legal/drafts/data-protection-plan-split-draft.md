# Plan split (WP-155): DRAFT additions for docs/DATA_PROTECTION.md and the privacy notice (28 October 2026)

**Not published. For the owner's approval.** Nothing here changes a live text: `docs/DATA_PROTECTION.md` and
`web/app/(public)/privacy/page.tsx` stay as they are. The company report is closed (`DGATE_COMPANY_REPORT_OPEN` unset), so
neither the report counts nor the name on reports can be written until the owner opens it; these texts should be in place
before that.

## What is held (migration 0147)

Rows to add to the inventory table of `docs/DATA_PROTECTION.md`, after the API key rows:

| Where | What | Why | Retention |
|---|---|---|---|
| `app_user.report_name` (migration 0147, WP-155) | the text an account holder on the Consultant plan chose to print in the head of its company reports ("Name on reports", up to 80 characters, plain text on one line). Usually a firm's name, but free text: it may hold a person's name if they type one | print it on the account's own reports | until the holder clears it or the account is deleted (a column of the account row). Kept, not printed, after a move to a plan without it |
| `company_report_open` (migration 0147) | per account, calendar month (UTC) and company: that the account opened that company's report, and when (first time that month) | count the reports of the month against the plan's number | the current and the previous month; older months are deleted by the accounts housekeeping (`accounts._prune`, every ten minutes); all of it with the account (cascade) |
| `app_user.api_licensed_at` (migration 0147) | when the operator granted the account a data API licence (empty: none) | only a licensed account may make and use API keys | until withdrawn (`python -m dgate.ops.api_licence --revoke --yes`) or the account is deleted |
| Security log, licence lines (WP-155) | `account event=api_licence_granted user=<account id>` and `api_licence_revoked`; never the address | evidence of who had a licence when | as the accounts lines (90 days) |

The data export (`GET /v1/account/export`, "Download my data") now includes the name on reports (`account.profile.reportName`),
`companyReports` (month, company id, time) and `apiLicensedAt`. Deleting the account deletes all three.

Which companies an account opened reports on is commercial information about the account holder's interest; it is never shown
to anyone else and never used for anything but the count.

## Privacy notice: proposed addition (next version, section 5 "Accounts")

> **Company reports.** When you open a company report we note, for that calendar month, which company's report you opened,
> so we can count your plan's reports. We delete these notes after the following month. If your plan prints your own name on
> reports, we keep the name you type in your settings until you clear it or delete your account.
>
> **Data licence.** If your organisation holds a data licence for our API, we note when it was granted.
