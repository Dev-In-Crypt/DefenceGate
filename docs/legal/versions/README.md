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

Present: Terms 2.0 (14 Oct 2026), Privacy 1.3 (14 Oct 2026), Privacy 1.4 (15 Oct 2026).
Terms 1.1 and earlier, Privacy 1.2 and earlier: texts are in git history only
(`git log -- "web/app/(public)/terms/page.tsx"`), not copied here.
