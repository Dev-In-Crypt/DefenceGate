# Stop link of the alert mails (WP-161): DRAFT addition for docs/DATA_PROTECTION.md (31 October 2026)

**Not published. For the owner's approval.** `docs/DATA_PROTECTION.md` and the privacy notice stay as they are.

The e-mail alerts of saved searches could be stopped only after signing in. Since WP-161 every alert mail ends with a stop
link that works without signing in (`/unsubscribe?kind=alerts&token=...`, also in the `List-Unsubscribe` header); the page
asks before it stops anything (a button, so a mail scanner opening the link changes nothing).

Row to add to the inventory, beside the `app_user` row:

| Where | What | Why | Retention proposed |
|---|---|---|---|
| `app_user.alerts_stop_token` (migration 0153, WP-161) | per account: a random token (244 random bits) that can only switch that account's e-mail alerts off | let the person stop the alerts from the mail, without signing in | as the account (deleted with it) |
| Security log (WP-161) | `account event=alerts_unsubscribed user=<account id>`; never an address or the token | as the accounts lines | as the accounts lines (90 days) |

The token travels as `?token=` so the proxy drops it from its access log (`infra/caddy/Caddyfile`). It is not in the data
export (it is a credential of one action, like the reset links, which the export also leaves out).
