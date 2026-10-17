-- Partner suggestions for a funding call (WP-32, dgate/partners.py): the projects of "the same area" are found
-- by the capability category of an EDF project and by the topic code of a CORDIS project. Additive and idempotent.
--
-- The topic code is compared in upper case (CORDIS writes HORIZON-JU-EuroHPC-...), as a prefix first, so the
-- index is on the upper-cased expression with the pattern operator class that makes LIKE 'HORIZON-CL3-%' use it.
CREATE INDEX IF NOT EXISTS project_category ON project (source_id, category) WHERE category IS NOT NULL;
CREATE INDEX IF NOT EXISTS project_topic_upper ON project (upper(topic_code) text_pattern_ops) WHERE topic_code IS NOT NULL;
