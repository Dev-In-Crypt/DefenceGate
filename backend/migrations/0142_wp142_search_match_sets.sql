-- WP-142 (r8-system, WP-139's open item): stored match sets for the frequent search words.
--
-- "ammunition" (8,851 notices) and "fuel" (7,024) took 3.3 s and 3.5 s cold on production on 26 October 2026: past the 5,000
-- matches `tenders.search_ids` reads once, every statement of the list re-ran the trigram scans of the word's regular
-- expressions. The worker now keeps the ids of the searches people make most (`tenders.refresh_search_sets`, with
-- ops/warm_lists, every four hours), and a request re-tests only the search rows written since the set was read:
--
--   search_match_set     key (sha256 of the condition and its parameters), the search as typed, the ids of every
--                        `opportunity_search` row that passed it, and the xmin of the snapshot they were read in;
--   opportunity_search.changed_xid   the transaction that last wrote the row (the trigger of 0113/0122, now also this):
--                        a row at or past a set's xmin may be newer than the set, and is re-tested; a row before it is not.
--
-- Derived, replaceable data: an empty table means every search runs live, as before. NULL `changed_xid` is a row written before
-- this migration, so before any set. Adding the column is a catalogue change (no rewrite); the index reads 394,000 rows once.

ALTER TABLE opportunity_search ADD COLUMN IF NOT EXISTS changed_xid xid8;

CREATE OR REPLACE FUNCTION dgate_opportunity_search_row() RETURNS trigger
    LANGUAGE plpgsql AS $f$
BEGIN
    INSERT INTO opportunity_search (id, title_en, title_original, buyer_name, cpv_heads, native_id, main_heads, changed_xid)
    VALUES (NEW.id, dg_fold(NEW.title_en), dg_fold(NEW.title_original),
            CASE WHEN NEW.buyer_withheld THEN NULL ELSE dg_fold(NEW.buyer_name_raw) END,
            dgate_cpv_heads(NEW.cpv_codes), NEW.native_id, dgate_cpv_heads(NEW.cpv_codes[1:1]), pg_current_xact_id())
    ON CONFLICT (id) DO UPDATE SET title_en = EXCLUDED.title_en, title_original = EXCLUDED.title_original,
        buyer_name = EXCLUDED.buyer_name, cpv_heads = EXCLUDED.cpv_heads, native_id = EXCLUDED.native_id,
        main_heads = EXCLUDED.main_heads, changed_xid = EXCLUDED.changed_xid;
    RETURN NULL;
END;
$f$;

CREATE INDEX IF NOT EXISTS opportunity_search_changed_xid ON opportunity_search (changed_xid);

CREATE TABLE IF NOT EXISTS search_match_set (
    key            TEXT PRIMARY KEY,
    q              TEXT NOT NULL,
    ids            BIGINT[] NOT NULL,
    snapshot_xmin  xid8 NOT NULL,
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT SELECT ON search_match_set TO dgate_api, dgate_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON search_match_set TO dgate_worker;
