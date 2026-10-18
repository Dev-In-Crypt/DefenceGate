-- WP-35 (17 October 2026). Additive and idempotent.
--
-- A call document covers many topics and its rules differ between them, so the answer of the
-- model is kept per (document, topic): the key of such a row is '<document url>#<topic code>'.
-- That key is no longer a row of `call_document_text`; `document_url` is the text it was read
-- from (equal to `url` for the rows read before, for general annexes and for topic texts).
ALTER TABLE call_eligibility DROP CONSTRAINT IF EXISTS call_eligibility_url_fkey;
ALTER TABLE call_eligibility ADD COLUMN IF NOT EXISTS document_url TEXT REFERENCES call_document_text(url);
UPDATE call_eligibility SET document_url = url WHERE document_url IS NULL;
