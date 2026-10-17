-- WP-31 (17 October 2026). Additive and idempotent.
--
-- 1. Eligibility of calls that have no call document. The rules of a Horizon topic are in the
--    work programme's general annexes (one PDF shared by many calls) and in the topic's own
--    conditions text. A row of `call_eligibility` now says which it is:
--      call_document  the PDF the call links as its "Call document" (everything until now)
--      general        the general annexes (or the programme's own work programme), read once
--      topic          the topic's own "other eligibility conditions" text; its key is
--                     'call-text:<hash>' and its text is kept in `call_document_text`
ALTER TABLE call_eligibility ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'call_document';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'call_eligibility_scope_check') THEN
        ALTER TABLE call_eligibility ADD CONSTRAINT call_eligibility_scope_check
            CHECK (scope IN ('call_document', 'general', 'topic'));
    END IF;
END $$;

-- 2. The weekly digest. One row per ISO week (UTC) and country ('' is every country), built by
--    the worker: the last complete week every day, and any week that is missing, so a page is one
--    row read. A week with no row is computed on the spot by the API (slower). Derived from the
--    archive; replaceable.
CREATE TABLE IF NOT EXISTS digest_issue (
    week         TEXT NOT NULL CHECK (week ~ '^[0-9]{4}-W[0-9]{2}$'),
    country      TEXT NOT NULL DEFAULT '' CHECK (country ~ '^([A-Z]{2})?$'),
    week_from    TIMESTAMPTZ NOT NULL,
    week_to      TIMESTAMPTZ NOT NULL,
    body         JSONB NOT NULL,
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (week, country)
);

GRANT SELECT ON digest_issue TO dgate_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON digest_issue TO dgate_worker;
