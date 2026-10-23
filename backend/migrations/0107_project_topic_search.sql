-- WP-91 (UX audit 22 October 2026, section 6): organisations searched by the topic of their projects (/v1/organisations?topic=).
--
-- The search reads the folded acronym, title and EDF capability category of a project, word-initial like every other search
-- of the site (`dg_fold`, `dg_word_pattern`, migration 0054). The folded text is a stored generated column, so a search word and
-- its synonyms are matched against it without folding every candidate row again for each of them (measured on 80,000 synthetic
-- projects: "drone" with its four synonyms 3.0 s with the fold in the index expression, see docs/verification/product/
-- wp91-selfcheck.md), and the trigram index serves the LIKE. Additive and idempotent: nothing is dropped; the column is derived.

ALTER TABLE project ADD COLUMN IF NOT EXISTS topic_fold TEXT
    GENERATED ALWAYS AS (dg_fold(COALESCE(acronym, '') || ' ' || title || ' ' || COALESCE(category, ''))) STORED;

CREATE INDEX IF NOT EXISTS project_topic_fold ON project USING gin (topic_fold gin_trgm_ops);
