# Published texts

One dated static copy of every version of the Terms of use and the Privacy notice that has
been published on the site, as plain text. These are what "earlier versions are kept and
available on request" is answered from; the page source is not the record.

Name: `<terms|privacy>-v<version>-<publication date>.md`.

To add one when a version is published (the same change that bumps the label on the page
and `TERMS_VERSION` / `PRIVACY_VERSION` in `backend/dgate/accounts.py`):

1. Copy the text of the new page into a new file with the name above. Say at the top that it
   is a static copy and which commit it was taken from.
2. Never edit a file once its version is published. A correction is a new version.

Present: Terms 2.0 (14 Oct 2026), Privacy 1.3 (14 Oct 2026), Privacy 1.4 (15 Oct 2026). Privacy 1.5 (18 Oct 2026) names OpenAI as a processor; published on the owner's instruction, a lawyer's review is open (OPEN_ITEMS_FOR_LAWYER.md P7).
Privacy 1.6 (written 18 Oct 2026, WP-39) is a DRAFT for the owner's approval and is **not published**: `privacy-v1.6-2026-10-18.md` is its static copy and the page source and `PRIVACY_VERSION` already carry it. Publishing it means setting the date (file name, first lines, the page's lead) and removing the draft sentence from the copy; until then 1.5 is the text in force.
Privacy 1.7 and Terms 2.2 (26 October 2026, WP-140, approved by the owner on 25 October 2026): accounts with an e-mail address and a password, Brevo as the mail processor, OpenAI as the only language-model processor, the archive item re-counted; the WP-124 payment additions are not in them (they wait for Creem in `docs/legal/drafts/`). Privacy 1.6 and Terms 2.1 were published on 24 October 2026 from the page source with no static copy made here (`privacy-v1.6-2026-10-18.md` is the 18 October draft, not the text published); both published texts are in git history, e.g. `git show d2cb603:"web/app/(public)/privacy/page.tsx"` and `.../terms/page.tsx`.
Privacy 1.8 (26 October 2026, WP-148, approved by the owner on 26 October 2026): Cloudflare as processor for network security and content delivery (In short, sections 2, 4 and 8, from `docs/legal/drafts/privacy-cloudflare-draft.md`); the rest is 1.7 word for word. Terms stay 2.2.
Terms 1.1 and earlier, Privacy 1.2 and earlier: texts are in git history only
(`git log -- "web/app/(public)/terms/page.tsx"`), not copied here.
