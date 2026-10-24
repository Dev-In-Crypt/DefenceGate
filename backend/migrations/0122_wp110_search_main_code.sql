-- WP-110 (round-4 re-check of 24 October 2026, search precision): the tender search reads a notice's codes by its MAIN code.
--
-- The search found a notice when any of its codes was a code whose English title a search word begins (WP-90) or a code of
-- a product group: q="wiring harness" listed a canteen, a concrete foundation and a battery room in Poland and France, all
-- main-coded 45000000 Construction work with 45311000 "Electrical wiring and fitting work" among their secondary codes, and
-- q=drone a Croatian pollution-control vessel (34513600) whose secondary codes hold 35512400 "Unmanned underwater vehicles".
-- A secondary code lists a part of the works; the main code says what the notice buys. So the search now reads the code heads
-- of the main code only (`main_heads`, as `cpv_heads` of migration 0113 over the first code alone); the list's own CPV filter
-- is unchanged (any code).
--
-- Derived data of `opportunity_search`, written by the same trigger. The backfill sets about 394,000 rows on production (one
-- UPDATE of a narrow table, a minute or two on the 2-core host); idempotent.

ALTER TABLE opportunity_search ADD COLUMN IF NOT EXISTS main_heads TEXT[] NOT NULL DEFAULT '{}';

CREATE OR REPLACE FUNCTION dgate_opportunity_search_row() RETURNS trigger
    LANGUAGE plpgsql AS $f$
BEGIN
    INSERT INTO opportunity_search (id, title_en, title_original, buyer_name, cpv_heads, native_id, main_heads)
    VALUES (NEW.id, dg_fold(NEW.title_en), dg_fold(NEW.title_original),
            CASE WHEN NEW.buyer_withheld THEN NULL ELSE dg_fold(NEW.buyer_name_raw) END,
            dgate_cpv_heads(NEW.cpv_codes), NEW.native_id, dgate_cpv_heads(NEW.cpv_codes[1:1]))
    ON CONFLICT (id) DO UPDATE SET title_en = EXCLUDED.title_en, title_original = EXCLUDED.title_original,
        buyer_name = EXCLUDED.buyer_name, cpv_heads = EXCLUDED.cpv_heads, native_id = EXCLUDED.native_id,
        main_heads = EXCLUDED.main_heads;
    RETURN NULL;
END;
$f$;

UPDATE opportunity_search s SET main_heads = dgate_cpv_heads(o.cpv_codes[1:1])
  FROM opportunity o
 WHERE o.id = s.id AND s.main_heads IS DISTINCT FROM dgate_cpv_heads(o.cpv_codes[1:1]);

CREATE INDEX IF NOT EXISTS opportunity_search_main_heads ON opportunity_search USING gin (main_heads);

ANALYZE opportunity_search;
