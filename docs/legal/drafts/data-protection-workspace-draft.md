# Team workspace and client profiles (WP-157): DRAFT additions for docs/DATA_PROTECTION.md and the privacy notice (30 October 2026)

**Not published. For the owner's approval.** Nothing here changes a live text: `docs/DATA_PROTECTION.md` and
`web/app/(public)/privacy/page.tsx` stay as they are. Accounts are closed (`DGATE_ACCOUNTS_OPEN` unset), so no workspace,
invitation or client profile can be made until the owner opens them; these texts should be in place before that.

## What is held (migration 0149)

Rows to add to the inventory table of `docs/DATA_PROTECTION.md`, after the plan split rows:

| Where | What | Why | Retention |
|---|---|---|---|
| `workspace` (migration 0149, WP-157) | per workspace: the owner's account id, when it was made | the team workspace (Team, Consultant) | until the owner ends it or deletes the account (cascade) |
| `workspace_member` | per member: workspace, account id, role (owner, member), when it joined | members share the owner's plan and see one another's saved searches, shortlist and follows | until the member leaves, is removed, or the workspace or the account goes (cascade) |
| `workspace_invite` | per invitation: the **e-mail address the owner typed** (as typed and canonical), the SHA-256 of the one-time token (the token itself is only in the mail), when it was sent, when it expires (7 days), when it was used | invite a colleague; only an account with that address can accept | deleted a day after it expired or was used (`workspace._prune`, at each invitation and each listing); all with the workspace (cascade). The invited person may never have had an account with us: their address is held for at most 8 days unless they join |
| `app_client` | per client profile (Consultant): a company name, its country, CPV codes, a note (up to 500 characters), dates. Commercial information about the consultant's client; free text, so it can hold a person's name if one is typed (a sole trader client); the form asks for no names of people and no contact details | label saved searches and shortlist entries, put the client's name on its company reports | until removed, the workspace ends or the owner's account is deleted (cascade) |
| `app_saved_search.workspace_id` / `client_id`, `app_shortlist.workspace_id` / `client_id`, `app_follow.workspace_id` | which workspace a member's row is shared with, and which client profile it belongs to | sharing; filtering by client | cleared when the member leaves or is removed and when the workspace or the client goes |
| Mail relay (Brevo, as now) | the invitation mail: the invited address, the link with the token. It names no inviter address | delivery | the relay's own |
| Security log, workspace lines | `account event=workspace_created|workspace_invite|workspace_joined|workspace_left|workspace_removed|workspace_dissolved user=<account id> workspace=<id>` (and the invitation or member id); never an address or a token | evidence of who joined which workspace when | as the accounts lines (90 days) |

Who sees what inside a workspace: every member sees the other members' e-mail addresses (the member list of the Team page),
their saved searches (name and filters), their shortlist entries with status and note, and their follows. The owner also sees
the addresses of the open invitations. Nobody outside the workspace sees any of it.

The data export (`GET /v1/account/export`, "Download my data") now includes `workspace`: the role and the date joined; for the
owner also the invitations sent (address, dates) and the client profiles. A member's own searches, shortlist entries and follows
were already in the export. Deleting a member's account deletes its membership and its rows; deleting the owner's account ends
the workspace (the members keep their own rows).

## Privacy notice: proposed addition (next version, section 5 "Accounts")

> **Team workspaces.** If you make a team workspace, you can invite colleagues by e-mail. We send the invitation and keep the
> address you typed until the invitation is used or expires, and for one more day. Members of a workspace see one another's
> e-mail addresses, saved searches, shortlist entries (with statuses and notes) and follows. When you leave a workspace, your
> own searches, shortlist entries and follows go with you.
>
> **Client profiles.** If your plan has client profiles, you can record the companies you work for: a name, a country, CPV
> codes and a note. Please record commercial information only, not names of people or contact details.

## Open for the owner

- The invited person is not our user yet: the invitation mail is sent on the inviter's instruction. Lawful basis to be named
  by the lawyer (likely Art. 6(1)(f), the inviter's and our interest in a requested introduction; one mail, no reminders).
- Whether members should see one another's e-mail addresses, or only a count (the Team page shows them now).
