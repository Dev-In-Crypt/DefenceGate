-- WP-101 (persona round of 24 October 2026): the tender search reads words folded once, when a notice is written.
--
-- The search (`tenders._tender_filters`) matched every word and every term of a product group against
-- `dg_fold(o.title_en)`, `dg_fold(o.title_original)` and `dg_fold(o.buyer_name_raw)` (migration 0054), and the
-- trigram indexes over those expressions found the candidates. But the index cannot answer a LIKE or a regular
-- expression by itself: every candidate row is re-checked, and the check folds the title again, once per term. A fold
-- costs 0.13 ms on production (the `translate` of 90 accented letters), and "Drehteile Frästeile" (two words of the
-- spare-parts group, 17 terms each) re-checked about 13,000 candidates with some 50 folds each: 12.6 s, a 503 every
-- time (production, 24 October 2026). The CPV part of a group (`dgate_cpv_heads(cpv_codes)`, 0.04 ms a row) was
-- computed again in the same way.
--
-- This table holds those folded texts and code heads once per notice, written by a trigger whenever the notice's
-- titles, buyer name, buyer withholding or codes change; the search reads it (`EXISTS (... opportunity_search s
-- WHERE s.id = o.id AND ...)`), so a re-check is a regular expression over stored text. Derived, replaceable data:
-- the backfill below rebuilds it from `opportunity` and nothing else reads it.
--
--   title_en, title_original  dg_fold() of the titles (' ' when there is none, as dg_fold gives)
--   buyer_name                dg_fold(buyer_name_raw), NULL while the buyer is withheld (the search never matches it)
--   cpv_heads                 dgate_cpv_heads(cpv_codes) (migration 0099)
--   native_id                 the notice number as stored, for the search by number
--
-- On production the backfill folds about 394,000 notices (about 3 minutes on the 2-core host) and the trigger takes
-- a lock on `opportunity` until the migration commits, so a load that writes notices waits for it: run it when no
-- load is running. Idempotent: a second run inserts nothing and keeps the indexes.

CREATE TABLE IF NOT EXISTS opportunity_search (
    id              BIGINT PRIMARY KEY REFERENCES opportunity(id) ON DELETE CASCADE,
    title_en        TEXT NOT NULL,
    title_original  TEXT NOT NULL,
    buyer_name      TEXT,
    cpv_heads       TEXT[] NOT NULL,
    native_id       TEXT NOT NULL
);

CREATE OR REPLACE FUNCTION dgate_opportunity_search_row() RETURNS trigger
    LANGUAGE plpgsql AS $f$
BEGIN
    INSERT INTO opportunity_search (id, title_en, title_original, buyer_name, cpv_heads, native_id)
    VALUES (NEW.id, dg_fold(NEW.title_en), dg_fold(NEW.title_original),
            CASE WHEN NEW.buyer_withheld THEN NULL ELSE dg_fold(NEW.buyer_name_raw) END,
            dgate_cpv_heads(NEW.cpv_codes), NEW.native_id)
    ON CONFLICT (id) DO UPDATE SET title_en = EXCLUDED.title_en, title_original = EXCLUDED.title_original,
        buyer_name = EXCLUDED.buyer_name, cpv_heads = EXCLUDED.cpv_heads, native_id = EXCLUDED.native_id;
    RETURN NULL;
END;
$f$;

DROP TRIGGER IF EXISTS opportunity_search_insert ON opportunity;
CREATE TRIGGER opportunity_search_insert AFTER INSERT ON opportunity
    FOR EACH ROW EXECUTE FUNCTION dgate_opportunity_search_row();
-- Any update whose final row differs in a searched column (the suppression trigger of 0047 sets buyer_withheld itself)
DROP TRIGGER IF EXISTS opportunity_search_update ON opportunity;
CREATE TRIGGER opportunity_search_update AFTER UPDATE ON opportunity
    FOR EACH ROW WHEN (OLD.title_en IS DISTINCT FROM NEW.title_en
                       OR OLD.title_original IS DISTINCT FROM NEW.title_original
                       OR OLD.buyer_name_raw IS DISTINCT FROM NEW.buyer_name_raw
                       OR OLD.buyer_withheld IS DISTINCT FROM NEW.buyer_withheld
                       OR OLD.cpv_codes IS DISTINCT FROM NEW.cpv_codes
                       OR OLD.native_id IS DISTINCT FROM NEW.native_id)
    EXECUTE FUNCTION dgate_opportunity_search_row();

INSERT INTO opportunity_search (id, title_en, title_original, buyer_name, cpv_heads, native_id)
SELECT o.id, dg_fold(o.title_en), dg_fold(o.title_original),
       CASE WHEN o.buyer_withheld THEN NULL ELSE dg_fold(o.buyer_name_raw) END,
       dgate_cpv_heads(o.cpv_codes), o.native_id
  FROM opportunity o
ON CONFLICT (id) DO NOTHING;

CREATE INDEX IF NOT EXISTS opportunity_search_title_en ON opportunity_search USING gin (title_en gin_trgm_ops);
CREATE INDEX IF NOT EXISTS opportunity_search_title_original ON opportunity_search USING gin (title_original gin_trgm_ops);
CREATE INDEX IF NOT EXISTS opportunity_search_buyer_name ON opportunity_search USING gin (buyer_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS opportunity_search_native_id ON opportunity_search USING gin (native_id gin_trgm_ops);
CREATE INDEX IF NOT EXISTS opportunity_search_cpv_heads ON opportunity_search USING gin (cpv_heads);

GRANT SELECT ON opportunity_search TO dgate_api, dgate_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON opportunity_search TO dgate_worker;

ANALYZE opportunity_search;
